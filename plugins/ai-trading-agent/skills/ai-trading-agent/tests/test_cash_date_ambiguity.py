import copy
from datetime import datetime, timedelta
from decimal import Decimal, localcontext, ROUND_UP
from itertools import product
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import planning_alignment as planning
import investment_ops


def event(identifier, when, value, *, kind=None, currency='USD', confirmed=True, **extra):
    return {'id': identifier, 'kind': kind or ('cash_credit' if value > 0 else 'cash_debit'),
            'available_at': when, 'currency': currency, 'amount': value,
            'confirmed': confirmed, 'evidence': 'fictional declared cash event', **extra}


def document(events, **extra):
    return {'currency': 'USD', 'role': 'hypothetical_scenario',
            'as_of': '2026-10-13T15:00:00Z', 'settled_balances': {'USD': 500},
            'reservations': {'USD': 0}, 'floors': {'USD': 100}, 'events': events, **extra}


def full_path():
    return document([
        event('initial', '2026-10-14T13:00:00Z', -120),
        event('deferred', '2026-10-16T13:00:00Z', -450),
        event('withdrawal', '2026-10-16T10:00:00Z', -180, kind='withdrawal'),
        event('settlement', '2026-10-16', 300, kind='trade_settlement'),
        event('later', '2026-10-20T12:00:00Z', -150, kind='withdrawal')])


class CashDateAmbiguityTests(unittest.TestCase):
    def test_cash_cents_do_not_depend_on_process_decimal_precision(self):
        request = document([event('credit', '2026-10-14', 0.01)], calendar_timezone='UTC')
        for opening, expected in [('1234.56', '1234.57'),
                                  ('1234567890123456789012345678.56', '1234567890123456789012345678.57')]:
            request['settled_balances']['USD'] = opening
            with self.subTest(opening=opening):
                normal = planning.cash_plan(request)
                with localcontext() as context:
                    context.prec = 5
                    context.rounding = ROUND_UP
                    low_precision = planning.cash_plan(request)
                self.assertEqual(normal, low_precision)
                self.assertEqual(normal['helper_result']['ending_available']['USD'], expected)
                for scenario in normal['scenarios'].values():
                    self.assertEqual(Decimal(scenario['conservation_residual']['USD']), Decimal(0))

    def bounds(self, result, currency='USD'):
        return result['cash_bounds'][currency]

    def test_full_deferred_path_and_later_withdrawal_survive_negative_cash(self):
        request = full_path(); request['calendar_timezone'] = 'UTC'
        unchanged = copy.deepcopy(request)
        result = planning.cash_plan(request)
        self.assertEqual(request, unchanged)
        self.assertEqual(result['source_events'], request['events'])
        self.assertEqual(result['status'], 'DATE_ONLY_TIMING_ENVELOPE')
        self.assertEqual(self.bounds(result)['minimum_available_range'], {'lower': '-250', 'upper': '-100'})
        self.assertEqual(self.bounds(result)['maximum_floor_gap_range'], {'lower': '200', 'upper': '350'})
        self.assertEqual(self.bounds(result)['ending_available_range'], {'lower': '-100', 'upper': '-100'})
        favorable = result['scenarios']['favorable_ordering']['timeline']
        adverse = result['scenarios']['adverse_ordering']['timeline']
        self.assertEqual([r['id'] for r in favorable], ['initial', 'settlement', 'withdrawal', 'deferred', 'later'])
        self.assertEqual([r['id'] for r in adverse], ['initial', 'withdrawal', 'deferred', 'settlement', 'later'])
        self.assertEqual([r['available'] for r in adverse], ['380', '200', '-250', '50', '-100'])
        for scenario in result['scenarios'].values():
            self.assertEqual(len(scenario['timeline']), len(request['events']))
            self.assertEqual(scenario['conservation_residual']['USD'], '0')
            self.assertEqual(scenario['ending_available']['USD'], '-100')
            by_id = {r['id']: r for r in scenario['timeline']}
            self.assertIsNone(by_id['settlement']['at'])
            self.assertEqual(by_id['withdrawal']['at'], request['events'][2]['available_at'])
        self.assertIsNone(result['helper_result']['timeline'])
        self.assertIsNone(result['spendable_cash'])
        self.assertFalse(result['execution_authorized'])

    def test_unknown_timezone_is_actionable_with_explicit_relaxed_bounds(self):
        result = planning.cash_plan(full_path())
        self.assertEqual(result['status'], 'UNRESOLVED_TIMING')
        self.assertEqual(result['missing_data'][0]['reason'], 'DATE_TIMEZONE_REQUIRED')
        timing = next(r for r in result['event_timing'] if r['id'] == 'settlement')
        self.assertIsNone(timing['calendar_timezone'])
        self.assertIsNone(timing['interval'])
        self.assertIsNone(result['helper_result']['ending_available'])
        self.assertEqual(result['envelope_basis'], 'RELAXED_CONDITIONAL_ORDERING_BOUNDS')
        self.assertEqual(self.bounds(result)['minimum_available_range'], {'lower': '-400', 'upper': '-100'})
        self.assertEqual(self.bounds(result)['ending_available_range'], {'lower': '-100', 'upper': '-100'})
        self.assertTrue(any('not a verified date-feasible path' in s for s in result['scenario_assumptions']))

    def test_known_date_is_before_or_after_exact_debit_as_declared(self):
        for cash_date, expected in [('2026-10-15', '200'), ('2026-10-17', '-100')]:
            with self.subTest(cash_date=cash_date):
                request = document([event('cash', cash_date, 300), event('demand', '2026-10-16T12:00:00Z', -600)],
                                   calendar_timezone='UTC')
                result = planning.cash_plan(request)
                self.assertEqual(self.bounds(result)['minimum_available_range'], {'lower': expected, 'upper': expected})
                self.assertEqual(self.bounds(result)['ending_available_range'], {'lower': '200', 'upper': '200'})

    def test_date_only_debit_has_two_orderings_without_rescheduling_source(self):
        request = document([event('demand', '2026-10-16', -600, kind='withdrawal'),
                            event('cash', '2026-10-16T12:00:00Z', 300)], calendar_timezone='UTC')
        result = planning.cash_plan(request)
        self.assertEqual(self.bounds(result)['minimum_available_range'], {'lower': '-100', 'upper': '200'})
        self.assertEqual(result['source_events'], request['events'])
        for scenario in result['scenarios'].values():
            row = next(r for r in scenario['timeline'] if r['id'] == 'demand')
            self.assertIsNone(row['at'])
            self.assertEqual(row['source_available_at'], '2026-10-16')

    def test_exact_midnight_demand_precedes_credit_at_earliest_date_boundary(self):
        request = document([event('cash', '2026-10-16', 300), event('debit', '2026-10-16T00:00:00Z', -600)],
                           calendar_timezone='UTC')
        result = planning.cash_plan(request)
        self.assertEqual(self.bounds(result)['minimum_available_range'], {'lower': '-100', 'upper': '-100'})

    def test_exclusive_end_limit_precedes_next_day_exact_cash(self):
        request = document([event('debit', '2026-10-16', -600), event('cash', '2026-10-17T00:00:00Z', 300)],
                           calendar_timezone='UTC')
        result = planning.cash_plan(request)
        self.assertEqual(self.bounds(result)['minimum_available_range'], {'lower': '-100', 'upper': '-100'})

    def test_overlapping_different_zones_bound_independently_enumerated_paths(self):
        request = document([
            event('a-credit', '2026-10-16', 100, calendar_timezone='UTC'),
            event('b-debit', '2026-10-16', -120, calendar_timezone='+05:30'),
            event('c-credit', '2026-10-15', 20, calendar_timezone='-07:00'),
            event('fixed-demand', '2026-10-16T10:00:00Z', -80)],
            settled_balances={'USD': 50}, floors={'USD': 0})
        result = planning.cash_plan(request)
        # Independent timestamp-only replays sample both limits and midday for
        # every uncertain flow. This checks overlapping intervals jointly,
        # including a date-only debit and different declared calendar zones.
        choices = []
        for timing in result['event_timing'][:3]:
            low = datetime.fromisoformat(timing['interval']['start_inclusive'])
            high = datetime.fromisoformat(timing['interval']['end_exclusive'])
            choices.append([low, low + (high - low) / 2, high - timedelta(microseconds=1)])
        minima = []
        for available in product(*choices):
            exact = copy.deepcopy(request)
            for row, at in zip(exact['events'], available):
                row['available_at'] = at.isoformat()
            minima.append(Decimal(str(planning.cash_plan(exact)['troughs']['USD']['minimum_available'])))
        claimed = self.bounds(result)['minimum_available_range']
        self.assertEqual(min(minima), Decimal(claimed['lower']))
        self.assertEqual(max(minima), Decimal(claimed['upper']))

    def test_opening_overlap_is_not_silently_counted_as_new_future_cash(self):
        request = document([event('cash', '2026-10-13', 300), event('demand', '2026-10-14T12:00:00Z', -600)],
                           calendar_timezone='UTC')
        result = planning.cash_plan(request)
        self.assertEqual(result['status'], 'UNRESOLVED_TIMING')
        self.assertEqual(result['missing_data'][0]['reason'], 'DATE_OVERLAPS_AS_OF_OPENING_INCLUSION_UNKNOWN')
        self.assertIsNone(result['helper_result']['ending_available'])
        self.assertTrue(any('not already included' in s for s in result['scenario_assumptions']))
        self.assertEqual(self.bounds(result)['ending_available_range'], {'lower': '200', 'upper': '200'})
        request['events'][0]['available_at'] = '2026-10-12'
        with self.assertRaisesRegex(ValueError, 'FUTURE_EVENTS_ONLY'):
            planning.cash_plan(request)

    def test_unknown_dates_and_opening_debt_keep_signed_shortfalls(self):
        request = document([event('cash', '2026-10-16', 5)], settled_balances={'USD': -12}, floors={'USD': 0})
        result = planning.cash_plan(request)
        self.assertEqual(self.bounds(result)['minimum_available_range'], {'lower': '-12', 'upper': '-12'})
        self.assertEqual(self.bounds(result)['ending_available_range'], {'lower': '-7', 'upper': '-7'})
        self.assertEqual(self.bounds(result)['shortfall_classification'], 'IN_EVERY_CONDITIONAL_ORDERING')

    def test_excluded_unconfirmed_credit_remains_visible_and_never_funds_path(self):
        request = document([event('unknown-credit', '2026-10-16', 900, confirmed=False),
                            event('demand', '2026-10-16T12:00:00Z', -600)])
        result = planning.cash_plan(request)
        self.assertEqual(result['source_events'], request['events'])
        self.assertEqual(result['helper_result']['ignored_unconfirmed_credits'], ['unknown-credit'])
        self.assertEqual(result['missing_data'], [])
        self.assertEqual(self.bounds(result)['ending_available_range'], {'lower': '-100', 'upper': '-100'})
        for scenario in result['scenarios'].values():
            self.assertEqual([r['id'] for r in scenario['timeline']], ['demand'])

    def test_per_currency_holds_cash_flows_and_non_cash_are_conserved(self):
        request = document([
            event('dollars', '2026-10-16', 75),
            event('usd-debit', '2026-10-16T12:00:00Z', -160, reservation_release=40),
            event('euros', '2026-10-16', 5, currency='EUR'),
            event('eur-debit', '2026-10-17T12:00:00Z', -50, currency='EUR', reservation_release=10)],
            calendar_timezone='UTC', settled_balances={'USD': 100, 'EUR': 20},
            reservations={'USD': 40, 'EUR': 10}, floors={'USD': 0, 'EUR': 2},
            noncash_events=[{'id': 'grant', 'kind': 'future_stock_grant', 'shares': 200}])
        result = planning.cash_plan(request)
        self.assertEqual(result['noncash_events_not_funding'], request['noncash_events'])
        self.assertEqual(self.bounds(result)['ending_available_range'], {'lower': '15', 'upper': '15'})
        self.assertEqual(self.bounds(result, 'EUR')['ending_available_range'], {'lower': '-25', 'upper': '-25'})
        for scenario in result['scenarios'].values():
            self.assertEqual(scenario['remaining_reservations'], {'USD': '0', 'EUR': '0'})
            self.assertEqual(scenario['conservation_residual'], {'USD': '0', 'EUR': '0'})

    def test_decimal_cash_is_not_lost_through_float_conversion(self):
        request = document([event('cash', '2026-10-16', 1)], calendar_timezone='UTC',
                           settled_balances={'USD': '100000000000000000.25'})
        result = planning.cash_plan(request)
        self.assertEqual(self.bounds(result)['ending_available_range']['lower'], '100000000000000001.25')

    def test_fixed_offset_and_event_override_define_calendar_not_machine_timezone(self):
        request = document([event('cash', '2026-10-16', 300, calendar_timezone='+05:30')], calendar_timezone='UTC')
        result = planning.cash_plan(request)
        interval = result['event_timing'][0]['interval']
        self.assertEqual(interval['start_inclusive'], '2026-10-15T18:30:00+00:00')
        self.assertEqual(interval['end_exclusive'], '2026-10-16T18:30:00+00:00')
        request['events'][0]['calendar_timezone'] = 'unknown'
        self.assertEqual(planning.cash_plan(request)['status'], 'UNRESOLVED_TIMING')

    def test_iana_dst_days_use_actual_local_boundaries(self):
        request = document([event('cash', '2027-03-14', 1)], calendar_timezone='America/New_York')
        spring = planning.cash_plan(request)['event_timing'][0]['interval']
        self.assertEqual(spring['start_inclusive'], '2027-03-14T05:00:00+00:00')
        self.assertEqual(spring['end_exclusive'], '2027-03-15T04:00:00+00:00')
        request['events'][0]['available_at'] = '2026-11-01'
        fall = planning.cash_plan(request)['event_timing'][0]['interval']
        self.assertEqual(fall['start_inclusive'], '2026-11-01T04:00:00+00:00')
        self.assertEqual(fall['end_exclusive'], '2026-11-02T05:00:00+00:00')

    def test_nonexistent_and_ambiguous_midnight_require_exact_timing(self):
        for zone, day in [('Pacific/Apia', '2011-12-30'), ('America/Havana', '2026-11-01')]:
            with self.subTest(zone=zone):
                request = document([event('cash', day, 1)], calendar_timezone=zone, as_of='2011-12-01T00:00:00Z')
                result = planning.cash_plan(request)
                self.assertEqual(result['status'], 'UNRESOLVED_TIMING')
                self.assertEqual(result['missing_data'][0]['reason'], 'LOCAL_DATE_BOUNDARY_AMBIGUOUS_OR_NONEXISTENT')

    def test_exact_timestamp_contract_keeps_legacy_ordering_and_outputs(self):
        request = full_path()
        request['events'][3]['available_at'] = '2026-10-16T10:00:00Z'
        result = planning.cash_plan(request)
        legacy = investment_ops.cash_ladder(**{k: request[k] for k in ('as_of', 'settled_balances', 'reservations', 'events', 'floors')})
        self.assertEqual(result['helper_result'], legacy)
        self.assertNotIn('cash_bounds', result)
        self.assertEqual(result['troughs']['USD']['minimum_available'], -100)

    def test_required_evidence_and_invalid_input_contracts(self):
        baseline = full_path(); baseline['calendar_timezone'] = 'UTC'
        mutations = [
            ('CALENDAR_TIMEZONE', lambda d: d.update(calendar_timezone='Not/AZone')),
            ('CALENDAR_TIMEZONE', lambda d: d.update(calendar_timezone='+25:00')),
            ('INVALID_CASH_CALENDAR_DATE', lambda d: d['events'][3].update(available_at='2026-02-30')),
            ('DUPLICATE_CASH_EVENT', lambda d: d['events'][3].update(id='initial')),
            ('CONFIRMATION_FLAG', lambda d: d['events'][3].update(confirmed='true')),
            ('CASH_TIMING_EVIDENCE', lambda d: d['events'][3].pop('evidence')),
            ('UNKNOWN_CURRENCY', lambda d: d['events'][3].update(currency='EUR')),
            ('CURRENCY_MAP', lambda d: d.update(reservations={})),
            ('DEBIT_SIGN', lambda d: d['events'][0].update(amount=1)),
            ('FINITE', lambda d: d['events'][3].update(amount='NaN')),
            ('RELEASE_CANNOT', lambda d: d['events'][3].update(reservation_release=1)),
            ('RESERVATION_ALREADY', lambda d: d['events'][0].update(reservation_release=1)),
            ('timezone', lambda d: d.update(as_of='2026-10-13')),
            ('timezone', lambda d: d['events'][0].update(available_at='2026-10-14T13:00:00')),
        ]
        for expected, change in mutations:
            with self.subTest(expected=expected):
                request = copy.deepcopy(baseline); change(request)
                with self.assertRaisesRegex(ValueError, expected):
                    planning.cash_plan(request)


if __name__ == '__main__':
    unittest.main()
