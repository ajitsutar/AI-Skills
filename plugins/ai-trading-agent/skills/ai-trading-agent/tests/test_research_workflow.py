"""Independent workflow tests using synthetic sources, never evaluation fixtures."""
import copy
import functools
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import quant_report as qr
import quant_workbench as qw
import report_facts as rf
import research_workflow as workflow


def encode(value):
    return qr.encoded(value)


def assumed(value, reason='Synthetic analyst scenario'):
    return {'$assumption': value, 'reason': reason}


def selected(source_id, pointer=''):
    return {'$source': {'id': source_id, 'pointer': pointer}}


def contract():
    return {'prompt': 'Measure uncertainty in this synthetic series.',
            'purpose': 'offline test', 'base_currency': 'USD', 'horizon_id': 'P7M',
            'as_of': '2027-07-01T00:00:00Z'}


def plan_for(sources, jobs, claims=None, requirements=None):
    """sources maps id -> (relative path, bytes, explicit role)."""
    return {'schema_version': 1, 'network_mode': 'offline', 'contract': contract(),
            'sources': [{'id': sid, 'path': name, 'sha256': workflow.sha(raw),
                         'format': 'json', 'role': role}
                        for sid, (name, raw, role) in sources.items()],
            'jobs': jobs, 'claims': claims or [], 'requirements': requirements or []}


def base_case():
    values = {'returns': [.021, -.007, .019, .002, .011, -.004],
              'cash_rate': .041, 'label': 'SYNTHETIC_PRIVATE_LABEL'}
    sources = {'sample': ('sample.json', encode(values), 'supplied_return_series')}
    plan = plan_for(sources, [{'id': 'hac', 'operation': 'validation.hac',
                              'arguments': {'returns': selected('sample', '/returns'),
                                            'lags': assumed(1, 'One-lag sensitivity scenario')}}],
                    claims=[{'id': 'mean', 'job_id': 'hac', 'pointer': '/result/mean'}],
                    requirements=[{'id': 'uncertainty', 'question': 'Compute serial-dependence-aware uncertainty',
                                   'job_ids': ['hac'], 'expected_operations': ['validation.hac']}])
    return plan, sources


def build(plan, sources):
    by_path = {name: raw for name, raw, _ in sources.values()}
    return workflow.build(encode(plan), by_path.__getitem__)


def write_artifacts(folder, artifacts):
    folder.mkdir()
    for name, raw in artifacts.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)


def resign(folder):
    """Recompute the editable manifest, simulating a self-consistent alteration."""
    path = folder / 'receipt.json'
    receipt = rf.strict_json(path.read_bytes())
    receipt['artifacts'] = {name: workflow.sha((folder / name).read_bytes())
                            for name in receipt['artifacts']}
    path.write_bytes(encode(receipt))


def regenerate_outer_report(folder):
    result = rf.strict_json((folder / 'result.json').read_bytes())
    reports = {}
    for index, job in enumerate(result['jobs']):
        quant = folder / f'jobs/{index:04d}/quant/report.md'
        if quant.is_file():
            reports[job['id']] = quant.read_text(encoding='utf-8')
        elif job['operation'] in ('report.quant', 'report.public_vqm') and job['status'] == 'COMPUTED':
            reports[job['id']] = rf.markdown(job['result']['facts'])
    (folder / 'report.md').write_bytes(workflow.render(result, reports))


class ResearchWorkflowTests(unittest.TestCase):
    def test_source_bindings_assumptions_and_unused_fields_are_retained(self):
        plan, sources = base_case()
        artifacts = build(plan, sources)
        result = rf.strict_json(artifacts['result.json'])
        self.assertEqual(result['jobs'][0]['status'], 'COMPUTED')
        self.assertAlmostEqual(result['claims'][0]['actual_value'], .007)
        self.assertEqual(result['claims'][0]['status'], 'PROJECTED')
        arguments = rf.strict_json(artifacts['jobs/0000/arguments.json'])
        self.assertEqual(arguments, {'returns': [.021, -.007, .019, .002, .011, -.004], 'lags': 1})
        bindings = result['bindings'][0]['arguments']
        source = next(b for b in bindings if b['kind'] == 'SOURCE')
        assumption = next(b for b in bindings if b['kind'] == 'ASSUMPTION')
        self.assertEqual(source['source_pointer'], '/returns')
        self.assertEqual(source['source_role'], 'supplied_return_series')
        self.assertEqual(source['source_sha256'], workflow.sha(sources['sample'][1]))
        self.assertEqual(source['selected_value_sha256'], qw.digest(arguments['returns']))
        self.assertEqual(assumption['value'], 1)
        self.assertEqual(assumption['reason'], 'One-lag sensitivity scenario')
        self.assertIn({'source_id': 'sample', 'pointer': '/cash_rate'}, result['unused_source_pointers'])
        self.assertFalse(any(x['pointer'].startswith('/returns') for x in result['unused_source_pointers']))

    def test_literal_is_not_silently_treated_as_observation_or_assumption(self):
        plan, sources = base_case()
        plan['jobs'][0]['arguments']['lags'] = 1
        result = rf.strict_json(build(plan, sources)['result.json'])
        self.assertEqual(result['jobs'][0]['status'], 'UNRESOLVED_INPUT_OR_FAILED')
        self.assertIn('UNBOUND_LITERAL', result['jobs'][0]['reason'])
        self.assertEqual(result['coverage'][0]['status'], 'PARTIAL_OR_FAILED')
        self.assertEqual(result['claims'][0]['status'], 'UNRESOLVED_POINTER')

    def test_canonical_facts_preserve_scalars_and_append_custom_without_replacement(self):
        original = {'results': [{'id': 'synthetic', 'operation': 'test.unknown', 'status': 'COMPUTED',
                                'result': {'amount': 12.125, 'zero': 0, 'flag': False,
                                           'unknown': None, 'decimal_text': '19.750', 'label': 'Private label'}}]}
        customs = {'facts': [{'pointer': '/results/0/result/amount', 'metric': 'Declared value', 'unit': 'USD'},
                             {'pointer': '/missing', 'metric': 'Missing source'}]}
        sources = {'original': ('original.json', encode(original), 'retained_helper_output'),
                   'custom': ('custom.json', encode(customs), 'analyst_fact_declarations')}
        plan = plan_for(sources, [{'id': 'projection', 'operation': 'report.quant',
                                  'arguments': {'source_id': assumed('original'),
                                                'custom_source_id': assumed('custom'),
                                                'include_source_text': assumed(True)}}])
        result = rf.strict_json(build(plan, sources)['result.json'])
        projected = result['jobs'][0]['result']
        expected = rf.project(sources['original'][1], 'quant', include_source_text=True)
        facts = projected['facts']['facts']
        self.assertEqual(facts[:len(expected['facts'])], expected['facts'])
        self.assertEqual(len(facts), len(expected['facts']) + 2)
        self.assertTrue(projected['projection_verification']['matches'])
        for fact in facts:
            if fact['missingness'] is None:
                value = rf.pointer(original, fact['source']['pointer'])
                self.assertEqual(fact['value'], value)
                self.assertIs(type(fact['value']), type(value))
        self.assertEqual(facts[-1]['missingness'], 'absent')
        self.assertEqual(facts[-1]['semantic_mapping'], 'CUSTOM_DECLARED_UNVERIFIED')
        self.assertEqual(result['unused_source_pointers'], [])

    def test_nested_invalid_forward_observation_is_retained_beneath_computed_wrapper(self):
        document = {'as_of': '2027-07-01T00:00:00Z', 'fictional': True,
                    'protocol': {'start': '2027-04-01T00:00:00Z', 'end': '2027-09-01T00:00:00Z',
                                 'frozen_at': '2027-03-01T00:00:00Z', 'minimum_observations': 4},
                    'observations': [{'id': 'old-row', 'decision_at': '2027-03-10T12:00:00Z',
                                      'outcome_at': '2027-03-11T12:00:00Z', 'available_at': '2027-03-09T12:00:00Z',
                                      'data_kind': 'synthetic', 'champion_net_return': .01, 'challenger_net_return': .02}]}
        sources = {'study': ('study.json', encode(document), 'synthetic_study')}
        plan = plan_for(sources, [{'id': 'forward', 'operation': 'validation.forward_observations',
                                  'arguments': {'document': selected('study')}}])
        artifacts = build(plan, sources)
        job = rf.strict_json(artifacts['result.json'])['jobs'][0]
        self.assertEqual(job['status'], 'COMPUTED')
        self.assertEqual(job['result']['rows'][0]['status'], 'NOT_ADMISSIBLE')
        self.assertIn('BEFORE_PROTOCOL_WINDOW', job['result']['rows'][0]['reasons'])
        self.assertIn('AVAILABLE_BEFORE_OUTCOME', job['result']['rows'][0]['reasons'])
        self.assertEqual(job['result']['admissible_declared_forward_count'], 0)
        self.assertEqual(job['result']['additional_admissible_observations_needed'], 4)
        self.assertIn({'pointer': '/rows/0/status', 'value': 'NOT_ADMISSIBLE'}, job['nested_states'])
        self.assertIn(b'NOT_ADMISSIBLE', artifacts['report.md'])

    def test_wrong_operation_and_contradictory_claim_are_visible(self):
        plan, sources = base_case()
        plan['requirements'][0]['expected_operations'] = ['research.inventory_evidence']
        plan['claims'][0]['assertion'] = .75
        result = rf.strict_json(build(plan, sources)['result.json'])
        self.assertEqual(result['status'], 'DIAGNOSTICS_PRESENT')
        self.assertEqual(result['coverage'][0]['status'], 'OPERATION_MISMATCH')
        self.assertEqual(result['coverage'][0]['missing_expected_operations'], ['research.inventory_evidence'])
        self.assertEqual(result['claims'][0]['status'], 'CONTRADICTED')
        self.assertAlmostEqual(result['claims'][0]['actual_value'], .007)

    def test_failed_and_unsupported_jobs_are_retained_next_to_success(self):
        plan, sources = base_case()
        plan['jobs'].extend([
            {'id': 'bad', 'operation': 'validation.hac', 'arguments': {'returns': assumed([]), 'lags': assumed(1)}},
            {'id': 'unknown', 'operation': 'custom.not_installed', 'arguments': {}},
            {'id': 'missing', 'operation': 'validation.hac', 'arguments': {'returns': selected('sample', '/absent')}}])
        result = rf.strict_json(build(plan, sources)['result.json'])
        self.assertEqual([j['id'] for j in result['jobs']], ['hac', 'bad', 'unknown', 'missing'])
        self.assertEqual(result['jobs'][1]['status'], 'REJECTED_INPUT')
        self.assertTrue(result['jobs'][1]['reason'])
        self.assertEqual(result['jobs'][2]['status'], 'UNSUPPORTED_OPERATION')
        self.assertEqual(result['jobs'][3]['status'], 'UNRESOLVED_INPUT_OR_FAILED')
        self.assertEqual(result['status'], 'DIAGNOSTICS_PRESENT')

    def test_source_hash_and_path_escape_fail_before_reading_unapproved_paths(self):
        plan, sources = base_case()
        for path in ('../outside.json', '/absolute.json', 'folder/../../outside', 'C:/outside.json',
                     '\\\\host\\share', 'https://example.invalid/data', 'folder//data.json'):
            with self.subTest(path=path):
                changed = copy.deepcopy(plan)
                changed['sources'][0]['path'] = path
                reader = mock.Mock(side_effect=AssertionError('Must not read escaped path'))
                with self.assertRaises(ValueError):
                    workflow.build(encode(changed), reader)
                reader.assert_not_called()
        changed = copy.deepcopy(plan)
        changed['sources'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            build(changed, sources)

    def test_source_bound_contract_operation_runs_and_reports_unknown_acquisition(self):
        doc = {'allowlist': [], 'sources': [], 'as_of': '2027-07-01T00:00:00Z', 'checks': []}
        sources = {'audit': ('audit.json', encode(doc), 'declared_evidence_audit')}
        plan = plan_for(sources, [{'id': 'audit', 'operation': 'research.inventory_evidence',
                                  'arguments': {'document': selected('audit')}}])
        result = rf.strict_json(build(plan, sources)['result.json'])
        self.assertEqual(result['jobs'][0]['status'], 'COMPUTED')
        acquisition = result['jobs'][0]['result']['result']['acquisition']
        self.assertIsNone(acquisition['declared_complete_failure_count'])
        self.assertEqual(acquisition['completeness'], 'UNKNOWN_OR_PARTIAL')

    def test_no_network_or_external_process_during_build_and_verify(self):
        plan, sources = base_case()
        with mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden')) as connect, \
                mock.patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden')) as connection, \
                mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('External process forbidden')) as process:
            artifacts = build(plan, sources)
            with tempfile.TemporaryDirectory() as directory:
                folder = Path(directory) / 'run'
                write_artifacts(folder, artifacts)
                checked = workflow.verify(folder)
                self.assertEqual(checked['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            connect.assert_not_called()
            connection.assert_not_called()
            process.assert_not_called()
        result = rf.strict_json(artifacts['result.json'])
        self.assertEqual(result['network_requests_performed'], 0)
        self.assertFalse(result['source_authenticity_verified'])

    def test_run_requires_new_private_output_and_cli_schema_run_verify(self):
        plan, sources = base_case()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'plan.json'
            source.write_bytes(encode(plan))
            for name, raw, _ in sources.values():
                (root / name).write_bytes(raw)
            output = root / 'direct'
            workflow.run(source, output)
            with self.assertRaises(ValueError):
                workflow.run(source, output)
            with self.assertRaises(ValueError):
                workflow.run(source, ROOT / 'forbidden-test-output')
            command = [sys.executable, '-B', str(ROOT / 'scripts/research_workflow.py')]
            schema = subprocess.run(command + ['schema'], capture_output=True, text=True)
            self.assertEqual(schema.returncode, 0, schema.stderr)
            self.assertIn('report.quant', json.loads(schema.stdout)['additional_operations'])
            created = subprocess.run(command + ['run', str(source), '--private-output-dir', str(root / 'cli')],
                                     capture_output=True, text=True)
            self.assertEqual(created.returncode, 0, created.stderr)
            self.assertEqual(created.stdout.strip(), 'COMPUTED')
            verified = subprocess.run(command + ['verify', str(root / 'cli')], capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assertEqual(verified.stdout.strip(), 'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            self.assertNotIn('SYNTHETIC_PRIVATE_LABEL', created.stdout + verified.stdout)

    def test_manifest_hash_tampering_and_resigned_false_claim_are_rejected(self):
        plan, sources = base_case()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'run'
            write_artifacts(folder, build(plan, sources))
            report = folder / 'report.md'
            report.write_bytes(report.read_bytes() + b'\nUnsupported conclusion.\n')
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH_MISMATCH'):
                workflow.verify(folder)
            resign(folder)
            with self.assertRaisesRegex(ValueError, 'CANONICAL_REPORT_MISMATCH'):
                workflow.verify(folder)

    def test_resigned_manifest_does_not_hide_result_or_source_mutation(self):
        plan, sources = base_case()
        with tempfile.TemporaryDirectory() as directory:
            for which in ('result', 'source'):
                with self.subTest(which=which):
                    folder = Path(directory) / which
                    write_artifacts(folder, build(plan, sources))
                    if which == 'result':
                        result = rf.strict_json((folder / 'result.json').read_bytes())
                        result['jobs'][0]['result']['mean'] += .1
                        (folder / 'result.json').write_bytes(encode(result))
                        regenerate_outer_report(folder)
                    else:
                        (folder / 'sources/sample.json').write_bytes(encode({'returns': [1, 2, 3]}))
                    resign(folder)
                    with self.assertRaises(ValueError):
                        workflow.verify(folder)

    def test_resigned_manifest_cannot_replace_retained_arguments(self):
        plan, sources = base_case()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'run'
            write_artifacts(folder, build(plan, sources))
            (folder / 'jobs/0000/arguments.json').write_bytes(encode({'returns': [7, 8, 9], 'lags': 0}))
            resign(folder)
            with self.assertRaises(ValueError):
                workflow.verify(folder)

    def test_independently_valid_foreign_quant_run_cannot_replace_selected_job(self):
        plan, sources = base_case()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'run'
            write_artifacts(folder, build(plan, sources))
            foreign = {'schema_version': 1, 'contract': contract(),
                       'jobs': [{'id': 'hac', 'operation': 'validation.hac',
                                 'inputs': {'returns': [.5, .4, -.2, .3, .1], 'lags': 1}}]}
            replacement = qr.build(encode(foreign), lambda *_: None)
            for name, raw in replacement.items():
                (folder / 'jobs/0000/quant' / name).write_bytes(raw)
            self.assertEqual(qr.verify(folder / 'jobs/0000/quant')['status'], 'REPLAY_AND_REPORT_MATCH')
            regenerate_outer_report(folder)
            resign(folder)
            with self.assertRaises(ValueError):
                workflow.verify(folder)

    def test_report_projection_values_are_exact_not_tolerant_replay_numbers(self):
        original = {'results': [{'id': 'one', 'operation': 'unknown', 'status': 'COMPUTED',
                                'result': {'value': .021}}]}
        sources = {'original': ('original.json', encode(original), 'retained_helper_output')}
        plan = plan_for(sources, [{'id': 'projection', 'operation': 'report.quant',
                                  'arguments': {'source_id': assumed('original')}}])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'run'
            write_artifacts(folder, build(plan, sources))
            result = rf.strict_json((folder / 'result.json').read_bytes())
            fact = next(f for f in result['jobs'][0]['result']['facts']['facts'] if f['source']['pointer'].endswith('/value'))
            fact['value'] += 5e-10
            (folder / 'result.json').write_bytes(encode(result))
            regenerate_outer_report(folder)
            resign(folder)
            with self.assertRaises(ValueError):
                workflow.verify(folder)

    def test_copied_contract_and_assumption_receipts_are_exact(self):
        plan, sources = base_case()
        plan['contract']['declared_capital'] = 7_000_000_000
        with tempfile.TemporaryDirectory() as directory:
            for changed in ('contract', 'assumption'):
                with self.subTest(changed=changed):
                    folder = Path(directory) / changed
                    write_artifacts(folder, build(plan, sources))
                    result = rf.strict_json((folder / 'result.json').read_bytes())
                    if changed == 'contract':
                        # Relative numerical tolerances must not alter copied source terms.
                        result['contract']['declared_capital'] += 500
                    else:
                        item = next(b for b in result['bindings'][0]['arguments'] if b['kind'] == 'ASSUMPTION')
                        item['value'] += 5e-10
                    (folder / 'result.json').write_bytes(encode(result))
                    regenerate_outer_report(folder)
                    resign(folder)
                    with self.assertRaises(ValueError):
                        workflow.verify(folder)

    def test_claim_value_is_exactly_bound_to_retained_result(self):
        plan, sources = base_case()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'run'
            write_artifacts(folder, build(plan, sources))
            result = rf.strict_json((folder / 'result.json').read_bytes())
            result['claims'][0]['actual_value'] += 5e-10
            (folder / 'result.json').write_bytes(encode(result))
            regenerate_outer_report(folder)
            resign(folder)
            with self.assertRaises(ValueError):
                workflow.verify(folder)

    def test_tolerant_quant_replay_does_not_compare_claim_digest_to_new_runtime(self):
        plan, sources = base_case()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'run'
            write_artifacts(folder, build(plan, sources))
            original = qw.OPERATIONS['validation.hac']
            @functools.wraps(original)
            def numerically_equivalent(*args, **kwargs):
                value = original(*args, **kwargs)
                value['mean'] += 5e-10
                return value
            with mock.patch.dict(qw.OPERATIONS, {'validation.hac': numerically_equivalent}):
                self.assertEqual(qr.verify(folder / 'jobs/0000/quant')['status'], 'REPLAY_AND_REPORT_MATCH')
                self.assertEqual(workflow.verify(folder)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')

    def test_within_tolerance_outer_value_must_still_match_retained_quant_bundle_exactly(self):
        plan, sources = base_case()
        plan['claims'] = []
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'run'
            write_artifacts(folder, build(plan, sources))
            result = rf.strict_json((folder / 'result.json').read_bytes())
            result['jobs'][0]['result']['mean'] += 5e-10
            (folder / 'result.json').write_bytes(encode(result))
            regenerate_outer_report(folder)
            resign(folder)
            with self.assertRaises(ValueError):
                workflow.verify(folder)

    def test_implementation_identity_includes_transitive_contract_dependencies(self):
        original_read_bytes, original_read_text = Path.read_bytes, Path.read_text
        original_hash = workflow.implementation_hash()
        # These modules execute under research.inventory_evidence or fixed-exit routing.
        for name in ('handoff_report.py', 'research_handoff.py', 'research_report_checks.py',
                     'horizon_review.py', 'trading_calendar.py', 'cash_benchmark.py'):
            with self.subTest(module=name):
                target = ROOT / 'scripts' / name
                def read_bytes(path):
                    raw = original_read_bytes(path)
                    return raw + b'\n# test-only dependency drift\n' if path == target else raw
                def read_text(path, *args, **kwargs):
                    text = original_read_text(path, *args, **kwargs)
                    return text + '\n# test-only dependency drift\n' if path == target else text
                with mock.patch.object(Path, 'read_bytes', read_bytes), mock.patch.object(Path, 'read_text', read_text):
                    self.assertNotEqual(workflow.implementation_hash(), original_hash)


if __name__ == '__main__':
    unittest.main()
