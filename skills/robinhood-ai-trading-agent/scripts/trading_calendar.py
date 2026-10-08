"""Exchange sessions and deterministic event-window/data-coverage checks.

exchange_calendars is a calendar library, not a live exchange-status feed.
Always compare today's session/halts with broker evidence before execution.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from risk_engine import canonical_hash, timestamp, positive


def sessions(start, end, exchange="XNYS"):
    import exchange_calendars as xcals
    first, last = str(start)[:10], str(end)[:10]
    if first > last:
        raise ValueError("Calendar range is reversed")
    # The library needs a nonempty construction range even for a holiday query.
    lower = (datetime.fromisoformat(first) - timedelta(days=7)).date().isoformat()
    upper = (datetime.fromisoformat(last) + timedelta(days=7)).date().isoformat()
    cal = xcals.get_calendar(exchange, start=lower, end=upper)
    return [{"date": day.date().isoformat(), "open": row["open"].isoformat(),
             "close": row["close"].isoformat()}
            for day, row in cal.schedule.loc[first:last].iterrows()]


def session_for(when, exchange="XNYS"):
    when = timestamp(when) if isinstance(when, str) else when
    day = when.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    records = sessions(day, day, exchange)
    if not records:
        return {"is_trading_day": False, "date": day, "exchange": exchange}
    return {"is_trading_day": True, "exchange": exchange, **records[0]}


def audit_timestamps(observed, start_date, end_date, interval_minutes=None,
                     through=None, exchange="XNYS"):
    """Daily observations label session close; intraday observations label bar END.

    start_date/end_date define requested coverage, not merely the rows received.
    through supports an in-progress session using only fully completed bars.
    """
    actual = [timestamp(t) if isinstance(t, str) else t for t in observed]
    if len(set(actual)) != len(actual) or actual != sorted(actual):
        raise ValueError("Duplicate or unordered price timestamps")
    if interval_minutes is not None and (isinstance(interval_minutes, bool)
            or int(interval_minutes) != interval_minutes or interval_minutes < 1):
        raise ValueError("Intraday interval must be a positive whole minute count")
    cutoff = timestamp(through) if isinstance(through, str) else through
    expected = []
    for session in sessions(start_date, end_date, exchange):
        opening, closing = timestamp(session["open"]), timestamp(session["close"])
        if interval_minutes is None:
            expected.append(closing)
        else:
            step = timedelta(minutes=interval_minutes)
            if (closing - opening).total_seconds() % step.total_seconds():
                raise ValueError("Interval does not partition this session; explicit partial-bar handling required")
            current = opening + step
            while current <= closing:
                expected.append(current)
                current += step
    if cutoff is not None:
        expected = [t for t in expected if t <= cutoff]
    missing, unexpected = set(expected) - set(actual), set(actual) - set(expected)
    return {"complete": bool(expected) and not missing and not unexpected,
            "expected_rows": len(expected), "observed_rows": len(actual),
            "missing": sorted(t.isoformat() for t in missing),
            "unexpected": sorted(t.isoformat() for t in unexpected),
            "exchange": exchange, "calendar_source": "exchange_calendars; confirm live session with broker"}


def event_gate(document, symbol, policy, now=None, hold_until=None, entry_at=None):
    """Assess a sourced, freshness-limited event list against session-based policy.

    Entries have kind, earliest_at, latest_at, evidence. Date-only events must be
    supplied as the whole credible interval in the issuer's timezone.
    """
    now = now or datetime.now(timezone.utc)
    hold_until = timestamp(hold_until) if isinstance(hold_until, str) else (hold_until or now)
    entry = timestamp(entry_at) if isinstance(entry_at, str) else (entry_at or now)
    scope = policy.get("scope", "entry_and_hold")  # Preserve the strict live-policy default.
    if scope == "holding_window":  # Existing approved personal policies use this spelling.
        scope = "entry_and_hold"
    if scope not in {"entry_only", "entry_and_hold"}:
        raise ValueError("Event scope must be entry_only or entry_and_hold")
    reasons, blocked, holding_events = [], [], []
    if entry < now or hold_until < entry:
        raise ValueError("Holding window ends before the decision")
    if timestamp(document["coverage_start"]) > timestamp(document["coverage_end"]):
        raise ValueError("Event coverage interval is reversed")
    before, after = policy["before_sessions"], policy["after_sessions"]
    if any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 60 for v in (before, after)):
        raise ValueError("Event window requires 0..60 whole sessions")
    if document["symbol"] != symbol or not document.get("source") or document.get("coverage_verified") is not True:
        reasons.append("EVENT_SOURCE_OR_COVERAGE_UNVERIFIED")
    checked = timestamp(document["checked_at"])
    max_age = float(positive(policy["max_age_seconds"]))
    if max_age <= 0 or not 0 <= (now - checked).total_seconds() <= max_age:
        reasons.append("EVENT_CALENDAR_STALE_OR_FUTURE")
    earliest = min(entry, timestamp(document["coverage_start"]))
    latest = max(hold_until, timestamp(document["coverage_end"]))
    schedule = sessions((earliest - timedelta(days=180)).date().isoformat(),
                        (latest + timedelta(days=180)).date().isoformat(), policy.get("exchange", "XNYS"))
    dates = [s["date"] for s in schedule]
    local_zone = ZoneInfo("America/New_York")

    def date_index(when, direction):
        day = when.astimezone(local_zone).date().isoformat()
        choices = [i for i, value in enumerate(dates) if value <= day] if direction == "previous" else [
            i for i, value in enumerate(dates) if value >= day]
        if not choices:
            raise ValueError("Event is outside calendar coverage")
        return choices[-1] if direction == "previous" else choices[0]

    # Need lookahead because an event after hold_until can begin its blackout earlier.
    lookahead = date_index(hold_until, "next") + before + 1
    needed_end = timestamp(schedule[lookahead]["close"])
    lookback = date_index(entry, "previous") - after - 1
    needed_start = timestamp(schedule[lookback]["open"])
    if timestamp(document["coverage_start"]) > needed_start or timestamp(document["coverage_end"]) < needed_end:
        reasons.append("EVENT_COVERAGE_INCOMPLETE")
    if not isinstance(document["events"], list):
        raise ValueError("events must be an explicit list, even when empty")
    for event in document["events"]:
        if not isinstance(event.get("evidence"), list) or not event["evidence"] or any(
                not isinstance(ref, str) or not ref.strip() for ref in event["evidence"]):
            reasons.append("EVENT_WITHOUT_SOURCE_EVIDENCE")
        begin, end = timestamp(event["earliest_at"]), timestamp(event["latest_at"])
        if begin > end:
            raise ValueError("Event date interval is reversed")
        if begin <= hold_until and end >= entry:
            holding_events.append({"kind": event["kind"], "earliest_at": begin.isoformat(),
                                   "latest_at": end.isoformat(), "evidence": event.get("evidence", []),
                                   "certainty": event.get("certainty", "unknown")})
        if event["kind"] not in policy["blocked_kinds"]:
            continue
        start_index, end_index = date_index(begin, "previous") - before, date_index(end, "next") + after
        if start_index < 0 or end_index >= len(schedule):
            raise ValueError("Event blackout exceeds calendar coverage")
        block_start, block_end = timestamp(schedule[start_index]["open"]), timestamp(schedule[end_index]["close"])
        gate_end = entry if scope == "entry_only" else hold_until
        if block_start <= gate_end and block_end >= entry:
            blocked.append({"kind": event["kind"], "start": block_start.isoformat(), "end": block_end.isoformat(),
                            "evidence": event.get("evidence", []), "certainty": event.get("certainty", "unknown")})
    if blocked:
        reasons.append("EVENT_BLACKOUT_OVERLAPS_ENTRY_OR_HOLD")
    return {"clear": not reasons, "symbol": symbol, "checked_at": now.isoformat(),
            "entry_at": entry.isoformat(), "hold_until": hold_until.isoformat(), "scope": scope,
            "reasons": sorted(set(reasons)), "blackouts": blocked, "holding_events": holding_events,
            "input_hash": canonical_hash(document), "policy_hash": canonical_hash(policy)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    session = sub.add_parser("session")
    session.add_argument("--at")
    events = sub.add_parser("events")
    events.add_argument("input", type=Path)
    events.add_argument("policy", type=Path)
    events.add_argument("--as-of")
    events.add_argument("--hold-until")
    args = parser.parse_args()
    if args.command == "session":
        result = session_for(timestamp(args.at) if args.at else datetime.now(timezone.utc))
    else:
        document = json.loads(args.input.read_text(encoding="utf-8-sig"))
        result = event_gate(document, document["symbol"], json.loads(args.policy.read_text(encoding="utf-8-sig")),
                            timestamp(args.as_of) if args.as_of else None, args.hold_until)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
