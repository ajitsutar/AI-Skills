"""Independent rational invariants and regression coverage for portfolio decisions."""
from copy import deepcopy
from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
from fractions import Fraction as F
from pathlib import Path
import random
import sys
import unittest

D = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D / 'scripts'))
import portfolio_decision as pd


def budget_doc(budget='100', price='10'):
    return {'currency': 'USD', 'role': 'hypothetical_scenario', 'mode': 'alternatives',
            'budget': budget,
            'rows': [{'id': 'x', 'price': price, 'price_basis': 'last', 'costs': []}],
            'quantity_scenarios': [{'id': 'whole', 'quantity_basis': 'whole_shares', 'quantity_step': '1'}]}


def allocation_doc():
    return {'currency': 'USD', 'role': 'supplied_observation',
            'denominator': {'amount': '100', 'basis': 'account equity'},
            'rows': [{'id': 'x', 'notional': '50', 'notional_basis': 'gross_notional',
                      'instrument_type': 'equity', 'issuer_id': 'issuer', 'sector': 'sector', 'industry': 'industry'}]}


class IndependentInvariantTests(unittest.TestCase):
    def test_randomized_affordability_and_maximality_exact_rational(self):
        rng = random.Random(4120)
        for case in range(240):
            d = budget_doc(str(Decimal(rng.randrange(0, 50000)) / 100),
                           str(Decimal(rng.randrange(1, 20000)) / 100))
            step = rng.choice(['1', '0.1', '0.03', '0.0025', '3'])
            d['quantity_scenarios'][0].update(quantity_basis='fractional_shares', quantity_step=step)
            orders = rng.randrange(1, 5)
            d['rows'][0]['entry_orders'] = orders
            costs = [{'id': 'share', 'amount': str(Decimal(rng.randrange(0, 100)) / 100), 'unit': 'per_share', 'phase': 'each_side'},
                     {'id': 'ticket', 'amount': str(Decimal(rng.randrange(0, 400)) / 100), 'unit': 'per_order', 'phase': 'entry'},
                     {'id': 'bp', 'amount': str(rng.randrange(0, 200)), 'unit': 'bps_notional', 'phase': 'entry'},
                     {'id': 'round', 'amount': str(Decimal(rng.randrange(0, 100)) / 100), 'unit': 'per_round_trip', 'phase': 'round_trip', 'charged_at': rng.choice(['entry', 'exit'])},
                     {'id': 'exit', 'amount': '9999', 'unit': 'per_order', 'phase': 'exit'}]
            d['rows'][0]['costs'] = costs
            r = pd.budget_sizing(d)['scenarios'][0]['rows'][0]
            qty = F(r['quantity']); price = F(d['rows'][0]['price'])
            fixed = F(costs[1]['amount']) * orders + (F(costs[3]['amount']) if costs[3]['charged_at'] == 'entry' else 0)
            def actual_debit(q):
                return q * price + (fixed + q * F(costs[0]['amount']) + q * price * F(costs[2]['amount']) / 10000 if q else 0)
            with self.subTest(case=case):
                self.assertEqual((qty / F(step)).denominator, 1)
                self.assertEqual(F(r['modeled_cash_debit']), actual_debit(qty))
                self.assertLessEqual(actual_debit(qty), F(d['budget']))
                self.assertGreater(actual_debit(qty + F(step)), F(d['budget']))
                self.assertEqual(F(r['budget_remainder']), F(d['budget']) - actual_debit(qty))

    def test_portfolio_rounding_residual_and_unassigned_cash_are_conserved(self):
        d = budget_doc('321.17', '31.07'); d['mode'] = 'portfolio'
        d['rows'][0]['budget'] = '100'
        d['rows'].append({'id': 'b', 'budget': '157.21', 'price': '13.75', 'costs': [
            {'id': 'fee', 'amount': '.004', 'unit': 'per_share', 'phase': 'entry'}]})
        r = pd.budget_sizing(d)['scenarios'][0]
        t = r['portfolio_totals']
        self.assertEqual(F(t['budget_remainder']), F(t['unassigned_cash_budget']) + sum(F(x['budget_remainder']) for x in r['rows']))
        self.assertEqual(F(t['gross_notional']) + F(t['modeled_entry_cost']) + F(t['budget_remainder']), F(d['budget']))

    def test_input_is_immutable_and_cost_order_does_not_change_arithmetic(self):
        d = budget_doc('72.50', '7.03')
        d['rows'][0]['costs'] = [{'id': str(i), 'amount': str(i), 'unit': 'bps_notional', 'phase': 'entry'} for i in range(9)]
        original = deepcopy(d)
        a = pd.budget_sizing(d)['scenarios'][0]['rows'][0]
        self.assertEqual(d, original)
        d['rows'][0]['costs'].reverse()
        b = pd.budget_sizing(d)['scenarios'][0]['rows'][0]
        for key in ['quantity', 'gross_notional', 'modeled_cash_debit', 'budget_remainder']:
            self.assertEqual(F(a[key]), F(b[key]))

    def test_external_inexact_and_rounded_traps_do_not_leak(self):
        d = budget_doc('100', '3')
        a = pd.budget_sizing(d)
        with localcontext() as ctx:
            ctx.prec = 2; ctx.rounding = ROUND_UP
            ctx.traps[Inexact] = True; ctx.traps[Rounded] = True
            b = pd.budget_sizing(d)
            c = allocation_doc(); c['denominator']['amount'] = '3'
            pd.allocation_context(c)
        self.assertEqual(a, b)

    def test_random_recursive_fund_conservation_with_exact_oracle(self):
        rng = random.Random(64120)
        for case in range(60):
            expected = {'i0': F(0), 'i1': F(0), 'i2': F(0)}
            cash = F(0); unknown = F(0)
            def node(depth, path, value):
                nonlocal cash, unknown
                if depth == 0:
                    kind = rng.choice(['equity', 'equity', 'cash', 'unknown'])
                    if kind == 'cash': cash += value
                    elif kind == 'unknown': unknown += value
                    else:
                        issuer = rng.choice(list(expected)); expected[issuer] += value
                        return {'id': path, 'instrument_type': kind, 'issuer_id': issuer, 'sector': 's', 'industry': 'n'}
                    return {'id': path, 'instrument_type': kind}
                weights = [rng.randrange(0, 31) for _ in range(3)]
                unknown += value * (1 - sum(F(w,100) for w in weights))
                cs = []
                for n,w in enumerate(weights):
                    c = node(depth-1, path+str(n), value*F(w,100)); c['weight'] = str(Decimal(w)/100); cs.append(c)
                return {'id': path, 'instrument_type': 'fund', 'lookthrough': {'constituents': cs}}
            d = allocation_doc(); row = node(3, 'fund', F(50))
            row.update(notional='50', notional_basis='gross_notional'); d['rows'] = [row]
            r = pd.allocation_context(d); e = r['exposures']['issuer_id']
            with self.subTest(case=case):
                self.assertEqual(F(e['unknown_notional']), unknown)
                self.assertEqual(F(e['non_applicable_cash_notional']), cash)
                for issuer, val in expected.items():
                    self.assertEqual(F(e['groups'].get(issuer, {'notional':'0'})['notional']), val)
                self.assertEqual(F(e['conservation_residual']), 0)
                self.assertEqual(F(r['fund_lookthrough']['conservation_residual']), 0)

    def test_empty_model_is_distinct_from_missing_or_null_model(self):
        d = budget_doc(); self.assertEqual(pd.budget_sizing(d)['status'], 'COMPUTED')
        d['rows'][0].pop('costs'); self.assertEqual(pd.budget_sizing(d)['status'], 'INPUTS_UNRESOLVED')
        d['rows'][0]['costs'] = None; self.assertEqual(pd.budget_sizing(d)['status'], 'INPUTS_UNRESOLVED')

    def test_budget_and_allocation_currency_mismatches_stay_unresolved(self):
        d = budget_doc(); d['rows'][0]['currency'] = 'EUR'
        self.assertIsNone(pd.budget_sizing(d)['scenarios'][0]['rows'][0]['quantity'])
        a = allocation_doc(); a['denominator']['currency'] = 'EUR'
        self.assertIsNone(pd.allocation_context(a)['exposures']['issuer_id']['groups']['issuer']['fraction_of_denominator'])


class ContractGapRegressionTests(unittest.TestCase):
    def test_literal_unknown_denominator_basis_keeps_fraction_null(self):
        d = allocation_doc(); d['denominator']['basis'] = 'unknown'
        r = pd.allocation_context(d)
        self.assertIsNone(r['exposures']['issuer_id']['groups']['issuer']['fraction_of_denominator'])

    def test_unknown_fund_weight_marks_overall_context_partial(self):
        d = allocation_doc(); d['rows'][0].update(instrument_type='fund', lookthrough={'constituents': [
            {'id': 'known', 'weight': '1', 'instrument_type': 'equity', 'issuer_id': 'issuer', 'sector': 'sector', 'industry': 'industry'},
            {'id': 'unknown', 'weight': None, 'instrument_type': 'equity', 'issuer_id': 'other'}]})
        r = pd.allocation_context(d)
        self.assertEqual(r['fund_lookthrough']['coverage_status'], 'INPUTS_UNRESOLVED')
        self.assertEqual(r['status'], 'PARTIAL_CONTEXT')

    def test_entry_slippage_cannot_be_declared_included_in_exit_only_fee(self):
        d = budget_doc()
        d['rows'][0]['costs'] = [{'id': 'exit-fee', 'amount': '1000', 'unit': 'bps_notional', 'phase': 'exit'}]
        d['rows'][0]['modeled_slippage'] = {'id': 'entry-slip', 'amount': '1000', 'unit': 'bps_notional', 'phase': 'entry',
            'convention': 'one_way', 'reference_price_basis': 'last', 'overlap': 'included_in_costs', 'overlapping_cost_ids': ['exit-fee']}
        try:
            r = pd.budget_sizing(d)['scenarios'][0]['rows'][0]
        except ValueError:
            return
        self.assertEqual(r['status'], 'INPUTS_UNRESOLVED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
