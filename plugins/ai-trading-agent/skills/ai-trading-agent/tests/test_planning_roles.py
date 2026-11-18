"""Role, missing-data and normalized comparison invariants, with varied values."""
from copy import deepcopy
from decimal import Decimal, ROUND_UP, localcontext
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import planning_roles as roles
import planning_alignment


def document(**values):
    return {'currency': 'USD', 'role': 'hypothetical_scenario', **values}


def record(identifier, **values):
    return {'id': identifier, 'source_role': 'supplied_observation', 'semantic_role': 'observation', **values}


def constraint_document(role='maximum', value='12.75', candidate='8.20'):
    dimensions = {'metric': 'planned_loss', 'unit': 'USD', 'scope': 'proposed-position', 'basis': 'after-cost'}
    return document(records=[record('limit', semantic_role=role, value=value, **dimensions)],
                    checks=[{'id': 'check', 'constraint_id': 'limit', 'candidate': {'value': candidate, **dimensions}}])


class InputRolesTests(unittest.TestCase):
    def test_absent_null_and_empty_are_distinct(self):
        result = roles.input_roles(document(records=[record('absent'), record('null', value=None), record('empty', value=[])]))
        self.assertEqual([r['value_presence'] for r in result['records']], ['absent', 'explicit_null', 'supplied'])
        self.assertEqual([r['is_observed_state'] for r in result['records']], [False, False, True])
        self.assertFalse(result['actual_portfolio_inferred'])

    def test_synthetic_empty_ledger_stays_hypothetical(self):
        result = roles.input_roles(document(records=[record('holdings', value=[], source_role='hypothetical_scenario')]))
        self.assertFalse(result['records'][0]['is_observed_state'])
        self.assertIsNone(result['selected_allocation'])

    def test_unknown_source_is_not_observed(self):
        source = record('cash', value='91')
        del source['source_role']
        self.assertFalse(roles.input_roles(document(records=[source]))['records'][0]['is_observed_state'])

    def test_pending_value_never_derives_reservation_or_quantity(self):
        data = document(records=[record('pending', value='137', semantic_role='pending')])
        result = roles.input_roles(data)
        self.assertEqual(result['records'][0]['pending_state'], 'unknown')
        self.assertEqual(result['records'][0]['pending_accounting_effect'], 'unresolved')
        self.assertIsNone(result['selected_quantity'])
        for state in ('reserved', 'open_position', 'proposed', 'cancelled'):
            data['records'][0]['pending_state'] = state
            row = roles.input_roles(data)['records'][0]
            self.assertEqual(row['pending_state'], state)
            self.assertIn('no_automatic_cash_adjustment', row['pending_accounting_effect'])

    def test_maximum_accepts_less_and_boundary_not_equality_target(self):
        for value, expected in [('8.20', True), ('12.75', True), ('12.75000001', False)]:
            row = roles.input_roles(constraint_document(candidate=value))['checks'][0]
            self.assertEqual(row['relation'], 'le')
            self.assertEqual(row['satisfies_declared_relation'], expected)
        self.assertFalse(roles.input_roles(constraint_document('target'))['checks'][0]['satisfies_declared_relation'])

    def test_minimum_and_exact_target(self):
        self.assertTrue(roles.input_roles(constraint_document('minimum', candidate='14'))['checks'][0]['satisfies_declared_relation'])
        self.assertTrue(roles.input_roles(constraint_document('target', candidate='12.750'))['checks'][0]['satisfies_declared_relation'])

    def test_mismatched_dimensions_and_missing_do_not_compare(self):
        for dimension in roles.DIMENSIONS:
            data = constraint_document()
            data['checks'][0]['candidate'][dimension] = 'different'
            row = roles.input_roles(data)['checks'][0]
            self.assertEqual(row['status'], 'INCOMPARABLE')
            self.assertIsNone(row['satisfies_declared_relation'])
            del data['checks'][0]['candidate'][dimension]
            row = roles.input_roles(data)['checks'][0]
            self.assertEqual(row['status'], 'UNRESOLVED')
        data = constraint_document(candidate=None)
        self.assertTrue(roles.input_roles(data)['checks'][0]['missing_value'])

    def test_exposure_is_not_an_alternative_loss_target(self):
        data = constraint_document()
        data['records'].append(record('exposure', semantic_role='pending', value='225'))
        result = roles.input_roles(data)
        self.assertTrue(result['checks'][0]['satisfies_declared_relation'])
        self.assertIsNone(result['selected_quantity'])
        data['checks'][0]['constraint_id'] = 'exposure'
        with self.assertRaisesRegex(ValueError, 'BOUND_OR_TARGET_REQUIRED'):
            roles.input_roles(data)

    def test_after_cost_loss_candidate_uses_existing_calculation(self):
        # Independent rational arithmetic: 3*(47-45) + 2*0.17 + 6*0.03 = 6.52.
        trade = planning_alignment.trade_costs(document(side='buy', price='47', exit_price='45', quantity='3',
                    entry_orders=1, exit_orders=1, costs=[
                        {'id': 'ticket', 'unit': 'per_order', 'phase': 'each_side', 'amount': '.17'},
                        {'id': 'slippage', 'unit': 'per_share', 'phase': 'each_side', 'amount': '.03'}]))
        expected = 3 * (Fraction(47) - 45) + 2 * Fraction(17, 100) + 6 * Fraction(3, 100)
        loss = -Decimal(trade['net_pnl'])
        self.assertEqual(Fraction(loss), expected)
        self.assertTrue(roles.input_roles(constraint_document(value='7', candidate=str(loss)))['checks'][0]['satisfies_declared_relation'])

    def test_validation_and_no_mutation(self):
        data = constraint_document()
        before = deepcopy(data)
        roles.input_roles(data)
        self.assertEqual(data, before)
        for bad in (True, 'NaN', 'Infinity'):
            data['checks'][0]['candidate']['value'] = bad
            with self.assertRaises(ValueError):
                roles.input_roles(data)
        with self.assertRaises(ValueError):
            roles.input_roles(document(records=[record('same'), record('same')]))


class ReferenceComparisonTests(unittest.TestCase):
    def test_labels_imply_no_model_allocations_or_shocks(self):
        data = document(sleeves=[{'id': name} for name in ('core', 'swing', 'intraday', 'cash')])
        result = roles.reference_comparison(data)
        self.assertEqual([row['id'] for row in result['sleeves']], ['core', 'swing', 'intraday', 'cash'])
        for row in result['sleeves']:
            self.assertEqual(row['exposure_model'], 'unknown')
            self.assertIsNone(row['observed_allocation'])
            self.assertEqual(row['reference_scenarios'], [])
            self.assertFalse(row['observed_holdings_available'])

    def test_explicit_models_are_not_inferred_from_labels(self):
        data = document(sleeves=[{'id': 'cash', 'exposure_model': 'long_linear_price'},
                                 {'id': 'core', 'exposure_model': 'not_applicable'}],
                        shocks=[{'id': 'source-downside', 'return_fraction': '-.173'}])
        result = roles.reference_comparison(data)['sleeves']
        self.assertEqual(result[0]['reference_scenarios'][0]['price_pnl_per_currency_unit'], '-0.173')
        self.assertEqual(result[1]['reference_scenarios'], [])
        self.assertEqual(result[1]['scenario_status'], 'NOT_APPLICABLE')

    def test_no_shocks_leaves_only_unit_relation(self):
        row = roles.reference_comparison(document(sleeves=[{'id': 'a', 'exposure_model': 'long_linear_price'}]))['sleeves'][0]
        self.assertEqual(row['reference_notional'], '1')
        self.assertEqual(row['scenario_status'], 'NO_SHOCKS_SUPPLIED')
        self.assertIsNone(row['performance_estimate'])

    def test_user_records_retained_without_promoting_scenario(self):
        data = document(sleeves=[{'id': 'a', 'allocation_record': record('amount', value='321', source_role='user_assumption'),
                                 'holdings_record': record('positions', value=[], source_role='hypothetical_scenario'),
                                 'return_observations_record': record('returns', value=[])}],
                        assumptions={'fees': 'not modeled', 'horizon': 'user supplied'})
        before = deepcopy(data)
        result = roles.reference_comparison(data)
        self.assertEqual(result['retained_input'], before)
        self.assertEqual(data, before)
        row = result['sleeves'][0]
        self.assertIsNone(row['observed_allocation'])
        self.assertFalse(row['observed_holdings_available'])
        self.assertFalse(row['supplied_return_observations_present'])

    def test_source_empty_holdings_are_available_but_no_implicit_cash(self):
        row = roles.reference_comparison(document(sleeves=[{'id': 'a', 'holdings_record': record('positions', value=[])}]))['sleeves'][0]
        self.assertTrue(row['observed_holdings_available'])
        self.assertIsNone(row['observed_allocation'])

    def test_precision_and_validation(self):
        data = document(sleeves=[{'id': 'a', 'exposure_model': 'long_linear_price'}],
                        shocks=[{'id': 'exact', 'return_fraction': '.12345678901234567890123456789'}])
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.rounding = ROUND_UP
            row = roles.reference_comparison(data)['sleeves'][0]['reference_scenarios'][0]
        self.assertEqual(Decimal(row['price_pnl_per_currency_unit']), Decimal(data['shocks'][0]['return_fraction']))
        for invalid in ('-1.0001', 'NaN', True):
            data['shocks'][0]['return_fraction'] = invalid
            with self.assertRaises(ValueError):
                roles.reference_comparison(data)


if __name__ == '__main__':
    unittest.main()
