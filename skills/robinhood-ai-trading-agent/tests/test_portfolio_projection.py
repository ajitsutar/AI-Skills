"""Boundary accounting and missing-data invariants for source-explicit scenarios."""
from copy import deepcopy
from decimal import Decimal, Inexact, ROUND_UP, localcontext
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import portfolio_projection as projection


def source(**values):
    return {'currency': 'USD', 'source_ref': 'supplied:ledger',
            'source_role': 'hypothetical_scenario', **values}


def flow(identifier, kind, **values):
    return source(id=identifier, kind=kind, state='confirmed', date='2031-04-02',
                  included_in_opening=False, **values)


def document(**values):
    return {'currency': 'USD', 'role': 'hypothetical_scenario',
            'opening': source(as_of='2031-04-01', cash='100', tax_reserve='0',
                              positions=[{'id': 'asset-a', 'quantity': '10'}]),
            'target_date': '2031-04-30', 'included_states': ['confirmed'],
            'mark_policy': 'target_date_only', 'flows': [], 'other_assets': [], 'liabilities': [],
            'marks': [source(id='mark-a', asset_id='asset-a', as_of='2031-04-30', price='20')],
            **values}


def tax_document(**values):
    return {'currency': 'USD', 'role': 'hypothetical_scenario', 'scenarios': [source(
        id='sale-a', as_of='2031-04-02', gross_proceeds='100', selling_costs='4',
        cost_basis='60', tax_rate='.25', selling_costs_reduce_gain='yes', **values)]}


class ProjectionTests(unittest.TestCase):
    def test_reserve_remains_asset_payment_reduces_asset(self):
        data = document(flows=[flow('earmark', 'reserve_change', amount='15')])
        held = projection.dated_projection(data)
        self.assertEqual(Decimal(held['cash_after_tax_earmark']), 85)
        self.assertEqual(Decimal(held['total_assets']), 300)
        data['flows'].append({**flow('pay', 'tax_payment', amount='15', reserve_release='15'), 'date': '2031-04-03'})
        paid = projection.dated_projection(data)
        self.assertEqual(Decimal(paid['cash']), 85)
        self.assertEqual(Decimal(paid['tax_reserve']), 0)
        self.assertEqual(Decimal(paid['cash_after_tax_earmark']), 85)
        self.assertEqual(Decimal(paid['total_assets']), 285)

    def test_sale_transfers_assets_and_costs_deducted_once(self):
        data = document(flows=[flow('sale', 'trade', asset_id='asset-a', trade={
            'side': 'sell', 'price': '20', 'quantity': '3', 'entry_orders': 1,
            'transaction_phase': 'exit', 'costs': [
                {'id': 'fee', 'unit': 'per_order', 'phase': 'exit', 'amount': '2'},
                {'id': 'variable', 'unit': 'per_share', 'phase': 'exit', 'amount': '.1'}]})])
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['cash']), Decimal('157.7'))
        self.assertEqual(Decimal(result['total_position_value']), 140)
        self.assertEqual(Decimal(result['total_assets']), Decimal('297.7'))

    def test_buy_debits_price_plus_cost_and_adds_units(self):
        data = document(flows=[flow('buy', 'trade', asset_id='asset-a', trade={
            'side': 'buy', 'price': '20', 'quantity': '2', 'entry_orders': 1,
            'costs': [{'id': 'fee', 'unit': 'per_order', 'phase': 'entry', 'amount': '3'}]})])
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['cash']), 57)
        self.assertEqual(Decimal(result['total_assets']), 297)

    def test_vest_is_units_and_intervening_obligation_is_retained(self):
        data = document(flows=[{**flow('vest', 'vest', asset_id='asset-a', quantity='2'), 'state': 'planned'},
                               flow('rent', 'external_obligation', amount='30')])
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['cash']), 70)
        self.assertEqual(result['excluded_supplied_flows'][0]['id'], 'vest')
        data['included_states'].append('planned')
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['cash']), 70)
        self.assertEqual(Decimal(result['total_assets']), 310)
        self.assertTrue(result['supplied_flows_all_included'])

    def test_all_exclusions_audited_including_obligations(self):
        data = document(flows=[{**flow('later', 'external_obligation', amount='22'), 'date': '2031-05-01'},
                               {**flow('conditional', 'external_obligation', amount='9'), 'state': 'scenario'}])
        result = projection.dated_projection(data)
        excluded = {r['id']: r['exclusion_reasons'] for r in result['excluded_supplied_flows']}
        self.assertEqual(excluded, {'later': ['AFTER_TARGET_DATE'], 'conditional': ['STATE_NOT_INCLUDED']})
        self.assertFalse(result['supplied_flows_all_included'])

    def test_missing_future_mark_does_not_invent_future_value(self):
        data = document(marks=[])
        result = projection.dated_projection(data)
        self.assertIsNone(result['total_assets'])
        self.assertEqual(result['cash'], '100')
        self.assertEqual(result['status'], 'UNRESOLVED')

    def test_old_mark_requires_explicit_carry_forward(self):
        data = document()
        data['marks'][0]['as_of'] = '2031-04-01'
        result = projection.dated_projection(data)
        self.assertIsNone(result['total_assets'])
        self.assertIn('MARK_DATE_MISMATCH', result['position_values'][0]['unresolved'])
        data['mark_policy'] = 'carry_forward_supplied'
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['total_assets']), 300)
        self.assertEqual(result['position_values'][0]['valuation_basis'], 'explicit_carried_forward_mark_no_return_forecast')
        self.assertFalse(result['future_returns_inferred'])

    def test_mixed_timestamp_date_and_old_flow_invalid(self):
        for day, message in [('2031-04-02T00:00:00Z', 'NO_MIXED_TIMESTAMPS'),
                             ('2031-04-01', 'FLOW_NOT_AFTER_OPENING')]:
            data = document(flows=[{**flow('payment', 'cash_debit', amount='1'), 'date': day}])
            with self.assertRaisesRegex(ValueError, message):
                projection.dated_projection(data)

    def test_target_date_boundary_included_later_excluded(self):
        data = document(flows=[{**flow('boundary', 'cash_credit', amount='7'), 'date': '2031-04-30'},
                               {**flow('later', 'cash_credit', amount='11'), 'date': '2031-05-01'}])
        self.assertEqual(Decimal(projection.dated_projection(data)['cash']), 107)

    def test_unknown_cash_quantity_and_reserve_propagate_separately(self):
        data = document(flows=[flow('demand', 'external_obligation', amount=None)])
        result = projection.dated_projection(data)
        self.assertIsNone(result['cash'])
        self.assertIsNone(result['total_assets'])
        self.assertEqual(Decimal(result['total_position_value']), 200)
        data = document(flows=[flow('payment', 'tax_payment', amount='5')])
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['total_assets']), 295)
        self.assertIsNone(result['tax_reserve'])
        self.assertIsNone(result['cash_after_tax_earmark'])
        data = document(flows=[flow('vest', 'vest', asset_id='asset-a', quantity=None)])
        self.assertIsNone(projection.dated_projection(data)['total_assets'])

    def test_unknown_trade_costs_do_not_mean_zero(self):
        data = document(flows=[flow('sale', 'trade', asset_id='asset-a', trade={
            'side': 'sell', 'price': '20', 'quantity': '3', 'entry_orders': 1,
            'transaction_phase': 'exit', 'costs': None})])
        result = projection.dated_projection(data)
        self.assertIsNone(result['cash'])
        self.assertEqual(Decimal(result['position_values'][0]['quantity']), 7)

    def test_zero_quantity_does_not_require_mark(self):
        data = document(marks=[])
        data['opening']['positions'][0]['quantity'] = '0'
        self.assertEqual(Decimal(projection.dated_projection(data)['total_assets']), 100)

    def test_invalid_currency_duplicate_and_state_selection(self):
        data = document()
        data['marks'][0]['currency'] = 'EUR'
        with self.assertRaisesRegex(ValueError, 'NO_FX'):
            projection.dated_projection(data)
        data = document(flows=[flow('x', 'cash_credit', amount='1'), flow('x', 'cash_credit', amount='2')])
        with self.assertRaisesRegex(ValueError, 'UNIQUE_IDS'):
            projection.dated_projection(data)
        data = document(included_states=['unknown'])
        with self.assertRaisesRegex(ValueError, 'INCLUDED_STATES'):
            projection.dated_projection(data)

    def test_reserve_overrelease_and_oversell_rejected(self):
        data = document(flows=[flow('release', 'reserve_change', amount='-1')])
        with self.assertRaisesRegex(ValueError, 'RELEASE_EXCEEDS_RESERVE'):
            projection.dated_projection(data)
        data = document(flows=[flow('sale', 'trade', asset_id='asset-a', trade={
            'side': 'sell', 'price': '20', 'quantity': '11', 'entry_orders': 1,
            'transaction_phase': 'exit', 'costs': []})])
        with self.assertRaisesRegex(ValueError, 'SALE_EXCEEDS_LONG_QUANTITY'):
            projection.dated_projection(data)

    def test_same_day_is_end_balance_without_intraday_claim(self):
        data = document(flows=[flow('payment', 'cash_debit', amount='150'), flow('credit', 'cash_credit', amount='80')])
        result = projection.dated_projection(data)
        self.assertEqual(len(result['timeline']), 1)
        self.assertEqual(Decimal(result['cash']), 30)
        self.assertNotIn('funding_feasible', result)

    def test_negative_cash_is_unfunded_arithmetic_not_permission(self):
        result = projection.dated_projection(document(flows=[flow('bill', 'external_obligation', amount='125')]))
        self.assertEqual(Decimal(result['cash']), -25)
        self.assertEqual(Decimal(result['total_assets']), 175)
        self.assertTrue(result['advisory_only'])

    def test_caller_context_and_input_unchanged(self):
        data = document(flows=[flow('bill', 'cash_debit', amount='0.123456789123456789')])
        before = deepcopy(data)
        expected = projection.dated_projection(data)
        with localcontext() as ctx:
            ctx.prec = 3
            ctx.rounding = ROUND_UP
            ctx.traps[Inexact] = True
            actual = projection.dated_projection(data)
        self.assertEqual(actual, expected)
        self.assertEqual(data, before)

    def test_residual_retained_and_post_flow_denominator_recomputed(self):
        data = document(other_assets=[source(id='unclassified', as_of='2031-04-30', amount='40')],
                        liabilities=[source(id='loan', as_of='2031-04-30', amount='13')],
                        flows=[flow('withdrawal', 'cash_debit', amount='7'),
                               flow('obligation', 'external_obligation', amount='23'),
                               flow('sale', 'trade', asset_id='asset-a', trade={
                                   'side': 'sell', 'price': '20', 'quantity': '2', 'entry_orders': 1,
                                   'transaction_phase': 'exit', 'costs': [
                                       {'id': 'fee', 'unit': 'per_order', 'phase': 'exit', 'amount': '1.7'}]})])
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['identified_assets']), Decimal('268.3'))
        self.assertEqual(Decimal(result['other_assets_value']), 40)
        self.assertEqual(Decimal(result['total_assets']), Decimal('308.3'))
        self.assertEqual(Decimal(result['net_equity']), Decimal('295.3'))
        self.assertEqual(Decimal(result['position_values'][0]['quantity']), 8)

    def test_absent_residual_or_liabilities_does_not_imply_empty(self):
        data = document()
        del data['other_assets']
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['identified_assets']), 300)
        self.assertIsNone(result['total_assets'])
        data = document()
        del data['liabilities']
        result = projection.dated_projection(data)
        self.assertEqual(Decimal(result['total_assets']), 300)
        self.assertIsNone(result['net_equity'])


class TaxTests(unittest.TestCase):
    def test_explicit_tax_treatments_and_cost_not_double_charged(self):
        data = tax_document()
        yes = projection.tax_sensitivity(data)['scenarios'][0]
        self.assertEqual(Decimal(yes['modeled_taxable_gain']), 36)
        self.assertEqual(Decimal(yes['positive_tax_estimate']), 9)
        self.assertEqual(Decimal(yes['net_sale_proceeds_after_tax_earmark']), 87)
        data['scenarios'][0]['selling_costs_reduce_gain'] = 'no'
        no = projection.tax_sensitivity(data)['scenarios'][0]
        self.assertEqual(Decimal(no['positive_tax_estimate']), 10)
        self.assertEqual(Decimal(no['net_sale_proceeds_after_tax_earmark']), 86)
        self.assertFalse(no['tax_payment_inferred'])

    def test_no_automatic_loss_credit(self):
        data = tax_document()
        data['scenarios'][0]['cost_basis'] = '120'
        row = projection.tax_sensitivity(data)['scenarios'][0]
        self.assertEqual(Decimal(row['modeled_taxable_gain']), -24)
        self.assertEqual(Decimal(row['positive_tax_estimate']), 0)
        self.assertEqual(Decimal(row['net_sale_proceeds_after_tax_earmark']), 96)
        self.assertFalse(row['cash_loss_credit_inferred'])

    def test_missing_basis_rate_treatment_or_cost_never_assumed(self):
        for key in ['cost_basis', 'tax_rate', 'selling_costs_reduce_gain', 'selling_costs', 'gross_proceeds']:
            data = tax_document()
            del data['scenarios'][0][key]
            row = projection.tax_sensitivity(data)['scenarios'][0]
            self.assertIsNone(row['positive_tax_estimate'], key)
            self.assertIn(key, row['missing_inputs'])
            self.assertIsNone(row['net_sale_proceeds_after_tax_earmark'])

    def test_zero_rate_is_explicit_and_unknown_treatment_still_unknown(self):
        data = tax_document()
        data['scenarios'][0]['tax_rate'] = '0'
        self.assertEqual(Decimal(projection.tax_sensitivity(data)['scenarios'][0]['positive_tax_estimate']), 0)
        data['scenarios'][0]['selling_costs_reduce_gain'] = 'unknown'
        self.assertIsNone(projection.tax_sensitivity(data)['scenarios'][0]['positive_tax_estimate'])


if __name__ == '__main__':
    unittest.main()
