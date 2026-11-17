"""Generic denominator identities; not investment forecasts or case answers."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import quant_portfolio as portfolio


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


if __name__=='__main__':unittest.main()
