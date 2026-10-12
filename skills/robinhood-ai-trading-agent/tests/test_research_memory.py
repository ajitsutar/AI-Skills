import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from research_memory import seal, verify, refresh_plan


class ResearchMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'facts.json').write_text('{"sales":12}', encoding='utf-8')
        self.catalog = {'run_id': 'example', 'as_of': '2026-10-11T20:00:00Z',
                        'hold': 'P1M', 'universe': 'CUSTOM', 'artifacts': [
                            {'path': 'facts.json', 'kind': 'filing',
                             'as_of': '2026-10-11T19:00:00Z'}]}

    def test_roundtrip_and_mutated_bytes(self):
        manifest = seal(self.root, self.catalog)
        self.assertEqual(verify(self.root, manifest)['status'], 'ARCHIVE_BYTES_MATCH')
        (self.root / 'facts.json').write_text('{"sales":99}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            verify(self.root, manifest)

    def test_paths_duplicates_and_future_facts(self):
        for path in ('../escape', 'C:/secret', '/absolute', 'folder\\file'):
            bad = copy.deepcopy(self.catalog)
            bad['artifacts'][0]['path'] = path
            with self.assertRaises(ValueError):
                seal(self.root, bad)
        bad = copy.deepcopy(self.catalog)
        bad['artifacts'].append(copy.deepcopy(bad['artifacts'][0]))
        with self.assertRaises(ValueError):
            seal(self.root, bad)
        bad = copy.deepcopy(self.catalog)
        bad['artifacts'][0]['as_of'] = '2026-10-12T00:00:00Z'
        with self.assertRaises(ValueError):
            seal(self.root, bad)

    def test_plan_never_promotes_stale_facts_and_recomputes_all_results(self):
        for kind, expected in [('filing', 'RECHECK_SOURCE_THEN_REUSE'),
                               ('result', 'RECOMPUTE'), ('prices', 'REFRESH'),
                               ('events', 'REFRESH'), ('universe', 'REFRESH')]:
            self.catalog['artifacts'][0]['kind'] = kind
            manifest = seal(self.root, self.catalog)
            plan = refresh_plan(self.root, manifest, '2026-10-12T20:00:00Z', 'P1Y', 'CUSTOM')
            self.assertEqual(plan['artifacts'][0]['action'], expected)
            self.assertTrue(plan['context_changed'])
            self.assertFalse(plan['automatic_download_performed'])
            self.assertFalse(plan['execution_authorized'])

    def test_manifest_tampering_and_backdated_refresh_fail(self):
        manifest = seal(self.root, self.catalog)
        with self.assertRaises(ValueError):
            refresh_plan(self.root, manifest, '2026-10-10T20:00:00Z', 'P1M', 'CUSTOM')
        manifest['hold'] = 'P1Y'
        with self.assertRaises(ValueError):
            verify(self.root, manifest)


if __name__ == '__main__':
    unittest.main()
