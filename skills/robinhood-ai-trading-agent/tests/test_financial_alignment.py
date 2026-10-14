from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import financial_alignment as f


def doc(**kwargs):return {'currency':'USD','role':'hypothetical_scenario',**kwargs}


class FinancialAlignmentTests(unittest.TestCase):
    def bridge(self):
        return doc(period_start='2025-01-01',period_end='2025-12-31',amount_unit='USD millions',reported_cfo=19,
                   total_capex=7,maintenance_capex=4,growth_capex=3,sbc_added_back_in_cfo=2.5,
                   acquisition_cash_paid=3,working_capital_cfo_effect=-2,reported_net_income=11,
                   earnings_adjustments=[{'id':'integration','after_tax_amount':'.6','basis':'explicit_assumption','rationale':'assumed nonrecurring expense'}],
                   cash_adjustments=[{'id':'integration','amount':'.6'}])

    def test_earnings_addback_does_not_automatically_enter_cash_bridge(self):
        result=f.owner_cash_bridge(self.bridge())
        self.assertEqual(result['reported_fcf'],'12');self.assertEqual(result['after_total_capex_and_acquisitions'],'9')
        self.assertEqual(result['maintenance_only_cash'],'15');self.assertEqual(result['sbc_deducted_economic_proxy'],'9.5')
        self.assertEqual(result['normalized_earnings_scenario'],'11.6')
        self.assertEqual(result['cash_after_supported_adjustments'],'12')
        self.assertIsNone(result['fcf_after_declared_cash_adjustments'])
        self.assertFalse(result['declared_cash_adjustments_fully_supported'])
        self.assertEqual(result['bridge_conservation_residual'],'0')

    def test_cash_addback_requires_cfo_effect_period_tax_and_evidence(self):
        request=self.bridge();request['cash_adjustments'][0].update(reported_cfo_effect='-.6',paid_on='2025-05-01',
            cash_tax_treatment='net cash expense including observed tax cash offset',evidence='supplied source paragraph')
        self.assertEqual(f.owner_cash_bridge(request)['fcf_after_declared_cash_adjustments'],'12.6')
        request['cash_adjustments'][0]['paid_on']='2026-01-01'
        self.assertIsNone(f.owner_cash_bridge(request)['fcf_after_declared_cash_adjustments'])
        request['cash_adjustments'][0]['paid_on']='2025-05-01';request['cash_adjustments'][0]['evidence']=[]
        self.assertIsNone(f.owner_cash_bridge(request)['fcf_after_declared_cash_adjustments'])

    def test_partial_capex_and_sbc_are_unknown_not_zero(self):
        request=self.bridge();del request['sbc_added_back_in_cfo'];del request['acquisition_cash_paid']
        request['growth_capex']=4
        result=f.owner_cash_bridge(request)
        self.assertEqual(result['capex_split_residual'],'-1')
        self.assertIsNone(result['sbc_deducted_economic_proxy']);self.assertIsNone(result['after_total_capex_and_acquisitions'])
        self.assertIn('sbc_added_back_in_cfo',result['missing_bridge_fields'])

    def test_duplicate_adjustment_identity_cannot_double_earnings_or_cash(self):
        for field in ('earnings_adjustments','cash_adjustments'):
            request=self.bridge();request[field]*=2
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'DUPLICATE_ADJUSTMENT'):f.owner_cash_bridge(request)

    def acquisition(self):
        return doc(pretax_synergies_per_year=24,tax_rate='.25',integration_costs_by_year=[12,6,0],
            interest_cash_by_year=[7,7,7],integration_cash_basis='after_tax_cash',interest_cash_basis='pretax_nondeductible',
            existing_shares=60,new_shares=6,scenarios=[
                {'id':'full','ramp_fraction_by_year':['.25','.75',1],'delay_years':0,'realization_fraction':1},
                {'id':'delay','ramp_fraction_by_year':['.25','.75',1],'delay_years':1,'realization_fraction':1}])

    def test_negative_interim_synergy_cash_is_not_total_deal_npv(self):
        result=f.acquisition_cash(self.acquisition())
        self.assertEqual(result['scenarios'][0]['cumulative_incremental_cash'],'-3.0000')
        self.assertEqual(result['scenarios'][1]['cumulative_incremental_cash'],'-21.0000')
        self.assertIsNone(result['total_deal_npv']);self.assertIn('standalone_target_cash_flows',result['missing_total_deal_inputs'])
        self.assertAlmostEqual(float(result['new_shares_fraction_of_post_issue']),6/66)

    def test_unknown_tax_cash_treatment_remains_partial_and_complete_deal_is_separate(self):
        request=self.acquisition();request['integration_cash_basis']='unknown'
        self.assertIsNone(f.acquisition_cash(request)['scenarios'][0]['cumulative_incremental_cash'])
        request['complete_deal_cashflow_contract']={'cashflow_basis':'equity','scope_complete':True,
            'evidence_or_assumptions':'explicit complete fictional equity cash stream','annual_discount_rate':'.1',
            'initial_cash_outlay':100,'dated_year_cashflows':[{'years_after_initial':1,'cash_amount':15,'scope':'complete_operating_cash'},
                {'years_after_initial':1,'cash_amount':110,'scope':'complete_terminal_residual'}]}
        result=f.acquisition_cash(request)
        self.assertAlmostEqual(float(result['total_deal_npv']),125/1.1-100)
        self.assertIsNone(result['scenarios'][0]['total_deal_npv'])

    def valuation(self):
        return doc(amount_unit='USD',years=2,starting_revenue=100,starting_shares=10,entry_price=20,
                   entry_cost_bps=20,exit_cost_bps=30,equity_value_floor_zero=True,
                   reinvestment={'maintenance_capex_fraction_revenue':'.03',
                       'growth_capex_fraction_positive_incremental_revenue':'.25',
                       'working_capital_fraction_incremental_revenue':'.15','working_capital_decrease_treatment':'unknown'},
                   scenarios=[{'id':'central','annual_revenue_growth':'.1','annual_dilution':0,
                       'terminal_ebit_margin':'.2','tax_rate':'.25','exit_ev_to_ebit':10,'net_debt_at_exit':12,
                       'cumulative_dividends_per_share':1}],
                   sensitivities=[{'id':'margin-down','base_scenario_id':'central','overrides':{'terminal_ebit_margin':'.1'}}])

    def test_terminal_price_return_and_reinvestment_are_distinct_with_real_sensitivity(self):
        result=f.terminal_scenarios(self.valuation());central=result['scenarios'][0]
        self.assertEqual(Decimal(central['terminal_share_price']),Decimal(23))
        self.assertEqual(Decimal(central['net_terminal_proceeds_plus_dividends']),Decimal('23.931'))
        self.assertAlmostEqual(float(central['net_total_return_fraction']),23.931/20.04-1)
        self.assertIsNone(central['present_value_of_modeled_distributions'])
        self.assertEqual(Decimal(central['reinvestment_schedule'][0]['total_reinvestment_cash']),Decimal('7.3'))
        self.assertEqual(Decimal(central['reinvestment_schedule'][1]['total_reinvestment_cash']),Decimal('8.03'))
        self.assertEqual(Decimal(result['sensitivities'][0]['terminal_share_price']),Decimal('10.9'))
        self.assertFalse(central['reinvestment_financing_reconciled']);self.assertIsNone(central['interim_free_cash_flow'])

    def test_discount_rate_without_dividend_timing_does_not_create_current_value(self):
        request=self.valuation();request['annual_discount_rate']='.1'
        result=f.terminal_scenarios(request)['scenarios'][0]
        self.assertIsNotNone(result['discounted_terminal_proceeds_only'])
        self.assertIsNone(result['present_value_of_modeled_distributions'])
        request['dividend_timing']='terminal'
        self.assertAlmostEqual(float(f.terminal_scenarios(request)['scenarios'][0]['present_value_of_modeled_distributions']),23.931/1.1**2)
        request['scenarios'][0]['annual_revenue_growth']='-.1'
        down=f.terminal_scenarios(request)['scenarios'][0]
        self.assertIsNone(down['total_reinvestment_cash'])
        self.assertEqual(Decimal(down['reinvestment_schedule'][0]['growth_capex']),0)

    def test_negative_equity_residual_does_not_generate_negative_price_or_fee_rebate(self):
        request=self.valuation();request['scenarios'][0]['net_debt_at_exit']=500;request['equity_value_floor_zero']=False
        result=f.terminal_scenarios(request);central=result['scenarios'][0]
        self.assertLess(Decimal(central['terminal_equity_residual_before_floor']),0)
        self.assertIsNone(central['terminal_share_price']);self.assertIsNone(central['exit_cost_per_share'])
        self.assertEqual(result['status'],'PARTIAL')

    def test_arbitrary_dated_price_horizon_has_two_sided_costs_without_year_rounding(self):
        request=doc(entry_at='2026-10-13T16:00:00Z',exit_at='2026-11-29T17:00:00Z',day_count='ACT/365F',
                    entry_price=40,entry_cost_bps=10,exit_cost_bps=20,
                    scenarios=[{'id':'supplied','terminal_price':44,'cumulative_dividends_per_share':'.4'}])
        result=f.price_scenarios(request);value=result['scenarios'][0]
        self.assertEqual(Decimal(value['terminal_share_price']),44)
        self.assertAlmostEqual(float(value['net_total_return_fraction']),(44-.088+.4)/40.04-1)
        self.assertIsNone(value['present_value_of_modeled_distributions'])
        self.assertLess(float(result['discount_year_fraction']),1)
        self.assertEqual(result['measurement_period']['exit'],request['exit_at'])

    def test_split_price_return_does_not_discard_dividend_or_invent_missing_later_mark(self):
        request=doc(start_mark_on='2026-08-01',end_mark_on='2026-08-02',requested_end_on='2026-08-20',
            start_raw_price=90,end_raw_price=30,new_shares_per_old=3,split_effective_on='2026-08-02',
            dividends=[{'ex_on':'2026-08-12','cash_per_share':'.2','share_basis':'new_share'}])
        result=f.corporate_action_return(request)
        self.assertEqual(Decimal(result['price_return_fraction']),0)
        self.assertIsNone(result['total_return_through_requested_end_fraction'])
        self.assertEqual(Decimal(result['dividends_outside_mark_window'][0]['cash_per_initial_old_share']),Decimal('.6'))
        request['end_mark_on']='2026-08-20'
        result=f.corporate_action_return(request)
        self.assertAlmostEqual(float(result['total_return_through_requested_end_fraction']),.6/90)


if __name__=='__main__':unittest.main()
