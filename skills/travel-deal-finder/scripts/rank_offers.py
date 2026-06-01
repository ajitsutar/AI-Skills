#!/usr/bin/env python3
"""Rank manually collected travel offers by qualifying status and total value."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def money(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("$", "").replace(",", "").strip()
    return float(text) if text else 0.0


def offer_total(offer: dict[str, Any]) -> float:
    if offer.get("total_price") not in (None, ""):
        return money(offer["total_price"])
    keys = [
        "base_price",
        "taxes",
        "fees",
        "resort_fees",
        "baggage_fees",
        "seat_fees",
        "car_fees",
        "parking_fees",
    ]
    return sum(money(offer.get(key)) for key in keys)


def penalty(offer: dict[str, Any]) -> float:
    value = 0.0
    if not offer.get("url"):
        value += 25
    if offer.get("cancellable") is False:
        value += 50
    if offer.get("refundable") is False:
        value += 50
    if offer.get("unknown_fees") in (True, "true", "yes"):
        value += 100
    else:
        value += money(offer.get("unknown_fees"))
    if offer.get("split_ticket"):
        value += 75
    if offer.get("poor_location"):
        value += 75
    return value


def qualifies(offer: dict[str, Any]) -> bool:
    if offer.get("qualifies") is False:
        return False
    if offer.get("hard_fail_reason"):
        return False
    return True


def load_offers(path: str) -> list[dict[str, Any]]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    data = json.loads(raw)
    offers = data.get("offers", data) if isinstance(data, dict) else data
    if not isinstance(offers, list):
        raise ValueError("Input must be a JSON array or an object with an offers array.")
    return [dict(offer) for offer in offers]


def markdown_table(offers: list[dict[str, Any]]) -> str:
    ranked = sorted(
        offers,
        key=lambda offer: (
            not qualifies(offer),
            offer_total(offer) + penalty(offer),
            offer_total(offer),
        ),
    )
    rows = [
        "| Rank | Qualifies | Source | Deal | Total | Value score | Notes |",
        "|---:|---|---|---|---:|---:|---|",
    ]
    for index, offer in enumerate(ranked, start=1):
        total = offer_total(offer)
        score = total + penalty(offer)
        source = str(offer.get("source", "")).replace("|", "\\|")
        title = str(offer.get("title", "")).replace("|", "\\|")
        if offer.get("url"):
            title = f"[{title}]({offer['url']})"
        notes = offer.get("hard_fail_reason") or offer.get("notes") or ""
        notes = str(notes).replace("|", "\\|").replace("\n", " ")
        currency = offer.get("currency", "USD")
        rows.append(
            f"| {index} | {'yes' if qualifies(offer) else 'no'} | {source} | "
            f"{title} | {currency} {total:,.2f} | {score:,.2f} | {notes} |"
        )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file path, or '-' for stdin")
    args = parser.parse_args()
    print(markdown_table(load_offers(args.input)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
