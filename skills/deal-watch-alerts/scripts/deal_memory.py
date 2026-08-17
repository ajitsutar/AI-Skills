#!/usr/bin/env python3
"""Atomic duplicate memory and notification claims for deal-watch alerts."""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import math
import os
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


KEY_VERSION = 2
DEFAULT_IDENTITY_FIELDS = (
    "store",
    "product_id_or_url",
    "item_id",
    "model",
    "variant",
    "condition",
    "seller",
    "currency",
)
TRACKING_QUERY_NAMES = {
    "dclid",
    "fbclid",
    "gclid",
    "gbraid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "ref",
    "ref_",
    "source",
    "tag",
    "wbraid",
}
TRACKING_QUERY_PREFIXES = ("utm_",)


@dataclass(frozen=True)
class KeyPolicy:
    identity_fields: tuple[str, ...] = DEFAULT_IDENTITY_FIELDS
    required_identity_fields: tuple[str, ...] = ()
    treat_lower_price_as_new: bool = True
    strip_tracking_parameters: bool = True


def _config_bool(mapping: dict[str, Any], key: str, default: bool) -> bool:
    value = mapping.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"memory.{key} must be true or false, not {value!r}")
    return value


def policy_from_config(config: dict[str, Any] | None) -> KeyPolicy:
    config = config or {}
    memory = config.get("memory") or {}
    if not isinstance(memory, dict):
        raise ValueError("config memory field must be an object")
    duplicate_policy = memory.get("duplicate_policy", "stable_key")
    if duplicate_policy != "stable_key":
        raise ValueError(f"unsupported duplicate_policy: {duplicate_policy}")

    fields = memory.get("key_fields", DEFAULT_IDENTITY_FIELDS)
    if not isinstance(fields, (list, tuple)) or not fields or not all(isinstance(field, str) for field in fields):
        raise ValueError("memory.key_fields must be a non-empty list of field names")
    normalized_fields = []
    for field in fields:
        field = field.strip()
        if not field or field == "price" or field in normalized_fields:
            continue
        normalized_fields.append(field)
    if "currency" not in normalized_fields:
        normalized_fields.append("currency")

    required_fields = memory.get("required_key_fields", ())
    if not isinstance(required_fields, (list, tuple)) or not all(
        isinstance(field, str) for field in required_fields
    ):
        raise ValueError("memory.required_key_fields must be a list of field names")
    normalized_required = []
    for field in required_fields:
        field = field.strip()
        if not field or field == "price" or field in normalized_required:
            continue
        if field not in normalized_fields:
            raise ValueError(f"required key field is not present in memory.key_fields: {field}")
        normalized_required.append(field)
    return KeyPolicy(
        identity_fields=tuple(normalized_fields),
        required_identity_fields=tuple(normalized_required),
        treat_lower_price_as_new=_config_bool(memory, "treat_lower_price_as_new", True),
        strip_tracking_parameters=_config_bool(memory, "strip_tracking_parameters", True),
    )


def _normalize_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).strip().split()).casefold()


def _normalize_url(value: Any, strip_tracking_parameters: bool = True) -> str:
    raw = " ".join(str(value).strip().split())
    if not raw:
        return ""
    parts = urlsplit(raw)
    if not parts.scheme or not parts.netloc:
        return _normalize_text(raw)

    scheme = parts.scheme.casefold()
    hostname = (parts.hostname or "").casefold()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"invalid product URL port: {raw}") from exc
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = hostname if port is None or default_port else f"{hostname}:{port}"
    query = []
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.casefold()
        if strip_tracking_parameters and (
            lowered in TRACKING_QUERY_NAMES or any(lowered.startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
        ):
            continue
        query.append((key, item))
    query.sort(key=lambda pair: (_normalize_text(pair[0]), _normalize_text(pair[1])))
    return urlunsplit((scheme, netloc, parts.path or "/", urlencode(query, doseq=True), ""))


def _canonical(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, (float, Decimal)):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("identity values cannot contain NaN or infinity")
        return _decimal_text(Decimal(str(value)))
    if isinstance(value, dict):
        return {
            _normalize_text(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: _normalize_text(pair[0]))
            if not _is_empty(item)
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value if not _is_empty(item)]
    return _normalize_text(value)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("deal price must be numeric")
    try:
        price = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid deal price: {value!r}") from exc
    if not price.is_finite() or price < 0:
        raise ValueError("deal price must be finite and non-negative")
    return price


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _product_id_or_url(deal: dict[str, Any], policy: KeyPolicy) -> str:
    for key in ("product_id", "asin", "sku", "item_number", "event_id"):
        value = deal.get(key)
        if not _is_empty(value):
            return _normalize_text(value)
    value = deal.get("product_url") or deal.get("final_url") or deal.get("url")
    return _normalize_url(value, policy.strip_tracking_parameters) if value else ""


def _field_value(deal: dict[str, Any], field: str, policy: KeyPolicy) -> Any:
    if field == "product_id_or_url":
        return _product_id_or_url(deal, policy)
    if field == "model":
        return deal.get("model") or deal.get("label")
    if field in {"product_url", "final_url", "url"}:
        return _normalize_url(deal.get(field), policy.strip_tracking_parameters) if deal.get(field) else ""
    return deal.get(field)


def identity_payload(deal: dict[str, Any], policy: KeyPolicy | None = None) -> dict[str, Any]:
    if not isinstance(deal, dict):
        raise ValueError("deal must be a JSON object")
    policy = policy or KeyPolicy()
    payload = {}
    for field in policy.identity_fields:
        value = _field_value(deal, field, policy)
        if not _is_empty(value):
            payload[field] = _canonical(value)

    missing_required = [
        field
        for field in policy.required_identity_fields
        if _is_empty(_field_value(deal, field, policy))
    ]
    if missing_required:
        raise ValueError(f"deal is missing required key fields: {', '.join(missing_required)}")

    identifying = any(
        not _is_empty(deal.get(field))
        for field in ("product_id", "asin", "sku", "item_number", "event_id", "product_url", "final_url", "url", "item_id", "model", "label")
    )
    if not identifying:
        raise ValueError("deal needs a product ID, stable URL, item_id, model, or label")
    if not any(field != "currency" for field in payload):
        raise ValueError("configured memory.key_fields produced no non-currency identity value")
    if not _is_empty(deal.get("price")) and _is_empty(deal.get("currency")):
        raise ValueError("deal currency is required whenever price is present")
    return payload


def _hash_key(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}:v{KEY_VERSION}:{hashlib.sha256(encoded).hexdigest()}"


def build_offer_key(deal: dict[str, Any], policy: KeyPolicy | None = None) -> str:
    policy = policy or KeyPolicy()
    return _hash_key("offer", identity_payload(deal, policy))


def build_key(deal: dict[str, Any], policy: KeyPolicy | None = None) -> str:
    policy = policy or KeyPolicy()
    payload = identity_payload(deal, policy)
    if policy.treat_lower_price_as_new:
        payload = {**payload, "price": _decimal_text(_decimal(deal.get("price")))}
    return _hash_key("deal", payload)


def _empty_memory() -> dict[str, Any]:
    return {
        "version": KEY_VERSION,
        "last_updated": None,
        "alerts_sent": [],
        "pending_claims": [],
        "claim_releases": [],
    }


def canonical_memory_path(path: Path) -> Path:
    """Return one canonical state path so aliases share a lock and data file."""
    path = Path(path).expanduser()
    if path.is_symlink() and not path.exists():
        raise ValueError(f"memory path is a broken symlink: {path}")
    if path.exists():
        return path.resolve(strict=True)
    return path.parent.resolve(strict=False) / path.name


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    if not path.is_file():
        raise ValueError(f"memory path is not a file: {path}")
    # utf-8-sig accepts both regular UTF-8 and the BOM emitted by some Windows tools.
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_memory(path: Path) -> dict[str, Any]:
    path = canonical_memory_path(path)
    memory = _load_json(path, _empty_memory())
    if not isinstance(memory, dict):
        raise ValueError("memory file must contain a JSON object")
    version = memory.get("version")
    if version is None:
        memory["version"] = KEY_VERSION
    elif isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("memory version must be a positive integer; manual review is required")
    elif version > KEY_VERSION:
        raise ValueError(
            f"memory version {version} is newer than supported version {KEY_VERSION}; manual review is required"
        )
    memory.setdefault("last_updated", None)
    memory.setdefault("alerts_sent", [])
    memory.setdefault("pending_claims", [])
    memory.setdefault("claim_releases", [])
    if not isinstance(memory["alerts_sent"], list):
        raise ValueError("memory alerts_sent must be a list")
    if not isinstance(memory["pending_claims"], list):
        raise ValueError("memory pending_claims must be a list")
    if not isinstance(memory["claim_releases"], list):
        raise ValueError("memory claim_releases must be a list")

    alert_keys: set[str] = set()
    for index, alert in enumerate(memory["alerts_sent"], start=1):
        if not isinstance(alert, dict):
            raise ValueError(f"sent alert {index} must be an object; manual review is required")
        deal_key = alert.get("deal_key")
        if not isinstance(deal_key, str) or not deal_key:
            raise ValueError(f"sent alert {index} is missing a valid deal_key; manual review is required")
        if deal_key in alert_keys:
            raise ValueError(f"duplicate sent alert deal_key {deal_key!r}; manual review is required")
        alert_keys.add(deal_key)

    claim_ids: set[str] = set()
    for index, claim in enumerate(memory["pending_claims"], start=1):
        if not isinstance(claim, dict):
            raise ValueError(f"pending claim {index} must be an object; manual review is required")
        required = ("claim_id", "deal_key", "offer_key", "claimed_at", "expires_at")
        missing = [field for field in required if not isinstance(claim.get(field), str) or not claim[field]]
        if missing:
            raise ValueError(
                f"pending claim {index} is missing valid {', '.join(missing)}; "
                "manual review is required"
            )
        if claim["claim_id"] in claim_ids:
            raise ValueError(f"duplicate pending claim id {claim['claim_id']!r}; manual review is required")
        claim_ids.add(claim["claim_id"])
        try:
            claimed_at = _now(claim["claimed_at"])
            expires_at = _now(claim["expires_at"])
        except ValueError as exc:
            raise ValueError(f"pending claim {index} has an invalid timestamp; manual review is required") from exc
        if expires_at <= claimed_at:
            raise ValueError(f"pending claim {index} expires before it was claimed; manual review is required")

    for index, release in enumerate(memory["claim_releases"], start=1):
        if not isinstance(release, dict):
            raise ValueError(f"claim release {index} must be an object; manual review is required")
        required = ("claim_id", "released_at", "reason")
        missing = [field for field in required if not isinstance(release.get(field), str) or not release[field]]
        if missing:
            raise ValueError(
                f"claim release {index} is missing valid {', '.join(missing)}; manual review is required"
            )
        try:
            _now(release["released_at"])
        except ValueError as exc:
            raise ValueError(f"claim release {index} has an invalid timestamp; manual review is required") from exc
    return memory


def _write_json_atomic(path: Path, data: Any) -> None:
    path = canonical_memory_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary_name = handle.name
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temporary_name)


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


def _try_os_lock(handle) -> bool:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def _unlock_os(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def memory_lock(path: Path, timeout: float = 10.0) -> Iterator[None]:
    path = canonical_memory_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with _thread_lock(lock_path):
        with lock_path.open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            deadline = time.monotonic() + timeout
            while not _try_os_lock(handle):
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"timed out waiting for memory lock: {lock_path}")
                time.sleep(0.05)
            try:
                yield
            finally:
                _unlock_os(handle)


def known_keys(memory: dict[str, Any]) -> set[str]:
    return {
        str(alert["deal_key"])
        for alert in memory.get("alerts_sent", [])
        if isinstance(alert, dict) and alert.get("deal_key")
    }


def _record_offer_key(record: dict[str, Any], policy: KeyPolicy) -> str | None:
    if record.get("offer_key"):
        return str(record["offer_key"])
    try:
        return build_offer_key(record, policy)
    except ValueError:
        return None


def _variant_value(record: dict[str, Any], field: str) -> Any:
    variant = record.get("variant")
    if isinstance(variant, dict) and not _is_empty(variant.get(field)):
        return variant.get(field)
    return record.get(field)


def _legacy_record_may_match(alert: dict[str, Any], deal: dict[str, Any], policy: KeyPolicy) -> bool:
    """Fail closed only when an unkeyable legacy alert plausibly describes this offer."""
    for field in ("store", "seller", "condition"):
        prior = alert.get(field)
        current = deal.get(field)
        if not _is_empty(prior) and not _is_empty(current) and _canonical(prior) != _canonical(current):
            return False

    for field in ("screen_size", "ram_gb", "storage_gb", "color"):
        prior = _variant_value(alert, field)
        current = _variant_value(deal, field)
        if not _is_empty(prior) and not _is_empty(current) and _canonical(prior) != _canonical(current):
            return False

    prior_item = alert.get("item_id")
    current_item = deal.get("item_id")
    if not _is_empty(prior_item) and not _is_empty(current_item):
        return _canonical(prior_item) == _canonical(current_item)

    prior_model = alert.get("model") or alert.get("label")
    current_model = deal.get("model") or deal.get("label")
    if not _is_empty(prior_model) and not _is_empty(current_model) and _canonical(prior_model) == _canonical(current_model):
        return True

    id_fields = ("product_id", "asin", "sku", "item_number", "event_id")
    prior_ids = {_normalize_text(alert.get(field)) for field in id_fields if not _is_empty(alert.get(field))}
    current_ids = {_normalize_text(deal.get(field)) for field in id_fields if not _is_empty(deal.get(field))}
    if prior_ids & current_ids:
        return True

    prior_url = alert.get("product_url") or alert.get("final_url") or alert.get("url")
    current_url = deal.get("product_url") or deal.get("final_url") or deal.get("url")
    for product_id in prior_ids | current_ids:
        if len(product_id) >= 4 and (
            (prior_url and product_id in _normalize_text(prior_url))
            or (current_url and product_id in _normalize_text(current_url))
        ):
            return True
    if prior_url and current_url:
        prior_parts = urlsplit(_normalize_url(prior_url, policy.strip_tracking_parameters))
        current_parts = urlsplit(_normalize_url(current_url, policy.strip_tracking_parameters))
        return (prior_parts.netloc, prior_parts.path) == (current_parts.netloc, current_parts.path)
    return False


def classify_deal(memory: dict[str, Any], deal: dict[str, Any], policy: KeyPolicy | None = None) -> dict[str, Any]:
    policy = policy or KeyPolicy()
    deal_key = build_key(deal, policy)
    offer_key = build_offer_key(deal, policy)
    alerts = [alert for alert in memory.get("alerts_sent", []) if isinstance(alert, dict)]
    if deal_key in known_keys(memory):
        return {"deal_key": deal_key, "offer_key": offer_key, "duplicate": True, "reason": "exact_deal_key"}

    same_offer = [alert for alert in alerts if _record_offer_key(alert, policy) == offer_key]
    ambiguous_legacy = [
        alert
        for alert in alerts
        if _record_offer_key(alert, policy) is None and _legacy_record_may_match(alert, deal, policy)
    ]
    if ambiguous_legacy:
        return {
            "deal_key": deal_key,
            "offer_key": offer_key,
            "duplicate": True,
            "reason": "legacy_record_requires_migration",
            "warning": (
                "A plausible prior alert cannot be canonicalized under the current key policy; "
                "notification is blocked until the legacy record is migrated or reviewed."
            ),
            "legacy_deal_keys": [str(alert.get("deal_key")) for alert in ambiguous_legacy],
        }
    if not same_offer:
        return {"deal_key": deal_key, "offer_key": offer_key, "duplicate": False, "reason": "new_offer"}
    if not policy.treat_lower_price_as_new:
        return {"deal_key": deal_key, "offer_key": offer_key, "duplicate": True, "reason": "offer_already_alerted"}

    current_price = _decimal(deal.get("price"))
    prior_prices = []
    for alert in same_offer:
        try:
            prior_prices.append(_decimal(alert.get("price")))
        except ValueError:
            continue
    if not prior_prices:
        return {"deal_key": deal_key, "offer_key": offer_key, "duplicate": False, "reason": "no_comparable_prior_price"}
    best_prior = min(prior_prices)
    if current_price < best_prior:
        return {
            "deal_key": deal_key,
            "offer_key": offer_key,
            "duplicate": False,
            "reason": "lower_price",
            "best_prior_price": _decimal_text(best_prior),
        }
    return {
        "deal_key": deal_key,
        "offer_key": offer_key,
        "duplicate": True,
        "reason": "price_not_lower",
        "best_prior_price": _decimal_text(best_prior),
    }


def _now(value: str | None = None) -> _dt.datetime:
    if value is None:
        return _dt.datetime.now(_dt.timezone.utc)
    parsed = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc)


def _claim_expired(claim: dict[str, Any], now: _dt.datetime) -> bool:
    """Expired claims remain blocking until a human-safe explicit release."""
    return _now(claim["expires_at"]) <= now


def _record_for(deal: dict[str, Any], policy: KeyPolicy, sent_at: str | None, notes: str | None) -> dict[str, Any]:
    now = _now(sent_at).isoformat()
    record = {
        "key_version": KEY_VERSION,
        "deal_key": build_key(deal, policy),
        "offer_key": build_offer_key(deal, policy),
        "store": deal.get("store"),
        "product_id": deal.get("product_id") or deal.get("asin") or deal.get("sku"),
        "product_url": deal.get("product_url") or deal.get("final_url") or deal.get("url"),
        "item_id": deal.get("item_id"),
        "model": deal.get("model") or deal.get("label"),
        "variant": deal.get("variant"),
        "condition": deal.get("condition"),
        "seller": deal.get("seller"),
        "shipping": deal.get("shipping"),
        "availability": deal.get("availability"),
        "price": _decimal_text(_decimal(deal.get("price"))),
        "currency": str(deal.get("currency")).upper(),
        "notified_at": now,
        "notes": notes or deal.get("notes"),
    }
    return {key: value for key, value in record.items() if value is not None}


def _upsert_record(memory: dict[str, Any], record: dict[str, Any]) -> None:
    alerts = memory["alerts_sent"]
    for index, existing in enumerate(alerts):
        if isinstance(existing, dict) and existing.get("deal_key") == record["deal_key"]:
            alerts[index] = {**existing, **record}
            break
    else:
        alerts.append(record)
    memory["version"] = KEY_VERSION
    memory["last_updated"] = record["notified_at"]


def record_alert(
    path: Path,
    deal: dict[str, Any],
    sent_at: str | None,
    notes: str | None,
    policy: KeyPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or KeyPolicy()
    path = canonical_memory_path(path)
    with memory_lock(path):
        memory = read_memory(path)
        record = _record_for(deal, policy, sent_at, notes)
        _upsert_record(memory, record)
        _write_json_atomic(path, memory)
    return record


def check_deal(path: Path, deal: dict[str, Any], policy: KeyPolicy | None = None) -> dict[str, Any]:
    policy = policy or KeyPolicy()
    path = canonical_memory_path(path)
    with memory_lock(path):
        memory = read_memory(path)
        now = _now()
        decision = classify_deal(memory, deal, policy)
        active = next(
            (claim for claim in memory["pending_claims"] if claim.get("offer_key") == decision["offer_key"]),
            None,
        )
        decision["claimed"] = active is not None
        if active:
            decision["claim_expires_at"] = active.get("expires_at")
            decision["claim_expired"] = _claim_expired(active, now)
            if decision["claim_expired"]:
                decision["claim_warning"] = (
                    "Expired claim remains blocking because delivery may have succeeded; "
                    "review provider state before explicit release."
                )
        return decision


def claim_deal(
    path: Path,
    deal: dict[str, Any],
    policy: KeyPolicy | None = None,
    lease_seconds: int = 900,
) -> dict[str, Any]:
    policy = policy or KeyPolicy()
    path = canonical_memory_path(path)
    if lease_seconds < 30 or lease_seconds > 86400:
        raise ValueError("claim lease must be between 30 and 86400 seconds")
    with memory_lock(path):
        memory = read_memory(path)
        now = _now()
        decision = classify_deal(memory, deal, policy)
        if decision["duplicate"]:
            return {**decision, "status": "duplicate", "claimed": False}
        active = next(
            (claim for claim in memory["pending_claims"] if claim.get("offer_key") == decision["offer_key"]),
            None,
        )
        if active:
            return {
                **decision,
                "status": "already_claimed",
                "claimed": False,
                "claim_expires_at": active.get("expires_at"),
                "claim_expired": _claim_expired(active, now),
                "claim_warning": (
                    "Claim remains blocking until delivery is confirmed or explicit release "
                    "is safe; expiration never proves that no notification was accepted."
                ),
            }

        claim_id = uuid.uuid4().hex
        expires = now + _dt.timedelta(seconds=lease_seconds)
        claim = {
            "claim_id": claim_id,
            "deal_key": decision["deal_key"],
            "offer_key": decision["offer_key"],
            "claimed_at": now.isoformat(),
            "expires_at": expires.isoformat(),
        }
        memory["pending_claims"].append(claim)
        memory["version"] = KEY_VERSION
        memory["last_updated"] = now.isoformat()
        _write_json_atomic(path, memory)
        return {**decision, **claim, "status": "claimed", "claimed": True}


def commit_claim(
    path: Path,
    claim_id: str,
    deal: dict[str, Any],
    sent_at: str | None,
    notes: str | None,
    policy: KeyPolicy | None = None,
) -> dict[str, Any]:
    policy = policy or KeyPolicy()
    path = canonical_memory_path(path)
    expected_key = build_key(deal, policy)
    with memory_lock(path):
        memory = read_memory(path)
        match_index = next(
            (
                index
                for index, claim in enumerate(memory["pending_claims"])
                if isinstance(claim, dict) and claim.get("claim_id") == claim_id
            ),
            None,
        )
        if match_index is None:
            raise ValueError("claim not found; do not mark an unclaimed notification as delivered")
        claim = memory["pending_claims"][match_index]
        if claim.get("deal_key") != expected_key:
            raise ValueError("claim does not match this deal")
        record = _record_for(deal, policy, sent_at, notes)
        _upsert_record(memory, record)
        del memory["pending_claims"][match_index]
        _write_json_atomic(path, memory)
        return record


def release_claim(
    path: Path,
    claim_id: str,
    *,
    confirmed_no_delivery: bool = False,
    reason: str | None = None,
) -> bool:
    if not confirmed_no_delivery:
        raise ValueError("claim release requires explicit confirmation that no provider accepted delivery")
    reason = " ".join((reason or "").split())
    if not reason:
        raise ValueError("claim release requires a non-empty nondelivery reason")
    path = canonical_memory_path(path)
    with memory_lock(path):
        memory = read_memory(path)
        released_claims = [
            claim
            for claim in memory["pending_claims"]
            if isinstance(claim, dict) and claim.get("claim_id") == claim_id
        ]
        memory["pending_claims"] = [
            claim
            for claim in memory["pending_claims"]
            if not (isinstance(claim, dict) and claim.get("claim_id") == claim_id)
        ]
        released = bool(released_claims)
        if released:
            released_at = _now().isoformat()
            claim = released_claims[0]
            memory["claim_releases"].append(
                {
                    "claim_id": claim_id,
                    "deal_key": claim.get("deal_key"),
                    "offer_key": claim.get("offer_key"),
                    "released_at": released_at,
                    "reason": reason,
                }
            )
            memory["last_updated"] = released_at
            _write_json_atomic(path, memory)
        return released


def _read_deal_arg(value: str) -> dict[str, Any]:
    stripped = value.lstrip()
    if stripped.startswith("{"):
        data = json.loads(stripped)
    elif value.startswith("@"):
        data = _load_json(Path(value[1:]), None)
    else:
        maybe_path = Path(value)
        data = _load_json(maybe_path, None) if maybe_path.is_file() else json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("deal must be a JSON object")
    return data


def _read_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.is_file():
        raise ValueError(f"config file not found: {config_path}")
    if config_path.suffix.casefold() == ".json":
        data = _load_json(config_path, {})
    else:
        try:
            import yaml
        except ModuleNotFoundError as exc:
            raise ValueError("YAML config requires PyYAML; use JSON or install PyYAML") from exc
        data = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(data, dict):
        raise ValueError("config must contain an object")
    return data


def _policy(args: argparse.Namespace) -> KeyPolicy:
    return policy_from_config(_read_config(getattr(args, "config", None)))


def cmd_key(args: argparse.Namespace) -> int:
    print(build_key(_read_deal_arg(args.deal), _policy(args)))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    result = check_deal(Path(args.memory), _read_deal_arg(args.deal), _policy(args))
    print(json.dumps(result, indent=2))
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    result = claim_deal(
        Path(args.memory),
        _read_deal_arg(args.deal),
        _policy(args),
        lease_seconds=args.lease_seconds,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    record = commit_claim(
        Path(args.memory),
        args.claim_id,
        _read_deal_arg(args.deal),
        args.sent_at,
        args.notes,
        _policy(args),
    )
    print(json.dumps(record, indent=2))
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    released = release_claim(
        Path(args.memory),
        args.claim_id,
        confirmed_no_delivery=args.confirm_no_delivery,
        reason=args.reason,
    )
    print(json.dumps({"claim_id": args.claim_id, "released": released, "reason": args.reason}, indent=2))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    record = record_alert(
        Path(args.memory),
        _read_deal_arg(args.deal),
        args.sent_at,
        args.notes,
        _policy(args),
    )
    print(json.dumps(record, indent=2))
    return 0


def _add_deal_and_policy(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--deal", required=True, help="inline deal JSON, existing JSON path, or @path")
    parser.add_argument("--config", default=None, help="optional JSON/YAML watch config defining memory key policy")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atomic deal alert duplicate memory helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    key_parser = subparsers.add_parser("key", help="print the canonical stable deal key")
    _add_deal_and_policy(key_parser)
    key_parser.set_defaults(func=cmd_key)

    check_parser = subparsers.add_parser("check", help="check prior alerts and active claims")
    check_parser.add_argument("--memory", required=True, help="memory JSON path")
    _add_deal_and_policy(check_parser)
    check_parser.set_defaults(func=cmd_check)

    claim_parser = subparsers.add_parser("claim", help="reserve a new deal before notification")
    claim_parser.add_argument("--memory", required=True, help="memory JSON path")
    _add_deal_and_policy(claim_parser)
    claim_parser.add_argument("--lease-seconds", type=int, default=900)
    claim_parser.set_defaults(func=cmd_claim)

    commit_parser = subparsers.add_parser("commit", help="record delivery for a previously claimed deal")
    commit_parser.add_argument("--memory", required=True, help="memory JSON path")
    commit_parser.add_argument("--claim-id", required=True)
    _add_deal_and_policy(commit_parser)
    commit_parser.add_argument("--sent-at", default=None, help="successful notification timestamp")
    commit_parser.add_argument("--notes", default=None, help="verification and delivery notes")
    commit_parser.set_defaults(func=cmd_commit)

    release_parser = subparsers.add_parser("release", help="release a claim after proven notification failure")
    release_parser.add_argument("--memory", required=True, help="memory JSON path")
    release_parser.add_argument("--claim-id", required=True)
    release_parser.add_argument(
        "--confirm-no-delivery",
        action="store_true",
        required=True,
        help="attest that every attempted provider proved it accepted no notification",
    )
    release_parser.add_argument("--reason", required=True, help="provider evidence supporting safe release")
    release_parser.set_defaults(func=cmd_release)

    record_parser = subparsers.add_parser("record", help="record a sent alert (single-run compatibility mode)")
    record_parser.add_argument("--memory", required=True, help="memory JSON path")
    _add_deal_and_policy(record_parser)
    record_parser.add_argument("--sent-at", default=None, help="successful notification timestamp")
    record_parser.add_argument("--notes", default=None, help="verification and delivery notes")
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
