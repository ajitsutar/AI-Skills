"""Fictional contracts test reporting controls, not investment performance."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from horizon_review import resolve_horizon, review_scenarios, review_primary
from screen_review import review_screen
from price_audit import timestamp
from trading_calendar import event_gate


def fixture():
    return json.loads((ROOT / 'examples/fictional-horizon-screen.json').read_text(encoding='utf-8'))


class HorizonTests(unittest.TestCase):
    def test_90_calendar_days_are_not_three_months_or_90_sessions(self):
        spec = fixture()['horizon']
        outputs = []
        for unit, count in [('calendar_days', 90), ('calendar_months', 3), ('trading_sessions', 90)]:
            spec['duration'] = {'unit': unit, 'value': count}
            outputs.append(resolve_horizon(spec))
        self.assertEqual(outputs[0]['raw_deadline_date'], '2026-04-15')
        self.assertEqual(outputs[1]['raw_deadline_date'], '2026-04-15')  # Coincides for this anchor only.
        self.assertNotEqual(outputs[2]['exit_at'], outputs[0]['exit_at'])
        spec.update(anchor_date='2026-01-14')
        spec['duration'] = {'unit': 'calendar_days', 'value': 91}
        self.assertEqual(resolve_horizon(spec)['raw_deadline_date'], '2026-04-15')
        spec.update(as_of='2026-02-27T13:00:00Z', entry_at='2026-02-27T15:00:00Z',
                    latest_entry_at='2026-02-27T15:00:00Z', anchor_date='2026-02-27')
        spec['duration'] = {'unit':'calendar_days','value':90}
        self.assertEqual(resolve_horizon(spec)['raw_deadline_date'], '2026-05-28')
        spec['duration'] = {'unit':'calendar_months','value':3}
        self.assertEqual(resolve_horizon(spec)['raw_deadline_date'], '2026-05-27')

    def test_delayed_entry_does_not_move_fixed_end(self):
        spec = fixture()['horizon']
        original = resolve_horizon(spec)
        spec['entry_at'] = spec['latest_entry_at']
        delayed = resolve_horizon(spec)
        self.assertEqual(original['exit_at'], delayed['exit_at'])
        self.assertEqual(delayed['planned_calendar_days'], original['planned_calendar_days'] - 1)

    def test_rolling_entry_changes_deadline_and_reports_latest_possible_exit(self):
        spec = fixture()['horizon']
        spec['deadline_mode'] = 'rolling_from_entry'
        original = resolve_horizon(spec)
        self.assertNotEqual(original['exit_at'], original['latest_possible_exit_at'])
        spec.update(entry_at=spec['latest_entry_at'], anchor_date='2026-01-16')
        self.assertEqual(resolve_horizon(spec)['exit_at'], original['latest_possible_exit_at'])

    def test_weekend_deadline_moves_back_never_forward(self):
        spec = fixture()['horizon']
        spec['duration'] = {'unit': 'calendar_days', 'value': 2}
        result = resolve_horizon(spec)
        self.assertEqual(result['raw_deadline_date'], '2026-01-17')
        self.assertEqual(result['exit_session'], '2026-01-16')

    def test_calendar_weeks_supported(self):
        spec = fixture()['horizon']
        spec['duration'] = {'unit': 'calendar_weeks', 'value': 7}
        self.assertEqual(resolve_horizon(spec)['raw_deadline_date'], '2026-03-05')

    def test_same_session_day_trade_and_fundamental_route_separation(self):
        doc = fixture()
        spec = doc['horizon']
        spec.update(strategy_route='intraday', latest_entry_at=spec['entry_at'],
                    duration={'unit': 'same_session', 'value': 1})
        result = resolve_horizon(spec)
        self.assertEqual(result['exit_at'], '2026-01-15T20:45:00+00:00')
        self.assertEqual(result['planned_calendar_days'], 0)
        with self.assertRaisesRegex(ValueError, 'intraday clock'):
            review_screen(doc)

    def test_intraday_cannot_silently_become_overnight(self):
        spec = fixture()['horizon']
        spec.update(strategy_route='intraday', duration={'unit': 'calendar_days', 'value': 1})
        with self.assertRaisesRegex(ValueError, 'entry session'):
            resolve_horizon(spec)

    def test_elapsed_hour_and_minute_clocks(self):
        spec = fixture()['horizon']
        spec.update(strategy_route='intraday', anchor_at=spec['entry_at'], latest_entry_at=spec['entry_at'])
        for unit, count in [('elapsed_hours', 2), ('elapsed_minutes', 120)]:
            spec['duration'] = {'unit': unit, 'value': count}
            self.assertEqual(resolve_horizon(spec)['exit_at'], '2026-01-15T16:45:00+00:00')

    def test_early_close_exit_uses_actual_close(self):
        spec = fixture()['horizon']
        spec.update(as_of='2026-11-27T13:00:00Z', entry_at='2026-11-27T15:00:00Z',
                    latest_entry_at='2026-11-27T15:00:00Z', anchor_date='2026-11-27',
                    strategy_route='intraday', duration={'unit':'same_session','value':1})
        self.assertEqual(resolve_horizon(spec)['exit_at'], '2026-11-27T17:45:00+00:00')

    def test_ten_and_twenty_year_holds_are_supported_with_provisional_calendar(self):
        spec = fixture()['horizon']
        spec['strategy_route'] = 'long_term'
        for years in (10, 20):
            spec['duration'] = {'unit':'calendar_years','value':years}
            result = resolve_horizon(spec)
            self.assertEqual(result['raw_deadline_date'], f'{2026 + years}-01-15')
            self.assertTrue(result['calendar_refresh_required'])
            self.assertEqual(result['calendar_status'], 'PROVISIONAL')

    def test_eighteen_months_and_long_session_periods_are_supported(self):
        spec = fixture()['horizon']
        spec['strategy_route'] = 'long_term'
        spec['duration'] = {'unit':'calendar_months','value':18}
        self.assertEqual(resolve_horizon(spec)['raw_deadline_date'], '2027-07-15')
        spec['duration'] = {'unit':'trading_sessions','value':500}
        self.assertEqual(resolve_horizon(spec)['subsequent_sessions'], 500)

    def test_calendar_month_end_clamps(self):
        spec = fixture()['horizon']
        spec.update(as_of='2026-01-30T13:00:00Z', entry_at='2026-01-30T15:00:00Z',
                    latest_entry_at='2026-01-30T15:00:00Z', anchor_date='2026-01-30',
                    duration={'unit':'calendar_months','value':1})
        result = resolve_horizon(spec)
        self.assertEqual(result['raw_deadline_date'], '2026-02-28')
        self.assertEqual(result['exit_session'], '2026-02-27')

    def test_invalid_entry_or_duration_does_not_produce_a_plan(self):
        for key, value in [('entry_at','2026-01-17T15:00:00Z'),
                           ('latest_entry_at','2026-04-16T15:00:00Z'),
                           ('anchor_date','2026-02-01'), ('non_session_exit','next_session'),
                           ('duration',{'unit':'calendar_days','value':True}),
                           ('duration',{'unit':'calendar_days','value':-3}),
                           ('duration',{'unit':'calendar_years','value':1.5})]:
            spec = fixture()['horizon']
            spec[key] = value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                resolve_horizon(spec)

    def test_leap_day_year_clamps_to_february_end(self):
        spec = fixture()['horizon']
        spec.update(as_of='2028-02-29T13:00:00Z', entry_at='2028-02-29T15:00:00Z',
                    latest_entry_at='2028-02-29T15:00:00Z', anchor_date='2028-02-29',
                    strategy_route='long_term', duration={'unit':'calendar_years','value':1})
        self.assertEqual(resolve_horizon(spec)['raw_deadline_date'], '2029-02-28')

    def test_nonblocked_event_still_disclosed_during_hold(self):
        doc = fixture()
        doc['candidates'][0]['horizon_review']['event_calendar']['events'][0]['kind'] = 'dividend'
        events = review_screen(doc)['candidates'][0]['horizon_review']['events']
        self.assertTrue(events['clear'])
        self.assertEqual(events['holding_events'][0]['kind'], 'dividend')

    def test_event_beyond_exit_not_mistaken_for_within_hold_catalyst(self):
        doc = fixture()
        doc['candidates'][0]['horizon_review']['event_calendar']['events'][0].update(
            earliest_at='2026-04-23T21:00:00Z', latest_at='2026-04-23T23:00:00Z')
        doc['horizon']['event_policy']['scope'] = 'entry_and_hold'
        events = review_screen(doc)['candidates'][0]['horizon_review']['events']
        self.assertTrue(events['clear'])
        self.assertEqual(events['holding_events'], [])

    def test_event_after_exit_can_have_applicable_pre_event_blackout(self):
        doc = fixture()
        doc.pop('report')
        doc['candidates'][0]['horizon_review']['event_calendar']['events'][0].update(
            earliest_at='2026-04-16T21:00:00Z', latest_at='2026-04-16T23:00:00Z')
        doc['horizon']['event_policy']['scope'] = 'entry_and_hold'
        result = review_screen(doc)['candidates'][0]
        self.assertEqual(result['status'], 'Event-blocked')
        self.assertEqual(result['horizon_review']['events']['holding_events'], [])

    def test_entry_only_discloses_held_event_without_blocking_entry(self):
        result = review_screen(fixture())
        review = result['candidates'][0]
        self.assertEqual(review['status'], 'Eligible')
        self.assertEqual(len(review['horizon_review']['events']['holding_events']), 1)
        self.assertFalse(result['execution_authorized'])

    def test_same_event_blocks_entry_and_hold_policy(self):
        doc = fixture()
        doc['horizon']['event_policy']['scope'] = 'entry_and_hold'
        doc.pop('report')
        result = review_screen(doc)['candidates'][0]
        self.assertEqual(result['status'], 'Event-blocked')
        self.assertEqual(result['fundamental_status'], 'Eligible')

    def test_entry_inside_blackout_blocked_even_with_entry_only(self):
        doc = fixture()
        doc['candidates'][0]['horizon_review']['event_calendar']['events'][0].update(
            earliest_at='2026-01-16T21:00:00Z', latest_at='2026-01-16T23:00:00Z')
        doc.pop('report')
        self.assertEqual(review_screen(doc)['candidates'][0]['status'], 'Event-blocked')

    def test_unknown_incomplete_stale_and_future_calendar_never_clear(self):
        for key, value in [('coverage_verified', False), ('coverage_end','2026-02-01T00:00:00Z'),
                           ('checked_at','2026-01-13T13:00:00Z'), ('checked_at','2026-01-15T15:00:00Z')]:
            doc = fixture()
            doc['candidates'][0]['horizon_review']['event_calendar'][key] = value
            doc.pop('report')
            with self.subTest(key=key,value=value):
                result = review_screen(doc)['candidates'][0]
                self.assertEqual(result['status'], 'Watch')
                self.assertEqual(result['event_status'], 'unknown')

    def test_default_event_scope_preserves_strict_legacy_behavior(self):
        doc = fixture()
        policy = doc['horizon']['event_policy']
        policy.pop('scope')
        result = event_gate(doc['candidates'][0]['horizon_review']['event_calendar'],
                            doc['candidates'][0]['symbol'], policy,
                            now=timestamp('2026-01-15T14:00:00Z'), hold_until='2026-04-15T19:45:00Z')
        self.assertFalse(result['clear'])
        self.assertEqual(result['scope'], 'entry_and_hold')
        policy['scope'] = 'holding_window'
        legacy = event_gate(doc['candidates'][0]['horizon_review']['event_calendar'],
                           doc['candidates'][0]['symbol'], policy,
                           now=timestamp('2026-01-15T14:00:00Z'), hold_until='2026-04-15T19:45:00Z')
        self.assertEqual(legacy['blackouts'], result['blackouts'])
        self.assertEqual(legacy['scope'], 'entry_and_hold')

    def test_long_hold_rolling_reviews_do_not_invent_ten_year_event_clearance(self):
        doc = fixture()
        spec = doc['horizon']
        spec.update(strategy_route='long_term', duration={'unit':'calendar_years','value':10},
                    review_schedule={'next_review_at':'2026-03-01T14:00:00Z',
                                     'cadence':'quarterly and material events','evidence':['fictional review policy']})
        spec['event_policy']['coverage_mode'] = 'rolling_review'
        terminal = doc['candidates'][0]['horizon_review']['terminal_scenarios']
        terminal['exit_at'] = resolve_horizon(spec)['exit_at']
        terminal['cash_benchmark'].update(exit_at=terminal['exit_at'], instrument_maturity_at=terminal['exit_at'])
        result = review_screen(doc)['candidates'][0]['horizon_review']
        self.assertEqual(result['status'], 'Eligible')
        self.assertEqual(result['events_beyond_review'], 'UNASSESSED')
        spec['event_policy']['scope'] = 'entry_and_hold'
        with self.assertRaisesRegex(ValueError, 'entire hold'):
            review_screen(doc)

    def test_required_horizon_checks_cannot_be_omitted(self):
        doc = fixture()
        doc['candidates'][0]['horizon_review']['checks'].pop('thesis_timing')
        with self.assertRaisesRegex(ValueError, 'cannot include Watch'):
            review_screen(doc)

    def test_fundamental_reject_not_hidden_by_event_or_horizon(self):
        doc = fixture()
        doc.pop('report')
        doc['candidates'][0]['checks']['balance_sheet']['status'] = 'fail'
        doc['horizon']['event_policy']['scope'] = 'entry_and_hold'
        self.assertEqual(review_screen(doc)['candidates'][0]['status'], 'Reject')

    def test_material_horizon_risk_remains_speculative(self):
        doc = fixture()
        doc.pop('report')
        doc['candidates'][0]['horizon_review']['checks']['downside_liquidity']['status'] = 'material_risk'
        self.assertEqual(review_screen(doc)['candidates'][0]['status'], 'Speculative')

    def test_stale_quarter_cannot_pass_as_latest(self):
        doc = fixture()
        doc['candidates'][0]['primary_review']['reviewed_period_end'] = '2025-09-30'
        with self.assertRaisesRegex(ValueError, 'cannot include Watch'):
            review_screen(doc)

    def test_primary_future_information_and_stale_check_rejected(self):
        for key,value in [('latest_published_at','2026-01-16T12:00:00Z'),
                          ('checked_at','2026-01-13T13:00:00Z'),
                          ('checked_at','2026-01-16T12:00:00Z')]:
            section = fixture()['candidates'][0]['primary_review']
            section[key] = value
            with self.subTest(key=key,value=value):
                self.assertTrue(review_primary(section, timestamp('2026-01-15T14:00:00Z')))

    def test_terminal_scenarios_use_same_exit_and_net_costs(self):
        doc = fixture()
        result = review_screen(doc)['candidates'][0]['horizon_review']['terminal_scenarios']
        self.assertAlmostEqual(result['cases'][1]['net_return'], 0.078)
        self.assertAlmostEqual(result['cases'][1]['excess_over_cash'], 0.068)
        self.assertIsNone(result['probability_of_profit'])
        doc['candidates'][0]['horizon_review']['terminal_scenarios']['exit_at'] = '2027-01-15T20:45:00Z'
        with self.assertRaisesRegex(ValueError, 'cannot include Watch'):
            review_screen(doc)

    def test_scenarios_cannot_manufacture_probabilities_or_accept_nan(self):
        for key,value in [('probability',0.5), ('terminal_price',float('nan')), ('terminal_price',True)]:
            doc = fixture()
            doc['candidates'][0]['horizon_review']['terminal_scenarios']['cases'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                review_screen(doc)

    def test_legacy_manifest_cannot_claim_horizon_review(self):
        doc = json.loads((ROOT / 'examples/fictional-screen.json').read_text())
        result = review_screen(doc)
        self.assertEqual(result['decision_mode'], 'legacy_unspecified')
        self.assertIsNone(result['horizon'])
        doc['horizon'] = fixture()['horizon']
        with self.assertRaisesRegex(ValueError, 'requires decision_mode'):
            review_screen(doc)

    def test_no_method_and_future_universe_cannot_claim_review(self):
        for operation in ('method','universe'):
            doc = fixture()
            if operation == 'method':
                doc.pop('run_spec')
            else:
                doc['universe']['as_of'] = '2026-01-16T14:00:00Z'
            with self.subTest(operation=operation), self.assertRaises(ValueError):
                review_screen(doc)

    def test_long_term_mode_requires_latest_primary_review(self):
        doc = fixture()
        doc['decision_mode'] = 'long_term'
        doc['research_as_of'] = doc['horizon']['as_of']
        doc.pop('horizon')
        self.assertEqual(review_screen(doc)['candidates'][0]['status'], 'Eligible')
        doc['candidates'][0].pop('primary_review')
        with self.assertRaisesRegex(ValueError, 'cannot include Watch'):
            review_screen(doc)


if __name__ == '__main__':
    unittest.main()
