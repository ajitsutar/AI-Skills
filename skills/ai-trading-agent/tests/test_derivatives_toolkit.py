"""Hand arithmetic, economic identities and domain checks for offline research."""
import copy
from decimal import localcontext, Overflow, Inexact
import json
import math
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import derivatives_toolkit as d


def option(**changes):
    return dict(spot=100,strike=100,time_years=1,risk_free_rate=0.05,dividend_yield=0,
                volatility=0.2,steps=200,right='put',exercise='american',
                dividend_model='continuous_yield',rate_compounding='continuous',**{}) | changes


def envelope(operation,inputs,currency='USD'):
    return dict(schema_version=1,action='research',operation=operation,currency=currency,information_cutoff='2026-10-23T23:00:00Z',inputs_available_at='2026-10-23T22:00:00Z',inputs=inputs)


def iv(**changes):
    spec=option(exercise='european',right='call',risk_free_rate=0,steps=100)
    spec.pop('volatility')
    return dict(option=spec,market_price=7.945678871638437,volatility_lower=0.05,
                volatility_upper=0.6,price_tolerance=1e-8,max_iterations=80) | changes


def bond(**changes):
    return dict(par=1000,settlement_date='2025-01-01',cashflows=[{'date':'2026-01-01','amount':50},
        {'date':'2027-01-01','amount':1050}],cashflows_complete=True,noncallable_fixed=True,
        yield_rate=.05,compounding_per_year=1,discount_day_count='ACT365F',
        accrual={'method':'supplied_amount','amount':0}) | changes


def futures(**changes):
    return dict(signed_contracts=2,multiplier=1000,price_unit='USD/barrel',entry_at='2026-10-20T16:00:00Z',
        entry_price=10,settlements=[{'at':'2026-10-20T21:00:00Z','price':-5},{'at':'2026-10-21T21:00:00Z','price':-10}],
        fees=12,settlement_method='variation_margin',rounding='unrounded_research',currency_decimals=2,
        terminal_state='open') | changes


class DerivativesTests(unittest.TestCase):
    def test_one_step_crr_hand_computed(self):
        # u=2,d=1/2,p=1/3. Call upper payoff100 =>100/3, put lower50 =>100/3.
        for right in ('put','call'):
            got=d.option_crr(option(volatility=math.log(2),risk_free_rate=0,steps=1,right=right))
            self.assertAlmostEqual(got['value_per_underlying_unit'],100/3)
            self.assertAlmostEqual(got['risk_neutral_up_probability'],1/3)

    def test_european_put_call_parity_with_yield_and_negative_rate(self):
        spec=option(risk_free_rate=-.02,dividend_yield=.03,exercise='european')
        call=d.option_crr(spec|{'right':'call'})['value_per_underlying_unit']
        put=d.option_crr(spec)['value_per_underlying_unit']
        self.assertAlmostEqual(call-put,100*math.exp(-.03)-100*math.exp(.02),places=9)

    def test_american_put_premium_and_intrinsic_bound(self):
        american=d.option_crr(option(spot=80))['value_per_underlying_unit']
        euro=d.option_crr(option(spot=80,exercise='european'))['value_per_underlying_unit']
        self.assertGreaterEqual(american,20)
        self.assertGreater(american,euro)

    def test_nondividend_american_call_equals_european(self):
        self.assertAlmostEqual(d.option_crr(option(right='call'))['value_per_underlying_unit'],
            d.option_crr(option(right='call',exercise='european'))['value_per_underlying_unit'])

    def test_expiry_zero_and_in_the_money(self):
        for right,expected in [('call',0),('put',20)]:
            result=d.option_crr(option(spot=80,time_years=0,right=right))
            self.assertEqual(result['value_per_underlying_unit'],expected)
            self.assertEqual(result['branch'],'expiry_intrinsic')

    def test_zero_volatility_and_early_exercise(self):
        spec=option(spot=80,volatility=0)
        self.assertEqual(d.option_crr(spec)['value_per_underlying_unit'],20)
        self.assertAlmostEqual(d.option_crr(spec|{'exercise':'european'})['value_per_underlying_unit'],
            100*math.exp(-.05)-80)

    def test_invalid_risk_neutral_probability(self):
        with self.assertRaisesRegex(ValueError,'CRR_ARBITRAGE_GRID'):
            d.option_crr(option(volatility=.001,steps=1))

    def test_discrete_dividends_and_unknown_keys_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_DIVIDEND_MODEL'):
            d.option_crr(option(dividend_model='discrete_cash'))
        with self.assertRaisesRegex(ValueError,'UNKNOWN_FIELDS'):
            d.option_crr(option(dividends=[3]))

    def test_crr_convergence_against_independent_closed_form(self):
        # ATM S=K=100,r=q=0,T=1,sigma=.2; BSM=100*(2 Phi(.1)-1).
        expected=100*math.erf(.1/math.sqrt(2))
        coarse=d.option_crr(option(steps=50,right='call',exercise='european',risk_free_rate=0))['value_per_underlying_unit']
        fine=d.option_crr(option(steps=400,right='call',exercise='european',risk_free_rate=0))['value_per_underlying_unit']
        self.assertLess(abs(fine-expected),.006)
        self.assertLess(abs(fine-expected),abs(coarse-expected))

    def test_iv_recovers_supplied_tree_price(self):
        spec=iv()
        # This checks inversion, not independent pricing accuracy; one-step/parity tests do that.
        spec['market_price']=d.option_crr(spec['option']|{'volatility':.3})['value_per_underlying_unit']
        result=d.implied_volatility(spec)
        self.assertEqual(result['status'],'CONVERGED')
        self.assertAlmostEqual(result['implied_volatility'],.3,places=7)
        self.assertLess(abs(result['price_residual']),1e-8)

    def test_american_iv_inverts_early_exercise_model(self):
        spec=iv();spec['option']=option(spot=90,steps=100)
        spec['option'].pop('volatility')
        spec['market_price']=d.option_crr(spec['option']|{'volatility':.35})['value_per_underlying_unit']
        result=d.implied_volatility(spec)
        self.assertEqual(result['status'],'CONVERGED')
        self.assertAlmostEqual(result['implied_volatility'],.35,places=7)

    def test_iv_economic_and_bracket_bounds(self):
        self.assertEqual(d.implied_volatility(iv(market_price=101))['status'],'PRICE_OUTSIDE_ECONOMIC_BOUNDS')
        self.assertEqual(d.implied_volatility(iv(market_price=90))['status'],'PRICE_OUTSIDE_VOLATILITY_BRACKET')

    def test_iv_expiry_not_invented(self):
        spec=iv();spec['option']['time_years']=0;spec['market_price']=0
        self.assertEqual(d.implied_volatility(spec)['status'],'NOT_IDENTIFIABLE_AT_EXPIRY')
        spec['market_price']=1
        self.assertEqual(d.implied_volatility(spec)['status'],'PRICE_INCONSISTENT_AT_EXPIRY')

    def test_iv_flat_boundary_not_unique(self):
        spec=iv();spec['option']=option(spot=1)|{'steps':100};spec['option'].pop('volatility')
        spec['market_price']=99
        self.assertEqual(d.implied_volatility(spec)['status'],'BOUNDARY_OR_FLAT_PRICE_NOT_IDENTIFIED')

    def test_iv_nonconvergence_preserves_no_estimate(self):
        result=d.implied_volatility(iv(max_iterations=1))
        self.assertEqual(result['status'],'MAX_ITERATIONS')
        self.assertIsNone(result['implied_volatility'])

    def test_fx_simple_hand_calculation_and_quote_reversal(self):
        spec=dict(spot_domestic_per_foreign=1.2,domestic_currency='USD',foreign_currency='EUR',
                  domestic_rate=.05,foreign_rate=.02,time_years=1,compounding='simple')
        f=d.fx_forward(spec)['forward_domestic_per_foreign']
        self.assertAlmostEqual(f,1.2352941176470589)
        inverse=d.fx_forward(spec|dict(spot_domestic_per_foreign=1/1.2,domestic_currency='EUR',foreign_currency='USD',domestic_rate=.02,foreign_rate=.05))
        self.assertAlmostEqual(inverse['forward_domestic_per_foreign'],1/f)
        self.assertFalse(inverse['spot_forecast'])

    def test_fx_zero_time_and_negative_rate(self):
        spec=dict(spot_domestic_per_foreign=1.2,domestic_currency='USD',foreign_currency='EUR',
                  domestic_rate=-.01,foreign_rate=.02,time_years=0,compounding='continuous')
        self.assertEqual(d.fx_forward(spec)['forward_domestic_per_foreign'],1.2)
        self.assertAlmostEqual(d.fx_forward(spec|{'time_years':1})['forward_domestic_per_foreign'],1.2*math.exp(-.03))
        with self.assertRaises(ValueError):
            d.fx_forward(spec|{'compounding':'simple','domestic_rate':-2,'time_years':1})

    def test_bond_par_and_clean_dirty_identity(self):
        result=d.bond_cashflows(bond())
        self.assertAlmostEqual(result['dirty_value'],1000)
        result=d.bond_cashflows(bond(accrual={'method':'supplied_amount','amount':20}))
        self.assertAlmostEqual(result['clean_value'],980)
        self.assertAlmostEqual(result['clean_value']+result['accrued_interest'],result['dirty_value'])
        self.assertAlmostEqual(result['clean_price_per_100_par'],98)

    def test_bond_actual_accrual_settlement_exclusive(self):
        spec=bond(settlement_date='2025-04-01',accrual={'method':'ACT360','annual_coupon_rate':.06,
            'last_coupon_date':'2025-01-01','next_coupon_date':'2026-01-01'})
        self.assertEqual(d.bond_cashflows(spec)['accrued_interest'],15)
        spec['accrual']['method']='ACT365F'
        self.assertAlmostEqual(d.bond_cashflows(spec)['accrued_interest'],1000*.06*90/365)

    def test_bond_rejects_past_and_duplicate_flows_unknown_schedules(self):
        for spec in [bond(cashflows=[{'date':'2025-01-01','amount':1000}]),
            bond(cashflows_complete=False),bond(noncallable_fixed=False),bond(discount_day_count='ACT_ACT')]:
            with self.assertRaises(ValueError):d.bond_cashflows(spec)

    def test_bond_negative_yield_valid_but_base_must_be_positive(self):
        self.assertGreater(d.bond_cashflows(bond(yield_rate=-.01))['dirty_value'],1100)
        with self.assertRaises(ValueError):d.bond_cashflows(bond(yield_rate=-1))

    def test_futures_negative_price_and_cash_conservation(self):
        result=d.futures_pnl(futures())
        self.assertEqual([x['variation_cash'] for x in result['ledger']],[-30000,-10000])
        self.assertEqual(result['gross_pnl'],-40000)
        self.assertEqual(result['net_pnl'],-40012)
        self.assertEqual(sum(x['variation_cash'] for x in result['ledger']),result['gross_pnl'])
        self.assertEqual(d.futures_pnl(futures(signed_contracts=-2))['gross_pnl'],40000)

    def test_futures_per_contract_rounding_is_not_round_delta(self):
        # Values .005 -> .015 round .01 -> .02; 3 contracts collect .03.
        spec=futures(signed_contracts=3,multiplier=1,entry_price=.005,settlements=[{'at':'2026-10-20T21:00:00Z','price':.015}],rounding='per_contract_half_up')
        self.assertEqual(d.futures_pnl(spec)['gross_pnl'],.03)

    def test_futures_rounding_negative_half_away_from_zero(self):
        spec=futures(signed_contracts=1,multiplier=1,entry_price=-.005,settlements=[{'at':'2026-10-20T21:00:00Z','price':.005}],rounding='per_contract_half_up')
        self.assertEqual(d.futures_pnl(spec)['gross_pnl'],.02)

    def test_futures_physical_delivery_not_invented(self):
        self.assertFalse(d.futures_pnl(futures(terminal_state='physical_delivery_pending'))['physical_delivery_completed'])
        with self.assertRaises(ValueError): d.futures_pnl(futures(signed_contracts=1.5))
        with self.assertRaises(ValueError): d.futures_pnl(futures(settlements=[{'at':'2026-10-19T21:00:00Z','price':10}]))

    def test_schema_finite_units_action_and_unknown_keys(self):
        doc=envelope('option_crr',option())
        original=copy.deepcopy(doc)
        self.assertEqual(d.run(doc),d.run(doc));self.assertEqual(doc,original)
        for change in [{'action':'trade'},{'schema_version':True},{'currency':'usd'},{'unexpected':1}]:
            with self.assertRaises(ValueError):d.run(doc|change)
        for bad in [True,None,float('nan'),float('inf'),-1]:
            with self.assertRaises(ValueError): d.run(envelope('option_crr',option(spot=bad)))
        with self.assertRaisesRegex(ValueError,'PRICE_CURRENCY_MUST_MATCH'):
            d.run(envelope('futures_pnl',futures(),'EUR'))

    def test_derivative_cutoff_and_packet_availability(self):
        doc=envelope('option_crr',option())
        for field in ('information_cutoff','inputs_available_at'):
            for invalid in ('2026-10-23','2026-10-23T23:00:00','2026-10-23T23:00:00+00:99'):
                with self.assertRaisesRegex(ValueError,'EXACT_AWARE_TIMESTAMP'):
                    d.run(doc|{field:invalid})
        with self.assertRaisesRegex(ValueError,'INPUTS_AFTER_INFORMATION_CUTOFF'):
            d.run(doc|{'inputs_available_at':'2026-10-24T00:00:00Z'})

    def test_futures_observed_settlement_times_cannot_be_projected(self):
        doc=envelope('futures_pnl',futures())
        doc['inputs']['settlements'][-1]['at']='2099-10-21T21:00:00Z'
        with self.assertRaisesRegex(ValueError,'FUTURES_OBSERVATION_AFTER_INPUT_AVAILABILITY'):
            d.run(doc)
        doc=envelope('futures_pnl',futures())
        doc['inputs_available_at']='2026-10-21T20:59:59Z'
        with self.assertRaisesRegex(ValueError,'FUTURES_OBSERVATION_AFTER_INPUT_AVAILABILITY'):
            d.run(doc)
        doc['inputs_available_at']='2026-10-21T14:00:00-07:00'
        self.assertEqual(d.run(doc)['gross_pnl'],-40000)

    def test_projected_bond_cashflows_remain_allowed(self):
        doc=envelope('bond_cashflows',bond())
        doc['information_cutoff']='2025-01-01T00:00:00Z'
        doc['inputs_available_at']='2025-01-01T00:00:00Z'
        self.assertAlmostEqual(d.run(doc)['dirty_value'],1000)

    def test_futures_decimal_context_is_fully_isolated(self):
        expected=d.run(envelope('futures_pnl',futures()))
        with localcontext() as ctx:
            ctx.Emax=2;ctx.Emin=-2;ctx.prec=3;ctx.traps[Overflow]=False;ctx.traps[Inexact]=True
            self.assertEqual(d.run(envelope('futures_pnl',futures())),expected)

    def test_executable_examples(self):
        paths=list((Path(__file__).resolve().parents[1]/'examples').glob('derivatives-*.json'))
        self.assertEqual(len(paths),5)
        for path in paths:
            with self.subTest(path=path.name):
                result=d.run(json.loads(path.read_text(encoding='utf-8')))
                self.assertIn(result['status'],('COMPUTED','CONVERGED'))

    def test_numeric_extremes_fail_without_infinite_or_zero_forward(self):
        spec=dict(spot_domestic_per_foreign=1,domestic_currency='USD',foreign_currency='EUR',
                  domestic_rate=-1000,foreign_rate=0,time_years=1,compounding='continuous')
        with self.assertRaisesRegex(ValueError,'NUMERIC_DOMAIN'):
            d.run(envelope('fx_forward',spec))
        with self.assertRaisesRegex(ValueError,'NUMERIC_DOMAIN'):
            d.run(envelope('futures_pnl',futures(multiplier=1e300,rounding='per_contract_half_up')))

    def test_cli_preserves_input_and_existing_output_and_rejects_duplicate_keys(self):
        script=Path(d.__file__)
        with tempfile.TemporaryDirectory() as folder:
            src=Path(folder)/'input.json';out=Path(folder)/'output.json'
            src.write_text(json.dumps(envelope('option_crr',option())),encoding='utf-8')
            original=src.read_bytes()
            command=[sys.executable,str(script),'--input',str(src),'--output',str(out)]
            first=subprocess.run(command,capture_output=True)
            self.assertEqual(first.returncode,0,first.stderr.decode())
            saved=out.read_bytes()
            second=subprocess.run(command,capture_output=True)
            self.assertNotEqual(second.returncode,0)
            self.assertEqual(out.read_bytes(),saved)
            self.assertEqual(src.read_bytes(),original)
            same=subprocess.run(command[:-1]+[str(src)],capture_output=True)
            self.assertNotEqual(same.returncode,0)
            self.assertEqual(src.read_bytes(),original)
            src.write_text('{"action":"research","action":"trade"}',encoding='utf-8')
            duplicate=subprocess.run(command,capture_output=True)
            self.assertIn(b'DUPLICATE_JSON_KEY',duplicate.stderr)


if __name__=='__main__':unittest.main()
