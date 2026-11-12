"""Research assurance routes replay without mutating a research registry."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import quant_workbench as q


def envelope(operation, document):
    return {'schema_version': 1, 'contract': {
        'prompt': 'Fictional integration fixture', 'purpose': 'offline regression',
        'base_currency': 'USD', 'horizon_id': 'one_day', 'as_of': '2026-11-01T23:00:00Z'},
        'jobs': [{'id': 'fixture', 'operation': operation, 'inputs': {'document': document}}]}


class AssuranceIntegrationTests(unittest.TestCase):
    def test_data_registry_rights_and_analyst_routes_replay(self):
        from test_analyst_adapter import request
        cases = []
        for name, operation in [('readiness', 'data.strategy_readiness'),
                                ('security-master', 'data.security_snapshot'),
                                ('features', 'data.source_features'),
                                ('price-refresh', 'data.price_refresh')]:
            cases.append((operation, json.loads((ROOT / ('examples/quant-data/' + name + '.json')).read_text())))
        attempt = json.loads((ROOT / 'examples/experiment-attempt.json').read_text())
        cases += [('experiment.validate_attempt', attempt),
                  ('experiment.overlap_review', {'attempts': [attempt]}),
                  ('release.rights_inventory', json.loads((ROOT / 'templates/source-rights-inventory.json').read_text())),
                  ('analyst.extract_table', request('Analyst | Firm | Target | Date\nPerson | Demo | $100 | 2026-10-30')),
                  ('analyst.earnings_basis', {'as_of': '2026-11-01T00:00:00Z',
                    'quote': {'price': 100, 'currency': 'USD', 'share_basis': 'post', 'available_at': '2026-10-30T00:00:00Z'},
                    'estimates': [{'id': 'demo', 'eps': 5, 'period_start': '2026-01-01', 'period_end': '2026-12-31',
                    'period_type': 'fiscal', 'accounting_basis': 'GAAP', 'share_basis': 'post', 'currency': 'USD',
                    'source': 'fictional', 'available_at': '2026-10-30T00:00:00Z'}]})]
        for operation, doc in cases:
            bundle = q.freeze(envelope(operation, doc))
            self.assertEqual(bundle['result']['results'][0]['status'], 'COMPUTED', bundle['result'])
            self.assertEqual(q.verify(bundle)['status'], 'REPLAY_MATCH')

    def test_accounting_freeze_replay_and_input_tampering(self):
        doc = json.loads((ROOT / 'examples/holdings-event-ledger.json').read_text())
        req = envelope('backtest.holdings_ledger', doc)
        bundle = q.freeze(q.prepare(req))
        self.assertEqual(bundle['result']['results'][0]['status'], 'COMPUTED')
        self.assertEqual(q.verify(bundle)['status'], 'REPLAY_MATCH')
        bundle['input']['jobs'][0]['inputs']['document']['opening']['cash'] = '1'
        with self.assertRaises(ValueError):
            q.verify(bundle)

    def test_accounting_cutoff_and_currency_bound_to_contract(self):
        doc = json.loads((ROOT / 'examples/holdings-event-ledger.json').read_text())
        for field, value, reason in [('as_of', '2027-01-01T00:00:00Z', 'FUTURE_ASSURANCE_CUTOFF'),
                                     ('currency', 'EUR', 'ASSURANCE_CURRENCY_MISMATCH')]:
            changed = copy.deepcopy(doc); changed[field] = value
            result = q.run(envelope('backtest.holdings_ledger', changed))['results'][0]
            self.assertEqual(result['status'], 'REJECTED_INPUT')
            self.assertIn(reason, result['reason'])

    def test_risk_examples_and_sensitivity_contract(self):
        example = json.loads((ROOT / 'examples/fictional-risk-diagnostics.json').read_text())
        for request in example['requests']:
            doc = request['inputs']['document']
            req = envelope(request['operation'], doc)
            if request['operation'] == 'portfolio.sensitivity':
                req['contract']['horizon_id'] = doc['base']['horizon_id']
            bundle = q.freeze(req)
            self.assertEqual(bundle['result']['results'][0]['status'], 'COMPUTED', bundle['result'])
            self.assertEqual(q.verify(bundle)['status'], 'REPLAY_MATCH')
            if request['operation'] == 'portfolio.sensitivity':
                req['contract']['horizon_id'] = 'different-horizon'
                self.assertEqual(q.run(req)['results'][0]['status'], 'REJECTED_INPUT')

    def test_pure_registry_and_grading_only(self):
        for op in ['experiment.register', 'experiment.capture_forward', 'release.run_fixtures']:
            self.assertNotIn(op, q.OPERATIONS)
        self.assertEqual(q.OPERATIONS['experiment.overlap_review']({'attempts': []})['registered_attempt_count'], 0)
        grade = {'response_text': '{"n": 2}', 'expected': {'n': 2}, 'absolute_tolerance': 0, 'relative_tolerance': 0}
        bundle = q.freeze(envelope('release.grade_response', grade))
        self.assertEqual(q.verify(bundle)['status'], 'REPLAY_MATCH')
        self.assertFalse(bundle['result']['results'][0]['result']['external_invocation_authenticated'])

    def test_implementation_hash_includes_assurance_dependencies(self):
        import report_facts
        self.assertEqual(q.implementation_hash(), report_facts.quant_hash())
        for name in ['research_contracts.py', 'garch_volatility.py', 'holdings_ledger.py',
                     'analyst_adapter.py', 'release_acceptance.py', 'experiment_registry.py']:
            self.assertIn(name, q.MODULES)
        self.assertEqual(len(q.ASSURANCE_OPERATIONS), 15)

    def test_readiness_all_clocks_bound_to_outer_cutoff(self):
        doc = json.loads((ROOT / 'examples/quant-data/readiness.json').read_text())
        for key in ('decision_at', 'valuation_at', 'execution_at'):
            changed = copy.deepcopy(doc)
            changed['decisions'][0][key] = '2027-01-01T00:00:00Z'
            row = q.run(envelope('data.strategy_readiness', changed))['results'][0]
            self.assertEqual(row['status'], 'REJECTED_INPUT')
            self.assertIn('FUTURE_READINESS_CLOCK', row['reason'])


if __name__ == '__main__':
    unittest.main()
