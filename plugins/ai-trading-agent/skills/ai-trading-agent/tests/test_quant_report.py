"""End-to-end retained-input binding, helper replay and report fidelity."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import quant_report as runner
import quant_workbench as workbench
import report_facts


def document():
    return {'schema_version': 1,
            'contract': {'prompt': 'Private fictional serial-dependence study', 'purpose': 'offline research',
                         'base_currency': 'USD', 'horizon_id': 'P19M', 'as_of': '2026-10-13T16:00:00Z'},
            'jobs': [{'id': 'tail', 'operation': 'validation.tail', 'inputs': {'returns': [.1, -.2, .03]}},
                     {'id': 'bootstrap', 'operation': 'validation.bootstrap',
                      'inputs': {'returns': [.01, -.03, .02, -.01] * 10, 'block_length': 4,
                                 'replications': 113, 'seed': 2718}}]}


def decode(artifacts, name):
    return report_facts.strict_json(artifacts[name])


def no_sources(path, index):
    raise AssertionError('Unexpected source read')


class QuantReportTests(unittest.TestCase):
    def test_one_path_preserves_raw_contract_parameters_and_exact_facts(self):
        original = document()
        # Byte identity includes formatting/BOM, separately from semantic hashes.
        raw = b'\xef\xbb\xbf' + json.dumps(original, indent=4).encode()
        artifacts = runner.build(raw, no_sources)
        self.assertEqual(artifacts['request.json'], raw)
        prepared, bindings = decode(artifacts, 'prepared.json'), decode(artifacts, 'bindings.json')
        self.assertEqual(prepared['contract'], original['contract'])
        self.assertEqual(prepared['jobs'][1], original['jobs'][1])
        self.assertEqual(bindings[0]['defaults_used'], {'confidence': .975})
        self.assertEqual(bindings[1]['defaults_used'], {})
        bundle = decode(artifacts, 'bundle.json')
        self.assertEqual(bundle['result']['results'], workbench.run(prepared)['results'])
        facts = decode(artifacts, 'facts.json')
        for fact in facts['facts']:
            if fact['missingness'] is None:
                self.assertEqual(fact['value'], report_facts.pointer(bundle, fact['source']['pointer']))
        drawdown = next(f for f in facts['facts'] if f['metric'] == 'Input-series maximum drawdown')
        self.assertEqual(drawdown['denominator'], 'running peak synthetic wealth')
        self.assertIsNone(drawdown['measurement_period'])
        self.assertEqual(drawdown['horizon'], 'P19M')
        self.assertEqual(artifacts, runner.build(raw, no_sources))

    def test_hashed_sources_select_the_whole_object_without_parameter_copying(self):
        source = runner.encoded({'retained': {'returns': [.01, -.02, .04] * 10, 'lags': 5}})
        request = document()
        request['jobs'] = [{'id': 'hac', 'operation': 'validation.hac', 'inputs_source': {
            'path': 'observations.json', 'sha256': runner.sha(source), 'pointer': '/retained'}}]
        artifacts = runner.build(runner.encoded(request), lambda path, index: source)
        self.assertEqual(artifacts['source-0000.json'], source)
        bundle = decode(artifacts, 'bundle.json')
        self.assertEqual(bundle['input']['jobs'][0]['inputs'], json.loads(source)['retained'])
        self.assertEqual(bundle['result']['results'][0]['result']['lags'], 5)
        self.assertEqual(decode(artifacts, 'receipt.json')['source_bindings'][0]['pointer'], '/retained')
        interval = next(f for f in decode(artifacts, 'facts.json')['facts']
                        if f['metric'] == 'HAC mean 95% interval lower endpoint')
        self.assertEqual(interval['value'], bundle['result']['results'][0]['result']['ci95'][0])
        self.assertEqual(interval['unit'], 'return_fraction')
        self.assertIn('not a future-return bound', interval['basis'])
        self.assertIsNone(interval['observation_frequency'])
        request['jobs'][0]['inputs'] = {'lags': 0}
        with self.assertRaisesRegex(ValueError, 'ONE_INPUT_SOURCE_REQUIRED'):
            runner.build(runner.encoded(request), lambda path, index: source)

    def test_source_change_does_not_silently_become_new_evidence(self):
        request = document()
        request['jobs'] = [{'id': 'hac', 'operation': 'validation.hac', 'inputs_source': {
            'path': 'source.json', 'sha256': '0' * 64, 'pointer': ''}}]
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            runner.build(runner.encoded(request), lambda path, index: b'{}')

    def test_required_parameters_are_missing_while_valid_jobs_still_compute(self):
        request = document()
        request['jobs'].insert(0, {'id': 'missing-lags', 'operation': 'validation.hac',
                                   'inputs': {'returns': [.01, -.02, .03] * 10}})
        artifacts = runner.build(runner.encoded(request), no_sources)
        self.assertEqual(decode(artifacts, 'analysis.json')['status'], 'PARTIAL_ANALYSIS')
        self.assertEqual(decode(artifacts, 'analysis.json')['computed_jobs'], 2)
        self.assertEqual(decode(artifacts, 'bundle.json')['result']['results'][0]['status'], 'REJECTED_INPUT')
        self.assertNotIn('lags', decode(artifacts, 'prepared.json')['jobs'][0]['inputs'])
        self.assertEqual(decode(artifacts, 'bindings.json')[0]['status'], 'INVALID_HELPER_INPUT')
        self.assertFalse(any('/results/0/result/' in f['source']['pointer'] for f in decode(artifacts, 'facts.json')['facts']))

    def test_all_noncomputations_are_not_a_successful_analysis(self):
        request = document()
        request['jobs'] = [{'id': 'invalid', 'operation': 'validation.tail', 'inputs': {'returns': [-1.2, .02]}}]
        artifacts = runner.build(runner.encoded(request), no_sources)
        self.assertEqual(decode(artifacts, 'analysis.json')['status'], 'NO_COMPUTED_JOBS')

    def test_computed_ambiguous_xirr_preserves_null_and_nested_outcome(self):
        request = document()
        request['jobs'] = [{'id': 'nonconventional', 'operation': 'ops.xirr', 'inputs': {
            'cashflows': [{'at': '2024-01-01T00:00:00Z', 'amount': -100},
                          {'at': '2025-01-01T00:00:00Z', 'amount': 250},
                          {'at': '2026-01-01T00:00:00Z', 'amount': -140}]}}]
        artifacts = runner.build(runner.encoded(request), no_sources)
        analysis = decode(artifacts, 'analysis.json')
        self.assertEqual(analysis['status'], 'COMPUTED')
        self.assertEqual(analysis['jobs'][0]['computation_status'], 'COMPUTED')
        self.assertEqual(analysis['jobs'][0]['helper_outcome'], 'AMBIGUOUS_OR_NONCONVENTIONAL_CASHFLOWS')
        rate = next(f for f in decode(artifacts, 'facts.json')['facts'] if f['metric'] == 'Annualized XIRR')
        self.assertIsNone(rate['value'])
        self.assertEqual(rate['missingness'], 'null')
        self.assertIn(b'AMBIGUOUS_OR_NONCONVENTIONAL_CASHFLOWS', artifacts['report.md'])

    def test_unknown_operation_and_nonfinite_duplicate_inputs_are_not_executed(self):
        request = document()
        request['jobs'][0]['operation'] = 'os.system'
        with self.assertRaisesRegex(ValueError, 'OPERATION_NOT_ALLOWED'):
            runner.build(runner.encoded(request), no_sources)
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"number":NaN}', b'{"number":1e999}'):
            with self.assertRaises(ValueError):
                runner.build(raw, no_sources)

    def test_replay_uses_retained_sources_after_originals_disappear_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'observations.json'
            source.write_bytes(runner.encoded({'returns': [.01, -.02, .03] * 10, 'lags': 4}))
            request = document()
            request['jobs'] = [{'id': 'hac', 'operation': 'validation.hac', 'inputs_source': {
                'path': source.name, 'sha256': runner.sha(source.read_bytes()), 'pointer': ''}}]
            input_path = root / 'input.json'
            input_path.write_bytes(runner.encoded(request))
            output = root / 'run'
            runner.run(input_path, output)
            source.unlink()
            input_path.unlink()
            verified = runner.verify(output)
            self.assertEqual(verified['status'], 'REPLAY_AND_REPORT_MATCH')
            self.assertEqual(verified['numeric_replay_tolerances'], {'absolute': 1e-8, 'relative': 1e-7})
            self.assertEqual(verified['report_comparison'], 'EXACT_BYTES')
            self.assertEqual(json.loads((output / 'receipt.json').read_text())['numeric_replay_tolerances'],
                             verified['numeric_replay_tolerances'])
            preserved = {p.name: p.read_bytes() for p in output.iterdir()}
            with self.assertRaisesRegex(ValueError, 'NEW_OUTPUT_DIRECTORY_REQUIRED'):
                runner.run(root / 'absent.json', output)
            self.assertEqual(preserved, {p.name: p.read_bytes() for p in output.iterdir()})

    def test_tampered_narrative_even_with_updated_manifest_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.json'
            source.write_bytes(runner.encoded(document()))
            output = root / 'run'
            runner.run(source, output)
            report = output / 'report.md'
            report.write_text('Claimed account drawdown 0; validated investment result.', encoding='utf-8')
            receipt_path = output / 'receipt.json'
            receipt = json.loads(receipt_path.read_text())
            receipt['artifacts']['report.md'] = runner.sha(report.read_bytes())
            receipt_path.write_bytes(runner.encoded(receipt))
            with self.assertRaisesRegex(ValueError, 'CANONICAL_REPORT_MISMATCH'):
                runner.verify(output)

    def test_tampered_calculation_even_with_updated_hashes_must_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.json'
            source.write_bytes(runner.encoded(document()))
            output = root / 'run'
            runner.run(source, output)
            path = output / 'bundle.json'
            bundle = json.loads(path.read_text())
            bundle['result']['results'][0]['result']['max_drawdown'] = 0
            bundle['result_sha256'] = workbench.digest(bundle['result'])
            path.write_bytes(runner.encoded(bundle))
            receipt_path = output / 'receipt.json'
            receipt = json.loads(receipt_path.read_text())
            receipt['artifacts']['bundle.json'] = runner.sha(path.read_bytes())
            receipt_path.write_bytes(runner.encoded(receipt))
            with self.assertRaisesRegex(ValueError, 'REPLAY_MISMATCH'):
                runner.verify(output)

    def test_cli_produces_private_exports_and_reports_invalid_request_without_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'input.json'
            source.write_bytes(runner.encoded(document()))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/quant_report.py'), 'run',
                                     str(source), '--private-output-dir', str(root / 'run')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            self.assertEqual(runner.verify(root / 'run')['jobs_verified'], 2)
            request = document()
            request['jobs'][0]['operation'] = 'PRIVATE_INVALID_OPERATION_SENTINEL'
            source.write_bytes(runner.encoded(request))
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/quant_report.py'), 'run',
                                     str(source), '--private-output-dir', str(root / 'invalid')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('PRIVATE_INVALID_OPERATION_SENTINEL', result.stderr)
            self.assertFalse((root / 'invalid').exists())

    def test_bootstrap_interval_and_seed_are_projected_without_annualization(self):
        artifacts = runner.build(runner.encoded(document()), no_sources)
        bundle = decode(artifacts, 'bundle.json')
        facts = decode(artifacts, 'facts.json')['facts']
        interval = next(f for f in facts if f['metric'] == 'Block-bootstrap mean 95% interval upper endpoint')
        self.assertEqual(interval['value'], bundle['result']['results'][1]['result']['mean_percentile_ci95'][1])
        self.assertEqual(interval['unit'], 'return_fraction')
        self.assertIsNone(interval['measurement_period'])
        self.assertEqual(next(f for f in facts if f['metric'] == 'Bootstrap random seed')['value'], 2718)

    def test_url_and_network_source_paths_are_rejected_before_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path in ('https://example.invalid/observations.json', '//host/share/source.json'):
                request = document()
                request['jobs'] = [{'id': 'tail', 'operation': 'validation.tail', 'inputs_source': {
                    'path': path, 'sha256': hashlib.sha256(b'{}').hexdigest(), 'pointer': ''}}]
                source = root / 'request.json'
                source.write_bytes(runner.encoded(request))
                with self.assertRaisesRegex(ValueError, 'LOCAL_PATH_REQUIRED'):
                    runner.run(source, root / 'run')


if __name__ == '__main__':
    unittest.main()
