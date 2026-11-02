"""Exact quantity-grid sizing for dollar budgets; no broker calls or schedules.

Planning increments are explicit assumptions. Live increments and eligibility must
come from the observed broker; a retail product page is not a tool capability.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR

from risk_engine import InvalidInput, dec, fresh, nonnegative, positive


CENT = Decimal("0.01")
SEMANTIC_TOKENS = {
    "order_types": {"limit", "market", "stop", "stop_market", "stop_limit", "trailing_stop"},
    "time_in_force": {"day", "gtc", "ioc", "fok"},
    "sides": {"buy", "sell"},
    "sessions": {"regular", "extended", "overnight"},
}


def validate_semantic_record(record):
    if not isinstance(record, dict):
        raise InvalidInput("Fractional capability rules must be an object")
    for field, allowed in SEMANTIC_TOKENS.items():
        values = record.get(field)
        if (not isinstance(values, list) or not values
                or any(not isinstance(value, str) or value not in allowed for value in values)):
            raise InvalidInput("Fractional " + field + " must be a nonempty list of exact supported tokens")
    evidence = record.get("evidence")
    if (not isinstance(evidence, list) or not evidence
            or any(not isinstance(value, str) or not value.strip() for value in evidence)):
        raise InvalidInput("Fractional evidence must be a nonempty list of source references")


def quantity_step(value):
    step = positive(value)
    if step > 1 or step.normalize().as_tuple().exponent < -18:
        raise InvalidInput("Quantity increment must be positive, <= 1 and at most 18 decimal places")
    return step


def round_quantity_down(quantity, increment="1"):
    step = quantity_step(increment)
    return (nonnegative(quantity) / step).to_integral_value(rounding=ROUND_FLOOR) * step


def fee_reservation(quantity, fee_per_share="0", fee_per_order="0"):
    qty = nonnegative(quantity)
    variable, fixed = nonnegative(fee_per_share), nonnegative(fee_per_order)
    return (qty * variable + fixed).quantize(CENT, rounding=ROUND_CEILING) if qty else Decimal(0)


def cash_requirement(quantity, price, fee_per_share="0", fee_per_order="0"):
    """Conservative USD reservation: round notional and aggregate fees up to cents.

    This is a reference-price planning estimate, not a guaranteed market debit.
    Actual cash and fees must be reconciled from broker records after execution.
    """
    qty, price = nonnegative(quantity), positive(price)
    if not qty:
        return Decimal(0)
    notional = (qty * price).quantize(CENT, rounding=ROUND_CEILING)
    fees = fee_reservation(qty, fee_per_share, fee_per_order)
    return notional + fees


def round_trip_friction(quantity, entry, slippage_bps="0", fee_per_share="0", fee_per_order="0"):
    """Conservative two-leg cost using the same cent-rounded fee reserves as cash."""
    return (2 * nonnegative(quantity) * positive(entry) * nonnegative(slippage_bps) / 10000
            + 2 * fee_reservation(quantity, fee_per_share, fee_per_order))


def size_dollar_buy(dollar_budget, price, quantity_increment="0.000001",
                   min_notional="1", min_quantity="0", fee_per_share="0",
                   fee_per_order="0"):
    """Estimate a quantity at the supplied reference price, rounding down.

    Six decimals is an offline planning assumption, not a Robinhood precision
    claim. Pass observed rules for broker-review proposals. A quantity limit order
    can leave cash unspent; it is not a native dollar-market order.
    """
    requested_budget = nonnegative(dollar_budget)
    budget = requested_budget.quantize(CENT, rounding=ROUND_FLOOR)
    price, step = positive(price), quantity_step(quantity_increment)
    floor, minimum = nonnegative(min_notional), nonnegative(min_quantity)
    variable, fixed = nonnegative(fee_per_share), nonnegative(fee_per_order)
    units = int((max(Decimal(0), budget - fixed) / ((price + variable) * step)).to_integral_value(rounding=ROUND_FLOOR))
    # Binary search avoids one-step loops for tiny grids and penny fee rounding.
    low, high = 0, units
    while low < high:
        candidate = (low + high + 1) // 2
        if cash_requirement(step * candidate, price, variable, fixed) <= budget:
            low = candidate
        else:
            high = candidate - 1
    qty = step * low
    status = "SIZED"
    if not qty or qty < minimum or qty * price < floor:
        qty, status = Decimal(0), "BELOW_MINIMUM_OR_BUDGET"
    debit = cash_requirement(qty, price, variable, fixed)
    return {"status": status, "quantity": str(qty), "quantity_increment": str(step),
            "order_basis": "quantity", "dollar_budget": str(budget),
            "reference_price": str(price), "notional_before_fees": str(qty * price),
            "fee_reserve": str(debit - (qty * price).quantize(CENT, rounding=ROUND_CEILING)),
            "maximum_cash_debit": str(debit), "unspent_budget": str(budget - debit),
            "execution_authorized": False,
            "request_basis": "dollar_budget", "requested_dollar_budget": str(requested_budget),
            "estimate_basis": "quantity_at_reference_price_with_supplied_fee_assumptions",
            "estimated_cash_debit": str(debit), "cash_debit_is_guaranteed": False,
            "calculation_only": True}


def validate_fractional_policy(policy):
    if "fractional_shares" not in policy:
        return
    config = policy["fractional_shares"]
    if not isinstance(config, dict):
        raise InvalidInput("fractional_shares policy must be an object")
    if type(config.get("enabled")) is not bool:
        raise InvalidInput("fractional_shares.enabled must be Boolean")
    positive(config["max_rules_age_seconds"])


def fractional_order_reasons(policy, quote, order, now):
    """Validate exact fractional orders; never round an approved live quantity."""
    qty = positive(order["quantity"])
    if qty == qty.to_integral_value():
        return []
    reasons = []
    config = policy.get("fractional_shares", {})
    if not isinstance(config, dict):
        raise InvalidInput("fractional_shares policy must be an object")
    if config.get("enabled") is not True:
        reasons.append("FRACTIONAL_SHARES_NOT_ENABLED")
    rules = quote.get("fractional_rules", {})
    if not isinstance(rules, dict):
        raise InvalidInput("Fractional capability rules must be an object")
    if rules.get("eligible") is not True:
        reasons.append("FRACTIONAL_ELIGIBILITY_NOT_CONFIRMED")
    if not rules:
        return reasons + ["FRACTIONAL_RULES_MISSING"]
    validate_semantic_record(rules)
    if not rules.get("evidence") or not fresh(rules["checked_at"], now, config.get("max_rules_age_seconds", 60)):
        reasons.append("FRACTIONAL_RULES_STALE_OR_UNVERIFIED")
    if policy["mode"] != "paper" and rules.get("source") != "official_broker":
        reasons.append("FRACTIONAL_RULES_REQUIRE_OFFICIAL_BROKER")
    step = quantity_step(rules["quantity_increment"])
    if qty % step:
        reasons.append("INVALID_QUANTITY_INCREMENT")
    if qty < nonnegative(rules["min_quantity"]) or qty * positive(order["limit_price"]) < nonnegative(rules["min_notional"]):
        reasons.append("FRACTIONAL_ORDER_BELOW_MINIMUM")
    if (order["order_type"] not in rules["order_types"]
            or order["time_in_force"] not in rules["time_in_force"]
            or order["side"] not in rules["sides"] or "regular" not in rules["sessions"]):
        reasons.append("FRACTIONAL_ORDER_COMBINATION_UNSUPPORTED")
    return reasons


def validate_broker_fractional_semantics(tool, order):
    """The observed tool must preserve exact fractional quantity and fill units."""
    if dec(order["quantity"]) == dec(order["quantity"]).to_integral_value():
        return
    semantics = tool.get("fractional_share_semantics", {})
    if not semantics:
        raise InvalidInput("Observed fractional quantity/order/fill broker semantics required")
    validate_semantic_record(semantics)
    if (semantics.get("quantity_based") is not True
            or semantics.get("cumulative_fractional_fills") is not True
            or not semantics.get("evidence")
            or order["order_type"] not in semantics.get("order_types", [])
            or order["time_in_force"] not in semantics.get("time_in_force", [])
            or order["side"] not in semantics.get("sides", [])
            or "regular" not in semantics.get("sessions", [])):
        raise InvalidInput("Observed fractional quantity/order/fill broker semantics required")
