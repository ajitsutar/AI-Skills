"""Point-in-time admission for imported reports; no live feeds or dates invented."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_analysis as na
from test_news_analysis import record, report, AS_OF


class NewsAvailabilityTests(unittest.TestCase):
    def analyze(self, row, cutoff=AS_OF):
        return na.analyze(report([row]), {}, cutoff)

    def test_future_publication_cannot_be_backdated_by_available_at(self):
        row = record(published_at='2026-10-12T16:00:00Z')
        row['available_at'] = '2026-10-12T14:30:00Z'
        row['flags'] = []  # Imported report also omits the normalizer's future flag.
        before = copy.deepcopy(row)
        result = self.analyze(row)
        self.assertEqual(result['records'], [])
        self.assertEqual(result['unique_headline_cluster_counts'], {})
        self.assertEqual(result['excluded'], [{'event_id': row['event_id'], 'reason': 'NOT_YET_OBSERVED_OR_FUTURE_DATED'}])
        self.assertEqual(row, before)

    def test_later_available_at_still_controls_old_publication(self):
        row = record(observed='2026-10-12T16:00:00Z')
        self.assertEqual(self.analyze(row)['records'], [])
        self.assertEqual(len(self.analyze(row, '2026-10-12T16:00:00Z')['records']), 1)

    def test_other_known_times_cannot_be_backdated_by_available_at(self):
        for key in ('first_seen_at', 'updated_at', 'provider_seen_at', 'event_at'):
            row = record()
            row[key] = '2026-10-12T16:00:00Z'
            with self.subTest(key=key):
                self.assertEqual(self.analyze(row)['records'], [])
                self.assertEqual(self.analyze(row)['excluded'][0]['reason'], 'NOT_YET_OBSERVED_OR_FUTURE_DATED')

    def test_effective_availability_boundary_and_timezone_are_inclusive(self):
        row = record()
        row['published_at'] = '2026-10-12T08:00:00-07:00'
        row['available_at'] = '2026-10-12T14:30:00Z'
        self.assertEqual(self.analyze(row, '2026-10-12T14:59:59Z')['records'], [])
        included = self.analyze(row)['records']
        self.assertEqual(len(included), 1)
        self.assertEqual(included[0]['published_at'], row['published_at'])

    def test_future_revision_does_not_displace_earlier_eligible_revision(self):
        old = record('Original growth')
        future = record('Revised losses', published_at='2026-10-12T16:00:00Z')
        future['available_at'] = '2026-10-12T14:45:00Z'
        for rows in ([old, future], [future, old]):
            result = na.analyze(report(rows), {}, AS_OF)
            self.assertEqual([r['event_id'] for r in result['records']], [old['event_id']])
            self.assertEqual(result['unique_headline_cluster_counts'], {'DEMO': {'POSITIVE_LANGUAGE': 1}})

    def test_missing_publication_is_not_invented_or_fresh_sentiment(self):
        row = record(published_at=None)
        included = self.analyze(row)['records']
        self.assertEqual(len(included), 1)
        self.assertIsNone(included[0]['published_at'])
        self.assertFalse(included[0]['issuer_sentiment_usable_for_research'])
        self.assertEqual(included[0]['recency_basis'], 'RECENT_OBSERVATION_OLD_OR_UNKNOWN_DATELINE')
        del row['published_at']
        self.assertNotIn('published_at', self.analyze(row)['records'][0])

    def test_unknown_required_or_malformed_supplied_times_are_explicitly_excluded(self):
        for key in ('available_at', 'first_seen_at'):
            for value in (None, '', '2026-10-12', '2026-10-12T14:30:00', 'not a date'):
                row = record()
                row[key] = value
                with self.subTest(key=key, value=value):
                    result = self.analyze(row)
                    self.assertEqual(result['records'], [])
                    self.assertEqual(result['excluded'][0]['reason'], 'UNRESOLVED_AVAILABILITY_TIMESTAMP')
            row = record()
            del row[key]
            self.assertEqual(self.analyze(row)['excluded'][0]['reason'], 'UNRESOLVED_AVAILABILITY_TIMESTAMP')
        row = record()
        row['published_at'] = 'not a date'
        self.assertEqual(self.analyze(row)['excluded'][0]['reason'], 'UNRESOLVED_AVAILABILITY_TIMESTAMP')

    def test_optional_timestamps_may_all_be_absent_or_null(self):
        for missing in (False, True):
            row = record(published_at=None)
            for key in ('published_at', 'updated_at', 'provider_seen_at', 'event_at'):
                if missing:
                    row.pop(key, None)
                else:
                    row[key] = None
            result = self.analyze(row)
            self.assertEqual(len(result['records']), 1)
            self.assertEqual(result['unique_headline_cluster_counts'], {})
            self.assertEqual(result['excluded'], [])

    def assert_latest_in_both_input_orders(self, older, newer):
        for rows in ([older, newer], [newer, older]):
            original = copy.deepcopy(rows)
            result = na.analyze(report(rows), {}, AS_OF)
            self.assertEqual([r['event_id'] for r in result['records']], [newer['event_id']])
            for field in ('available_at', 'published_at', 'updated_at', 'first_seen_at'):
                self.assertEqual(result['records'][0].get(field), newer.get(field))
            self.assertEqual(rows, original)

    def test_two_eligible_revisions_rank_by_effective_availability(self):
        older = record('Older growth', observed='2026-10-12T14:30:00Z')
        newer = record('Newer losses', observed='2026-10-12T14:40:00Z',
                       updated_at='2026-10-12T14:35:00Z')
        newer['available_at'] = '2026-10-12T14:10:00Z'
        self.assert_latest_in_both_input_orders(older, newer)

    def test_availability_timezone_offset_ranks_by_instant(self):
        older = record('Older growth', observed='2026-10-12T14:20:00Z')
        newer = record('Newer losses', observed='2026-10-12T14:40:00Z')
        newer['available_at'] = '2026-10-12T07:40:00-07:00'
        self.assert_latest_in_both_input_orders(older, newer)

    def test_tied_availability_revision_timezone_offset_ranks_by_instant(self):
        older = record('Older growth', observed='2026-10-12T14:50:00Z', updated_at='2026-10-12T14:10:00Z')
        newer = record('Newer losses', observed='2026-10-12T14:50:00Z')
        newer['updated_at'] = '2026-10-12T07:30:00-07:00'
        self.assert_latest_in_both_input_orders(older, newer)

    def test_equivalent_time_spellings_use_event_id_tie_break(self):
        older = record('Tie a', observed='2026-10-12T14:50:00Z', updated_at='2026-10-12T14:30:00Z')
        newer = record('Tie z', observed='2026-10-12T14:50:00Z')
        older['event_id'], newer['event_id'] = 'a', 'z'
        newer['available_at'] = '2026-10-12T07:50:00-07:00'
        newer['updated_at'] = '2026-10-12T07:30:00-07:00'
        self.assert_latest_in_both_input_orders(older, newer)

    def test_output_order_uses_effective_instants_and_retains_source_strings(self):
        early = record('Early', url='https://issuer.example/early', observed='2026-10-12T14:20:00Z')
        late = record('Late', url='https://issuer.example/late', observed='2026-10-12T14:40:00Z')
        for claimed in ('2026-10-12T07:40:00-07:00', '2026-10-12T14:10:00Z'):
            late['available_at'] = claimed
            for rows in ([early, late], [late, early]):
                result = na.analyze(report(rows), {}, AS_OF)
                self.assertEqual([r['title'] for r in result['records']], ['Early', 'Late'])
                self.assertEqual(result['records'][1]['available_at'], claimed)

    def test_normalized_fractional_seconds_are_chronological(self):
        earlier = record('Earlier', observed='2026-10-12T14:30:00Z')
        later = record('Later', observed='2026-10-12T14:30:00.100000Z')
        self.assert_latest_in_both_input_orders(earlier, later)
        later['url'] = 'https://issuer.example/later'
        result = na.analyze(report([later, earlier]), {}, AS_OF)
        self.assertEqual([r['title'] for r in result['records']], ['Earlier', 'Later'])


if __name__ == '__main__':
    unittest.main()
