"""Original standard-library point-in-time selection of supplied observations.

snapshot(document) takes exactly {as_of, dataset}. dataset takes exactly
{schema_version: 1, dataset_id, source, records}; source takes exactly nonempty
name, license and uri strings. A record takes exactly instrument_id, asset_class,
currency, field, event_at, available_at, value, unit and revision_id.

Allowed classes: equity, option, future, fx, bond, crypto. currency uses the
three-uppercase-letter ISO 4217 format, not a verified membership/entitlement
claim. Numeric values are finite JSON numbers, never bools. Timestamps require
seconds, a known explicit offset and at most six fractional digits, normalize to
UTC Z without truncation, and are compared chronologically.

Duplicates of instrument/field/event/revision are rejected. Revisions of one
observation must retain asset class, currency and unit; equal availability times
are ambiguous and rejected. Select the latest available revision at as_of after
excluding future event times and future availability. These exclusion counts
partition input rows: future-event exclusion takes precedence over availability.

All output is a new object; inputs are never mutated. Source URI is inert text.
Availability/licensing are caller declarations, not verification. No acquisition,
corporate-action adjustment, fill-forward, FX conversion, filesystem store,
service or trading action occurs. Hashes identify normalized inputs, not source
authenticity. CLI: python point_in_time_data.py supplied-request.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re


DATASET_KEYS = frozenset({"schema_version", "dataset_id", "source", "records"})
SOURCE_KEYS = frozenset({"name", "license", "uri"})
RECORD_KEYS = frozenset({"instrument_id", "asset_class", "currency", "field",
                         "event_at", "available_at", "value", "unit", "revision_id"})
ASSET_CLASSES = frozenset({"equity", "option", "future", "fx", "bond", "crypto"})
TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")


def _object(value, keys, label):
    if type(value) is not dict:
        raise ValueError(f"{label} must be a JSON object")
    if set(value) != keys:
        missing = sorted(keys - set(value))
        unknown = sorted(str(key) for key in set(value) - keys)
        raise ValueError(f"{label} invalid fields; missing={missing}, unknown={unknown}")
    return value


def _text(value, label):
    if type(value) is not str or not value or value != value.strip():
        raise ValueError(f"{label} must be a nonempty trimmed string")
    if any(ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f"{label} contains control characters or invalid Unicode")
    return value


def timestamp(value):
    """Return a canonical known UTC instant; never infer or truncate a timezone."""
    if type(value) is not str or not TIMESTAMP.fullmatch(value):
        raise ValueError("timestamp must be offset-aware RFC 3339 with <=6 fractional digits")
    if value.endswith("-00:00"):
        raise ValueError("timestamp offset must be known")
    if not value.endswith("Z") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("timestamp has an invalid timezone offset")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise ValueError("timestamp is invalid") from error
    precision = "microseconds" if instant.microsecond else "seconds"
    return instant.isoformat(timespec=precision).replace("+00:00", "Z")


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _observation(row):
    return row["instrument_id"], row["field"], row["event_at"]


def _sort_key(row):
    return (row["instrument_id"], row["field"], _instant(row["event_at"]),
            _instant(row["available_at"]), row["revision_id"])


def _hash(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def normalize(document):
    """Validate and return a new, canonically ordered dataset."""
    document = _object(document, DATASET_KEYS, "dataset")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    dataset_id = _text(document["dataset_id"], "dataset_id")
    declared = _object(document["source"], SOURCE_KEYS, "source")
    source = {key: _text(declared[key], "source." + key) for key in sorted(SOURCE_KEYS)}
    if type(document["records"]) is not list:
        raise ValueError("records must be a JSON array")
    records, identities, available_times, conventions = [], set(), set(), {}
    for index, original in enumerate(document["records"]):
        label = f"records[{index}]"
        _object(original, RECORD_KEYS, label)
        row = {key: _text(original[key], label + "." + key)
               for key in ("instrument_id", "asset_class", "currency", "field", "unit", "revision_id")}
        if row["asset_class"] not in ASSET_CLASSES:
            raise ValueError(label + ".asset_class is unsupported")
        if not re.fullmatch(r"[A-Z]{3}", row["currency"]):
            raise ValueError(label + ".currency must use uppercase three-letter ISO 4217 format")
        row.update({key: timestamp(original[key]) for key in ("event_at", "available_at")})
        value = original["value"]
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            raise ValueError(label + ".value must be a finite JSON number, never bool")
        row["value"] = int(value) if type(value) is float and value.is_integer() else value
        observation = _observation(row)
        identity = observation + (row["revision_id"],)
        if identity in identities:
            raise ValueError(label + " duplicates instrument/field/event/revision")
        identities.add(identity)
        availability = observation + (row["available_at"],)
        if availability in available_times:
            raise ValueError(label + " has ambiguous revisions at the same availability time")
        available_times.add(availability)
        convention = row["asset_class"], row["currency"], row["unit"]
        if observation in conventions and conventions[observation] != convention:
            raise ValueError(label + " changes asset class, currency or unit across revisions")
        conventions[observation] = convention
        records.append(row)
    return {"schema_version": 1, "dataset_id": dataset_id, "source": source,
            "records": sorted(records, key=_sort_key)}


def content_hash(document):
    """SHA256 of the normalized entire dataset, including declared provenance."""
    return _hash(normalize(document))


def snapshot(document):
    """Select revisions from exactly {as_of, dataset}, preserving source identity."""
    _object(document, {"as_of", "dataset"}, "request")
    cutoff = timestamp(document["as_of"])
    cutoff_instant = _instant(cutoff)
    dataset = normalize(document["dataset"])
    counts = {"future_event": 0, "future_availability": 0, "superseded_revision": 0}
    selected = {}
    for row in dataset["records"]:
        if _instant(row["event_at"]) > cutoff_instant:
            counts["future_event"] += 1
            continue
        if _instant(row["available_at"]) > cutoff_instant:
            counts["future_availability"] += 1
            continue
        key = _observation(row)
        if key in selected:
            counts["superseded_revision"] += 1
        selected[key] = row
    return {"schema_version": 1, "dataset_id": dataset["dataset_id"],
            "source": dataset["source"], "as_of": cutoff,
            "records": sorted(selected.values(), key=_sort_key),
            "input_record_count": len(dataset["records"]), "selected_record_count": len(selected),
            "exclusion_counts": counts, "dataset_sha256": _hash(dataset),
            "input_sha256": _hash({"as_of": cutoff, "dataset": dataset}),
            "availability_basis": "caller_declared_not_verified",
            "source_license_basis": "caller_declared_not_verified",
            "corporate_action_policy": "no_adjustments_applied",
            "limitation": "Selection from supplied declarations only; no source authenticity, data entitlement, observation completeness or investment-performance verification."}


def strict_load(raw):
    """CLI JSON reader rejects duplicate keys and nonstandard nonfinite literals."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    def constant(value):
        raise ValueError("nonfinite JSON literal: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    arguments = parser.parse_args()
    try:
        result = snapshot(strict_load(arguments.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, OverflowError) as error:
        print(json.dumps({"status": "REJECTED_INPUT", "reason": str(error)}))
        return 1
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
