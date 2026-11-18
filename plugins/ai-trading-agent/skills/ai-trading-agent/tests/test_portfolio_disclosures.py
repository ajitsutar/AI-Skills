import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from portfolio_disclosures import normalize, changes, refresh_checkpoint
from portfolio_follower import build_targets


def event(**overrides):
    result = {'event_id': 'fictional:filing:row-1', 'source_ref': 'fixture:filing',
              'event_at': '2026-01-02T16:00:00Z', 'published_at': '2026-01-10T16:00:00Z',
              'available_at': '2026-01-10T16:01:00Z', 'revision': 0, 'withdrawn': False,
              'security_id': 'FICTIONAL-A', 'action': 'BUY', 'asset_type': 'common_stock',
              'identity_reviewed': True, 'source_reviewed': True, 'owner': 'spouse',
              'amount_range': {'lower': 1001, 'upper': 15000, 'currency': 'USD'}}
    result.update(overrides)
    return result


def transaction_doc(*events):
    return {'kind': 'public_transactions', 'as_of': '2026-01-12T00:00:00Z',
            'subject_id': 'fictional-family', 'events': list(events) or [event()]}


def table_row(cusip='000000001', value='100', option='', share_type='SH'):
    return ('<infoTable><nameOfIssuer>Fictional issuer</nameOfIssuer><titleOfClass>COM</titleOfClass>'
            f'<cusip>{cusip}</cusip><value>{value}</value><shrsOrPrnAmt><sshPrnamt>10</sshPrnamt>'
            f'<sshPrnamtType>{share_type}</sshPrnamtType></shrsOrPrnAmt>{option}</infoTable>')


def sec_doc(rows=None):
    rows = rows or [table_row()]
    xml = '<informationTable xmlns="urn:fixture">' + ''.join(rows) + '</informationTable>'
    meta = {key: value for key, value in event().items() if key in
            ('event_id', 'source_ref', 'event_at', 'published_at', 'available_at', 'revision', 'withdrawn')}
    meta.update(form='13F-HR', amendment_type='none', currency='USD', value_unit='USD',
                source_reviewed=True, reported_table_complete=True, expected_table_entry_count=len(rows),
                expected_table_value=100 * len(rows), table_sha256=hashlib.sha256(xml.encode()).hexdigest())
    return {'kind': 'sec_13f', 'as_of': '2026-01-12T00:00:00Z', 'subject_id': 'fictional-manager',
            'source': meta, 'information_table_xml': xml,
            'security_map': [{'cusip': '000000001', 'security_id': 'FICTIONAL-A',
                              'asset_type': 'common_stock', 'source_ref': 'fixture:identity',
                              'valid_from': '2020-01-01T00:00:00Z', 'valid_to': None,
                              'available_at': '2020-01-01T00:00:00Z'}]}


class DisclosureTests(unittest.TestCase):
    def test_range_kept_not_midpoint(self):
        result = normalize(transaction_doc())
        row = result['records'][0]
        self.assertEqual(row['amount_range'], {'lower': '1001', 'upper': '15000', 'currency': 'USD'})
        self.assertIsNone(row['actual_portfolio_weight'])
        self.assertIsNone(row['exact_quantity'])
        self.assertEqual(row['owner'], 'spouse')

    def test_open_ended_range_retained(self):
        row = normalize(transaction_doc(event(amount_range={'lower': 1000000, 'upper': None, 'currency': 'USD'})))['records'][0]
        self.assertIsNone(row['amount_range']['upper'])

    def test_partial_sale_not_full(self):
        row = normalize(transaction_doc(event(action='PARTIAL_SELL')))['records'][0]
        self.assertEqual((row['action'], row['sale_scope']), ('SELL', 'partial'))

    def test_unsupported_exchange_not_sale(self):
        result = normalize(transaction_doc(event(action='EXCHANGE')))
        self.assertEqual(result['records'], [])
        self.assertEqual(result['status'], 'unavailable')

    def test_options_unqualified_for_long_stock(self):
        row = normalize(transaction_doc(event(asset_type='call_option')))['records'][0]
        self.assertFalse(row['eligible_common'])
        self.assertFalse(row['qualifying'])

    def test_future_disclosure_excluded(self):
        result = normalize(transaction_doc(event(available_at='2026-01-13T00:00:00Z')))
        self.assertEqual(result['records'], [])

    def test_time_order_required(self):
        with self.assertRaisesRegex(ValueError, 'CLOCKS'):
            normalize(transaction_doc(event(event_at='2026-01-11T00:00:00Z')))

    def test_naive_time_rejected(self):
        with self.assertRaises(ValueError):
            normalize(transaction_doc(event(available_at='2026-01-11')))

    def test_negative_or_inverted_range_rejected(self):
        for limits in [(-1, 100), (100, 1)]:
            with self.assertRaises(ValueError):
                normalize(transaction_doc(event(amount_range={'lower': limits[0], 'upper': limits[1], 'currency': 'USD'})))

    def test_duplicate_event_deduplicated(self):
        result = normalize(transaction_doc(event(), event()))
        self.assertEqual(len(result['records']), 1)

    def test_conflict_not_silently_resolved(self):
        result = normalize(transaction_doc(event(), event(action='SELL')))
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any('CONFLICTING' in reason for reason in result['warnings']))

    def test_cramer_quote_requires_original_qualified_recommendation(self):
        doc = transaction_doc(event(speaker='fictional-presenter', speaker_verified=True,
                                    recommendation_verified=True, source_context='headline'))
        doc['kind'] = 'public_recommendations'
        self.assertFalse(normalize(doc)['records'][0]['qualifying'])
        doc['events'][0]['source_context'] = 'original_recommendation'
        self.assertTrue(normalize(doc)['records'][0]['qualifying'])

    def test_sec_explicit_units(self):
        doc = sec_doc()
        self.assertEqual(normalize(doc)['records'][0]['positions'][0]['market_value'], '100')
        doc['source']['value_unit'] = 'USD_thousands'
        self.assertEqual(normalize(doc)['records'][0]['positions'][0]['market_value'], '100000')
        del doc['source']['value_unit']
        with self.assertRaises(KeyError):
            normalize(doc)

    def test_sec_options_value_excluded(self):
        doc = sec_doc([table_row(), table_row(option='<putCall>PUT</putCall>')])
        result = normalize(doc)
        self.assertEqual(result['status'], 'normalized')
        self.assertEqual(len(result['records'][0]['positions']), 1)
        self.assertEqual(result['excluded_rows'][0]['reason'], 'OPTION_OR_NON_SHARE_EXCLUDED_FROM_COMMON_BASKET')

    def test_sec_unmapped_identity_makes_partial_basket(self):
        doc = sec_doc([table_row(cusip='000000002')])
        result = normalize(doc)
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['records'][0]['complete_reported_basket'])
        self.assertEqual(result['records'][0]['positions'], [])

    def test_sec_future_mapping_not_used(self):
        doc = sec_doc()
        doc['security_map'][0]['available_at'] = '2027-01-01T00:00:00Z'
        self.assertFalse(normalize(doc)['records'][0]['complete_reported_basket'])

    def test_sec_mapping_publication_delays_usable_record(self):
        doc = sec_doc()
        doc['security_map'][0]['available_at'] = '2026-01-11T00:00:00Z'
        self.assertEqual(normalize(doc)['records'][0]['available_at'], '2026-01-11T00:00:00+00:00')

    def test_sec_ambiguous_mapping_rejected(self):
        doc = sec_doc()
        doc['security_map'].append(copy.deepcopy(doc['security_map'][0]))
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS'):
            normalize(doc)

    def test_cover_count_and_total_checked(self):
        for key in ('expected_table_value', 'expected_table_entry_count'):
            doc = sec_doc()
            doc['source'][key] += 1
            result = normalize(doc)
            self.assertFalse(result['records'][0]['complete_reported_basket'])

    def test_sec_notice_not_liquidation(self):
        doc = sec_doc()
        doc['source']['form'] = '13F-NT'
        result = normalize(doc)
        self.assertEqual(result['records'], [])
        self.assertIn('NOTICE_ONLY_FOLLOW_REPORTING_MANAGER_NOT_LIQUIDATION', result['warnings'])

    def test_supplement_not_full_replacement(self):
        doc = sec_doc()
        doc['source'].update(form='13F-HR/A', amendment_type='new_holdings')
        self.assertEqual(normalize(doc)['records'], [])
        doc['source']['amendment_type'] = 'restatement'
        self.assertTrue(normalize(doc)['records'][0]['complete_reported_basket'])

    def test_xml_hash_and_entity_checks(self):
        doc = sec_doc()
        doc['information_table_xml'] += ' '
        with self.assertRaisesRegex(ValueError, 'HASH'):
            normalize(doc)
        doc['information_table_xml'] = '<!DOCTYPE x>' + doc['information_table_xml']
        with self.assertRaisesRegex(ValueError, 'DECLARATIONS'):
            normalize(doc)

    def test_sec_adapter_engine_contract(self):
        doc = sec_doc()
        records = normalize(doc)['records']
        result = build_targets({'as_of': doc['as_of'], 'currency': 'USD', 'max_position_weight': 1,
                                'sleeves': [{'id': 'fictional', 'subject_id': doc['subject_id'],
                                             'mode': 'snapshot', 'budget_weight': 1, 'current_weights': {},
                                             'source_status': 'verified', 'checked_at': doc['as_of'],
                                             'max_age_days': 90, 'records': records}]})
        self.assertEqual(result['target_weights'], {'FICTIONAL-A': 1.0})

    def test_initial_baseline_silent_then_no_change(self):
        doc = transaction_doc()
        first = changes({'current': doc})
        self.assertTrue(first['baseline_created'])
        self.assertEqual(first['new_event_ids'], [])
        second = changes({'current': doc, 'previous': first['checkpoint']})
        self.assertFalse(second['baseline_created'])
        self.assertEqual(second['new_event_ids'], [])
        self.assertEqual(second['updated_event_ids'], [])

    def test_explicit_withdrawal_correction_and_older_record(self):
        doc = transaction_doc()
        first = changes({'current': doc})
        doc['events'][0].update(revision=1, withdrawn=True)
        result = changes({'current': doc, 'previous': first['checkpoint']})
        self.assertEqual(result['updated_event_ids'], ['fictional:filing:row-1'])
        self.assertTrue(result['checkpoint']['events']['fictional:filing:row-1']['withdrawn'])
        older = changes({'current': transaction_doc(), 'previous': result['checkpoint']})
        self.assertTrue(older['checkpoint']['events']['fictional:filing:row-1']['withdrawn'])

    def test_omitted_event_not_withdrawal(self):
        first = changes({'current': transaction_doc()})
        doc = transaction_doc()
        doc['events'] = []
        result = changes({'current': doc, 'previous': first['checkpoint']})
        self.assertEqual(first['checkpoint']['events'], result['checkpoint']['events'])

    def test_conflicting_baseline_never_saves_arbitrary_record(self):
        result = changes({'current': transaction_doc(event(), event(action='SELL'))})
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(result['checkpoint']['events'], {})

    def test_checkpoint_atomic_idempotent_and_lock_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.json'
            first = refresh_checkpoint(transaction_doc(), path)
            second = refresh_checkpoint(transaction_doc(), path)
            self.assertTrue(first['baseline_created'])
            self.assertEqual(second['updated_event_ids'], [])
            self.assertEqual(json.loads(path.read_text()), second['checkpoint'])
            self.assertFalse(path.with_suffix('.json.lock').exists())
            path.with_suffix('.json.lock').write_text('other owner')
            with self.assertRaises(FileExistsError):
                refresh_checkpoint(transaction_doc(), path)
            self.assertEqual(path.with_suffix('.json.lock').read_text(), 'other owner')

    def test_later_refetch_preserves_first_availability_without_conflict(self):
        first = changes({'current': transaction_doc()})
        doc = transaction_doc(event(available_at='2026-01-11T00:00:00Z', retrieved_at='2026-01-12T00:00:00Z'))
        second = changes({'current': doc, 'previous': first['checkpoint']})
        self.assertEqual(second['status'], 'normalized')
        self.assertEqual(second['updated_event_ids'], [])
        self.assertEqual(first['checkpoint']['events'], second['checkpoint']['events'])

    def test_same_batch_later_refetch_is_not_conflicting_revision(self):
        result = normalize(transaction_doc(event(), event(available_at='2026-01-11T00:00:00Z')))
        self.assertEqual(result['status'], 'normalized')
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(result['records'][0]['available_at'], '2026-01-10T16:01:00Z')

    def test_unavailable_refresh_does_not_refresh_last_successful_clock(self):
        first = changes({'current': transaction_doc()})
        doc = transaction_doc()
        doc['events'] = []
        doc['as_of'] = '2026-01-14T00:00:00Z'
        second = changes({'current': doc, 'previous': first['checkpoint']})
        self.assertEqual(second['checkpoint']['last_successful_as_of'], first['checkpoint']['as_of'])
        self.assertEqual(second['checkpoint']['last_attempt_status'], 'unavailable')

    def test_first_success_after_failed_initial_fetch_still_baselines(self):
        doc = transaction_doc()
        doc['events'] = []
        first = changes({'current': doc})
        second = changes({'current': transaction_doc(), 'previous': first['checkpoint']})
        self.assertTrue(second['baseline_created'])
        self.assertEqual(second['new_event_ids'], [])

    def test_conflict_persists_until_higher_revision(self):
        first = changes({'current': transaction_doc(event(), event(action='SELL'))})
        second = changes({'current': transaction_doc(), 'previous': first['checkpoint']})
        self.assertEqual(second['status'], 'conflict')
        third = changes({'current': transaction_doc(event(revision=1)), 'previous': second['checkpoint']})
        self.assertEqual(third['status'], 'normalized')
        self.assertEqual(third['checkpoint']['unresolved_conflicts'], {})

    def test_checkpoint_kind_is_bound(self):
        first = changes({'current': transaction_doc()})
        doc = transaction_doc()
        doc['kind'] = 'public_recommendations'
        with self.assertRaisesRegex(ValueError, 'KIND_MISMATCH'):
            changes({'current': doc, 'previous': first['checkpoint']})

    def test_normalization_error_leaves_old_checkpoint_and_cleans_owned_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'checkpoint.json'
            refresh_checkpoint(transaction_doc(), path)
            before = path.read_bytes()
            doc = transaction_doc(event(event_at='2027-01-01T00:00:00Z'))
            with self.assertRaises(ValueError):
                refresh_checkpoint(doc, path)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['checkpoint.json'])


if __name__ == '__main__':
    unittest.main()
