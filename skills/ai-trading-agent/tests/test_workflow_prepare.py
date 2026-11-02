"""Generic request preparation and verified, literal answer projections."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(os.environ.get('WORKFLOW_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
import report_facts
import research_workflow as workflow


def request():
    return {'schema_version': 1,
            'contract': {'prompt': 'Assess these synthetic comparison probabilities.',
                         'purpose': 'offline generic test', 'base_currency': 'USD',
                         'horizon_id': 'P13M', 'as_of': '2034-06-03T00:00:00Z',
                         'declared_scenario': {'capital': 8_765_432.125, 'observed': False}},
            'jobs': [{'id': 'comparison/a~b', 'operation': 'validation.holm',
                      'inputs': {'p_values': {'first': .0037, 'second': .034, 'third': .217}}}],
            'requirements': [{'id': 'correction', 'question': 'Apply the declared comparison correction',
                              'job_ids': ['comparison/a~b'], 'expected_operations': ['validation.holm']},
                             {'id': 'unavailable', 'question': 'Acquire missing observations',
                              'job_ids': [], 'reason': 'Offline bytes were not supplied'}],
            'claims': [{'id': 'adjusted', 'job_id': 'comparison/a~b', 'pointer': '/result/trials/first/holm_p'},
                       {'id': 'default', 'job_id': 'comparison/a~b', 'pointer': '/result/alpha',
                        'assertion': .05}]}


def write_artifacts(directory, artifacts):
    directory.mkdir()
    for name, raw in artifacts.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def resign_changed_result(directory, result):
    """Keep report and manifest consistent, exposing deeper provenance checks."""
    (directory / 'result.json').write_bytes(workflow.encode(result))
    reports = {job['id']: (directory / f'jobs/{index:04d}/quant/report.md').read_text(encoding='utf-8')
               for index, job in enumerate(result['jobs'])}
    (directory / 'report.md').write_bytes(workflow.render(result, reports))
    receipt_path = directory / 'receipt.json'
    receipt = report_facts.strict_json(receipt_path.read_bytes())
    receipt['artifacts'] = {name: workflow.sha((directory / name).read_bytes()) for name in receipt['artifacts']}
    receipt_path.write_bytes(workflow.encode(receipt))


class WorkflowPrepareTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(os.environ.get('WORKFLOW_TEST_SCRATCH', ROOT.parents[1] / 'workflow-usability-checks'))
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix='prepare-', dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def prepared(self, document=None):
        raw = workflow.encode(request() if document is None else document)
        artifacts = workflow.prepare_artifacts(raw, lambda *_: self.fail('Unexpected source read'),
                                               'Caller-declared synthetic request')
        directory = self.directory / 'prepared'
        write_artifacts(directory, artifacts)
        return directory, artifacts

    def test_original_bytes_contract_inputs_requirements_and_claims_are_preserved(self):
        document = request()
        raw = b'\xef\xbb\xbf' + json.dumps(document, ensure_ascii=False).encode('utf-8')
        artifacts = workflow.prepare_artifacts(raw, lambda *_: None, 'Explicit synthetic request')
        self.assertEqual(artifacts['original-request.json'], raw)
        plan = report_facts.strict_json(artifacts['plan.json'])
        for field in ('contract', 'requirements', 'claims'):
            self.assertEqual(workflow.encode(plan[field]), workflow.encode(document[field]))
        self.assertEqual(plan['sources'][0]['sha256'], workflow.sha(raw))
        self.assertEqual(plan['sources'][0]['role'], 'Explicit synthetic request')
        self.assertEqual(plan['jobs'][0]['arguments'],
                         {'$source': {'id': 'request', 'pointer': '/jobs/0/inputs'}})
        built = workflow.build(artifacts['plan.json'], artifacts.__getitem__)
        supplied = report_facts.strict_json(built['jobs/0000/arguments.json'])
        self.assertEqual(workflow.encode(supplied), workflow.encode(document['jobs'][0]['inputs']))
        self.assertNotIn('alpha', supplied)
        prepared = report_facts.strict_json(built['jobs/0000/quant/prepared.json'])
        self.assertEqual(prepared['jobs'][0]['inputs']['alpha'], .05)
        bindings = report_facts.strict_json(built['jobs/0000/quant/bindings.json'])
        self.assertEqual(bindings[0]['defaults_used'], {'alpha': .05})
        result = report_facts.strict_json(built['result.json'])
        self.assertEqual(result['jobs'][0]['status'], 'COMPUTED')
        self.assertEqual(result['claims'][0]['status'], 'PROJECTED')
        self.assertEqual(result['claims'][1]['status'], 'MATCH')
        self.assertEqual(result['unused_source_pointers'], [])
        self.assertEqual(result['coverage'][1]['status'], 'UNADDRESSED')
        self.assertEqual(result['status'], 'DIAGNOSTICS_PRESENT')

    def test_explicit_parameter_is_never_replaced_with_helper_default(self):
        document = request()
        document['jobs'][0]['inputs']['alpha'] = .07125
        _, artifacts = self.prepared(document)
        built = workflow.build(artifacts['plan.json'], artifacts.__getitem__)
        bindings = report_facts.strict_json(built['jobs/0000/quant/bindings.json'])
        self.assertEqual(bindings[0]['defaults_used'], {})
        self.assertEqual(report_facts.strict_json(built['jobs/0000/arguments.json'])['alpha'], .07125)

    def test_source_pointer_hash_binding_copies_exact_bytes_and_roles(self):
        document = request()
        source_raw = b'{"a/b":{"x~y":{"p_values":{"first":0.0021,"second":0.031,"third":0.23},"alpha":0.0375}},"unselected":17}\n'
        job = document['jobs'][0]
        del job['inputs']
        job['inputs_source'] = {'path': 'raw observations.json', 'sha256': workflow.sha(source_raw),
                                'pointer': '/a~1b/x~0y'}
        reads = []
        def reader(path, index):
            reads.append((path, index))
            return source_raw
        artifacts = workflow.prepare_artifacts(workflow.encode(document), reader, 'Explicit test request',
                                               {'raw observations.json': 'Retained synthetic observations'})
        self.assertEqual(reads, [('raw observations.json', 0)])
        self.assertEqual(artifacts['inputs/source-0000.json'], source_raw)
        plan = report_facts.strict_json(artifacts['plan.json'])
        self.assertEqual(plan['jobs'][0]['arguments'],
                         {'$source': {'id': 'input-0000', 'pointer': '/a~1b/x~0y'}})
        self.assertEqual(plan['sources'][1]['role'], 'Retained synthetic observations')
        built = workflow.build(artifacts['plan.json'], artifacts.__getitem__)
        self.assertEqual(report_facts.strict_json(built['jobs/0000/arguments.json']),
                         {'p_values': {'first': .0021, 'second': .031, 'third': .23}, 'alpha': .0375})
        self.assertEqual(report_facts.strict_json(built['result.json'])['unused_source_pointers'],
                         [{'source_id': 'input-0000', 'pointer': '/unselected'}])

    def test_mixed_inline_and_external_jobs_keep_order_and_run_without_original_files(self):
        document = request()
        second = {'id': 'external', 'operation': 'validation.holm',
                  'inputs_source': {'path': 'sample.json', 'sha256': workflow.sha(b'{"p_values":{"one":0.17,"two":0.43}}'),
                                    'pointer': ''}}
        document['jobs'].append(second)
        original = self.directory / 'request.json'
        original.write_bytes(workflow.encode(document))
        source = self.directory / 'sample.json'
        source.write_bytes(b'{"p_values":{"one":0.17,"two":0.43}}')
        prepared = self.directory / 'prepared'
        workflow.prepare(original, prepared, 'Explicit original request', {'sample.json': 'Synthetic input'})
        original.unlink()
        source.unlink()
        output = self.directory / 'run'
        result = workflow.run(prepared / 'plan.json', output)
        self.assertEqual([job['id'] for job in result['jobs']], ['comparison/a~b', 'external'])
        self.assertEqual([job['status'] for job in result['jobs']], ['COMPUTED', 'COMPUTED'])
        self.assertEqual(workflow.verify(output)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')

    def test_missing_or_mismatched_roles_fail_before_source_read(self):
        document = request()
        job = document['jobs'][0]
        del job['inputs']
        job['inputs_source'] = {'path': 'expected.json', 'sha256': 'a' * 64, 'pointer': ''}
        for role, roles in [(None, {'expected.json': 'test'}), ('', {'expected.json': 'test'}),
                            ('request', {}), ('request', {'typo.json': 'test'}),
                            ('request', {'expected.json': ''}),
                            ('request', {'expected.json': 'test', 'extra.json': 'extra'})]:
            with self.subTest(role=role, roles=roles):
                reader = mock.Mock(side_effect=AssertionError('Must not read'))
                with self.assertRaises(ValueError):
                    workflow.prepare_artifacts(workflow.encode(document), reader, role, roles)
                reader.assert_not_called()

    def test_source_hash_pointer_and_whole_input_object_are_validated(self):
        for source, pointer, digest in [(b'{"inputs":{}}', '/inputs', '0' * 64),
                                        (b'{"inputs":{}}', '/absent', None),
                                        (b'{"inputs":false}', '/inputs', None)]:
            with self.subTest(pointer=pointer, source=source):
                document = request()
                job = document['jobs'][0]
                del job['inputs']
                job['inputs_source'] = {'path': 'source.json', 'pointer': pointer,
                                        'sha256': digest or workflow.sha(source)}
                with self.assertRaises((ValueError, KeyError)):
                    workflow.prepare_artifacts(workflow.encode(document), lambda *_: source,
                                               'Original', {'source.json': 'Declared source'})

    def test_no_unsupported_fields_operations_or_override_languages_are_dropped(self):
        original = request()
        documents = []
        extra_top = copy.deepcopy(original)
        extra_top['override'] = {'alpha': .8}
        documents.append(extra_top)
        extra_job = copy.deepcopy(original)
        extra_job['jobs'][0]['overrides'] = {'alpha': .8}
        documents.append(extra_job)
        unknown_op = copy.deepcopy(original)
        unknown_op['jobs'][0]['operation'] = 'custom.import'
        documents.append(unknown_op)
        online = copy.deepcopy(original)
        online['network_mode'] = 'online'
        documents.append(online)
        for document in documents:
            with self.subTest(document=document):
                with self.assertRaises(ValueError):
                    workflow.prepare_artifacts(workflow.encode(document), lambda *_: None, 'Declared request')

    def test_missing_checklists_stay_empty_and_invalid_inputs_remain_rejected(self):
        document = request()
        del document['requirements']
        del document['claims']
        document['jobs'][0]['inputs']['extra_parameter'] = {'$expression': 'run something'}
        _, artifacts = self.prepared(document)
        built = workflow.build(artifacts['plan.json'], artifacts.__getitem__)
        self.assertEqual(report_facts.strict_json(built['jobs/0000/arguments.json']), document['jobs'][0]['inputs'])
        result = report_facts.strict_json(built['result.json'])
        self.assertEqual(result['coverage'], [])
        self.assertEqual(result['claims'], [])
        self.assertEqual(result['jobs'][0]['status'], 'REJECTED_INPUT')
        self.assertEqual(result['status'], 'DIAGNOSTICS_PRESENT')

    def test_prepared_contract_jobs_requirements_claims_and_sources_cannot_drift(self):
        _, artifacts = self.prepared()
        plan = report_facts.strict_json(artifacts['plan.json'])
        for field in ('contract', 'jobs', 'requirements', 'claims', 'sources'):
            changed = copy.deepcopy(plan)
            if field == 'contract':
                changed[field]['horizon_id'] = 'P99Y'
            elif field == 'jobs':
                changed[field][0]['arguments'] = {'$assumption': {'p_values': [.99]}, 'reason': 'Changed'}
            elif field == 'sources':
                changed[field][0]['path'] = 'renamed.json'
            else:
                changed[field] = []
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                workflow.build(workflow.encode(changed), artifacts.__getitem__)

    def test_summary_is_deterministic_exact_and_preserves_unresolved_literals(self):
        document = request()
        document['jobs'].append({'id': 'calendar', 'operation': 'evidence.event_window',
                                 'inputs': {'event': 'unknown timing', 'start': '2034-01', 'end': '2034-04'}})
        document['claims'].append({'id': 'missing-window', 'job_id': 'calendar', 'pointer': '/result/window'})
        prepared, _ = self.prepared(document)
        output = self.directory / 'run'
        result = workflow.run(prepared / 'plan.json', output)
        summary = workflow.summarize(output)
        self.assertEqual(workflow.encode(summary), workflow.encode(workflow.summarize(output)))
        for field in ('contract', 'coverage', 'claims', 'sources', 'bindings', 'unused_source_pointers'):
            self.assertEqual(workflow.encode(summary[field]), workflow.encode(result[field]))
        self.assertEqual(summary['result_sha256'], workflow.sha((output / 'result.json').read_bytes()))
        self.assertEqual(summary['claims'][-1]['status'], 'PROJECTED')
        self.assertIsNone(summary['claims'][-1]['actual_value'])
        self.assertEqual(summary['jobs'][1]['status'], 'COMPUTED')
        self.assertIn({'pointer': '/status', 'value': 'UNRESOLVED'}, summary['jobs'][1]['nested_states'])
        self.assertIn('/window', summary['jobs'][1]['null_result_pointers'])
        self.assertNotIn('result', summary['jobs'][0])
        self.assertEqual(summary['execution_gates'], [])

    def test_summary_refuses_tampered_report_even_after_manifest_is_resigned(self):
        prepared, _ = self.prepared()
        output = self.directory / 'run'
        workflow.run(prepared / 'plan.json', output)
        report = output / 'report.md'
        report.write_bytes(report.read_bytes() + b'\nInvented assertion.\n')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH_MISMATCH'):
            workflow.summarize(output)
        receipt_path = output / 'receipt.json'
        receipt = report_facts.strict_json(receipt_path.read_bytes())
        receipt['artifacts']['report.md'] = workflow.sha(report.read_bytes())
        receipt_path.write_bytes(workflow.encode(receipt))
        with self.assertRaisesRegex(ValueError, 'CANONICAL_REPORT_MISMATCH'):
            workflow.summarize(output)

    def test_resigned_claim_actual_and_assertion_type_changes_are_rejected(self):
        document = request()
        document['jobs'][0]['inputs'] = {'p_values': {'first': 1.0}}
        document['claims'] = [
            {'id': 'flag', 'job_id': 'comparison/a~b', 'pointer': '/result/trials/first/reject', 'assertion': False},
            {'id': 'number', 'job_id': 'comparison/a~b', 'pointer': '/result/trials/first/holm_p', 'assertion': 1.0}]
        prepared, _ = self.prepared(document)
        for field in ('actual_value', 'assertion'):
            for index, changed in ((0, 0), (1, 1)):
                with self.subTest(field=field, claim=index):
                    output = self.directory / f'{field}-{index}'
                    result = workflow.run(prepared / 'plan.json', output)
                    self.assertEqual(result['claims'][index]['status'], 'MATCH')
                    self.assertNotEqual(type(result['claims'][index][field]), type(changed))
                    result['claims'][index][field] = changed
                    resign_changed_result(output, result)
                    with self.assertRaisesRegex(ValueError, 'RETAINED_CLAIM_BINDING_MISMATCH'):
                        workflow.verify(output)

    def test_outer_quant_result_requires_exact_json_type_even_when_replay_is_tolerant(self):
        document = request()
        document['jobs'][0]['inputs'] = {'p_values': {'first': 1.0}}
        document['claims'] = []
        prepared, _ = self.prepared(document)
        output = self.directory / 'typed-result'
        result = workflow.run(prepared / 'plan.json', output)
        self.assertIs(type(result['jobs'][0]['result']['trials']['first']['holm_p']), float)
        result['jobs'][0]['result']['trials']['first']['holm_p'] = 1
        resign_changed_result(output, result)
        with self.assertRaisesRegex(ValueError, 'QUANT_RESULT_BINDING_MISMATCH'):
            workflow.verify(output)

    def test_retained_claim_dictionary_key_order_remains_equivalent(self):
        document = request()
        document['claims'] = [{'id': 'trial', 'job_id': 'comparison/a~b', 'pointer': '/result/trials/first'}]
        prepared, _ = self.prepared(document)
        output = self.directory / 'reordered'
        result = workflow.run(prepared / 'plan.json', output)
        result['claims'][0]['actual_value'] = dict(reversed(list(result['claims'][0]['actual_value'].items())))
        resign_changed_result(output, result)
        self.assertEqual(workflow.verify(output)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')

    def test_prepare_and_summary_do_not_open_network_or_launch_code(self):
        with mock.patch.object(socket.socket, 'connect', side_effect=AssertionError('Network forbidden')), \
                mock.patch.object(socket, 'create_connection', side_effect=AssertionError('Network forbidden')), \
                mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('Processes forbidden')):
            prepared, _ = self.prepared()
            output = self.directory / 'run'
            workflow.run(prepared / 'plan.json', output)
            self.assertEqual(workflow.summarize(output)['verification']['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')

    def test_preparation_rejects_reused_skill_output_and_remote_source_paths(self):
        source = self.directory / 'request.json'
        source.write_bytes(workflow.encode(request()))
        output = self.directory / 'prepared'
        workflow.prepare(source, output, 'Declared request')
        for target in (output, ROOT / 'forbidden-test-prepare'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                workflow.prepare(source, target, 'Declared request')
        for remote in ('https://example.invalid/input.json', '//host/share/input.json'):
            document = request()
            del document['jobs'][0]['inputs']
            document['jobs'][0]['inputs_source'] = {'path': remote, 'sha256': '1' * 64, 'pointer': ''}
            source.write_bytes(workflow.encode(document))
            with self.subTest(remote=remote), self.assertRaises(ValueError):
                workflow.prepare(source, self.directory / 'remote', 'Declared request', {remote: 'Declared bytes'})
        self.assertFalse((self.directory / 'remote').exists())

    def test_prepare_and_summary_cli_use_retained_inputs_and_private_output(self):
        source = self.directory / 'request.json'
        source.write_bytes(workflow.encode(request()))
        command = [sys.executable, '-X', 'utf8', '-B', str(ROOT / 'scripts/research_workflow.py')]
        prepared = self.directory / 'prepared'
        created = subprocess.run(command + ['prepare', str(source), '--private-output-dir', str(prepared),
                                            '--request-role', 'Synthetic original request'],
                                 capture_output=True, text=True)
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(created.stdout.strip(), 'PREPARED')
        output = self.directory / 'run'
        executed = subprocess.run(command + ['run', str(prepared / 'plan.json'),
                                            '--private-output-dir', str(output)], capture_output=True, text=True)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        projected = subprocess.run(command + ['summary', str(output)], capture_output=True, text=True)
        self.assertEqual(projected.returncode, 0, projected.stderr)
        summary = json.loads(projected.stdout)
        self.assertEqual(summary['verification']['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')
        self.assertEqual(summary['coverage'][1]['status'], 'UNADDRESSED')
        self.assertEqual(summary['claims'], workflow.summarize(output)['claims'])
        invalid = subprocess.run(command + ['prepare', str(source), '--private-output-dir', str(prepared),
                                            '--source-role', 'x', 'one', '--source-role', 'x', 'two'],
                                 capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertNotIn('Assess these synthetic', invalid.stdout + invalid.stderr)


if __name__ == '__main__':
    unittest.main()
