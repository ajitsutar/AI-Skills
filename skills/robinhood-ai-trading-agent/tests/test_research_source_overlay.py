import copy
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from public_research import digest
from research_source_overlay import apply_overlay
from test_public_research import fixture


class SourceOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'release.txt').write_bytes(b'Fictional test source, not market data.')
        self.s = fixture()
        self.o = {'schema_version': 1, 'base_input_sha256': digest(self.s),
                  'information_cutoff': '2026-06-12T20:00:00Z',
                  'source_policy': 'Latest primary GAAP takes precedence', 'scope': 'DEMO0 only',
                  'unresolved_gaps': 'Other issuers have not been independently verified',
                  'sources': [{'id': 's1', 'url': 'https://issuer.invalid/earnings', 'kind': 'issuer',
                    'published_at': '2026-06-01T12:00:00Z', 'retrieved_at': '2026-06-12T19:00:00Z',
                    'file': 'release.txt', 'content_sha256': hashlib.sha256((self.root / 'release.txt').read_bytes()).hexdigest()}],
                  'changes': [{'symbol': 'DEMO0', 'table': 'income', 'field': 'OperatingIncome',
                    'period_end': '2026-05-31', 'old_value': None, 'value': 120000000,
                    'basis': 'GAAP', 'currency': 'USD', 'units': 'USD', 'duration': 'quarter',
                    'source_ids': ['s1'], 'locator': 'Table 1 row 3', 'derivation': '120 million times 1000000',
                    'conflict_reviewed': True, 'choice_reason': 'Primary release newer than vendor'}]}

    def test_new_quarter_preserves_original_and_provenance(self):
        before = digest(self.s)
        r = apply_overlay(self.s, self.o, self.root)
        self.assertEqual(digest(self.s), before)
        self.assertEqual(r['source_overlay']['base_input_sha256'], before)
        t = next(x for x in r['rows'] if x['symbol'] == 'DEMO0')['income']
        self.assertEqual(t['data'][t['index'].index('OperatingIncome')][-1], '120000000')
        self.assertEqual(r['universe_symbols'], self.s['universe_symbols'])

    def test_vendor_sources_allowed_but_bad_bytes_or_future_sources_fail(self):
        self.o['sources'][0]['kind'] = 'vendor'
        self.assertEqual(apply_overlay(self.s, self.o, self.root)['source_overlay']['source_kinds'], ['vendor'])
        self.o['sources'][0]['content_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SOURCE_BYTES'): apply_overlay(self.s, self.o, self.root)
        self.o['sources'][0]['published_at'] = '2026-06-13T12:00:00Z'
        with self.assertRaisesRegex(ValueError, 'AFTER_CUTOFF'): apply_overlay(self.s, self.o, self.root)

    def test_bad_mappings_duplicate_cells_and_base_changes_fail(self):
        for field, value in [('basis', 'adjusted'), ('duration', 'YTD'), ('currency', 'EUR'),
                             ('conflict_reviewed', False), ('old_value', 0), ('value', 'NaN')]:
            o = copy.deepcopy(self.o); o['changes'][0][field] = value
            with self.assertRaises(ValueError): apply_overlay(self.s, o, self.root)
        o = copy.deepcopy(self.o); o['changes'] *= 2
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_CELL'): apply_overlay(self.s, o, self.root)
        o['base_input_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'BASE_MISMATCH'): apply_overlay(self.s, o, self.root)


if __name__ == '__main__': unittest.main()
