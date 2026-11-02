"""Preference-neutral comparison and explicit listed-date path invariants."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_comparison import alternative_comparison, settlement_transfer_paths


def document(**fields):
    return {'currency': 'USD', 'role': 'hypothetical_scenario', **fields}


def comparison():
    return document(criteria=[
        {'id': 'cost', 'metric': 'total_cost', 'unit': 'USD', 'basis': 'same-scenario-all-in', 'direction': 'minimize'},
        {'id': 'benefit', 'metric': 'concentration_reduction', 'unit': 'fraction', 'basis': 'same-projected-equity', 'direction': 'maximize'}],
        alternatives=[{'id': 'low_cost', 'values': {'cost': '2.7', 'benefit': '.02'}},
                      {'id': 'large_reduction', 'values': {'cost': '4.1', 'benefit': '.04'}},
                      {'id': 'inferior', 'values': {'cost': '4.1', 'benefit': '.01'}}])


def dates():
    # Deliberately irregular supplied sequence: no actual weekday inference.
    return document(business_dates=['2037-04-02', '2037-04-05', '2037-04-09', '2037-04-10', '2037-04-18'],
                    sale_date='2037-04-02', settlement_lag=1, transfer_lag=1,
                    spendable_deadline='2037-04-09')


class AlternativeComparisonTests(unittest.TestCase):
    def test_conflicting_objectives_keep_both_without_winner(self):
        result = alternative_comparison(comparison())
        self.assertEqual(result['non_dominated_ids'], ['low_cost', 'large_reduction'])
        self.assertEqual(result['dominated_ids'], ['inferior'])
        self.assertIsNone(result['selected_alternative'])
        pair = result['pairwise'][0]
        self.assertEqual(pair['relation'], 'TRADEOFF')
        self.assertEqual(pair['left_favored_criteria'], ['cost'])
        self.assertEqual(pair['right_favored_criteria'], ['benefit'])

    def test_unknown_cannot_dominate_or_be_excluded(self):
        for missing in (None, 'absent'):
            data = comparison()
            if missing is None:
                data['alternatives'][2]['values']['benefit'] = None
            else:
                del data['alternatives'][2]['values']['benefit']
            result = alternative_comparison(data)
            self.assertEqual(result['dominated_ids'], [])
            self.assertEqual(result['not_proven_dominated_ids'], ['low_cost', 'large_reduction', 'inferior'])
            self.assertEqual(result['non_dominated_ids'], [])
            self.assertEqual(len(result['indeterminate_ids']), 3)
            for pair in result['pairwise'][1:]:
                self.assertEqual(pair['relation'], 'INDETERMINATE')
                self.assertIsNone(pair['dominant_id'])

    def test_dimension_mismatch_and_missing_block_dominance(self):
        for dimension in ('metric', 'unit', 'basis'):
            for mode in ('missing', 'mismatch'):
                data = comparison()
                criterion = data['criteria'][1]
                record = {'value': '.01', **{k: criterion[k] for k in ('metric', 'unit', 'basis')}}
                if mode == 'missing':
                    del record[dimension]
                else:
                    record[dimension] = 'different'
                data['alternatives'][2]['values']['benefit'] = record
                result = alternative_comparison(data)
                self.assertIn('inferior', result['indeterminate_ids'])
                self.assertNotIn('inferior', result['dominated_ids'])

    def test_permutation_changes_only_presentation_not_pareto_sets(self):
        data = comparison(); first = alternative_comparison(data)
        data['alternatives'].reverse(); data['criteria'].reverse()
        second = alternative_comparison(data)
        self.assertEqual(set(first['non_dominated_ids']), set(second['non_dominated_ids']))
        self.assertEqual(second['non_dominated_ids'], ['large_reduction', 'low_cost'])
        self.assertEqual(first['dominated_ids'], second['dominated_ids'])
        self.assertFalse(second['input_order_is_priority'])

    def test_equality_is_not_strict_dominance_and_decimal_boundaries_are_exact(self):
        data = comparison()
        data['alternatives'] = [{'id': 'a', 'values': {'cost': '2.7000000000000000000000000001', 'benefit': '0'}},
                                {'id': 'b', 'values': {'cost': '2.7', 'benefit': '0'}}]
        self.assertEqual(alternative_comparison(data)['dominated_ids'], ['a'])
        data['alternatives'][0]['values']['cost'] = '2.700'
        result = alternative_comparison(data)
        self.assertEqual(result['dominated_ids'], [])
        self.assertEqual(result['pairwise'][0]['relation'], 'EQUIVALENT_ON_DECLARED_CRITERIA')
        self.assertIsNone(result['selected_alternative'])

    def test_single_unknown_is_indeterminate_and_preferences_not_silently_applied(self):
        data = comparison(); data['alternatives'] = [data['alternatives'][0]]
        data['alternatives'][0]['values']['cost'] = None
        self.assertEqual(alternative_comparison(data)['indeterminate_ids'], ['low_cost'])
        data['weights'] = {'cost': 1}
        with self.assertRaises(ValueError):
            alternative_comparison(data)

    def test_source_preserved_and_nonfinite_rejected(self):
        data = comparison(); original = deepcopy(data)
        result = alternative_comparison(data)
        self.assertEqual(data, original)
        self.assertEqual(result['retained_input'], original)
        for invalid in ('NaN', 'Infinity', True):
            data['alternatives'][0]['values']['cost'] = invalid
            with self.assertRaises(ValueError):
                alternative_comparison(data)


class SettlementTransferTests(unittest.TestCase):
    def test_same_day_is_possible_next_day_late_and_initiation_not_arrival(self):
        result = settlement_transfer_paths(dates())
        same, following = result['paths']
        self.assertEqual(result['settlement_date'], '2037-04-05')
        self.assertEqual(same['transfer_initiation_date'], '2037-04-05')
        self.assertEqual(same['arrival_date'], '2037-04-09')
        self.assertEqual(same['status'], 'POSSIBLE_INTRADAY_ACCEPTANCE_UNKNOWN')
        self.assertEqual(same['date_relation_to_deadline'], 'ON_DEADLINE_DATE_INTRADAY_UNRESOLVED')
        self.assertEqual(following['transfer_initiation_date'], '2037-04-09')
        self.assertEqual(following['arrival_date'], '2037-04-10')
        self.assertEqual(following['date_relation_to_deadline'], 'AFTER_DEADLINE_DATE')
        self.assertFalse(any(path['guaranteed_spendable_by_deadline'] for path in result['paths']))

    def test_explicit_same_day_assumption_never_guarantees_deadline_time(self):
        for accepted, status in ((True, 'CONDITIONAL_DATE_PATH'), (False, 'EXCLUDED_BY_EXPLICIT_ASSUMPTION')):
            data = dates(); data['same_day_transfer_assumption'] = {'accepted': accepted, 'basis': 'supplied scenario acceptance ordering'}
            result = settlement_transfer_paths(data)
            self.assertEqual(result['paths'][0]['status'], status)
            self.assertFalse(result['paths'][0]['guaranteed_spendable_by_deadline'])
            self.assertTrue(result['paths'][1]['conditions'])

    def test_insufficient_calendar_not_extended_even_for_very_large_lag(self):
        data = dates(); data['settlement_lag'] = 1000000
        result = settlement_transfer_paths(data)
        self.assertIsNone(result['settlement_date'])
        self.assertFalse(result['calendar_extended'])
        for path in result['paths']:
            self.assertIsNone(path['arrival_date'])
            self.assertEqual(path['status'], 'UNRESOLVED_CALENDAR_COVERAGE')
            self.assertIsNone(path['date_relation_to_deadline'])
        data['settlement_lag'] = 3
        result = settlement_transfer_paths(data)
        self.assertEqual(result['paths'][0]['arrival_date'], '2037-04-18')
        self.assertIsNone(result['paths'][1]['arrival_date'])

    def test_zero_lags_date_boundaries_and_monotonic_lags(self):
        data = dates(); data.update(settlement_lag=0, transfer_lag=0)
        result = settlement_transfer_paths(data)
        self.assertEqual(result['paths'][0]['arrival_date'], data['sale_date'])
        self.assertEqual(result['paths'][0]['date_relation_to_deadline'], 'BEFORE_DEADLINE_DATE')
        arrivals = []
        for lag in range(4):
            data['transfer_lag'] = lag
            arrivals.append(settlement_transfer_paths(data)['paths'][0]['arrival_date'])
        self.assertEqual(arrivals, data['business_dates'][:4])
        data['spendable_deadline'] = '2037-04-01'
        self.assertEqual(settlement_transfer_paths(data)['paths'][0]['date_relation_to_deadline'], 'AFTER_DEADLINE_DATE')

    def test_invalid_order_lags_dates_or_assumptions_rejected(self):
        cases = [{'business_dates': ['2037-04-05', '2037-04-02']},
                 {'business_dates': ['2037-04-02', '2037-04-02']},
                 {'sale_date': '2037-04-03'}, {'settlement_lag': -1}, {'transfer_lag': True},
                 {'sale_date': '2037-04-02T09:00:00Z'}, {'spendable_deadline': '2037-02-30'},
                 {'same_day_transfer_assumption': {'accepted': True}}]
        for update in cases:
            with self.subTest(update=update), self.assertRaises(ValueError):
                settlement_transfer_paths({**dates(), **update})

    def test_common_source_contract_and_no_mutation(self):
        for helper, data in ((alternative_comparison, comparison()), (settlement_transfer_paths, dates())):
            original = deepcopy(data); result = helper(data)
            self.assertEqual(data, original)
            self.assertTrue(result['advisory_only'])
            self.assertFalse(result['source_authenticity_verified'])
            self.assertEqual(result['input_role'], 'hypothetical_scenario')
            for field in ('role', 'currency'):
                bad = deepcopy(data); del bad[field]
                with self.assertRaises(ValueError):
                    helper(bad)


if __name__ == '__main__':
    unittest.main()
