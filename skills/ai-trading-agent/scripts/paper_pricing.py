"""As-of paper marks and common-anchor checks on retained, single-series captures."""
import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo


def session(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Use an ISO calendar date for the trading session")
    return parsed


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.utcoffset() is None:
        raise ValueError("A timestamp with UTC offset is required")
    return result


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def required_text(record, name):
    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing " + name)
    return value


def exchange_close(data, day, zone):
    stamp = data.get("session_closes", {}).get(day.isoformat())
    if day.isoformat() == data["session"] and "session_close_at" in data:
        if stamp is not None and instant(stamp) != instant(data["session_close_at"]):
            raise ValueError("Conflicting exchange close timestamps")
        stamp = data["session_close_at"]
    if stamp is None:
        if zone.key != "America/New_York":
            raise ValueError("Supply exchange closing timestamps for all sessions")
        return datetime.combine(day, time(16), zone)
    closing = instant(stamp)
    if closing.astimezone(zone).date() != day:
        raise ValueError("Closing timestamp must refer to its exchange session")
    return closing


def series(data):
    """Each row declares its series identity. A changed/null capture remains visible."""
    identity = {key: required_text(data, key) for key in ("symbol", "currency", "basis", "provider")}
    target = session(data["session"])
    cutoff = instant(data["as_of"])
    zone = ZoneInfo(data.get("session_timezone", "America/New_York"))
    close_time = exchange_close(data, target, zone)
    if close_time > cutoff:
        raise ValueError("The requested session must have closed by the supplied cutoff")
    history = defaultdict(dict)
    for row in data["bars"]:
        if any(row.get(key) != value for key, value in identity.items()):
            raise ValueError("Mixed symbol, currency, price basis or provider")
        day = session(row["session"])
        when = instant(row["observed_at"])
        if day > target or when > cutoff:
            continue
        if when < exchange_close(data, day, zone):
            raise ValueError("A closing mark was captured before the session closed")
        source = required_text(row, "source_id")
        price = row["close"]
        if price is not None and not positive(price):
            raise ValueError("Close must be positive and finite, or explicitly null")
        capture = {"close": price, "observed_at": row["observed_at"], "source_id": source}
        if when in history[day] and capture != history[day][when]:
            raise ValueError("Ambiguous price captures at one timestamp")
        history[day][when] = capture
    current = {}
    revisions = []
    for day, captures in sorted(history.items()):
        ordered = [captures[key] for key in sorted(captures)]
        current[day] = ordered[-1]
        for previous, updated in zip(ordered, ordered[1:]):
            if previous["close"] != updated["close"]:
                revisions.append({"session": day.isoformat(), "before": previous, "after": updated})
    return identity, target, cutoff, current, revisions, close_time


def paper_mark(data):
    identity, day, cutoff, current, revisions, close_time = series(data)
    out = {**identity, "requested_session": day.isoformat(), "as_of": data["as_of"],
           "revisions": revisions, "executable_price": False, "carried": False, "close": None}
    latest = current.get(day)
    if latest and latest["close"] is not None:
        return {**out, **latest, "status": "OBSERVED", "last_bar_session": day.isoformat()}
    prior = [d for d in current if d < day and current[d]["close"] is not None]
    if not prior:
        return {**out, "status": "NO_PRIOR_MARK"}
    last = max(prior)
    out.update(last_bar_session=last.isoformat(), prior_observation=current[last])
    check = data.get("status_check") or {}
    if (check.get("symbol") != identity["symbol"] or check.get("session") != day.isoformat()
            or not isinstance(check.get("source_id"), str) or not check["source_id"].strip()
            or not check.get("observed_at")):
        return {**out, "status": "NEEDS_SAME_SESSION_HALT_DELIST_CHECK"}
    checked = instant(check["observed_at"])
    if checked < close_time or checked > cutoff or checked.astimezone(ZoneInfo(data.get("session_timezone", "America/New_York"))).date() != day:
        return {**out, "status": "STATUS_CHECK_OUTSIDE_CUTOFF"}
    out["status_check"] = check
    if check.get("status") != "NO_HALT_OR_DELISTING_OBSERVED":
        return {**out, "status": "UNRESOLVED_SECURITY_STATUS"}
    return {**out, "close": current[last]["close"], "carried": True, "status": "CARRIED_FOR_VALUATION"}


def common_anchor(data):
    """Sessions must be completed exchange sessions in newest-first order."""
    days = [session(d) for d in data["completed_sessions"]]
    if not days or days != sorted(set(days), reverse=True) or days[0] != session(data["requested_session"]):
        raise ValueError("Start with the requested completed session; supply unique earlier sessions in order")
    symbols = data["universe"]
    if not isinstance(symbols, list) or not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("An explicit unique frozen universe is required")
    for key in ("provider", "basis", "currency"):
        required_text(data, key)
    series_by_symbol = {}
    for packet in data["series"]:
        for key in ("provider", "basis", "currency", "as_of"):
            if packet[key] != data[key]:
                raise ValueError("Mixed anchor panel conventions")
        if packet.get("session_timezone", "America/New_York") != data.get("session_timezone", "America/New_York"):
            raise ValueError("Mixed session timezones")
        if packet.get("session_close_at") != data.get("session_close_at"):
            raise ValueError("Mixed session closes")
        if packet.get("session_closes", {}) != data.get("session_closes", {}):
            raise ValueError("Mixed historical session closes")
        if packet["session"] != data["requested_session"] or packet["symbol"] in series_by_symbol:
            raise ValueError("Duplicate symbol or inconsistent requested anchor")
        series_by_symbol[packet["symbol"]] = series(packet)[3]
    if set(series_by_symbol) != set(symbols):
        raise ValueError("Supply a series, possibly empty, for each frozen universe member")
    attempts = []
    trigger = data.get("fallback_max_coverage_fraction", 0)
    if type(trigger) not in (int, float) or not 0 <= trigger < 1:
        raise ValueError("Fallback coverage trigger must be a fraction from zero up to, excluding, one")
    for day in days:
        missing = sorted(s for s in symbols if series_by_symbol[s].get(day, {}).get("close") is None)
        attempts.append({"session": day.isoformat(), "missing": missing})
        if not missing:
            return {"status": "READY", "requested_session": data["requested_session"],
                    "actual_session": day.isoformat(), "coverage": attempts}
        if data.get("allow_previous_complete") is not True:
            break
        # Only the requested date triggers fallback. Earlier dates must cover every name.
        if day == days[0] and (len(symbols) - len(missing)) / len(symbols) > trigger:
            break
    return {"status": "ANCHOR_INCOMPLETE", "requested_session": data["requested_session"],
            "actual_session": None, "coverage": attempts}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["mark", "anchor"])
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8-sig"))
    answer = (paper_mark if args.operation == "mark" else common_anchor)(document)
    print(json.dumps(answer, indent=2, allow_nan=False))
    raise SystemExit(0 if answer["status"] in ("OBSERVED", "CARRIED_FOR_VALUATION", "READY") else 2)
