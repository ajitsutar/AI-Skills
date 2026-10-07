#!/usr/bin/env python3
"""Audit declared screening coverage and classify evidenced research judgments.

No network, financial-statement model, recommendation or order submission.
The caller verifies facts and supplies judgments; this helper enforces reporting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from price_audit import evidence, timestamp


REQUIRED_CHECKS = (
    "earnings_quality", "cash_support", "balance_sheet", "cycle_normalization",
    "structural_health", "valuation_growth", "analyst_evidence",
)


def review_run_spec(document):
    """Describe declared methodology; a hash is not a source/economic audit."""
    spec = document.get("run_spec")
    if spec is None:
        return {"status": "NOT_RECORDED", "spec_sha256": None,
                "limitations": "Legacy manifest: selection/ranking methodology not recorded"}
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("Unsupported run_spec schema")
    for key in ("run_id", "methodology_version", "mandate", "peer_policy",
                "discovery_policy", "deep_review_policy", "ranking_policy", "valuation_policy"):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError("run_spec requires " + key)
    timestamp(spec["defined_at"])
    if not evidence(spec.get("input_snapshot")):
        raise ValueError("run_spec requires input_snapshot evidence references")
    fields = spec.get("field_definitions")
    if (not isinstance(fields, dict) or not fields
            or any(not isinstance(k, str) or not k.strip() or not isinstance(v, str)
                   or not v.strip() for k, v in fields.items())):
        raise ValueError("run_spec requires field_definitions")
    changes = spec.get("changes")
    if not isinstance(changes, list) or any(not isinstance(c, str) or not c.strip() for c in changes):
        raise ValueError("run_spec changes must be a list of explained revisions/overrides")
    digest = hashlib.sha256(json.dumps(spec, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return {"status": "DECLARED", "spec_sha256": digest,
            "specification": spec,
            "limitations": "Validates declarations only; does not verify input files, sources, "
                           "when rules were chosen, economic merit or reproducibility of judgments"}


def review_report(document, candidates):
    """Prevent a declared eligible ranking from silently containing Watch names."""
    report = document.get("report")
    if report is None:
        return {"kind": "NOT_RECORDED", "ranked_symbols": [],
                "selection_rationale": {}, "execution_authorized": False}
    if not isinstance(report, dict) or report.get("kind") not in {
            "screened_hypotheses", "eligible_comparison"}:
        raise ValueError("report kind must be screened_hypotheses or eligible_comparison")
    symbols = report.get("ranked_symbols")
    if (not isinstance(symbols, list) or any(not isinstance(s, str) for s in symbols)
            or len(set(symbols)) != len(symbols)):
        raise ValueError("report ranked_symbols must be a unique list")
    by_symbol = {c["symbol"]: c for c in candidates}
    rationale = report.get("selection_rationale", {})
    if not isinstance(rationale, dict) or set(rationale) != set(symbols):
        raise ValueError("report requires selection_rationale for exactly the ranked symbols")
    for symbol in symbols:
        if symbol not in by_symbol:
            raise ValueError("Ranked symbol needs a retained candidate review: " + symbol)
        if not isinstance(rationale[symbol], str) or not rationale[symbol].strip():
            raise ValueError("Ranked symbol needs a selection rationale: " + symbol)
        if report["kind"] == "eligible_comparison" and by_symbol[symbol]["status"] != "Eligible":
            raise ValueError("Eligible comparison cannot include " + by_symbol[symbol]["status"] + ": " + symbol)
    return {"kind": report["kind"], "ranked_symbols": symbols,
            "selection_rationale": rationale, "execution_authorized": False}


def assess_candidate(candidate):
    """Keep fundamental rejection visible even when an event blocks entry."""
    checks = candidate.get("checks", {})
    reasons, states = [], []
    for name in REQUIRED_CHECKS:
        check = checks.get(name, {})
        state = check.get("status", "unresolved")
        if state not in {"pass", "unresolved", "material_risk", "fail"}:
            raise ValueError(f"Invalid status for {name}")
        if not check.get("reason") or not evidence(check.get("evidence")):
            state = "unresolved"
        states.append(state)
        if state != "pass":
            reasons.append({"check": name, "status": state,
                            "reason": check.get("reason") or "Missing review/evidence"})
    if "fail" in states:
        fundamental = "Reject"
    elif "material_risk" in states:
        fundamental = "Speculative"
    elif "unresolved" in states:
        fundamental = "Watch"
    else:
        fundamental = "Eligible"
    event = candidate.get("event_review", {})
    event_state = event.get("status", "unknown")
    if event_state not in {"clear", "blocked", "unknown"}:
        raise ValueError("Invalid event-review status")
    if not event.get("reason") or not evidence(event.get("evidence")):
        event_state = "unknown"
    # This reports a review, not a live freshness/calendar gate.
    display = fundamental
    if fundamental == "Eligible":
        if event_state == "blocked":
            display = "Event-blocked"
        elif event_state == "unknown":
            display = "Watch"
    return {"symbol": candidate["symbol"], "status": display,
            "fundamental_status": fundamental, "event_status": event_state,
            "unresolved_checks": sum(state == "unresolved" for state in states),
            "reasons": reasons, "event_reason": event.get("reason", "No event review"),
            "execution_authorized": False}


def review_screen(document):
    universe = document["universe"]
    if (not universe.get("name") or not universe.get("source")
            or not universe.get("scope_and_filters")):
        raise ValueError("Universe requires name, source and scope_and_filters")
    timestamp(universe["as_of"])
    symbols = universe["symbols"]
    if (not isinstance(symbols, list) or not symbols
            or any(not isinstance(s, str) or not s.strip() or s != s.strip() for s in symbols)
            or len(set(symbols)) != len(symbols)):
        raise ValueError("Universe must contain nonempty unique exact security identifiers")
    expected, seen, rows = set(symbols), set(), document.get("screening", [])
    counts = Counter()
    for row in rows:
        symbol = row["symbol"]
        if symbol not in expected or symbol in seen:
            raise ValueError("Duplicate or out-of-universe screening row: " + symbol)
        seen.add(symbol)
        outcome = row["outcome"]
        if outcome not in {"retained", "excluded", "not_advanced", "missing_data"}:
            raise ValueError("Invalid screening outcome")
        if not row.get("reason"):
            raise ValueError("Every screening row requires a reason")
        if outcome != "missing_data" and not evidence(row.get("evidence")):
            raise ValueError("Screened rows need evidence; otherwise mark missing_data")
        counts[outcome] += 1
    reviewed, candidates = set(), []
    retained = {row["symbol"] for row in rows if row["outcome"] == "retained"}
    for candidate in document.get("candidates", []):
        symbol = candidate["symbol"]
        if symbol in reviewed or symbol not in retained:
            raise ValueError("Candidate reviews must be unique retained screening rows")
        reviewed.add(symbol)
        candidates.append(assess_candidate(candidate))
    absent = sorted(expected - seen)
    methodology = review_run_spec(document)
    report = review_report(document, candidates)
    return {"universe": {key: universe[key] for key in ("name", "source", "as_of", "scope_and_filters")},
            "coverage": {"expected_securities": len(expected), "retrieved_rows": len(seen),
                         "screened_with_evidence": counts["retained"] + counts["excluded"] + counts["not_advanced"],
                         "retained": counts["retained"], "excluded": counts["excluded"],
                         "not_advanced": counts["not_advanced"],
                         "missing_data": counts["missing_data"], "absent_symbols": absent,
                         "candidate_reviews": len(candidates),
                         "retained_without_review": sorted(retained - reviewed),
                         "all_constituents_screened": not absent and counts["missing_data"] == 0},
            "candidates": candidates,
            "methodology": methodology, "report": report,
            "status_counts": dict(Counter(c["status"] for c in candidates)),
            "execution_authorized": False,
            "limitations": "Checks declared coverage/judgments only; does not verify universe membership, sources or current events"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", help="Offline screening manifest with evidence references")
    args = parser.parse_args()
    result = review_screen(json.loads(Path(args.json).read_text(encoding="utf-8-sig")))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
