import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import analysis_checks as checks


class AnalysisChecksTests(unittest.TestCase):
    def test_covariance_change_is_not_scale_even_when_weights_similar(self):
        result = checks.covariance_comparison({'asset_ids': ['X','Y'],
            'base': [[.04,.015],[.015,.09]], 'alternative': [[.09,.03],[.03,.16]]})
        self.assertFalse(result['pure_nonnegative_scale'])
        self.assertAlmostEqual(result['variances'][0]['variance_multiplier'], 2.25)
        self.assertNotEqual(result['variance_ratios'][0]['base_variance_ratio'],
                            result['variance_ratios'][0]['alternative_variance_ratio'])
        self.assertIsNone(result['observation_frequency'])

    def test_scale_requires_zero_entries_to_stay_zero(self):
        base = [[.01,0],[0,.04]]
        valid = checks.covariance_comparison({'asset_ids':['a','b'], 'base':base,
                                             'alternative':[[.03,0],[0,.12]]})
        self.assertTrue(valid['pure_nonnegative_scale'])
        self.assertAlmostEqual(valid['common_scale'], 3)
        changed = checks.covariance_comparison({'asset_ids':['a','b'], 'base':base,
                                               'alternative':[[.03,.01],[.01,.12]]})
        self.assertFalse(changed['pure_nonnegative_scale'])

    def test_put_and_linear_hedge_conservation(self):
        doc={'shares':100,'price':25,'currency':'USD','shock_returns':[-.3,-.1,0,.2],
             'hedges':[{'id':'put','kind':'expiry_put','strike':23,'underlying_units':100,
                        'premium_per_unit':1.2,'basis':'same_underlying','total_explicit_cost':2},
                       {'id':'short','kind':'short_linear','short_notional':1250,
                        'shock_sensitivity':.8,'total_explicit_cost':7}]}
        result=checks.hedge_scenarios(doc)
        self.assertEqual(result['hedges'][0]['scenarios'][1]['hedge_payoff_before_cost'],50)
        self.assertAlmostEqual(result['hedges'][1]['linear_residual_fraction'],.6)
        for hedge in result['hedges']:
            for row in hedge['scenarios']:
                self.assertAlmostEqual(row['combined_net_pnl'], row['equity_pnl']+
                    row['hedge_payoff_before_cost']-row['premium']-row['total_explicit_cost'])

    def test_missing_fee_is_not_zero_fee(self):
        with self.assertRaises(KeyError):
            checks.hedge_scenarios({'shares':1,'price':8,'currency':'USD','shock_returns':[0],
                                   'hedges':[{'id':'none','kind':'none'}]})

    def test_exact_inequality_boundary_and_float_tolerance_differ(self):
        meta=dict(unit='ratio',denominator='same supplied definition',basis='declared covenant',horizon='not_applicable',
                  observation_frequency='not_applicable',measurement_period='current snapshot')
        left=dict(value=3.5,**meta); right=dict(value=3.5,**meta)
        self.assertFalse(checks.compare_claim(dict(left=left,right=right,relation='lt'))['typed_comparison'])
        self.assertTrue(checks.compare_claim(dict(left=left,right=right,relation='le'))['typed_comparison'])
        right['value']+=1e-9
        self.assertTrue(checks.compare_claim(dict(left=left,right=right,relation='eq'))['typed_comparison'])

    def test_matching_unknown_dimensions_do_not_establish_comparability(self):
        result=checks.compare_claim({'left':{'value':1},'right':{'value':1},'relation':'eq'})
        self.assertEqual(result['status'],'UNKNOWN_COMPARABILITY')
        self.assertIsNone(result['typed_comparison'])

    def test_units_and_nonfinite_values_cannot_silently_match(self):
        meta=dict(denominator='d',basis='b',horizon='h',observation_frequency='f',measurement_period='p')
        result=checks.compare_claim({'left':dict(value=1,unit='USD',**meta),
                                     'right':dict(value=1,unit='EUR',**meta),'relation':'eq'})
        self.assertEqual(result['status'],'INCOMPARABLE')
        with self.assertRaises(ValueError):
            checks.compare_claim({'left':{'value':float('nan')},'right':{'value':1},'relation':'eq'})

    def test_blank_metadata_and_different_denominators(self):
        meta=dict(unit='fraction',denominator='equity',basis='net',horizon='h',observation_frequency='f',measurement_period='p')
        left=dict(value=.1,**meta);right=dict(left,denominator='trade capital')
        result=checks.compare_claim(dict(left=left,right=right,relation='eq'))
        self.assertEqual(result['mismatched_dimensions'],['denominator'])
        self.assertIsNone(result['typed_comparison'])
        right=dict(left,denominator='  ')
        self.assertEqual(checks.compare_claim(dict(left=left,right=right,relation='eq'))['status'],'UNKNOWN_COMPARABILITY')
        with self.assertRaises(ValueError):
            checks.compare_claim(dict(left=left,right=dict(left,unit=[]),relation='eq'))

    def test_tiny_nonzero_covariance_still_has_identifiable_scale(self):
        result=checks.covariance_comparison({'asset_ids':['tiny'],'base':[[1e-14]],'alternative':[[2e-14]]})
        self.assertTrue(result['pure_nonnegative_scale'])
        self.assertEqual(result['common_scale'],2)
        changed=checks.covariance_comparison({'asset_ids':['a','b'],
            'base':[[1e-14,0],[0,2e-14]],'alternative':[[2e-14,1e-14],[1e-14,4e-14]]})
        self.assertFalse(changed['pure_nonnegative_scale'])


if __name__=='__main__':
    unittest.main()
