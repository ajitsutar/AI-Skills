"""Single-command execution preserves stages, failures and private evidence."""
import copy
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
import research_workflow as workflow
import answer_facts
from test_answer_facts import trade_request


class WorkflowExecuteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='workflow-execute-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.request = self.directory / 'request.json'
        self.output = self.directory / 'execution'

    def execute(self, document=None):
        self.request.write_bytes(workflow.encode(document or trade_request()))
        return workflow.execute(self.request, self.output, 'Synthetic original request')

    def read(self, name):
        return json.loads((self.output / name).read_bytes())

    def test_success_stages_hash_inventory_and_offline_no_download_claim(self):
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden')):
            receipt = self.execute()
        self.assertEqual(receipt['status'], 'COMPLETED_LOCAL_WORKFLOW')
        self.assertTrue(all(s['status'] == 'COMPLETED' for s in receipt['stages'].values()))
        self.assertEqual(receipt['jobs'][0]['evidence']['status'], 'CURRENT_EXECUTION_VERIFIED')
        self.assertFalse(receipt['host_download_observed'])
        self.assertFalse(receipt['whole_answer_pass'])
        self.assertEqual((self.output / 'original-request.json').read_bytes(), self.request.read_bytes())
        inventory = self.read('export-inventory.json')
        expected = {p.relative_to(self.output).as_posix() for p in self.output.rglob('*') if p.is_file()}
        self.assertEqual({row['path'] for row in inventory['artifacts']}, expected - {'export-inventory.json'})
        for row in inventory['artifacts']:
            self.assertEqual(workflow.sha((self.output / row['path']).read_bytes()), row['sha256'])
        self.assertFalse(inventory['remote_upload_observed'])
        facts = self.read('answer-facts.json')
        self.assertTrue(all((self.output / f['source']['artifact']).is_file() for f in facts['facts']))
        self.assertTrue(all(f['source']['artifact'] == 'run/result.json' for f in facts['facts']))
        self.assertEqual(answer_facts.verify_projection(self.output, (self.output / 'answer-facts.json').read_bytes())['status'],
                         'FIXED_ANSWER_FACTS_MATCH')

    def test_bad_job_is_retained_and_does_not_hide_good_job_or_missing_requirement(self):
        request = trade_request()
        bad = copy.deepcopy(request['jobs'][0])
        bad['id'] = 'bad'
        bad['inputs']['document']['quantity'] = -1
        request['jobs'].append(bad)
        request['requirements'].append({'id': 'unavailable', 'question': 'Missing provider data', 'job_ids': []})
        receipt = self.execute(request)
        self.assertEqual(receipt['status'], 'COMPLETED_WITH_DIAGNOSTICS')
        self.assertEqual([j['computation_status'] for j in receipt['jobs']], ['COMPUTED', 'REJECTED_INPUT'])
        self.assertFalse(receipt['jobs'][1]['evidence']['completion_supported'])
        self.assertEqual(receipt['coverage'][1]['status'], 'UNADDRESSED')
        facts = self.read('answer-facts.json')
        self.assertFalse(any(f['job_id'] == 'bad' for f in facts['facts']))

    def test_preparation_failure_preserves_original_and_unexecuted_jobs(self):
        request = trade_request()
        request['jobs'][0]['inputs_source'] = {'path': 'missing.json', 'sha256': '0' * 64, 'pointer': ''}
        del request['jobs'][0]['inputs']
        receipt = self.execute(request)
        self.assertEqual(receipt['status'], 'INCOMPLETE')
        self.assertEqual(receipt['stages']['prepare']['status'], 'FAILED')
        self.assertEqual(receipt['jobs'][0]['computation_status'], 'NOT_EXECUTED_OR_UNRESOLVED')
        self.assertFalse(receipt['jobs'][0]['evidence']['completion_supported'])
        self.assertTrue((self.output / 'failure.json').is_file())
        self.assertEqual((self.output / 'original-request.json').read_bytes(), self.request.read_bytes())
        self.assertFalse((self.output / 'answer-facts.json').exists())

    def test_verification_failure_keeps_run_but_never_issues_answer_facts(self):
        with mock.patch.object(workflow, 'verify', side_effect=ValueError('Synthetic verifier rejection')):
            receipt = self.execute()
        self.assertEqual(receipt['status'], 'INCOMPLETE')
        self.assertEqual(receipt['stages']['verification']['status'], 'FAILED')
        self.assertTrue((self.output / 'run/result.json').exists())
        self.assertFalse((self.output / 'answer-facts.json').exists())
        self.assertFalse(receipt['jobs'][0]['evidence']['completion_supported'])

    def test_unexpected_failure_preserves_prior_completed_job_artifacts(self):
        request = trade_request()
        second = copy.deepcopy(request['jobs'][0]); second['id'] = 'second'
        request['jobs'].append(second)
        real_build = workflow.quant_report.build
        count = 0
        def build(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('Synthetic unavailable runtime')
            return real_build(*args, **kwargs)
        with mock.patch.object(workflow.quant_report, 'build', side_effect=build):
            receipt = self.execute(request)
        self.assertEqual(receipt['status'], 'INCOMPLETE')
        self.assertTrue((self.output / 'run/jobs/0000/quant/bundle.json').exists())
        self.assertTrue((self.output / 'run/jobs/0001/arguments.json').exists())
        self.assertFalse((self.output / 'answer-facts.json').exists())
        self.assertEqual(len(receipt['jobs']), 2)
        self.assertTrue(all(not j['evidence']['completion_supported'] for j in receipt['jobs']))
        self.assertEqual(receipt['jobs'][0]['computation_status'], 'PARTIAL_ARTIFACTS_UNVERIFIED')
        self.assertEqual(receipt['jobs'][0]['partial_artifact'], 'run/jobs/0000/quant/bundle.json')

    def test_prepare_failure_retains_each_external_source_already_read(self):
        request = trade_request()
        source_raw = workflow.encode(request['jobs'][0].pop('inputs'))
        (self.directory / 'first.json').write_bytes(source_raw)
        request['jobs'][0]['inputs_source'] = {'path': 'first.json', 'sha256': workflow.sha(source_raw), 'pointer': ''}
        second = copy.deepcopy(request['jobs'][0]); second['id'] = 'second'
        second['inputs_source']['path'] = 'missing.json'
        request['jobs'].append(second)
        self.request.write_bytes(workflow.encode(request))
        receipt = workflow.execute(self.request, self.output, 'Synthetic request',
                                   {'first.json': 'Synthetic first input', 'missing.json': 'Missing second input'})
        self.assertEqual(receipt['status'], 'INCOMPLETE')
        self.assertEqual((self.output / 'attempted-sources/0000/source.json').read_bytes(), source_raw)
        self.assertEqual(self.read('attempted-sources/0000/identity.json')['status'], 'READ_BYTES_NOT_YET_VALIDATED')
        self.assertFalse((self.output / 'prepare/plan.json').exists())

    def test_missing_dependency_at_process_start_saves_explicit_blocker_without_install(self):
        self.request.write_bytes(workflow.encode(trade_request()))
        # -S supplies a real dependency-unavailable runtime without removing or
        # installing any package or mocking the workflow's outcome.
        command = [sys.executable, '-S', str(ROOT / 'scripts/research_workflow.py'), 'execute', str(self.request),
                   '--request-role', 'Synthetic test', '--private-output-dir', str(self.output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        receipt = self.read('completion.json')
        self.assertEqual(receipt['status'], 'INCOMPLETE')
        self.assertEqual(receipt['failure']['category'], 'DEPENDENCY_UNAVAILABLE')
        self.assertEqual(receipt['dependency_installs_performed'], 0)
        self.assertEqual(receipt['stages']['run']['status'], 'NOT_STARTED')
        self.assertFalse((self.output / 'answer-facts.json').exists())
        self.assertEqual((self.output / 'original-request.json').read_bytes(), self.request.read_bytes())

    def test_new_root_only_and_cli_exit_status(self):
        self.request.write_bytes(workflow.encode(trade_request()))
        command = [sys.executable, str(ROOT / 'scripts/research_workflow.py'), 'execute', str(self.request),
                   '--request-role', 'Synthetic test', '--private-output-dir', str(self.output)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'COMPLETED_LOCAL_WORKFLOW')
        before = {p.relative_to(self.output).as_posix(): p.read_bytes() for p in self.output.rglob('*') if p.is_file()}
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT_REQUIRED'):
            workflow.execute(self.request, self.output, 'Synthetic test')
        self.assertEqual(before, {p.relative_to(self.output).as_posix(): p.read_bytes()
                                for p in self.output.rglob('*') if p.is_file()})
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT_REQUIRED'):
            workflow.execute(self.request, ROOT / 'forbidden-execute-test', 'Synthetic test')


if __name__ == '__main__':
    unittest.main()
