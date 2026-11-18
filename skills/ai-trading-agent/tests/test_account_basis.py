"""Generic account-basis reporting invariants; no live account or private case."""
import copy
from decimal import Decimal as D
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from portfolio_manager import rebalance, account_basis_summary
import report_facts


def request():
    return dict(equity='1200', cash='1200', holdings={},
                targets={'ALDER': '.20', 'BIRCH': '.15'},
                prices={'ALDER': '40', 'BIRCH': '90'}, cash_floor='.08',
                band='.02', max_turnover='.60', min_trade='1')


class AccountBasisTests(unittest.TestCase):
    def test_cash_only_account_is_not_doubled(self):
        inputs = request(); before = copy.deepcopy(inputs)
        result = rebalance(**inputs); r = result['account_basis']
        self.assertEqual(inputs, before)
        self.assertEqual(D(r['total_account_equity']), 1200)
        self.assertEqual(D(r['supplied_cash_fraction_of_equity']), 1)
        self.assertEqual(D(r['cash_floor_amount']), 96)
        self.assertEqual({k:D(v) for k,v in r['target_notionals'].items()}, {'ALDER':D(240),'BIRCH':D(180)})
        self.assertEqual(D(r['equity_outside_supplied_targets']), 780)
        self.assertEqual(D(r['cash_remaining_after_reservations']), 780)
        self.assertEqual(D(r['initial_planning_budget']), 720)
        self.assertEqual(D(r['unused_planning_budget']), 300)
        self.assertEqual(r['residual_status'], 'EXACTLY_RECONCILED')

    def test_mixed_account_retains_unrepresented_equity(self):
        inputs = request(); inputs.update(cash='300', holdings={'ALDER':'10'})
        r = rebalance(**inputs)['account_basis']
        self.assertEqual(D(r['priced_supplied_holdings']), 400)
        self.assertEqual(D(r['unrepresented_equity_residual']), 500)
        self.assertEqual(r['residual_status'], 'UNREPRESENTED_EQUITY')
        self.assertEqual(D(r['cash_floor_amount']), 96)
        self.assertEqual(D(r['initial_planning_budget']), 204)
        self.assertNotEqual(r['equity_outside_supplied_targets'],r['cash_remaining_after_reservations'])
        self.assertIn('not necessarily cash',account_basis_summary(r))

    def test_existing_small_negative_reconciliation_tolerance_is_visible(self):
        inputs=request(); inputs.update(cash='1200.005')
        r=rebalance(**inputs)['account_basis']
        self.assertEqual(D(r['unrepresented_equity_residual']), D('-.005'))
        self.assertEqual(r['residual_status'],'SUPPLIED_COMPONENTS_EXCEED_EQUITY_WITHIN_EXISTING_TOLERANCE')
        inputs['cash']='1200.02'
        with self.assertRaisesRegex(ValueError,'exceed account equity'):
            rebalance(**inputs)

    def test_nonzero_fees_distinguish_notionals_reservations_and_cash(self):
        inputs=request(); inputs.update(fee_per_order='.37',fee_per_share='.02')
        result=rebalance(**inputs);r=result['account_basis']
        debit=sum(D(x['maximum_cash_debit']) for x in result['buy_candidates'])
        notional=sum(D(x['notional_before_fees']) for x in result['buy_candidates'])
        self.assertGreater(debit,notional)
        self.assertEqual(D(r['proposed_debit_reservations']),debit)
        self.assertEqual(D(r['proposed_notional_before_fees']),notional)
        self.assertEqual(D(r['cash_remaining_after_reservations']),D(1200)-debit)
        self.assertEqual(D(r['cash_remaining_before_fees']),D(1200)-notional)
        self.assertEqual(D(r['total_supplied_target_notional']),420)

    def test_whole_shares_and_turnover_cap_do_not_relabel_policy_targets(self):
        inputs=request();inputs.update(prices={'ALDER':'175','BIRCH':'410'},allow_fractional=False,max_turnover='.25')
        result=rebalance(**inputs);r=result['account_basis']
        self.assertEqual(D(r['total_supplied_target_notional']),420)
        self.assertEqual(D(r['turnover_cap_amount']),300)
        self.assertEqual(D(r['proposed_debit_reservations']),175)
        self.assertEqual(D(r['cash_remaining_after_reservations']),1025)
        self.assertEqual(D(r['unused_planning_budget']),125)
        self.assertEqual([(x['symbol'],x['quantity']) for x in result['buy_candidates']],[('ALDER','1')])

    def test_floor_binds_cash_and_unfilled_sales_are_not_funding(self):
        inputs=request();inputs.update(cash='60',holdings={'ALDER':'20'},allow_sales=True)
        result=rebalance(**inputs);r=result['account_basis']
        self.assertEqual(D(r['cash_available_above_floor']),0)
        self.assertEqual(D(r['initial_planning_budget']),0)
        self.assertEqual(D(r['cash_remaining_after_reservations']),60)
        self.assertEqual(result['buy_candidates'],[])
        self.assertTrue(result['sell_reviews'])

    def test_equity_scale_preserves_fractions_and_scales_denominators(self):
        a=rebalance(**request())['account_basis'];inputs=request()
        inputs.update(equity='3600',cash='3600')
        b=rebalance(**inputs)['account_basis']
        for k in ['total_account_equity','cash_floor_amount','drift_band_amount','turnover_cap_amount','initial_planning_budget','total_supplied_target_notional','equity_outside_supplied_targets']:
            self.assertEqual(D(b[k]),3*D(a[k]),k)
        for k in ['cash_floor_fraction','drift_band_fraction','turnover_cap_fraction','target_weights','currency_status']:
            self.assertEqual(a[k],b[k],k)

    def test_summary_and_field_semantics_preserve_actual_basis_and_unknown_currency(self):
        result=rebalance(**request());r=result['account_basis'];text=result['account_basis_summary']
        self.assertEqual(text,account_basis_summary(r))
        self.assertIsNone(r['currency']);self.assertEqual(r['currency_status'],'UNSPECIFIED')
        self.assertIn('Currency unspecified; amounts are account currency units',text)
        self.assertIn('Total account equity 1200 already includes supplied cash 1200',text)
        self.assertIn('Cash floor 0.08 of equity = 96.00',text)
        self.assertIn('cash after reservations 780.00',text)
        self.assertNotIn('USD',text)
        spec=report_facts.extended_spec('portfolio_manager.rebalance','account_basis/cash_floor_amount')
        self.assertEqual(spec[1],'account_currency_amount')
        self.assertIn('total account equity',spec[2])
        self.assertIn('unspecified',spec[3])
        target=report_facts.extended_spec('portfolio_manager.rebalance','account_basis/target_notionals/ALDER')
        self.assertIn('total account equity',target[2])
        self.assertEqual(target[1],spec[1])
        json.dumps(result,allow_nan=False)

    def test_summary_renders_supplied_record_values_not_fixed_examples(self):
        record=rebalance(**request())['account_basis']
        changed=copy.deepcopy(record);changed['cash_floor_amount']='193.17'
        self.assertIn('= 193.17;',account_basis_summary(changed))
        self.assertNotIn('= 96.00;',account_basis_summary(changed))

    def test_standalone_cli_uses_same_additive_record_without_new_route(self):
        # A child interpreter exercises JSON serialization without a temp fixture.
        code="import json,sys;sys.path.insert(0,'scripts');from portfolio_manager import rebalance;print(json.dumps(rebalance(**json.loads(sys.argv[1]))))"
        child=subprocess.run([sys.executable,'-B','-c',code,json.dumps(request())],cwd=ROOT,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(child.stdout),rebalance(**request()))


if __name__=='__main__':unittest.main()
