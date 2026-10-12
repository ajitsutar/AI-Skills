import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_evidence as ae
from news_sources import digest


class AnalystEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.text = 'Fictional attributed analyst excerpt; source is test data only.'
        (self.root / 'evidence.txt').write_text(self.text, encoding='utf-8')
        self.request = {'as_of': '2026-10-12T15:00:00Z', 'issuer': 'DEMO', 'currency': 'USD',
                        'price_basis': 'current_common_share', 'target_horizon': 'forward_12_months',
                        'individual_targets': [], 'provider_consensus': [], 'analyst_track_records': []}

    def source(self, published='2026-10-10T12:00:00Z'):
        return {'path': 'evidence.txt', 'sha256': digest((self.root / 'evidence.txt').read_bytes()),
                'url': 'https://publisher.example/analyst-report', 'published_at': published,
                'observed_at': '2026-10-12T14:30:00Z', 'locator': 'Attributed analyst paragraph',
                'verbatim_excerpt': 'Fictional attributed analyst excerpt'}

    def target(self, firm='firm_a', target=100, issued='2026-10-10T12:00:00Z', **changes):
        value = {k: self.request[k] for k in ('issuer', 'currency', 'price_basis', 'target_horizon')}
        value.update(record_id=firm + '_' + str(target), firm_id=firm, analyst_id=firm + '_analyst',
                     target=target, issued_at=issued, access='ATTRIBUTED_EXCERPT', source=self.source(issued))
        value.update(changes)
        return value

    def aggregate(self, **changes):
        value = {k: self.request[k] for k in ('issuer', 'currency', 'price_basis', 'target_horizon')}
        value.update(provider='public_provider', source=self.source(), mean=115, median=110,
                     minimum=80, maximum=160, analyst_count=4, target_count=4)
        value.update(changes)
        return value

    def track_record(self, **changes):
        value = {'analyst_id': 'analyst_a', 'firm_id': 'firm_a', 'provider': 'public_provider',
                 'evaluation_start': '2025-01-01T00:00:00Z', 'evaluation_end': '2026-10-01T00:00:00Z',
                 'holding_rule': 'Close after one year', 'benchmark': 'US total return index',
                 'return_definition': 'Total return net of stated assumed transaction costs',
                 'methodology_url': 'https://provider.example/methodology',
                 'success_definition': 'Positive excess total return versus stated benchmark',
                 'recommendation_count': 50, 'success_rate_pct': 62, 'average_return_pct': 8.5,
                 'source': self.source()}
        value.update(changes)
        return value

    def review(self):
        return ae.review(self.request, self.root)

    def test_independent_firm_consensus_has_mean_median_range_and_iqr(self):
        self.request['individual_targets'] = [self.target('firm_' + str(i), v)
                                              for i, v in enumerate((80, 100, 120, 160))]
        self.request['quote'] = {'issuer': 'DEMO', 'currency': 'USD', 'price_basis': 'current_common_share',
                                 'price': 100, 'source': self.source()}
        result = self.review()
        cohort = result['consensus']
        self.assertEqual(cohort['independent_firms'], 4)
        self.assertEqual(cohort['mean'], 115)
        self.assertEqual(cohort['median'], 110)
        self.assertEqual((cohort['minimum'], cohort['maximum']), (80, 160))
        self.assertEqual((cohort['q1'], cohort['q3']), (95, 130))
        self.assertAlmostEqual(cohort['iqr_over_median'], 35 / 110)
        self.assertAlmostEqual(cohort['median_implied_price_change_pct'], 10)
        self.assertEqual(cohort['status'], 'PARTIAL_OBSERVED_COHORT')
        self.assertEqual(result['coverage'], 'OBSERVED_SOURCES_ONLY')
        self.assertFalse(result['strong_buy_available'])
        self.assertFalse(result['execution_authorized'])

    def test_latest_issue_per_firm_beats_recaps_and_syndication_without_double_counting(self):
        old = self.target('firm_a', 100, issued='2026-10-01T12:00:00Z')
        old['source'] = self.source('2026-10-11T12:00:00Z')
        latest = self.target('firm_a', 120)
        duplicate = copy.deepcopy(latest)
        duplicate['record_id'] = 'syndicated_copy'
        other = self.target('firm_b', 80)
        for rows in ([old, latest, duplicate, other], [other, duplicate, latest, old]):
            self.request['individual_targets'] = rows
            result = self.review()
            self.assertEqual(result['consensus']['independent_firms'], 2)
            self.assertEqual(result['consensus']['median'], 100)
            self.assertEqual({r['target'] for r in result['individual_targets_used']}, {80, 120})
            self.assertEqual(len(result['excluded']), 2)

    def test_simultaneous_conflicting_firm_targets_do_not_depend_on_input_order(self):
        a, b = self.target('firm_a', 100), self.target('firm_a', 130)
        for rows in ([a, b], [b, a]):
            self.request['individual_targets'] = rows
            result = self.review()
            self.assertEqual(result['individual_targets_used'], [])
            self.assertEqual(result['consensus']['status'], 'UNAVAILABLE')
            self.assertIn('UNRESOLVED_FIRM_CONFLICT', {r['reason'] for r in result['excluded']})
        later = self.target('firm_a', 125, issued='2026-10-11T12:00:00Z')
        self.request['individual_targets'] = [a, b, later]
        self.assertEqual(self.review()['consensus']['median'], 125)

    def test_horizon_currency_issuer_and_share_basis_must_match(self):
        for key, value in (('target_horizon', 'forward_52_weeks'), ('currency', 'EUR'),
                           ('issuer', 'OTHER'), ('price_basis', 'pre_split_2_for_1')):
            self.request['individual_targets'] = [self.target(**{key: value})]
            with self.subTest(key=key):
                result = self.review()
                self.assertEqual(result['consensus']['status'], 'UNAVAILABLE')
                self.assertEqual(result['excluded'][0]['reason'], 'TARGET_DIMENSIONS_MISMATCH')
        self.request['target_horizon'] = 'fiscal_2027'
        with self.assertRaisesRegex(ValueError, 'separate cohort'):
            self.review()

    def test_recent_recap_of_old_target_does_not_refresh_target_age(self):
        stale = self.target(issued='2026-01-01T12:00:00Z')
        stale['source'] = self.source('2026-10-11T12:00:00Z')
        unknown_issue = self.target('unknown')
        del unknown_issue['issued_at']
        invalid_issue = self.target('impossible', issued='2026-10-11T12:00:00Z')
        invalid_issue['source'] = self.source('2026-10-10T12:00:00Z')
        self.request['individual_targets'] = [stale, unknown_issue, invalid_issue]
        result = self.review()
        self.assertEqual(result['consensus']['status'], 'UNAVAILABLE')
        self.assertEqual(len(result['excluded']), 3)
        self.assertIn('STALE_TARGET', {r['reason'] for r in result['excluded']})
        self.assertIn('TARGET_ISSUED_AFTER_SOURCE_PUBLICATION', {r['reason'] for r in result['excluded']})

    def test_missing_access_analyst_identity_invalid_values_or_bad_saved_hash_are_excluded(self):
        bad_hash = self.target('bad_hash')
        bad_hash['source']['sha256'] = '0' * 64
        missing_analyst = self.target('missing_analyst', analyst_id='')
        inaccessible = self.target('paywalled', access='SEARCH_SNIPPET_ONLY')
        invalid_targets = [self.target('invalid_' + str(i), value) for i, value in
                           enumerate((True, 0, -1, float('nan'), float('inf'), '120'))]
        self.request['individual_targets'] = [bad_hash, missing_analyst, inaccessible] + invalid_targets
        result = self.review()
        self.assertEqual(result['consensus']['independent_firms'], 0)
        self.assertEqual(len(result['excluded']), 9)
        self.assertIn('REPORT_NOT_ACCESSED', {r['reason'] for r in result['excluded']})
        self.assertIn('ANALYST_OR_FIRM_UNKNOWN', {r['reason'] for r in result['excluded']})

    def test_provider_pools_remain_separate_and_are_never_averaged_together(self):
        self.request['individual_targets'] = [self.target('firm_a', 100)]
        self.request['provider_consensus'] = [self.aggregate(mean=150, median=150),
                                             self.aggregate(provider='another_provider', target_horizon='unknown')]
        result = self.review()
        self.assertEqual(result['consensus']['median'], 100)
        self.assertEqual(result['consensus']['independent_firms'], 1)
        self.assertEqual(len(result['provider_consensus']), 2)
        self.assertTrue(result['provider_consensus'][0]['comparable_dimensions'])
        self.assertFalse(result['provider_consensus'][1]['comparable_dimensions'])
        self.assertTrue(all(r['status'] == 'PROVIDER_REPORTED_NOT_COMBINED' for r in result['provider_consensus']))

    def test_provider_consensus_rejects_nonfinite_values_impossible_counts_and_ranges(self):
        for changes in ({'mean': float('nan')}, {'median': True}, {'maximum': -1},
                        {'minimum': 170}, {'median': 300}, {'analyst_count': 0},
                        {'target_count': 2.5}, {'analyst_count': True}):
            self.request['provider_consensus'] = [self.aggregate(**changes)]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.review()

    def test_quote_comparison_rejects_unmatched_share_basis_and_nonpositive_price(self):
        self.request['individual_targets'] = [self.target()]
        quote = {'issuer': 'DEMO', 'currency': 'USD', 'price_basis': 'current_common_share',
                 'price': 100, 'source': self.source()}
        for changes in ({'price_basis': 'ADR_unit'}, {'currency': 'EUR'}, {'price': 0}):
            self.request['quote'] = dict(quote, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.review()

    def test_stale_quote_preserves_consensus_but_does_not_produce_current_implied_upside(self):
        self.request['individual_targets'] = [self.target('firm_a', 120)]
        self.request['quote'] = {'issuer': 'DEMO', 'currency': 'USD', 'price_basis': 'current_common_share',
                                 'price': 100, 'source': self.source('2026-09-12T15:00:00Z')}
        result = self.review()['consensus']
        self.assertEqual(result['median'], 120)
        self.assertEqual(result['quote_status'], 'STALE')
        self.assertIsNone(result['median_implied_price_change_pct'])
        self.request['quote']['source'] = self.source('2026-10-12T14:00:00Z')
        self.request['max_quote_age_hours'] = 2
        self.assertAlmostEqual(self.review()['consensus']['median_implied_price_change_pct'], 20)
        self.request['max_quote_age_hours'] = 0
        with self.assertRaises(ValueError):
            self.review()

    def test_track_record_partial_metadata_never_becomes_a_selection_weight(self):
        partial = {'analyst_id': 'analyst_a', 'firm_id': 'firm_a', 'provider': 'public_provider',
                   'success_rate_pct': 62, 'source': self.source()}
        self.request['analyst_track_records'] = [partial, self.track_record()]
        result = self.review()['analyst_track_records']
        self.assertEqual(result[0]['status'], 'PROVIDER_REPORTED_PARTIAL')
        self.assertIn('recommendation_count', result[0]['missing'])
        self.assertIn('holding_rule', result[0]['missing'])
        self.assertEqual(result[1]['status'], 'PROVIDER_REPORTED_WITH_METHOD')
        self.assertEqual(result[1]['missing'], [])
        self.assertTrue(all(not r['independently_reproduced'] and r['selection_weight'] is None for r in result))

    def test_success_rate_without_success_definition_is_partial(self):
        self.request['analyst_track_records'] = [self.track_record(success_definition=None)]
        result = self.review()['analyst_track_records'][0]
        self.assertEqual(result['status'], 'PROVIDER_REPORTED_PARTIAL')
        self.assertIn('success_definition', result['missing'])
        self.assertIsNone(result['selection_weight'])

    def test_track_record_invalid_metrics_and_lookahead_are_rejected(self):
        for changes in ({'success_rate_pct': -1}, {'success_rate_pct': 101},
                        {'success_rate_pct': True}, {'average_return_pct': float('inf')},
                        {'recommendation_count': 0}, {'recommendation_count': 5.5},
                        {'evaluation_end': '2026-11-01T00:00:00Z'},
                        {'evaluation_end': '2026-10-11T00:00:00Z'},
                        {'evaluation_start': '2026-10-02T00:00:00Z'}):
            self.request['analyst_track_records'] = [self.track_record(**changes)]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.review()

    def test_frozen_evidence_replay_is_identical_and_does_not_mutate_request(self):
        self.request['individual_targets'] = [self.target('firm_a', 100), self.target('firm_b', 120)]
        self.request['analyst_track_records'] = [self.track_record()]
        original = copy.deepcopy(self.request)
        result = self.review()
        self.assertEqual(result, self.review())
        self.assertEqual(self.request, original)
        self.assertEqual(result['input_sha256'], digest(json.dumps(self.request, sort_keys=True)))


if __name__ == '__main__':
    unittest.main()
