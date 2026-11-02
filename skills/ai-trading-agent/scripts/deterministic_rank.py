"""Deterministic numeric discovery order and evidence-gated research selection.

The user/run profile supplies metrics, scales, filters and weights. This module
does not invent an investment strategy, fetch facts, or estimate expected returns.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, localcontext

from price_audit import evidence, timestamp


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("Ranking numbers must be finite decimal values")
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError("Ranking numbers must be finite decimal values") from exc
    if not result.is_finite():
        raise ValueError("Ranking numbers must be finite decimal values")
    return result


def rank_screen(document, reviews):
    with localcontext() as context:
        context.prec = 40
        return _rank_screen(document, reviews)


def _rank_screen(document, reviews):
    spec = document.get("ranking_spec")
    if spec is None:
        return {"status": "NOT_CONFIGURED", "selected_symbols": [],
                "limitations": "No reproducible numeric selection rule was supplied"}
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("ranking_spec requires schema_version 1")
    for field in ("profile_id", "profile_version", "snapshot_id"):
        if not isinstance(spec.get(field), str) or not spec[field].strip():
            raise ValueError("ranking_spec requires " + field)
    if spec.get("missing_data_policy") != "exclude" or spec.get("tie_break") != "symbol_ascending":
        raise ValueError("Ranking requires missing_data_policy=exclude and tie_break=symbol_ascending")
    cutoff = timestamp(document.get("research_as_of") or document.get("horizon", {}).get("as_of"))
    if timestamp(spec["as_of"]) != cutoff:
        raise ValueError("ranking_spec.as_of must match the research cutoff")
    age = spec.get("max_age_seconds")
    if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
        raise ValueError("ranking_spec.max_age_seconds must be a positive integer")
    count, group_cap = spec.get("selection_count"), spec.get("max_per_group")
    for field, value in (("selection_count", count), ("max_per_group", group_cap)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
            raise ValueError("ranking_spec." + field + " must be null or a positive integer")
    allowed = spec.get("allowed_statuses")
    if not isinstance(allowed, list) or not allowed or len(set(allowed)) != len(allowed) or set(allowed) - {"Eligible", "Speculative"}:
        raise ValueError("ranking_spec.allowed_statuses permits Eligible and explicitly chosen Speculative only")
    minimum = number(spec["minimum_score"])
    if not 0 <= minimum <= 1:
        raise ValueError("ranking_spec.minimum_score must be between 0 and 1")
    criteria = spec.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("ranking_spec.criteria cannot be empty")
    fields, weights = set(), []
    for criterion in criteria:
        metric = criterion["metric"]
        if not isinstance(metric, str) or not metric.strip() or metric in fields:
            raise ValueError("Ranking criteria need unique nonempty metric names")
        fields.add(metric)
        weight = number(criterion["weight"])
        if weight <= 0 or number(criterion["high"]) <= number(criterion["low"]):
            raise ValueError("Ranking weights must be positive and high must exceed low")
        if criterion["direction"] not in {"higher", "lower"}:
            raise ValueError("Ranking direction must be higher or lower")
        weights.append(weight)
    if sum(weights) != Decimal(1):
        raise ValueError("Ranking weights must sum exactly to 1")
    filters = spec.get("filters")
    if not isinstance(filters, list):
        raise ValueError("ranking_spec.filters must be an explicit list")
    for gate in filters:
        if gate.get("operator") not in {"ge", "le"} or not isinstance(gate.get("metric"), str):
            raise ValueError("Numeric discovery filters require metric and operator ge/le")
        number(gate["value"])
        fields.add(gate["metric"])
    definitions = spec.get("field_definitions", {})
    for metric in fields:
        definition = definitions.get(metric, {})
        if any(not isinstance(definition.get(key), str) or not definition[key].strip()
               for key in ("unit", "period", "basis", "normalization")) or not evidence(definition.get("source_priority")):
            raise ValueError("ranking_spec.field_definitions." + metric + " needs unit, period, basis, normalization and source_priority")
    rows = document.get("ranking_inputs")
    if not isinstance(rows, list):
        raise ValueError("ranking_inputs must contain the frozen numeric snapshot")
    universe = set(document["universe"]["symbols"])
    symbols = [r["symbol"] for r in rows]
    if len(symbols) != len(set(symbols)) or set(symbols) != universe:
        raise ValueError("ranking_inputs must cover every exact universe symbol once, including missing-data rows")
    by_symbol = {r["symbol"]: r for r in reviews}
    scored, exclusions = [], []
    with localcontext() as ctx:
        ctx.prec = 40
        for row in rows:
            symbol, metrics = row["symbol"], row.get("metrics", {})
            reason = None
            if not evidence(row.get("evidence")) or not row.get("observed_at"):
                reason = "SNAPSHOT_EVIDENCE_MISSING"
            elif not 0 <= (cutoff - timestamp(row["observed_at"])).total_seconds() <= age:
                reason = "SNAPSHOT_STALE_OR_FUTURE"
            elif any(metrics.get(field) is None for field in fields):
                reason = "METRICS_MISSING"
            if reason:
                exclusions.append({"symbol": symbol, "reason": reason})
                continue
            values = {field: number(metrics[field]) for field in fields}
            failed = [g["metric"] for g in filters if
                      (g["operator"] == "ge" and values[g["metric"]] < number(g["value"])) or
                      (g["operator"] == "le" and values[g["metric"]] > number(g["value"]))]
            if failed:
                exclusions.append({"symbol": symbol, "reason": "DISCOVERY_FILTER", "metrics": sorted(set(failed))})
                continue
            contributions = {}
            for criterion in criteria:
                low, high = number(criterion["low"]), number(criterion["high"])
                scaled = max(Decimal(0), min(Decimal(1), (values[criterion["metric"]] - low) / (high - low)))
                if criterion["direction"] == "lower":
                    scaled = 1 - scaled
                contributions[criterion["metric"]] = scaled * number(criterion["weight"])
            score = sum(contributions.values())
            if group_cap and (not isinstance(row.get("group"), str) or not row["group"].strip()):
                raise ValueError("Group caps require an explicit group for every scored symbol")
            scored.append({"symbol": symbol, "score": score, "group": row.get("group"),
                           "contributions": contributions})
        scored.sort(key=lambda r: (-r["score"], r["symbol"]))
        selected, groups, pending = [], {}, []
        for row in scored:
            symbol, review = row["symbol"], by_symbol.get(row["symbol"])
            reason = None
            if row["score"] < minimum:
                reason = "BELOW_MINIMUM_SCORE"
            elif review is None:
                reason = "REVIEW_REQUIRED"
                pending.append(symbol)
            elif (review["status"] not in allowed or review["event_status"] != "clear"
                  or review.get("unresolved_checks") or review.get("primary_review_gaps")
                  or not review.get("primary_evidence_complete", False)
                  or (review.get("horizon_review") and not review["horizon_review"]["evidence_complete"])):
                reason = "RESEARCH_OR_EVENT_GATE"
            elif group_cap and groups.get(row["group"], 0) >= group_cap:
                reason = "GROUP_CAP"
            elif count is not None and len(selected) >= count:
                reason = "COUNT_LIMIT"
            else:
                selected.append(symbol)
                groups[row["group"]] = groups.get(row["group"], 0) + 1
            row["selection_reason"] = reason or "SELECTED"
            row["score"] = str(row["score"])
            row["contributions"] = {k: str(v) for k, v in row["contributions"].items()}
    discovery = [r["symbol"] for r in scored]
    cutoff_index = discovery.index(selected[-1]) if count is not None and len(selected) == count else len(scored)
    blockers = [s for s in pending if discovery.index(s) <= cutoff_index]
    return {"status": "COMPUTED", "profile_sha256": digest(spec), "snapshot_sha256": digest(rows),
            "discovery_order": [r["symbol"] for r in scored], "review_queue": pending,
            "blocking_review_queue": blockers,
            "selected_symbols": selected, "scores": scored, "excluded": sorted(exclusions, key=lambda r: r["symbol"]),
            "execution_authorized": False,
            "limitations": "Identical frozen inputs, judgments and profile produce identical results; scores are preference weights, not probabilities, fair values, performance evidence or source verification"}
