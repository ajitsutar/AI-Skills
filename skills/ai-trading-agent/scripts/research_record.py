"""Open one literal local JSON record named by the original research request."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote

import research_contracts as contracts


# Consume all words and spans, including unrelated inline code. Never search
# for a matching path inside a larger URI or stop a bare token midway through a key.
TOKENS = re.compile(r"(?:`([^`\r\n]*)`|<([^<>\r\n]*)>)(\S*)|(\S+)")
URI_MARKER = re.compile(r"\.json#", re.IGNORECASE)
DESIGN_FIELDS = {"design_kind", "design_terms", "proposed_decision_rules", "answer_controls"}
PROMPT = "__research_request__/original.txt"


def located(text, allowed):
    refs = []
    for match in TOKENS.finditer(text):
        code, angle, suffix, bare = match.groups()
        if not URI_MARKER.search(match.group()):
            continue
        if bare is None:
            literal = code if code is not None else angle
            contracts.require(all(ch in ".,;:!?)]\"'" for ch in suffix), "DELIMITED_REFERENCE_BOUNDARY_REQUIRED")
        else:
            literal = bare
        contracts.require(len(URI_MARKER.findall(literal)) == 1, "EXACTLY_ONE_REFERENCE_PER_TOKEN")
        contracts.require(not re.search(r"%(?![0-9a-fA-F]{2})", literal), "INVALID_URI_ESCAPE")
        path, fragment = literal.split("#", 1)
        path = contracts.relative_name(unquote(path, errors="strict"))
        contracts.require(path in allowed, "REQUEST_SOURCE_OUTSIDE_ALLOWLIST")
        contracts.require(fragment.startswith("/"), "NONROOT_RECORD_POINTER_REQUIRED")
        refs.append((path, fragment, bare is not None))
    contracts.require(refs, "EXPLICIT_LOCAL_JSON_REFERENCE_REQUIRED")
    contracts.require(len({(name, pointer) for name, pointer, _ in refs}) == 1, "MULTIPLE_REQUEST_REFERENCES")
    name, fragment, _ = refs[0]
    return name, fragment, all(bare for _, _, bare in refs)


def selected(raw_prompt, allowed, read_source):
    name, fragment, bare = located(raw_prompt.decode("utf-8-sig"), allowed)
    raw = read_source(name)
    value = contracts.binding_json.strict_json(raw)
    candidates = [fragment]
    while bare and candidates[-1][-1:] in (".", ",", ";", ":", "!", "?"):
        candidates.append(candidates[-1][:-1])
    resolved = []
    for candidate in candidates:
        pointer = unquote(candidate, errors="strict")
        try:
            record = contracts.pointer(value, pointer)
        except (KeyError, IndexError, ValueError):
            continue
        resolved.append((pointer, record))
    contracts.require(len(resolved) == 1, "MISSING_OR_AMBIGUOUS_RECORD_USE_DELIMITED_REFERENCE")
    pointer, record = resolved[0]
    return {"source_path": name, "pointer": pointer, "record": record,
            "source_sha256": hashlib.sha256(raw).hexdigest(), "request_sha256": hashlib.sha256(raw_prompt).hexdigest()}


def bound_design(document, source_root):
    contracts.require("strategy_source" not in document and document["original_request"] == PROMPT,
                      "ORIGINAL_REQUEST_OWNS_RECORD_SELECTION")
    inventory, values = contracts.inventory_sources(document, source_root)
    by_id = {row["id"]:row for row in inventory}
    contracts.require(set(by_id) == {"request", "record"} and set(values) == set(by_id) and
                      by_id["request"]["path"] == PROMPT, "ORIGINAL_REQUEST_SOURCE_BINDING")
    name = by_id["record"]["path"]
    contracts.require(len(document["allowlist"]) == 2 and set(document["allowlist"]) == {name, PROMPT},
                      "EXTRA_ORIGINAL_REQUEST_SOURCE")
    raw_prompt = contracts.source_path(source_root, PROMPT).read_bytes()
    chosen = selected(raw_prompt, {name}, lambda n: contracts.source_path(source_root, n).read_bytes())
    contracts.require(chosen["request_sha256"] == by_id["request"]["actual_sha256"] and
                      chosen["source_sha256"] == by_id["record"]["actual_sha256"], "ORIGINAL_REQUEST_SOURCE_CHANGED")
    return {"source_id":"record", "pointer":chosen["pointer"]}, {k:v for k,v in chosen.items() if k != "record"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Original user request text file")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source", action="append", required=True, help="Allowed source path relative to the source root")
    designs = parser.add_mutually_exclusive_group()
    designs.add_argument("--scoped-design", help="Executable design with selected-record clocks and generated strategy limitations")
    designs.add_argument("--executable-design", help="Require typed signal, exposure, return, costs and trade activity conventions")
    designs.add_argument("--registered-design", help="Require a typed comparator, calendar and single estimator")
    designs.add_argument("--design", help="Existing design choices, including legacy open prose")
    parser.add_argument("--response-contract", help="Original separate response field declaration for this request")
    parser.add_argument("--private-output", help="Fresh strategy-answer export directory")
    args = parser.parse_args()
    try:
        design = args.scoped_design or args.executable_design or args.registered_design or args.design
        contracts.require(bool(design) == bool(args.private_output), "DESIGN_AND_OUTPUT_REQUIRED_TOGETHER")
        raw_prompt = contracts.binding_json.local_path(args.request).read_bytes()
        allowed = {contracts.relative_name(n) for n in args.source}
        contracts.require(len({n.casefold() for n in allowed}) == len(allowed), "AMBIGUOUS_ALLOWLIST")
        name, _, _ = located(raw_prompt.decode("utf-8-sig"), allowed)
        raw = contracts.source_path(args.source_root, name).read_bytes()
        chosen = selected(raw_prompt, allowed, lambda _:raw)
        if design:
            options = contracts.parse_document(contracts.binding_json.local_path(design).read_bytes())
            from strategy_intake import original_contract
            declaration = original_contract(raw_prompt, args.source_root, args.response_contract)
            economic = isinstance(options.get('strategy_registration'), dict) and isinstance(
                options['strategy_registration'].get('economics'), dict)
            scoped = bool(args.scoped_design or (declaration is not None and economic))
            clock_fields = options.pop('clock_fields', {}) if scoped else {}
            if args.scoped_design or args.executable_design:
                contracts.require(isinstance(options.get("strategy_registration"), dict) and
                                  isinstance(options["strategy_registration"].get("economics"), dict),
                                  "EXECUTABLE_ECONOMIC_DESIGN_REQUIRED")
            if args.registered_design or args.executable_design or args.scoped_design:
                contracts.require("strategy_registration" in options, "TYPED_STRATEGY_REGISTRATION_REQUIRED")
            contracts.require(set(options) in (DESIGN_FIELDS, DESIGN_FIELDS | {"strategy_registration"}), "DESIGN_CHOICES_ONLY")
            document = dict(options, original_request=PROMPT, allowlist=[PROMPT, name], sources=[
                {"id":"request","path":PROMPT,"role":"original_user_request","format":"text","sha256":chosen["request_sha256"]},
                {"id":"record","path":name,"role":"supplied_document","format":"json","sha256":chosen["source_sha256"]}])
            if scoped:
                document['clock_fields'] = clock_fields
            with tempfile.TemporaryDirectory() as temp:
                snapshot = Path(temp).resolve()
                contracts.write_files(snapshot, {PROMPT:raw_prompt, name:raw})
                report = contracts.export_run("strategy-answer", json.dumps(document).encode(), snapshot, args.private_output, original_contract=declaration)
            receipt = contracts.parse_document((Path(args.private_output) / "receipt.json").read_bytes())
            print(json.dumps({"operation":"strategy-answer", "output":args.private_output, "pointer":chosen["pointer"],
                              "registration_scope": receipt["registration_scope"],
                              "delivery_scope": "current_registered_strategy" if declaration is not None and
                              contracts.current_strategy_design(report["result"]) else "scoped_incomplete"}))
        else:
            contracts.require(args.response_contract is None, 'DELIVERY_DECLARATION_REQUIRES_A_DESIGN')
            try:
                print(json.dumps(chosen, ensure_ascii=True, indent=2))
            except TypeError:
                print(contracts.binding_json.encode(chosen))
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        parser.exit(2, "Request record unavailable: " + str(exc) + "\n")
