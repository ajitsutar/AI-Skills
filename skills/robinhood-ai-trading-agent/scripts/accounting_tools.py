"""Broker-sourced cash reconciliation, flow-time returns and tax-lot proposal helpers.

The broker remains authoritative. Wash-sale output flags review cases; it does not
calculate tax-basis adjustments or certify substantially-identical securities.
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from risk_engine import dec, nonnegative, positive, timestamp


def cash_reconciliation(opening_cash, entries, broker_cash, as_of):
    """Signed broker ledger entries; trade date and settlement date remain distinct."""
    now = timestamp(as_of)
    balance = dec(opening_cash)
    seen, unsettled = set(), Decimal(0)
    for entry in entries:
        if entry["id"] in seen:
            raise ValueError("Duplicate cash ledger entry")
        seen.add(entry["id"])
        if timestamp(entry["posted_at"]) > now:
            raise ValueError("Future cash entry")
        amount = dec(entry["amount"])
        balance += amount
        if entry["kind"] == "trade" and timestamp(entry["settles_at"]) > now and amount > 0:
            unsettled += amount
    difference = balance - dec(broker_cash)
    return {"calculated_cash": str(balance), "broker_cash": str(dec(broker_cash)),
            "difference": str(difference), "reconciled": abs(difference) <= Decimal("0.01"),
            "unsettled_positive_trade_proceeds": str(unsettled),
            "caveat": "Not a buying-power calculation: use broker settled cash, restrictions and existing reservations"}


def time_weighted_return(initial_equity, initial_at, flow_valuations, ending_equity, ending_at):
    """Exact chaining when values immediately before/after every external flow exist."""
    previous, previous_time = positive(initial_equity), timestamp(initial_at)
    wealth, peak, drawdown = Decimal(1), Decimal(1), Decimal(0)
    periods = []
    for event in flow_valuations:
        at = timestamp(event["at"])
        before, after, flow = positive(event["pre_flow_equity"]), positive(event["post_flow_equity"]), dec(event["external_flow"])
        if at <= previous_time or at > timestamp(ending_at):
            raise ValueError("Flow valuations must be chronological within the measurement period")
        if abs(before + flow - after) > Decimal("0.01"):
            raise ValueError("Pre/post values do not reconcile with external flow")
        factor = before / previous
        wealth *= factor
        peak = max(peak, wealth)
        drawdown = max(drawdown, 1 - wealth / peak)
        periods.append(str(factor - 1))
        previous, previous_time = after, at
    if timestamp(ending_at) < previous_time:
        raise ValueError("Ending valuation precedes last observation")
    factor = positive(ending_equity) / previous
    wealth *= factor
    peak = max(peak, wealth)
    drawdown = max(drawdown, 1 - wealth / peak)
    periods.append(str(factor - 1))
    return {"time_weighted_return": str(wealth - 1), "sampled_drawdown": str(drawdown),
            "period_returns": periods, "caveat": "Drawdown only at supplied marks; dividends/internal cash movements are not external flows"}


def select_lots(lots, quantity, method="FIFO", specific=None):
    quantity = positive(quantity)
    if method not in {"FIFO", "HIFO", "SPECIFIC"}:
        raise ValueError("Unsupported explicit lot-selection method")
    if len({lot["lot_ref"] for lot in lots}) != len(lots):
        raise ValueError("Duplicate tax lot")
    if len({lot["symbol"] for lot in lots}) != 1:
        raise ValueError("Lot selection requires one security")
    prepared = []
    for lot in lots:
        held, cost = nonnegative(lot["quantity"]), nonnegative(lot["cost_per_share"])
        acquired = timestamp(lot["acquired_at"])
        prepared.append((lot, held, cost, acquired))
    if method == "FIFO":
        prepared.sort(key=lambda item: (item[3], item[0]["lot_ref"]))
    elif method == "HIFO":
        prepared.sort(key=lambda item: (-item[2], item[3], item[0]["lot_ref"]))
    else:
        if not specific or len(set(specific)) != len(specific):
            raise ValueError("Specific method needs unique ordered lot references")
        mapping = {item[0]["lot_ref"]: item for item in prepared}
        prepared = [mapping[reference] for reference in specific]
    remaining, selected = quantity, []
    for lot, held, cost, _ in prepared:
        take = min(remaining, held)
        if take:
            selected.append({"lot_ref": lot["lot_ref"], "quantity": str(take), "basis": str(take * cost)})
            remaining -= take
        if remaining == 0:
            break
    if remaining:
        raise ValueError("Insufficient shares in the selected lots")
    return {"method": method, "lots": selected, "execution_authorized": False,
            "next_step": "Verify broker supports this method/lot instruction and obtain applicable order approval"}


def wash_sale_review(symbol, proposed_sale_at, loss_expected, transactions, identity_groups=None,
                     external_account_coverage_complete=False, trade_timezone="America/New_York"):
    zone = ZoneInfo(trade_timezone)
    day = timestamp(proposed_sale_at).astimezone(zone).date()
    group = {symbol} | set((identity_groups or {}).get(symbol, []))
    potential = []
    if loss_expected:
        for entry in transactions:
            distance = (timestamp(entry["at"]).astimezone(zone).date() - day).days
            if entry["side"] == "buy" and entry["symbol"] in group and abs(distance) <= 30:
                potential.append({"local_ref": entry["local_ref"], "symbol": entry["symbol"],
                                  "days_from_sale": distance, "quantity": str(positive(entry["quantity"]))})
    return {"potential_replacements": potential, "external_coverage_complete": external_account_coverage_complete,
            "future_30_day_monitor_needed": bool(loss_expected), "tax_clearance": False,
            "caveat": "Potential matches only; future purchases, other accounts, options and substantially-identical interpretation need review"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8-sig"))
    functions = {"cash": cash_reconciliation, "returns": time_weighted_return,
                 "lots": select_lots, "wash_review": wash_sale_review}
    print(json.dumps(functions[document["operation"]](**document["inputs"]), indent=2))


if __name__ == "__main__":
    main()
