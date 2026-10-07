"""Portfolio exposure, aligned-return covariance and explicit scenario analysis."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from research_analytics import fraction, number
from risk_engine import canonical_hash, timestamp


def lookthrough(positions, equity, funds):
    """Recursively expand declared ETF holdings; retain missing coverage as UNKNOWN.

    Fund record: as_of, evidence, holdings [{symbol, fraction, sector, asset_type}].
    Freshness is reported and must be checked against policy by the calling workflow.
    """
    equity = number(equity)
    if equity <= 0:
        raise ValueError("Positive equity required")
    issuer, sector = defaultdict(float), defaultdict(float)
    unknown = 0.0
    sources = {}
    embedded_cash = 0.0

    def expand(symbol, kind, value, label, stack, issuer_id=None):
        nonlocal unknown, embedded_cash
        if kind == 'cash':
            if symbol != 'USD':
                raise ValueError('Only explicitly identified USD fund cash is modeled')
            embedded_cash += value
            return
        if kind != "etf":
            if kind != "equity":
                raise ValueError("Unsupported look-through asset")
            issuer[issuer_id or symbol] += value
            sector[label or "UNKNOWN"] += value
            return
        if symbol in stack:
            raise ValueError("Cyclic fund ownership")
        fund = funds.get(symbol)
        if not fund or not fund.get("evidence"):
            unknown += value
            issuer["UNKNOWN:" + symbol] += value
            sector["UNKNOWN"] += value
            return
        timestamp(fund["as_of"])
        sources[symbol] = {"as_of": fund["as_of"], "evidence": fund["evidence"], "hash": canonical_hash(fund)}
        total = sum(fraction(h["fraction"]) for h in fund["holdings"])
        if total > 1.00000001:
            raise ValueError("Fund weights exceed one")
        for holding in fund["holdings"]:
            expand(holding["symbol"], holding["asset_type"], value * fraction(holding["fraction"]),
                   holding.get("sector"), stack | {symbol}, holding.get('issuer_id'))
        residual = value * max(0, 1 - total)
        unknown += residual
        issuer["UNKNOWN:" + symbol] += residual
        sector["UNKNOWN"] += residual

    total_value = 0.0
    for position in positions:
        quantity, mark = number(position["quantity"]), number(position["mark"])
        if quantity < 0 or mark <= 0:
            raise ValueError("Long-only positions required")
        value = quantity * mark
        total_value += value
        expand(position["symbol"], position["asset_type"], value, position.get("sector"), set(), position.get('issuer_id'))
    if total_value > equity + .01:
        raise ValueError("Positions exceed unlevered equity")
    return {"issuer_exposure": dict(sorted(issuer.items())), "sector_exposure": dict(sorted(sector.items())),
            "unknown_fund_value": unknown, "unallocated_or_cash_value": equity - total_value,
            'embedded_fund_cash': embedded_cash,
            "unknown_sector_value": sector.get("UNKNOWN", 0),
            "fund_sources": sources, "complete_fund_coverage": unknown < .000001,
            "caveat": "Declared holdings/fund weights; reconcile timestamps, cash and pending orders before decisions"}


def covariance_risk(returns, weights, periods_per_year=252, shrinkage=.1, min_observations=60):
    import numpy as np
    shrinkage = fraction(shrinkage)
    annualization = number(periods_per_year)
    if annualization <= 0 or not isinstance(min_observations, int) or min_observations < 3:
        raise ValueError("Invalid covariance window/annualization")
    symbols = sorted(weights)
    w = np.array([fraction(weights[s]) for s in symbols])
    if not symbols or sum(w) > 1.00000001:
        raise ValueError("Require long-only weights summing to at most one; remainder is cash")
    matrix, reference = [], None
    for symbol in symbols:
        observations = returns[symbol]
        dates = [timestamp(row["timestamp"]) for row in observations]
        if dates != sorted(set(dates)):
            raise ValueError("Returns must have unique increasing timestamps")
        if reference is not None and dates != reference:
            raise ValueError("Unaligned returns; do not pair different dates or silently drop gaps")
        reference = dates
        matrix.append([number(row["return"]) for row in observations])
    if len(reference) < min_observations:
        raise ValueError("Insufficient aligned return history")
    x = np.array(matrix).T
    sample = np.atleast_2d(np.cov(x, rowvar=False, ddof=1))
    covariance = ((1 - shrinkage) * sample + shrinkage * np.diag(np.diag(sample))) * annualization
    variance = float(w @ covariance @ w)
    vol = float(np.sqrt(max(variance, 0)))
    component = w * (covariance @ w) / vol if vol > 0 else np.zeros(len(w))
    std = np.sqrt(np.diag(sample))
    correlation = np.divide(sample, np.outer(std, std), out=np.zeros_like(sample), where=np.outer(std, std) > 0)
    return {"symbols": symbols, "observations": len(reference), "periods_per_year": annualization,
            "shrinkage_to_diagonal": shrinkage, "annualized_volatility": vol,
            "component_volatility": dict(zip(symbols, map(float, component))),
            "covariance": covariance.tolist(), "sample_correlation": correlation.tolist(),
            "cash_weight": float(1 - sum(w)), "constant_return_symbols": [s for s, v in zip(symbols, std) if v == 0],
            "caveat": "Historical covariance with an explicit shrinkage assumption; excludes unmodeled gaps and liquidity risk"}


def stress(positions, equity, scenarios):
    equity = number(equity)
    if equity <= 0:
        raise ValueError("Positive equity required")
    results = []
    for scenario in scenarios:
        impacts = []
        for position in positions:
            shock = number(scenario.get("symbols", {}).get(position["symbol"],
                scenario.get("sectors", {}).get(position["sector"], scenario["default_shock"])))
            if shock < -1:
                raise ValueError("Long equity price shock cannot be below -100%")
            quantity, mark = number(position["quantity"]), number(position["mark"])
            if quantity < 0 or mark <= 0:
                raise ValueError("Long-only stress positions required")
            value = quantity * mark
            impacts.append({"symbol": position["symbol"], "shock": shock, "pnl": value * shock})
        pnl = sum(item["pnl"] for item in impacts)
        results.append({"name": scenario["name"], "pnl": pnl, "equity_fraction": pnl / equity,
                        "post_scenario_equity": equity + pnl, "positions": impacts})
    return {"scenarios": results, "caveat": "User-defined shocks; no probability, guaranteed bound or stop-fill assumption"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8-sig"))
    functions = {"lookthrough": lookthrough, "covariance": covariance_risk, "stress": stress}
    print(json.dumps(functions[document["operation"]](**document["inputs"]), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
