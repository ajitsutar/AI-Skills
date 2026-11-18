"""Literal assertions stay exact; installed platform line endings are portable."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(os.environ.get('WORKFLOW_TEST_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / 'scripts'))
import research_workflow as workflow
import ranking_alignment as ranking


class WorkflowClaimsAndPortabilityTests(unittest.TestCase):
    def test_literal_assertions_do_not_use_numerical_replay_tolerance(self):
        for actual, assertion in [(1000000000, 1000000050), (.1, .100000001),
                                  (True, 1), (1, 1.0), ([12, 23], [12, 23.0])]:
            with self.subTest(actual=actual, assertion=assertion):
                result = workflow.claims([{'id': 'claim', 'job_id': 'job',
                                          'pointer': '/result', 'assertion': assertion}],
                                         {'job': {'result': actual}})
                self.assertEqual(result[0]['status'], 'CONTRADICTED')
                self.assertEqual(result[0]['actual_value'], actual)

    def test_equal_literals_allow_object_key_reordering_but_preserve_list_order(self):
        rows = workflow.claims([
            {'id': 'same', 'job_id': 'j', 'pointer': '/result',
             'assertion': {'b': 2, 'a': [3, 4]}},
            {'id': 'different', 'job_id': 'j', 'pointer': '/result',
             'assertion': {'a': [4, 3], 'b': 2}}],
            {'j': {'result': {'a': [3, 4], 'b': 2}}})
        self.assertEqual([r['status'] for r in rows], ['MATCH', 'CONTRADICTED'])

    def test_ranking_route_replay_survives_installed_profile_newline_variants(self):
        profile = json.loads((ROOT / 'profiles/vqm-fundamental-v1.json').read_text(encoding='utf-8'))
        text = json.dumps(profile)
        document = {'schema_version': 1,
                    'profile': {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()},
                    'snapshot': {'schema_version': 1, 'profile_sha256': ranking.digest(profile)},
                    'requested': {'profile_id': profile['profile_id'],
                                  'profile_sha256': ranking.digest(profile)}}
        plan = {'schema_version': 1, 'network_mode': 'offline',
                'contract': {'prompt': 'Identify a synthetic retained method.', 'purpose': 'test',
                             'base_currency': 'USD', 'horizon_id': 'P1Y',
                             'as_of': '2031-02-01T00:00:00Z'},
                'sources': [],
                'jobs': [{'id': 'route', 'operation': 'ranking.route',
                          'arguments': {'document': {'$assumption': document,
                                                      'reason': 'Synthetic routing input'}}}],
                'requirements': [{'id': 'method', 'question': 'Identify the bound method.',
                                  'job_ids': ['route'], 'expected_operations': ['ranking.route']}]}
        profile_paths = {ROOT / 'profiles' / route[1] for route in ranking.ROUTES}
        original_reader = Path.read_bytes
        expected_routes = ranking.installed_routes()
        for ending in (b'\r\n', b'\r'):
            with self.subTest(ending=ending):
                def read_variant(path):
                    raw = original_reader(path)
                    return raw.replace(b'\r\n', b'\n').replace(b'\n', ending) if path in profile_paths else raw
                with patch.object(Path, 'read_bytes', read_variant):
                    self.assertEqual(ranking.installed_routes(), expected_routes)
                    artifacts = workflow.build(workflow.encode(plan), lambda _: b'')
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    for name, data in artifacts.items():
                        target = root / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                    self.assertEqual(workflow.verify(root)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')


if __name__ == '__main__':
    unittest.main()
