"""Free public market evidence: pure parsers/eligibility and explicit bounded CLI.

No network or filesystem access occurs in normalize() or parse(). Source metadata
is a declaration, not authentication, licensing advice, or execution authority.
"""
import argparse
import copy
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from http.client import HTTPException
import io
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET
import zipfile

KINDS = frozenset(("trade", "bar", "short_sale_volume", "short_interest", "float",
                   "borrow", "catalyst", "social_lead", "disclosure", "ftd", "venue_aggregate"))
MAX_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 200000
LIMITATIONS = [
    "Source declarations and local hashes do not authenticate a source or establish redistribution rights.",
    "Eligibility means usable under declared clocks; it does not establish accuracy, completeness, freshness or a trading edge.",
    "Short-sale volume is trading activity, not outstanding short interest; short-exempt volume is already included.",
    "FTD rows are outstanding aggregate balances, not daily new fails, positions or evidence of abusive short selling.",
    "Disclosures are delayed reported holdings/transactions; 13F omits short positions and does not identify today's trades.",
    "Venue totals and public prints do not identify beneficial owners, aggressor intent, opening/closing trades or hedges.",
    "Social posts are leads requiring primary verification, never an authenticated catalyst or always-on feed.",
]
ADAPTERS = frozenset(("sec_submissions", "sec_form4_xml", "sec_13f_xml",
                     "finra_short_volume", "finra_short_interest_csv", "sec_ftd",
                     "venue_csv", "social_leads"))


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _clock(value):
    _require(type(value) is str and bool(re.search(r"T\d{2}:\d{2}", value)),
             "Timestamp must include time and timezone")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid timestamp") from error
    _require(result.utcoffset() is not None, "Timestamp must include timezone")
    return result.astimezone(timezone.utc)


def _url(value):
    if type(value) is not str:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username
                and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        return False


def _number(value, optional=False, exact=False):
    if optional and (value is None or str(value).strip() in ("", ".", "N/A", "NA", "--")):
        return None
    _require(type(value) in (str, int, float, Decimal) and type(value) is not bool, "Numeric value required")
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except InvalidOperation as error:
        raise ValueError("Invalid numeric value") from error
    _require(result.is_finite() and result >= 0, "Finite nonnegative number required")
    converted = float(result)
    _require(math.isfinite(converted), "Number exceeds finite output range")
    if exact:
        return result
    return int(result) if result == result.to_integral_value() else converted


def _day(value):
    value = str(value).strip()
    if re.fullmatch(r"\d{8}", value):
        value = value[:4] + "-" + value[4:6] + "-" + value[6:]
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError("Expected ISO or YYYYMMDD date") from error


def normalize(document):
    """Preserve envelopes and add cutoff/revision eligibility; never fetch data."""
    _require(type(document) is dict and type(document.get("schema_version")) is int
             and document["schema_version"] == 1, "Expected schema_version 1 document")
    cutoff = _clock(document.get("as_of"))
    supplied = document.get("records")
    _require(type(supplied) is list and len(supplied) <= MAX_RECORDS, "records must be a bounded list")
    records, issues, ids, availability = [], [], {}, {}
    for index, original in enumerate(supplied):
        _require(type(original) is dict, "Each record must be an object")
        row = copy.deepcopy(original)
        reasons = []
        identity = row.get("id")
        if type(identity) is not str or not identity.strip():
            reasons.append("MISSING_RECORD_ID")
        else:
            ids.setdefault(identity, []).append(index)
        if type(row.get("kind")) is not str or row.get("kind") not in KINDS:
            reasons.append("UNKNOWN_RECORD_KIND")
        if type(row.get("payload")) is not dict:
            reasons.append("PAYLOAD_NOT_OBJECT")
        source = row.get("source")
        if type(source) is not dict:
            source = {}
            reasons.append("SOURCE_NOT_OBJECT")
        if type(source.get("id")) is not str or not source.get("id", "").strip():
            reasons.append("MISSING_SOURCE_ID")
        if not _url(source.get("url")):
            reasons.append("SOURCE_URL_INVALID")
        try:
            available = _clock(row.get("available_at"))
            availability[index] = available
            if available > cutoff:
                reasons.append("NOT_YET_AVAILABLE")
        except ValueError:
            available = None
            reasons.append("AVAILABILITY_UNKNOWN_OR_INVALID")
        parsed_clocks = {}
        for field in ("retrieved_at", "published_at", "observed_at"):
            value = source.get(field)
            if value is not None:
                try:
                    parsed_clocks[field] = _clock(value)
                except ValueError:
                    reasons.append("INVALID_SOURCE_" + field.upper())
        if available is not None:
            snapshot = parsed_clocks.get("retrieved_at")
            if source.get("availability_basis") == "first_observed_snapshot":
                if snapshot is None:
                    reasons.append("SNAPSHOT_RETRIEVAL_UNKNOWN")
                elif available < snapshot:
                    reasons.append("AVAILABILITY_BEFORE_SNAPSHOT")
            if parsed_clocks.get("published_at", available) > available:
                reasons.append("AVAILABILITY_BEFORE_DECLARED_PUBLICATION")
        if parsed_clocks.get("observed_at", cutoff) > cutoff:
            reasons.append("SOURCE_OBSERVATION_AFTER_CUTOFF")
        if row.get("parse_error"):
            reasons.append("PARSE_ERROR")
        if row.get("action", "new") not in ("new", "replace", "cancel"):
            reasons.append("UNKNOWN_REVISION_ACTION")
        if row.get("action") in ("replace", "cancel") and not row.get("supersedes"):
            reasons.append("REVISION_TARGET_MISSING")
        if row.get("kind") == "social_lead":
            payload = row.get("payload", {})
            if type(payload) is dict and (not payload.get("author") or not payload.get("canonical_url")):
                reasons.append("SOCIAL_IDENTITY_MISSING")
        row["eligible"] = not reasons
        row["exclusion_reasons"] = reasons
        records.append(row)
    for identity, positions in ids.items():
        if len(positions) > 1:
            issues.append({"code": "DUPLICATE_RECORD_ID", "id": identity, "indices": positions})
            for index in positions:
                records[index]["exclusion_reasons"].append("DUPLICATE_RECORD_ID")
                records[index]["eligible"] = False
    # Apply explicit revisions only when the new vintage was usable at cutoff.
    # Raw envelopes remain present, including unavailable and cancelled vintages.
    for index in sorted(availability, key=lambda number: (availability[number], number)):
        row = records[index]
        action = row.get("action", "new")
        if action not in ("replace", "cancel") or not row["eligible"]:
            continue
        target = row.get("supersedes")
        positions = ids.get(target, []) if type(target) is str else []
        reason = None
        if len(positions) != 1 or positions[0] == index:
            reason = "REVISION_TARGET_AMBIGUOUS_OR_MISSING"
        elif positions[0] not in availability or availability[positions[0]] >= availability[index]:
            reason = "REVISION_ORDER_UNRESOLVED"
        else:
            previous = records[positions[0]]
            current_scope = (row.get("kind"), row.get("ticker"), row["source"].get("id"),
                             urlsplit(row["source"]["url"]).hostname)
            previous_source = previous.get("source", {})
            if type(previous_source) is not dict:
                previous_source = {}
            previous_scope = (previous.get("kind"), previous.get("ticker"), previous_source.get("id"),
                              urlsplit(previous_source["url"]).hostname if _url(previous_source.get("url")) else None)
            if current_scope != previous_scope:
                reason = "REVISION_SCOPE_MISMATCH"
            scope_fields = {
                "trade": ("feed_id", "trade_id", "currency", "quantity_unit", "issuer_id", "share_class"),
                "bar": ("feed_id", "bar_type", "start_at", "end_at", "session_id", "volume_unit",
                        "currency", "comparison_group", "issuer_id", "share_class", "price_basis", "volume_basis"),
            }.get(row.get("kind"), ())
            left, right = row.get("payload", {}), previous.get("payload", {})
            if type(right) is not dict:
                right = {}
            if any((key in left or key in right)
                   and (key not in left or key not in right or left[key] != right[key])
                   for key in scope_fields):
                reason = "REVISION_SCOPE_MISMATCH"
        if reason:
            row["eligible"] = False
            row["exclusion_reasons"].append(reason)
            continue
        previous = records[positions[0]]
        previous["eligible"] = False
        previous["exclusion_reasons"].append("CANCELLED_BY_AVAILABLE_REVISION" if action == "cancel"
                                             else "SUPERSEDED_BY_AVAILABLE_REVISION")
        if action == "cancel":
            row["eligible"] = False
            row["exclusion_reasons"].append("CANCELLATION_ENVELOPE")
    return {"kind": "MARKET_EVIDENCE", "schema_version": 1, "as_of": document["as_of"],
            "records": records, "issues": issues, "limitations": list(LIMITATIONS),
            "execution_authorized": False}


def _xml(text):
    _require(not re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I), "DTD/entities are not supported")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("Invalid XML") from error
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    return root


def _text(node, path):
    child = node.find(path)
    return child.text.strip() if child is not None and child.text else None


def _table(text, delimiter=None):
    lines = text.lstrip("\ufeff").splitlines()
    _require(bool(lines), "Empty delimited file")
    if delimiter is None:
        delimiter = "|" if "|" in lines[0] else ","
    _require(delimiter in (",", "|", "\t"), "Unsupported delimiter")
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter=delimiter)
    # DictReader would silently discard one value for an identical literal
    # heading. Distinct spellings stay intact for field-level alias comparison.
    _require(reader.fieldnames and all(_key(field) for field in reader.fieldnames)
             and len(set(reader.fieldnames)) == len(reader.fieldnames),
             "Missing or duplicate header fields")
    rows = []
    for row in reader:
        _require(len(rows) <= MAX_RECORDS, "Too many source rows")
        rows.append(row)
    return reader.fieldnames, rows


def _key(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _field(row, *names, required=True, compare=None):
    keys = {_key(name) for name in names}
    matches = [(key, value) for key, value in row.items() if key is not None and _key(key) in keys]
    if matches:
        # Include normalized-heading collisions and every supported semantic
        # alias. A returned field is never selected ahead of a conflicting one.
        comparable = [compare(value) if compare else value.strip() for _, value in matches]
        _require(all(value == comparable[0] for value in comparable),
                 "Conflicting source field aliases: " + ", ".join(key for key, _ in matches))
        return matches[0][1]
    if required:
        raise ValueError("Missing source field: " + names[0])
    return None


def _source_record(document, index, kind, ticker, payload):
    source = copy.deepcopy(document.get("source", {}))
    available = document.get("available_at")
    if available is None and source.get("retrieved_at"):
        available = source["retrieved_at"]
        source["availability_basis"] = "first_observed_snapshot"
    prefix = document["_parsed_id_prefix"]
    record = {"id": str(prefix) + ":" + str(index), "kind": kind, "ticker": ticker,
              "available_at": available, "source": source, "payload": payload}
    context = document.get("security_context", {})
    if type(context) is dict and type(context.get(ticker)) is dict:
        for key, value in context[ticker].items():
            payload.setdefault(key, copy.deepcopy(value))
    return record


def parse(document):
    """Parse retained source text/JSON; never read paths, download, or infer clocks."""
    _require(type(document) is dict and document.get("adapter") in ADAPTERS, "Unsupported source adapter")
    adapter = document["adapter"]
    _require(type(document.get("source", {})) is dict, "Parser source must be an object")
    document = dict(document)
    source_text = document.get("text", "")
    _require(type(source_text) is str and len(source_text.encode("utf8")) <= MAX_BYTES, "Source text too large")
    if document.get("id_prefix") is not None:
        _require(type(document["id_prefix"]) is str and document["id_prefix"].strip(), "id_prefix must be nonempty")
        document["_parsed_id_prefix"] = document["id_prefix"]
    else:
        content = json.dumps(document["data"], sort_keys=True, ensure_ascii=False, allow_nan=False) if document.get("data") is not None else source_text
        source = document.get("source", {})
        vintage = json.dumps([adapter, source.get("url"), source.get("retrieved_at"), content], ensure_ascii=False)
        document["_parsed_id_prefix"] = str(source.get("id", adapter)) + ":" + hashlib.sha256(vintage.encode("utf8")).hexdigest()[:20]
    records, metadata, issues = [], {}, []

    def emit(kind, ticker, payload):
        _require(len(records) < MAX_RECORDS, "Too many parsed records")
        records.append(_source_record(document, len(records), kind, ticker, payload))

    if adapter == "sec_submissions":
        data = document.get("data")
        if data is None:
            data = json.loads(source_text)
        _require(type(data) is dict, "SEC submissions JSON must be an object")
        recent = data.get("filings", {}).get("recent", data if "accessionNumber" in data else {})
        _require(type(recent) is dict and type(recent.get("accessionNumber")) is list, "Missing SEC recent array")
        count = len(recent["accessionNumber"])
        _require(count <= MAX_RECORDS and all(type(values) is list and len(values) == count
                                            for values in recent.values()), "SEC column lengths differ")
        cik = str(data.get("cik", document.get("cik", "")))
        for index in range(count):
            raw = {key: values[index] for key, values in recent.items()}
            accession = str(raw.get("accessionNumber", ""))
            primary = raw.get("primaryDocument")
            primary_url = None
            if cik.isdigit() and re.fullmatch(r"\d{10}-\d{2}-\d{6}", accession) and type(primary) is str:
                parts = primary.split("/")
                if all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) and part not in (".", "..") for part in parts):
                    primary_url = ("https://www.sec.gov/Archives/edgar/data/" + str(int(cik)) + "/"
                                   + accession.replace("-", "") + "/" + "/".join(quote(part) for part in parts))
            emit("disclosure", document.get("ticker"), {
                "form": raw.get("form"), "filing_date": raw.get("filingDate"),
                "report_date": raw.get("reportDate"), "accession_number": accession,
                "reported_acceptance_at": raw.get("acceptanceDateTime"),
                "primary_document_url": primary_url,
                "primary_document_url_status": "CONSTRUCTED_NOT_FETCHED" if primary_url else "UNRESOLVED",
                "filer_cik": cik,
                "filer_name": data.get("name"), "raw_fields": raw,
                "disclosure_scope": "filing_metadata_not_position_or_trade",
            })
        metadata = {"additional_history_files": copy.deepcopy(data.get("filings", {}).get("files", [])),
                    "filer_tickers": data.get("tickers"), "history_complete": False}
    elif adapter in ("sec_form4_xml", "sec_13f_xml"):
        root = _xml(source_text)
        if adapter == "sec_form4_xml":
            _require(root.tag == "ownershipDocument", "Expected raw ownership XML, not rendered HTML")
            ticker = _text(root, "issuer/issuerTradingSymbol") or document.get("ticker")
            metadata = {"issuer_cik": _text(root, "issuer/issuerCik"),
                        "reporting_owners": [ET.tostring(node, encoding="unicode") for node in root.findall("reportingOwner")],
                        "footnotes": [ET.tostring(node, encoding="unicode") for node in root.findall("footnotes/footnote")]}
            for tag in ("nonDerivativeTransaction", "derivativeTransaction"):
                for node in root.iter(tag):
                    emit("disclosure", ticker, {
                        "form": _text(root, "documentType"), "transaction_type": tag,
                        "transaction_date": _text(node, "transactionDate/value"),
                        "transaction_code": _text(node, "transactionCoding/transactionCode"),
                        "acquired_disposed_code": _text(node, "transactionAmounts/transactionAcquiredDisposedCode/value"),
                        "shares": _number(_text(node, "transactionAmounts/transactionShares/value"), optional=True),
                        "price": _number(_text(node, "transactionAmounts/transactionPricePerShare/value"), optional=True),
                        "security_title": _text(node, "securityTitle/value"),
                        "direct_indirect": _text(node, "ownershipNature/directOrIndirectOwnership/value"),
                        "raw_xml": ET.tostring(node, encoding="unicode"),
                        "interpretation": "reported_transaction_code_requires_footnote_and_ownership_review",
                    })
        else:
            nodes = list(root.iter("infoTable"))
            _require(bool(nodes) or root.tag == "informationTable", "Expected raw 13F information table XML")
            value_unit = document.get("value_unit", "unknown")
            _require(value_unit in ("USD", "USD_thousands", "unknown"), "Declare 13F value_unit")
            for node in nodes:
                emit("disclosure", None, {
                    "form": document.get("form", "13F-HR"), "report_date": document.get("report_date"),
                    "issuer_name": _text(node, "nameOfIssuer"), "security_class": _text(node, "titleOfClass"),
                    "cusip": _text(node, "cusip"), "figi": _text(node, "figi"),
                    "reported_value": _number(_text(node, "value")), "value_unit": value_unit,
                    "shares_or_principal": _number(_text(node, "shrsOrPrnAmt/sshPrnamt")),
                    "shares_or_principal_unit": _text(node, "shrsOrPrnAmt/sshPrnamtType"),
                    "put_call": _text(node, "putCall"), "investment_discretion": _text(node, "investmentDiscretion"),
                    "raw_xml": ET.tostring(node, encoding="unicode"),
                    "disclosure_scope": "reported_long_holdings_not_short_positions_or_current_trades",
                })
            metadata = {"value_unit_declared": value_unit, "ticker_mapping_performed": False}
    elif adapter == "social_leads":
        data = document.get("data")
        if data is None:
            data = json.loads(source_text)
        _require(type(data) is list and len(data) <= MAX_RECORDS, "Social leads must be a bounded list")
        for item in data:
            _require(type(item) is dict, "Social lead must be an object")
            original_url = item.get("url", "")
            match = re.fullmatch(r"https://(?:www\.)?(?:x\.com|twitter\.com)/([A-Za-z0-9_]{1,15})/status/(\d+)(?:[?#].*)?", original_url)
            canonical = "https://x.com/" + match[1] + "/status/" + match[2] if match else None
            payload = copy.deepcopy(item)
            payload.update(canonical_url=canonical, author=item.get("author"),
                           original_url=original_url, requires_primary_verification=True,
                           declared_primary_verified=copy.deepcopy(item.get("primary_verified")),
                           primary_verified=False, raw_fields=copy.deepcopy(item),
                           primary_verification_status="NOT_ESTABLISHED_BY_SOCIAL_PARSER",
                           use="lead_only")
            emit("social_lead", item.get("ticker"), payload)
    else:
        headers, rows = _table(source_text, document.get("delimiter"))
        if adapter == "finra_short_volume":
            trailer_present = False
            if rows:
                last = rows[-1]
                values = [value for value in last.values() if value is not None]
            else:
                values = []
            if len(values) == 1 and str(values[0]).isdigit():
                trailer_present = True
                declared_count = int(values[0])
                rows.pop()
                if declared_count != len(rows):
                    issues.append({"code": "FINRA_TRAILER_COUNT_MISMATCH", "declared": declared_count, "observed": len(rows)})
            if not trailer_present:
                issues.append({"code": "FINRA_TRAILER_MISSING"})
        for index, row in enumerate(rows):
            kind = {"finra_short_volume": "short_sale_volume", "finra_short_interest_csv": "short_interest",
                    "sec_ftd": "ftd", "venue_csv": "venue_aggregate"}[adapter]
            ticker = None
            try:
                _require(None not in row and all(value is not None for value in row.values()), "Malformed delimited row")
                ticker = _field(row, "Symbol", "Issue Symbol", "issueSymbolIdentifier", "BATS-Symbol")
                if adapter == "finra_short_volume":
                    payload = {"trade_date": _day(_field(row, "Date", compare=_day)),
                               "short_volume": _number(_field(row, "ShortVolume", compare=lambda v: _number(v, exact=True))),
                               "short_exempt_volume": _number(_field(row, "ShortExemptVolume", "Short Exempt Volume", compare=lambda v: _number(v, exact=True))),
                               "total_volume": _number(_field(row, "TotalVolume", compare=lambda v: _number(v, exact=True))),
                               "market": _field(row, "Market"), "volume_unit": "shares",
                               "coverage": "FINRA_reported_subset", "short_volume_includes_exempt": True}
                    _require(payload["short_exempt_volume"] <= payload["short_volume"] <= payload["total_volume"],
                             "Inconsistent short-sale volume components")
                elif adapter == "finra_short_interest_csv":
                    payload = {"settlement_date": _day(_field(row, "Settlement Date", "settlementDate", "Cycle Settlement Date", compare=_day)),
                               "short_interest_shares": _number(_field(row, "Current Short", "currentShortPositionQuantity", "Short Interest", "# Shares Net Short Current Cycle", compare=lambda v: _number(v, exact=True))),
                               "average_daily_volume": _number(_field(row, "Avg Daily Volume", "averageDailyVolumeQuantity", "Cycle Avg Daily Trade Vol", required=False, compare=lambda v: _number(v, optional=True, exact=True)), optional=True),
                               "reported_days_to_cover": _number(_field(row, "Days to Cover", "daysToCoverQuantity", "Min # of Trade Days To Cover Shorts", required=False, compare=lambda v: _number(v, optional=True, exact=True)), optional=True),
                               "security_name": _field(row, "Issue Name", "issueName", "Security Name", required=False),
                               "measure_basis": "official_reported", "volume_unit": "shares",
                               "source_authenticity": "not_verified_by_parser"}
                    if any(_key(key) == _key("Min # of Trade Days To Cover Shorts") for key in row):
                        payload["reported_days_to_cover_semantics"] = "source_reported_minimum_trade_days_to_cover"
                    if any(_key(key) == _key("Cycle Avg Daily Trade Vol") for key in row):
                        payload["average_daily_volume_semantics"] = "source_reported_cycle_average_daily_trade_volume"
                elif adapter == "sec_ftd":
                    payload = {"settlement_date": _day(_field(row, "SETTLEMENT DATE", compare=_day)),
                               "cusip": _field(row, "CUSIP"), "quantity": _number(_field(row, "QUANTITY (FAILS)", compare=lambda v: _number(v, exact=True))),
                               "price": _number(_field(row, "PRICE", compare=lambda v: _number(v, optional=True, exact=True)), optional=True),
                               "description": _field(row, "DESCRIPTION"), "quantity_unit": "shares",
                               "balance_semantics": "aggregate_outstanding_fails",
                               "price_semantics": "reported_prior_day_close_or_unavailable"}
                else:
                    columns = document.get("columns")
                    _require(type(columns) is dict and all(key in columns for key in ("week_start", "venue", "shares", "trades")),
                             "venue_csv requires explicit week_start/venue/shares/trades column mapping")
                    payload = {"week_start": _day(row[columns["week_start"]]), "venue": row[columns["venue"]],
                               "shares": _number(row[columns["shares"]]), "trades": _number(row[columns["trades"]]),
                               "volume_unit": "shares", "scope": document.get("venue_scope", "declared_export_subset")}
                payload["raw_fields"] = copy.deepcopy(row)
                emit(kind, ticker, payload)
            except (ValueError, KeyError, TypeError) as error:
                emit(kind, ticker, {"raw_fields": copy.deepcopy(row)})
                records[-1]["parse_error"] = str(error)
                issues.append({"code": "ROW_PARSE_ERROR", "row": index, "detail": str(error)})
        if issues and any(item["code"] in ("FINRA_TRAILER_COUNT_MISMATCH", "FINRA_TRAILER_MISSING") for item in issues):
            for record in records:
                record["parse_error"] = "FINRA trailer count does not reconcile"
        metadata["source_headers"] = headers
    result = normalize({"schema_version": document.get("schema_version"), "as_of": document.get("as_of"), "records": records})
    result["issues"].extend(issues)
    result["adapter"] = adapter
    result["adapter_metadata"] = metadata
    return result


def allowed_public_url(url):
    """Exact public-source host/path families, without redirects or credentials."""
    _require(_url(url), "Only credential-free HTTPS URLs are supported")
    parsed = urlsplit(url)
    _require(not parsed.query and not parsed.fragment, "Use an exact public file URL without query/fragment")
    patterns = {
        "data.sec.gov": [r"/submissions/CIK\d{10}(?:-submissions-\d{3})?\.json"],
        "www.sec.gov": [r"/Archives/edgar/data/\d+/\d{18}/(?:[A-Za-z0-9_.-]+/){0,2}[A-Za-z0-9_.-]+\.(?:xml|txt|json|htm|html)",
                        r"/files/data/fails-deliver-data/[A-Za-z0-9_-]+\.(?:zip|txt)"],
        "cdn.finra.org": [r"/equity/regsho/daily/[A-Za-z]+shvol\d{8}(?:[_-][A-Za-z]+)?\.txt"],
        "cdn.cboe.com": [r"/resources/us/equities/market-statistics/short-interest/[A-Za-z0-9_.-]+\.csv"],
    }
    _require(parsed.hostname in patterns and any(re.fullmatch(pattern, parsed.path) for pattern in patterns[parsed.hostname]),
             "URL is outside supported public file families")
    _require(all(part not in (".", "..") for part in parsed.path.split("/")), "Unsafe public path")
    return parsed.hostname


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise HTTPError(request.full_url, code, "Redirect refused; verify the final public URL", headers, response)


def _write_json(path, value):
    with path.open("x", encoding="utf8") as output:
        json.dump(value, output, indent=2, ensure_ascii=False, allow_nan=False)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())


def acquire(url, output_dir, source_id, user_agent, rights="unknown", max_bytes=8 * 1024 * 1024,
            timeout=15, retries=1):
    """One explicitly requested public download; no credentials, polling or parser execution."""
    allowed_public_url(url)
    _require(type(source_id) is str and source_id.strip(), "source_id required")
    _require(type(user_agent) is str and len(user_agent) <= 300 and "\n" not in user_agent
             and "\r" not in user_agent and ("@" in user_agent or "https://" in user_agent),
             "Identify the research client with a real contact User-Agent")
    _require(type(max_bytes) is int and 1 <= max_bytes <= MAX_BYTES, "Invalid byte bound")
    _require(type(retries) is int and 0 <= retries <= 2, "retries must be 0..2")
    _require(type(timeout) in (int, float) and not isinstance(timeout, bool)
             and math.isfinite(timeout) and 0 < timeout <= 30, "timeout must be 0..30 seconds")
    _require(type(rights) is str and bool(rights.strip()), "Retain a rights declaration or unknown")
    target = Path(output_dir)
    target.mkdir(parents=False, exist_ok=False)
    attempts = []
    manifest = {"schema_version": 1, "kind": "MARKET_SOURCE_ACQUISITION", "status": "FAILED",
                "request_url": url, "method": "GET", "source_id": source_id, "access": "public",
                "rights": rights, "max_bytes": max_bytes, "retries_limit": retries,
                "attempts": attempts, "execution_authorized": False,
                "limitations": list(LIMITATIONS)}
    opener = build_opener(_NoRedirect())
    for number in range(retries + 1):
        started = datetime.now(timezone.utc).isoformat()
        entry = {"attempt": number + 1, "started_at": started, "raw_complete": False}
        attempts.append(entry)
        response = None
        try:
            request = Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
            try:
                response = opener.open(request, timeout=timeout)
            except HTTPError as error:
                response = error
            entry["http_status"] = response.code if hasattr(response, "code") else response.status
            entry["final_url"] = response.geturl()
            entry["response_headers"] = {key: response.headers.get(key) for key in
                                          ("Content-Type", "Content-Length", "Content-Encoding", "ETag",
                                           "Last-Modified", "Date", "Retry-After") if response.headers.get(key) is not None}
            raw_path = target / ("attempt-" + str(number + 1).zfill(2) + ".raw")
            count, digest = 0, hashlib.sha256()
            entry.update(raw_file=raw_path.name, raw_sha256=digest.hexdigest(), retained_bytes=0)
            oversized = False
            with raw_path.open("xb") as output:
                while True:
                    chunk = response.read(min(65536, max_bytes - count + 1))
                    if not chunk:
                        break
                    remaining = max_bytes - count
                    retained = chunk[:remaining]
                    output.write(retained); digest.update(retained); count += len(retained)
                    entry.update(raw_file=raw_path.name, raw_sha256=digest.hexdigest(), retained_bytes=count)
                    if len(chunk) > remaining:
                        oversized = True
                        break
                output.flush()
                os.fsync(output.fileno())
            entry.update(raw_file=raw_path.name, raw_sha256=digest.hexdigest(), retained_bytes=count)
            _require(not oversized, "BODY_LIMIT_EXCEEDED_PARTIAL_PREFIX_RETAINED")
            declared_length = entry["response_headers"].get("Content-Length")
            if declared_length is not None:
                _require(str(declared_length).isdigit() and int(declared_length) == count,
                         "CONTENT_LENGTH_MISMATCH_PARTIAL_RETAINED")
            entry["raw_complete"] = True
            _require(entry["final_url"] == url, "UNEXPECTED_REDIRECT")
            _require(entry["http_status"] == 200, "HTTP_" + str(entry["http_status"]))
            _require(not entry["response_headers"].get("Content-Encoding", "").strip()
                     or entry["response_headers"]["Content-Encoding"].lower() == "identity",
                     "Encoded response retained; explicit decoding required")
            finished = datetime.now(timezone.utc).isoformat()
            entry["finished_at"] = finished
            manifest.update(status="ACQUIRED", raw_file=raw_path.name, raw_sha256=digest.hexdigest(),
                            source={"id": source_id, "url": url, "retrieved_at": finished,
                                    "published_at": None, "observed_at": finished,
                                    "availability_basis": "first_observed_snapshot", "access": "public", "rights": rights,
                                    "response_headers": entry["response_headers"]},
                            available_at=finished)
            break
        except (OSError, ValueError, URLError, TimeoutError, HTTPException) as error:
            entry["error"] = type(error).__name__ + ": " + str(error)
            entry["finished_at"] = datetime.now(timezone.utc).isoformat()
            status = entry.get("http_status")
            # Denials/404/rate limits are concrete gaps, never a browser bypass or
            # an excuse to keep polling. Only transient failures get one bounded retry.
            if status not in (None, 408, 500, 502, 503, 504) or "BODY_LIMIT" in str(error):
                break
            if number < retries:
                time.sleep(1.0)
        finally:
            if response is not None:
                response.close()
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(target / "manifest.json", manifest)
    return manifest


def raw_text(path, member=None):
    """CLI-only bounded read/ZIP member decode; never extracts archive paths."""
    path = Path(path)
    _require(path.stat().st_size <= MAX_BYTES, "Raw file exceeds byte limit")
    raw = path.read_bytes()
    if zipfile.is_zipfile(io.BytesIO(raw)):
        _require(type(member) is str and member and ".." not in Path(member).parts
                 and not Path(member).is_absolute(), "Select one explicit safe ZIP member")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            matches = [item for item in archive.infolist() if item.filename == member]
            _require(len(matches) == 1 and not matches[0].is_dir() and matches[0].file_size <= MAX_BYTES,
                     "ZIP member missing, duplicate or too large")
            with archive.open(matches[0]) as stream:
                content = stream.read(MAX_BYTES + 1)
                _require(len(content) <= MAX_BYTES, "Expanded member too large")
    else:
        _require(member is None, "ZIP member given for a non-ZIP file")
        content = raw
    return content.decode("utf-8-sig"), hashlib.sha256(raw).hexdigest(), hashlib.sha256(content).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("normalize", "parse"):
        item = sub.add_parser(command)
        item.add_argument("--input", required=True)
        item.add_argument("--output", required=True)
        if command == "parse":
            item.add_argument("--raw-file")
            item.add_argument("--zip-member")
    item = sub.add_parser("acquire")
    item.add_argument("--url", required=True)
    item.add_argument("--output-dir", required=True)
    item.add_argument("--source-id", required=True)
    item.add_argument("--user-agent", required=True)
    item.add_argument("--rights", default="unknown")
    item.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    item.add_argument("--timeout", type=float, default=15)
    item.add_argument("--retries", type=int, default=1)
    args = parser.parse_args()
    if args.command == "acquire":
        result = acquire(args.url, args.output_dir, args.source_id, args.user_agent, args.rights,
                         args.max_bytes, args.timeout, args.retries)
        print(json.dumps({"status": result["status"], "manifest": str(Path(args.output_dir) / "manifest.json")}))
        return 0 if result["status"] == "ACQUIRED" else 1
    path = Path(args.input)
    _require(path.stat().st_size <= MAX_BYTES, "Input document too large")
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    if args.command == "parse" and args.raw_file:
        text, raw_sha, content_sha = raw_text(args.raw_file, args.zip_member)
        document["text"] = text
        document.setdefault("source", {})["raw_sha256"] = raw_sha
        document["source"]["decoded_content_sha256"] = content_sha
        if document.get("adapter") in ("sec_submissions", "social_leads"):
            document["data"] = json.loads(text)
    result = parse(document) if args.command == "parse" else normalize(document)
    _write_json(Path(args.output), result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
