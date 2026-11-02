import copy
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import planning_alignment as p


def doc(**kwargs):
    return {'currency':'USD','role':'hypothetical_scenario',**kwargs}


class PlanningAlignmentTests(unittest.TestCase):
    def costs(self,**changes):
        return doc(side='buy',price='37.20',quantity='3',entry_orders=1,costs=[
            {'id':'impact','unit':'per_share','phase':'each_side','amount':'0.04'},
            {'id':'ticket','unit':'per_order','phase':'each_side','amount':'0.13'}],**changes)

    def test_two_sided_cost_conservation_and_after_cost_affordability(self):
        request=self.costs(exit_price='35.10',exit_orders=1,budget='112',quantity_step='1')
        result=p.trade_costs(request)
        self.assertEqual(result['entry_cash_debit'],'111.85')
        self.assertEqual(result['exit_net_proceeds'],'105.05')
        self.assertEqual(result['net_pnl'],'-6.80')
        self.assertEqual(result['total_cost'],'0.50')
        self.assertEqual(result['max_affordable_quantity'],'3')
        self.assertEqual(Decimal(result['exit_net_proceeds'])-Decimal(result['entry_cash_debit']),Decimal(result['net_pnl']))
        request['budget']='111.70'
        self.assertEqual(p.trade_costs(request)['max_affordable_quantity'],'2')

    def test_round_trip_fee_is_charged_once_and_order_count_is_explicit(self):
        request=doc(side='buy',price=20,quantity=4,entry_orders=2,exit_price=22,exit_orders=1,
                    costs=[{'id':'round','unit':'per_round_trip','phase':'round_trip','charged_at':'exit','amount':'0.7'},
                           {'id':'order','unit':'per_order','phase':'each_side','amount':'0.2'}])
        result=p.trade_costs(request)
        self.assertEqual(result['entry_cost'],'0.4');self.assertEqual(result['exit_cost'],'0.9')
        self.assertEqual(result['net_pnl'],'6.7')
        del request['costs'][0]['charged_at']
        with self.assertRaisesRegex(ValueError,'CHARGE_TIME'):p.trade_costs(request)

    def test_sale_sizing_net_of_bps_and_fee_and_fractional_increment(self):
        request=doc(side='sell',transaction_phase='exit',price=80,quantity=3,entry_orders=1,required_net_proceeds=240,quantity_step='1',
                    costs=[{'id':'slip','unit':'bps_notional','phase':'exit','amount':12},
                           {'id':'fee','unit':'per_order','phase':'exit','amount':'0.75'}])
        result=p.trade_costs(request)
        self.assertEqual(result['sale_net_proceeds'],'238.962')
        self.assertEqual(result['minimum_quantity_at_increment'],'4')
        self.assertFalse(result['quoted_quantity_meets_proceeds'])
        request['quantity_step']='0.000001';sized=p.trade_costs(request)
        self.assertGreaterEqual(Decimal(sized['sized_net_proceeds']),Decimal(240))
        self.assertLess(Decimal(sized['minimum_quantity_at_increment']),Decimal(4))

    def test_unaffordable_zero_size_has_no_phantom_order_fee(self):
        request=self.costs(budget='0.05',quantity_step='1');request['quantity']=0
        result=p.trade_costs(request)
        self.assertEqual(result['entry_cost'],'0');self.assertEqual(result['affordable_cash_debit'],'0.00')

    def test_cash_ladder_preserves_withdrawal_before_later_credit_and_reports_true_trough(self):
        request=doc(as_of='2026-10-01T00:00:00Z',settled_balances={'USD':150},reservations={'USD':0},floors={'USD':40},events=[
            {'id':'withdraw','kind':'withdrawal','available_at':'2026-10-02T10:00:00Z','currency':'USD','amount':-230,'confirmed':True,'evidence':'declared cash demand'},
            {'id':'sale','kind':'trade_settlement','available_at':'2026-10-02T14:00:00Z','currency':'USD','amount':105,'confirmed':True,'evidence':'declared settlement'}])
        result=p.cash_plan(request)
        self.assertEqual(result['troughs']['USD']['minimum_available'],-80)
        self.assertEqual(result['troughs']['USD']['maximum_floor_gap'],120)
        self.assertEqual(result['helper_result']['ending_available']['USD'],25)
        self.assertIn('10:00:00',result['troughs']['USD']['first_minimum_at'])
        request['events'][1]['available_at']=request['events'][0]['available_at']
        self.assertEqual(p.cash_plan(request)['troughs']['USD']['minimum_available'],-80)

    def test_cash_ladder_rejects_stock_event_as_cash_and_ignores_unconfirmed_credit(self):
        request=doc(as_of='2026-10-01T00:00:00Z',settled_balances={'USD':5},reservations={'USD':0},floors={'USD':0},events=[
            {'id':'stock','kind':'vest_shares','available_at':'2026-10-02T00:00:00Z','currency':'USD','amount':100,'confirmed':True,'evidence':'vesting'}])
        with self.assertRaisesRegex(ValueError,'CASH_EVENT_KIND'):p.cash_plan(request)
        request['events'][0].update(kind='cash_credit',confirmed=False)
        self.assertEqual(p.cash_plan(request)['helper_result']['ending_available']['USD'],5)

    def test_timed_cash_removes_withdrawal_before_future_interest(self):
        request=doc(start_at='2025-01-01T00:00:00Z',end_at='2027-01-01T00:00:00Z',day_count='ACT/365F',
                    annual_effective_rate=.1,opening_cash=1000,floor=0,events=[
                        {'id':'w','at':'2026-01-01T00:00:00Z','kind':'withdrawal','amount':-200,'confirmed':True}])
        result=p.cash_projection(request)
        self.assertAlmostEqual(result['ending_cash'],990)
        self.assertNotAlmostEqual(result['ending_cash'],1010)
        self.assertAlmostEqual(result['conservation_residual'],0)
        request['events'][0]['amount']=-1200
        short=p.cash_projection(request);self.assertIsNone(short['ending_cash']);self.assertEqual(short['status'],'UNFUNDED_SHORTFALL')

    def test_currency_mismatch_is_not_silently_credited_without_fx(self):
        request=doc(start_at='2025-01-01T00:00:00Z',end_at='2027-01-01T00:00:00Z',day_count='ACT/365F',
                    annual_effective_rate=0,opening_cash=0,floor=0,events=[
                        {'id':'foreign','at':'2026-01-01T00:00:00Z','kind':'deposit','amount':100,'confirmed':True,'currency':'EUR'}])
        with self.assertRaisesRegex(ValueError,'CURRENCY_MISMATCH'):p.cash_projection(request)
        request['events'][0].pop('currency')
        self.assertEqual(p.cash_projection(request)['ending_cash'],100)

    def test_vest_tax_shares_reconcile_but_future_values_are_not_cash(self):
        request=doc(as_of='2026-10-13T16:00:00Z',grants=[
            {'id':'a','vest_date':'2026-11-02','status':'future_scheduled','gross_shares':80,'shares_withheld_for_tax':21,'shares_sold_for_tax':3,'assumed_vest_price':40},
            {'id':'b','vest_date':'2027-02-02','status':'future_scheduled','gross_shares':120,'shares_withheld_for_tax':30,'shares_sold_for_tax':6,'assumed_vest_price':35}])
        result=p.vest_reconciliation(request)
        self.assertEqual(result['total_tax_shares'],'60');self.assertEqual(result['totals']['net_shares'],'140')
        self.assertEqual(result['tax_share_fraction'],'0.3');self.assertEqual(result['observed_settled_sale_cash'],'0')
        self.assertIsNone(result['combined_future_concentration']);self.assertIsNone(result['total_spendable_cash'])
        request['grants'][0]['sale']={'confirmed':True}
        with self.assertRaisesRegex(ValueError,'CONFIRMED_VEST'):p.vest_reconciliation(request)

    def test_zero_share_sale_cannot_manufacture_settled_cash(self):
        request=doc(as_of='2026-10-13T16:00:00Z',grants=[{'id':'a','vest_date':'2026-10-01','status':'vested',
                    'gross_shares':10,'shares_withheld_for_tax':0,'shares_sold_for_tax':0,'sale':{
                        'confirmed':True,'sold_net_shares':0,'net_cash_proceeds':100,'executed_at':'2026-10-02T00:00:00Z',
                        'settled_at':'2026-10-03T00:00:00Z','evidence':'fictional receipt'}}])
        with self.assertRaisesRegex(ValueError,'ZERO_SHARE'):p.vest_reconciliation(request)

    def test_original_decimal_position_value_survives_legacy_float_expansion(self):
        request=doc(declared_equity='100000000000000000.3',explicit_cash='.1',positions=[
            {'symbol':'A','asset_type':'equity','quantity':'100000000000000000.2','mark':1,'sector':'x'}],funds={})
        result=p.portfolio_reconciliation(request)
        self.assertEqual(result['identified_position_value'],'100000000000000000.2')
        self.assertEqual(Decimal(result['unexplained_equity_difference']),0)

    def portfolio(self):
        return doc(declared_equity=1200,explicit_cash=200,positions=[
            {'symbol':'A','issuer_id':'ISSUER','asset_type':'equity','quantity':3,'mark':100,'sector':'technology'},
            {'symbol':'F','asset_type':'etf','quantity':5,'mark':100}],funds={
                'F':{'as_of':'2026-10-01T00:00:00Z','evidence':'fixture','holdings':[
                    {'symbol':'A.B','issuer_id':'ISSUER','asset_type':'equity','fraction':.4,'sector':'technology'},
                    {'symbol':'USD','asset_type':'cash','fraction':.1}]}})

    def test_equity_cash_and_fund_unknowns_have_distinct_denominators(self):
        result=p.portfolio_reconciliation(self.portfolio())
        self.assertEqual(Decimal(result['unexplained_equity_difference']),200)
        self.assertEqual(result['unknown_fund_value_within_identified_positions'],250)
        self.assertEqual(result['embedded_fund_cash'],50)
        issuer=result['issuer_exposures']['ISSUER']
        self.assertEqual(issuer['value'],500)
        self.assertAlmostEqual(issuer['fraction_of_declared_equity'],500/1200)
        self.assertEqual(issuer['fraction_of_identified_assets'],.5)
        self.assertEqual(Decimal(result['conservation_residual']),0)

    def test_contribution_only_scenario_changes_exposure_without_sales(self):
        request=self.portfolio();request.update(contribution_allocations={'F':100},unchanged_marks_assumption=True)
        result=p.portfolio_reconciliation(request)
        changed=result['contribution_only_scenario']
        self.assertEqual(Decimal(changed['declared_equity']),1300)
        self.assertEqual(Decimal(changed['unexplained_equity_difference']),200)
        self.assertNotEqual(result['issuer_exposures']['ISSUER']['fraction_of_declared_equity'],changed['issuer_exposures']['ISSUER']['fraction_of_declared_equity'])

    def test_aggregate_cash_discrepancy_is_not_spendable_balance(self):
        result=p.cash_reconciliation(doc(mode='aggregate_bridge',opening_cash=900,observed_cash=940,
            entries=[{'id':'sale','amount':75},{'id':'purchase','amount':-40},{'id':'fee','amount':-2}]))
        self.assertEqual(result['calculated_cash'],'933');self.assertEqual(result['difference'],'-7')
        self.assertIsNone(result['spendable_cash'])

    def test_gross_net_groups_and_costs_are_not_conflated(self):
        request=doc(pnl_basis='gross_before_costs',trades=[{'id':'a','pnl':2,'fees':1,'slippage':2},
                   {'id':'b','pnl':8,'fees':1,'slippage':2},{'id':'c','pnl':-4,'fees':1,'slippage':2}])
        result=p.trade_history_costs(request)
        self.assertEqual(result['gross']['wins'],2);self.assertEqual(result['net']['wins'],1)
        self.assertEqual(result['net']['average_win'],'5');self.assertEqual(result['net']['average_loss'],'-4')
        self.assertEqual(result['net']['total'],'-3')
        request['pnl_basis']='net_after_costs'
        self.assertEqual(p.trade_history_costs(request)['net']['total'],'6')

    def test_lifetime_losses_cannot_be_reported_as_session_pnl_without_prior_marks(self):
        request=doc(session_start='2026-10-13T13:00:00Z',as_of='2026-10-13T16:00:00Z',
                    open_positions=[{'id':'a','quantity':2,'basis_per_share':45,'current_mark':42}],closed_trades=[
                        {'id':'closed','quantity':1,'buy_price':30,'sell_price':28,'fees':'.4'}])
        result=p.session_pnl(request)
        self.assertEqual(result['observed_basis_to_mark_sum'],'-6');self.assertIsNone(result['session_pnl'])
        self.assertIsNone(result['after_declared_session_close'])
        request['open_positions'][0].update(session_start_mark=41,unchanged_quantity_in_session=True,session_fees='.1')
        request['closed_trades'][0].update(opened_at='2026-10-13T14:00:00Z',closed_at='2026-10-13T15:00:00Z')
        request.update(coverage_complete=True,session_distributions=0)
        self.assertEqual(p.session_pnl(request)['session_pnl'],'-0.5')


if __name__=='__main__':unittest.main()
