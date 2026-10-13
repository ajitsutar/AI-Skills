"""Cash-first core allocation planner. Outputs proposals, never places orders."""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from risk_engine import InvalidInput, canonical_hash, dec, positive, nonnegative
from fractional_shares import size_dollar_buy


def _sizing_rules(symbol, allow_fractional, quantity_rules):
    if type(allow_fractional) is not bool:
        raise InvalidInput("allow_fractional must be Boolean")
    supplied = (quantity_rules or {}).get(symbol)
    if not allow_fractional:
        return {"quantity_increment": "1", "min_notional": "0", "min_quantity": "1"}, "WHOLE_SHARES"
    if supplied is None:
        return {"quantity_increment": "0.000001", "min_notional": "1", "min_quantity": "0"}, "OFFLINE_ASSUMPTIONS_UNVERIFIED"
    if supplied.get("eligible") is not True:
        return None, "FRACTIONAL_ELIGIBILITY_NOT_CONFIRMED"
    return {name: supplied[name] for name in ("quantity_increment", "min_notional", "min_quantity")}, "SUPPLIED_RULES_REQUIRE_FRESH_BROKER_REVIEW"


def rebalance(equity, cash, holdings, targets, prices, cash_floor="0.05",
              band="0.02", min_trade="1", max_turnover="0.05", allow_sales=False,
              allow_fractional=True, quantity_rules=None, fee_per_share="0", fee_per_order="0"):
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
    drifts, proposals, reviews, skipped = {}, [], [], []
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
        rules, rule_status = _sizing_rules(symbol, allow_fractional, quantity_rules)
        if rules is None:
            skipped.append({"symbol": symbol, "reason": rule_status})
            continue
        rules["min_notional"] = str(max(min_trade, dec(rules["min_notional"])))
        sizing = size_dollar_buy(amount, quote[symbol], **rules,
                                 fee_per_share=fee_per_share, fee_per_order=fee_per_order)
        if sizing["status"] != "SIZED":
            skipped.append({"symbol": symbol, "reason": sizing["status"]})
            continue
        proposals.append(dict(sizing, symbol=symbol, side="buy", sleeve="core", quantity_rules_status=rule_status))
        budget -= dec(sizing["maximum_cash_debit"])
    return {"buy_candidates": proposals, "sell_reviews": reviews,
            "skipped": skipped, "allow_fractional": allow_fractional,
            "unused_planning_budget": str(budget),
            "cash_remaining_before_fees": str(cash - sum((dec(p["notional_before_fees"]) for p in proposals), Decimal(0))),
            "cash_remaining_after_reservations": str(cash - sum((dec(p["maximum_cash_debit"]) for p in proposals), Decimal(0))),
            "next_step": "Use these allocation estimates as research; native host/broker tools own any user-requested execution"}


def recurring_buys(plan_id, occurrence_id, account_alias, amounts, prices, available_cash,
                   reserve_amount="0", allow_fractional=True, quantity_rules=None,
                   fee_per_share="0", fee_per_order="0"):
    """Prepare one scheduled occurrence; never create a broker recurring schedule.

    The caller resolves the scheduled occurrence using an actual exchange calendar
    and supplies settled, unreserved cash. Never run the same plan through both a
    native broker schedule and this host loop. Stable signal keys survive changed
    prices/restarts; the execution ledger enforces deduplication when claimed.
    """
    for value in (plan_id, occurrence_id, account_alias):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise InvalidInput("Explicit bounded plan, occurrence and account alias required")
    if not amounts:
        raise InvalidInput("At least one dollar allocation required")
    budgets = {symbol: positive(value) for symbol, value in amounts.items()}
    if any(value != value.quantize(Decimal("0.01")) for value in budgets.values()):
        raise InvalidInput("Recurring dollar allocations require whole cents")
    cash, reserve = nonnegative(available_cash), nonnegative(reserve_amount)
    total = sum(budgets.values(), Decimal(0))
    if total > max(Decimal(0), cash - reserve):
        return {"status": "WAIT_FOR_SETTLED_CASH", "buy_candidates": [],
                "requested_budget": str(total), "available_after_reserve": str(max(Decimal(0), cash - reserve)),
                "execution_authorized": False}
    proposals, skipped = [], []
    for symbol in sorted(budgets):
        rules, rule_status = _sizing_rules(symbol, allow_fractional, quantity_rules)
        if rules is None:
            skipped.append({"symbol": symbol, "reason": rule_status})
            continue
        sized = size_dollar_buy(budgets[symbol], prices[symbol], **rules,
                                fee_per_share=fee_per_share, fee_per_order=fee_per_order)
        if sized["status"] != "SIZED":
            skipped.append({"symbol": symbol, "reason": sized["status"]})
            continue
        identity = canonical_hash({"plan_id": plan_id, "occurrence_id": occurrence_id,
                                   "account_alias": account_alias, "symbol": symbol})
        proposals.append(dict(sized, id="recurring-" + identity, signal_id="recurring-" + identity,
                              plan_id=plan_id, occurrence_id=occurrence_id,
                              account_alias=account_alias, symbol=symbol, side="buy", sleeve="core",
                              setup="core_rebalance", quantity_rules_status=rule_status))
    spend = sum((dec(row["maximum_cash_debit"]) for row in proposals), Decimal(0))
    return {"status": "PROPOSALS_ONLY", "buy_candidates": proposals, "skipped": skipped,
            "maximum_cash_debit": str(spend), "cash_remaining_after_reservations": str(cash - spend),
            "schedule_created": False, "execution_authorized": False,
            "next_step": "For this occurrence refresh broker state, policy targets and each exact limit order; claim once through the durable ledger. Native recurring schedules use a different broker workflow."}


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
    parser.add_argument("--recurring", action="store_true", help="Prepare one explicitly scheduled dollar contribution occurrence")
    args = parser.parse_args()
    operation = recurring_buys if args.recurring else rebalance
    print(json.dumps(operation(**json.loads(args.input.read_text(encoding="utf-8"))), indent=2))


if __name__ == "__main__":
    main()
