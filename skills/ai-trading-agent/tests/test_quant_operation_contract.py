"""Explicit-default receipts separate model parameter choices from arithmetic."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import quant_workbench as workbench


def document():
    return {'schema_version': 1,
            'contract': {'prompt': 'Fictional tail and bootstrap study', 'purpose': 'research',
                         'base_currency': 'USD', 'horizon_id': 'P1D', 'as_of': '2026-10-13T16:00:00Z'},
            'jobs': [{'id': 'tail', 'operation': 'validation.tail', 'inputs': {'returns': [-.1, .02, .03]}},
                     {'id': 'bootstrap', 'operation': 'validation.bootstrap',
                      'inputs': {'returns': [.01, -.02, .03, -.01] * 10, 'block_length': 4}}]}


class OperationContractTests(unittest.TestCase):
    def test_preparation_is_idempotent_and_preserves_original(self):
        raw = document()
        original = copy.deepcopy(raw)
        prepared = workbench.prepare(raw)
        self.assertEqual(raw, original)
        self.assertEqual(prepared, workbench.prepare(prepared))
        self.assertEqual(prepared['jobs'][0]['inputs']['confidence'], .975)
        self.assertEqual(prepared['jobs'][1]['inputs']['seed'], 0)
        self.assertEqual(prepared['jobs'][1]['inputs']['replications'], 1000)

    def test_explicit_and_omitted_defaults_bind_same_computation(self):
        raw = document()
        prepared = workbench.prepare(raw)
        a, b = workbench.run(raw), workbench.run(prepared)
        for x, y in zip(a['results'], b['results']):
            self.assertEqual(x['result'], y['result'])
            self.assertEqual(x['resolved_inputs_sha256'], y['resolved_inputs_sha256'])
            self.assertTrue(x['defaults_used'])
            self.assertEqual(y['defaults_used'], {})
        self.assertNotEqual(a['input_sha256'], b['input_sha256'])

    def test_explicit_seed_and_confidence_never_overridden(self):
        raw = document()
        raw['jobs'][0]['inputs']['confidence'] = .9
        raw['jobs'][1]['inputs'].update(seed=17, replications=100)
        prepared = workbench.prepare(raw)
        self.assertEqual(prepared, raw)
        changed = document()
        self.assertNotEqual(workbench.run(raw)['results'][1]['resolved_inputs_sha256'],
                            workbench.run(changed)['results'][1]['resolved_inputs_sha256'])

    def test_missing_measurements_and_unknown_parameters_not_invented(self):
        raw = document()
        del raw['jobs'][0]['inputs']['returns']
        with self.assertRaises(TypeError):
            workbench.prepare(raw)
        self.assertEqual(workbench.run(raw)['results'][0]['status'], 'REJECTED_INPUT')
        raw = document()
        raw['jobs'][0]['inputs']['made_up_model_flag'] = True
        with self.assertRaises(TypeError):
            workbench.prepare(raw)

    def test_catalog_is_actual_allowlist_and_runtime_receipt_replays(self):
        catalog = workbench.operation_catalog()
        self.assertEqual(set(catalog['operations']), set(workbench.OPERATIONS))
        self.assertEqual(catalog['operations']['validation.hac']['required'], ['returns', 'lags'])
        bundle = workbench.freeze(workbench.prepare(document()))
        self.assertIn('python', bundle['environment'])
        self.assertIn('numpy', bundle['environment'])
        self.assertEqual(workbench.verify(bundle)['status'], 'REPLAY_MATCH')


if __name__ == '__main__':
    unittest.main()
