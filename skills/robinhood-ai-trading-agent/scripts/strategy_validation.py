"""Promotion-evidence checks against explicit user-approved quantitative criteria.

Passing criteria is an operational eligibility decision, not proof of future profit.
Reports must be generated from retained market data and forward-paper journals.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

from research_analytics import number
from risk_engine import canonical_hash, timestamp


def evaluate_evidence(report, criteria, setup, version, now=None):
    now = now or datetime.now(timezone.utc)
    for key in ("test_min_trades", "forward_paper_min_trades"):
        value = number(criteria[key])
        if value < 1 or value != int(value):
            raise ValueError("Positive integer minimum trade counts required")
    if not 0 < number(criteria["max_drawdown"]) < 1:
        raise ValueError("Drawdown criterion must be between zero and one")
    if number(criteria["minimum_stress_cost_multiplier"]) < 1:
        raise ValueError("Cost stress cannot reduce assumed costs")
    if number(criteria["min_net_expectancy_per_trade"]) < 0:
        raise ValueError("Positive net expectancy is required for promotion")
    reasons = []
    if report.get("setup") != setup or report.get("version") != version:
        reasons.append("STRATEGY_VERSION_MISMATCH")
    if report.get("data_kind") != "market" or not report.get("input_hashes"):
        reasons.append("REAL_MARKET_DATA_EVIDENCE_REQUIRED")
    if report.get("data_audit_passed") is not True:
        reasons.append("STRATEGY_DATA_AUDIT_INCOMPLETE")
    windows = report["windows"]
    previous_end = None
    for name in ("development", "validation", "test", "forward_paper"):
        window = windows[name]
        start, end = timestamp(window["start"]), timestamp(window["end"])
        if start >= end or (previous_end is not None and start <= previous_end):
            reasons.append("STRATEGY_WINDOWS_OVERLAP_OR_INVALID")
        if end > now:
            reasons.append("STRATEGY_EVIDENCE_FROM_FUTURE")
        previous_end = end
    if report.get("test_was_used_for_selection") is not False or not report.get("variants_tried"):
        reasons.append("UNTOUCHED_TEST_OR_VARIANT_HISTORY_MISSING")
    for field in ("costs_included", "delisted_universe_handled", "no_lookahead_audit", "operational_failure_drills_passed"):
        if report.get(field) is not True:
            reasons.append(field.upper() + "_REQUIRED")
    if not report.get("benchmark") or not report.get("evidence_refs"):
        reasons.append("BENCHMARK_AND_RETAINED_REPORTS_REQUIRED")
    for phase, prefix in (("test_metrics", "test"), ("forward_paper_metrics", "forward_paper")):
        metrics = report[phase]
        trades = number(metrics["trades"])
        if trades < 0 or trades != int(trades) or not 0 <= number(metrics["max_drawdown"]) <= 1:
            raise ValueError("Invalid observed trade count/drawdown")
        if number(metrics["trades"]) < number(criteria[prefix + "_min_trades"]):
            reasons.append(prefix.upper() + "_TOO_FEW_TRADES")
        if number(metrics["max_drawdown"]) > number(criteria["max_drawdown"]):
            reasons.append(prefix.upper() + "_DRAWDOWN_EXCEEDS_CRITERION")
        if number(metrics["net_expectancy_per_trade"]) <= number(criteria["min_net_expectancy_per_trade"]):
            reasons.append(prefix.upper() + "_EXPECTANCY_INSUFFICIENT")
        if number(metrics["net_excess_return_vs_matched_benchmark"]) < number(criteria["min_excess_return"]):
            reasons.append(prefix.upper() + "_BENCHMARK_CRITERION_FAILED")
    if number(report["stress_cost_multiplier"]) < number(criteria["minimum_stress_cost_multiplier"]):
        reasons.append("INSUFFICIENT_COST_STRESS")
    if report.get("cost_stress_survived") is not True:
        reasons.append("COST_STRESS_FAILED")
    return {"eligible_for_promotion_review": not reasons, "reasons": sorted(set(reasons)),
            "report_hash": canonical_hash(report), "criteria_hash": canonical_hash(criteria),
            "setup": setup, "version": version,
            "caveat": "Host must verify retained evidence; thresholds and passing results do not prove an investment edge"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("criteria", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    result = evaluate_evidence(report, json.loads(args.criteria.read_text(encoding="utf-8-sig")), report["setup"], report["version"])
    print(json.dumps(result, indent=2))
    return 0 if result["eligible_for_promotion_review"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
