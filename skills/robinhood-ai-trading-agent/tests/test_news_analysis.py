import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_analysis as na
import news_sources as ns


AS_OF = '2026-10-12T15:00:00Z'


def record(title='Demo Industries growth', source_id='issuer', observed='2026-10-12T14:30:00Z', **changes):
    source = {'id': source_id, 'source_kind': 'issuer', 'scope_issuers': ['DEMO']}
    row = {'title': title, 'summary': '', 'url': 'https://issuer.example/news/1',
           'published_at': '2026-10-12T14:00:00Z', 'updated_at': None, 'evidence_kind': 'FEED_EXCERPT'}
    row.update(changes)
    return ns.normalize(row, source, observed, {})


def report(rows):
    return {'records': rows, 'sources': [{'source_id': 'issuer', 'status': 'PARSED'}]}


class NewsTriageTests(unittest.TestCase):
    def test_negation_mixed_language_and_unscored_text_do_not_invent_predictions(self):
        negated = na.sentiment('Demo did not improve but will not beat expectations')
        self.assertEqual(negated['label'], 'NEGATIVE_LANGUAGE')
        self.assertTrue(negated['hits'][0]['negated'])
        self.assertEqual(na.sentiment('Growth despite losses')['label'], 'MIXED')
        self.assertEqual(na.sentiment('Investor day on Tuesday')['label'], 'UNSCORED')
        self.assertIsNone(negated['return_prediction'])
        self.assertIsNone(negated['calibrated_confidence'])

    def test_entity_matching_requires_scope_name_or_cashtag_not_bare_short_ticker(self):
        r = record('ALL IT CAT: routine business discussion')
        r['scope_issuers'] = []
        aliases = {'CAT': ['Caterpillar'], 'ALL': ['Allstate Corporation'], 'IT': ['Gartner']}
        self.assertEqual(na.issuers(r, aliases), [])
        r['title'] = 'Caterpillar and $ALL announce updates'
        self.assertEqual(na.issuers(r, aliases), ['ALL', 'CAT'])

    def test_future_and_not_yet_observed_revisions_do_not_enter_backtest(self):
        old = record('Demo Industries growth', observed='2026-10-12T14:10:00Z')
        new = record('Demo Industries losses', observed='2026-10-12T16:00:00Z',
                     updated_at='2026-10-12T14:20:00Z')
        future = record('Future release', url='https://issuer.example/future',
                        published_at='2026-10-12T17:00:00Z')
        result = na.analyze(report([old, new, future]), {}, AS_OF)
        self.assertEqual([r['event_id'] for r in result['records']], [old['event_id']])
        self.assertEqual(len(result['excluded']), 2)
        self.assertTrue(all(r['reason'] == 'NOT_YET_OBSERVED_OR_FUTURE_DATED' for r in result['excluded']))

    def test_same_poll_revision_ties_use_disclosure_time_not_content_hash_order(self):
        older = record('Older update', updated_at='2026-10-12T14:01:00Z')
        newer = record('Newer update', updated_at='2026-10-12T14:20:00Z')
        older['event_id'], newer['event_id'] = 'zzz_old', 'aaa_new'
        for rows in ([older, newer], [newer, older]):
            result = na.analyze(report(rows), {}, AS_OF)
            self.assertEqual([r['title'] for r in result['records']], ['Newer update'])

    def test_syndicated_headlines_count_once_and_conflicting_excerpts_are_mixed(self):
        a = record('Demo Industries earnings update', summary='Growth')
        b = record('Demo Industries earnings update', source_id='wire', summary='Growth')
        c = record('Demo Industries earnings update', source_id='publisher', summary='Losses')
        same = na.analyze(report([a, b]), {}, AS_OF)
        self.assertEqual(same['unique_headline_cluster_counts'], {'DEMO': {'POSITIVE_LANGUAGE': 1}})
        conflict = na.analyze(report([a, b, c]), {}, AS_OF)
        self.assertEqual(conflict['unique_headline_cluster_counts'], {'DEMO': {'MIXED': 1}})

    def test_sec_metadata_macro_and_missing_time_never_become_issuer_sentiment_votes(self):
        metadata = record('Record 8-K filed', evidence_kind='FILING_METADATA_ONLY')
        macro = record('Macro growth', source_id='fed', url='https://fed.example/release')
        macro['source_kind'] = 'macro'
        unknown = record('Growth', source_id='unknown', published_at=None)
        result = na.analyze(report([metadata, macro, unknown]), {}, AS_OF)
        self.assertEqual(result['unique_headline_cluster_counts'], {})
        self.assertTrue(all(not r['issuer_sentiment_usable_for_research'] for r in result['records']))
        sec = next(r for r in result['records'] if r['source_id'] == 'issuer')
        self.assertEqual(sec['language']['label'], 'UNSCORED')
        self.assertIn('READ_FILING_AND_EXHIBITS', sec['review_events'])

    def test_cached_news_after_skipped_or_failed_refresh_does_not_count_as_fresh_sentiment(self):
        for status in ('NOT_DUE', 'FAILED', 'ACCESS_DENIED', 'RATE_LIMITED'):
            row = record()
            row['source_refresh_status'] = status
            data = report([row])
            data['sources'][0]['status'] = status
            with self.subTest(status=status):
                result = na.analyze(data, {}, AS_OF)
                self.assertEqual(len(result['records']), 1)
                self.assertFalse(result['records'][0]['issuer_sentiment_usable_for_research'])
                self.assertEqual(result['unique_headline_cluster_counts'], {})
                self.assertEqual(result['source_gaps_or_unpolled'][0]['status'], status)

    def test_guidance_preannouncement_and_material_risks_are_review_hints(self):
        row = record('Demo raises revenue guidance', summary='Preliminary results, convertible offering and litigation')
        result = na.analyze(report([row]), {}, AS_OF)
        events = result['records'][0]['review_events']
        self.assertIn('GUIDANCE_RAISE_HINT', events)
        self.assertIn('PREANNOUNCEMENT_REVIEW', events)
        self.assertIn('FINANCING_REVIEW', events)
        self.assertIn('MATERIAL_RISK_REVIEW', events)
        self.assertFalse(result['alpha_validated'])
        self.assertFalse(result['execution_authorized'])
        self.assertTrue(result['records'][0]['requires_primary_review'])

    def test_lookback_filters_old_disclosures_and_reports_access_gaps(self):
        old = record('Old release', published_at='2026-10-01T14:00:00Z', observed='2026-10-01T14:30:00Z')
        data = report([old])
        data['sources'].extend([{'source_id': 'wire', 'status': 'ACCESS_DENIED'},
                                {'source_id': 'gdelt', 'status': 'NOT_DUE'}])
        result = na.analyze(data, {}, AS_OF, lookback_hours=24)
        self.assertEqual(result['records'], [])
        self.assertEqual({r['source_id'] for r in result['source_gaps_or_unpolled']}, {'wire', 'gdelt'})
        for invalid in (0, -1, float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                na.analyze(data, {}, AS_OF, invalid)

    def test_new_revision_without_updated_time_survives_old_original_dateline(self):
        old = record('Demo guidance update', summary='Prior range',
                     published_at='2026-10-01T14:00:00Z', observed='2026-10-01T14:30:00Z')
        revised = record('Demo guidance update', summary='Corrected range withdrawn',
                         published_at='2026-10-01T14:00:00Z', observed='2026-10-12T14:30:00Z')
        result = na.analyze(report([old, revised]), {}, AS_OF, lookback_hours=24)
        self.assertEqual([r['event_id'] for r in result['records']], [revised['event_id']])
        self.assertEqual(result['records'][0]['published_at'], '2026-10-01T14:00:00Z')
        self.assertIsNone(result['records'][0]['updated_at'])
        self.assertEqual(result['records'][0]['first_seen_at'], '2026-10-12T14:30:00Z')

    def test_newly_discovered_old_or_undated_news_is_reviewable_but_not_fresh_sentiment(self):
        for published in ('2026-10-01T14:00:00Z', None):
            r = record('Demo Industries growth', published_at=published, observed='2026-10-12T14:30:00Z')
            with self.subTest(published=published):
                result = na.analyze(report([r]), {}, AS_OF, lookback_hours=24)
                self.assertEqual(len(result['records']), 1)
                reviewed = result['records'][0]
                self.assertEqual(reviewed['recency_basis'], 'RECENT_OBSERVATION_OLD_OR_UNKNOWN_DATELINE')
                self.assertEqual(reviewed['published_at'], published)
                self.assertFalse(reviewed['issuer_sentiment_usable_for_research'])
                self.assertEqual(result['unique_headline_cluster_counts'], {})

    def test_exchange_feed_same_url_does_not_collapse_distinct_halt_items(self):
        rows = []
        for ticker in ('DEMO', 'TEST'):
            r = record('Trading halt', source_id='exchange', published_at=None,
                       source_item_id=ticker + '|10/12/2026|10:45:00',
                       event_at='2026-10-12T14:45:00Z', evidence_kind='EXCHANGE_STATUS_EVENT',
                       exchange_fields={'IssueSymbol': ticker, 'ReasonCode': 'T7',
                                        'ResumptionQuoteTime': '11:10:00', 'ResumptionTradeTime': ''})
            r['source_kind'], r['scope_issuers'] = 'exchange', []
            rows.append(r)
        result = na.analyze(report(rows), {}, AS_OF)
        self.assertEqual(len(result['records']), 2)
        self.assertEqual({r['issuers'][0] for r in result['records']}, {'DEMO', 'TEST'})
        self.assertTrue(all('VERIFY_CURRENT_HALT_AND_TRADE_RESUMPTION' in r['review_events'] for r in result['records']))
        self.assertEqual(result['unique_headline_cluster_counts'], {})

    def test_frozen_replay_is_deterministic_and_does_not_mutate_input(self):
        data = report([record()])
        original = copy.deepcopy(data)
        result = na.analyze(data, {}, AS_OF)
        self.assertEqual(result, na.analyze(copy.deepcopy(data), {}, AS_OF))
        self.assertEqual(data, original)


class GuidanceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.previous = self.guidance('prior', '2026-10-01T12:00:00Z', 100, 120)
        self.current = self.guidance('current', '2026-10-10T12:00:00Z', 110, 130)

    def guidance(self, name, published, low, high):
        text = 'Fictional company guidance evidence: range reviewed by a human.'
        path = self.root / (name + '.txt')
        path.write_text(text, encoding='utf-8')
        return {'issuer': 'DEMO', 'metric': 'revenue', 'period_start': '2027-01-01',
                'period_end': '2027-12-31', 'currency': 'USD', 'unit': 'millions',
                'accounting_basis': 'GAAP', 'status': 'issued', 'low': low, 'high': high,
                'source': {'source_kind': 'issuer', 'path': path.name, 'sha256': ns.digest(path.read_bytes()),
                           'url': 'https://issuer.example/' + name, 'published_at': published,
                           'observed_at': published, 'verbatim_excerpt': 'range reviewed by a human',
                           'locator': 'Guidance paragraph'}}

    def compare(self, old=None, new=None):
        return na.guidance_change({'as_of': AS_OF, 'previous': self.previous if old is None else old,
                                   'current': self.current if new is None else new}, self.root)

    def test_range_change_arithmetic_preserves_overlap_and_no_price_prediction(self):
        result = self.compare()
        self.assertEqual(result['classification'], 'RAISED_RANGE')
        self.assertEqual(result['previous_midpoint'], 110)
        self.assertEqual(result['current_midpoint'], 120)
        self.assertAlmostEqual(result['midpoint_change_pct'], 100 / 11)
        self.assertTrue(result['ranges_overlap'])
        self.assertEqual(result['economic_direction'], 'REQUIRES_METRIC_AND_CONTEXT_REVIEW')
        self.assertFalse(result['execution_authorized'])
        for bounds, label in (((90, 110), 'LOWERED_RANGE'), ((90, 130), 'MIXED_RANGE_CHANGE'),
                              ((100, 120), 'UNCHANGED_RANGE')):
            new = dict(self.current, low=bounds[0], high=bounds[1])
            self.assertEqual(self.compare(new=new)['classification'], label)

    def test_forecast_dimensions_cannot_be_silently_combined(self):
        for field, value in (('issuer', 'OTHER'), ('metric', 'EPS'), ('currency', 'EUR'),
                             ('unit', 'billions'), ('accounting_basis', 'adjusted'),
                             ('period_end', '2028-12-31')):
            with self.subTest(field=field):
                result = self.compare(new=dict(self.current, **{field: value}))
                self.assertEqual(result['classification'], 'NOT_COMPARABLE')
                self.assertNotIn('midpoint_change_pct', result)

    def test_withdrawal_reissue_and_nonpositive_baseline_do_not_invent_percent_change(self):
        withdrawn = {k: v for k, v in dict(self.current, status='withdrawn').items() if k not in ('low', 'high')}
        self.assertEqual(self.compare(new=withdrawn)['classification'], 'WITHDRAWN')
        first = na.guidance_change({'as_of': AS_OF, 'current': self.current}, self.root)
        self.assertEqual(first['classification'], 'ISSUED')
        reissue = self.compare(old=dict(self.previous, status='withdrawn'))
        self.assertEqual(reissue['classification'], 'ISSUED')
        for lo, hi in ((-10, 10), (-20, -10)):
            result = self.compare(old=dict(self.previous, low=lo, high=hi))
            self.assertIsNone(result['midpoint_change_pct'])

    def test_numeric_period_and_primary_source_guards(self):
        invalid = [dict(self.current, low=True), dict(self.current, high=float('inf')),
                   dict(self.current, low=140), dict(self.current, period_start='2028-01-01'),
                   dict(self.current, period_end='not a date'), dict(self.current, unit='')]
        secondary = copy.deepcopy(self.current)
        secondary['source']['source_kind'] = 'news_vendor'
        invalid.append(secondary)
        for new in invalid:
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.compare(new=new)

    def test_saved_source_hash_excerpt_and_path_must_verify(self):
        for key, value in (('sha256', '0' * 64), ('path', '../outside.txt'),
                           ('verbatim_excerpt', 'This sentence was never in the saved source'),
                           ('locator', ''), ('url', 'http://issuer.example/release')):
            source = dict(self.current['source'], **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                na.evidence(source, self.root, ns.stamp(AS_OF))
        (self.root / 'empty.txt').write_bytes(b'')
        empty = dict(self.current['source'], path='empty.txt', sha256=ns.digest(b''))
        with self.assertRaises(ValueError):
            na.evidence(empty, self.root, ns.stamp(AS_OF))

    def test_disclosures_must_be_available_in_order_at_information_cutoff(self):
        for field in ('published_at', 'observed_at'):
            new = copy.deepcopy(self.current)
            new['source'][field] = '2026-10-13T12:00:00Z'
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'not available'):
                self.compare(new=new)
        new = copy.deepcopy(self.current)
        new['source']['published_at'] = self.previous['source']['published_at']
        with self.assertRaisesRegex(ValueError, 'must be later'):
            self.compare(new=new)

    def test_source_cannot_be_observed_before_its_publication(self):
        source = dict(self.current['source'], observed_at='2026-10-09T12:00:00Z')
        with self.assertRaisesRegex(ValueError, 'observed before'):
            na.evidence(source, self.root, ns.stamp(AS_OF))


if __name__ == '__main__':
    unittest.main()
