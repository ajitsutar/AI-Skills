"""Deterministic accounting and explicit unsupported arithmetic under hostile hosts."""
import copy
import sys
import unittest
from decimal import (Context, Decimal, Inexact, ROUND_CEILING, ROUND_DOWN,
                     ROUND_FLOOR, ROUND_HALF_EVEN, Rounded, localcontext)
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import holdings_ledger as ledger
import quant_workbench as workbench

T0 = '2026-01-01T00:00:00Z'
T1 = '2026-01-02T00:00:00Z'
T2 = '2026-01-03T00:00:00Z'


def base():
    return dict(currency='USD', as_of=T2, price_basis='unadjusted',
                valuation_policy='observed_only', tax_mode='explicit_event_amounts',
                equal_time_order='supplied_order',
                opening=dict(at=T0, cash='1000000', lots=[], marks=[]), events=[])


def event(event_type, **fields):
    return dict(id=event_type, type=event_type, at=T1, source='synthetic accounting declaration', **fields)


def mark(sid, price):
    return event('mark', security_id=sid, price=price, kind='observed',
                 observed_at=T1, available_at=T1)


def host_contexts():
    for precision, rounding, emin, emax, traps in (
            (6, ROUND_FLOOR, -999999, 999999, False),
            (28, ROUND_HALF_EVEN, -999999, 999999, False),
            (80, ROUND_CEILING, -2, 2, True),
            (2, ROUND_DOWN, -1, 1, True)):
        ctx = Context(prec=precision, rounding=rounding, Emin=emin, Emax=emax,
                      capitals=0, clamp=1)
        for signal in ctx.traps:
            ctx.traps[signal] = traps
        ctx.flags[Inexact] = True
        ctx.flags[Rounded] = True
        yield ctx


def signature(ctx):
    return (ctx.prec, ctx.rounding, ctx.Emin, ctx.Emax, ctx.capitals, ctx.clamp,
            dict(ctx.traps), dict(ctx.flags))


def workbench_document(document):
    return {'schema_version': 1, 'contract': {'prompt': 'Synthetic decimal ledger replay',
        'purpose': 'software regression', 'base_currency': 'USD', 'horizon_id': 'P2D', 'as_of': T2},
        'jobs': [{'id': 'ledger', 'operation': 'backtest.holdings_ledger',
                  'inputs': {'document': document}}]}


class HoldingsDecimalContextTests(unittest.TestCase):
    def invariant_result(self, document, operation=ledger.replay):
        original = copy.deepcopy(document)
        results = []
        for hostile in host_contexts():
            with localcontext(hostile) as ambient:
                before = signature(ambient)
                results.append(operation(document))
                self.assertEqual(signature(ambient), before)
        self.assertEqual(document, original)
        for result in results[1:]:
            self.assertEqual(result, results[0])
        return results[0]

    def invariant_error(self, document, error):
        errors = []
        for hostile in host_contexts():
            with localcontext(hostile) as ambient:
                before = signature(ambient)
                with self.assertRaisesRegex(ValueError, error) as caught:
                    ledger.replay(document)
                errors.append(str(caught.exception))
                self.assertEqual(signature(ambient), before)
        self.assertEqual(len(set(errors)), 1)

    def test_million_plus_cent_retains_source_intent_and_conservation(self):
        document = base()
        document['events'] = [event('deposit', amount='.01')]
        result = self.invariant_result(document)
        self.assertEqual(result['final']['settled_cash'], '1000000.01')
        self.assertEqual(result['cash_and_receivable_conservation_residual'], '0.00')
        self.assertEqual(Fraction(result['final']['settled_cash']), Fraction('1000000')+Fraction('.01'))

    def test_minimum_supplied_increment_is_not_silently_lost(self):
        document = base()
        document['opening']['cash'] = '9'*36
        document['events'] = [event('deposit', amount='1e-36')]
        result = self.invariant_result(document)
        self.assertEqual(Fraction(result['final']['settled_cash']), Fraction('9'*36)+Fraction('1e-36'))

    def test_near_floor_withdrawal_and_purchase_are_not_rounded_into_funding(self):
        for kind in ('withdrawal', 'buy'):
            with self.subTest(kind=kind):
                document = base()
                document['opening']['cash'] = '1000000.01'
                document['cash_floor'] = '1000000'
                if kind == 'withdrawal':
                    document['events'] = [event(kind, amount='.01')]
                    amount_field = 'amount'
                else:
                    document['events'] = [event(kind, security_id='P', lot_id='b', quantity='1',
                        price='.01', cost='0', execution_price_basis='observed', settles_at=T2)]
                    amount_field = 'price'
                result = self.invariant_result(document)
                self.assertEqual(Fraction(result['final']['settled_cash']), Fraction(1000000))
                document['events'][0][amount_field] = '.010000000000000000000000000001'
                self.invariant_error(document, 'INSUFFICIENT_SETTLED_UNRESERVED_CASH')

    def test_partial_basis_cost_tax_payment_and_split_preserve_known_identities(self):
        document = base()
        document['tax_mode'] = 'positive_sale_gains'
        document['opening']['lots'] = [dict(lot_id='p', security_id='P', quantity='3',
                                          basis='10', acquired_at=T0)]
        document['events'] = [event('split', security_id='P', factor='2'),
            event('sell', security_id='P', quantity='1', price='4', cost='.01', lots=['p'],
                  execution_price_basis='observed', settles_at=T1, tax_rate='.2'),
            event('tax_payment', amount='.1')]
        result = self.invariant_result(document)
        allocated = Fraction(result['realizations'][0]['basis'])
        remaining = Fraction(result['lots'][0]['basis'])
        self.assertEqual(allocated+remaining, 10)
        self.assertLess(abs(allocated-Fraction(5, 3)), Fraction(1, 10**59))
        self.assertEqual(Fraction(result['lots'][0]['quantity']), 5)
        gain = Fraction('3.99')-allocated
        self.assertEqual(Fraction(result['realizations'][0]['realized_gain']), gain)
        self.assertEqual(Fraction(result['final']['declared_tax_liability']), gain*Fraction('.2')-Fraction('.1'))
        self.assertEqual(result['final']['settled_cash'], '1000003.89')

    def test_full_disposal_consumes_residual_after_partial_basis_rounding(self):
        document = base()
        document['opening']['lots'] = [dict(lot_id='p', security_id='P', quantity='3',
                                          basis='1', acquired_at=T0)]
        document['events'] = [dict(event('sell', security_id='P', quantity='1', price='1', cost='0',
            lots=['p'], execution_price_basis='observed', settles_at=T1, tax_amount='0'), id='s1'),
            dict(event('sell', security_id='P', quantity='2', price='1', cost='0',
            lots=['p'], execution_price_basis='observed', settles_at=T1, tax_amount='0'), id='s2')]
        result = self.invariant_result(document)
        self.assertEqual(sum(Fraction(row['basis']) for row in result['realizations']), 1)
        self.assertEqual(result['lots'], [])

    def test_spinoff_and_merger_basis_cash_entitlements(self):
        document = base()
        document['opening']['lots'] = [dict(lot_id='p', security_id='P', quantity='1.25',
                                          basis='1000000.01', acquired_at=T0)]
        document['events'] = [event('spinoff', security_id='P', child_security_id='C',
            child_ratio='.2', child_basis_fraction='.125', tax_amount='0'),
            event('merger', security_id='P', child_security_id='M', child_ratio='2.5',
                  cash_per_unit='.04', settles_at=T2, terminal_outcome_confirmed=True,
                  child_basis_by_parent_lot={'p':'875000.00875'}, tax_amount='0'),
            dict(mark('C', '50'), id='mc'), dict(mark('M', '20'), id='mm')]
        result = self.invariant_result(document)
        self.assertEqual(sum(Fraction(row['basis']) for row in result['lots']), Fraction('1000000.01'))
        self.assertEqual(result['final']['settled_cash'], '1000000.0500')
        self.assertEqual(Fraction(result['final']['positions']['C']['quantity']), Fraction('.25'))
        self.assertEqual(Fraction(result['final']['positions']['M']['quantity']), Fraction('3.125'))

    def test_bad_decimal_and_range_fail_consistently_without_touching_host(self):
        for value in ('not-a-number', 'NaN', 'sNaN', 'Infinity', '1e37', '1e-37', '0e999', '9'*37):
            document = base()
            document['opening']['cash'] = value
            self.invariant_error(document, 'INVALID_DECIMAL|INVALID_RANGE|UNSUPPORTED_DECIMAL_INPUT_RANGE')

    def test_excessive_derived_precision_fails_instead_of_losing_quantity(self):
        document = base()
        document['opening']['lots'] = [dict(lot_id='p', security_id='P', quantity='1', basis='1', acquired_at=T0)]
        factor = '1.'+'1'*35
        document['events'] = [dict(event('split', security_id='P', factor=factor), id='split'+str(i))
                              for i in range(5)]
        self.invariant_error(document, 'UNSUPPORTED_DECIMAL_ARITHMETIC:Inexact')

    def test_workbench_replay_and_error_mapping_are_context_invariant(self):
        document = base()
        document['events'] = [event('deposit', amount='.01')]
        bundle = self.invariant_result(workbench_document(document), workbench.freeze)
        self.assertEqual(bundle['result']['results'][0]['result']['final']['settled_cash'], '1000000.01')
        for hostile in host_contexts():
            with localcontext(hostile):
                self.assertEqual(workbench.verify(bundle)['status'], 'REPLAY_MATCH')
        document['opening']['cash'] = '1e37'
        result = self.invariant_result(workbench_document(document), workbench.run)
        self.assertEqual(result['results'][0]['status'], 'REJECTED_INPUT')
        self.assertEqual(result['results'][0]['reason'], 'ValueError:UNSUPPORTED_DECIMAL_INPUT_RANGE:cash')


if __name__ == '__main__':
    unittest.main()
