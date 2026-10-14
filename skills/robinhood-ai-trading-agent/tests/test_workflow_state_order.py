"""JSON object insertion order cannot change a workflow's evidence states."""
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get('WORKFLOW_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
import research_workflow as workflow


class WorkflowStateOrderTests(unittest.TestCase):
    def test_nested_state_projection_is_invariant_to_object_insertion_order(self):
        entries = [('warnings', ['Synthetic observation']), ('status', 'UNCERTAIN'),
                   ('result', {'reason': 'Missing input', 'limits': ['Unmeasured']})]
        expected = None
        for permutation in itertools.permutations(entries):
            value = dict(permutation)
            states = list(workflow.nested_states(value))
            self.assertEqual(states, list(workflow.nested_states(json.loads(workflow.encode(value)))))
            if expected is None:
                expected = states
            self.assertEqual(states, expected)

    def test_array_sequence_and_pointer_escaping_are_preserved(self):
        value = {'z/key': [{'status': 'FIRST', 'reason': 'One'},
                           {'status': 'SECOND', 'reason': 'Two'}],
                 'a~key': {'warnings': [], 'status': 'UNKNOWN'}}
        rows = list(workflow.nested_states(value))
        self.assertEqual([r['pointer'] for r in rows],
                         ['/a~0key/status', '/a~0key/warnings', '/z~1key/0/reason',
                          '/z~1key/0/status', '/z~1key/1/reason', '/z~1key/1/status'])
        self.assertEqual([r['value'] for r in rows if r['pointer'].endswith('/status')],
                         ['UNKNOWN', 'FIRST', 'SECOND'])

    def test_full_report_projection_round_trip_verifies_without_order_false_positive(self):
        raw = workflow.encode({'results': [
            {'id': 'synthetic', 'operation': 'historical.example', 'status': 'COMPUTED',
             'result': {'value': 12.25, 'status': 'UNKNOWN', 'warnings': ['Synthetic only']}}]})
        plan = {'schema_version': 1, 'network_mode': 'offline',
                'contract': {'prompt': 'Project the supplied synthetic result.',
                             'purpose': 'regression test', 'base_currency': 'USD',
                             'horizon_id': 'P1Y', 'as_of': '2032-02-01T00:00:00Z'},
                'sources': [{'id': 'source', 'path': 'source.json',
                             'sha256': workflow.sha(raw), 'format': 'json',
                             'role': 'synthetic retained calculation'}],
                'jobs': [{'id': 'projection', 'operation': 'report.quant',
                          'arguments': {'source_id': {'$assumption': 'source',
                                                     'reason': 'Select the declared source'}}}],
                'requirements': [{'id': 'report', 'question': 'Project all retained facts',
                                  'job_ids': ['projection'], 'expected_operations': ['report.quant']}],
                'claims': [{'id': 'facts', 'job_id': 'projection', 'pointer': '/result/facts'}]}
        artifacts = workflow.build(workflow.encode(plan), lambda path: raw)
        result = json.loads(artifacts['result.json'])
        self.assertEqual(result['jobs'][0]['status'], 'COMPUTED')
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / 'saved'
            target.mkdir()
            for name, content in artifacts.items():
                destination = target / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            self.assertEqual(workflow.verify(target)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')


if __name__ == '__main__':
    unittest.main()
