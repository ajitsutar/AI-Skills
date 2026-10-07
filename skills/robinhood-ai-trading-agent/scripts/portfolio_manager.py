"""Cash-first core allocation planner. Outputs proposals, never places orders."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

from risk_engine import InvalidInput, dec, positive, nonnegative


def rebalance(equity, cash, holdings, targets, prices, cash_floor="0.05",
              band="0.02", min_trade="50", max_turnover="0.05", allow_sales=False):
    """Weights are fractions of TOTAL equity, not core-only equity.

    Use only settled unreserved cash supplied by caller. Never fund a buy from an
    unfilled sale. No automatic tax-lot selection. Sales are separate review items.
    """
    equity, cash = positive(equity), nonnegative(cash)
    band, min_trade, max_turnover = map(nonnegative, (band, min_trade, max_turnover))
    floor = nonnegative(cash_floor)
    weights = {k: nonnegative(v) for k, v in targets.items()}
    if not weights or sum(weights.values()) + floor > 1 or max_turnover > 1:
        raise InvalidInput("Invalid target/cash/turnover fractions")
    quantity = {k: nonnegative(v) for k, v in holdings.items()}
    quote = {k: positive(prices[k]) for k in set(weights) | set(quantity)}
    if cash + sum(quantity[k] * quote[k] for k in quantity) > equity + Decimal("0.01"):
        raise InvalidInput("Core holdings and cash exceed account equity")
    drifts, proposals, reviews = {}, [], []
    budget = min(max(cash - equity * floor, Decimal(0)), equity * max_turnover)
    for symbol in set(weights) | set(quantity):
        value = quantity.get(symbol, Decimal(0)) * quote[symbol]
        drifts[symbol] = weights.get(symbol, Decimal(0)) * equity - value
        if drifts[symbol] < -equity * band:
            reviews.append({"symbol": symbol, "action": "REVIEW_TRIM" if allow_sales else "HOLD_FOR_REVIEW",
                            "excess_value": str(-drifts[symbol]),
                            "reason": "Inspect tax lots, wash sales and thesis before any sale"})
    for symbol in sorted(drifts, key=lambda k: (-drifts[k], k)):
        if drifts[symbol] <= equity * band:
            continue
        amount = min(drifts[symbol], budget)
        qty = (amount / quote[symbol]).to_integral_value(rounding=ROUND_FLOOR)
        cost = qty * quote[symbol]
        if cost < min_trade or qty <= 0:
            continue
        proposals.append({"symbol": symbol, "side": "buy", "sleeve": "core",
                          "quantity": str(qty), "reference_price": str(quote[symbol]),
                          "notional_before_fees": str(cost)})
        budget -= cost
    return {"buy_candidates": proposals, "sell_reviews": reviews,
            "unused_planning_budget": str(budget),
            "cash_remaining_before_fees": str(cash - sum((dec(p["notional_before_fees"]) for p in proposals), Decimal(0))),
            "next_step": "Add fees, current broker quotes and run each exact order through risk_engine and execution_ledger"}


def performance(equity_path, net_flows):
    """Daily chain-linked return, with external flows at end of each period.

    Intraday deposits require valuations at each flow for exact TWR; do not pass
    them here as if this end-of-day convention were exact.
    """
    values = list(map(positive, equity_path))
    flows = list(map(dec, net_flows))
    if len(values) < 2 or len(flows) != len(values) - 1:
        raise InvalidInput("Need n equity values and n-1 end-period flows")
    wealth = high = Decimal(1)
    worst = Decimal(0)
    returns = []
    for previous, current, flow in zip(values, values[1:], flows):
        r = (current - flow) / previous - 1
        if r <= -1:
            raise InvalidInput("Nonpositive flow-adjusted wealth")
        returns.append(str(r))
        wealth *= 1 + r
        high = max(high, wealth)
        worst = max(worst, 1 - wealth / high)
    return {"time_weighted_return": str(wealth - 1), "max_drawdown": str(worst),
            "period_returns": returns, "flow_convention": "end_of_period"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    print(json.dumps(rebalance(**json.loads(args.input.read_text(encoding="utf-8"))), indent=2))


if __name__ == "__main__":
    main()
