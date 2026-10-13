"""Fictional offline research and allocation walkthrough; no order dispatcher."""
import copy
import json
from pathlib import Path
from portfolio_manager import rebalance
from risk_engine import evaluate, timestamp
from execution_handoff import handoff

def main():
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root/'templates/policy.example.json').read_text())
    snapshot = json.loads((root/'examples/snapshot.json').read_text())
    order = json.loads((root/'examples/order.json').read_text())
    now = timestamp('2026-10-06T14:00:00Z')
    risk = evaluate(policy,snapshot,order,now)
    checks = {'fictional_risk_diagnostics':risk,
              'core_rebalance_candidates':rebalance(**json.loads((root/'examples/rebalance.json').read_text())),
              'native_execution_handoff':handoff({'order':order,'risk_observations':risk}),
              'scope':'FICTIONAL OFFLINE RESEARCH; no broker access or live validation'}
    print(json.dumps(checks,indent=2))

if __name__ == '__main__':
    main()
