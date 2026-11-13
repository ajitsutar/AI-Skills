from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import scenario_claims as claims
from financial_alignment import _terminal
from planning_alignment import finish


def objective(identifier='capital', measure='net_total_return_fraction', value=0, op='>='):
    unit, basis = claims.MEASURES[measure]
    target = {'value': value, 'unit': unit, 'valuation_basis': basis, 'horizon_years': 1}
    if unit == 'currency_per_share':
        target['currency'] = 'USD'
    if basis == 'present_value':
        target['valued_at'] = '2031-01-01T00:00:00Z'
    return {'id': identifier, 'measure': measure, 'operator': op,
            'role': 'diagnostic_comparator', 'target': target}


def model():
    return {'currency': 'USD', 'role': 'hypothetical_scenario', 'amount_unit': 'USD',
            'as_of': '2031-01-01T00:00:00Z', 'years': 1, 'starting_revenue': 100,
            'starting_shares': 10, 'entry_price': 10, 'entry_cost_bps': 0,
            'exit_cost_bps': 0, 'equity_value_floor_zero': True,
            'reinvestment': {'maintenance_capex_fraction_revenue': 0,
                             'growth_capex_fraction_positive_incremental_revenue': 0,
                             'working_capital_fraction_incremental_revenue': 0,
                             'working_capital_decrease_treatment': 'no_release'},
            'scenarios': [{'id': 'base', 'annual_revenue_growth': 0,
                           'terminal_ebit_margin': '.1', 'annual_dilution': 0,
                           'tax_rate': '.2', 'net_debt_at_exit': 0,
                           'exit_ev_to_ebit': 5, 'cumulative_dividends_per_share': 0}],
            'objective_evidence': {
                'domain': {'mode': 'cartesian', 'base_scenario_id': 'base',
                           'axes': {'terminal_ebit_margin': ['.1', '.2'], 'exit_ev_to_ebit': [5, 10]}},
                'objectives': [objective()],
                'claims': [{'id': 'joint', 'objective_id': 'capital', 'conditions': [
                    {'parameter': 'terminal_ebit_margin', 'operator': '>=', 'value': '.2'},
                    {'parameter': 'exit_ev_to_ebit', 'operator': '>=', 'value': 10}]}]}}


class ScenarioClaimsTests(unittest.TestCase):
    def test_joint_and_each_condition_refuted_by_distinct_counterexamples(self):
        result = claims.analyze(model(), _terminal)
        assessment = result['claims'][0]
        self.assertEqual(assessment['joint_condition']['necessary'], 'REFUTED_BY_COUNTEREXAMPLE')
        self.assertEqual(assessment['joint_condition']['sufficient'], 'HOLDS_ON_EVALUATED_FINITE_DOMAIN')
        self.assertEqual(len(assessment['joint_condition']['necessity_counterexample_row_ids']), 2)
        self.assertTrue(all(x['necessary'] == 'REFUTED_BY_COUNTEREXAMPLE'
                            for x in assessment['individual_conditions']))
        prices = [r['objectives']['capital']['value'] for r in result['rows']]
        # Prices are 5,10,10,20; outlay10 => returns -.5,0,0,1.
        self.assertEqual(sorted(prices), [Decimal('-.5'), Decimal(0), Decimal(0), Decimal(1)])

    def test_same_claim_has_different_evidence_for_different_goal(self):
        doc = model()
        doc['objective_evidence']['objectives'].append(objective('hurdle', value='.5'))
        second = deepcopy(doc['objective_evidence']['claims'][0])
        second.update(id='joint-hurdle', objective_id='hurdle')
        doc['objective_evidence']['claims'].append(second)
        result = claims.analyze(doc, _terminal)
        self.assertEqual(result['claims'][0]['joint_condition']['necessary'], 'REFUTED_BY_COUNTEREXAMPLE')
        self.assertEqual(result['claims'][1]['joint_condition']['necessary'], 'HOLDS_ON_EVALUATED_FINITE_DOMAIN')
        self.assertFalse(result['claims'][1]['joint_condition']['continuous_or_real_world_necessity_established'])

    def test_strict_return_target_does_not_count_equality_as_gain(self):
        doc = model()
        doc['objective_evidence']['objectives'][0]['operator'] = '>'
        result = claims.analyze(doc, _terminal)
        self.assertEqual(len(result['objectives'][0]['passing_row_ids']), 1)

    def test_return_price_and_distribution_pv_are_distinct(self):
        doc = model()
        doc.update(annual_discount_rate='.1', dividend_timing='terminal')
        doc['objective_evidence']['objectives'] += [
            objective('price', 'terminal_share_price', 10),
            objective('pv', 'present_value_of_modeled_distributions', 10)]
        result = claims.analyze(doc, _terminal)
        by_id = {o['id']: o for o in result['objectives']}
        self.assertEqual(len(by_id['capital']['passing_row_ids']), 3)
        self.assertEqual(len(by_id['price']['passing_row_ids']), 3)
        self.assertEqual(len(by_id['pv']['passing_row_ids']), 1)
        equality = next(r for r in result['rows'] if r['objectives']['price']['value'] == 10)
        self.assertTrue(equality['objectives']['capital']['met'])
        self.assertFalse(equality['objectives']['pv']['met'])

    def test_present_value_opinion_cannot_be_silently_used_as_terminal_price(self):
        doc = model()
        obj = objective('price', 'terminal_share_price', 12)
        obj['target']['valuation_basis'] = 'present_value'
        doc['objective_evidence']['objectives'] = [obj]
        with self.assertRaisesRegex(ValueError, 'DIMENSIONS_MISMATCH'):
            claims.analyze(doc, _terminal)

    def test_dcf_closure_unavailable_even_if_after_cost_return_passes(self):
        doc = model()
        doc['objective_evidence']['objectives'].append(
            {'id': 'dcf', 'role': 'declared_objective', 'measure': 'dcf_discount_closure'})
        doc['objective_evidence']['claims'][0]['objective_id'] = 'dcf'
        result = claims.analyze(doc, _terminal)
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['objectives'][1]['status'], 'UNAVAILABLE_DCF_MODEL_NOT_EVALUATED')
        self.assertTrue(all(r['objectives']['dcf']['met'] is None for r in result['rows']))
        self.assertEqual(result['claims'][0]['joint_condition']['necessary'], 'UNDETERMINED')

    def test_supplied_row_association_does_not_cover_joint_parameter_space(self):
        doc = model()
        high = deepcopy(doc['scenarios'][0])
        high.update(id='high', terminal_ebit_margin='.2', exit_ev_to_ebit=10)
        doc['scenarios'].append(high)
        doc['objective_evidence']['domain'] = {'mode': 'supplied_scenarios'}
        result = claims.analyze(doc, _terminal)
        self.assertEqual(result['claims'][0]['joint_condition']['necessary'], 'HOLDS_ON_EVALUATED_FINITE_DOMAIN')
        self.assertEqual(result['scope']['kind'], 'SUPPLIED_ROWS')
        self.assertFalse(result['scope']['joint_parameter_space_exhaustive'])
        self.assertEqual(result['objectives'][0]['discrete_frontiers'], [])

    def test_empty_success_and_condition_sets_do_not_produce_vacuous_proofs(self):
        doc = model()
        doc['objective_evidence']['objectives'][0]['target']['value'] = 100
        doc['objective_evidence']['claims'][0]['conditions'][0]['value'] = '.9'
        result = claims.analyze(doc, _terminal)['claims'][0]['joint_condition']
        self.assertEqual(result['necessary'], 'NO_OBJECTIVE_SUCCESSES')
        self.assertEqual(result['sufficient'], 'NO_CONDITION_WITNESSES')

    def test_missing_distribution_timing_is_unknown_not_failure(self):
        doc = model()
        doc['annual_discount_rate'] = '.1'
        doc['objective_evidence']['objectives'] = [objective('capital', 'present_value_of_modeled_distributions', 10)]
        result = claims.analyze(doc, _terminal)
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['objectives'][0]['failing_row_ids'], [])
        self.assertEqual(len(result['objectives'][0]['unavailable_row_ids']), 4)

    def test_nonmonotone_predicate_frontier_does_not_infer_continuous_threshold(self):
        doc = model()
        doc['objective_evidence']['domain']['axes'] = {'exit_ev_to_ebit': [5, 10, 15]}
        doc['objective_evidence']['objectives'] = [objective('capital', 'terminal_share_price', 10, '==')]
        result = claims.analyze(doc, _terminal)
        frontier = result['objectives'][0]['discrete_frontiers'][0]
        self.assertEqual(len(frontier['adjacent_outcome_changes']), 2)
        self.assertEqual(frontier['minimum_passing_evaluated_value'], 10)
        self.assertEqual(frontier['maximum_passing_evaluated_value'], 10)
        self.assertIsNone(frontier['continuous_threshold'])

    def test_frontiers_hold_other_axis_values_fixed(self):
        result = claims.analyze(model(), _terminal)
        frontier = next(f for f in result['objectives'][0]['discrete_frontiers']
                        if f['axis'] == 'exit_ev_to_ebit' and f['held_axis_values']['terminal_ebit_margin'] == Decimal('.1'))
        self.assertEqual(frontier['minimum_passing_evaluated_value'], 10)
        self.assertEqual(len(frontier['adjacent_outcome_changes']), 1)
        self.assertEqual([v['axis_value'] for v in frontier['evaluated_values']], [5, 10])
        self.assertEqual([v['value'] for v in frontier['evaluated_values']], [Decimal('-.5'), Decimal(0)])
        self.assertFalse(result['scope']['economic_feasibility_established'])

    def test_costs_and_dividends_change_goal_evidence(self):
        doc = model()
        doc.update(entry_cost_bps=100, exit_cost_bps=100)
        doc['scenarios'][0]['cumulative_dividends_per_share'] = '.2'
        result = claims.analyze(doc, _terminal)
        at_ten = next(r for r in result['rows'] if r['parameters']['terminal_ebit_margin'] == Decimal('.1')
                      and r['parameters']['exit_ev_to_ebit'] == 10)
        self.assertEqual(at_ten['objectives']['capital']['value'], 0)
        self.assertTrue(at_ten['objectives']['capital']['met'])

    def test_zero_equity_and_noninvestable_equity_are_not_conflated(self):
        doc = model()
        doc['scenarios'][0]['net_debt_at_exit'] = 1000
        floored = claims.analyze(doc, _terminal)
        self.assertTrue(all(r['objectives']['capital']['value'] == -1 for r in floored['rows']))
        doc['equity_value_floor_zero'] = False
        unavailable = claims.analyze(doc, _terminal)
        self.assertEqual(unavailable['status'], 'PARTIAL')
        self.assertTrue(all(r['objectives']['capital']['met'] is None for r in unavailable['rows']))

    def test_inputs_immutable_even_with_mutating_evaluator(self):
        doc = model()
        before = deepcopy(doc)
        def evaluator(d, s):
            result = _terminal(d, s)
            d.clear()
            s.clear()
            return result
        claims.analyze(doc, evaluator)
        self.assertEqual(doc, before)

    def test_horizon_currency_date_and_goal_role_are_bound(self):
        cases = [('horizon_years', 2, 'HORIZON_MISMATCH'),
                 ('currency', 'EUR', 'CURRENCY_MISMATCH'),
                 ('valued_at', '2030-01-01T00:00:00Z', 'DATE_MISMATCH')]
        for field, value, message in cases:
            doc = model()
            obj = objective('capital', 'present_value_of_modeled_distributions', 10)
            obj['target'][field] = value
            doc['objective_evidence']['objectives'] = [obj]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                claims.analyze(doc, _terminal)
        doc = model()
        del doc['objective_evidence']['objectives'][0]['role']
        with self.assertRaisesRegex(ValueError, 'ROLE_REQUIRED'):
            claims.analyze(doc, _terminal)

    def test_domain_budget_numeric_duplicates_and_nonfinite_values_rejected(self):
        for values, error in [([1, '1.00'], 'DUPLICATE'),
                              ([float('inf')], 'FINITE'), ([True], 'BOOLEAN'),
                              (list(range(4097)), 'LIMIT_EXCEEDED')]:
            doc = model()
            doc['objective_evidence']['domain']['axes'] = {'exit_ev_to_ebit': values}
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                claims.analyze(doc, _terminal)

    def test_claim_cannot_rebind_to_missing_objective(self):
        doc = model()
        doc['objective_evidence']['claims'][0]['objective_id'] = 'invented'
        with self.assertRaisesRegex(ValueError, 'BINDING_REQUIRED'):
            claims.analyze(doc, _terminal)

    def test_axis_order_does_not_change_evaluated_rows(self):
        doc = model()
        first = claims.analyze(doc, _terminal)
        doc['objective_evidence']['domain']['axes'] = {'exit_ev_to_ebit': [10, 5], 'terminal_ebit_margin': ['.2', '.1']}
        second = claims.analyze(doc, _terminal)
        self.assertEqual(first['rows'], second['rows'])

    def test_standard_financial_serializer_retains_objective_evidence(self):
        doc = model()
        result = finish(doc, 'terminal-valuation-and-reinvestment', objective_evidence=claims.analyze(doc, _terminal))
        self.assertEqual(result['objective_evidence']['rows'][0]['objectives']['capital']['value'], '-0.5')


if __name__ == '__main__':
    unittest.main()
