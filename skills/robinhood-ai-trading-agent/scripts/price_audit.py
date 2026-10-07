"""Offline checks on a caller-supplied price audit. No vendor access or auto-repair."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime


JUMP_THRESHOLD = 0.25  # Absolute simple return; a review trigger, never a split detector.


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Audit timestamps require timezone offsets")
    return result


def evidence(value):
    return isinstance(value, list) and bool(value) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def audit_prices(raw_csv, prices, times, metadata=None, *, close_column="close",
                 timestamp_column="timestamp", periods_per_year=252.0):
    """Bind declarations to the exact CSV; fail on unresolved actions/jumps.

    An accepted audit is a structurally complete assertion, not independently
    verified evidence. Missing metadata allows research computation only.
    """
    if len(prices) < 2 or len(prices) != len(times):
        raise ValueError("Audit requires matching price/time series with at least two rows")
    if any(not math.isfinite(float(p)) or p <= 0 for p in prices):
        raise ValueError("Audit requires finite positive prices")
    if any(t.tzinfo is None for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Audit requires unique increasing timezone-bearing timestamps")
    digest = hashlib.sha256(raw_csv).hexdigest()
    jumps = [{"timestamp": times[i].isoformat(), "simple_return": float(prices[i] / prices[i - 1] - 1)}
             for i in range(1, len(prices))
             if abs(prices[i] / prices[i - 1] - 1) >= JUMP_THRESHOLD]
    report = {"csv_sha256": digest, "jump_threshold": JUMP_THRESHOLD,
              "large_moves": jumps, "status": "UNVERIFIED", "eligible_for_sizing": False,
              "limitations": "Caller-supplied audit; evidence not fetched or authenticated by this helper"}
    if metadata is None:
        if jumps:
            raise ValueError("Unreviewed price jump(s): " + ", ".join(j["timestamp"] for j in jumps)
                             + "; audit corporate actions/data before fitting; do not delete real moves")
        report["reasons"] = ["No data-audit manifest: corporate actions and session coverage unverified"]
        return report
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise ValueError("Unsupported data-audit schema")
    if metadata.get("csv_sha256") != digest:
        raise ValueError("Data-audit CSV hash mismatch; regenerate audit after any data change")
    for key, expected in (("close_column", close_column), ("timestamp_column", timestamp_column),
                          ("periods_per_year", periods_per_year)):
        if metadata.get(key) != expected:
            raise ValueError(f"Data-audit {key} does not match this run")
    for key in ("symbol", "provider", "provider_field", "bar_interval", "adjustment_notes"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError(f"Data-audit requires {key}")
    if timestamp(metadata["retrieved_at"]) < times[-1]:
        raise ValueError("Data-audit retrieval precedes the last price")
    if metadata.get("data_kind") not in {"market", "fictional"}:
        raise ValueError("Data-audit data_kind must be market or fictional")
    if metadata.get("price_basis") not in {"split_adjusted", "total_return_adjusted"}:
        raise ValueError("Use a documented split_adjusted or total_return_adjusted series")
    # Audit scope must bind the entire sample, including holdout, to this exact file.
    for field in ("corporate_actions", "session_review"):
        section = metadata.get(field, {})
        if (section.get("status") != "reviewed" or not evidence(section.get("evidence"))
                or timestamp(section["window_start"]) != times[0]
                or timestamp(section["window_end"]) != times[-1]):
            raise ValueError(f"Incomplete {field} review for the exact sample window")
    if not str(metadata["session_review"].get("calendar", "")).strip():
        raise ValueError("Session review must name the calendar/frequency checked")
    actions = metadata["corporate_actions"].get("events")
    if not isinstance(actions, list):
        raise ValueError("Corporate actions must include an events list, even when empty")
    for event in actions:
        effective = timestamp(event["effective_at"])
        if not str(event.get("type", "")).strip() or not evidence(event.get("evidence")):
            raise ValueError("Corporate action requires type and evidence")
        resolution = event.get("resolution")
        if resolution == "outside_sample":
            if times[0] < effective <= times[-1]:
                raise ValueError("Corporate action marked outside_sample is inside the sample")
        elif resolution != "adjusted_in_series":
            raise ValueError("Unresolved corporate action; repair/re-source prices or use a post-action sample")
    reviews = metadata.get("large_move_reviews", [])
    if not isinstance(reviews, list):
        raise ValueError("large_move_reviews must be a list")
    reviewed = {}
    for entry in reviews:
        when = timestamp(entry["timestamp"])
        if when in reviewed or when not in times[1:]:
            raise ValueError("Duplicate or out-of-sample large-move review")
        if entry.get("conclusion") != "genuine_market_move" or not evidence(entry.get("evidence")):
            raise ValueError("Large move must be corroborated as genuine; repair artifacts upstream")
        reviewed[when] = entry
    for jump in jumps:
        if timestamp(jump["timestamp"]) not in reviewed:
            raise ValueError("Unreviewed price jump at " + jump["timestamp"])
    fictional = metadata["data_kind"] == "fictional"
    report.update(status="FICTIONAL" if fictional else "REVIEWED_DECLARATION",
                  eligible_for_sizing=not fictional,
                  reasons=["Fictional data cannot support investment sizing"] if fictional else [],
                  symbol=metadata["symbol"], provider=metadata["provider"],
                  price_basis=metadata["price_basis"], bar_interval=metadata["bar_interval"],
                  action_count=len(actions))
    return report
