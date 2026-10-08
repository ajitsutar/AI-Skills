"""Deterministic, fail-closed gates for long-only equity/ETF order proposals.

No networking or broker credentials. Monetary calculations use Decimal. Inputs
must be normalized from a fresh broker snapshot, never filled in by inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path


class InvalidInput(ValueError):
    pass


def dec(value):
    if isinstance(value, bool):
        raise InvalidInput("Boolean is not a monetary value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidInput("Expected a finite decimal number") from exc
    if not result.is_finite():
        raise InvalidInput("Non-finite number")
    return result


def positive(value):
    result = dec(value)
    if result <= 0:
        raise InvalidInput("Expected a positive number")
    return result


def nonnegative(value):
    result = dec(value)
    if result < 0:
        raise InvalidInput("Expected a nonnegative number")
    return result


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise InvalidInput("Timestamp requires UTC offset")
    return result.astimezone(timezone.utc)


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def fresh(value, now, max_seconds):
    age = (now - timestamp(value)).total_seconds()
    return 0 <= age <= float(positive(max_seconds))


def validate_policy(policy):
    if type(policy["schema_version"]) is not int or policy["schema_version"] not in {2, 3}:
        raise InvalidInput("Unsupported policy version")
    if policy["mode"] not in {"paper", "approval", "bounded_autonomous"}:
        raise InvalidInput("Unknown execution mode")
    if policy["deployment_context"] not in {"learning", "personal"}:
        raise InvalidInput("Unknown deployment context")
    limits = policy["limits"]
    for name in ("single_stock", "single_etf", "sector", "risk_per_trade", "open_risk",
                 "daily_loss", "weekly_loss", "drawdown", "cash_floor"):
        if not 0 <= dec(limits[name]) <= 1:
            raise InvalidInput("Fraction outside [0,1]: " + name)
    sleeves = policy["sleeves"]
    if set(sleeves) != {"core", "swing", "intraday"}:
        raise InvalidInput("Expected core, swing and intraday sleeve caps")
    if any(not 0 <= dec(v) <= 1 for v in sleeves.values()):
        raise InvalidInput("Invalid sleeve fraction")
    if sum(map(dec, sleeves.values())) + dec(limits["cash_floor"]) > 1:
        raise InvalidInput("Sleeves plus cash floor exceed capital")
    for name in ("max_quote_age_seconds", "max_snapshot_age_seconds", "max_spread_bps",
                 "max_order_notional", "max_price_deviation_bps", "max_positions", "max_orders_per_day",
                 "max_daily_turnover", "min_reward_risk", "min_daily_dollar_volume"):
        positive(limits[name])
    for name in ("slippage_bps", "fee_per_share", "no_entry_minutes_before_close"):
        nonnegative(limits[name])
    reserve_fraction = dec(limits.get("intraday_settled_cash_floor_fraction", limits["cash_floor"]))
    if not 0 <= reserve_fraction <= 1:
        raise InvalidInput("Intraday settled cash floor fraction outside [0,1]")
    nonnegative(limits.get("intraday_settled_cash_floor_amount", 0))
    if policy["allow_leverage"] is not False or policy["allow_shorting"] is not False:
        raise InvalidInput("This runtime supports unlevered long-only equities/ETFs")
    if not policy["allowed_symbols"] or not policy["allowed_setups"]:
        raise InvalidInput("Explicit symbol and setup allowlists required")
    setup_sleeves = policy["setup_sleeves"]
    if set(setup_sleeves) != set(policy["allowed_setups"]) or any(
            not isinstance(v, list) or not v or set(v) - set(sleeves)
            for v in setup_sleeves.values()):
        raise InvalidInput("Each allowed setup needs explicit permitted sleeves")
    targets = {k: nonnegative(v) for k, v in policy["core_targets"].items()}
    if sum(targets.values()) > dec(sleeves["core"]) or set(targets) - set(policy["allowed_symbols"]):
        raise InvalidInput("Core targets exceed sleeve or symbol allowlist")
    if policy["schema_version"] == 3:
        from personal_policy import validate_personal_fields
        validate_personal_fields(policy)


def size_tactical(equity, entry, stop, risk_fraction, notional_cap,
                  slippage_bps=5, fee_per_share=0):
    """Sizing suggestion only; approval must bind the final rounded quantity."""
    equity, entry, stop = map(positive, (equity, entry, stop))
    risk_fraction = positive(risk_fraction)
    if risk_fraction > 1 or stop >= entry:
        raise InvalidInput("Long stop must be below entry; risk fraction <= 1")
    friction = 2 * entry * nonnegative(slippage_bps) / 10000 + 2 * nonnegative(fee_per_share)
    unit_risk = entry - stop + friction
    risk_qty = equity * risk_fraction / unit_risk
    cash_qty = nonnegative(notional_cap) / (entry + nonnegative(fee_per_share))
    qty = min(risk_qty, cash_qty).to_integral_value(rounding=ROUND_FLOOR)
    return {"quantity": str(qty), "planned_loss": str(qty * unit_risk),
            "per_share_risk": str(unit_risk), "gap_loss_is_uncapped": True}


def evaluate(policy, snapshot, order, now=None):
    """Return all applicable rejection reasons; invalid or missing inputs block."""
    now = now or datetime.now(timezone.utc)
    reasons = []
    metrics = {}
    try:
        validate_policy(policy)
        limits = policy["limits"]
        equity = positive(snapshot["equity"])
        cash = nonnegative(snapshot["cash"])
        settled = nonnegative(snapshot["settled_cash"])
        buying_power = nonnegative(snapshot["buying_power"])
        if snapshot["reconciled"] is not True:
            reasons.append("BROKER_STATE_NOT_RECONCILED")
        if not fresh(snapshot["as_of"], now, limits["max_snapshot_age_seconds"]):
            reasons.append("STALE_OR_FUTURE_ACCOUNT_SNAPSHOT")
        if snapshot["agent_tradable"] is not True:
            reasons.append("NOT_AGENT_TRADABLE_ACCOUNT")
        symbol, side, sleeve = order["symbol"], order["side"], order["sleeve"]
        for key in ("id", "signal_id", "symbol", "account_alias"):
            if not isinstance(order[key], str) or not order[key].strip() or len(order[key]) > 200:
                raise InvalidInput("Invalid order identifier: " + key)
        if order["account_alias"] != snapshot["account_alias"]:
            reasons.append("ACCOUNT_SCOPE_MISMATCH")
        if side not in {"buy", "sell"} or sleeve not in policy["sleeves"]:
            raise InvalidInput("Unsupported side or sleeve")
        if order["asset_type"] not in {"equity", "etf"}:
            reasons.append("UNSUPPORTED_ASSET")
        if order["order_type"] != "limit" or order["time_in_force"] != "day":
            reasons.append("ONLY_DAY_LIMIT_ORDERS_SUPPORTED")
        if order.get("extended_hours") is not False:
            reasons.append("EXTENDED_HOURS_DISABLED")
        qty, price = positive(order["quantity"]), positive(order["limit_price"])
        if qty != qty.to_integral_value():
            reasons.append("WHOLE_SHARES_REQUIRED")
        quote = snapshot["quotes"][symbol]
        if quote["asset_type"] != order["asset_type"]:
            reasons.append("INSTRUMENT_TYPE_MISMATCH")
        bid, ask = positive(quote["bid"]), positive(quote["ask"])
        if ask < bid:
            raise InvalidInput("Crossed quote")
        if quote["tradable"] is not True or quote["halted"] is not False:
            reasons.append("UNTRADABLE_OR_HALTED")
        if not fresh(quote["as_of"], now, limits["max_quote_age_seconds"]):
            reasons.append("STALE_OR_FUTURE_QUOTE")
        tick = positive(quote["tick_size"])
        if price % tick:
            reasons.append("INVALID_PRICE_INCREMENT")
        session = snapshot["session"]
        opening, closing = timestamp(session["open"]), timestamp(session["close"])
        if opening >= closing:
            raise InvalidInput("Invalid official session bounds")
        if session["is_trading_day"] is not True or not opening <= now < closing:
            reasons.append("OUTSIDE_REGULAR_SESSION")
        if not fresh(order["created_at"], now, limits["max_snapshot_age_seconds"]):
            reasons.append("STALE_PROPOSAL")
        if timestamp(order["expires_at"]) <= now:
            reasons.append("PROPOSAL_EXPIRED")
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10000
        if abs(price - (ask + bid) / 2) / ((ask + bid) / 2) * 10000 > dec(limits["max_price_deviation_bps"]):
            reasons.append("LIMIT_TOO_FAR_FROM_CURRENT_QUOTE")
        if spread_bps > dec(limits["max_spread_bps"]):
            reasons.append("SPREAD_TOO_WIDE")
        if qty * price > dec(limits["max_order_notional"]):
            reasons.append("ORDER_NOTIONAL_LIMIT")

        positions = snapshot["positions"]
        pending = snapshot["open_orders"]
        seen = set()
        total_value = Decimal(0)
        sleeve_values = {k: Decimal(0) for k in policy["sleeves"]}
        symbol_values, sector_values = {}, {}
        open_risk = Decimal(0)
        held = reserved_sell = reserved_cash = Decimal(0)
        for p in positions:
            key = (p["symbol"], p["sleeve"])
            if key in seen or p["sleeve"] not in sleeve_values:
                raise InvalidInput("Duplicate or invalid sleeve position")
            seen.add(key)
            pqty, mark = nonnegative(p["quantity"]), positive(p["mark"])
            value = pqty * mark
            total_value += value
            sleeve_values[p["sleeve"]] += value
            symbol_values[p["symbol"]] = symbol_values.get(p["symbol"], Decimal(0)) + value
            if p.get('asset_type') != 'etf':
                sector_values[p["sector"]] = sector_values.get(p["sector"], Decimal(0)) + value
            if p["symbol"] == symbol and p["sleeve"] == sleeve:
                held += pqty
            if side == "buy" and p["symbol"] == symbol and p["sleeve"] != sleeve and pqty:
                reasons.append("CROSS_SLEEVE_SYMBOL_CONFLICT")
            if p["sleeve"] != "core" and pqty:
                stop = positive(p["stop_price"])
                if side == "buy" and mark <= stop:
                    reasons.append("EXISTING_TACTICAL_STOP_BREACHED")
                open_risk += pqty * (max(mark - stop, Decimal(0)) +
                                     2 * mark * dec(limits["slippage_bps"]) / 10000 +
                                     2 * dec(limits["fee_per_share"]))
        if abs(total_value + cash - equity) > max(Decimal("1"), equity * Decimal("0.0001")):
            reasons.append("EQUITY_POSITION_CASH_MISMATCH")
        seen_pending = set()
        for p in pending:
            if p["local_ref"] in seen_pending:
                raise InvalidInput("Duplicate pending order")
            seen_pending.add(p["local_ref"])
            if p["status"] not in {"open", "partially_filled", "cancel_pending"}:
                reasons.append("UNKNOWN_OPEN_ORDER_STATE")
            remaining = nonnegative(p["remaining_quantity"])
            if p["side"] not in {"buy", "sell"} or p["sleeve"] not in sleeve_values:
                raise InvalidInput("Invalid pending order")
            if p["symbol"] == symbol and remaining:
                reasons.append("SYMBOL_HAS_PENDING_ORDER")
            if p["side"] == "buy":
                reserve_price = positive(p["reservation_price"])
                reserve = remaining * reserve_price
                reserved_cash += reserve + remaining * dec(limits["fee_per_share"])
                sleeve_values[p["sleeve"]] += reserve
                symbol_values[p["symbol"]] = symbol_values.get(p["symbol"], Decimal(0)) + reserve
                if p.get('asset_type') != 'etf':
                    sector_values[p["sector"]] = sector_values.get(p["sector"], Decimal(0)) + reserve
                if p["sleeve"] != "core":
                    stop = positive(p["stop_price"])
                    if stop >= reserve_price:
                        raise InvalidInput("Invalid pending stop")
                    open_risk += remaining * (reserve_price - stop +
                        2 * reserve_price * dec(limits["slippage_bps"]) / 10000 +
                        2 * dec(limits["fee_per_share"]))
            elif p["symbol"] == symbol and p["sleeve"] == sleeve:
                reserved_sell += remaining

        if side == "sell":
            if qty > held - reserved_sell:
                reasons.append("SELL_EXCEEDS_SLEEVE_AVAILABLE_SHARES")
            # Loss breakers must never block a valid reduction of owned shares.
        else:
            if symbol not in policy["allowed_symbols"] or order["setup"] not in policy["allowed_setups"]:
                reasons.append("SYMBOL_OR_SETUP_NOT_ALLOWED")
            if sleeve not in policy["setup_sleeves"].get(order["setup"], []):
                reasons.append("SETUP_SLEEVE_MISMATCH")
            if snapshot["restricted"] is not False or dec(snapshot["maintenance_deficit"]) > 0:
                reasons.append("ACCOUNT_RESTRICTED_OR_MARGIN_DEFICIT")
            if snapshot["risk_metrics_verified"] is not True:
                reasons.append("UNVERIFIED_PNL_OR_DRAWDOWN")
            day_start = positive(snapshot["day_start_equity"])
            week_start = positive(snapshot["week_start_equity"])
            high = positive(snapshot["flow_adjusted_high_water_equity"])
            day_pnl = dec(snapshot["day_pnl_ex_flows"])
            week_pnl = dec(snapshot["week_pnl_ex_flows"])
            flow_adjusted_equity = positive(snapshot["flow_adjusted_equity"])
            if day_pnl <= -day_start * dec(limits["daily_loss"]):
                reasons.append("DAILY_LOSS_BREAKER")
            if week_pnl <= -week_start * dec(limits["weekly_loss"]):
                reasons.append("WEEKLY_LOSS_BREAKER")
            if (high - flow_adjusted_equity) / high >= dec(limits["drawdown"]):
                reasons.append("DRAWDOWN_BREAKER")
            if snapshot["kill_switch"] is not False:
                reasons.append("KILL_SWITCH")
            if quote["event_clear"] is not True:
                reasons.append("EVENT_RISK_NOT_CLEARED")
            if nonnegative(quote["average_daily_dollar_volume"]) < dec(limits["min_daily_dollar_volume"]):
                reasons.append("INSUFFICIENT_LIQUIDITY")
            if (closing - now).total_seconds() <= float(dec(limits["no_entry_minutes_before_close"]) * 60):
                reasons.append("TOO_LATE_FOR_NEW_ENTRY")
            notional = qty * max(price, ask)
            cost = qty * price + qty * dec(limits["fee_per_share"])
            available = min(cash - reserved_cash - equity * dec(limits["cash_floor"]),
                            settled - reserved_cash, buying_power)
            if cost > available:
                reasons.append("INSUFFICIENT_UNRESERVED_SETTLED_CASH")
            # Gross ledger cash may include unsettled proceeds. Keep the intraday
            # liquidity reserve in usable settled funds, after ALL buy reservations.
            # This is an entry budget, never a restriction on reducing owned shares.
            reserve_floor = Decimal(0)
            if sleeve == "intraday":
                reserve_floor = max(
                    equity * dec(limits.get("intraday_settled_cash_floor_fraction", limits["cash_floor"])),
                    dec(limits.get("intraday_settled_cash_floor_amount", 0)))
                settled_budget = max(Decimal(0), settled - reserved_cash - reserve_floor)
                available = min(available, settled_budget)
                if cost > settled_budget:
                    reasons.append("INTRADAY_SETTLED_CASH_RESERVE")
            metrics.update(required_cash=str(cost), reserved_buy_cash=str(reserved_cash),
                           unreserved_settled_cash=str(max(Decimal(0), settled - reserved_cash)),
                           intraday_settled_cash_floor=str(reserve_floor),
                           cash_budget_shortfall=str(max(Decimal(0), cost - available)))
            if sleeve_values[sleeve] + notional > equity * dec(policy["sleeves"][sleeve]):
                reasons.append("SLEEVE_CAP")
            if sleeve == "core" and symbol_values.get(symbol, 0) + notional > equity * dec(policy["core_targets"].get(symbol, 0)):
                reasons.append("CORE_TARGET_CAP")
            asset_cap = "single_etf" if order["asset_type"] == "etf" else "single_stock"
            if symbol_values.get(symbol, 0) + notional > equity * dec(limits[asset_cap]):
                reasons.append("SYMBOL_CAP")
            if order['asset_type'] != 'etf' and sector_values.get(quote["sector"], 0) + notional > equity * dec(limits["sector"]):
                reasons.append("SECTOR_CAP")
            live_symbols = {p["symbol"] for p in positions if dec(p["quantity"]) > 0}
            live_symbols.update(p["symbol"] for p in pending if p["side"] == "buy" and dec(p["remaining_quantity"]) > 0)
            if len(live_symbols | {symbol}) > dec(limits["max_positions"]):
                reasons.append("MAX_POSITIONS")
            if sleeve != "core":
                stop, target = positive(order["stop_price"]), positive(order["target_price"])
                if not stop < price < target:
                    raise InvalidInput("Expected stop < long entry < target")
                friction = 2 * price * dec(limits["slippage_bps"]) / 10000 + 2 * dec(limits["fee_per_share"])
                unit_risk = price - stop + friction
                risk = qty * unit_risk
                if risk > equity * dec(limits["risk_per_trade"]):
                    reasons.append("PER_TRADE_RISK_CAP")
                if open_risk + risk > equity * dec(limits["open_risk"]):
                    reasons.append("OPEN_RISK_CAP")
                reward_risk = (target - price - friction) / unit_risk
                if reward_risk < dec(limits["min_reward_risk"]):
                    reasons.append("REWARD_RISK_AFTER_COSTS")
                exit_by = timestamp(order["exit_by"])
                if exit_by <= now or (sleeve == "intraday" and exit_by >= closing):
                    reasons.append("INVALID_TIME_EXIT")
                metrics.update(planned_loss=str(risk), reward_risk=str(reward_risk))
            metrics.update(available_cash=str(available), projected_sleeve_value=str(sleeve_values[sleeve] + notional))
        metrics.update(spread_bps=str(spread_bps), notional=str(qty * price),
                       existing_open_risk=str(open_risk))
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        reasons.append("INVALID_OR_MISSING_INPUT: " + str(exc))
    disposition = "READY_FOR_NEXT_GATE" if not reasons else "BLOCKED"
    if reasons and set(reasons) <= {"INSUFFICIENT_UNRESERVED_SETTLED_CASH", "INTRADAY_SETTLED_CASH_RESERVE"}:
        disposition = "WAIT_FOR_CASH_BUDGET"
    return {"allowed": not reasons, "reasons": sorted(set(reasons)), "metrics": metrics,
            "entry_disposition": disposition if order.get("side") == "buy" else "NOT_AN_ENTRY",
            "order_hash": canonical_hash(order), "policy_hash": canonical_hash(policy),
            "planned_loss_is_not_guaranteed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("order", type=Path)
    parser.add_argument("--as-of", help="Explicit evaluation time for offline replay only")
    args = parser.parse_args()
    result = evaluate(*(json.loads(p.read_text(encoding="utf-8")) for p in
                        (args.policy, args.snapshot, args.order)),
                      now=timestamp(args.as_of) if args.as_of else None)
    print(json.dumps(result, indent=2))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
