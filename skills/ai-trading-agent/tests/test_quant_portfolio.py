"""Generic denominator identities; not investment forecasts or case answers."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import quant_portfolio as portfolio
import numpy as np


def allocation():
    symbols=['PINE','ELM','ASH']
    return {'assets':[{'id':s,'issuer':s,'groups':['basket'],'currency':'CAD',
        'instrument_model':'cash_funded_linear','eligible':True,'previous_weight':0,
        'min_weight':0,'max_weight':.6,'one_way_cost':0,'impact_coefficient':0,
        'borrow_cost_per_period':0,'max_trade_weight':1} for s in symbols],
        'currency':'CAD','horizon_id':'P1M','covariance_horizon_id':'P1M',
        'risk_estimated_at':'2025-06-01T00:00:00Z','decision_at':'2025-06-02T00:00:00Z',
        'covariance_ids':symbols,'covariance':[[.03,0,0],[0,.07,0],[0,0,.12]],
        'objective':'minimum_risk','constraints':{'net_target':.65,'gross_cap':.65,
          'gross_turnover_cap':1,'cash_floor':.2,'collateral_reserve':0,'risk_aversion':1,
          'issuer_gross_cap':.6,'group_gross_caps':{'basket':.65}},
        'scenarios':[{'name':'decline','returns':[-.2,-.2,-.2],'max_loss_fraction':.25}]}


class ConcentrationTests(unittest.TestCase):
    def test_idle_cash_does_not_inflate_effective_risky_count(self):
        result=portfolio.weight_concentration({'PINE':.15,'ELM':.15})
        d=result['risky_position_gross_distribution']
        self.assertAlmostEqual(result['nav_squared_weight_sum_excluding_cash'],.045)
        self.assertAlmostEqual(d['denominator_value'],.3)
        self.assertAlmostEqual(d['hhi'],.5)
        self.assertAlmostEqual(d['effective_equal_weight_count'],2)
        self.assertFalse(d['cash_included'])
        self.assertEqual(result['whole_account_concentration']['status'],'NOT_COMPUTED')

    def test_scale_invariant_normalization_raw_squares_scale_quadratically(self):
        first=portfolio.weight_concentration({'PINE':.12,'ELM':.28})
        second=portfolio.weight_concentration({'PINE':.24,'ELM':.56})
        for field in ('hhi','effective_equal_weight_count'):
            self.assertAlmostEqual(first['risky_position_gross_distribution'][field],second['risky_position_gross_distribution'][field])
        self.assertAlmostEqual(second['nav_squared_weight_sum_excluding_cash'],4*first['nav_squared_weight_sum_excluding_cash'])

    def test_one_nonzero_member_and_zero_members(self):
        d=portfolio.weight_concentration({'PINE':.22,'ELM':0})['risky_position_gross_distribution']
        self.assertEqual(d['nonzero_member_count'],1)
        self.assertEqual(d['normalized_shares'],{'PINE':1,'ELM':0})
        self.assertEqual(d['effective_equal_weight_count'],1)

    def test_zero_gross_has_no_infinite_or_invented_count(self):
        result=portfolio.weight_concentration({'PINE':0,'ELM':0})
        d=result['risky_position_gross_distribution']
        self.assertEqual(d['status'],'ZERO_GROSS_UNAVAILABLE')
        self.assertIsNone(d['hhi']);self.assertIsNone(d['effective_equal_weight_count'])
        self.assertIsNone(d['normalized_shares'])
        self.assertIn('unavailable',portfolio.concentration_summary(result))
        json.dumps(result,allow_nan=False)

    def test_zero_net_signed_book_uses_absolute_gross_not_net(self):
        result=portfolio.weight_concentration({'PINE':.3,'ELM':-.3})
        d=result['risky_position_gross_distribution']
        self.assertEqual(result['signed_input_weights'],{'PINE':.3,'ELM':-.3})
        self.assertEqual(d['scope'],'absolute_gross_signed_positions')
        self.assertTrue(d['negative_weights_present'])
        self.assertAlmostEqual(d['denominator_value'],.6)
        self.assertEqual(d['hhi'],.5);self.assertEqual(d['effective_equal_weight_count'],2)

    def test_invalid_weights_rejected_without_permissive_replacement(self):
        for value in ({},{'PINE':True},{'PINE':float('nan')},{'PINE':float('inf')},{'PINE':'0.2'},{1:.1},None):
            with self.subTest(value=value),self.assertRaises(ValueError):portfolio.weight_concentration(value)

    def test_legacy_empty_string_asset_id_remains_supported(self):
        document=allocation()
        document['assets'][0]['id']='';document['covariance_ids'][0]=''
        out=portfolio.construct(document)
        self.assertEqual(out['status'],'RESEARCH_PROPOSAL')
        self.assertIn('',out['weights'])
        self.assertIn('',out['concentration_diagnostics']['risky_position_gross_distribution']['members'])
        self.assertEqual(out['concentration_diagnostics']['signed_input_weights'],out['weights'])

    def test_member_named_cash_is_retained_as_supplied_not_special_bucket(self):
        d=portfolio.weight_concentration({'CASH':.13,'PINE':.26})['risky_position_gross_distribution']
        self.assertEqual(d['members'],['CASH','PINE'])
        self.assertFalse(d['cash_included'])
        self.assertAlmostEqual(d['normalized_shares']['CASH'],1/3)

    def test_generic_count_bounds_and_summary_same_record(self):
        for values in ({'PINE':.17,'ELM':.23,'ASH':.06},{'PINE':-.1,'ELM':.3},{'PINE':1e-150,'ELM':1e-150}):
            r=portfolio.weight_concentration(values);d=r['risky_position_gross_distribution']
            self.assertGreaterEqual(d['effective_equal_weight_count'],1-1e-12)
            self.assertLessEqual(d['effective_equal_weight_count'],d['nonzero_member_count']+1e-12)
            text=portfolio.concentration_summary(r)
            self.assertIn(f"{d['denominator_value']:.12g}",text)
            self.assertIn(f"{d['hhi']:.12g}",text)
            self.assertIn('reciprocal is not an effective asset count',text)

    def test_construct_native_integration_and_input_unchanged(self):
        document=allocation();before=copy.deepcopy(document);out=portfolio.construct(document)
        self.assertEqual(out['status'],'RESEARCH_PROPOSAL')
        self.assertEqual(document,before)
        self.assertEqual(out['concentration_diagnostics'],portfolio.weight_concentration(out['weights']))
        self.assertEqual(out['concentration_summary'],portfolio.concentration_summary(out['concentration_diagnostics']))
        self.assertFalse(out['execution_authorized'])
        # Concentration must not promote the optimizer's separate certificate.
        # This synthetic model can leave a small gap above certificate tolerance.
        self.assertIn(out['independent_optimality_certificate']['status'],
                      {'CONDITIONAL_MINIMUM_CERTIFIED','NOT_ESTABLISHED'})
        self.assertNotIn('CERTIFIED',out['concentration_summary'])

    def test_sensitivity_retains_covariance_caps_and_failed_cases(self):
        base=allocation();request={'base':base,'covariance_scenarios':[{'id':'revised','covariance_ids':base['covariance_ids'],
            'horizon_id':'P1M','estimated_at':base['risk_estimated_at'],'covariance':[[.06,0,0],[0,.1,0],[0,0,.14]]}],
            'constraint_scenarios':[{'id':'cap','asset_max_weights':{'PINE':.2}},
                                   {'id':'infeasible','constraint_overrides':{'group_gross_caps':{'basket':.1}}}]}
        before=copy.deepcopy(request);out=portfolio.sensitivity(request)
        self.assertEqual(request,before);self.assertIsNone(out['selected_case']);self.assertFalse(out['execution_authorized'])
        for result in [out['baseline'],out['cases'][0]['result'],out['constraint_cases'][0]['result']]:
            self.assertEqual(result['concentration_diagnostics'],portfolio.weight_concentration(result['weights']))
            self.assertIn(result['concentration_summary'],out['concentration_summary'])
        failed=out['constraint_cases'][1]['result'];self.assertIsNone(failed['weights'])
        self.assertNotIn('concentration_diagnostics',failed)
        self.assertIn('no verified feasible weights',out['concentration_summary'])

    def test_report_fact_units_for_construct_and_all_sensitivity_scopes(self):
        import report_facts
        for operation,prefix in [('portfolio.construct',''),('portfolio.sensitivity','baseline/'),
                                 ('portfolio.sensitivity','cases/0/result/'),('portfolio.sensitivity','constraint_cases/1/result/')]:
            with self.subTest(operation=operation,prefix=prefix):
                path=prefix+'concentration_diagnostics/risky_position_gross_distribution/'
                mapping=report_facts.extended_spec(operation,path+'effective_equal_weight_count')
                self.assertEqual(mapping[1],'equivalent_equal_weight_gross_positions')
                self.assertIn('cash excluded',mapping[2])
                self.assertIn('not actual',mapping[3])

    def test_cli_generated_record_serializes_and_native_summary_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();path=root/'request.json'
            path.write_text(json.dumps({'operation':'construct','inputs':{'document':allocation()}}),encoding='utf-8')
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/quant_portfolio.py'),str(path)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            out=json.loads(result.stdout)
            self.assertEqual(out['concentration_summary'],portfolio.concentration_summary(out['concentration_diagnostics']))


class RiskContributionTests(unittest.TestCase):
    def record(self, weights, sigma, horizon='P1M'):
        return portfolio._risk_contributions(list(weights),np.array(list(weights.values()),dtype=float),
                                            np.array(sigma,dtype=float),horizon)

    def test_diagonal_units_and_three_different_additive_identities(self):
        r=self.record({'PINE':.2,'ELM':.3},[[.025,0],[0,.08]])
        terms=r['signed_variance_contributions'];euler=r['euler_volatility_contributions'];shares=r['normalized_variance_shares']
        expected={'PINE':.001,'ELM':.0072};variance=.0082
        for name in expected:
            self.assertAlmostEqual(terms['values'][name],expected[name])
            self.assertAlmostEqual(euler['values'][name],expected[name]/math.sqrt(variance))
            self.assertAlmostEqual(shares['values'][name],expected[name]/variance)
        self.assertAlmostEqual(terms['sum'],variance)
        self.assertAlmostEqual(euler['sum'],math.sqrt(variance))
        self.assertAlmostEqual(shares['sum'],1)
        self.assertNotEqual(terms['unit'],euler['unit']);self.assertNotEqual(shares['unit'],terms['unit'])
        self.assertEqual(r['covariance_horizon_id'],'P1M')
        self.assertEqual(r['scope'],'total_portfolio_covariance_risk')

    def test_signed_hedge_preserves_negative_components_and_shares_above_one(self):
        r=self.record({'PINE':.8,'ELM':-.2},[[.04,.018],[.018,.01]])
        self.assertAlmostEqual(r['portfolio_variance'],.02024)
        self.assertAlmostEqual(r['signed_variance_contributions']['values']['PINE'],.02272)
        self.assertAlmostEqual(r['signed_variance_contributions']['values']['ELM'],-.00248)
        self.assertGreater(r['normalized_variance_shares']['values']['PINE'],1)
        self.assertLess(r['normalized_variance_shares']['values']['ELM'],0)
        self.assertLess(r['euler_volatility_contributions']['values']['ELM'],0)
        self.assertAlmostEqual(r['normalized_variance_shares']['sum'],1)

    def test_negative_covariance_can_hedge_even_without_short_positions(self):
        r=self.record({'PINE':.9,'ELM':.1},[[.04,-.05],[-.05,.09]])
        self.assertLess(r['signed_variance_contributions']['values']['ELM'],0)
        self.assertAlmostEqual(r['signed_variance_contributions']['sum'],r['portfolio_variance'])

    def test_weight_and_covariance_scaling_preserve_unit_relationships(self):
        r=self.record({'PINE':.12,'ELM':.28},[[.03,.01],[.01,.06]])
        doubled=self.record({'PINE':.24,'ELM':.56},[[.03,.01],[.01,.06]])
        covariance_scaled=self.record({'PINE':.12,'ELM':.28},[[.12,.04],[.04,.24]])
        for other in (doubled,covariance_scaled):
            for name in ('PINE','ELM'):
                self.assertAlmostEqual(other['signed_variance_contributions']['values'][name],4*r['signed_variance_contributions']['values'][name])
                self.assertAlmostEqual(other['euler_volatility_contributions']['values'][name],2*r['euler_volatility_contributions']['values'][name])
                self.assertAlmostEqual(other['normalized_variance_shares']['values'][name],r['normalized_variance_shares']['values'][name])

    def test_zero_tiny_and_tolerated_negative_variance_are_not_normalized(self):
        for sigma,status in [([[0.,0.],[0.,0.]],'ZERO_VARIANCE_UNAVAILABLE'),
                             ([[1e-22,0.],[0.,1e-22]],'NEAR_ZERO_VARIANCE_UNAVAILABLE'),
                             ([[-1e-13,0.],[0.,0.]],'NEGATIVE_VARIANCE_UNAVAILABLE')]:
            with self.subTest(status=status):
                # The final example is accepted by the existing PSD tolerance;
                # reporting must not silently turn it into certified zero risk.
                portfolio.covariance(sigma,2)
                r=self.record({'PINE':.3,'ELM':.2},sigma)
                self.assertEqual(r['normalization_status'],status)
                self.assertIsNone(r['normalized_variance_shares']['values'])
                self.assertIsNone(r['euler_volatility_contributions']['values'])
                self.assertIsNone(r['normalized_variance_shares']['sum'])
                self.assertIsNotNone(r['signed_variance_contributions']['values'])
                self.assertTrue(r['unavailable_reason'])
                json.dumps(r,allow_nan=False)
        self.assertLess(r['portfolio_variance'],0)

    def test_threshold_matches_legacy_strict_greater_than_rule(self):
        for variance,available in [(1e-20,False),(1.01e-20,True)]:
            r=self.record({'PINE':1.},[[variance]])
            self.assertEqual(r['normalized_variance_shares']['values'] is not None,available)

    def test_construct_preserves_legacy_fraction_and_uses_declared_horizon(self):
        d=allocation();before=copy.deepcopy(d);out=portfolio.construct(d)
        self.assertEqual(d,before)
        r=out['risk_contributions']
        self.assertEqual(r['normalized_variance_shares']['values'],out['risk_diagnostics']['variance_contribution_fraction'])
        self.assertEqual(r['portfolio_variance'],out['risk_diagnostics']['variance_over_covariance_horizon'])
        self.assertEqual(r['portfolio_volatility'],out['volatility_over_covariance_horizon'])
        self.assertEqual(r['covariance_horizon_id'],d['covariance_horizon_id'])
        self.assertEqual(out['risk_contribution_summary'],portfolio.risk_contribution_summary(r))
        text=out['risk_contribution_summary']
        self.assertIn('Normalized variance shares (dimensionless fraction of portfolio variance',text)
        self.assertIn('Euler volatility contributions (return fraction',text)
        self.assertIn('Signed variance contributions (return fraction squared',text)
        self.assertFalse(out['execution_authorized'])

    def test_sensitivity_uses_each_retained_covariance_and_omits_failed_results(self):
        base=allocation();sigma=[[.06,0,0],[0,.12,0],[0,0,.18]]
        request={'base':base,'covariance_scenarios':[{'id':'revised','covariance_ids':base['covariance_ids'],
            'horizon_id':'P1M','estimated_at':base['risk_estimated_at'],'covariance':sigma}],
            'constraint_scenarios':[{'id':'infeasible','constraint_overrides':{'group_gross_caps':{'basket':.1}}}]}
        out=portfolio.sensitivity(request)
        result=out['cases'][0]['result'];weights=np.array(list(result['weights'].values()))
        expected=float(weights@np.array(sigma)@weights)
        self.assertAlmostEqual(result['risk_contributions']['signed_variance_contributions']['sum'],expected)
        self.assertNotIn('risk_contributions',out['constraint_cases'][0]['result'])
        self.assertIsNone(out['selected_case'])

    def test_generated_report_preserves_three_metric_units_and_native_values(self):
        import quant_report, report_facts
        d=allocation()
        request={'schema_version':1,'contract':{'prompt':'Synthetic covariance attribution','purpose':'offline research',
            'base_currency':'CAD','horizon_id':'P1M','as_of':d['decision_at']},
            'jobs':[{'id':'allocate','operation':'portfolio.construct','inputs':{'document':d}}]}
        artifacts=quant_report.build(quant_report.encoded(request),lambda path,index:self.fail('Unexpected source read'))
        facts=json.loads(artifacts['facts.json'])
        wanted={'Signed contribution to portfolio variance':'return_fraction_squared_over_covariance_horizon',
                'Euler contribution to portfolio volatility':'return_fraction_over_covariance_horizon',
                'Normalized share of portfolio variance':'fraction_of_portfolio_variance'}
        for metric,unit in wanted.items():
            found=[f for f in facts['facts'] if f['metric']==metric and '/risk_contributions/' in f['source']['pointer']]
            self.assertEqual(len(found),3)
            self.assertTrue(all(f['unit']==unit for f in found))
        self.assertEqual(report_facts.verify_projection(artifacts['bundle.json'],'quant',artifacts['facts.json'])['status'],'VERIFIED_PROJECTION')
        changed=copy.deepcopy(facts)
        next(f for f in changed['facts'] if f['metric']=='Normalized share of portfolio variance')['unit']='return_fraction_squared'
        self.assertEqual(report_facts.verify_projection(artifacts['bundle.json'],'quant',quant_report.encoded(changed))['status'],'PROJECTION_MISMATCH')

    def test_report_semantics_cover_nested_sensitivity_and_legacy_fractions(self):
        import report_facts
        for operation,prefix in [('portfolio.construct',''),('portfolio.sensitivity','baseline/'),
                                 ('portfolio.sensitivity','cases/0/result/'),('portfolio.sensitivity','constraint_cases/1/result/')]:
            with self.subTest(operation=operation,prefix=prefix):
                new=report_facts.extended_spec(operation,prefix+'risk_contributions/normalized_variance_shares/values/PINE')
                legacy=report_facts.extended_spec(operation,prefix+'risk_diagnostics/variance_contribution_fraction/PINE')
                self.assertEqual(new,legacy)
                self.assertEqual(new[1],'fraction_of_portfolio_variance')
                self.assertIn('portfolio variance',new[2])


if __name__=='__main__':unittest.main()
