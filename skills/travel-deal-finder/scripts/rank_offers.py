#!/usr/bin/env python3
"""Rank eligible, same-currency travel offers by their supplied actual totals.

Input is an offers array or an object with an offers array. Eligibility requires
literal JSON qualifies: true, verification: "verified", a nonblank verified_at
string, an HTTP(S) URL, a known total, explicitly false/zero unknown_fees (existing
false forms accepted), and no hard_fail_reason. Missing or blank unknown_fees
leaves fee completeness unconfirmed.
Totals may use total_price or the existing price components; priced offers need
one shared three-letter currency. Missing verification metadata is unverified.
Verification metadata is caller-supplied; this helper does not verify websites
or assess the freshness of the supplied verification timestamp.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
from typing import Any
from urllib.parse import quote, urlsplit


PRICE_COMPONENT_KEYS = (
    "base_price",
    "taxes",
    "fees",
    "resort_fees",
    "baggage_fees",
    "seat_fees",
    "car_fees",
    "parking_fees",
)
TRUE_STRINGS = {"true", "yes", "y", "1"}
UNKNOWN_FEE_TRUE_STRINGS = TRUE_STRINGS | {"unknown"}
FALSE_STRINGS = {"false", "no", "n", "0", "none"}


def money(value: Any, *, field: str = "amount") -> float | None:
    """Parse a nonnegative monetary amount, preserving missing values as None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a monetary number, not a boolean.")
    if isinstance(value, (int, float)):
        amount = float(value)
    else:
        text = str(value).replace("$", "").replace(",", "").strip()
        if not text:
            return None
        try:
            amount = float(text)
        except ValueError as exc:
            raise ValueError(f"{field} is not a valid monetary amount: {value!r}") from exc
    if not math.isfinite(amount) or amount < 0:
        raise ValueError(f"{field} must be a finite, nonnegative amount.")
    return amount


def offer_total(offer: dict[str, Any]) -> float | None:
    if offer.get("total_price") not in (None, ""):
        return money(offer["total_price"], field="total_price")

    components: list[float] = []
    for key in PRICE_COMPONENT_KEYS:
        amount = money(offer.get(key), field=key)
        if amount is not None:
            components.append(amount)
    return money(sum(components), field="component total") if components else None


def boolean_value(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_STRINGS:
            return True
        if normalized in FALSE_STRINGS:
            return False
    raise ValueError(f"Expected a boolean value, got {value!r}.")


def unknown_fee_details(offer: dict[str, Any]) -> tuple[bool | None, float | None]:
    """Return fee presence and estimate; None means completeness is unconfirmed."""
    raw = offer.get("unknown_fees")
    if raw is None or raw == "":
        return None, None
    if raw is False:
        return False, None
    if raw is True:
        return True, None
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in UNKNOWN_FEE_TRUE_STRINGS:
            return True, None
        if normalized in FALSE_STRINGS:
            return False, None
    amount = money(raw, field="unknown_fees")
    if amount is None:
        return None, None
    if amount == 0.0:
        return False, None
    return True, amount


def offer_currency(offer: dict[str, Any]) -> str | None:
    raw = offer.get("currency")
    if raw is None or str(raw).strip() == "":
        return None
    currency = str(raw).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError(f"currency must be a three-letter code, got {raw!r}.")
    return currency


def validate_comparison(offers: list[dict[str, Any]]) -> str | None:
    currencies: set[str] = set()
    for index, offer in enumerate(offers, start=1):
        total = offer_total(offer)
        _, estimated_unknown_fees = unknown_fee_details(offer)
        if total is None and estimated_unknown_fees is None:
            continue
        currency = offer_currency(offer)
        if currency is None:
            raise ValueError(
                f"Offer {index} has a monetary amount but no three-letter currency."
            )
        currencies.add(currency)
    if len(currencies) > 1:
        joined = ", ".join(sorted(currencies))
        raise ValueError(
            f"Priced offers use multiple currencies ({joined}). Convert them to one "
            "documented comparison currency or rank them separately."
        )
    return next(iter(currencies), None)


def qualifies(offer: dict[str, Any]) -> bool:
    return offer.get("qualifies") is True and not offer.get("hard_fail_reason")


def has_url(offer: dict[str, Any]) -> bool:
    raw = offer.get("url")
    return bool(raw) and bool(str(raw).strip())


def eligibility_reasons(offer: dict[str, Any]) -> list[str]:
    """Return all ranking blockers, without treating metadata as live evidence."""
    reasons: list[str] = []
    if offer.get("qualifies") is not True:
        reasons.append("qualifies is not explicitly true")
    if offer.get("hard_fail_reason"):
        reasons.append(f"hard constraint failed: {offer['hard_fail_reason']}")
    if offer.get("verification") != "verified":
        reasons.append("verification is not verified")
    verified_at = offer.get("verified_at")
    if not isinstance(verified_at, str) or not verified_at.strip():
        reasons.append("missing verified_at")
    if not has_url(offer):
        reasons.append("missing source URL")
    else:
        markdown_link_target(offer["url"])
    if offer_total(offer) is None:
        reasons.append("unknown total")
    has_unknown_fees, _ = unknown_fee_details(offer)
    if has_unknown_fees is None:
        reasons.append("fee completeness unconfirmed")
    elif has_unknown_fees:
        reasons.append("unknown fees")
    return reasons


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
    for index, offer in enumerate(offers, start=1):
        if not isinstance(offer, dict):
            raise ValueError(f"Offer {index} must be a JSON object.")
    return [dict(offer) for offer in offers]


def markdown_escape(value: Any) -> str:
    text = html.escape(str(value), quote=False).replace("\r", " ").replace("\n", " ")
    return (
        text.replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )


def markdown_link_target(value: Any) -> str:
    """Return a table-safe URL for an angle-bracketed Markdown destination."""
    text = str(value).replace("\r", "").replace("\n", "")
    try:
        parsed = urlsplit(text)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError(f"offer URL is invalid: {value!r}") from exc
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"offer URL must be an absolute HTTP(S) URL: {value!r}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("offer URL must not embed credentials")
    return quote(text, safe=":/?#[]@!$&'()*+,;=%")


def risk_notes(offer: dict[str, Any]) -> str:
    notes: list[str] = []
    if offer.get("hard_fail_reason"):
        notes.append(str(offer["hard_fail_reason"]))
    if offer.get("notes"):
        notes.append(str(offer["notes"]))
    if not has_url(offer):
        notes.append("missing source URL")
    if boolean_value(offer.get("cancellable")) is False:
        notes.append("noncancellable")
    if boolean_value(offer.get("refundable")) is False:
        notes.append("nonrefundable")
    if boolean_value(offer.get("split_ticket")) is True:
        notes.append("split ticket")
    if boolean_value(offer.get("poor_location")) is True:
        notes.append("poor location")
    return markdown_escape("; ".join(notes))


def sort_key(offer: dict[str, Any]) -> tuple[Any, ...]:
    if eligibility_reasons(offer):
        # Keep unranked offers in input order, without implying price priority.
        return (True, math.inf, "")
    total = offer_total(offer)
    return (False, total, str(offer.get("title", "")))


def markdown_table(offers: list[dict[str, Any]]) -> str:
    validate_comparison(offers)
    ranked = sorted(offers, key=sort_key)
    rows = [
        "Verification metadata is caller-supplied; this helper does not independently "
        "verify live websites or verification freshness.",
        "",
        "| Rank | Qualifies | Verification | Verified at | Source | Deal | Total | Unknown fees | Unranked reason | Notes |",
        "|---:|---|---|---|---|---|---:|---|---|---|",
    ]
    rank = 0
    for offer in ranked:
        reasons = eligibility_reasons(offer)
        if reasons:
            rank_text = "Unranked"
        else:
            rank += 1
            rank_text = str(rank)
        total = offer_total(offer)
        currency = offer_currency(offer)
        has_unknown_fees, estimated_unknown_fees = unknown_fee_details(offer)
        if total is None:
            total_text = "Unknown"
        else:
            assert currency is not None
            total_text = f"{currency} {total:,.2f}"
        if has_unknown_fees is None:
            unknown_fee_text = "unconfirmed"
        elif not has_unknown_fees:
            unknown_fee_text = "no"
        elif estimated_unknown_fees is None:
            unknown_fee_text = "yes (amount unknown)"
        else:
            assert currency is not None
            unknown_fee_text = f"estimated additional {currency} {estimated_unknown_fees:,.2f}"

        source = markdown_escape(offer.get("source", ""))
        title = markdown_escape(offer.get("title", ""))
        if has_url(offer):
            target = markdown_link_target(offer["url"])
            title = f"[{title}](<{target}>)"
        rows.append(
            f"| {rank_text} | {'yes' if qualifies(offer) else 'no'} | "
            f"{markdown_escape(offer.get('verification') or 'unverified')} | "
            f"{markdown_escape(offer.get('verified_at') or '')} | {source} | "
            f"{title} | {total_text} | {unknown_fee_text} | "
            f"{markdown_escape('; '.join(reasons))} | "
            f"{risk_notes(offer)} |"
        )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON file path, or '-' for stdin")
    args = parser.parse_args()
    try:
        output = markdown_table(load_offers(args.input))
    except (json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
