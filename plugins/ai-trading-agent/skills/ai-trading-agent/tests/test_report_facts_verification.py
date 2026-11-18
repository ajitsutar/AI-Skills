"""Projection integrity tests; synthetic retained claims are not helper replay."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import report_facts as rf


def encoded(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')


def source_bundle():
    inputs = {'contract': {'horizon_id': 'P7M'}, 'jobs': [
        {'id': 'fees', 'operation': 'ops.shortfall', 'inputs': {}},
        {'id': 'rejected', 'operation': 'risk.option', 'inputs': {}},
        {'id': 'nested', 'operation': 'ops.xirr', 'inputs': {}}]}
    result = {'input_sha256': rf.digest(inputs), 'implementation_sha256': rf.quant_hash(),
              'results': [
                  {'id': 'fees', 'operation': 'ops.shortfall', 'status': 'COMPUTED',
                   'result': {'fees': 2.75, 'total_shortfall': 9.25}},
                  {'id': 'rejected', 'operation': 'risk.option', 'status': 'REJECTED_INPUT',
                   'reason': 'PRIVATE_REJECTION_REASON', 'result': {'stale_price': 999}},
                  {'id': 'nested', 'operation': 'ops.xirr', 'status': 'COMPUTED',
                   'result': {'status': 'AMBIGUOUS_OR_NONCONVENTIONAL_CASHFLOWS',
                              'annual_xirr': None}}]}
    return {'input': inputs, 'result': result, 'result_sha256': rf.digest(result),
            'supplement': {'label': 'PRIVATE_SELECTED_TEXT', 'amount': 18.5}}


class ProjectionVerificationTests(unittest.TestCase):
    def setUp(self):
        self.bundle = source_bundle()
        self.raw = encoded(self.bundle)
        self.report = rf.project(self.raw, 'quant')
        self.custom = encoded({'facts': [
            {'pointer': '/supplement/amount', 'metric': 'Declared amount', 'unit': 'USD'},
            {'pointer': '/supplement/label', 'metric': 'Declared label'},
            {'pointer': '/absent', 'metric': 'Absent observation', 'horizon': 'P3D'}]})

    def verify(self, report, **options):
        return rf.verify_projection(self.raw, 'quant', encoded(report), **options)

    def test_unchanged_and_appended_custom_are_canonical(self):
        result = self.verify(self.report)
        self.assertEqual(result['status'], 'VERIFIED_PROJECTION')
        self.assertTrue(result['matches'])
        self.assertTrue(all(result['binding_matches'].values()))
        self.assertEqual(result['builtin_facts']['exact_match_count'], len(self.report['facts']))
        self.assertFalse(result['calculation_replayed'])
        appended = rf.project(self.raw, 'quant', self.custom)
        self.assertEqual(appended['facts'][:len(self.report['facts'])], self.report['facts'])
        verified = self.verify(appended, custom_raw=self.custom)
        self.assertTrue(verified['matches'])
        self.assertEqual(verified['custom_facts']['exact_match_count'], 3)
        # JSON formatting is irrelevant; the bound source bytes are not.
        self.assertTrue(rf.verify_projection(self.raw, 'quant',
                        json.dumps(appended, indent=4).encode(), self.custom)['matches'])

    def test_custom_only_projection_loses_all_canonical_facts(self):
        report = rf.project(self.raw, 'quant', self.custom)
        report['facts'] = [f for f in report['facts'] if f['semantic_mapping'] == 'CUSTOM_DECLARED_UNVERIFIED']
        result = self.verify(report, custom_raw=self.custom)
        self.assertEqual(result['status'], 'PROJECTION_MISMATCH')
        self.assertEqual(len(result['builtin_facts']['missing']), len(self.report['facts']))
        self.assertEqual(result['custom_facts']['exact_match_count'], 3)

    def test_numeric_unit_pointer_and_bool_tampering_are_detected(self):
        index = next(i for i, f in enumerate(self.report['facts']) if f['metric'] == 'Explicit fees')
        for field, value, expected_path in (
                ('value', 4.5, '/value'), ('unit', 'percentage', '/unit'),
                ('pointer', '/supplement/amount', '/source/pointer'), ('value', True, '/value')):
            with self.subTest(field=field, value=value):
                report = copy.deepcopy(self.report)
                target = report['facts'][index]
                if field == 'pointer':
                    target['source']['pointer'] = value
                else:
                    target[field] = value
                result = self.verify(report)
                self.assertFalse(result['matches'])
                self.assertEqual(result['builtin_facts']['altered'][0]['changed_fields'], [expected_path])

    def test_rejected_job_and_nested_noncomputation_cannot_be_dropped(self):
        for selected_pointer in ('/result/results/1/status', '/result/results/1/reason',
                                 '/result/results/2/result/status', '/result/results/2/result/annual_xirr'):
            with self.subTest(pointer=selected_pointer):
                report = copy.deepcopy(self.report)
                report['facts'] = [f for f in report['facts'] if f['source']['pointer'] != selected_pointer]
                result = self.verify(report)
                self.assertFalse(result['matches'])
                self.assertEqual(result['builtin_facts']['missing'][0]['pointer'], selected_pointer)
                self.assertNotIn('PRIVATE_REJECTION_REASON', json.dumps(result))

    def test_added_duplicate_reordered_and_relabelled_builtin_fail(self):
        added = copy.deepcopy(self.report)
        added['facts'].append(copy.deepcopy(added['facts'][0]))
        result = self.verify(added)
        self.assertEqual(len(result['builtin_facts']['added']), 1)
        reordered = copy.deepcopy(self.report)
        reordered['facts'].reverse()
        result = self.verify(reordered)
        self.assertFalse(result['matches'])
        self.assertFalse(result['facts_sequence_matches'])
        self.assertEqual(result['builtin_facts']['exact_match_count'], len(self.report['facts']))
        relabelled = copy.deepcopy(self.report)
        relabelled['facts'][0]['semantic_mapping'] = 'CUSTOM_DECLARED_UNVERIFIED'
        result = self.verify(relabelled)
        self.assertEqual(len(result['builtin_facts']['missing']), 1)
        self.assertEqual(len(result['custom_facts']['added']), 1)

    def test_foreign_original_bundle_and_source_bytes_do_not_verify(self):
        foreign = copy.deepcopy(self.bundle)
        # Even a source difference outside projected fields invalidates the binding.
        foreign['supplement']['amount'] += 1
        report = rf.project(encoded(foreign), 'quant')
        result = self.verify(report)
        self.assertFalse(result['binding_matches']['source_artifact_sha256'])
        self.assertTrue(result['builtin_facts']['altered'])
        result = rf.verify_projection(self.raw + b'\n', 'quant', encoded(self.report))
        self.assertFalse(result['matches'])

    def test_custom_binding_bytes_and_source_text_options_are_bound(self):
        report = rf.project(self.raw, 'quant', self.custom, include_source_text=True)
        self.assertTrue(self.verify(report, custom_raw=self.custom, include_source_text=True)['matches'])
        wrong_options = self.verify(report, custom_raw=self.custom)
        self.assertFalse(wrong_options['binding_matches']['source_text_exported'])
        self.assertTrue(wrong_options['custom_facts']['altered'])
        self.assertNotIn('PRIVATE_SELECTED_TEXT', json.dumps(wrong_options))
        changed = json.loads(self.custom)
        changed['facts'][0]['unit'] = 'EUR'
        wrong_custom = self.verify(report, custom_raw=encoded(changed), include_source_text=True)
        self.assertFalse(wrong_custom['binding_matches']['custom_bindings_sha256'])
        self.assertTrue(wrong_custom['custom_facts']['altered'])
        self.assertEqual(len(self.verify(report)['custom_facts']['added']), 3)
        empty = encoded({'facts': []})
        empty_report = rf.project(self.raw, 'quant', empty)
        self.assertTrue(self.verify(empty_report, custom_raw=empty)['matches'])
        self.assertFalse(self.verify(empty_report)['matches'])

    def test_adapter_semantics_kind_and_claimed_checks_are_bound(self):
        for field, value in (
                ('adapter_code_sha256', 'foreign-adapter'), ('adapter_version', 'future-adapter'),
                ('semantics_code_sha256', {}), ('kind', 'public-vqm'),
                ('checks', [{'calculation_replayed': True}]), ('extra_claim', 'authenticated')):
            with self.subTest(field=field):
                report = copy.deepcopy(self.report)
                report[field] = value
                result = self.verify(report)
                self.assertFalse(result['matches'])
                self.assertTrue(any(p.startswith('/' + field) for p in result['metadata_mismatch_paths']))

    def test_historical_schema_is_interpreted_without_current_replay(self):
        historical = copy.deepcopy(self.bundle)
        historical['result']['implementation_sha256'] = next(iter(rf.COMPATIBLE_QUANT_SCHEMAS))
        historical['result_sha256'] = rf.digest(historical['result'])
        raw = encoded(historical)
        report = rf.project(raw, 'quant')
        result = rf.verify_projection(raw, 'quant', encoded(report))
        self.assertTrue(result['matches'])
        checks = result['source_mapping_checks'][0]
        self.assertTrue(checks['known_historical_schema'])
        self.assertFalse(checks['code_mapping_matches'])
        self.assertFalse(checks['calculation_replayed'])
        self.assertFalse(result['calculation_replayed'])
        # An old adapter export remains a mismatch, even for a recognized source schema.
        report['adapter_code_sha256'] = 'historical-adapter'
        self.assertFalse(rf.verify_projection(raw, 'quant', encoded(report))['matches'])

    def test_unknown_schema_and_inconsistent_source_can_project_without_authentication(self):
        unknown = copy.deepcopy(self.bundle)
        unknown['result']['implementation_sha256'] = 'unrecognized-implementation'
        raw = encoded(unknown)  # Deliberately leaves the embedded result hash inconsistent.
        report = rf.project(raw, 'quant')
        result = rf.verify_projection(raw, 'quant', encoded(report))
        self.assertTrue(result['matches'])
        self.assertFalse(result['source_mapping_checks'][0]['semantics_mapping_known'])
        self.assertFalse(result['source_mapping_checks'][0]['embedded_result_hash_matches'])
        self.assertTrue(any(f['semantic_mapping'] == 'UNMAPPED' for f in report['facts']))

    def test_public_rejection_projection_is_verified_with_reason_retained(self):
        raw = encoded({'status': 'REJECTED_INPUT', 'reason': 'PRIVATE_PUBLIC_REASON',
                       'scores': [{'score': 100}]})
        report = rf.project(raw, 'public-vqm')
        result = rf.verify_projection(raw, 'public-vqm', encoded(report))
        self.assertTrue(result['matches'])
        report['facts'].pop()
        result = rf.verify_projection(raw, 'public-vqm', encoded(report))
        self.assertFalse(result['matches'])
        self.assertEqual(result['builtin_facts']['missing'][0]['pointer'], '/reason')

    def test_malformed_candidate_returns_diagnostic_but_invalid_source_raises(self):
        for raw in (b'not json', b'{"facts":[],"facts":[]}', b'{"facts":[NaN]}',
                    b'[]', b'{"facts":{}}', b'{"facts":[1]}'):
            with self.subTest(raw=raw):
                result = rf.verify_projection(self.raw, 'quant', raw)
                self.assertEqual(result['status'], 'INVALID_PROJECTION')
                self.assertFalse(result['matches'])
        with self.assertRaises(ValueError):
            rf.verify_projection(b'not json', 'quant', encoded(self.report))

    def test_cli_private_diagnostics_exit_codes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source, bindings, candidate = (folder / x for x in ('source.json', 'bindings.json', 'facts.json'))
            source.write_bytes(self.raw)
            bindings.write_bytes(self.custom)
            base = [sys.executable, '-B', str(ROOT / 'scripts/report_facts.py'), 'quant', str(source),
                    '--custom-bindings', str(bindings), '--include-source-text']
            projected = subprocess.run(base + ['--private-output', str(candidate)], capture_output=True, text=True)
            self.assertEqual(projected.returncode, 0, projected.stderr)
            diagnostic = folder / 'verification.json'
            command = base + ['--verify-projection', str(candidate), '--private-output', str(diagnostic)]
            verified = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(verified.stdout, '')
            self.assertTrue(json.loads(diagnostic.read_bytes())['matches'])
            saved = diagnostic.read_bytes()
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)
            self.assertEqual(diagnostic.read_bytes(), saved)
            changed = json.loads(candidate.read_bytes())
            changed['facts'].pop(0)
            candidate.write_bytes(encoded(changed))
            mismatch = folder / 'mismatch.json'
            checked = subprocess.run(base + ['--verify-projection', str(candidate), '--private-output', str(mismatch)],
                                     capture_output=True, text=True)
            self.assertEqual(checked.returncode, 1)
            self.assertEqual(checked.stdout, '')
            self.assertEqual(checked.stderr, '')
            self.assertEqual(json.loads(mismatch.read_bytes())['status'], 'PROJECTION_MISMATCH')
            candidate.write_bytes(b'not json')
            invalid = subprocess.run(base + ['--verify-projection', str(candidate), '--format', 'markdown',
                                            '--private-output', str(folder / 'invalid.md')], capture_output=True, text=True)
            self.assertEqual(invalid.returncode, 1)
            self.assertIn('INVALID_PROJECTION', (folder / 'invalid.md').read_text())
            self.assertNotIn('PRIVATE_', saved.decode())


if __name__ == '__main__':
    unittest.main()
