"""Offline cash-return assumptions matched to an exact holding interval.

Evidence is declared, not fetched. A calculated benchmark is not a guaranteed
yield, an executable quote, or a statement that a broker pays interest on cash.
"""
from __future__ import annotations

import math

from price_audit import evidence, timestamp


def review_cash_benchmark(section, resolved):
    result = {"status": "UNVERIFIED", "holding_period_return": None,
              "reasons": [], "inputs": section,
              "limitations": "Declared cash-return assumptions; not guaranteed or source-authenticated"}
    if not isinstance(section, dict):
        result["reasons"] = ["CASH_BENCHMARK_STRUCTURED_INPUT_REQUIRED"]
        return result
    try:
        if not evidence(section.get("evidence")) or not str(section.get("instrument", "")).strip():
            raise ValueError("instrument and evidence are required")
        observed, as_of = timestamp(section["observed_at"]), timestamp(resolved["as_of"])
        age = section["max_age_seconds"]
        if isinstance(age, bool) or not isinstance(age, int) or age <= 0:
            raise ValueError("max_age_seconds must be a positive integer")
        if not 0 <= (as_of - observed).total_seconds() <= age:
            raise ValueError("observation is stale or later than research as_of")
        entry, exit_at = timestamp(section["entry_at"]), timestamp(section["exit_at"])
        if entry != timestamp(resolved["entry_at"]) or exit_at != timestamp(resolved["exit_at"]):
            raise ValueError("entry_at/exit_at must match the resolved holding interval")
        if exit_at <= entry:
            raise ValueError("exit_at must follow entry_at")
        maturity = timestamp(section["instrument_maturity_at"]) if section.get("instrument_maturity_at") else None
        if maturity and maturity <= entry:
            raise ValueError("instrument must mature after entry")
        if not maturity or maturity != exit_at:
            if not evidence(section.get("horizon_adjustment_evidence")):
                raise ValueError("mismatched/unspecified maturity needs horizon_adjustment_evidence for rollover, early sale, or floating/no-interest cash")
        value = section["rate_or_return"]
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= -1:
            raise ValueError("rate_or_return must be finite and greater than -1")
        basis = section["basis"]
        if not str(section.get("methodology", "")).strip():
            raise ValueError("methodology must explain the yield basis, costs and conversion assumptions")
        if basis == "holding_period_return":
            calculated = value
        elif basis in {"annual_effective", "annual_simple"}:
            denominator = {"ACT/365F": 365, "ACT/360": 360}.get(section.get("day_count"))
            if denominator is None:
                raise ValueError("annual rates require day_count ACT/365F or ACT/360")
            years = (exit_at - entry).total_seconds() / (86400 * denominator)
            calculated = math.expm1(math.log1p(value) * years) if basis == "annual_effective" else value * years
            result["year_fraction"] = years
        else:
            raise ValueError("basis must be holding_period_return, annual_effective or annual_simple; convert bill discount yields before use")
        if not math.isfinite(calculated) or calculated <= -1:
            raise ValueError("calculated holding return is invalid")
        result.update(status="CALCULATED_ASSUMPTION", holding_period_return=calculated)
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        result["reasons"] = ["CASH_BENCHMARK_UNVERIFIED: " + str(exc)]
    return result
