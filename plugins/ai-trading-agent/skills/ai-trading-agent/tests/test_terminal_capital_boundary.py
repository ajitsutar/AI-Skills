"""Conditional one-parameter boundaries use independent generic model inputs."""
import copy
from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import financial_alignment as f
import research_workflow as workflow
from test_research_workflow import encode,plan_for,selected,build,write_artifacts


def document():
    return {'currency':'EUR','role':'hypothetical_scenario','amount_unit':'EUR',
        'years':2,'starting_revenue':120,'starting_shares':8,'entry_price':18,
        'entry_cost_bps':30,'exit_cost_bps':40,'equity_value_floor_zero':False,
        'scenario_probabilities':None,
        'reinvestment':{'maintenance_capex_fraction_revenue':'.04',
            'growth_capex_fraction_positive_incremental_revenue':'.3',
            'working_capital_fraction_incremental_revenue':'.1','working_capital_decrease_treatment':'unknown'},
        'scenarios':[{'id':'moderate','annual_revenue_growth':'.08','terminal_ebit_margin':'.2',
            'tax_rate':'.22','net_debt_at_exit':18,'annual_dilution':'.02',
            'exit_ev_to_ebit':4,'cumulative_dividends_per_share':'.8'}]}


def diagnostic(doc):return f.terminal_scenarios(doc)['conditional_exit_multiple_diagnostics'][0]
def exact(row):return Fraction(int(row['exact_numerator']),int(row['exact_denominator']))


class CapitalBoundaryTests(unittest.TestCase):
    def test_exact_boundary_equation_and_replayed_neighbours(self):
        doc=document();result=f.terminal_scenarios(doc);d=result['conditional_exit_multiple_diagnostics'][0]
        self.assertEqual(d['status'],'CONDITIONAL_BOUNDARY_COMPUTED')
        row=result['scenarios'][0];m=exact(d['solution']['minimum_multiple'])
        e=Fraction(Decimal(row['terminal_ebit']));shares=Fraction(Decimal(row['terminal_diluted_shares']))
        outlay=Fraction(Decimal(row['entry_outlay_per_share']));dividend=Fraction(Decimal('.8'))
        self.assertEqual(((e*m-18)/shares)*(1-Fraction(40,10000))+dividend,outlay)
        self.assertEqual(d['boundary_replay']['exact_retained_operand_relation'],'AT_TARGET')
        self.assertLessEqual(abs(Decimal(d['boundary_replay']['proceeds_minus_outlay'])),Decimal(d['numerical_replay_tolerance']['absolute_proceeds_per_share']))
        self.assertEqual(d['below_probe']['replay_relation'],'BELOW_TARGET')
        self.assertEqual(d['above_probe']['replay_relation'],'ABOVE_TARGET')
        self.assertFalse(d['solution']['strict_positive_return_established_by_equality'])
        self.assertIsNone(d['necessary_joint_parameter_conditions'])

    def test_weaker_row_has_sufficient_alternative_without_joint_favorable_inputs(self):
        doc=document();weak=doc['scenarios'][0]
        weak.update(annual_revenue_growth='0',terminal_ebit_margin='.1',annual_dilution='.04',net_debt_at_exit=35)
        strong={**weak,'id':'strong','annual_revenue_growth':'.14','terminal_ebit_margin':'.25',
                'annual_dilution':'0','net_debt_at_exit':5,'exit_ev_to_ebit':9}
        doc['scenarios'].append(strong)
        result=f.terminal_scenarios(doc);a,b=result['conditional_exit_multiple_diagnostics']
        self.assertLess(Decimal(result['scenarios'][0]['net_total_return_fraction']),0)
        self.assertGreater(Decimal(a['above_probe']['net_total_return_fraction']),0)
        self.assertGreater(exact(a['solution']['minimum_multiple']),exact(b['solution']['minimum_multiple']))
        self.assertEqual(a['held_assumptions']['scenario']['terminal_ebit_margin'],'.1')
        self.assertEqual(a['held_assumptions']['scenario']['annual_dilution'],'.04')
        self.assertEqual(a['held_assumptions']['scenario']['net_debt_at_exit'],35)

    def test_original_rows_inputs_sensitivity_counts_probabilities_and_reinvestment_unchanged(self):
        doc=document();doc['sensitivities']=[{'id':'other-margin','base_scenario_id':'moderate','overrides':{'terminal_ebit_margin':'.15'}}]
        before=copy.deepcopy(doc)
        raw=f._terminal(doc,doc['scenarios'][0]);result=f.terminal_scenarios(doc)
        # Serialize the original kernel's Decimal values through its existing finish wrapper.
        original=f.finish(doc,'comparison',row=raw)['row']
        self.assertEqual(result['scenarios'][0],original)
        self.assertEqual(doc,before)
        self.assertEqual(result['scenario_coverage']['evaluated_row_count'],2)
        self.assertEqual(result['scenario_coverage']['scenario_ids'],['moderate'])
        self.assertEqual(result['scenario_coverage']['sensitivity_ids'],['other-margin'])
        self.assertEqual(len(result['conditional_exit_multiple_diagnostics']),2)
        second=result['conditional_exit_multiple_diagnostics'][1]
        self.assertEqual(second['row_kind'],'declared_sensitivity')
        self.assertEqual(second['source_base_scenario_id'],'moderate')
        self.assertEqual(second['held_assumptions']['scenario']['terminal_ebit_margin'],'.15')
        self.assertIsNone(result['scenario_probabilities']);self.assertIsNone(result['probability_weighted_value'])
        self.assertFalse(result['scenarios'][0]['reinvestment_financing_reconciled'])
        self.assertFalse(result['scenario_coverage']['parameter_domain_exhaustive'])

    def test_costs_dividends_and_dilution_have_correct_conditional_direction(self):
        base=document();m=exact(diagnostic(base)['solution']['minimum_multiple'])
        high=copy.deepcopy(base);high['entry_cost_bps']=200;high['exit_cost_bps']=350
        self.assertGreater(exact(diagnostic(high)['solution']['minimum_multiple']),m)
        dividend=copy.deepcopy(base);dividend['scenarios'][0]['cumulative_dividends_per_share']=3
        self.assertLess(exact(diagnostic(dividend)['solution']['minimum_multiple']),m)
        dilution=copy.deepcopy(base);dilution['scenarios'][0]['annual_dilution']='.1'
        self.assertGreater(exact(diagnostic(dilution)['solution']['minimum_multiple']),m)

    def test_zero_costs_and_dividends_and_positive_ebit_net_cash(self):
        doc=document();doc.update(entry_cost_bps=0,exit_cost_bps=0)
        doc['scenarios'][0]['cumulative_dividends_per_share']=0
        row=f._terminal(doc,doc['scenarios'][0]);d=diagnostic(doc)
        expected=(Fraction(18)+Fraction(row['terminal_diluted_shares'])*18)/Fraction(row['terminal_ebit'])
        self.assertEqual(exact(d['solution']['minimum_multiple']),expected)
        doc['scenarios'][0]['net_debt_at_exit']=-250
        d=diagnostic(doc)
        self.assertEqual(d['status'],'ALREADY_SATISFIED_AT_DOMAIN_MINIMUM')
        self.assertEqual(exact(d['solution']['minimum_multiple']),0)
        self.assertEqual(d['boundary_replay']['exact_retained_operand_relation'],'ABOVE_TARGET')

    def test_zero_ebit_unattainable_and_no_investable_domain_are_distinct(self):
        doc=document();doc['scenarios'][0]['terminal_ebit_margin']=0;doc['equity_value_floor_zero']=True
        d=diagnostic(doc)
        self.assertEqual(d['status'],'UNATTAINABLE_WITH_FIXED_INPUTS');self.assertIsNone(d['solution'])
        self.assertEqual(d['above_probe']['exact_retained_operand_relation'],'BELOW_TARGET')
        doc['equity_value_floor_zero']=False
        d=diagnostic(doc)
        self.assertEqual(d['status'],'NO_INVESTABLE_PRICE_IN_DOMAIN')
        self.assertTrue(d['domain']['investable_price_domain_empty'])
        doc['scenarios'][0]['net_debt_at_exit']=0
        self.assertEqual(diagnostic(doc)['status'],'UNATTAINABLE_WITH_FIXED_INPUTS')

    def test_zero_ebit_net_cash_or_dividends_can_already_preserve_capital(self):
        for floor in (True,False):
            doc=document();doc['equity_value_floor_zero']=floor
            doc['scenarios'][0].update(terminal_ebit_margin=0,net_debt_at_exit=-220)
            d=diagnostic(doc)
            self.assertEqual(d['status'],'ALREADY_SATISFIED_AT_DOMAIN_MINIMUM')
            self.assertEqual(exact(d['solution']['minimum_multiple']),0)
            self.assertEqual(d['domain_minimum_replay']['net_total_return_fraction'],d['above_probe']['net_total_return_fraction'])
        doc=document();doc['equity_value_floor_zero']=True
        doc['scenarios'][0].update(terminal_ebit_margin=0,cumulative_dividends_per_share=25)
        self.assertEqual(diagnostic(doc)['status'],'ALREADY_SATISFIED_AT_DOMAIN_MINIMUM')

    def test_dividend_floor_plateau_equality_is_not_strict_outperformance(self):
        doc=document();doc['equity_value_floor_zero']=True
        doc['scenarios'][0].update(net_debt_at_exit=300,cumulative_dividends_per_share='18.054')
        d=diagnostic(doc)
        self.assertEqual(d['status'],'ALREADY_SATISFIED_AT_DOMAIN_MINIMUM')
        self.assertEqual(d['boundary_replay']['exact_retained_operand_relation'],'AT_TARGET')
        self.assertEqual(d['above_probe']['exact_retained_operand_relation'],'AT_TARGET')
        self.assertIsNone(d['below_probe'])
        self.assertFalse(d['solution']['strict_positive_return_established_by_equality'])

    def test_no_floor_boundary_uses_valid_price_domain(self):
        doc=document();doc['scenarios'][0].update(exit_ev_to_ebit=0,net_debt_at_exit=55,cumulative_dividends_per_share=25)
        result=f.terminal_scenarios(doc);d=result['conditional_exit_multiple_diagnostics'][0]
        self.assertEqual(result['scenarios'][0]['status'],'NEGATIVE_EQUITY_RESIDUAL_NO_INVESTABLE_PRICE')
        self.assertIsNone(result['scenarios'][0]['terminal_share_price'])
        self.assertEqual(d['status'],'ALREADY_SATISFIED_AT_DOMAIN_MINIMUM')
        self.assertGreater(exact(d['domain']['investable_minimum_multiple']),0)
        self.assertEqual(d['boundary_replay']['status'],'COMPUTED')
        self.assertGreaterEqual(Decimal(d['boundary_replay']['terminal_share_price']),0)
        self.assertIsNone(d['below_probe'])

    def test_negative_ebit_guard_and_existing_kernel_rejection(self):
        doc=document();base=f._terminal(doc,doc['scenarios'][0]);base['terminal_ebit']=Decimal(-2)
        d=f._capital_preservation_boundary(doc,doc['scenarios'][0],base)
        self.assertEqual(d['status'],'UNSUPPORTED_NEGATIVE_EBIT_DIAGNOSTIC')
        self.assertIsNone(d['solution'])
        doc['scenarios'][0]['terminal_ebit_margin']='-.1'
        with self.assertRaises(ValueError):f.terminal_scenarios(doc)

    def test_no_discount_benchmark_or_objective_is_inferred(self):
        doc=document();d=diagnostic(doc)
        self.assertEqual(d['criterion']['id'],'AFTER_COST_CAPITAL_PRESERVATION')
        self.assertFalse(d['criterion']['user_objective_inferred'])
        self.assertIsNone(d['domain']['maximum_multiple'])
        self.assertNotIn('annual_discount_rate',d['held_assumptions']['document'])
        self.assertIsNone(f.terminal_scenarios(doc)['scenarios'][0]['present_value_of_modeled_distributions'])

    def test_source_bound_replay_keeps_original_arguments(self):
        doc=document();sources={'scenario':('scenario.json',encode(doc),'synthetic scenario')}
        plan=plan_for(sources,[{'id':'terminal','operation':'financial.terminal_scenarios','arguments':{'document':selected('scenario')}}])
        artifacts=build(plan,sources)
        self.assertEqual(json.loads(artifacts['jobs/0000/arguments.json']),{'document':doc})
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';write_artifacts(folder,artifacts)
            self.assertEqual(workflow.verify(folder)['status'],'WORKFLOW_REPLAY_AND_REPORT_MATCH')


if __name__=='__main__':unittest.main()
