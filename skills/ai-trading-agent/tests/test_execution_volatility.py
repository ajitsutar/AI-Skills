"""Stock-relative execution checks: data quality, leakage, and sparse coverage."""
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from execution_volatility import DEFAULT_CONFIG, evaluate_volatility, normalize_config


def fixture(count=20):
    current_open = datetime(2026, 10, 13, 13, 30, tzinfo=timezone.utc)
    now = current_open + timedelta(minutes=10, seconds=10)
    sessions, bars = [], []
    rates = ['0.01', '-0.02', '0.03', '-0.04', '0.05', '-0.06']
    for offset in range(count, -1, -1):
        opening = current_open - timedelta(days=offset)
        session_id = opening.date().isoformat()
        sessions.append({'session_id': session_id, 'open': opening.isoformat(),
                         'close': (opening + timedelta(minutes=30)).isoformat()})
        if offset:
            for index, rate in enumerate(rates):
                start = opening + timedelta(minutes=5 * index)
                bars.append({'session_id': session_id, 'start': start.isoformat(),
                             'end': (start + timedelta(minutes=5)).isoformat(),
                             'open': '100', 'close': str(Decimal(100) + Decimal(rate))})
    current = {'session_id': current_open.date().isoformat(),
               'start': (current_open + timedelta(minutes=5)).isoformat(),
               'end': (current_open + timedelta(minutes=10)).isoformat(),
               'open': '100', 'close': '100.04'}
    return {'symbol': 'TEST', 'sessions': sessions, 'bars': bars, 'current_bar': current,
            'source': {'symbol': 'TEST', 'provider': 'Synthetic unit-test fixture',
                       'evidence_ref': 'fixture://intervals', 'interval_minutes': 5,
                       'basis': 'unadjusted', 'retrieved_at': now.isoformat(),
                       'corporate_actions_verified': True}}, now


class ExecutionVolatilityTests(unittest.TestCase):
    def setUp(self):
        self.context, self.now = fixture()

    def run_check(self):
        return evaluate_volatility(self.context, self.now)

    def assert_unavailable(self, contains):
        result = self.run_check()
        self.assertFalse(result['within_historical_range'])
        self.assertEqual(result['status'], 'data_unavailable')
        self.assertIsNone(result['observation_refresh_after'])
        self.assertIn(contains, ' '.join(result['reasons']))

    def test_normal_observation_reports_configuration_and_exact_threshold(self):
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['status'], 'normal')
        self.assertEqual(result['evidence']['config'], DEFAULT_CONFIG)
        self.assertEqual(result['evidence']['threshold_pct'], '0.06')
        self.assertEqual(result['evidence']['current_absolute_move_pct'], '0.04')
        self.assertEqual(result['evidence']['sample_count'], 120)
        self.assertEqual(len(result['evidence']['config_hash']), 64)

    def test_unusual_up_and_down_moves_pause_symmetrically(self):
        for close in ('102', '98'):
            with self.subTest(close=close):
                self.context['current_bar']['close'] = close
                result = self.run_check()
                self.assertFalse(result['within_historical_range'])
                self.assertEqual(result['status'], 'excessive_volatility')
                self.assertEqual(result['evidence']['current_absolute_move_pct'], '2')

    def test_threshold_equality_does_not_pause(self):
        self.context['current_bar']['close'] = '100.06'
        self.assertTrue(self.run_check()['within_historical_range'])

    def test_no_fixed_stock_percentage_threshold(self):
        for row in self.context['bars']:
            row['close'] = '105'
        self.context['current_bar']['close'] = '104'
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['threshold_pct'], '5')

    def test_constant_baseline_zero_current_is_normal(self):
        for row in self.context['bars']:
            row['close'] = row['open']
        self.context['current_bar']['close'] = '100'
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertTrue(result['evidence']['zero_baseline_threshold'])

    def test_constant_baseline_nonzero_move_is_disclosed_as_unusual(self):
        for row in self.context['bars']:
            row['close'] = row['open']
        self.context['current_bar']['close'] = '100.000001'
        result = self.run_check()
        self.assertEqual(result['status'], 'excessive_volatility')
        self.assertIn('percentile is zero', result['reasons'][0])

    def test_single_historical_outlier_does_not_set_99th_percentile_for_120_samples(self):
        self.context['bars'][0]['close'] = '200'
        result = self.run_check()
        self.assertEqual(result['evidence']['percentile_rank'], 119)
        self.assertEqual(result['evidence']['threshold_pct'], '0.06')

    def test_sparse_intervals_disclose_coverage_without_automatic_block(self):
        self.context['bars'] = self.context['bars'][1:]
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['missing_intervals'], 1)
        self.assertEqual(result['evidence']['sample_count'], 119)

    def test_short_sample_pauses_for_data_not_for_volatility(self):
        self.context['bars'] = self.context['bars'][:99]
        self.assert_unavailable('sample count')
        self.assertEqual(self.run_check()['evidence']['sample_count'], 99)

    def test_minimum_samples_is_configurable(self):
        self.context['config'] = {'min_samples': 2}
        self.context['bars'] = self.context['bars'][:2]
        self.assertTrue(self.run_check()['within_historical_range'] is False)  # 0.04 exceeds 0.02.
        self.assertEqual(self.run_check()['status'], 'excessive_volatility')

    def test_lookback_uses_last_calendar_sessions_excluding_older_outlier(self):
        self.context, self.now = fixture(21)
        for row in self.context['bars'][:6]:
            row['close'] = '200'
        result = self.run_check()
        self.assertEqual(result['evidence']['sample_count'], 120)
        self.assertEqual(result['evidence']['threshold_pct'], '0.06')
        self.assertEqual(len(result['evidence']['baseline_sessions']), 20)

    def test_current_session_and_current_bar_never_enter_baseline(self):
        prefix = copy.deepcopy(self.context['current_bar'])
        prefix['end'], prefix['start'] = prefix['start'], self.context['sessions'][-1]['open']
        prefix['close'] = '300'
        current = copy.deepcopy(self.context['current_bar'])
        current['close'] = '400'
        self.context['bars'].extend([prefix, current])
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['threshold_pct'], '0.06')
        self.assertEqual(result['evidence']['sample_count'], 120)
        self.assertEqual(result['evidence']['excluded_current_or_outside_window_intervals'], 2)

    def test_future_bar_is_not_used(self):
        future = copy.deepcopy(self.context['current_bar'])
        future['start'] = future['end']
        future['end'] = (self.now + timedelta(minutes=4, seconds=50)).isoformat()
        self.context['bars'].append(future)
        self.assert_unavailable('future-dated')

    def test_overnight_cross_session_return_is_excluded(self):
        cross = copy.deepcopy(self.context['bars'][5])
        cross.pop('session_id')
        cross['start'] = self.context['bars'][5]['end']
        cross['end'] = self.context['bars'][6]['start']
        cross['close'] = '300'
        self.context['bars'].insert(6, cross)
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['excluded_noncomparable_intervals'], 1)

    def test_unknown_interval_or_gap_return_not_rescaled(self):
        self.context['bars'][0]['end'] = self.context['bars'][1]['end']
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['sample_count'], 119)
        self.assertEqual(result['evidence']['excluded_noncomparable_intervals'], 1)

    def test_timestamp_jitter_is_not_a_known_comparable_interval(self):
        row = self.context['bars'][0]
        row['start'] = (datetime.fromisoformat(row['start']) + timedelta(microseconds=1)).isoformat()
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['excluded_noncomparable_intervals'], 1)
        self.context['current_bar']['start'] = (datetime.fromisoformat(
            self.context['current_bar']['start']) + timedelta(microseconds=1)).isoformat()
        self.assert_unavailable('exact within-session')

    def test_duplicate_or_out_of_order_bars_are_unavailable(self):
        self.context['bars'].insert(0, copy.deepcopy(self.context['bars'][0]))
        self.assert_unavailable('duplicate')

    def test_incomplete_current_interval_is_not_normal(self):
        self.context['current_bar']['complete'] = False
        self.assert_unavailable('Incomplete bar')

    def test_synthetic_interpolated_history_is_not_a_real_observation(self):
        self.context['bars'][0]['interpolated'] = True
        self.context['bars'][0]['close'] = self.context['bars'][0]['open']
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['sample_count'], 119)
        self.assertEqual(result['evidence']['excluded_noncomparable_intervals'], 1)

    def test_interpolated_current_bar_requires_a_real_observation(self):
        self.context['current_bar']['interpolated'] = True
        self.assert_unavailable('Interpolated current bar')

    def test_interpolated_flag_cannot_be_truthy_text(self):
        self.context['bars'][0]['interpolated'] = 'false'
        self.assert_unavailable('must be Boolean')

    def test_stale_current_interval_requires_new_observation(self):
        self.now += timedelta(minutes=5)
        self.context['source']['retrieved_at'] = self.now.isoformat()
        self.assert_unavailable('latest completed')

    def test_no_completed_interval_at_session_open(self):
        self.now = datetime.fromisoformat(self.context['sessions'][-1]['open'])
        self.context['source']['retrieved_at'] = self.now.isoformat()
        self.assert_unavailable('No completed interval')

    def test_source_freshness_has_exclusive_boundary(self):
        self.context['source']['retrieved_at'] = (self.now - timedelta(seconds=900)).isoformat()
        self.assert_unavailable('stale')

    def test_future_source_is_unavailable(self):
        self.context['source']['retrieved_at'] = (self.now + timedelta(seconds=1)).isoformat()
        self.assert_unavailable('future-dated')

    def test_source_cannot_claim_bar_that_closed_after_retrieval(self):
        self.context['source']['retrieved_at'] = (self.now - timedelta(seconds=11)).isoformat()
        self.assert_unavailable('available at retrieval')

    def test_unknown_corporate_actions_are_data_unavailable(self):
        self.context['source']['corporate_actions_verified'] = False
        self.assert_unavailable('Corporate-action')

    def test_mismatched_basis_or_instrument_is_rejected(self):
        for key, value, message in [('basis', 'split_adjusted', 'basis'), ('symbol', 'OTHER', 'symbol')]:
            with self.subTest(key=key):
                self.context['bars'][0][key] = value
                self.assert_unavailable(message)
                self.context['bars'][0].pop(key)

    def test_nonpositive_or_nonfinite_prices_are_not_normal(self):
        for value in ('0', '-1', 'NaN', 'Infinity', True):
            with self.subTest(value=value):
                self.context['current_bar']['close'] = value
                self.assertEqual(self.run_check()['status'], 'data_unavailable')

    def test_naive_timestamp_is_rejected(self):
        self.context['current_bar']['end'] = '2026-10-13T13:40:00'
        self.assert_unavailable('timezone')

    def test_result_deadline_is_next_completed_interval(self):
        self.assertEqual(self.run_check()['observation_refresh_after'], '2026-10-13T13:45:00+00:00')

    def test_tighter_configured_freshness_shortens_deadline(self):
        self.context['config'] = {'max_age_seconds': 30}
        self.assertEqual(self.run_check()['observation_refresh_after'], '2026-10-13T13:40:30+00:00')

    def test_configuration_change_changes_hash_and_replay_is_deterministic(self):
        before = self.run_check()
        self.assertEqual(before, self.run_check())
        self.context['config'] = {'percentile': 95}
        after = self.run_check()
        self.assertNotEqual(before['evidence']['config_hash'], after['evidence']['config_hash'])
        self.context['config'] = {'percentile': 99.0}
        self.assertEqual(before['evidence']['config_hash'], self.run_check()['evidence']['config_hash'])

    def test_invalid_configuration_never_silently_defaults(self):
        for supplied in ({'percentile': 0}, {'percentile': 101}, {'min_samples': True},
                         {'interval_minutes': 0}, {'lookback_sessions': -1}, {'spred': 2}):
            with self.subTest(supplied=supplied):
                self.context['config'] = supplied
                self.assertEqual(self.run_check()['status'], 'data_unavailable')

    def test_sessions_and_bar_session_ids_can_be_derived(self):
        supplied = self.context.pop('sessions')
        for bar in self.context['bars'] + [self.context['current_bar']]:
            bar.pop('session_id')
        calendar_rows = [dict(row, date=row['session_id']) for row in supplied]
        with patch('trading_calendar.sessions', return_value=calendar_rows) as calendar:
            result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(result['evidence']['calendar_source'], 'exchange_calendars/XNYS')
        self.assertEqual(calendar.call_args.args[-1], 'XNYS')

    def test_real_exchange_calendar_excludes_weekend_observations(self):
        self.context.pop('sessions')
        self.context['config'] = {'min_samples': 20}
        for bar in self.context['bars'] + [self.context['current_bar']]:
            bar.pop('session_id')
        result = self.run_check()
        self.assertTrue(result['within_historical_range'])
        self.assertEqual(len(result['evidence']['baseline_sessions']), 20)
        self.assertNotIn('2026-10-11', result['evidence']['baseline_sessions'])
        self.assertGreater(result['evidence']['excluded_noncomparable_intervals'], 0)
        self.assertLess(result['evidence']['sample_count'], 120)

    def test_minimal_source_as_of_alias(self):
        self.context['source']['as_of'] = self.context['source'].pop('retrieved_at')
        self.assertTrue(self.run_check()['within_historical_range'])

    def test_no_mutation_of_input(self):
        original = copy.deepcopy(self.context)
        self.run_check()
        self.assertEqual(self.context, original)

    def test_missing_context_yields_actionable_data_status(self):
        result = evaluate_volatility({}, self.now)
        self.assertEqual(result['status'], 'data_unavailable')
        self.assertIn('symbol', result['reasons'][0])

    def test_cli_outputs_adverse_observation_without_execution_veto(self):
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'execution_volatility.py'
        self.context['current_bar']['close'] = '103'
        process = subprocess.run([sys.executable, str(path)], input=json.dumps(
            {'context': self.context, 'now': self.now.isoformat()}), text=True, capture_output=True)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)['status'], 'excessive_volatility')
        self.assertEqual(process.stderr, '')


if __name__ == '__main__':
    unittest.main()
