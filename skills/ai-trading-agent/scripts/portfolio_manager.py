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


def _account_basis(equity, cash, quantity, quote, weights, floor, band,
                   max_turnover, result):
    """Report the already validated rebalance basis without changing planning."""
    held = sum((quantity[k] * quote[k] for k in quantity), Decimal(0))
    residual = equity - cash - held
    targets = {k: str(weights[k] * equity) for k in sorted(weights)}
    target_total = sum((weights[k] * equity for k in weights), Decimal(0))
    above_floor = max(cash - equity * floor, Decimal(0))
    turnover_amount = equity * max_turnover
    return {
        "producer": "portfolio_manager.rebalance",
        "amount_unit": "account_currency_amount",
        "currency_status": "UNSPECIFIED",
        "currency": None,
        "currency_basis": "No currency input is supplied to this helper; legacy dollar field names do not establish USD or another currency.",
        "equity_basis": "Total account equity already includes supplied cash; do not add cash to equity.",
        "total_account_equity": str(equity),
        "supplied_settled_unreserved_cash": str(cash),
        "supplied_cash_fraction_of_equity": str(cash / equity),
        "priced_supplied_holdings": str(held),
        "unrepresented_equity_residual": str(residual),
        "residual_status": ("UNREPRESENTED_EQUITY" if residual > 0 else
                            "EXACTLY_RECONCILED" if residual == 0 else
                            "SUPPLIED_COMPONENTS_EXCEED_EQUITY_WITHIN_EXISTING_TOLERANCE"),
        "residual_basis": "Equity minus supplied cash and priced supplied holdings; positive residual is unrepresented account value, not inferred cash or an identified asset. A negative residual is retained within the planner's existing 0.01 reconciliation tolerance.",
        "policy_denominator": "total_account_equity",
        "policy_denominator_value": str(equity),
        "target_weights": {k: str(weights[k]) for k in sorted(weights)},
        "target_notionals": targets,
        "total_supplied_target_notional": str(target_total),
        "equity_outside_supplied_targets": str(equity - target_total),
        "target_basis": "Target weight times total account equity; targets are policy assumptions, not purchases, fills or current holdings. Equity outside this target map is not necessarily cash.",
        "cash_floor_fraction": str(floor),
        "cash_floor_amount": str(equity * floor),
        "cash_available_above_floor": str(above_floor),
        "drift_band_fraction": str(band),
        "drift_band_amount": str(equity * band),
        "turnover_cap_fraction": str(max_turnover),
        "turnover_cap_amount": str(turnover_amount),
        "initial_planning_budget": str(min(above_floor, turnover_amount)),
        "unused_planning_budget": result["unused_planning_budget"],
        "proposed_notional_before_fees": str(sum((dec(p["notional_before_fees"]) for p in result["buy_candidates"]), Decimal(0))),
        "proposed_debit_reservations": str(sum((dec(p["maximum_cash_debit"]) for p in result["buy_candidates"]), Decimal(0))),
        "cash_remaining_before_fees": result["cash_remaining_before_fees"],
        "cash_remaining_after_reservations": result["cash_remaining_after_reservations"],
        "planning_basis": "Initial budget is min(max(cash - equity * cash_floor, 0), equity * max_turnover). Proposal reservations include supplied/default fee assumptions and rounding; remaining budget is not remaining cash. No sales or fills are assumed.",
    }


def account_basis_summary(record):
    """Render the native account-basis values, not surrounding authored claims."""
    targets = ", ".join(f"{k}={v}" for k, v in record["target_notionals"].items())
    return (
        f"Currency unspecified; amounts are account currency units. Total account equity "
        f"{record['total_account_equity']} already includes supplied cash "
        f"{record['supplied_settled_unreserved_cash']} (do not add cash again). "
        f"Priced supplied holdings {record['priced_supplied_holdings']}; unrepresented equity residual "
        f"{record['unrepresented_equity_residual']} ({record['residual_status']}); residual is not inferred cash. "
        f"Target notionals on total account equity: {targets}; total {record['total_supplied_target_notional']}. "
        f"Equity outside supplied targets {record['equity_outside_supplied_targets']} is not necessarily cash. "
        f"Cash floor {record['cash_floor_fraction']} of equity = {record['cash_floor_amount']}; "
        f"drift band {record['drift_band_fraction']} of equity = {record['drift_band_amount']}; "
        f"turnover cap {record['turnover_cap_fraction']} of equity = {record['turnover_cap_amount']}. "
        f"Initial planning budget {record['initial_planning_budget']}; unused budget {record['unused_planning_budget']}. "
        f"Proposed notional before fees {record['proposed_notional_before_fees']}; "
        f"debit reservations {record['proposed_debit_reservations']}; "
        f"cash after reservations {record['cash_remaining_after_reservations']}. "
        "Policy targets and planning estimates are not executed trades or observed account balances."
    )


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
    result = {"buy_candidates": proposals, "sell_reviews": reviews,
            "skipped": skipped, "allow_fractional": allow_fractional,
            "unused_planning_budget": str(budget),
            "cash_remaining_before_fees": str(cash - sum((dec(p["notional_before_fees"]) for p in proposals), Decimal(0))),
            "cash_remaining_after_reservations": str(cash - sum((dec(p["maximum_cash_debit"]) for p in proposals), Decimal(0))),
            "next_step": "Use these allocation estimates as research; native host/broker tools own any user-requested execution"}
    result["account_basis"] = _account_basis(equity, cash, quantity, quote, weights,
                                              floor, band, max_turnover, result)
    result["account_basis_summary"] = account_basis_summary(result["account_basis"])
    return result


def recurring_buys(plan_id, occurrence_id, account_alias, amounts, prices, available_cash,
                   reserve_amount="0", allow_fractional=True, quantity_rules=None,
                   fee_per_share="0", fee_per_order="0"):
    """Prepare one scheduled occurrence; never create a broker recurring schedule.

    The caller resolves the scheduled occurrence using an actual exchange calendar
    and supplies settled, unreserved cash for this planning calculation. Stable
    signal keys identify the same occurrence across changed prices/restarts;
    this helper does not submit, deduplicate or schedule orders. The native host
    and broker own any requested execution and recurring schedule.
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
    intent = {
        "plan_id": plan_id, "occurrence_id": occurrence_id, "account_alias": account_alias,
        "request_basis": "dollar_budget",
        "requested_amounts": {symbol: str(budgets[symbol]) for symbol in sorted(budgets)},
        "calculation_only": True,
        "handoff_guidance": (
            "Preserve requested_amounts as native dollar instructions where the actual host/broker supports them; "
            "estimated quantities are not replacement order instructions. "
            "Legacy maximum_cash_debit is a reference-price estimate, not a guaranteed market debit. "
            "Local status and execution_authorized describe this calculation, not permission for host execution. "
            "This helper submits nothing; report submission and fills only from actual host/broker results."
        ),
    }
    if total > max(Decimal(0), cash - reserve):
        return {**intent, "status": "WAIT_FOR_SETTLED_CASH", "buy_candidates": [],
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
    return {**intent, "status": "PROPOSALS_ONLY", "buy_candidates": proposals, "skipped": skipped,
            "estimated_cash_debit": str(spend), "cash_debit_is_guaranteed": False,
            "estimate_basis": "quantity_at_reference_price_with_supplied_fee_assumptions",
            "maximum_cash_debit": str(spend), "cash_remaining_after_reservations": str(cash - spend),
            "schedule_created": False, "execution_authorized": False,
            "next_step": "Use these estimates for the requested occurrence; preserve the user's amounts and order type in the native host/broker handoff. The host and broker own submission, duplicate handling and any explicitly requested recurring schedule."}


def recurring_handoff(recurring_request, *, currency=None, companion_context=None):
    """Return unmapped economic intent alongside unchanged sizing observations."""
    from execution_handoff import recurring_dollar_intent
    result = recurring_dollar_intent(recurring_request, currency=currency,
                                    companion_context=companion_context)
    result['sizing_observation'] = recurring_buys(**recurring_request)
    result['sizing_basis'] = ('Calculation only; do not replace requested dollar amounts with estimated quantities. '
                              'Funding or sizing status does not establish broker schema support or execution permission.')
    return result


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
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--recurring", action="store_true", help="Prepare one explicitly scheduled dollar contribution occurrence")
    operations.add_argument("--recurring-handoff", action="store_true", help="Describe unmapped recurring dollar intent and separate sizing observations")
    args = parser.parse_args()
    if args.recurring_handoff:
        from execution_handoff import redact_private
        def unique_fields(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('Duplicate JSON key in recurring handoff input')
                result[key] = value
            return result
        # Only this new route preserves JSON fractional-number lexemes as strings.
        request = json.loads(args.input.read_text(encoding="utf-8"), parse_float=str,
                             object_pairs_hook=unique_fields)
        print(json.dumps(redact_private(recurring_handoff(**request)), indent=2, allow_nan=False))
    else:
        operation = recurring_buys if args.recurring else rebalance
        print(json.dumps(operation(**json.loads(args.input.read_text(encoding="utf-8"))), indent=2))


if __name__ == "__main__":
    main()
