"""Fictional permitted-input tests, not observed markets or access claims."""
from copy import deepcopy
import csv
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import market_flow
import market_sources
import options_activity as options

AS_OF = '2026-11-16T21:00:00Z'
SOURCE = {'id': 'fictional-export', 'url': 'https://example.org/fictional-export',
          'retrieved_at': AS_OF, 'access': 'supplied', 'rights': 'synthetic_fixture',
          'availability_basis': 'first_observed_snapshot'}
CONTRACT = dict(contract_id='DEMO-20261218-C-50', underlying_id='fictional-issuer:A',
                expiry='2026-12-18', strike='50', right='call', multiplier='100', currency='USD',
                premium_unit='currency_per_multiplier_unit', deliverable='100 DEMO class A shares')


def record(rid='print', kind='option_print', **changes):
    p = dict(CONTRACT, feed_id='fictional-feed')
    if kind == 'option_print':
        p.update(print_id='event-1', event_at='2026-11-16T20:30:00Z', contracts='3',
                 quantity_unit='contracts', price='1.85', price_basis='actual_print',
                 bid='1.80', ask='1.90', quote_at='2026-11-16T20:29:59Z')
    else:
        p.update(observed_at='2026-11-16T20:30:00Z', volume_contracts='3000', volume_date='2026-11-16',
                 open_interest_contracts='1000', open_interest_date='2026-11-13',
                 bid='1.80', ask='1.90', quote_at='2026-11-16T20:30:00Z', last_price='1.88')
    p.update(changes)
    return dict(id=rid, kind=kind, ticker='DEMO', available_at=AS_OF, source=deepcopy(SOURCE), payload=p)


def doc(*records):
    return dict(schema_version=1, as_of=AS_OF, records=list(records))


def vintage(row, available):
    row['available_at'] = available
    row['source']['retrieved_at'] = available
    return row


def error_codes(result):
    return [issue['code'] for issue in result['issues']]


class ActivityTests(unittest.TestCase):
    def test_actual_premium_multiplier_currency_and_no_exposure_inference(self):
        row = options.analyze(doc(record()))['prints'][0]
        self.assertEqual(row['actual_print_premium'], 555)
        self.assertEqual(row['premium_currency'], 'USD')
        self.assertEqual(row['quote']['midpoint'], 1.85)
        self.assertFalse(row['quote']['executed_trade'])
        self.assertIsNone(row['underlying_exposure'])
        self.assertEqual(row['aggressor_side'], 'UNKNOWN')
        self.assertEqual(row['open_close_intent'], 'UNKNOWN')

    def test_nonstandard_multiplier_never_defaults_to_100(self):
        self.assertEqual(options.analyze(doc(record(multiplier='10')))['prints'][0]['actual_print_premium'], 55.5)
        out = options.analyze(doc(record(multiplier=None)))
        self.assertEqual(out['prints'], [])
        self.assertIn('MISSING_CONTRACT_MULTIPLIER', str(out['issues']))

    def test_quote_and_last_price_do_not_become_actual_prints(self):
        out = options.analyze(doc(record('chain', 'option_chain')))
        self.assertEqual(out['prints'], [])
        row = out['chains'][0]
        self.assertIsNone(row['actual_print_premium'])
        self.assertEqual(row['last_price'], '1.88')
        self.assertEqual(row['volume_to_dated_open_interest'], 3)
        self.assertEqual(row['open_interest_date'], '2026-11-13')
        self.assertIsNone(out['summary']['pooled_premium'])

    def test_mid_or_mark_cannot_masquerade_as_print(self):
        for basis in ('midpoint', 'mark', None):
            out = options.analyze(doc(record(price_basis=basis)))
            self.assertEqual(out['prints'], [])
            self.assertIn('ACTUAL_PRINT_PRICE_BASIS_REQUIRED', str(out['issues']))

    def test_missing_or_future_oi_date_keeps_count_but_not_ratio(self):
        for day in (None, '2026-11-17', 'not-a-date'):
            out = options.analyze(doc(record('chain', 'option_chain', open_interest_date=day)))
            self.assertEqual(out['chains'][0]['open_interest_contracts'], 1000)
            self.assertIsNone(out['chains'][0]['volume_to_dated_open_interest'])
            self.assertTrue(out['issues'])

    def test_zero_oi_and_missing_volume_remain_distinct(self):
        out = options.analyze(doc(record('chain', 'option_chain', open_interest_contracts='0')))
        self.assertEqual(out['chains'][0]['open_interest_contracts'], 0)
        self.assertIsNone(out['chains'][0]['volume_to_dated_open_interest'])
        out = options.analyze(doc(record('chain', 'option_chain', volume_contracts=None)))
        self.assertIsNone(out['chains'][0]['volume_contracts'])

    def test_invalid_contracts_identity_and_numbers_are_rejected(self):
        for changes in ({'contracts': '1.5'}, {'price': 'NaN'}, {'currency': None},
                        {'right': 'C'}, {'expiry': '2026-11-01'}, {'strike': '0'},
                        {'deliverable': ''}, {'deliverable': 'unknown'}, {'premium_unit': 'unknown'}):
            with self.subTest(changes=changes):
                out = options.analyze(doc(record(**changes)))
                self.assertEqual(out['prints'], [])
                self.assertTrue(out['issues'])

    def test_bad_quote_retains_identified_actual_print_without_quote_classification(self):
        for changes in ({'bid': '2'}, {'quote_at': '2026-11-16T20:31:00Z'}):
            out = options.analyze(doc(record(**changes)))
            self.assertEqual(out['prints'][0]['actual_print_premium'], 555)
            self.assertEqual(out['prints'][0]['quote']['print_location'], 'UNKNOWN')

    def test_quote_at_ask_does_not_infer_buyer_or_opening(self):
        row = options.analyze(doc(record(price='1.90')))['prints'][0]
        self.assertEqual(row['quote']['print_location'], 'AT_ASK')
        self.assertEqual(row['aggressor_side'], 'UNKNOWN')
        self.assertEqual(row['open_close_intent'], 'UNKNOWN')

    def test_declared_quote_age_limit_keeps_premium_but_removes_location(self):
        request = doc(record(price='1.90'))
        request['settings'] = {'max_quote_age_seconds': 0}
        row = options.analyze(request)['prints'][0]
        self.assertEqual(row['quote']['print_location'], 'UNKNOWN_STALE_UNDER_DECLARED_LIMIT')
        self.assertEqual(row['actual_print_premium'], 570)

    def test_deduplicates_within_feed_and_refuses_conflicting_contract_id(self):
        a = record(); b = deepcopy(a); b['id'] = 'duplicate'
        out = options.analyze(doc(a, b))
        self.assertEqual(len(out['prints']), 1)
        self.assertIn('DUPLICATE_WITHIN_FEED_NOT_COUNTED', error_codes(out))
        b['payload']['strike'] = '55'
        self.assertEqual(options.analyze(doc(a, b))['prints'], [])

    def test_numeric_contract_representations_preserve_distinct_actual_prints(self):
        a = record('a')
        b = record('b', print_id='event-2', strike='50.0', multiplier='100.0')
        c = record('c', print_id='event-3', strike=50, multiplier=100)
        original = doc(a, b, c); frozen = deepcopy(original)
        out = options.analyze(original)
        self.assertEqual([row['actual_print_premium'] for row in out['prints']], [555, 555, 555])
        self.assertNotIn('CONFLICTING_CONTRACT_IDENTITY', error_codes(out))
        self.assertEqual(out['prints'][1]['contract']['strike'], '50.0')
        self.assertEqual(out['prints'][2]['contract']['multiplier'], 100)
        self.assertEqual(original, frozen)

    def test_repr_variant_correction_replaces_stale_premium_and_preserves_bytes(self):
        a = vintage(record(), '2026-11-16T20:40:00Z')
        b = vintage(record('corrected', price='2', strike='50.0', multiplier='100.0'), '2026-11-16T20:50:00Z')
        b.update(action='replace', supersedes=a['id'])
        original = doc(a, b); frozen = deepcopy(original)
        normalized = market_sources.normalize(original)
        self.assertFalse(normalized['records'][0]['eligible'])
        self.assertTrue(normalized['records'][1]['eligible'])
        out = options.analyze(original)
        self.assertEqual(len(out['prints']), 1)
        self.assertEqual(out['prints'][0]['record_id'], 'corrected')
        self.assertEqual(out['prints'][0]['actual_print_premium'], 600)
        self.assertEqual(out['prints'][0]['contract']['strike'], '50.0')
        self.assertEqual(original, frozen)

    def test_option_revision_invalid_numeric_terms_fail_closed(self):
        for field in ('strike', 'multiplier'):
            for value in ('NaN', 'Infinity', '0', '-1', None, True):
                with self.subTest(field=field, value=value):
                    a = vintage(record(), '2026-11-16T20:40:00Z')
                    b = vintage(record('invalid', price='2', **{field: value}), '2026-11-16T20:50:00Z')
                    b.update(action='replace', supersedes=a['id'])
                    normalized = market_sources.normalize(doc(a, b))
                    self.assertTrue(normalized['records'][0]['eligible'])
                    self.assertIn('REVISION_SCOPE_MISMATCH', normalized['records'][1]['exclusion_reasons'])
                    self.assertEqual(options.analyze(doc(a, b))['prints'][0]['actual_print_premium'], 555)

    def test_chain_repr_variant_revision_preserves_snapshot_and_replaces_volume(self):
        a = vintage(record('chain-a', 'option_chain'), '2026-11-16T20:40:00Z')
        b = vintage(record('chain-b', 'option_chain', strike='50.0', multiplier='100.0', volume_contracts='4000'),
                    '2026-11-16T20:50:00Z')
        b.update(action='replace', supersedes='chain-a')
        out = options.analyze(doc(a, b))
        self.assertEqual(len(out['chains']), 1)
        self.assertEqual(out['chains'][0]['record_id'], 'chain-b')
        self.assertEqual(out['chains'][0]['volume_to_dated_open_interest'], 4)

    def test_unlinked_conflicting_prints_and_overlapping_feeds_never_pool(self):
        a = record(); b = deepcopy(a); b['id'] = 'second'; b['payload']['price'] = '1.80'
        out = options.analyze(doc(a, b))
        self.assertEqual(out['prints'], [])
        self.assertIn('CONFLICTING_OPTION_FEED_IDENTITY_REQUIRES_REVISION', error_codes(out))
        b['payload']['feed_id'] = 'other-feed'
        out = options.analyze(doc(a, b))
        self.assertEqual(len(out['prints']), 2)
        self.assertIsNone(out['summary']['pooled_premium'])

    def test_cutoff_correction_cancellation_and_contract_scope(self):
        a = vintage(record(), '2026-11-16T20:40:00Z')
        b = vintage(record('correction', price='2'), '2026-11-16T20:50:00Z')
        b.update(action='replace', supersedes=a['id'])
        self.assertEqual(options.analyze(doc(a, b))['prints'][0]['actual_print_premium'], 600)
        earlier = doc(a, b); earlier['as_of'] = '2026-11-16T20:45:00Z'
        self.assertEqual(options.analyze(earlier)['prints'][0]['actual_print_premium'], 555)
        b['action'] = 'cancel'
        self.assertEqual(options.analyze(doc(a, b))['prints'], [])
        b['action'] = 'replace'; b['payload']['multiplier'] = '10'
        normalized = market_sources.normalize(doc(a, b))
        self.assertTrue(normalized['records'][0]['eligible'])
        self.assertIn('REVISION_SCOPE_MISMATCH', normalized['records'][1]['exclusion_reasons'])

    def test_revision_fork_not_counted_as_two_actual_prints(self):
        a = vintage(record(), '2026-11-16T20:40:00Z')
        b = vintage(record('b', price='2'), '2026-11-16T20:50:00Z')
        c = vintage(record('c', price='3'), '2026-11-16T20:55:00Z')
        b.update(action='replace', supersedes=a['id']); c.update(action='replace', supersedes=a['id'])
        out = options.analyze(doc(a, b, c))
        self.assertEqual(out['prints'], [])
        self.assertIn('UNRESOLVED_OPTION_REVISION_GRAPH', error_codes(out))
        earlier = doc(a, b, c); earlier['as_of'] = '2026-11-16T20:52:00Z'
        self.assertEqual(options.analyze(earlier)['prints'][0]['actual_print_premium'], 600)

    def test_inputs_are_not_mutated(self):
        original = doc(record()); frozen = deepcopy(original)
        options.analyze(original)
        self.assertEqual(original, frozen)

    def test_status_cannot_replace_revision_envelope(self):
        for status in ('cancelled', 'corrected', 'unknown'):
            out = options.analyze(doc(record(status=status)))
            self.assertEqual(out['prints'], [])
            self.assertTrue(out['issues'])

    def test_future_event_and_unknown_source_availability_are_not_current(self):
        out = options.analyze(doc(record(event_at='2026-11-16T22:00:00Z')))
        self.assertEqual(out['prints'], [])
        row = record(); row['available_at'] = None
        self.assertEqual(options.analyze(doc(row))['prints'], [])

    def test_future_or_unidentified_record_cannot_poison_current_contract(self):
        for changes in ({'event_at': '2026-11-16T22:00:00Z'}, {'print_id': None}):
            with self.subTest(changes=changes):
                current = record('current')
                unusable = record('unusable', strike='55', **changes)
                result = options.analyze(doc(current, unusable))
                self.assertEqual([r['record_id'] for r in result['prints']], ['current'])
                self.assertEqual(result['prints'][0]['actual_print_premium'], 555)
                self.assertNotIn('CONFLICTING_CONTRACT_IDENTITY', error_codes(result))
                self.assertTrue(result['issues'])

    def test_option_chain_revision_cannot_change_contract_or_snapshot_clock(self):
        a = vintage(record('chain-a', 'option_chain'), '2026-11-16T20:40:00Z')
        b = vintage(record('chain-b', 'option_chain', observed_at='2026-11-16T20:31:00Z'), '2026-11-16T20:50:00Z')
        b.update(action='replace', supersedes='chain-a')
        out = market_sources.normalize(doc(a, b))
        self.assertTrue(out['records'][0]['eligible'])
        self.assertIn('REVISION_SCOPE_MISMATCH', out['records'][1]['exclusion_reasons'])


def csv_request(payload, adapter, **extra):
    output = io.StringIO(); writer = csv.DictWriter(output, fieldnames=list(payload))
    writer.writeheader(); writer.writerow(payload)
    return dict(schema_version=1, as_of=AS_OF, adapter=adapter, text=output.getvalue(),
                columns={key: key for key in payload}, source=deepcopy(SOURCE), **extra)


def float_payload(**changes):
    p = dict(ticker='DEMO', issuer_id='fictional-issuer', share_class='A', float_shares='6000',
             effective_date='2026-11-13', share_basis='float', quantity_unit='shares',
             measure_basis='reported_float_shares', adjustment_basis='unadjusted')
    p.update(changes)
    return p


class IntakeAndFloatTests(unittest.TestCase):
    def test_retained_csv_parse_then_analyze_without_contract_defaults(self):
        r = record('chain', 'option_chain'); payload = dict(ticker='DEMO', **r['payload'])
        request = csv_request(payload, 'options_chain_csv')
        parsed = options.parse(request)
        self.assertEqual(parsed['records'][0]['payload']['raw_fields']['contract_id'], CONTRACT['contract_id'])
        self.assertEqual(len(parsed['source_text_sha256']), 64)
        self.assertEqual(options.analyze(parsed)['chains'][0]['volume_to_dated_open_interest'], 3)

    def test_csv_header_collision_and_ragged_rows_do_not_succeed_silently(self):
        request = csv_request(float_payload(), 'float_shares_csv')
        request['text'] = 'ticker,ticker\nDEMO,DEMO\n'
        with self.assertRaisesRegex(ValueError, 'HEADERS'):
            options.parse(request)
        request = csv_request(float_payload(), 'float_shares_csv')
        request['text'] = request['text'].rstrip() + ',extra\n'
        self.assertFalse(options.parse(request)['records'][0]['eligible'])

    def test_float_share_intake_rejects_currency_value_and_outstanding_substitutes(self):
        for changes in ({'share_basis': 'outstanding'}, {'quantity_unit': 'USD'}, {'float_shares': None}):
            result = options.parse(csv_request(float_payload(**changes), 'float_shares_csv'))
            self.assertFalse(result['records'][0]['eligible'])
            self.assertTrue(result['records'][0]['parse_error'])

    def binding(self, **float_changes):
        parsed = options.parse(csv_request(float_payload(**float_changes), 'float_shares_csv', id_prefix='float'))
        floating = parsed['records'][0]
        si = dict(id='si', kind='short_interest', ticker='DEMO', source=deepcopy(SOURCE), available_at=AS_OF,
                  payload=dict(issuer_id='fictional-issuer', share_class='A', settlement_date='2026-11-13',
                               short_interest_shares='1200', measure_basis='official_reported', adjustment_basis='unadjusted'))
        request = doc(floating, si)
        request['float_links'] = [dict(short_interest_record_id='si', float_record_id='float:0')]
        request['settings'] = {'squeeze_criteria': {'min_short_interest_percent_float': 20}}
        return request

    def test_explicit_binding_uses_existing_calculation_and_preserves_original(self):
        request = self.binding(); frozen = deepcopy(request)
        result = options.bind_float(request)
        self.assertEqual(result['positioning']['short_interest'][0]['short_interest_percent_float'], 20)
        self.assertEqual(result['positioning'], market_flow.positioning(result['document']))
        self.assertEqual(result['squeeze'], market_flow.squeeze(result['document']))
        self.assertEqual(request, frozen)
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['squeeze']['assessments'][0]['state'], 'DATED_POSITIONING_CANDIDATE')

    def test_unknown_adjustment_later_float_and_wrong_class_cannot_create_percent(self):
        for changes in ({'adjustment_basis': None}, {'effective_date': '2026-11-14'}, {'share_class': 'B'}):
            result = options.bind_float(self.binding(**changes))
            self.assertIsNone(result['positioning']['short_interest'][0]['short_interest_percent_float'])
            self.assertEqual(result['squeeze']['assessments'][0]['state'], 'INSUFFICIENT_EVIDENCE')

    def test_conflicting_existing_or_duplicate_link_fails(self):
        request = self.binding(); request['records'][1]['payload']['float_record_id'] = 'different'
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_EXISTING'):
            options.bind_float(request)
        request = self.binding(); request['float_links'] *= 2
        with self.assertRaisesRegex(ValueError, 'UNIQUE_FLOAT'):
            options.bind_float(request)
        request = self.binding(); request['records'][0]['payload']['quantity_unit'] = 'USD'
        with self.assertRaisesRegex(ValueError, 'CONTRADICTORY_QUANTITY_UNIT'):
            options.bind_float(request)


class OptionsReportIntegrationTests(unittest.TestCase):
    def facts(self, operation, document):
        import quant_workbench
        import report_facts
        request = {'schema_version': 1, 'contract': {
            'prompt': 'Explain the fictional retained options and float evidence.',
            'purpose': 'Offline report integration', 'base_currency': 'USD',
            'horizon_id': 'dated-observations', 'as_of': AS_OF},
            'jobs': [{'id': 'observations', 'operation': operation, 'inputs': {'document': document}}]}
        bundle = quant_workbench.freeze(request)
        self.assertEqual(bundle['result']['results'][0]['status'], 'COMPUTED')
        result = report_facts.project(json.dumps(bundle).encode('utf8'), 'quant')
        self.assertTrue(result['checks'][0]['code_mapping_matches'])
        self.assertFalse(result['checks'][0]['calculation_replayed'])
        prefix = '/result/results/0/result/'
        return {row['source']['pointer'][len(prefix):]: row for row in result['facts']
                if row['source']['pointer'].startswith(prefix)}

    def test_print_and_chain_report_keeps_premium_quotes_contract_counts_and_unknown_intent(self):
        facts = self.facts('market.options_activity', doc(record(), record('chain', 'option_chain')))
        premium = facts['prints/0/actual_print_premium']
        self.assertEqual((premium['value'], premium['unit']), (555, 'source_currency_amount'))
        self.assertIn('premium_currency', premium['basis'])
        self.assertIn('No FX conversion', premium['basis'])
        self.assertEqual((facts['prints/0/contracts']['value'], facts['prints/0/contracts']['unit']), (3, 'contracts'))
        quote = facts['prints/0/quote/midpoint']
        self.assertEqual((quote['value'], quote['unit']), (1.85, 'currency_per_multiplier_unit'))
        self.assertIn('not an executed trade', quote['basis'])
        self.assertFalse(facts['prints/0/quote/executed_trade']['value'])
        self.assertEqual(facts['prints/0/aggressor_side']['value'], 'UNKNOWN')
        self.assertEqual(facts['prints/0/open_close_intent']['value'], 'UNKNOWN')
        ratio = facts['chains/0/volume_to_dated_open_interest']
        self.assertEqual((ratio['value'], ratio['unit']), (3, 'ratio'))
        self.assertIn('dated open_interest_contracts', ratio['denominator'])
        self.assertEqual(facts['chains/0/open_interest_contracts']['unit'], 'contracts')
        self.assertIsNone(facts['chains/0/actual_print_premium']['value'])
        self.assertEqual(facts['chains/0/actual_print_premium']['missingness'], 'null')
        self.assertFalse(facts['summary/squeeze_confirmed']['value'])
        self.assertEqual(facts['prints/0/feed_id']['missingness'], 'source_text_withheld')

    def test_missing_dated_oi_remains_unknown_in_typed_ratio_report(self):
        facts = self.facts('market.options_activity', doc(record('chain', 'option_chain', open_interest_date=None)))
        ratio = facts['chains/0/volume_to_dated_open_interest']
        self.assertIsNone(ratio['value'])
        self.assertEqual((ratio['unit'], ratio['missingness']), ('ratio', 'null'))
        self.assertEqual((facts['chains/0/open_interest_contracts']['value'],
                          facts['chains/0/open_interest_contracts']['unit']), (1000, 'contracts'))
        self.assertIsNone(facts['summary/pooled_premium']['value'])

    def test_float_report_delegates_existing_units_and_preserves_unresolved_comparability(self):
        source = IntakeAndFloatTests()
        facts = self.facts('market.bind_float', source.binding())
        self.assertEqual((facts['positioning/short_interest/0/float_shares']['value'],
                          facts['positioning/short_interest/0/float_shares']['unit']), (6000, 'shares'))
        ratio = facts['positioning/short_interest/0/short_interest_percent_float']
        self.assertEqual((ratio['value'], ratio['unit']), (20, 'percent'))
        self.assertIn('same-issuer/class dated float', ratio['denominator'])
        self.assertEqual(facts['squeeze/assessments/0/state']['value'], 'DATED_POSITIONING_CANDIDATE')
        unknown = self.facts('market.bind_float', source.binding(adjustment_basis=None))
        ratio = unknown['positioning/short_interest/0/short_interest_percent_float']
        self.assertIsNone(ratio['value'])
        self.assertEqual((ratio['unit'], ratio['missingness']), ('percent', 'null'))
        self.assertEqual(unknown['squeeze/assessments/0/state']['value'], 'INSUFFICIENT_EVIDENCE')


if __name__ == '__main__':
    unittest.main()
