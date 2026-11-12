"""Synthetic, independent arithmetic and information-cutoff regressions."""
from copy import deepcopy
from fractions import Fraction
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import market_flow


AS_OF = '2026-11-11T21:00:00Z'
IDENTITY = {'issuer_id': 'fictional-issuer-1', 'share_class': 'A'}


def record(rid, kind, payload, ticker='DEMO', available=AS_OF):
    return {'id': rid, 'kind': kind, 'ticker': ticker, 'available_at': available,
            'source': {'id': 'synthetic-source', 'url': 'https://example.org/synthetic',
                       'retrieved_at': AS_OF, 'published_at': None,
                       'observed_at': available, 'availability_basis': 'first_observed_snapshot',
                       'access': 'public', 'rights': 'synthetic_fixture'},
            'payload': deepcopy(payload)}


def document(records=None):
    return {'schema_version': 1, 'as_of': AS_OF, 'records': records or []}


def trade(rid, quantity, role='baseline', feed='feed-one'):
    return record(rid, 'trade', dict(IDENTITY, feed_id=feed, trade_id=rid,
        event_at='2026-11-10T15:00:00Z' if role == 'baseline' else '2026-11-11T20:30:00Z',
        quantity=quantity, price='10', currency='USD', quantity_unit='shares',
        comparison_group='regular_unadjusted_all_reported_prints', role=role))


def bar(rid, day, volume, role='baseline', ticker='DEMO'):
    return record(rid, 'bar', dict(IDENTITY, bar_type='cumulative', feed_id='feed-one',
        start_at=day + 'T14:30:00Z', end_at=day + 'T15:30:00Z', session_id=day,
        volume=volume, volume_unit='shares', volume_basis='unadjusted', currency='USD',
        comparison_group='regular_first_hour', role=role, price_basis='unadjusted_close'), ticker=ticker)


def pressure_document():
    b1, b2 = bar('b1', '2026-11-09', '100'), bar('b2', '2026-11-10', '200')
    current = bar('current', '2026-11-11', '900', 'current')
    current['payload'].update(start_price='100', end_price='106', benchmark_record_id='benchmark')
    benchmark = bar('benchmark', '2026-11-11', None, 'benchmark', 'BENCH')
    benchmark['payload'].update(start_price='100', end_price='101')
    floating = record('float', 'float', dict(IDENTITY, float_shares='6000', effective_date='2026-11-01',
        share_basis='float', measure_basis='vendor_estimate', adjustment_basis='same_split_basis'))
    daily = [record('d1', 'bar', dict(IDENTITY, bar_type='daily_volume', session_date='2026-11-09',
                    volume='200', volume_unit='shares', feed_id='one-daily-feed', adjustment_basis='same_split_basis')),
             record('d2', 'bar', dict(IDENTITY, bar_type='daily_volume', session_date='2026-11-10',
                    volume='400', volume_unit='shares', feed_id='one-daily-feed', adjustment_basis='same_split_basis'))]
    si = record('si', 'short_interest', dict(IDENTITY, settlement_date='2026-11-10',
        short_interest_shares='1200', measure_basis='official_reported',
        measurement_scope='same_reporting_population', adjustment_basis='same_split_basis',
        float_record_id='float', adv_record_ids=['d1', 'd2'],
        adv_window={'start_date': '2026-11-09', 'end_date': '2026-11-10',
                    'expected_sessions': ['2026-11-09', '2026-11-10']}))
    result = document([b1, b2, current, benchmark, floating] + daily + [si])
    result['settings'] = {'squeeze_criteria': {'min_short_interest_percent_float': 20,
        'min_days_to_cover': 4, 'min_relative_volume': 3, 'min_benchmark_relative_return_percent': 2}}
    return result


class PrintTests(unittest.TestCase):
    def test_empirical_rank_ties_and_actual_notional(self):
        d = document([trade('a', 100), trade('b', 200), trade('c', 200), trade('d', 400), trade('now', 200, 'current')])
        d['settings'] = {'print_percentile_threshold': 80}
        current = market_flow.analyze(d)['prints'][-1]
        self.assertEqual(current['baseline_count'], 4)
        self.assertEqual(current['quantity_percentile'], float(Fraction(3, 4) * 100))
        self.assertEqual(current['notional'], 2000)
        self.assertEqual(current['notional_percentile'], 75)
        self.assertFalse(current['declared_large_print_flag'])
        self.assertEqual(current['aggressor_side'], 'UNKNOWN')
        self.assertEqual(current['open_close_intent'], 'UNKNOWN')

    def test_missing_baseline_is_unknown_and_no_default_rule(self):
        row = market_flow.analyze(document([trade('now', 100, 'current')]))['prints'][0]
        self.assertIsNone(row['quantity_percentile'])
        self.assertIsNone(row['declared_large_print_flag'])

    def test_feeds_and_currency_are_not_pooled(self):
        old = trade('old', 10000, feed='other-feed')
        euro = trade('euro', 10000); euro['payload']['currency'] = 'EUR'
        d = document([old, euro, trade('now', 10, 'current')])
        self.assertEqual(market_flow.analyze(d)['prints'][-1]['baseline_count'], 0)

    def test_baseline_after_print_not_used(self):
        old = trade('later', 100)
        old['payload']['event_at'] = '2026-11-11T20:31:00Z'
        self.assertEqual(market_flow.analyze(document([old, trade('now', 200, 'current')]))['prints'][-1]['baseline_count'], 0)

    def test_identical_feed_print_is_counted_once(self):
        a = trade('a', 100); duplicate = deepcopy(a); duplicate['id'] = 'duplicate'
        out = market_flow.analyze(document([a, duplicate, trade('now', 200, 'current')]))
        self.assertEqual(out['summary']['eligible_trade_count'], 2)
        self.assertTrue(any(x.get('code') == 'DUPLICATE_WITHIN_FEED_NOT_COUNTED' for x in out['issues']))

    def test_conflicting_feed_print_requires_revision(self):
        a = trade('a', 100); duplicate = deepcopy(a); duplicate['id'] = 'duplicate'; duplicate['payload']['quantity'] = 300
        out = market_flow.analyze(document([a, duplicate, trade('now', 200, 'current')]))
        self.assertEqual(out['summary']['eligible_trade_count'], 1)
        self.assertIsNone(out['prints'][0]['quantity_percentile'])

    def test_available_replacement_and_cancellation(self):
        a = trade('a', 100); a['available_at'] = '2026-11-11T20:00:00Z'
        a['source'].update(observed_at=a['available_at'], retrieved_at=a['available_at'])
        replacement = deepcopy(a); replacement.update(id='correction', action='replace', supersedes='a', available_at='2026-11-11T20:05:00Z')
        replacement['source'].update(observed_at=replacement['available_at'], retrieved_at=replacement['available_at'])
        replacement['payload'].update(quantity=1000, status='corrected')
        out = market_flow.analyze(document([a, replacement, trade('now', 200, 'current')]))
        self.assertEqual(out['prints'][-1]['quantity_percentile'], 0)
        cancel = deepcopy(a); cancel.update(id='cancel', action='cancel', supersedes='a', available_at='2026-11-11T20:05:00Z')
        cancel['source'].update(observed_at=cancel['available_at'], retrieved_at=cancel['available_at'])
        out = market_flow.analyze(document([a, cancel, trade('now', 200, 'current')]))
        self.assertIsNone(out['prints'][-1]['quantity_percentile'])

    def test_future_correction_does_not_rewrite_decision(self):
        a = trade('a', 100); replacement = deepcopy(a)
        replacement.update(id='later', action='replace', supersedes='a', available_at='2026-11-12T21:00:00Z')
        replacement['source'].update(observed_at='2026-11-12T21:00:00Z', retrieved_at='2026-11-12T21:00:00Z')
        replacement['payload']['quantity'] = 1000
        row = market_flow.analyze(document([a, replacement, trade('now', 200, 'current')]))['prints'][-1]
        self.assertEqual(row['quantity_percentile'], 100)

    def test_correction_cannot_change_feed_currency_or_share_class(self):
        for field, value in [('feed_id', 'other-feed'), ('currency', 'EUR'), ('share_class', 'B')]:
            original = trade('a', 100); original['available_at'] = '2026-11-11T20:00:00Z'
            original['source'].update(observed_at=original['available_at'], retrieved_at=original['available_at'])
            correction = deepcopy(original)
            correction.update(id='correction', action='replace', supersedes='a', available_at='2026-11-11T20:05:00Z')
            correction['source'].update(observed_at=correction['available_at'], retrieved_at=correction['available_at'])
            correction['payload'].update(quantity=1000, status='corrected')
            correction['payload'][field] = value
            row = market_flow.analyze(document([original, correction, trade('now', 200, 'current')]))['prints'][-1]
            self.assertEqual(row['quantity_percentile'], 100)

    def test_quote_math_and_side_are_distinct(self):
        a = trade('now', 200, 'current'); a['payload'].update(bid='9.99', ask='10.01', quote_at='2026-11-11T20:29:59Z')
        row = market_flow.analyze(document([a]))['prints'][0]
        self.assertEqual(row['quote_context']['spread_bps'], 20)
        self.assertEqual(row['quote_context']['quote_age_seconds'], 1)
        self.assertEqual(row['quote_context']['execution_location'], 'BETWEEN')
        self.assertEqual(row['aggressor_side'], 'UNKNOWN')

    def test_declared_stale_quote_and_future_quote(self):
        a = trade('now', 200, 'current'); a['payload'].update(bid='9', ask='10', quote_at='2026-11-11T20:29:00Z')
        d = document([a]); d['settings'] = {'max_quote_age_seconds': 5}
        self.assertEqual(market_flow.analyze(d)['prints'][0]['quote_context']['execution_location'], 'UNKNOWN_STALE_UNDER_DECLARED_LIMIT')
        a['payload']['quote_at'] = '2026-11-11T20:31:00Z'
        self.assertEqual(market_flow.analyze(document([a]))['prints'][0]['quote_context']['execution_location'], 'UNKNOWN')

    def test_invalid_price_does_not_become_zero(self):
        a = trade('bad', '-1', 'current')
        self.assertEqual(market_flow.analyze(document([a]))['prints'], [])


class BarTests(unittest.TestCase):
    def test_time_of_day_rvol_and_benchmark_independent_math(self):
        row = next(x for x in market_flow.analyze(pressure_document())['cumulative_bars'] if x['record_id'] == 'current')
        self.assertEqual(row['baseline_mean_volume'], float(Fraction(100 + 200, 2)))
        self.assertEqual(row['relative_volume'], float(Fraction(900, 150)))
        expected = (Fraction(106, 100) - Fraction(101, 100)) * 100
        self.assertEqual(row['benchmark_relative_return_percent'], float(expected))

    def test_other_elapsed_window_cannot_fill_baseline(self):
        d = pressure_document(); d['records'][0]['payload']['end_at'] = '2026-11-09T16:30:00Z'
        row = next(x for x in market_flow.analyze(d)['cumulative_bars'] if x['record_id'] == 'current')
        self.assertEqual(row['relative_volume'], 4.5)
        self.assertEqual(row['baseline_sessions'], 1)

    def test_zero_baseline_unknown_ratio(self):
        d = pressure_document()
        for x in d['records'][:2]: x['payload']['volume'] = 0
        row = next(x for x in market_flow.analyze(d)['cumulative_bars'] if x['record_id'] == 'current')
        self.assertEqual(row['baseline_mean_volume'], 0)
        self.assertIsNone(row['relative_volume'])

    def test_same_duration_different_time_of_day_not_comparable(self):
        d = pressure_document(); p = d['records'][0]['payload']
        p.update(start_at='2026-11-09T15:30:00Z', end_at='2026-11-09T16:30:00Z')
        row = next(x for x in market_flow.analyze(d)['cumulative_bars'] if x['record_id'] == 'current')
        self.assertEqual(row['baseline_sessions'], 1)
        self.assertEqual(row['relative_volume'], 4.5)

    def test_benchmark_different_currency_or_window_not_compared(self):
        for key, value in [('currency', 'EUR'), ('end_at', '2026-11-11T15:31:00Z'), ('price_basis', 'adjusted')]:
            d = pressure_document(); d['records'][3]['payload'][key] = value
            row = next(x for x in market_flow.analyze(d)['cumulative_bars'] if x['record_id'] == 'current')
            self.assertIsNone(row['benchmark_relative_return_percent'])


class PositionTests(unittest.TestCase):
    def test_source_parser_reported_days_preserved_separately_from_recomputed(self):
        from market_sources import parse
        source = record('source', 'short_interest', {})['source']
        d = {'schema_version': 1, 'as_of': AS_OF, 'adapter': 'finra_short_interest_csv', 'source': source,
             'text': 'Settlement Date,Symbol,Current Short,Avg Daily Volume,Days to Cover,Issue Name\n2026-10-30,DEMO,1200,500,2.40,Demo Inc\n'}
        parsed = parse(d)
        result = market_flow.positioning({'schema_version': 1, 'as_of': AS_OF, 'records': parsed['records']})
        row = result['short_interest'][0]
        self.assertEqual(row['provider_reported_days_to_cover'], 2.4)
        self.assertEqual(row['provider_reported_days_to_cover_fields'], {'reported_days_to_cover': 2.4})
        self.assertEqual(row['provider_reported_average_daily_volume'], 500)
        self.assertIsNone(row['adv']['days_to_cover'])

    def test_reported_days_alias_conflict_is_retained_and_not_selected(self):
        d = pressure_document(); d['records'][-1]['payload'].update(reported_days_to_cover=2.4, days_to_cover=4)
        out = market_flow.positioning(d); row = out['short_interest'][0]
        self.assertIsNone(row['provider_reported_days_to_cover'])
        self.assertEqual(row['provider_reported_days_to_cover_fields'], {'reported_days_to_cover': 2.4, 'days_to_cover': 4})
        self.assertEqual(row['adv']['days_to_cover'], 4)
        self.assertTrue(any('CONFLICTING_PROVIDER_REPORTED_DAYS' in x.get('code', '') for x in out['issues']))

    def test_short_float_and_declared_daily_window_math(self):
        row = market_flow.positioning(pressure_document())['short_interest'][0]
        self.assertEqual(row['short_interest_percent_float'], 20)
        self.assertEqual(row['adv']['average_daily_volume'], 300)
        self.assertEqual(row['adv']['days_to_cover'], float(Fraction(1200, 300)))
        self.assertEqual(row['float_measure_basis'], 'vendor_estimate')

    def test_missing_expected_sessions_remains_conditional(self):
        d = pressure_document(); del d['records'][-1]['payload']['adv_window']['expected_sessions']
        adv = market_flow.positioning(d)['short_interest'][0]['adv']
        self.assertIsNone(adv['days_to_cover'])
        self.assertEqual(adv['conditional_days_to_cover'], 4)

    def test_incomplete_window_not_silently_complete(self):
        d = pressure_document(); d['records'][-1]['payload']['adv_record_ids'] = ['d1']
        adv = market_flow.positioning(d)['short_interest'][0]['adv']
        self.assertEqual(adv['window_coverage'], 'INCOMPLETE_DECLARED_SESSIONS')
        self.assertIsNone(adv['days_to_cover'])

    def test_adv_overlapping_feeds_and_duplicate_sessions_rejected(self):
        d = pressure_document(); d['records'][6]['payload']['feed_id'] = 'second-feed'
        self.assertEqual(market_flow.positioning(d)['short_interest'][0]['adv']['window_coverage'], 'UNUSABLE')
        d = pressure_document(); d['records'][6]['payload']['session_date'] = '2026-11-09'
        self.assertEqual(market_flow.positioning(d)['short_interest'][0]['adv']['window_coverage'], 'UNUSABLE')

    def test_adv_missing_or_mismatched_share_basis_cannot_supply_days_to_cover(self):
        for basis in [None, 'different_split_basis']:
            d = pressure_document(); d['records'][5]['payload']['adjustment_basis'] = basis
            adv = market_flow.positioning(d)['short_interest'][0]['adv']
            self.assertIsNone(adv['average_daily_volume'])
            self.assertIsNone(adv['days_to_cover'])
            self.assertIsNone(adv['conditional_days_to_cover'])
            self.assertEqual(adv['supplied_volume_arithmetic_mean'], 300)
            self.assertEqual(adv['unreconciled_share_count_quotient'], 4)
            self.assertIn(adv['share_adjustment_comparability'], ['UNKNOWN', 'MISMATCH'])
            self.assertEqual(market_flow.squeeze(d)['assessments'][0]['state'], 'INSUFFICIENT_EVIDENCE')
    def test_float_date_class_and_adjustment_mismatch_unknown(self):
        for key, value in [('effective_date', '2026-11-11'), ('share_class', 'B'), ('adjustment_basis', 'other')]:
            d = pressure_document(); d['records'][4]['payload'][key] = value
            self.assertIsNone(market_flow.positioning(d)['short_interest'][0]['short_interest_percent_float'])

    def test_zero_short_interest_is_observed_zero(self):
        d = pressure_document(); d['records'][-1]['payload']['short_interest_shares'] = 0
        row = market_flow.positioning(d)['short_interest'][0]
        self.assertEqual(row['short_interest_percent_float'], 0)
        self.assertEqual(row['adv']['days_to_cover'], 0)

    def test_short_volume_fractional_and_exempt_not_added(self):
        a = record('sv', 'short_sale_volume', {'trade_date': '2026-11-10', 'short_volume': '30.5',
            'short_exempt_volume': '5.5', 'total_volume': '100', 'volume_unit': 'shares', 'coverage': 'one_facility'})
        row = market_flow.positioning(document([a]))['short_sale_volume'][0]
        self.assertEqual(row['reported_short_volume_ratio'], float(Fraction(61, 200)))
        self.assertIsNone(row['outstanding_short_position_change'])

    def test_borrow_zero_unknown_scope_and_provider_separation(self):
        a = record('borrow', 'borrow', dict(IDENTITY, observed_at='2026-11-11T20:00:00Z',
            provider='one-lender', provider_scope='one-client-view', shares_available=0, utilization_percent=0))
        row = market_flow.positioning(document([a]))['borrow'][0]
        self.assertEqual(row['shares_available'], 0)
        self.assertIsNone(row['fee_rate_annual_percent'])
        del a['payload']['provider_scope']
        self.assertEqual(market_flow.positioning(document([a]))['borrow'], [])

    def test_ftd_balances_never_summed_or_given_countdown(self):
        d = document([record('f1', 'ftd', {'settlement_date': '2026-11-09', 'quantity': 100}),
                      record('f2', 'ftd', {'settlement_date': '2026-11-10', 'quantity': 100})])
        out = market_flow.positioning(d)
        self.assertEqual([x['quantity'] for x in out['failures_to_deliver']], [100, 100])
        self.assertNotIn('total_fails', out)
        self.assertTrue(all(x['forced_buy_in_date'] is None and not x['naked_shorting_established'] for x in out['failures_to_deliver']))


class SqueezeTests(unittest.TestCase):
    def test_no_default_rule_or_probability(self):
        d = pressure_document(); del d['settings']
        row = market_flow.squeeze(d)['assessments'][0]
        self.assertEqual(row['state'], 'INSUFFICIENT_EVIDENCE')
        self.assertIsNone(row['probability'])
        self.assertFalse(row['squeeze_confirmed'])

    def test_declared_pressure_is_heuristic_not_cause(self):
        row = market_flow.squeeze(pressure_document())['assessments'][0]
        self.assertEqual(row['state'], 'DEVELOPING_PRESSURE_HEURISTIC')
        self.assertFalse(row['causal_covering_confirmed'])

    def test_positioning_only_and_wrong_issuer_flow(self):
        d = pressure_document(); d['settings']['squeeze_criteria'] = {'min_short_interest_percent_float': 20}
        self.assertEqual(market_flow.squeeze(d)['assessments'][0]['state'], 'DATED_POSITIONING_CANDIDATE')
        d = pressure_document(); d['records'][2]['payload']['issuer_id'] = 'different-issuer'
        self.assertEqual(market_flow.squeeze(d)['assessments'][0]['state'], 'DATED_POSITIONING_CANDIDATE')

    def test_short_interest_decline_not_direct_covering(self):
        d = pressure_document(); earlier = deepcopy(d['records'][-1]); earlier['id'] = 'earlier'
        earlier['payload'].update(settlement_date='2026-10-30', short_interest_shares=1800)
        earlier['payload'].pop('adv_record_ids'); earlier['payload'].pop('float_record_id')
        d['records'].append(earlier)
        out = market_flow.squeeze(d)
        self.assertEqual(out['retrospective_short_interest_changes'][0]['net_short_share_change'], -600)
        self.assertEqual(out['retrospective_short_interest_changes'][0]['classification'], 'REPORTED_NET_SHORT_REDUCTION')
        self.assertIsNone(out['retrospective_short_interest_changes'][0]['gross_covering_volume'])
        self.assertEqual(out['reported_covering'], [])

    def test_official_and_estimate_or_adjustment_not_spliced(self):
        for key, value in [('measure_basis', 'vendor_estimate'), ('adjustment_basis', 'different_split_basis')]:
            d = pressure_document(); earlier = deepcopy(d['records'][-1]); earlier['id'] = 'earlier'
            earlier['payload'].update(settlement_date='2026-10-30', short_interest_shares=1800)
            earlier['payload'][key] = value; d['records'].append(earlier)
            self.assertEqual(market_flow.squeeze(d)['retrospective_short_interest_changes'], [])

    def test_direct_source_report_only_and_future_disclosure_excluded(self):
        a = record('close', 'disclosure', dict(IDENTITY, event_type='short_covering_disclosure',
            event_at='2026-11-11T20:00:00Z', covered_shares=100, position_scope='one fictional disclosed position',
            text_evidence='Fictional source explicitly reports a close.'))
        out = market_flow.squeeze(document([a]))
        self.assertEqual(out['reported_covering'][0]['source_reported_covered_shares'], 100)
        self.assertFalse(out['reported_covering'][0]['source_authenticity_verified'])
        a['payload']['event_at'] = '2026-11-12T20:00:00Z'
        self.assertEqual(market_flow.squeeze(document([a]))['reported_covering'], [])

    def test_zero_short_shares_never_candidate_even_under_zero_rule(self):
        d = pressure_document(); d['records'][-1]['payload']['short_interest_shares'] = 0
        d['settings']['squeeze_criteria'] = {'min_days_to_cover': 0}
        self.assertEqual(market_flow.squeeze(d)['assessments'][0]['state'], 'INSUFFICIENT_EVIDENCE')

    def test_later_short_measurement_does_not_label_earlier_flow_pressure(self):
        d = pressure_document()
        for index, day in [(0, '2026-11-05'), (1, '2026-11-06'), (2, '2026-11-09'), (3, '2026-11-09')]:
            p = d['records'][index]['payload']; p.update(start_at=day+'T14:30:00Z', end_at=day+'T15:30:00Z', session_id=day)
        out = market_flow.squeeze(d)
        self.assertEqual(out['assessments'][0]['state'], 'DATED_POSITIONING_CANDIDATE')
        self.assertEqual(out['assessments'][0]['flow_contexts'], [])

    def test_net_change_uses_original_decimals_not_rounded_output_floats(self):
        d = pressure_document(); earlier = deepcopy(d['records'][-1]); earlier['id'] = 'earlier'
        earlier['payload'].update(settlement_date='2026-10-30', short_interest_shares='10000000000000001')
        d['records'][-1]['payload']['short_interest_shares'] = '10000000000000000'
        d['records'].append(earlier)
        self.assertEqual(market_flow.squeeze(d)['retrospective_short_interest_changes'][0]['net_short_share_change'], -1)

    def test_input_preserved_and_all_outputs_json_safe_and_nonexecuting(self):
        d = pressure_document(); before = deepcopy(d)
        for fn in [market_flow.analyze, market_flow.positioning, market_flow.squeeze]:
            result = fn(d)
            json.dumps(result, allow_nan=False)
            self.assertIs(result['execution_authorized'], False)
            self.assertEqual(d, before)

    def test_unrecognized_or_nonfinite_rules_rejected(self):
        for rules in [{'magic_probability': .9}, {'min_days_to_cover': 'NaN'}, {'min_relative_volume': True}]:
            d = pressure_document(); d['settings']['squeeze_criteria'] = rules
            with self.assertRaises(ValueError): market_flow.squeeze(d)


if __name__ == '__main__':
    unittest.main()
