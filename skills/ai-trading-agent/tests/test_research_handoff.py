import copy
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from public_research import calculate, digest
from research_handoff import lock, evaluate, freshness, verify_contract
from test_public_research import fixture


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source_root = Path(self.temp.name)
        for name in ("release", "index"):
            (self.source_root / (name + ".txt")).write_text("Fictional " + name, encoding="utf-8")
        self.s = fixture()
        self.s['universe_evidence'] = {'universe_id': 'FICTIONAL'}
        self.m = {'prompt': 'Find research alternatives', 'universe': 'FICTIONAL', 'hold': 'P1Y',
                  'count': 3, 'capital': 400, 'risk_posture': 'aggressive', 'early_exit_policy': 'allowed',
                  'standing_preferences': 'ignore', 'earnings_policy': 'allow_with_disclosure',
                  'selection_mode': 'computed_order', 'allowed_statuses': ['Eligible', 'Speculative'],
                  'custom_filters': [], 'information_cutoff': '2026-06-12T20:00:00Z',
                  'entry_at': '2026-06-15T14:00:00Z', 'exit_at': '2027-06-15T19:45:00Z',
                  'price_date': self.s['price_date']}
        self.c = lock(self.m)
        self.l = {'contract_sha256': digest(self.c), 'acquisition': 'shared_snapshot', 'rows': []}
        self.cutoff = datetime(2026, 6, 12, 20, tzinfo=timezone.utc)

    def evidence(self, symbol, latest='2026-03-31'):
        raw = next(r for r in self.s['rows'] if r['symbol'] == symbol)
        return {'symbol': symbol, 'vendor_row_sha256': digest(raw),
                'latest_release': {'url': 'https://issuer.invalid/results', 'kind': 'issuer',
                                   'file': 'release.txt', 'content_sha256': hashlib.sha256((self.source_root / 'release.txt').read_bytes()).hexdigest(), 'published_at': '2026-06-01T20:00:00Z', 'period_end': latest},
                'release_index': {'url': 'https://issuer.invalid/news', 'kind': 'issuer', 'file': 'index.txt', 'content_sha256': hashlib.sha256((self.source_root / 'index.txt').read_bytes()).hexdigest()},
                'checked_at': '2026-06-12T19:00:00Z', 'amendments_checked': True,
                'unresolved_restatements': False, 'reviewed_period_end': latest, 'earnings_during_hold': True}

    def reviews(self):
        return {'horizon': {'as_of': self.m['information_cutoff'], 'entry_at': self.m['entry_at'], 'exit_at': self.m['exit_at']},
                'candidates': [{'symbol': 'DEMO' + str(i), 'status': 'Speculative', 'event_status': 'clear',
                    'unresolved_checks': 0, 'primary_evidence_complete': True,
                    'horizon_review': {'evidence_complete': True}} for i in range(10)]}

    def test_mandate_prevents_implicit_rules_and_tampering(self):
        for field, value in [('custom_filters', [{'beta': 1.2}]), ('earnings_policy', None),
                             ('standing_preferences', None), ('capital', 'NaN'), ('capital', True)]:
            bad = copy.deepcopy(self.m); bad[field] = value
            with self.assertRaises(ValueError): lock(bad)
        self.c['mandate']['count'] = 4
        with self.assertRaisesRegex(ValueError, 'MISMATCH'): verify_contract(self.c)

    def test_fresh_download_does_not_fix_newer_primary_quarter(self):
        a = self.evidence('DEMO9', '2026-05-29')
        r = freshness(a, '2026-03-31', self.cutoff, self.source_root)
        self.assertEqual(r['status'], 'STALE_OR_MISMATCHED')
        self.assertEqual(freshness(None, '2026-03-31', self.cutoff, self.source_root)['status'], 'UNKNOWN')
        a['unresolved_restatements'] = True
        self.assertEqual(freshness(a, '2026-03-31', self.cutoff, self.source_root)['status'], 'UNKNOWN')

    def test_month_end_bridge_requires_evidence(self):
        a = self.evidence('DEMO9', '2026-03-29')
        self.assertNotEqual(freshness(a, '2026-03-31', self.cutoff, self.source_root)['status'], 'CURRENT')
        a['period_bridge'] = 'Vendor labels the issuer 13-week quarter using month end; checked both statements.'
        self.assertEqual(freshness(a, '2026-03-31', self.cutoff, self.source_root)['status'], 'CURRENT')
        a['checked_at'] = '2026-06-13T19:00:00Z'
        self.assertEqual(freshness(a, '2026-03-31', self.cutoff, self.source_root)['status'], 'UNKNOWN')
        a['information_as_of'] = self.cutoff.isoformat()
        a['point_in_time_evidence'] = 'Archived June 1 release and dated filing index filtered at cutoff'
        self.assertEqual(freshness(a, '2026-03-31', self.cutoff, self.source_root)['status'], 'CURRENT')

    def test_no_reviews_produce_queue_not_fabricated_buys(self):
        r = evaluate(self.c, self.s, self.l)
        self.assertEqual([q['symbol'] for q in r['research_candidates']], ['DEMO9', 'DEMO8', 'DEMO7'])
        self.assertEqual(r['selected_symbols'], [])
        self.assertFalse(r['horizon_alpha_validated'])
        self.assertFalse(r['execution_authorized'])

    def test_fixed_order_blocks_cherry_picking_and_known_stale_lower_name(self):
        self.l['rows'] = [self.evidence('DEMO' + str(i)) for i in range(10)]
        doc = {'decision_mode': 'fixed_horizon'}
        with patch('research_handoff.review_screen', return_value=self.reviews()):
            r = evaluate(self.c, self.s, self.l, doc, self.source_root)
            self.assertEqual(r['selected_symbols'], ['DEMO9', 'DEMO8', 'DEMO7'])
            self.l['rows'].pop()  # Highest-ranked issuer has no current source check.
            r = evaluate(self.c, self.s, self.l, doc, self.source_root)
            self.assertEqual(r['selected_symbols'], [])
            self.assertIn('DEMO9', r['blocking_review_symbols'])
            self.l['rows'].append(self.evidence('DEMO9'))
            self.l['rows'][0] = self.evidence('DEMO0', '2026-05-29')
            r = evaluate(self.c, self.s, self.l, doc, self.source_root)
            self.assertEqual(r['selected_symbols'], [])
            self.assertIn('DEMO0', r['known_stale_symbols_requiring_rerank'])

    def test_claimed_hash_without_bytes_never_establishes_freshness(self):
        a = self.evidence('DEMO9')
        self.assertEqual(freshness(a, '2026-03-31', self.cutoff)['status'], 'UNKNOWN')
        for name, value in [('file', 'missing.txt'), ('file', '../release.txt'),
                            ('file', str(self.source_root / 'release.txt')),
                            ('content_sha256', 'a' * 64)]:
            bad = copy.deepcopy(a); bad['release_index'][name] = value
            self.assertEqual(freshness(bad, '2026-03-31', self.cutoff, self.source_root)['status'], 'UNKNOWN')
        (self.source_root / 'index.txt').write_bytes(b'')
        a['release_index']['content_sha256'] = hashlib.sha256(b'').hexdigest()
        self.assertEqual(freshness(a, '2026-03-31', self.cutoff, self.source_root)['status'], 'UNKNOWN')

    def test_complete_reviews_cannot_override_missing_ranking_inputs(self):
        from public_research import make_bundle
        bundle = make_bundle(self.s, 3)
        bundle['result']['ranking_relevant_acquisition_failures'] = 1
        self.l['rows'] = [self.evidence('DEMO' + str(i)) for i in range(10)]
        with patch('research_handoff.review_screen', return_value=self.reviews()), patch('research_handoff.make_bundle', return_value=bundle):
            result = evaluate(self.c, self.s, self.l, {'decision_mode': 'fixed_horizon'}, self.source_root)
        self.assertEqual(result['provisional_reviewed_choices'], ['DEMO9', 'DEMO8', 'DEMO7'])
        self.assertEqual(result['selected_symbols'], [])
        self.assertFalse(result['ranking_acquisition_complete'])

    def test_policy_binding_and_research_clocks(self):
        self.l['rows'] = [self.evidence('DEMO' + str(i)) for i in range(10)]
        self.m['earnings_policy'] = 'exclude_during_hold'; self.c = lock(self.m)
        self.l['contract_sha256'] = digest(self.c)
        with patch('research_handoff.review_screen', return_value=self.reviews()):
            self.assertEqual(evaluate(self.c, self.s, self.l, {'decision_mode': 'fixed_horizon'}, self.source_root)['selected_symbols'], [])
        self.l['rows'][0]['vendor_row_sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'INPUT_BINDING'):
            evaluate(self.c, self.s, self.l)


if __name__ == '__main__':
    unittest.main()
