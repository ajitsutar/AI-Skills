"""Offline fixed-horizon research checks. No market data fetch or order authority.

Dates use US equity exchange sessions. Evidence references are declarations, not
authenticated facts. This module does not estimate return probabilities.
"""
from __future__ import annotations

import calendar
import argparse
import json
import math
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from price_audit import evidence, timestamp
from trading_calendar import event_gate, sessions


HORIZON_CHECKS = ("thesis_timing", "terminal_valuation", "downside_liquidity",
                  "portfolio_fit", "exit_plan")
ZONE = ZoneInfo("America/New_York")


def iso_date(value):
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError("Use exact YYYY-MM-DD dates")
    return result


def finite(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < minimum:
        raise ValueError(name + " must be a finite number >= " + str(minimum))
    return value


def resolve_horizon(spec):
    """Resolve a proposed fill and hard exit; any actual fill change needs rerun."""
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("fixed_horizon requires horizon schema_version 1")
    as_of, entry, latest = (timestamp(spec[k]) for k in ("as_of", "entry_at", "latest_entry_at"))
    if not as_of <= entry <= latest:
        raise ValueError("Require as_of <= proposed entry <= latest entry")
    mode = spec.get("deadline_mode")
    if mode not in {"fixed_end", "rolling_from_entry"}:
        raise ValueError("Declare fixed_end or rolling_from_entry")
    if spec.get("early_exit_policy") not in {"risk_exits_allowed", "strict_hold"}:
        raise ValueError("Declare early_exit_policy")
    if spec.get("non_session_exit") != "previous_session":
        raise ValueError("A hard exit uses the previous session, never a later session")
    buffer = spec.get("exit_buffer_minutes")
    if isinstance(buffer, bool) or not isinstance(buffer, int) or not 1 <= buffer <= 120:
        raise ValueError("exit_buffer_minutes must be 1..120 whole minutes")
    if not evidence(spec.get("calendar_evidence")):
        raise ValueError("Retain calendar_evidence; library sessions are not live status")
    confirmed_through = iso_date(spec["calendar_confirmed_through"])
    route = spec.get("strategy_route")
    if route not in {"intraday", "swing", "long_term"}:
        raise ValueError("Declare strategy_route intraday, swing or long_term")
    exchange = spec.get("exchange", "XNYS")
    if exchange not in {"XNYS", "XNAS"}:
        raise ValueError("This helper supports US equity calendars XNYS/XNAS only")
    entry_day, latest_day = (t.astimezone(ZONE).date() for t in (entry, latest))
    for when, day in ((entry, entry_day), (latest, latest_day)):
        row = sessions(day, day, exchange)
        if not row or not timestamp(row[0]["open"]) <= when < timestamp(row[0]["close"]):
            raise ValueError("Proposed/latest entry must be inside a regular exchange session")
    anchor = iso_date(spec["anchor_date"])
    if anchor > entry_day or (mode == "rolling_from_entry" and anchor != entry_day):
        raise ValueError("Fixed anchor cannot follow entry; rolling anchor must equal entry date")
    duration = spec["duration"]
    unit, count = duration.get("unit"), duration.get("value")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("Duration must be positive whole units; normalize fractions into smaller units")
    if unit not in {"same_session", "elapsed_minutes", "elapsed_hours", "calendar_days",
                    "calendar_weeks", "calendar_months", "calendar_years", "trading_sessions"}:
        raise ValueError("Unsupported duration unit")
    if unit == "same_session" and count != 1:
        raise ValueError("same_session uses value 1; multiple sessions use trading_sessions")
    anchor_at = timestamp(spec["anchor_at"]) if unit in {"elapsed_minutes", "elapsed_hours"} else None
    if anchor_at and (anchor_at > entry or anchor_at.astimezone(ZONE).date() != anchor
                      or (mode == "rolling_from_entry" and anchor_at != entry)):
        raise ValueError("Elapsed-time anchor must match the anchor date and deadline mode")

    def exit_for(origin, instant=None):
        raw_instant = None
        if unit in {"elapsed_minutes", "elapsed_hours"}:
            raw_instant = instant + timedelta(minutes=count * (60 if unit == "elapsed_hours" else 1))
            deadline = raw_instant.astimezone(ZONE).date()
        elif unit == "same_session":
            deadline = origin
        elif unit in {"calendar_days", "calendar_weeks"}:
            deadline = origin + timedelta(days=count * (7 if unit == "calendar_weeks" else 1))
        elif unit in {"calendar_months", "calendar_years"}:
            month = origin.year * 12 + origin.month - 1 + count * (12 if unit == "calendar_years" else 1)
            year, month = divmod(month, 12)
            month += 1
            deadline = date(year, month, min(origin.day, calendar.monthrange(year, month)[1]))
        else:
            # Entry/anchor is day zero; count subsequent trading sessions.
            future = sessions(origin + timedelta(days=1), origin + timedelta(days=count * 3 + 30), exchange)
            if len(future) < count:
                raise ValueError("Insufficient exchange calendar coverage")
            deadline = iso_date(future[count - 1]["date"])
        preceding = sessions(deadline - timedelta(days=14), deadline, exchange)
        if raw_instant:
            preceding = [row for row in preceding if timestamp(row["open"]) < raw_instant]
        if not preceding:
            raise ValueError("No exit session before the deadline")
        row = preceding[-1]
        boundary = min(timestamp(row["close"]), raw_instant) if raw_instant else timestamp(row["close"])
        exit_at = boundary - timedelta(minutes=buffer)
        if exit_at <= timestamp(row["open"]):
            raise ValueError("Exit buffer consumes the session")
        return deadline, row["date"], exit_at

    raw, exit_day, exit_at = exit_for(anchor, anchor_at)
    if entry >= exit_at or (mode == "fixed_end" and latest >= exit_at):
        raise ValueError("Entry window must precede the fixed exit deadline")
    latest_exit = exit_for(latest_day, latest)[2] if mode == "rolling_from_entry" else exit_at
    if route == "intraday" and (iso_date(exit_day) != entry_day
            or latest_exit.astimezone(ZONE).date() != latest_day):
        raise ValueError("Intraday positions must exit in their entry session; use swing for overnight risk")
    return {"as_of": as_of.isoformat(), "entry_at": entry.isoformat(),
            "latest_entry_at": latest.isoformat(), "deadline_mode": mode,
            "duration": duration, "strategy_route": route, "anchor_date": anchor.isoformat(),
            "raw_deadline_date": raw.isoformat(), "exit_session": exit_day,
            "exit_at": exit_at.isoformat(), "latest_possible_exit_at": latest_exit.isoformat(),
            "planned_calendar_days": (iso_date(exit_day) - entry_day).days,
            "subsequent_sessions": (len(sessions(entry_day + timedelta(days=1), exit_day, exchange))
                                    if iso_date(exit_day) > entry_day else 0),
            "early_exit_policy": spec["early_exit_policy"], "exchange": exchange,
            "calendar_status": "PROVISIONAL" if latest_exit.astimezone(ZONE).date() > confirmed_through else "DECLARED_CONFIRMED",
            "calendar_refresh_required": latest_exit.astimezone(ZONE).date() > confirmed_through,
            "execution_authorized": False,
            "limitations": "Calendar calculation and declared evidence only; no guaranteed fill or settlement"}


def review_primary(section, as_of):
    """Latest known report must be the report actually reviewed, as of this run."""
    if not isinstance(section, dict) or not section:
        return ["PRIMARY_REVIEW_MISSING"]
    if not section.get("reason") or not evidence(section.get("evidence")):
        return ["PRIMARY_REVIEW_UNSOURCED"]
    if section.get("status") != "reviewed":
        return ["PRIMARY_REVIEW_UNRESOLVED"]
    published, checked = (timestamp(section[k]) for k in ("latest_published_at", "checked_at"))
    latest, reviewed = (iso_date(section[k]) for k in ("latest_public_period_end", "reviewed_period_end"))
    reasons = []
    if not published <= checked <= as_of or latest > published.date():
        reasons.append("PRIMARY_PUBLICATION_OR_CHECK_TIME_INVALID")
    if latest != reviewed:
        reasons.append("LATEST_FINANCIAL_PERIOD_NOT_REVIEWED")
    if (as_of - checked).total_seconds() > 86400:
        reasons.append("PRIMARY_LATEST_REPORT_CHECK_NOT_CURRENT_FOR_RUN")
    return reasons


def review_scenarios(section, resolved):
    if not isinstance(section, dict) or not section:
        return {"complete": False, "reasons": ["TERMINAL_SCENARIOS_MISSING"]}
    if not evidence(section.get("evidence")) or not evidence(section.get("cash_benchmark_evidence")):
        return {"complete": False, "reasons": ["SCENARIO_OR_CASH_BENCHMARK_EVIDENCE_MISSING"]}
    if timestamp(section["exit_at"]) != timestamp(resolved["exit_at"]):
        return {"complete": False, "reasons": ["SCENARIOS_USE_DIFFERENT_EXIT"]}
    entry = finite(section["entry_price"], "entry_price")
    if entry == 0:
        raise ValueError("entry_price must be positive")
    costs = finite(section["round_trip_cost_bps"], "round_trip_cost_bps") / 10000
    cash = finite(section["cash_benchmark_return"], "cash_benchmark_return", -1)
    cases = section.get("cases")
    if not isinstance(cases, list) or [c.get("name") for c in cases] != ["downside", "base", "upside"]:
        raise ValueError("Provide downside, base, upside scenarios in that order")
    output = []
    for case in cases:
        if "probability" in case or "probabilities" in section or "expected_return" in section:
            raise ValueError("This helper does not validate probabilities or expected returns")
        if not case.get("assumptions") or not evidence(case.get("evidence")):
            return {"complete": False, "reasons": ["SCENARIO_ASSUMPTIONS_OR_EVIDENCE_MISSING"]}
        terminal = finite(case["terminal_price"], "terminal_price")
        distributions = finite(case["distributions_per_share"], "distributions_per_share")
        net = (terminal + distributions) / entry - 1 - costs
        if not math.isfinite(net) or not math.isfinite(net - cash):
            raise ValueError("Scenario return arithmetic must remain finite")
        output.append({"name": case["name"], "net_return": net,
                       "excess_over_cash": net - cash, "assumptions": case["assumptions"]})
    if [c["net_return"] for c in output] != sorted(c["net_return"] for c in output):
        raise ValueError("Scenario terminal payoffs must be ordered downside <= base <= upside")
    return {"complete": True, "reasons": [], "cases": output,
            "exit_at": resolved["exit_at"], "probability_of_profit": None,
            "limitations": "Assumption-driven terminal outcomes, not forecasts or calibrated probabilities"}


def review_horizon_candidate(candidate, spec, resolved):
    review = candidate.get("horizon_review", {})
    reasons = review_primary(candidate.get("primary_review"), timestamp(resolved["as_of"]))
    states = []
    for name in HORIZON_CHECKS:
        check = review.get("checks", {}).get(name, {})
        state = check.get("status", "unresolved")
        if state not in {"pass", "unresolved", "material_risk", "fail"}:
            raise ValueError("Invalid horizon check status: " + name)
        if not check.get("reason") or not evidence(check.get("evidence")):
            state = "unresolved"
        states.append(state)
        if state != "pass":
            reasons.append(name + ": " + state + ": " + (check.get("reason") or "Missing evidence"))
    scenarios = review_scenarios(review.get("terminal_scenarios"), resolved)
    reasons.extend(scenarios["reasons"])
    events, policy = review.get("event_calendar"), spec.get("event_policy")
    if not isinstance(policy, dict) or policy.get("scope") not in {"entry_only", "entry_and_hold"}:
        raise ValueError("Fixed-horizon event_policy requires explicit scope")
    if policy.get("exchange", resolved["exchange"]) != resolved["exchange"]:
        raise ValueError("Event and horizon exchange must match")
    coverage = policy.get("coverage_mode")
    if coverage not in {"full_hold", "rolling_review"}:
        raise ValueError("Declare event coverage_mode full_hold or rolling_review")
    event_end = resolved["exit_at"]
    if coverage == "rolling_review":
        schedule = spec.get("review_schedule", {})
        if policy["scope"] != "entry_only":
            raise ValueError("Rolling review cannot certify no prohibited events over the entire hold")
        if not schedule.get("cadence") or not evidence(schedule.get("evidence")):
            raise ValueError("Rolling event coverage needs an evidenced review_schedule")
        next_review = timestamp(schedule["next_review_at"])
        if not timestamp(resolved["entry_at"]) < next_review <= timestamp(resolved["exit_at"]):
            raise ValueError("Next review must be after entry and no later than exit")
        event_end = next_review.isoformat()
    if events is None:
        event_result = {"clear": False, "reasons": ["EVENT_CALENDAR_MISSING"], "blackouts": []}
    else:
        event_result = event_gate(events, candidate["symbol"], {**policy, "exchange": resolved["exchange"]},
                                  now=timestamp(resolved["as_of"]), hold_until=event_end,
                                  entry_at=resolved["entry_at"])
    event_status = "clear" if event_result["clear"] else (
        "blocked" if event_result["blackouts"] else "unknown")
    reasons.extend(event_result["reasons"])
    status = ("Reject" if "fail" in states else "Speculative" if "material_risk" in states else
              "Watch" if any(s == "unresolved" for s in states) or not scenarios["complete"]
              or review_primary(candidate.get("primary_review"), timestamp(resolved["as_of"]))
              else "Eligible")
    return {"status": status, "event_status": event_status, "reasons": reasons,
            "terminal_scenarios": scenarios, "events": event_result,
            "event_coverage_mode": coverage, "events_beyond_review": "UNASSESSED" if coverage == "rolling_review" else "DECLARED_COVERED",
            "execution_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", help="Horizon contract, or screen manifest containing horizon")
    args = parser.parse_args()
    document = json.loads(Path(args.json).read_text(encoding="utf-8-sig"))
    print(json.dumps(resolve_horizon(document.get("horizon", document)), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
