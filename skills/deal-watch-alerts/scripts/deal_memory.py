#!/usr/bin/env python3
"""JSON memory helper for deal-watch alerts."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_KEY_FIELDS = [
    "store",
    "product_id_or_url",
    "item_id",
    "model",
    "variant",
    "condition",
    "seller",
    "price",
]


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _clean(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, dict):
        parts = []
        for key in sorted(value):
            cleaned = _clean(value[key])
            if cleaned:
                parts.append(f"{key}={cleaned}")
        return ",".join(parts)
    if isinstance(value, list):
        return ",".join(_clean(item) for item in value if _clean(item))
    return " ".join(str(value).strip().split())


def _product_id_or_url(deal: dict[str, Any]) -> str:
    for key in ("product_id", "asin", "sku", "item_number", "event_id"):
        value = _clean(deal.get(key))
        if value:
            return value
    return _clean(deal.get("product_url") or deal.get("final_url") or deal.get("url"))


def build_key(deal: dict[str, Any]) -> str:
    if deal.get("deal_key"):
        return _clean(deal["deal_key"])

    normalized = dict(deal)
    normalized["product_id_or_url"] = _product_id_or_url(deal)
    if "price" in normalized and normalized["price"] is not None:
        try:
            normalized["price"] = f"{float(normalized['price']):.2f}"
        except (TypeError, ValueError):
            normalized["price"] = _clean(normalized["price"])

    parts = []
    for field in DEFAULT_KEY_FIELDS:
        value = _clean(normalized.get(field))
        if value:
            parts.append(f"{field}={value}")
    return "|".join(parts)


def read_memory(path: Path) -> dict[str, Any]:
    memory = _load_json(path, {"last_updated": None, "alerts_sent": []})
    if not isinstance(memory, dict):
        raise ValueError("memory file must contain a JSON object")
    memory.setdefault("alerts_sent", [])
    if not isinstance(memory["alerts_sent"], list):
        raise ValueError("memory alerts_sent must be a list")
    return memory


def known_keys(memory: dict[str, Any]) -> set[str]:
    keys = set()
    for alert in memory.get("alerts_sent", []):
        if isinstance(alert, dict):
            key = _clean(alert.get("deal_key"))
            if key:
                keys.add(key)
    return keys


def record_alert(path: Path, deal: dict[str, Any], sent_at: str | None, notes: str | None) -> dict[str, Any]:
    memory = read_memory(path)
    deal_key = build_key(deal)
    now = sent_at or _dt.datetime.now(_dt.timezone.utc).isoformat()
    record = {
        "deal_key": deal_key,
        "store": deal.get("store"),
        "product_url": deal.get("product_url") or deal.get("final_url") or deal.get("url"),
        "item_id": deal.get("item_id"),
        "model": deal.get("model") or deal.get("label"),
        "variant": deal.get("variant"),
        "condition": deal.get("condition"),
        "seller": deal.get("seller"),
        "price": deal.get("price"),
        "currency": deal.get("currency"),
        "notified_at": now,
        "notes": notes or deal.get("notes"),
    }
    record = {key: value for key, value in record.items() if value is not None}

    alerts = memory["alerts_sent"]
    for idx, existing in enumerate(alerts):
        if isinstance(existing, dict) and existing.get("deal_key") == deal_key:
            alerts[idx] = {**existing, **record}
            break
    else:
        alerts.append(record)

    memory["last_updated"] = now
    _write_json(path, memory)
    return record


def _read_deal_arg(value: str) -> dict[str, Any]:
    maybe_path = Path(value)
    if maybe_path.exists():
        return _load_json(maybe_path, {})
    return json.loads(value)


def cmd_key(args: argparse.Namespace) -> int:
    deal = _read_deal_arg(args.deal)
    print(build_key(deal))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    deal = _read_deal_arg(args.deal)
    memory = read_memory(Path(args.memory))
    deal_key = build_key(deal)
    duplicate = deal_key in known_keys(memory)
    print(json.dumps({"deal_key": deal_key, "duplicate": duplicate}, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    deal = _read_deal_arg(args.deal)
    record = record_alert(Path(args.memory), deal, args.sent_at, args.notes)
    print(json.dumps(record, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deal alert memory helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    key_parser = subparsers.add_parser("key", help="print the stable deal key")
    key_parser.add_argument("--deal", required=True, help="deal JSON string or path")
    key_parser.set_defaults(func=cmd_key)

    check_parser = subparsers.add_parser("check", help="check if deal key exists in memory")
    check_parser.add_argument("--memory", required=True, help="memory JSON path")
    check_parser.add_argument("--deal", required=True, help="deal JSON string or path")
    check_parser.set_defaults(func=cmd_check)

    record_parser = subparsers.add_parser("record", help="record a sent alert")
    record_parser.add_argument("--memory", required=True, help="memory JSON path")
    record_parser.add_argument("--deal", required=True, help="deal JSON string or path")
    record_parser.add_argument("--sent-at", default=None, help="notification timestamp")
    record_parser.add_argument("--notes", default=None, help="verification notes")
    record_parser.set_defaults(func=cmd_record)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
