"""Create/verify self-contained JSON inputs and deterministic screen outputs.

Replays declarations, not research or source authenticity. No network, arbitrary
code execution, linked-file reads, broker data access or execution authority.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from screen_review import review_screen

ROOT = Path(__file__).resolve().parents[1]


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def implementation():
    dependencies = {}
    for name in ("numpy", "pandas", "exchange_calendars", "tzdata"):
        try:
            dependencies[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            dependencies[name] = "NOT_INSTALLED"
    # Normalize line endings so Windows/Linux exports identify the same source.
    files = {p.relative_to(ROOT).as_posix(): hashlib.sha256(
        p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        for p in sorted((ROOT / "scripts").glob("*.py"))}
    return {"skill_version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
            "source_sha256": files, "dependencies": dependencies}


def create_bundle(document):
    result = review_screen(document)
    return {"schema_version": 1, "input_document": document,
            "input_sha256": canonical_hash(document), "result": result,
            "result_sha256": canonical_hash(result), "implementation": implementation(),
            "execution_authorized": False,
            "limitations": "Reproducible classification/arithmetic from supplied declarations. External evidence references are not downloaded or authenticated; hashes are not signatures."}


def verify_bundle(bundle):
    if not isinstance(bundle, dict) or bundle.get("schema_version") != 1:
        raise ValueError("Unsupported research bundle schema")
    if bundle.get("execution_authorized") is not False:
        raise ValueError("Research bundle cannot grant execution authority")
    document, result = bundle["input_document"], bundle["result"]
    if canonical_hash(document) != bundle.get("input_sha256"):
        raise ValueError("Bundle input hash mismatch")
    if canonical_hash(result) != bundle.get("result_sha256"):
        raise ValueError("Bundle result hash mismatch")
    if bundle.get("implementation") != implementation():
        raise ValueError("Bundle code/version/dependencies differ from this installation; replay with the recorded environment")
    replay = review_screen(document)
    if canonical_hash(replay) != canonical_hash(result):
        raise ValueError("Bundle results do not reproduce from its candidate inputs")
    return {"status": "REPLAY_MATCH", "completion": replay["completion"],
            "input_sha256": bundle["input_sha256"], "execution_authorized": False,
            "limitations": bundle["limitations"]}


def compare_bundles(left, right):
    """Compare retained inputs; do not execute code embedded in either bundle."""
    for bundle in (left, right):
        if bundle.get("schema_version") != 1 or bundle.get("execution_authorized") is not False:
            raise ValueError("Comparison requires research bundles without execution authority")
        if (canonical_hash(bundle["input_document"]) != bundle["input_sha256"]
                or canonical_hash(bundle["result"]) != bundle["result_sha256"]):
            raise ValueError("Comparison bundle hash mismatch")
    a, b = left["input_document"], right["input_document"]
    fields = ("decision_mode", "research_as_of", "horizon", "universe", "run_spec",
              "ranking_spec", "ranking_inputs", "screening", "candidates", "report")
    differences = [field for field in fields if a.get(field) != b.get(field)]
    if left["implementation"] != right["implementation"]:
        differences.append("implementation")
    picks = [bundle["result"].get("ranking", {}).get("selected_symbols", []) for bundle in (left, right)]
    configured = all(bundle["result"].get("ranking", {}).get("status") == "COMPUTED" for bundle in (left, right))
    return {"differing_components": differences, "selected_symbols": picks,
            "same_picks": picks[0] == picks[1] if configured else None,
            "execution_authorized": False,
            "limitations": "Structural comparison only; run verify separately to establish replay, not investment merit"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("input", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument("--strict-final", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("bundle", type=Path)
    verify.add_argument("--strict-final", action="store_true")
    compare = commands.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    args = parser.parse_args()
    if args.command == "compare":
        print(json.dumps(compare_bundles(
            json.loads(args.left.read_text(encoding="utf-8-sig")),
            json.loads(args.right.read_text(encoding="utf-8-sig"))), indent=2, allow_nan=False))
        return
    if args.command == "create":
        document = json.loads(args.input.read_text(encoding="utf-8-sig"))
        bundle = create_bundle(document)
        # Do not overwrite input files, existing reports, or the installed skill.
        target = args.output.resolve()
        if target == ROOT or ROOT in target.parents:
            raise ValueError("Save research bundles outside the installed skill")
        with target.open("x", encoding="utf-8") as stream:
            json.dump(bundle, stream, indent=2, allow_nan=False)
            stream.write("\n")
        result = verify_bundle(bundle)
        strict = args.strict_final or bundle["result"]["report"]["stage"] == "final"
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8-sig"))
        result = verify_bundle(bundle)
        strict = args.strict_final or bundle["result"]["report"]["stage"] == "final"
    print(json.dumps(result, indent=2, allow_nan=False))
    if strict and result["completion"]["status"] != "COMPLETE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
