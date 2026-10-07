"""Deterministic research calculations on sourced inputs; no automatic buy verdict.

Sector/industry comparisons, explicit normalization bridges, valuation scenarios
and dated analyst distributions. All modeled assumptions remain visible.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

from risk_engine import canonical_hash, timestamp


def number(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a financial number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite financial input")
    return result


def fraction(value):
    result = number(value)
    if not 0 <= result <= 1:
        raise ValueError("Expected fraction between zero and one")
    return result


def normalization_bridge(reported, adjustments, period):
    """After-tax earnings bridge. FCF requires a separate bridge, not this result.

    Adjustments carry signed pre/after-tax amounts and explicit realization rates.
    Cash effects are reported separately, never silently erased as nonrecurring.
    """
    total, applied = number(reported), []
    cash_effect = 0.0
    for item in adjustments:
        if item["period"] != period or not item.get("evidence") or not item.get("reason"):
            raise ValueError("Adjustment requires matching period, evidence and explanation")
        amount = number(item["amount"])
        realization = fraction(item["realization_fraction"])
        if item["tax_basis"] == "pre_tax":
            amount *= 1 - fraction(item["tax_rate"])
        elif item["tax_basis"] != "after_tax":
            raise ValueError("Specify pre_tax or after_tax adjustment")
        value = amount * realization
        total += value
        cash = number(item["cash_effect_in_period"])
        cash_effect += cash
        applied.append({**item, "applied_after_tax": value})
    return {"reported": number(reported), "period": period, "normalized_after_tax": total,
            "adjustments": applied, "separate_cash_effect": cash_effect,
            "caveat": "Explicit assumption bridge; no verification of recurrence, realization or cash-flow equivalence"}


def valuation_scenarios(price, base_equity_earnings, shares, scenarios):
    price, base_equity_earnings, shares = map(number, (price, base_equity_earnings, shares))
    if min(price, shares) <= 0 or base_equity_earnings <= 0:
        raise ValueError("Equity earnings-multiple model requires positive price, shares and earnings")
    if not scenarios or len({s["name"] for s in scenarios}) != len(scenarios):
        raise ValueError("Use nonempty uniquely named valuation scenarios")
    results = []
    for scenario in scenarios:
        years = scenario["years"]
        growth, dilution, discount, multiple = map(number, (scenario["annual_earnings_growth"],
            scenario["annual_share_count_growth"], scenario["discount_rate"], scenario["exit_pe"]))
        if not isinstance(years, int) or isinstance(years, bool) or not 1 <= years <= 30:
            raise ValueError("Scenario horizon must be 1..30 whole years")
        if growth <= -1 or dilution <= -1 or discount <= -1 or multiple <= 0:
            raise ValueError("Invalid growth/dilution/discount/multiple assumptions")
        eps = base_equity_earnings * (1 + growth) ** years / (shares * (1 + dilution) ** years)
        terminal_price = eps * multiple
        current_value = terminal_price / (1 + discount) ** years
        results.append({**scenario, "terminal_eps": eps, "terminal_price": terminal_price,
                        "discounted_terminal_value": current_value, "value_vs_price": current_value / price - 1})
    if not all(math.isfinite(r["discounted_terminal_value"]) for r in results):
        raise ValueError("Scenario overflow")
    return {"basis": "equity earnings multiple; no enterprise-value/debt double count",
            "scenarios": results, "caveat": "Omits intermediate dividends; assumptions are scenarios, not estimated probabilities or recommendations"}


def peer_comparisons(rows, minimum_peers=3):
    """Median by explicit peer group AND metric basis, one security per issuer.

    Negative/zero multiples are excluded as nonmeaningful, never made cheap.
    No sector/index median is substituted silently when the peer group is small.
    """
    if not isinstance(minimum_peers, int) or minimum_peers < 2:
        raise ValueError("At least two comparable issuers required")
    if len({r["symbol"] for r in rows}) != len(rows):
        raise ValueError("Duplicate security row")
    groups = defaultdict(dict)
    for row in sorted(rows, key=lambda r: r["symbol"]):
        if not row.get("issuer_id") or not row.get("peer_group") or not row.get("evidence"):
            raise ValueError("Each row needs issuer, suitable peer group and evidence")
        for metric, observation in row["metrics"].items():
            if observation.get("value") is None:
                continue
            value = number(observation["value"])
            if value <= 0:
                continue
            if not observation.get("basis") or not observation.get("period"):
                raise ValueError("Metric basis and period are required")
            key = (row["peer_group"], metric, observation["basis"], observation["period"])
            groups[key].setdefault(row["issuer_id"], (row["symbol"], value, observation["period"]))
    outputs = []
    for row in rows:
        comparisons = {}
        for metric, observation in row["metrics"].items():
            peers = groups.get((row["peer_group"], metric, observation.get("basis"), observation.get("period")), {})
            values = [p[1] for p in peers.values()]
            current = observation.get("value")
            valid = current is not None and number(current) > 0 and len(peers) >= minimum_peers
            median = statistics.median(values) if valid else None
            comparisons[metric] = {"value": current, "basis": observation.get("basis"), "period": observation.get("period"),
                "peer_count": len(peers), "peer_median": median,
                "relative_discount": 1 - number(current) / median if valid else None,
                "representatives": [p[0] for p in peers.values()],
                "peer_periods": sorted(set(p[2] for p in peers.values())),
                "status": "comparable_screen_only" if valid else "missing_or_nonmeaningful_or_too_few_peers"}
        outputs.append({"symbol": row["symbol"], "peer_group": row["peer_group"], "comparisons": comparisons})
    return {"rows": outputs, "input_hash": canonical_hash(rows),
            "method": "Median of positive same-basis, same-period metrics; one alphabetically first available security per issuer",
            "caveat": "Host must align fiscal/TTM dates within each period label; cheap relative to peers is not intrinsic undervaluation"}


def free_cash_flow(cash_from_operations, capital_expenditures, stock_compensation, adjustments, period):
    cfo, capex, sbc = map(number, (cash_from_operations, capital_expenditures, stock_compensation))
    if capex < 0 or sbc < 0:
        raise ValueError("Supply capex as positive cash outflow and SBC as nonnegative expense")
    normalized = cfo - capex
    for adjustment in adjustments:
        if adjustment['period'] != period or not adjustment.get('evidence') or not adjustment.get('reason'):
            raise ValueError("FCF adjustment requires matching period and evidence")
        normalized += number(adjustment['cash_amount']) * fraction(adjustment['realization_fraction'])
    return dict(period=period, reported_fcf=cfo-capex, normalized_fcf=normalized,
                sbc_adjusted_owner_earnings_sensitivity=normalized-sbc, adjustments=adjustments,
                caveat='SBC sensitivity is not a cash outflow; separately model dilution, recurring capex and working-capital reversals')


def estimate_revisions(records, as_of, metric, fiscal_period, unit, revision_days=90):
    """Matched contributor revisions; no mixing EPS periods or currencies/units."""
    now = timestamp(as_of)
    if type(revision_days) is not int or revision_days <= 0:
        raise ValueError('Positive whole-day revision window required')
    cutoff = now - timedelta(days=revision_days)
    groups = defaultdict(dict)
    for row in records:
        dated = timestamp(row['published_at'])
        if (row['metric'],row['fiscal_period'],row['unit']) != (metric,fiscal_period,unit) or dated > now or not row.get('evidence'):
            continue
        value = number(row['value'])
        previous = groups[row['contributor']].get(dated)
        if previous is not None and previous != value:
            raise ValueError('Contradictory same-time estimate')
        groups[row['contributor']][dated] = value
    changes, missing = [], []
    for name, values in groups.items():
        before = sorted((t,v) for t,v in values.items() if t <= cutoff)
        after = sorted((t,v) for t,v in values.items() if cutoff < t <= now)
        if not before or not after or (cutoff-before[-1][0]).days > revision_days:
            missing.append(name)
            continue
        baseline, latest = before[-1][1], after[-1][1]
        changes.append(dict(contributor=name,baseline=baseline,latest=latest,absolute_change=latest-baseline,
                            percentage_change=(latest/baseline-1) if baseline > 0 else None))
    return dict(metric=metric,fiscal_period=fiscal_period,unit=unit,as_of=as_of,matched_revisions=changes,
                contributors_without_comparable_pair=missing,
                caveat='No percentage revision for a zero/negative baseline; ratings need their own explicit ordinal mapping')


def percentile(sorted_values, probability):
    point = (len(sorted_values) - 1) * probability
    lower, upper = math.floor(point), math.ceil(point)
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (point - lower)


def analyst_targets(records, as_of, currency, horizon_months=12, max_age_days=180, revision_days=90):
    now = timestamp(as_of)
    cutoff = now - timedelta(days=max_age_days)
    if max_age_days <= 0 or revision_days <= 0 or horizon_months <= 0:
        raise ValueError("Analyst windows/horizon must be positive")
    groups = defaultdict(list)
    excluded = 0
    for record in records:
        dated = timestamp(record["published_at"])
        if (record["currency"] != currency or record["horizon_months"] != horizon_months
                or not cutoff <= dated <= now or not record.get("evidence")):
            excluded += 1
            continue
        value = number(record["target"])
        if value <= 0 or not record.get("firm"):
            raise ValueError("Analyst target requires positive value and firm")
        groups[record["firm"]].append((dated, value))
    latest, revisions, unavailable = [], [], []
    for firm, entries in groups.items():
        entries.sort()
        # Contradictory same-time publications cannot be silently deduplicated.
        if any(a[0] == b[0] and a[1] != b[1] for a, b in zip(entries, entries[1:])):
            raise ValueError("Conflicting same-time analyst targets for " + firm)
        latest.append(entries[-1][1])
        baseline = [entry for entry in entries if entry[0] <= now - timedelta(days=revision_days)]
        if baseline and entries[-1][0] > now - timedelta(days=revision_days):
            revisions.append({"firm": firm, "baseline": baseline[-1][1], "latest": entries[-1][1],
                              "change": entries[-1][1] / baseline[-1][1] - 1})
        else:
            unavailable.append(firm)
    values = sorted(latest)
    result = {"as_of": as_of, "currency": currency, "horizon_months": horizon_months,
              "count": len(values), "excluded_records": excluded, "revision_days": revision_days,
              "same_firm_target_revisions": revisions, "firms_without_revision_pair": unavailable,
              "caveat": "Targets only; rating upgrades and EPS/revenue revisions require their own dated series"}
    if values:
        median = statistics.median(values)
        result.update(low=values[0], median=median, high=values[-1], mean=statistics.mean(values),
                      q1=percentile(values, .25), q3=percentile(values, .75),
                      iqr_over_median=(percentile(values, .75) - percentile(values, .25)) / median)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8-sig"))
    operations = {"normalization": normalization_bridge, "valuation": valuation_scenarios,
                  "peers": peer_comparisons, "analysts": analyst_targets,
                  "fcf": free_cash_flow, "revisions": estimate_revisions}
    result = operations[document["operation"]](**document["inputs"])
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
