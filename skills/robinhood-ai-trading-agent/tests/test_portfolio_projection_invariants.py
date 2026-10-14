"""Independent projection invariants; candidate source remains read-only."""
from copy import deepcopy
from decimal import Decimal, Inexact, ROUND_FLOOR, localcontext
from fractions import Fraction
from itertools import permutations
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from portfolio_projection import dated_projection, tax_sensitivity


def src(**kw):
    return dict(currency='USD', source_ref='independent:declared-input', source_role='user_assumption', **kw)


def doc(**kw):
    result = dict(currency='USD', role='user_assumption',
                  opening=src(as_of='2032-01-01', cash='1000', tax_reserve='60',
                              positions=[dict(id='A', quantity='100')]),
                  target_date='2032-01-31', included_states=['confirmed'],
                  mark_policy='target_date_only', flows=[],
                  marks=[src(id='ma', asset_id='A', as_of='2032-01-31', price='10')],
                  other_assets=[], liabilities=[])
    result.update(kw)
    return result


def flow(identifier, kind, **kw):
    row = src(id=identifier, kind=kind, date='2032-01-15', state='confirmed', included_in_opening=False)
    row.update(kw)
    return row


def trade(identifier, side, qty, costs=None):
    return flow(identifier, 'trade', asset_id='A', trade=dict(side=side, quantity=str(qty),
                price='10', entry_orders=2, transaction_phase='exit' if side == 'sell' else 'entry',
                costs=[] if costs is None else costs))


def n(value):
    return Fraction(value)


class IndependentProjectionTests(unittest.TestCase):
    def test_150_exact_rational_sale_buy_cost_conservation_cases(self):
        rng = random.Random(412001)
        for case in range(150):
            side = 'buy' if case % 2 else 'sell'
            qty = rng.randrange(1, 100)
            fee = rng.randrange(0, 200)
            per_share = rng.randrange(0, 100)
            bps = rng.randrange(0, 200)
            phase = 'entry' if side == 'buy' else 'exit'
            costs = [dict(id='order', unit='per_order', phase=phase, amount=str(Decimal(fee)/100)),
                     dict(id='share', unit='per_share', phase='each_side', amount=str(Decimal(per_share)/1000)),
                     dict(id='bps', unit='bps_notional', phase=phase, amount=str(bps)),
                     dict(id='wrongphase', unit='per_order', phase='exit' if side == 'buy' else 'entry', amount='999')]
            expected_cost = 2 * Fraction(fee, 100) + qty * (Fraction(per_share, 1000) + Fraction(10*bps, 10000))
            result = dated_projection(doc(flows=[trade('trade', side, qty, costs)]))
            with self.subTest(case=case):
                self.assertEqual(n(result['total_assets']), 2000 - expected_cost)
                self.assertEqual(n(result['cash']), 1000 + (qty*10 if side == 'sell' else -qty*10) - expected_cost)
                self.assertEqual(n(result['position_values'][0]['quantity']), 100 + (-qty if side == 'sell' else qty))
                self.assertEqual(n(result['net_equity']), n(result['total_assets']))

    def test_payment_settles_liability_without_second_equity_charge(self):
        prior = dated_projection(doc(liabilities=[src(id='debt', as_of='2032-01-31', amount='80')]))
        after = dated_projection(doc(flows=[flow('settle', 'external_obligation', amount='80')],
                         liabilities=[src(id='debt', as_of='2032-01-31', amount='0')]))
        self.assertEqual(n(prior['net_equity']), 1920)
        self.assertEqual(n(after['net_equity']), 1920)
        self.assertEqual(n(after['total_assets']), 1920)
        self.assertEqual(n(after['total_liabilities']), 0)

    def test_reserve_release_and_actual_tax_payment_conservation(self):
        before = dated_projection(doc())
        after = dated_projection(doc(flows=[flow('tax', 'tax_payment', amount='60', reserve_release='60')]))
        self.assertEqual(n(before['cash_after_tax_earmark']), 940)
        self.assertEqual(n(after['cash_after_tax_earmark']), 940)
        self.assertEqual(n(before['total_assets']) - n(after['total_assets']), 60)
        self.assertEqual(n(after['tax_reserve']), 0)

    def test_vest_then_sale_conserves_stock_value_less_cost(self):
        data = doc(flows=[flow('vest', 'vest', asset_id='A', quantity='10'),
                          trade('sell', 'sell', 10, [dict(id='fee', unit='per_order', phase='exit', amount='1')])])
        result = dated_projection(data)
        self.assertEqual(n(result['cash']), 1098)
        self.assertEqual(n(result['total_assets']), 2098)
        self.assertEqual(n(result['position_values'][0]['quantity']), 100)
        vest_only = dated_projection(doc(flows=[flow('vest', 'vest', asset_id='A', quantity='10')]))
        self.assertEqual(n(vest_only['cash']), 1000)
        self.assertEqual(n(vest_only['total_assets']), 2100)

    def test_residual_added_once_not_converted_to_cash(self):
        result = dated_projection(doc(other_assets=[src(id='residual', as_of='2032-01-31', amount='300')],
                                      flows=[trade('sale', 'sell', 30)]))
        self.assertEqual(n(result['cash']), 1300)
        self.assertEqual(n(result['total_position_value']), 700)
        self.assertEqual(n(result['identified_assets']), 2000)
        self.assertEqual(n(result['other_assets_value']), 300)
        self.assertEqual(n(result['total_assets']), 2300)

    def test_all_sameday_permutations_keep_same_balance(self):
        rows = [trade('sell', 'sell', 100), flow('vest', 'vest', asset_id='A', quantity='3'),
                flow('debit', 'cash_debit', amount='19')]
        for perm in permutations(rows):
            result = dated_projection(doc(flows=list(perm)))
            self.assertEqual(n(result['cash']), 1981)
            self.assertEqual(n(result['total_assets']), 2011)
            self.assertEqual(len(result['timeline']), 1)
            self.assertNotIn('minimum_cash', result)

    def test_future_unknown_states_and_target_date_are_audited(self):
        rows = [flow('on_target', 'cash_credit', date='2032-01-31', amount='1'),
                flow('future', 'cash_debit', date='2032-02-01', amount='999'),
                flow('unknown', 'external_obligation', state='unknown', amount='777')]
        result = dated_projection(doc(flows=rows))
        self.assertEqual(n(result['cash']), 1001)
        audit = {r['id']:r for r in result['flow_audit']}
        self.assertTrue(audit['on_target']['included'])
        self.assertEqual(audit['future']['exclusion_reasons'], ['AFTER_TARGET_DATE'])
        self.assertEqual(audit['unknown']['exclusion_reasons'], ['STATE_NOT_INCLUDED'])
        self.assertEqual(len(result['excluded_supplied_flows']), 2)

    def test_opening_date_rejects_even_if_flow_would_be_excluded(self):
        with self.assertRaisesRegex(ValueError, 'FLOW_NOT_AFTER_OPENING'):
            dated_projection(doc(flows=[flow('old', 'cash_credit', state='planned', date='2032-01-01', amount='1')]))

    def test_unknown_price_keeps_quantity_known_and_cash_unknown(self):
        row = trade('sale', 'sell', 30)
        row['trade']['price'] = None
        result = dated_projection(doc(flows=[row]))
        self.assertIsNone(result['cash'])
        self.assertIsNone(result['total_assets'])
        self.assertEqual(n(result['total_position_value']), 700)
        self.assertEqual(result['status'], 'UNRESOLVED')

    def test_unknown_reserve_does_not_destroy_known_asset_total(self):
        data = doc()
        data['opening']['tax_reserve'] = None
        result = dated_projection(data)
        self.assertEqual(n(result['total_assets']), 2000)
        self.assertIsNone(result['cash_after_tax_earmark'])
        self.assertEqual(result['status'], 'UNRESOLVED')

    def test_unknown_ledgers_are_not_empty_ledgers(self):
        for field, affected in [('other_assets', 'total_assets'), ('liabilities', 'net_equity')]:
            data = doc()
            del data[field]
            result = dated_projection(data)
            self.assertIsNone(result[affected])
            self.assertEqual(n(result['identified_assets']), 2000)
            self.assertEqual(result['status'], 'UNRESOLVED')

    def test_carryforward_is_explicit_and_labeled(self):
        data = doc(other_assets=[src(id='residual', as_of='2032-01-01', amount='20')],
                   liabilities=[src(id='loan', as_of='2032-01-01', amount='10')])
        result = dated_projection(data)
        self.assertIsNone(result['total_assets'])
        self.assertIsNone(result['net_equity'])
        data['mark_policy'] = 'carry_forward_supplied'
        result = dated_projection(data)
        self.assertEqual(n(result['net_equity']), 2010)
        for field in ['other_assets_valuations', 'liability_valuations']:
            self.assertEqual(result[field][0]['valuation_basis'], 'explicit_carried_forward_value_no_return_forecast')

    def test_decimal_context_and_source_immutability(self):
        data = doc(flows=[flow('tiny', 'cash_credit', amount='0.123456789123456789')])
        original = deepcopy(data)
        expected = dated_projection(data)
        with localcontext() as ctx:
            ctx.prec = 2
            ctx.rounding = ROUND_FLOOR
            ctx.traps[Inexact] = True
            self.assertEqual(dated_projection(data), expected)
        self.assertEqual(data, original)
        self.assertEqual(n(expected['cash']), Fraction('1000.123456789123456789'))


class IndependentTaxTests(unittest.TestCase):
    def calc(self, **kw):
        row = src(id='s', as_of='2032-01-31', gross_proceeds='1000', selling_costs='31',
                  cost_basis='700', tax_rate='.3', selling_costs_reduce_gain='yes')
        row.update(kw)
        return tax_sensitivity(dict(currency='USD', role='user_assumption', scenarios=[row]))['scenarios'][0]

    def test_yes_no_unknown_gain_cost_treatment(self):
        yes = self.calc()
        no = self.calc(selling_costs_reduce_gain='no')
        unknown = self.calc(selling_costs_reduce_gain='unknown')
        self.assertEqual(n(yes['positive_tax_estimate']), Fraction('80.7'))
        self.assertEqual(n(no['positive_tax_estimate']), 90)
        self.assertEqual(n(yes['net_sale_proceeds_after_tax_earmark']), Fraction('888.3'))
        self.assertEqual(n(no['net_sale_proceeds_after_tax_earmark']), 879)
        self.assertIsNone(unknown['positive_tax_estimate'])
        self.assertIsNone(unknown['net_sale_proceeds_after_tax_earmark'])
        self.assertEqual(n(unknown['net_sale_proceeds']), 969)

    def test_loss_no_credit_and_no_payment_inference(self):
        row = self.calc(cost_basis='1200')
        self.assertEqual(n(row['modeled_taxable_gain']), -231)
        self.assertEqual(n(row['positive_tax_estimate']), 0)
        self.assertEqual(n(row['net_sale_proceeds_after_tax_earmark']), 969)
        self.assertFalse(row['cash_loss_credit_inferred'])
        self.assertFalse(row['tax_payment_inferred'])

    def test_missing_inputs_preserve_unknown_even_if_zero_rate(self):
        for key in ['gross_proceeds', 'selling_costs', 'cost_basis', 'tax_rate']:
            row = self.calc(**{key: None})
            self.assertEqual(row['status'], 'UNRESOLVED')
            self.assertIn(key, row['missing_inputs'])
            self.assertIsNone(row['positive_tax_estimate'])
        self.assertIsNone(self.calc(tax_rate='0', selling_costs_reduce_gain='unknown')['positive_tax_estimate'])

    def test_independent_tax_scenarios_do_not_net_gains_and_losses(self):
        gain = self.calc()
        loss = self.calc(cost_basis='1200')
        self.assertEqual(n(gain['positive_tax_estimate']) + n(loss['positive_tax_estimate']), Fraction('80.7'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
