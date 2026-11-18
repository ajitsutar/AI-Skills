"""Portable synthetic retained-notice regressions; no acquisition or broker calls."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import halt_review as hr
import news_evidence as ne


class HaltReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        common = {'halt_event_time': '2033-05-04T08:09:00Z',
                  'feed_dateline': '2033-05-04T00:00:00Z', 'reason': 'pending_update',
                  'quote_resume_at': None, 'trade_resume_at': None}
        self.doc = {'symbol': 'SYNTH', 'exchange': 'EXAMPLE', 'messages': [
            dict(common, message_id='alpha', published_at='2033-05-04T08:10:00Z'),
            dict(common, message_id='beta', published_at='2033-05-04T08:25:00Z',
                 reason='update_released', quote_resume_at='2033-05-04T08:29:00Z'),
            dict(common, message_id='gamma', published_at='2033-05-04T08:31:00Z',
                 reason='update_released', quote_resume_at='2033-05-04T08:29:00Z',
                 trade_resume_at='2033-05-04T08:35:00Z')]}
        self.scope = {'as_of': '2033-05-04T08:30:00Z'}
        self.request = {'source': {'path': 'notices.json', 'sha256': ''}, 'collection_pointer': '/messages',
                        'as_of': {'source': {'path': 'scope.json', 'sha256': ''}, 'pointer': '/as_of'}}
        self.save()

    def save(self):
        for data, path, ref in [(self.doc, self.root/'notices.json', self.request['source']),
                                (self.scope, self.root/'scope.json', self.request['as_of']['source'])]:
            path.write_text(json.dumps(data), encoding='utf-8')
            ref['sha256'] = hr.digest(path.read_bytes())

    def review(self):
        self.save()
        return hr.review(self.request, self.root)

    def test_future_notice_does_not_fill_cutoff_trade_schedule(self):
        before = (self.root/'notices.json').read_bytes()
        out = hr.review(self.request, self.root)
        self.assertEqual(out['publication_view']['selected_message_id'], 'beta')
        self.assertIsNone(out['publication_view']['trade_resumption']['scheduled_at'])
        self.assertEqual(out['publication_view']['excluded'][0]['reasons'], ['PUBLICATION_AFTER_CUTOFF'])
        self.assertEqual(len(out['all_notices']), 3)
        self.assertEqual((self.root/'notices.json').read_bytes(), before)

    def test_unknown_observation_never_becomes_publication(self):
        out = self.review()
        self.assertIsNone(out['observed_view']['selected_message_id'])
        self.assertEqual(out['publication_view']['basis'], 'SOURCE_PUBLICATION_ONLY')
        self.assertEqual(out['all_notices'][1]['observation_clocks'], {})

    def test_known_observation_after_cutoff_only_affects_observed_view(self):
        self.doc['messages'][0]['observed_at'] = '2033-05-04T08:11:00Z'
        self.doc['messages'][1]['observed_at'] = '2033-05-04T08:32:00Z'
        out = self.review()
        self.assertEqual(out['publication_view']['selected_message_id'], 'beta')
        self.assertEqual(out['observed_view']['selected_message_id'], 'alpha')
        self.assertIn('OBSERVATION_AFTER_CUTOFF', out['observed_view']['excluded'][0]['reasons'])

    def test_all_observation_clocks_checked(self):
        self.doc['messages'][1].update(observed_at='2033-05-04T08:26:00Z', first_seen_at='2033-05-04T08:33:00Z')
        self.assertIsNone(self.review()['observed_view']['selected_message_id'])

    def test_observation_before_publication_rejected(self):
        self.doc['messages'][1]['observed_at'] = '2033-05-04T08:20:00Z'
        with self.assertRaisesRegex(ValueError, 'OBSERVATION_PRECEDES_PUBLICATION'):
            self.review()

    def test_late_retrieval_does_not_change_notice_publication_order(self):
        self.doc['messages'][0]['observed_at'] = '2033-05-04T08:29:00Z'
        self.doc['messages'][1]['observed_at'] = '2033-05-04T08:26:00Z'
        self.assertEqual(self.review()['observed_view']['selected_message_id'], 'beta')

    def test_exact_cutoff_inclusive_and_microsecond_later_excluded(self):
        self.doc['messages'][2]['published_at'] = self.scope['as_of']
        self.assertEqual(self.review()['publication_view']['selected_message_id'], 'gamma')
        self.doc['messages'][2]['published_at'] = '2033-05-04T08:30:00.000001Z'
        self.assertEqual(self.review()['publication_view']['selected_message_id'], 'beta')

    def test_offset_timestamps_order_by_instant(self):
        self.doc['messages'][0]['published_at'] = '2033-05-04T09:10:00+01:00'
        self.assertEqual(self.review()['publication_view']['selected_message_id'], 'beta')

    def test_order_permutations_keep_same_selection_and_complete_inventory(self):
        self.doc['messages'].reverse()
        out = self.review()
        self.assertEqual(out['publication_view']['selected_message_id'], 'beta')
        self.assertEqual(out['publication_view']['selected_source_pointer'], '/messages/1')
        self.assertEqual([r['message_id'] for r in out['all_notices']], ['alpha', 'beta', 'gamma'])
        self.assertEqual({r['source_pointer'] for r in out['all_notices']}, {'/messages/0', '/messages/1', '/messages/2'})

    def test_equal_instant_latest_notices_are_ambiguous(self):
        self.doc['messages'][0]['published_at'] = '2033-05-04T09:25:00+01:00'
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS_LATEST'):
            self.review()

    def test_future_schedule_announced_by_eligible_notice_is_retained(self):
        self.doc['messages'][1]['trade_resume_at'] = '2033-05-04T08:35:00Z'
        out = self.review()['publication_view']
        self.assertEqual(out['trade_resumption']['relative_to_cutoff'], 'AFTER')
        self.assertEqual(out['announcement_state'], 'TRADE_RESUMPTION_SCHEDULE_IN_SELECTED_NOTICE')
        self.assertFalse(out['trade_resumption']['actual_activity_verified'])

    def test_elapsed_schedule_never_proves_execution_or_broker_clearance(self):
        self.scope['as_of'] = '2033-05-04T09:00:00Z'
        out = self.review()
        self.assertEqual(out['publication_view']['trade_resumption']['relative_to_cutoff'], 'BEFORE')
        self.assertIsNone(out['publication_view']['trades_observed'])
        self.assertIsNone(out['publication_view']['broker_clearance'])
        for key in ('source_authenticity_verified', 'live_exchange_status_verified', 'observed_execution_verified',
                    'execution_authorized', 'new_skill_gate_created'):
            self.assertFalse(out[key])

    def test_latest_null_does_not_carry_forward_previous_schedule(self):
        self.doc['messages'][0].update(quote_resume_at='2033-05-04T08:20:00Z', trade_resume_at='2033-05-04T08:22:00Z')
        self.assertIsNone(self.review()['publication_view']['trade_resumption']['scheduled_at'])

    def test_dateline_or_event_time_cannot_replace_missing_publication(self):
        del self.doc['messages'][1]['published_at']
        with self.assertRaisesRegex(ValueError, 'PUBLICATION_TIMESTAMP_REQUIRED'):
            self.review()

    def test_invalid_optional_and_naive_clock_rejected(self):
        for field, value in [('published_at', '2033-05-04T08:25:00'), ('feed_dateline', '2033-05-04'),
                             ('quote_resume_at', 'bad clock'), ('first_seen_at', '')]:
            with self.subTest(field=field):
                original = copy.deepcopy(self.doc)
                self.doc['messages'][1][field] = value
                with self.assertRaisesRegex(ValueError, 'INVALID_TIMEZONE_AWARE_TIMESTAMP'):
                    self.review()
                self.doc = original

    def test_duplicate_ids_rejected(self):
        self.doc['messages'][2]['message_id'] = 'alpha'
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_MESSAGE_ID'):
            self.review()

    def test_other_symbol_exchange_or_halt_episode_rejected(self):
        for field, value, error in [('symbol', 'OTHER', 'SYMBOL_MISMATCH'),
                                     ('exchange', 'OTHER', 'EXCHANGE_MISMATCH'),
                                     ('halt_event_time', '2033-05-04T08:08:00Z', 'MULTIPLE_HALT_EPISODES')]:
            with self.subTest(field=field):
                original = copy.deepcopy(self.doc)
                self.doc['messages'][1][field] = value
                with self.assertRaisesRegex(ValueError, error):
                    self.review()
                self.doc = original

    def test_resumption_clock_contradictions_rejected(self):
        for value, error in [('2033-05-04T08:08:00Z', 'PRECEDES_HALT_EVENT'),
                             ('2033-05-04T08:28:00Z', 'PRECEDES_QUOTE_RESUMPTION')]:
            self.doc['messages'][1]['trade_resume_at'] = value
            with self.assertRaisesRegex(ValueError, error):
                self.review()

    def test_source_hash_tampering_and_path_escape_rejected(self):
        self.request['source']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            hr.review(self.request, self.root)
        self.request['source']['path'] = '../notices.json'
        with self.assertRaisesRegex(ValueError, 'UNSAFE_SOURCE_PATH'):
            hr.review(self.request, self.root)

    def test_scope_hash_tampering_and_value_override_rejected(self):
        self.request['as_of']['source']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            hr.review(self.request, self.root)
        self.save()
        self.request['as_of']['value'] = '2033-05-04T09:00:00Z'
        with self.assertRaisesRegex(ValueError, 'SOURCE_BOUND_AS_OF_REQUIRED'):
            hr.review(self.request, self.root)

    def test_cutoff_role_and_collection_subset_overrides_rejected(self):
        self.request['as_of']['pointer'] = '/published_at'
        with self.assertRaisesRegex(ValueError, 'AS_OF_ROLE_BINDING_REQUIRED'):
            hr.review(self.request, self.root)
        self.request['as_of']['pointer'] = '/as_of'
        self.request['message_ids'] = ['alpha', 'beta']
        with self.assertRaisesRegex(ValueError, 'REQUEST_FIELDS'):
            hr.review(self.request, self.root)
        del self.request['message_ids']
        self.request['collection_pointer'] = '/messages/0'
        with self.assertRaisesRegex(ValueError, 'TOP_LEVEL_MESSAGE_COLLECTION_REQUIRED'):
            hr.review(self.request, self.root)

    def test_nested_collection_cannot_inherit_root_identity(self):
        messages = self.doc.pop('messages')
        for nested_symbol, nested_exchange in [('OTHER', 'OTHER_EXCHANGE'), ('SYNTH', 'EXAMPLE')]:
            with self.subTest(nested_symbol=nested_symbol):
                self.doc['archive'] = {'symbol': nested_symbol, 'exchange': nested_exchange, 'messages': messages}
                self.request['collection_pointer'] = '/archive/messages'
                self.save()
                original = (self.root/'notices.json').read_bytes()
                with self.assertRaisesRegex(ValueError, 'TOP_LEVEL_MESSAGE_COLLECTION_REQUIRED'):
                    hr.review(self.request, self.root)
                self.assertEqual((self.root/'notices.json').read_bytes(), original)

    def test_escaped_root_field_is_still_same_identity_scope(self):
        self.doc['notices/current'] = self.doc.pop('messages')
        self.request['collection_pointer'] = '/notices~1current'
        out = self.review()
        self.assertEqual(out['publication_view']['selected_message_id'], 'beta')
        self.assertEqual(out['publication_view']['selected_notice']['symbol'], 'SYNTH')
        self.assertEqual(out['publication_view']['selected_source_pointer'], '/notices~1current/1')

    def test_empty_collection_and_duplicate_json_keys_rejected(self):
        self.doc['messages'] = []
        with self.assertRaisesRegex(ValueError, 'MESSAGE_COLLECTION_REQUIRED'):
            self.review()
        path = self.root/'notices.json'
        path.write_text('{"symbol":"A","symbol":"B","messages":[]}', encoding='utf-8')
        self.request['source']['sha256'] = hr.digest(path.read_bytes())
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
            hr.review(self.request, self.root)

    def test_all_notices_after_cutoff_has_no_selected_notice(self):
        self.scope['as_of'] = '2033-05-04T08:00:00Z'
        out = self.review()['publication_view']
        self.assertIsNone(out['selected_message_id'])
        self.assertEqual(out['announcement_state'], 'NO_ELIGIBLE_NOTICE')

    def test_saved_claim_audit_rejects_future_schedule_attribution(self):
        path = self.root/'output.json'
        path.write_text(json.dumps(self.review()), encoding='utf-8')
        result = ne.audit_claims({'output': {'path': path.name, 'sha256': hr.digest(path.read_bytes())},
                                 'claims': [{'id': 'future-borrow', 'pointer': '/publication_view/trade_resumption/scheduled_at',
                                             'value': '2033-05-04T08:35:00Z'}]}, self.root)
        self.assertEqual(result['status'], 'CLAIM_MISMATCH')

    def test_cli_exclusive_output_preserves_prior_result(self):
        req, out = self.root/'request.json', self.root/'result.json'
        req.write_text(json.dumps(self.request), encoding='utf-8')
        command = [sys.executable, '-B', hr.__file__, str(req), str(self.root), str(out)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        before = out.read_bytes()
        self.assertEqual(json.loads(before)['publication_view']['selected_message_id'], 'beta')
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(out.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
