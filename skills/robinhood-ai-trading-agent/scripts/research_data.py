"""Read-only public research data and configurable JSON-provider acquisition.

Public prices/fundamentals are research inputs, never executable broker quotes.
Credentials stay in environment variables; saved manifests contain no headers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl, urlunsplit

from risk_engine import canonical_hash, timestamp
from trading_calendar import audit_timestamps, sessions


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_symbol(value):
    if not re.fullmatch(r"[A-Z0-9.^=-]{1,24}", value):
        raise ValueError("Unsupported symbol format; use explicit vendor mapping")
    return value


def clean_json(value):
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path, value):
    Path(path).write_text(json.dumps(clean_json(value), indent=2, allow_nan=False) + "\n", encoding="utf-8")


def get_json(url, headers=None):
    """Bounded GET only; no cross-host redirect carrying provider credentials."""
    import requests
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname
            or parts.username or parts.password):
        raise ValueError("Research provider requires HTTPS without URL credentials")
    if any(re.search(r"(?i)(key|token|secret|password|authorization|credential)", key)
           for key, _ in parse_qsl(parts.query)):
        raise ValueError("Put provider credentials in a configured header environment variable")
    last_status = None
    for attempt in range(3):
        response = requests.get(url, headers=headers or {}, timeout=(5, 20), allow_redirects=False)
        last_status = response.status_code
        if response.status_code == 200:
            return response.json()
        if response.status_code not in {429, 500, 502, 503, 504}:
            break
        if attempt < 2:
            time.sleep(0.5 * (attempt + 1))
    raise ValueError(f"Research provider returned HTTP {last_status}; no cached substitution claimed current")


def sec_companyfacts(cik, output):
    if not re.fullmatch(r"\d{1,10}", str(cik)):
        raise ValueError("CIK must be 1..10 digits")
    contact = os.environ.get("SEC_USER_AGENT")
    if not contact or "@" not in contact:
        raise ValueError("Set SEC_USER_AGENT to your application name and contact email; do not save it in reports")
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json"
    body = get_json(url, {"User-Agent": contact, "Accept": "application/json"})
    if int(body.get("cik", -1)) != int(cik) or not isinstance(body.get("facts"), dict):
        raise ValueError("SEC companyfacts response does not match the requested CIK")
    result = {"source": url, "retrieved_at": utc_now(), "source_hash": canonical_hash(body),
              "cik": int(cik), "data": body,
              "caveat": "Facts retain filing/period/unit contexts; do not sum overlapping quarterly and YTD values"}
    write_json(output, result)
    return {k: v for k, v in result.items() if k != "data"}


def point_in_time_fact(companyfacts, namespace, concept, unit, as_of, start=None, end=None):
    """Select an exact period/unit using only filings available by as_of.

    No guessing tag synonyms, period aggregation or quarters from YTD totals.
    Ambiguous dimensions remain the caller's filing-review responsibility.
    """
    records = companyfacts["facts"][namespace][concept]["units"][unit]
    eligible = [row for row in records if row.get("filed", "9999") <= str(as_of)[:10]
                and (start is None or row.get("start") == start)
                and (end is None or row.get("end") == end)]
    if start is None and end is None:
        raise ValueError("Specify an exact period endpoint; no arbitrary latest fact")
    if not eligible:
        return None
    # Same date with contradictory values must not be silently selected.
    latest_filing = max(row["filed"] for row in eligible)
    latest = [row for row in eligible if row["filed"] == latest_filing]
    contexts = {(row.get("start"), row.get("end"), row["val"]) for row in latest}
    if len(contexts) != 1:
        raise ValueError("Ambiguous SEC period/context; inspect the filing")
    return latest[0]


def yahoo_history(symbol, start, end, directory):
    import yfinance as yf
    symbol = safe_symbol(symbol)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Cache is local to this requested output; no browser profile or broker login.
    yf.set_tz_cache_location(str(directory / ".public-data-cache"))
    frame = yf.Ticker(symbol).history(start=start, end=end, interval="1d", auto_adjust=False,
        back_adjust=False, actions=True, repair=False, keepna=True)
    if frame.empty or "Adj Close" not in frame:
        raise ValueError("No adjusted daily history; do not substitute raw Close")
    schedule = {s["date"]: s for s in sessions(start, end)}
    rows, actions = [], []
    for index, row in frame.iterrows():
        day = index.date().isoformat()
        if day not in schedule:
            raise ValueError("Provider returned a non-session daily observation: " + day)
        if timestamp(schedule[day]['close']) > datetime.now(timezone.utc):
            raise ValueError('Daily history contains an unfinished/future session; request completed sessions only')
        price = float(row["Adj Close"])
        raw_close = float(row["Close"])
        if not all(math.isfinite(p) and p > 0 for p in (price, raw_close)):
            raise ValueError("Missing/invalid price; no silent row dropping")
        rows.append({"timestamp": schedule[day]["close"], "close": price, "raw_close": raw_close})
        for column, kind in (("Stock Splits", "split"), ("Dividends", "dividend")):
            amount = float(row.get(column, 0))
            if amount:
                actions.append({"date": day, "type": kind, "vendor_value": amount,
                                "resolution": "needs_corroboration"})
    csv_path = directory / f"{symbol}-daily.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["timestamp", "close", "raw_close"])
        writer.writeheader()
        writer.writerows(rows)
    # Provider end is exclusive; verify all requested completed sessions before it.
    requested_days = [day for day in schedule if start <= day < end]
    if not requested_days:
        raise ValueError("No sessions in the requested exclusive-end date range")
    coverage = audit_timestamps([row["timestamp"] for row in rows], requested_days[0], requested_days[-1])
    result = {"symbol": symbol, "provider": f"yfinance {yf.__version__} / Yahoo Finance",
        "provider_field": "Adj Close; auto_adjust=false, back_adjust=false, repair=false, keepna=true",
        "retrieved_at": utc_now(), "price_basis": "total_return_adjusted", "bar_interval": "1d",
        "requested_start": start, "requested_end_exclusive": end,
        "csv_path": str(csv_path.resolve()), "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "session_coverage": coverage, "vendor_actions": actions,
        "corporate_action_status": "unreviewed",
        "missing_action_types": ["spinoffs", "merger/security-history completeness", "special distribution treatment"],
        "eligible_as_execution_quote": False,
        "next_step": "Corroborate action treatment and complete price_audit manifest; do not label vendor actions exhaustive"}
    write_json(directory / f"{symbol}-daily-source.json", result)
    return result


def configured_json_provider(config, symbol, output):
    """Optional paid/public JSON endpoint configured by the user, no assumed schema.

    A provider adapter may read this saved envelope; raw fields never become a
    broker snapshot without normalization, source/schema and freshness checks.
    """
    symbol = safe_symbol(symbol)
    endpoint = config["url_template"]
    if endpoint.count("{symbol}") != 1:
        raise ValueError("Provider URL must contain exactly one {symbol} placeholder")
    headers = {"Accept": "application/json"}
    for header, environment in config.get("header_env", {}).items():
        if not re.fullmatch(r"[A-Za-z0-9-]+", header) or not os.environ.get(environment):
            raise ValueError("Missing or invalid configured provider header environment")
        headers[header] = os.environ[environment]
    body = get_json(endpoint.replace("{symbol}", symbol), headers)
    parts = urlsplit(endpoint.replace("{symbol}", symbol))
    result = {"provider": config["name"], "symbol": symbol, "retrieved_at": utc_now(),
              "source_url": urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")), "data": body,
              "source_hash": canonical_hash(body), "eligible_as_execution_quote": False}
    write_json(output, result)
    return {k: v for k, v in result.items() if k != "data"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sec = sub.add_parser("sec-facts")
    sec.add_argument("cik")
    sec.add_argument("output", type=Path)
    history = sub.add_parser("history")
    history.add_argument("symbol")
    history.add_argument("--start", required=True)
    history.add_argument("--end", required=True)
    history.add_argument("--output-dir", type=Path, required=True)
    custom = sub.add_parser("provider")
    custom.add_argument("config", type=Path)
    custom.add_argument("symbol")
    custom.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.command == "sec-facts":
        result = sec_companyfacts(args.cik, args.output)
    elif args.command == "history":
        result = yahoo_history(args.symbol, args.start, args.end, args.output_dir)
    else:
        result = configured_json_provider(json.loads(args.config.read_text(encoding="utf-8-sig")), args.symbol, args.output)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
