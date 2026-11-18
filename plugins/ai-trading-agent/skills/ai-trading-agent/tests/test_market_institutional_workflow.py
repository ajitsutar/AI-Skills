"""Source-bound additive integration checks with fictional public evidence."""
import copy
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import quant_workbench as qw
import report_facts as rf
import research_workflow as workflow
import market_sources
import institutional_research


def fixture(name):
    return json.loads((ROOT / 'examples' / name).read_text(encoding='utf8'))


def contract(as_of):
    return {'prompt': 'Review fictional event evidence', 'purpose': 'offline synthetic research',
            'base_currency': 'USD', 'horizon_id': 'declared-event-window', 'as_of': as_of}


class MarketInstitutionalIntegrationTests(unittest.TestCase):
    def test_pure_operations_are_registered_but_acquisition_and_journal_are_not(self):
        expected = {'market.normalize', 'market.parse', 'market.flow', 'market.positioning',
                    'market.squeeze', 'institutional.plan', 'institutional.brief', 'institutional.evaluate'}
        self.assertTrue(expected <= qw.OPERATIONS.keys())
        self.assertFalse({'market.acquire', 'institutional.journal', 'institutional.capture',
                          'institutional.recover', 'institutional.release-lock'} & qw.OPERATIONS.keys())
        self.assertEqual(qw.implementation_hash(), rf.quant_hash())

    def test_outer_cutoff_and_currency_reject_future_or_conflicting_payloads(self):
        original = fixture('market-flow-synthetic.json')
        for operation in qw.MARKET_RESEARCH_OPERATIONS:
            if operation == 'market.parse':
                continue
            with self.subTest(operation=operation):
                payload = copy.deepcopy(original)
                request = {'schema_version': 1, 'contract': contract('2020-01-01T00:00:00Z'),
                           'jobs': [{'id': 'future', 'operation': operation, 'inputs': {'document': payload}}]}
                result = qw.run(request)['results'][0]
                self.assertEqual(result['status'], 'REJECTED_INPUT')
                self.assertIn('FUTURE_MARKET_RESEARCH_CUTOFF', result['reason'])
                request['contract']['as_of'] = payload['as_of']
                payload['currency'] = 'EUR'
                result = qw.run(request)['results'][0]
                self.assertEqual(result['status'], 'REJECTED_INPUT')
                self.assertIn('MARKET_RESEARCH_CURRENCY_MISMATCH', result['reason'])

    def test_pure_replay_performs_no_acquisition_or_journal_mutation(self):
        document = fixture('institutional-event-input.json')
        request = {'schema_version': 1, 'contract': contract(document['as_of']), 'jobs': [
            {'id': 'plan', 'operation': 'institutional.plan', 'inputs': {'document': document}},
            {'id': 'brief', 'operation': 'institutional.brief', 'inputs': {'document': document}}]}
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')), \
             mock.patch.object(market_sources, 'acquire', side_effect=AssertionError('acquisition forbidden')), \
             mock.patch.object(institutional_research, '_record', side_effect=AssertionError('journal forbidden')):
            bundle = qw.freeze(request)
            self.assertEqual(qw.verify(bundle)['status'], 'REPLAY_MATCH')
        self.assertTrue(all(x['status'] == 'COMPUTED' for x in bundle['result']['results']))
        self.assertFalse(bundle['result']['execution_authorized'])

    def test_report_preserves_units_unknowns_and_heuristic_state(self):
        document = fixture('market-flow-synthetic.json')
        request = {'schema_version': 1, 'contract': contract(document['as_of']), 'jobs': [
            {'id': 'flow', 'operation': 'market.flow', 'inputs': {'document': document}},
            {'id': 'squeeze', 'operation': 'market.squeeze', 'inputs': {'document': document}}]}
        bundle = qw.freeze(request)
        self.assertTrue(all(x['status'] == 'COMPUTED' for x in bundle['result']['results']))
        facts = rf.project(json.dumps(bundle).encode(), 'quant')['facts']
        relative = next(x for x in facts if x['metric'] == 'Price return minus matched benchmark'
                        and x['value'] is not None)
        self.assertEqual(relative['unit'], 'percentage_points')
        state = next(x for x in facts if x['metric'] == 'Declared squeeze evidence heuristic')
        self.assertEqual(state['value'], 'DEVELOPING_PRESSURE_HEURISTIC')
        self.assertEqual(state['unit'], 'status')
        missing = next(x for x in facts if x['source']['pointer'].endswith('/probability'))
        self.assertIsNone(missing['value'])
        self.assertEqual(missing['missingness'], 'null')

    def test_source_bound_execute_retains_original_and_verifies_new_operation(self):
        document = fixture('institutional-event-input.json')
        with tempfile.TemporaryDirectory(prefix='event-wf-') as temp:
            directory = Path(temp)
            source = directory / 'event.json'
            raw = workflow.encode({'document': document})
            source.write_bytes(raw)
            request = {'schema_version': 1, 'contract': contract(document['as_of']),
                'jobs': [{'id': 'brief', 'operation': 'institutional.brief',
                          'inputs_source': {'path': 'event.json', 'sha256': workflow.sha(raw), 'pointer': ''}}],
                'requirements': [{'id': 'brief', 'question': 'Retain a dated event brief',
                                  'job_ids': ['brief'], 'expected_operations': ['institutional.brief']}]}
            request_path = directory / 'request.json'
            request_raw = workflow.encode(request)
            request_path.write_bytes(request_raw)
            output = directory / 'output'
            with mock.patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
                completed = workflow.execute(request_path, output, 'Synthetic event request',
                                             {'event.json': 'fictional retained event evidence'})
            self.assertIsNone(completed['failure'])
            self.assertEqual(completed['jobs'][0]['computation_status'], 'COMPUTED')
            self.assertEqual((output / 'original-request.json').read_bytes(), request_raw)
            self.assertFalse(completed['whole_answer_pass'])
            self.assertFalse(completed['execution_authorized'])
            self.assertEqual(workflow.verify(output / 'run')['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            result = json.loads((output / 'run/result.json').read_bytes())
            brief = result['jobs'][0]['result']
            self.assertEqual(brief['evidence_record_ids'], ['fictional-catalyst-v1'])
            self.assertFalse(brief['profitability_established'])
            self.assertTrue((output / 'answer-facts.json').is_file())

    def test_event_example_keeps_benchmark_and_separate_causal_costed_signal(self):
        request = fixture('market-event-workbench.json')
        bundle = qw.freeze(request)
        self.assertTrue(all(x['status'] == 'COMPUTED' for x in bundle['result']['results']))
        brief, replay = [x['result'] for x in bundle['result']['results']]
        self.assertEqual(brief['squeeze']['assessments'][0]['state'], 'DEVELOPING_PRESSURE_HEURISTIC')
        current = next(x for x in brief['flow']['cumulative_bars'] if x['role'] == 'current')
        self.assertEqual(current['benchmark_relative_return_percent'], 5.0)
        self.assertEqual(replay['fills'][0]['at'], '2026-11-12T14:30:00Z')
        self.assertEqual(replay['fills'][0]['quantity'], '20')
        self.assertGreater(float(replay['total_fees']), 0)
        self.assertFalse(brief['profitability_established'])
        self.assertFalse(replay['production_qualified'])
        self.assertEqual(qw.verify(bundle)['status'], 'REPLAY_MATCH')

    def test_nested_institutional_currency_cannot_bypass_outer_contract(self):
        for operation, name in [('institutional.brief', 'institutional-event-input.json'),
                                ('institutional.evaluate', 'institutional-evaluation-input.json')]:
            document = fixture(name)
            request = {'schema_version': 1, 'contract': contract(document['as_of']),
                       'jobs': [{'id': 'currency', 'operation': operation, 'inputs': {'document': document}}]}
            self.assertNotIn('currency', document)
            with self.subTest(operation=operation):
                positive = qw.run(request)['results'][0]
                self.assertEqual(positive['status'], 'COMPUTED')
                request['contract']['base_currency'] = 'EUR'
                negative = qw.run(request)['results'][0]
                self.assertEqual(negative['status'], 'REJECTED_INPUT')
                self.assertIn('INSTITUTIONAL_CURRENCY_MISMATCH_NO_FX_MODEL', negative['reason'])

    def test_cost_only_and_benchmark_currency_conflicts_are_detected(self):
        document = fixture('institutional-event-input.json')
        document.pop('portfolio'); document.pop('proposed_trade'); document.pop('liquidity')
        document['cost_contract']['currency'] = 'EUR'
        request = {'schema_version': 1, 'contract': contract(document['as_of']),
                   'jobs': [{'id': 'cost', 'operation': 'institutional.brief', 'inputs': {'document': document}}]}
        self.assertIn('INSTITUTIONAL_CURRENCY_MISMATCH_NO_FX_MODEL', qw.run(request)['results'][0]['reason'])
        document = fixture('institutional-evaluation-input.json')
        document['evaluation']['cases'][0]['paper_return']['benchmark']['currency'] = 'EUR'
        request['contract'] = contract(document['as_of'])
        request['jobs'][0].update(operation='institutional.evaluate', inputs={'document': document})
        self.assertIn('INSTITUTIONAL_CURRENCY_MISMATCH_NO_FX_MODEL', qw.run(request)['results'][0]['reason'])

    def test_plan_without_monetary_inputs_does_not_invent_a_currency_requirement(self):
        document = fixture('institutional-event-input.json')
        for key in ('portfolio', 'proposed_trade', 'cost_contract', 'liquidity'):
            document.pop(key, None)
        request = {'schema_version': 1, 'contract': dict(contract(document['as_of']), base_currency='EUR'),
                   'jobs': [{'id': 'plan', 'operation': 'institutional.plan', 'inputs': {'document': document}}]}
        self.assertEqual(qw.run(request)['results'][0]['status'], 'COMPUTED')

    def test_report_keeps_unknown_volume_basis_and_independent_price_context(self):
        document = fixture('market-flow-synthetic.json')
        for record in document['records']:
            if record['kind'] == 'bar':
                record['payload'].pop('volume_basis', None)
        request = {'schema_version': 1, 'contract': contract(document['as_of']),
                   'jobs': [{'id': 'basis', 'operation': 'market.flow', 'inputs': {'document': document}}]}
        facts = rf.project(json.dumps(qw.freeze(request)).encode(), 'quant')['facts']
        qualifier = next(x for x in facts if x['metric'] == 'Relative-volume comparability qualification'
                         and x['value'] == 'VOLUME_BASIS_UNKNOWN_OR_UNRESOLVED')
        self.assertEqual(qualifier['unit'], 'status')
        ratio = next(x for x in facts if x['metric'] == 'Same-window relative volume')
        self.assertIsNone(ratio['value'])
        self.assertTrue(any(x['metric'] == 'Price return minus matched benchmark' and x['value'] is not None for x in facts))

    def test_report_keeps_protocol_conflict_and_zero_included_cases(self):
        document = fixture('institutional-evaluation-input.json')
        document['pilot']['study']['usefulness_criterion'] = 'Different frozen fictional criterion'
        request = {'schema_version': 1, 'contract': contract(document['as_of']),
                   'jobs': [{'id': 'protocol', 'operation': 'institutional.evaluate', 'inputs': {'document': document}}]}
        bundle = qw.freeze(request)
        self.assertEqual(bundle['result']['results'][0]['status'], 'COMPUTED')
        result = bundle['result']['results'][0]['result']
        self.assertEqual(result['protocol_reconciliation']['status'], 'PROTOCOL_CONFLICT')
        self.assertEqual(result['usefulness']['included_cases'], 0)
        self.assertEqual(result['returns']['included_cases'], 0)
        facts = rf.project(json.dumps(bundle).encode(), 'quant')['facts']
        status = next(x for x in facts if x['source']['pointer'].endswith('/protocol_reconciliation/status'))
        self.assertEqual(status['value'], 'PROTOCOL_CONFLICT')
        self.assertEqual(status['unit'], 'status')
        self.assertTrue(any(x['metric'] == 'Included declared usefulness judgments' and x['value'] == 0 for x in facts))


if __name__ == '__main__':
    unittest.main()
