"""Exact source-object contract exports, independent of evaluation packets."""
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import handoff_report as exact_json
import research_contracts
import research_workflow as workflow


class ContractDecimalExportTests(unittest.TestCase):
    def test_whole_object_decimal_binding_claim_report_and_replay(self):
        raw = b'{"prompt":"Inspect the supplied observation.","data":{"ratio":0.123456789012345678901,"nested":[0.07,3,true,null],"label":"0.07"},"comparison":{"x":0.0700,"tiny":1e-7,"whole":1.0}}'
        expected = exact_json.strict_json(raw)['data']
        source = {'id': 'observation', 'path': 'observation.json',
                  'sha256': workflow.sha(raw), 'format': 'json', 'role': 'supplied_observation'}
        document = {'allowlist': ['observation.json'], 'sources': [source],
                    'prompt_binding': {'source_id': 'observation', 'pointer': '/prompt'},
                    'bindings': [{'id': 'whole', 'source_id': 'observation', 'pointer': '/data',
                                  'target': 'observation', 'usage': 'selected'},
                                 {'id': 'comparison', 'source_id': 'observation', 'pointer': '/comparison',
                                  'target': 'comparison', 'usage': 'selected'}]}
        plan = {'schema_version': 1, 'network_mode': 'offline',
                'contract': {'prompt': 'Inspect the supplied observation.'},
                'sources': [source], 'jobs': [{'id': 'bind', 'operation': 'research.bind_request',
                    'arguments': {'document': {'$assumption': document, 'reason': 'Explicit source selection'}}}],
                'requirements': [{'id': 'whole', 'question': 'Retain the whole selected object.',
                                  'job_ids': ['bind'], 'expected_operations': ['research.bind_request']}],
                'claims': [{'id': 'ratio', 'job_id': 'bind',
                            'pointer': '/result/result/bindings/0/value/ratio'},
                           {'id': 'object', 'job_id': 'bind',
                            'pointer': '/result/result/bindings/1/value',
                            'assertion': {'x': 0.07, 'tiny': 1e-7, 'whole': 1.0}}]}
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'observation.json').write_bytes(raw)
            (folder / 'plan.json').write_bytes(workflow.encode(plan))
            output = folder / 'result'
            result = workflow.run(folder / 'plan.json', output)
            self.assertEqual(result['status'], 'COMPUTED')
            binding = result['jobs'][0]['result']['result']['bindings'][0]
            self.assertEqual(binding['value'], expected)
            self.assertIsInstance(binding['value']['ratio'], Decimal)
            self.assertEqual(binding['value_sha256'], research_contracts.digest(expected))
            self.assertEqual(result['claims'][0]['status'], 'PROJECTED')
            self.assertEqual(result['claims'][0]['actual_value'], expected['ratio'])
            self.assertEqual(result['claims'][1]['status'], 'MATCH')
            saved = exact_json.strict_json((output / 'result.json').read_bytes())
            self.assertEqual(saved['jobs'][0]['result']['result']['bindings'][0]['value'], expected)
            for retained_binding in saved['jobs'][0]['result']['result']['bindings']:
                self.assertEqual(research_contracts.digest(retained_binding['value']),
                                 retained_binding['value_sha256'])
            comparison = saved['jobs'][0]['result']['result']['bindings'][1]['value']
            self.assertEqual(str(comparison['x']), '0.0700')
            self.assertIn(b'0.123456789012345678901', (output / 'report.md').read_bytes())
            self.assertEqual(workflow.verify(output)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            summary = workflow.summarize(output)
            self.assertEqual(summary['claims'][0]['actual_value'], expected['ratio'])
            self.assertEqual((output / 'sources/observation.json').read_bytes(), raw)

    def test_encoder_preserves_numeric_types_and_rejects_nonfinite_decimals(self):
        value = {'number': Decimal('0.000000000000000000123456789'),
                 'text': '0.000000000000000000123456789', 'integer': 4, 'boolean': True}
        self.assertEqual(exact_json.strict_json(workflow.encode(value)), value)
        for bad in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                workflow.encode({'number': Decimal(bad)})
        with self.assertRaises(TypeError):
            workflow.encode({'unsupported': object()})
        self.assertTrue(workflow.assertion_matches(
            {'x': Decimal('0.0700'), 'tiny': Decimal('1E-7')}, {'x': 0.07, 'tiny': 1e-7}))
        self.assertIn(b'0.0700', workflow.encode({'x': Decimal('0.0700')}))
        self.assertNotEqual(workflow.encode({'x': Decimal('1.0')}), workflow.encode({'x': 1}))
        self.assertNotEqual(workflow.encode(True), workflow.encode(1))
        self.assertFalse(workflow.assertion_matches({'x': Decimal('1.0')}, {'x': 1}))
        self.assertFalse(workflow.assertion_matches(True, 1))

    def test_generated_contract_float_scientific_notation_replays(self):
        plan = {'schema_version': 1, 'network_mode': 'offline',
                'contract': {'prompt': 'Inspect generated diagnostics.'}, 'sources': [],
                'jobs': [{'id': 'route', 'operation': 'research.route_horizon',
                          'arguments': {'document': {}}}],
                'requirements': [{'id': 'route', 'question': 'Inspect diagnostics.', 'job_ids': ['route']}],
                'claims': [{'id': 'value', 'job_id': 'route', 'pointer': '/result',
                            'assertion': {'status': 'TEST_DIAGNOSTIC', 'small': 1e-7, 'integral': 1.0}}]}
        generated = {'status': 'TEST_DIAGNOSTIC', 'small': 1e-7, 'integral': 1.0}
        # Exercise the workflow boundary independently of an adapter's internals.
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(
                workflow.CONTRACT_OPERATIONS, {'research.route_horizon': lambda document: generated}):
            folder = Path(temporary)
            (folder / 'plan.json').write_bytes(workflow.encode(plan))
            result = workflow.run(folder / 'plan.json', folder / 'result')
            self.assertEqual(result['claims'][0]['status'], 'MATCH')
            self.assertEqual(workflow.verify(folder / 'result')['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            self.assertEqual(workflow.summarize(folder / 'result')['claims'][0]['status'], 'MATCH')


if __name__ == '__main__':
    unittest.main()
