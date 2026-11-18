"""Source-bound workflow retains cross-tool clock conflicts and replay evidence."""
import json
from pathlib import Path
import unittest

from test_research_workflow import build, encode, plan_for, selected, workflow


class HorizonConsistencyWorkflowTests(unittest.TestCase):
    def test_conflict_survives_dispatch_with_original_bindings(self):
        root = Path(__file__).resolve().parents[1]
        document = json.loads((root / 'examples/fictional-horizon-consistency.json').read_text())
        sources = {'request': ('request.json', encode(document), 'supplied research request')}
        operation = 'research.audit_horizon_consistency'
        plan = plan_for(sources, [{'id': 'clocks', 'operation': operation,
                                  'arguments': {'document': selected('request')}}],
                        claims=[{'id': 'clock-state', 'job_id': 'clocks',
                                 'pointer': '/result/result/status', 'assertion': 'CONFLICT'}])
        artifacts = build(plan, sources)
        result = workflow.read_result(artifacts['result.json'])
        job = result['jobs'][0]
        self.assertEqual(job['status'], 'COMPUTED')
        self.assertEqual(job['result']['result']['status'], 'CONFLICT')
        self.assertFalse(job['result']['result']['screen_checks_replaced'])
        self.assertEqual(artifacts['sources/request.json'], sources['request'][1])
        self.assertIn(operation, workflow.catalog()['additional_operations'])


if __name__ == '__main__':
    unittest.main()
