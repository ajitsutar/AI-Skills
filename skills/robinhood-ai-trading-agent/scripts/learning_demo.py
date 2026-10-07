"""Offline walkthrough with fictional data. No broker client or network calls."""
import copy
import json
import tempfile
from pathlib import Path

from execution_ledger import ExecutionLedger, GateClosed
from portfolio_manager import rebalance
from risk_engine import evaluate, timestamp


def main():
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root / "templates/policy.example.json").read_text())
    snapshot = json.loads((root / "examples/snapshot.json").read_text())
    order = json.loads((root / "examples/order.json").read_text())
    now = timestamp("2026-10-06T14:00:00Z")  # Fixed replay clock, never a live clock.
    risk = evaluate(policy, snapshot, order, now)
    stale = copy.deepcopy(snapshot)
    stale["quotes"]["DEMO"]["as_of"] = "2026-10-06T13:59:00Z"
    checks = {"valid_fictional_proposal": risk,
              "stale_quote_is_blocked": evaluate(policy, stale, order, now)}
    with tempfile.TemporaryDirectory(prefix="trading-learning-") as directory:
        ledger = ExecutionLedger(Path(directory) / "paper.db")
        try:
            checks["paper_claim"] = ledger.claim(policy, snapshot, order, {}, now=now)
            ledger.reconcile(order["id"], "PARTIALLY_FILLED", "5", "100.01", now)
            state = ledger.reconcile(order["id"], "CANCELLED", "5", "100.01", now)
            checks["partial_fill_then_cancel"] = {k: state[k] for k in ("state", "filled", "average_price")}
            try:
                ledger.claim(policy, snapshot, order, {}, now=now)
            except GateClosed as exc:
                checks["duplicate_blocked"] = str(exc)
        finally:
            ledger.close()
    checks["core_rebalance_candidates"] = rebalance(**json.loads((root / "examples/rebalance.json").read_text()))
    checks["scope"] = "FICTIONAL OFFLINE LEARNING ONLY; no broker access, investment recommendation or live validation"
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
