"""Source-bound analytical tax-lot comparisons; no legal or execution authority."""
from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from accounting_tools import _select_validated_lots, _wash_sale_calendar_review

CONVENTION = "illustrative_calendar_anniversary_more_than_one_year"
DEPENDENCIES = ("tax_lot_report.py", "accounting_tools.py", "risk_engine.py", "execution_policy.py", "execution_handoff.py")
FILES = {"input.json", "original-request.txt", "original-source.json", "first-response.md", "response.json", "summary.txt"}
MAX_BYTES = 2_000_000


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def number(value, positive=False):
    require(not isinstance(value, bool) and isinstance(value, (str, int, Decimal)), "Expected exact decimal")
    try:
        result = Decimal(value)
    except Exception as exc:
        raise ValueError("Invalid decimal") from exc
    require(result.is_finite(), "Non-finite number")
    require(len(result.as_tuple().digits) <= 100 and abs(result.as_tuple().exponent) <= 100, "Numeric magnitude exceeds supported bound")
    require(result > 0 if positive else result >= 0, "Invalid quantity or price")
    return result


def pairs_unique(items):
    result = {}
    for key, value in items:
        require(key not in result, "Duplicate JSON object key")
        result[key] = value
    return result


def parse_json(raw):
    require(len(raw) <= MAX_BYTES, "Source/input too large")
    def reject_constant(value):
        raise ValueError("Non-finite JSON constant: " + value)
    return json.loads(raw.decode("utf-8-sig"), parse_float=Decimal, parse_int=Decimal,
                      object_pairs_hook=pairs_unique, parse_constant=reject_constant)


def label(value, field):
    require(isinstance(value, str) and value.strip() and len(value) <= 500, "Invalid " + field)
    require(not any(ord(c) < 32 for c in value), "Control character in " + field)
    return value


def day(value, timezone):
    require(isinstance(value, str), "Date must be a source string")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    require("T" in value, "Unsupported date shape")
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(at.tzinfo is not None, "Timestamp requires offset")
    require(isinstance(timezone, str) and timezone, "Timestamp calendar timezone required")
    return at.astimezone(ZoneInfo(timezone)).date()


def term(acquired, sold, policy):
    elapsed = (sold - acquired).days
    if policy["convention"] is None:
        return {"category": "unresolved", "elapsed_days": elapsed, "anniversary": None,
                "reason": policy["reason"]}
    try:
        anniversary = acquired.replace(year=acquired.year + 1)
    except ValueError:
        rule = policy["leap_day_policy"]
        if rule == "unresolved":
            return {"category": "unresolved", "elapsed_days": elapsed, "anniversary": None,
                    "reason": "Leap-day anniversary policy not established"}
        anniversary = date(acquired.year + 1, 2, 28) if rule == "february_28" else date(acquired.year + 1, 3, 1)
    return {"category": "long_under_assumption" if sold > anniversary else "short_under_assumption",
            "elapsed_days": elapsed, "anniversary": anniversary.isoformat(), "reason": None}


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def source_binding(sha, pointer):
    return {"source_sha256": sha, "pointer": pointer}


def _build(document):
    require(isinstance(document, dict) and set(document) == {"schema_version", "request", "source", "holding_period", "calendar", "common_unit_assumption", "alternatives"}, "Exact report input fields required")
    require(document["schema_version"] == 1 and not isinstance(document["schema_version"], bool), "Unsupported schema")
    request, source = document["request"], document["source"]
    require(isinstance(request, dict) and set(request) == {"text", "sha256"}, "Request binding required")
    require(isinstance(source, dict) and set(source) == {"id", "text", "sha256", "adapter"}, "Source binding required")
    for obj in [request, source]:
        require(isinstance(obj["text"], str) and obj["text"].strip(), "Original source/request required")
        require(len(obj["text"].encode("utf-8")) <= MAX_BYTES and digest(obj["text"].encode("utf-8")) == obj["sha256"], "Original byte hash mismatch")
    label(source["id"], "source id")
    require(source["adapter"] == "accounting_snapshot_v1", "Unsupported source adapter")
    raw = parse_json(source["text"].encode("utf-8")); require(isinstance(raw, dict), "Source object required")
    policy = document["holding_period"]
    require(isinstance(policy, dict), "Holding-period policy required")
    if policy.get("convention") is None:
        require(set(policy) == {"convention", "reason"}, "Unresolved convention requires reason")
        label(policy["reason"], "convention reason")
    else:
        require(set(policy) == {"convention", "assumption_label", "leap_day_policy"} and policy["convention"] == CONVENTION, "Unsupported analytical holding convention")
        label(policy["assumption_label"], "assumption label")
        require(policy["leap_day_policy"] in {"unresolved", "february_28", "march_1"}, "Leap-day policy required")
    calendar = document["calendar"]
    require(isinstance(calendar, dict) and set(calendar) == {"timestamp_timezone"}, "Calendar required")
    tz = calendar["timestamp_timezone"]
    require(tz is None or isinstance(tz, str), "Invalid timestamp timezone")
    if tz is not None:
        ZoneInfo(tz)
    alternatives = document["alternatives"]
    require(isinstance(alternatives, list) and alternatives and all(isinstance(x, str) for x in alternatives), "Alternatives required")
    require(len(set(alternatives)) == len(alternatives) and set(alternatives) <= {"FIFO", "HIFO"}, "Supported distinct alternatives required")
    sale = raw.get("sale"); lots_raw = raw.get("tax_lots")
    require(isinstance(sale, dict) and isinstance(lots_raw, list) and 0 < len(lots_raw) <= 10000, "Sale and complete lot collection required")
    symbol = label(sale.get("symbol"), "sale symbol"); qty = number(sale.get("quantity"), True)
    price = number(sale.get("price")); sold = day(sale.get("date"), tz)
    sha = source["sha256"]; lots = []; inventory = []; seen = set()
    for i, value in enumerate(lots_raw):
        require(isinstance(value, dict), "Lot object required")
        ident = label(value.get("id"), "lot id"); require(ident not in seen, "Duplicate lot id"); seen.add(ident)
        security = label(value.get("symbol"), "lot symbol"); held = number(value.get("quantity"), True)
        cost = number(value.get("unit_basis")); acquired = day(value.get("acquired"), tz)
        binding = source_binding(sha, "/tax_lots/" + str(i))
        item = {"id": ident, "symbol": security, "original_quantity": str(held), "unit_basis": str(cost),
                "acquired_source": value["acquired"], "acquired_calendar_date": acquired.isoformat(),
                "binding": binding, "scope": "eligible" if security == symbol else "not_target_security"}
        inventory.append(item)
        if security == symbol:
            require(acquired <= sold, "Existing lot acquisition follows sale")
            lots.append({"item": item, "record": value, "held": held, "cost": cost, "date": acquired})
    require(lots and sum((x["held"] for x in lots), Decimal(0)) >= qty, "Insufficient eligible shares")
    shared = raw.get("monetary_scope"); shared_currency = None
    if shared is not None:
        require(isinstance(shared, dict) and set(shared) == {"currency", "applies_to"} and isinstance(shared["applies_to"], list) and len(shared["applies_to"]) == 2 and set(shared["applies_to"]) == {"sale", "tax_lots"}, "Unsupported shared monetary scope")
        shared_currency = shared["currency"]
    currencies = []; missing = []; currency_bindings = []
    for pointer, record in [("/sale", sale)] + [(x["item"]["binding"]["pointer"], x["record"]) for x in lots]:
        local = record.get("currency")
        if local is not None:
            require(isinstance(local, str) and re.fullmatch(r"[A-Z]{3}", local), "Invalid source currency")
            currencies.append(local); currency_bindings.append({**source_binding(sha, pointer + "/currency"), "currency": local})
        elif shared_currency is None:
            missing.append(pointer)
        if shared_currency is not None:
            require(isinstance(shared_currency, str) and re.fullmatch(r"[A-Z]{3}", shared_currency), "Invalid shared currency")
            currencies.append(shared_currency)
    require(len(set(currencies)) <= 1, "Conflicting source currencies; conversion not established")
    assumption = document["common_unit_assumption"]
    if assumption is not None:
        label(assumption, "common-unit assumption")
    require(not missing or assumption is not None, "Unspecified monetary units require explicit common-unit analytical assumption")
    if shared_currency is not None:
        currency_bindings.append({**source_binding(sha, "/monetary_scope"), "currency": shared_currency})
    currency = {"status": "UNSPECIFIED_IN_SOME_SALE_OR_LOT_FIELDS" if missing else "SOURCE_SCOPED", "currency": None if missing else currencies[0],
                "missing_source_fields": missing, "assumption": assumption, "bindings": currency_bindings,
                "cash_ledger_used": False, "sale_fees": "NOT_ESTABLISHED_GROSS_BEFORE_FEES"}
    by_id = {x["item"]["id"]: x for x in lots}
    prepared = [(dict(lot_ref=x["item"]["id"], symbol=symbol), x["held"], x["cost"], x["date"]) for x in lots]
    selections = []
    if "specific_lots" in sale:
        specific = sale["specific_lots"]
        require(isinstance(specific, list) and specific, "Nonempty supplied specific selection required")
        selected = []; ids = set()
        for i, pick in enumerate(specific):
            require(isinstance(pick, dict) and set(pick) == {"id", "quantity"}, "Explicit specific quantities required")
            ident = label(pick["id"], "specific lot id"); require(ident in by_id and ident not in ids, "Invalid/duplicate specific lot"); ids.add(ident)
            take = number(pick["quantity"], True); require(take <= by_id[ident]["held"], "Specific over-selection")
            selected.append({"lot_ref": ident, "quantity": str(take)})
        require(sum((Decimal(x["quantity"]) for x in selected), Decimal(0)) == qty, "Specific quantities differ from sale")
        selections.append(("SPECIFIC_SOURCE", selected))
    for method in alternatives:
        selected = _select_validated_lots(list(prepared), qty, method)["lots"]
        selections.append((method, selected))
    purchases = [{"local_ref": "lot:" + x["item"]["id"], "symbol": symbol, "side": "buy", "calendar_day": x["date"],
                  "quantity": str(x["held"]), "linked_lot": x["item"]["id"], "scope": "known_lot_acquisition",
                  "binding": x["item"]["binding"]} for x in lots]
    coverage = {}; external_inventory = []; unresolved = []
    for key in ["outside_account_transactions", "future_purchases"]:
        records = raw.get(key)
        if records is None:
            coverage[key] = "UNKNOWN_NULL" if key in raw else "UNKNOWN_ABSENT"
            unresolved.append(key + " is unknown")
            continue
        if not isinstance(records, list):
            coverage[key] = "UNSUPPORTED_MAPPING"; unresolved.append(key + " is not a supported collection"); continue
        require(len(records) <= 10000, "Transaction collection too large")
        coverage[key] = "EMPTY_SUPPLIED_SCOPE" if not records else "SUPPLIED_SCOPE_ONLY"
        ids = set()
        for i, rec in enumerate(records):
            binding = source_binding(sha, "/" + key + "/" + str(i))
            if not isinstance(rec, dict) or not {"id", "symbol", "side", "date", "quantity"} <= set(rec) or set(rec) - {"id", "symbol", "side", "date", "quantity", "lot_ref"}:
                external_inventory.append({"binding": binding, "status": "UNSUPPORTED_MAPPING"}); unresolved.append(key + " has an unsupported record"); continue
            ident = label(rec["id"], "transaction id"); require(ident not in ids, "Duplicate transaction id"); ids.add(ident)
            security = label(rec["symbol"], "transaction symbol"); require(rec["side"] in {"buy", "sell"}, "Unsupported transaction side")
            amount = number(rec["quantity"], True); when = day(rec["date"], tz); linked = rec.get("lot_ref")
            if linked is not None:
                require(isinstance(linked, str) and linked in by_id and security == symbol and when == by_id[linked]["date"] and amount == by_id[linked]["held"] and rec["side"] == "buy", "Conflicting acquisition-to-lot link")
            item = {"id": ident, "symbol": security, "side": rec["side"], "date": when.isoformat(), "quantity": str(amount),
                    "scope": key, "linked_lot": linked, "binding": binding,
                    "status": "REPEATED_LINKED_ACQUISITION" if linked else "OBSERVATION_NOT_EXECUTION"}
            external_inventory.append(item)
            if not linked:
                purchases.append({"local_ref": key + ":" + ident, "symbol": security, "side": rec["side"], "calendar_day": when,
                                  "quantity": str(amount), "linked_lot": None, "scope": key, "binding": binding})
    proposals = []
    for method, chosen in selections:
        takes = {x["lot_ref"]: Decimal(x["quantity"]) for x in chosen}
        components = []; remaining = []; totals = {k: Decimal(0) for k in ["long_under_assumption", "short_under_assumption", "unresolved"]}
        basis = Decimal(0); proceeds = Decimal(0)
        for lot in lots:
            ident = lot["item"]["id"]; take = takes.get(ident, Decimal(0)); rest = lot["held"] - take
            require(rest >= 0 and take + rest == lot["held"], "Per-lot conservation failure")
            remaining.append({"lot_id": ident, "original_quantity": str(lot["held"]), "selected_quantity": str(take), "remaining_quantity": str(rest), "acquired_calendar_date": lot["date"].isoformat(), "binding": lot["item"]["binding"]})
            if take:
                holding = term(lot["date"], sold, policy); cost = take * lot["cost"]; money = take * price; gain = money - cost
                components.append({"lot_id": ident, "quantity": str(take), "basis": str(cost), "proceeds": str(money), "signed_gain": str(gain), "holding_period": holding, "binding": lot["item"]["binding"]})
                basis += cost; proceeds += money; totals[holding["category"]] += gain
        require(sum(takes.values(), Decimal(0)) == qty and sum((Decimal(x["remaining_quantity"]) for x in remaining), Decimal(0)) == sum((x["held"] for x in lots), Decimal(0)) - qty, "Proposal conservation failure")
        loss = [x for x in components if Decimal(x["signed_gain"]) < 0]
        screen = _wash_sale_calendar_review(symbol, sold, bool(loss), purchases)
        flags = []; purchase_map = {x["local_ref"]: x for x in purchases}
        for flag in screen["potential_replacements"]:
            obs = purchase_map[flag["local_ref"]]; linked = obs["linked_lot"]
            if linked:
                original = by_id[linked]["held"]; selected = takes.get(linked, Decimal(0)); retained = original - selected
                state = "fully_sold_in_this_proposal" if retained == 0 else "partly_retained_in_this_proposal" if selected else "retained_unselected"
                detail = {"linked_lot": linked, "original_quantity": str(original), "selected_quantity": str(selected), "remaining_quantity": str(retained)}
            else:
                state = "linkage_unknown"; detail = {"linked_lot": None, "original_quantity": None, "selected_quantity": None, "remaining_quantity": None}
            flags.append({**flag, **detail, "disposition": state, "scope": obs["scope"], "binding": obs["binding"], "tax_disallowance_established": False})
        proposals.append({"method": method, "components": components, "lot_inventory": remaining, "basis": str(basis), "gross_proceeds": str(proceeds), "signed_gain": str(proceeds - basis), "term_signed_totals": {k: str(v) for k, v in totals.items()}, "loss_components": [x["lot_id"] for x in loss], "purchase_date_flags": flags, "external_coverage_complete": False, "future_monitor_needed": bool(loss), "tax_clearance": False, "execution_authorized": False})
    term_unresolved = any(c["holding_period"]["category"] == "unresolved" for p in proposals for c in p["components"])
    return {"schema_version": 1, "operation": "tax_lot_comparison_report", "status": "PARTIAL" if term_unresolved or unresolved else "COMPLETE_FOR_SUPPORTED_ANALYTICAL_SCOPE", "request_sha256": request["sha256"], "source": {"id": source["id"], "sha256": sha, "adapter": source["adapter"]}, "sale": {"symbol": symbol, "quantity": str(qty), "price": str(price), "source_date": sale["date"], "calendar_date": sold.isoformat(), "binding": source_binding(sha, "/sale")}, "purchase_review_window": {"start": (sold - timedelta(days=30)).isoformat(), "end": (sold + timedelta(days=30)).isoformat(), "basis": "conventional30calendar_day_review_flag_not_legal_disallowance"}, "source_lot_inventory": inventory, "holding_period_convention": policy, "calendar": calendar, "currency_scope": currency, "external_evidence": {"coverage": coverage, "records": external_inventory, "unresolved": unresolved}, "proposals": proposals, "execution_authorized": False, "semantic_request_completeness_verified": False, "limitations": ["Analytical convention only; jurisdiction, account rules and actual tax treatment are not established.", "Purchase-date flags and proposed remaining inventory do not determine replacement matching, disallowance, basis adjustment or deductibility.", "Known fully sold lots are not known retained shares; external/future facts remain separately scoped and incomplete.", "FIFO compares earliest acquisition calendar dates (same-day ties by lot identifier) and HIFO highest unit basis then calendar date and identifier; lower gross gain alone does not establish a preferable after-tax sale.", "Gross amounts before unprovided sale fees/adjustments; no tax rate, FX, after-tax benefit or forced selection.", "Generated projections only; no verification of additional host prose, source authenticity, all user intent or broker acceptance."]}


def build_report(document):
    with localcontext() as context:
        context.prec = 1024
        context.Emax = 9999
        context.Emin = -9999
        return _build(document)


def escaped(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("`", "\\`")


def render_markdown(report):
    policy = report["holding_period_convention"]; currency = report["currency_scope"]
    convention = policy.get("assumption_label", policy.get("reason"))
    lines = ["# Tax-lot comparison", "", "Status: " + report["status"], "", "Sale: " + escaped(report["sale"]["symbol"]) + "; quantity " + report["sale"]["quantity"] + "; calendar date " + report["sale"]["calendar_date"] + ".", "", "Holding-period convention: " + escaped(policy["convention"] or "unresolved") + ". " + escaped(convention) + ". This is an analytical assumption, not legal tax status.", "", "Monetary units: " + (currency["currency"] or "unspecified in sale/lot source fields") + ". Common-unit assumption: " + escaped(currency["assumption"] or "none needed") + ". Gross amounts before unprovided fees and adjustments."]
    lines += ["Calendar: " + escaped(json.dumps(report["calendar"])) + ". Leap-day policy: " + escaped(policy.get("leap_day_policy", "unresolved")) + "."]
    for proposal in report["proposals"]:
        lines += ["", "## " + proposal["method"], "", "| Lot | Quantity | Basis | Proceeds | Signed gain | Holding category |", "|---|---:|---:|---:|---:|---|"]
        for item in proposal["components"]:
            holding = item["holding_period"]
            lines.append("| " + " | ".join(escaped(v) for v in [item["lot_id"], item["quantity"], item["basis"], item["proceeds"], item["signed_gain"], holding["category"] + (": " + holding["reason"] if holding["reason"] else "")]) + " |")
        lines += ["", "Gross proceeds " + proposal["gross_proceeds"] + "; basis " + proposal["basis"] + "; signed gain " + proposal["signed_gain"] + ".", "Term components: " + "; ".join(k + " " + v for k, v in proposal["term_signed_totals"].items()) + ".", "Negative-gain lots: " + (", ".join(escaped(v) for v in proposal["loss_components"]) or "none") + ". A net gain does not remove an individual loss component.", "", "Remaining lot inventory:"]
        for item in proposal["lot_inventory"]:
            lines.append("- " + escaped(item["lot_id"]) + ": original " + item["original_quantity"] + ", selected " + item["selected_quantity"] + ", remaining " + item["remaining_quantity"] + "; acquired " + item["acquired_calendar_date"] + ".")
        lines += ["", "Conventional purchase-date screen: " + report["purchase_review_window"]["start"] + " through " + report["purchase_review_window"]["end"] + "; 30 calendar days before/after the sale; flags only."]
        if not proposal["purchase_date_flags"]:
            lines.append("No matching purchase flag in the supplied screen. This is not tax clearance.")
        for flag in proposal["purchase_date_flags"]:
            text = "- " + escaped(flag["local_ref"]) + ": " + str(flag["days_from_sale"]) + " days from sale; purchase quantity " + flag["quantity"] + "; " + flag["disposition"]
            if flag["linked_lot"]:
                text += "; selected " + flag["selected_quantity"] + ", remaining " + flag["remaining_quantity"]
            lines.append(text + ". This proposal disposition does not determine tax disallowance or retained replacement matching.")
        lines.append("External account completeness: not established. Future monitoring needed for a loss component: " + str(proposal["future_monitor_needed"]).lower() + ". No execution or tax clearance.")
    lines += ["", "## Evidence scope"]
    lines += ["- " + key + ": " + value + "." for key, value in report["external_evidence"]["coverage"].items()]
    lines += ["- " + escaped(reason) for reason in report["external_evidence"]["unresolved"]]
    lines += ["", "## Limits"] + ["- " + text for text in report["limitations"]]
    return "\n".join(lines) + "\n"


def render_summary(report):
    # A compact deterministic projection retaining the required semantic fields.
    lines = ["Tax-lot comparison: " + report["status"], "Convention: " + json.dumps(report["holding_period_convention"], ensure_ascii=False), "Units: " + json.dumps(report["currency_scope"], ensure_ascii=False)]
    for proposal in report["proposals"]:
        lines.append(proposal["method"] + ": gain " + proposal["signed_gain"] + "; term components " + json.dumps(proposal["term_signed_totals"]) + "; selected " + json.dumps([{k: x[k] for k in ["lot_id", "quantity", "signed_gain", "holding_period"]} for x in proposal["components"]]) + "; remaining " + json.dumps(proposal["lot_inventory"]) + "; flags " + json.dumps(proposal["purchase_date_flags"]))
    lines += ["Review window: " + json.dumps(report["purchase_review_window"])] + report["limitations"] + report["external_evidence"]["unresolved"]
    return "\n".join(lines) + "\n"


def safe_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        require(not item.is_symlink() and not (item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 1024), "Reparse path rejected")
    require(path.resolve() == path, "Noncanonical path")
    return path


def module_hashes():
    root = Path(__file__).resolve().parent
    return {name: digest(safe_path(root / name).read_bytes()) for name in DEPENDENCIES}


def projections(input_bytes):
    document = parse_json(input_bytes); report = build_report(document)
    return {"input.json": input_bytes, "original-request.txt": document["request"]["text"].encode("utf-8"), "original-source.json": document["source"]["text"].encode("utf-8"), "first-response.md": render_markdown(report).encode("utf-8"), "response.json": json_bytes(report), "summary.txt": render_summary(report).encode("utf-8")}, report


def compose(input_path, output):
    source = safe_path(input_path); output = safe_path(output)
    require(not output.exists() and not source.is_relative_to(output), "New disjoint output directory required")
    original = source.read_bytes(); files, report = projections(original); dependencies = module_hashes()
    output.mkdir(parents=True)
    for name, raw in files.items():
        with (output / name).open("xb") as stream:
            stream.write(raw)
    require(source.read_bytes() == original and module_hashes() == dependencies, "Input/dependency changed")
    receipt = {"status": "SOURCE_BOUND_TAX_LOT_REPORT_GENERATED", "schema_version": 1, "report_status": report["status"], "request_sha256": report["request_sha256"], "source_sha256": report["source"]["sha256"], "files": {name: digest(raw) for name, raw in files.items()}, "dependencies": dependencies, "execution_authorized": False, "semantic_request_completeness_verified": False}
    with (output / "receipt.json").open("xb") as stream:
        stream.write(json_bytes(receipt))
    verify(output)
    return receipt


def verify(output, expected_receipt=None):
    output = safe_path(output)
    entries = list(output.iterdir())
    require(all(safe_path(p).is_file() for p in entries) and {p.name for p in entries} == FILES | {"receipt.json"}, "Exact artifact inventory required")
    receipt_bytes = (output / "receipt.json").read_bytes()
    if expected_receipt is not None:
        require(digest(receipt_bytes) == expected_receipt, "External receipt pin mismatch")
    receipt = parse_json(receipt_bytes)
    require(isinstance(receipt, dict) and set(receipt) == {"status", "schema_version", "report_status", "request_sha256", "source_sha256", "files", "dependencies", "execution_authorized", "semantic_request_completeness_verified"}, "Exact receipt fields required")
    require(receipt["schema_version"] == 1 and not isinstance(receipt["schema_version"], bool) and receipt["execution_authorized"] is False and receipt["semantic_request_completeness_verified"] is False, "Invalid receipt authority fields")
    require(receipt.get("status") == "SOURCE_BOUND_TAX_LOT_REPORT_GENERATED" and set(receipt.get("files", {})) == FILES, "Receipt schema")
    require(receipt.get("dependencies") == module_hashes(), "Report dependency changed")
    files, report = projections((output / "input.json").read_bytes())
    for name, raw in files.items():
        require((output / name).read_bytes() == raw and digest(raw) == receipt["files"][name], "Generated projection/source changed: " + name)
    require(receipt.get("request_sha256") == report["request_sha256"] and receipt.get("source_sha256") == report["source"]["sha256"] and receipt.get("report_status") == report["status"], "Receipt identity mismatch")
    return {"status": "SOURCE_BOUND_TAX_LOT_REPORT_REPLAYED", "receipt_sha256": digest(receipt_bytes), "files_verified": len(FILES), "report_status": report["status"], "execution_authorized": False, "semantic_request_completeness_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("compose"); make.add_argument("input", type=Path); make.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("verify"); check.add_argument("output", type=Path); check.add_argument("--receipt-sha256")
    args = parser.parse_args()
    value = compose(args.input, args.output) if args.command == "compose" else verify(args.output, args.receipt_sha256)
    print(json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
