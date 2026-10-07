"""Portable local runtime for a supervised personal Codex host.

No brokerage calls, login or tokens. Mutations consume JSON from stdin, using the
actual clock; private broker routing is not written to the journal or output.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from execution_ledger import ExecutionLedger
from risk_engine import canonical_hash, evaluate, validate_policy
from supervised_session import SupervisedSession

ROOT = Path(__file__).resolve().parents[1]


def initialize(directory):
    directory = Path(directory).resolve()
    if directory == ROOT or ROOT in directory.parents:
        raise ValueError("Runtime must be outside the installed skill")
    directory.mkdir(parents=True, exist_ok=False)
    policy = json.loads((ROOT / "templates/personal-policy.example.json").read_text(encoding="utf-8"))
    (directory / "policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    for name in ("evidence", "reports"):
        (directory / name).mkdir()
    ledger = ExecutionLedger(directory / "execution.db")
    ledger.close()
    session = SupervisedSession(directory / "supervised-session.db")
    session.close()
    return {"runtime": str(directory), "mode": "paper", "configuration_status": "draft",
            "next": "Configure investor policy and personal broker capability mapping; no live authority created"}


def doctor(directory):
    directory = Path(directory).resolve()
    checks, failures = {}, []
    for dependency in ("numpy", "scipy", "exchange_calendars", "yfinance", "jsonschema", "requests"):
        try:
            checks[dependency] = importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            failures.append("MISSING_DEPENDENCY:" + dependency)
    try:
        policy = json.loads((directory / "policy.json").read_text(encoding="utf-8-sig"))
        validate_policy(policy)
        checks["policy_hash"] = canonical_hash(policy)
        checks["mode"] = policy["mode"]
        if policy["schema_version"] != 3 or policy.get("configuration_status") != "approved":
            failures.append("PERSONAL_POLICY_REQUIRES_CONFIGURATION_AND_APPROVAL")
        if policy["mode"] == "paper":
            failures.append("PAPER_MODE_NO_LIVE_AUTHORITY")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append("POLICY_INVALID_OR_MISSING:" + type(exc).__name__)
    for filename in ("execution.db", "supervised-session.db"):
        if not (directory / filename).is_file():
            failures.append("MISSING_RUNTIME_DATABASE:" + filename)
    if (directory / "execution.db").is_file():
        ledger = ExecutionLedger(directory / "execution.db")
        try:
            checks["unresolved_intents"] = len(ledger.unresolved())
            checks['unresolved_cancellations'] = len(ledger.unresolved_cancellations())
            if checks["unresolved_intents"] or checks['unresolved_cancellations']:
                failures.append("UNRESOLVED_INTENTS_REQUIRE_BROKER_RECONCILIATION")
        finally:
            ledger.close()
    return {"local_checks_passed": not failures, "failures": failures, "checks": checks,
            "live_readiness": "Requires an exact claim with fresh broker evidence, active session and human authorization"}


def dispatch(directory, operation, request):
    directory = Path(directory).resolve()
    if not (directory / "execution.db").is_file():
        raise ValueError("Initialize an explicit runtime directory first")
    if "now" in request or "now" in request.get("inputs", {}):
        raise ValueError("The personal command interface does not accept a caller-supplied clock")
    now = datetime.now(timezone.utc)
    policy = json.loads((directory / "policy.json").read_text(encoding="utf-8-sig"))
    if operation == "session":
        session = SupervisedSession(directory / "supervised-session.db")
        try:
            action = request["operation"]
            if action not in {"start", "heartbeat", "status", "stop"}:
                raise ValueError("Unknown session action")
            inputs = dict(request["inputs"])
            if action != "stop":
                inputs["policy_hash"] = canonical_hash(policy)
            return getattr(session, action)(**inputs, now=now) or {"state": "STOPPED"}
        finally:
            session.close()
    if operation == "risk":
        return evaluate(policy, request["snapshot"], request["order"], now)
    ledger = ExecutionLedger(directory / "execution.db")
    try:
        if operation == "authorize":
            if request["policy_hash"] != canonical_hash(policy):
                raise ValueError("Authorization must bind the currently saved policy")
            ledger.authorize(request)
            return {"recorded": request["id"], "caveat": "Host must have verified the actual human grant"}
        if operation == "revoke":
            ledger.revoke(request["authorization_id"])
            return {"revoked": request["authorization_id"], "existing_broker_orders_unchanged": True}
        if operation == "claim":
            return ledger.claim(policy, request["snapshot"], request["order"], request["review"],
                                request.get("authorization_id"), now)
        if operation == "reconcile":
            row = ledger.reconcile(request["order_id"], request["state"], request["cumulative_filled"],
                                   request.get("average_price"), now)
            return {k: row[k] for k in ("id", "state", "filled", "average_price")}
        if operation == 'claim-cancel':
            return ledger.claim_cancel(policy,request['snapshot'],request['action'],request['review'],request['authorization_id'],now)
        if operation == 'reconcile-cancel':
            return ledger.reconcile_cancel(request['action_id'],request['target_state'],request['evidence_ref'],now)
        if operation == "unresolved":
            return dict(orders=[{k: row[k] for k in ("id", "state", "filled")} for row in ledger.unresolved()],
                        cancellations=ledger.unresolved_cancellations())
        raise ValueError("Unsupported local operation")
    finally:
        ledger.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["init", "doctor", "risk", "authorize", "revoke", "claim", "reconcile", "unresolved", "session", "claim-cancel", "reconcile-cancel"])
    parser.add_argument("runtime", type=Path)
    args = parser.parse_args()
    try:
        if args.operation == "init":
            result = initialize(args.runtime)
        elif args.operation == "doctor":
            result = doctor(args.runtime)
        else:
            result = dispatch(args.runtime, args.operation, {} if args.operation == "unresolved" else json.load(sys.stdin))
        print(json.dumps(result, indent=2, allow_nan=False))
        if isinstance(result, dict) and (result.get("allowed") is False or result.get("local_checks_passed") is False):
            return 2
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"blocked": True, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
