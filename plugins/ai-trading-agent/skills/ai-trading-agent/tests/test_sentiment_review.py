import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from sentiment_review import review, DIMENSIONS


def fixture():
    stamp = '2026-10-20T20:00:00Z'
    source = {'url': 'https://issuer.example/release', 'observed_at': stamp}
    triage = {'as_of': stamp, 'records': [{'event_id': 'a', 'cluster_id': 'one',
              'language': {'label': 'UNSCORED', 'hits': []}, 'first_seen_at': stamp}]}
    document = {'as_of': stamp, 'window_start': '2026-10-19T20:00:00Z',
                'dimensions': {d: {'status': 'reviewed', 'evidence': [source],
                   'interpretation': 'Reviewer assessment based on supplied source.'} for d in DIMENSIONS},
                'event_reviews': [{'event_id': 'a', 'interpretation': 'Positive qualitative business development.',
                                  'evidence': [source]}], 'conclusion': 'Qualitatively positive; no return forecast.'}
    return triage, document


class SentimentReviewTests(unittest.TestCase):
    def test_unscored_can_have_positive_review_without_computed_signal(self):
        triage, document = fixture()
        original = copy.deepcopy(triage)
        result = review(triage, document)
        self.assertEqual(result['event_reviews'][0]['automatic_language']['label'], 'UNSCORED')
        self.assertIn('Positive', result['event_reviews'][0]['reviewer_interpretation'])
        self.assertIsNone(result['computed_sentiment_score'])
        self.assertEqual(result['execution_permission_effect'], 'NONE_RESEARCH_ONLY')
        self.assertEqual(triage, original)

    def test_credential_bearing_evidence_url_rejected(self):
        triage, document = fixture()
        document['event_reviews'][0]['evidence'][0]['url'] = 'https://user:secret' + '@' + 'issuer.example/release'
        with self.assertRaisesRegex(ValueError, 'INVALID_EVIDENCE_URL'):
            review(triage, document)

    def test_missing_evidence_rejected(self):
        t, d = fixture(); d['event_reviews'][0]['evidence'] = []
        with self.assertRaisesRegex(ValueError, 'EVIDENCE_REQUIRED'): review(t, d)

    def test_unknown_event_rejected(self):
        t, d = fixture(); d['event_reviews'][0]['event_id'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'UNKNOWN_EVENT'): review(t, d)

    def test_syndicated_group_cannot_be_counted_twice(self):
        t, d = fixture(); t['records'].append({**t['records'][0], 'event_id': 'b'})
        d['event_reviews'].append({**d['event_reviews'][0], 'event_id': 'b'})
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_EVENT_GROUP'): review(t, d)
        d['event_reviews'].pop()
        self.assertEqual(review(t, d)['unreviewed_event_groups'], [])

    def test_future_observation_rejected(self):
        t, d = fixture(); d['event_reviews'][0]['evidence'] = [{'url': 'https://issuer.example/release', 'observed_at': '2026-10-21T00:00:00Z'}]
        with self.assertRaisesRegex(ValueError, 'FUTURE_OBSERVATION'): review(t, d)

    def test_material_unattempted_is_incomplete(self):
        t, d = fixture(); d['dimensions']['positioning'] = {'status': 'not_attempted', 'reason': 'Awaiting review'}
        d['required_dimensions'] = ['news', 'analyst', 'positioning']
        self.assertEqual(review(t, d)['coverage_status'], 'INCOMPLETE')

    def test_optional_social_limitation_is_partial(self):
        t, d = fixture(); d['dimensions']['social'] = {'status': 'unavailable', 'reason': 'Provider requires unavailable licensed access'}
        self.assertEqual(review(t, d)['coverage_status'], 'PARTIAL')

    def test_unreviewed_no_hit_event_blocks_complete_coverage(self):
        t, d = fixture(); t['records'].append({**t['records'][0], 'event_id': 'b', 'cluster_id': 'two'})
        self.assertEqual(review(t, d)['coverage_status'], 'INCOMPLETE')

    def test_missing_dimension_cannot_disappear(self):
        t, d = fixture(); del d['dimensions']['social']
        with self.assertRaisesRegex(ValueError, 'ALL_FIVE'): review(t, d)

    def test_cutoff_mismatch_rejected(self):
        t, d = fixture(); d['as_of'] = '2026-10-21T20:00:00Z'
        with self.assertRaisesRegex(ValueError, 'CUTOFF_MISMATCH'): review(t, d)

    def test_unavailable_required_dimension_is_partial_not_stop_gate(self):
        t, d = fixture(); d['dimensions']['analyst'] = {'status': 'unavailable', 'reason': 'Licensed source inaccessible'}
        self.assertEqual(review(t, d)['coverage_status'], 'PARTIAL')

    def test_paraphrased_events_can_share_one_interpretation(self):
        t, d = fixture(); t['records'].append({**t['records'][0], 'event_id': 'b', 'cluster_id': 'paraphrase'})
        d['event_reviews'][0].update(event_ids=['a', 'b'], event_group_id='same-economic-event')
        result = review(t, d)
        self.assertEqual(len(result['event_reviews']), 1)
        self.assertEqual(result['unreviewed_event_groups'], [])

    def test_undeclared_not_attempted_remains_disclosed(self):
        t, d = fixture(); d['dimensions']['social'] = {'status': 'not_attempted', 'reason': 'Outside declared scope'}
        self.assertEqual(review(t, d)['coverage_status'], 'PARTIAL')

    def test_old_failed_context_does_not_become_fresh_by_review(self):
        t, d = fixture()
        t['records'][0].update(recency_basis='RECENT_OBSERVATION_OLD_OR_UNKNOWN_DATELINE',
            issuer_sentiment_usable_for_research=False, flags=['UNKNOWN_PUBLICATION_TIME'],
            source_refresh_status='FAILED')
        result = review(t, d)
        context = result['event_reviews'][0]['source_context_by_event']['a']
        self.assertFalse(context['issuer_sentiment_usable_for_research'])
        self.assertEqual(context['source_refresh_status'], 'FAILED')
        self.assertEqual(context['flags'], ['UNKNOWN_PUBLICATION_TIME'])
        self.assertEqual(context['recency_basis'], 'RECENT_OBSERVATION_OLD_OR_UNKNOWN_DATELINE')

    def test_observation_before_publication_rejected(self):
        t, d = fixture()
        d['event_reviews'][0]['evidence'] = [{'url': 'https://issuer.example/release',
            'observed_at': '2026-10-20T18:00:00Z', 'published_at': '2026-10-20T19:00:00Z'}]
        with self.assertRaisesRegex(ValueError, 'OBSERVATION_PRECEDES_PUBLICATION'): review(t, d)

    def test_malformed_evidence_clean_error(self):
        t, d = fixture(); d['event_reviews'][0]['evidence'] = ['not-an-object']
        with self.assertRaisesRegex(ValueError, 'INVALID_EVIDENCE_RECORD'): review(t, d)


if __name__ == '__main__':
    unittest.main()
