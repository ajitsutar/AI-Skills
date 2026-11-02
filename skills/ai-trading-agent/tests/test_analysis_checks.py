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

    def test_expiry_put_model_properties_cover_unlisted_prices_and_unit_mismatch(self):
        # Deliberately sample only rising prices: the analytic domain is wider.
        for units in (40, 80, 120):
            doc = {'shares':80, 'price':30, 'currency':'USD', 'shock_returns':[0.1, 0.4],
                   'hedges':[{'id':'p', 'kind':'expiry_put', 'strike':27,
                              'underlying_units':units, 'premium_per_unit':1.5,
                              'basis':'same_underlying', 'total_explicit_cost':4}]}
            hedge = checks.hedge_scenarios(doc)['hedges'][0]
            model = hedge['expiry_payoff_model']
            self.assertEqual(model['exactly_matched_underlying_units'], units == 80)
            self.assertFalse(model['real_world_loss_guarantee_established'])
            self.assertEqual(model['minimum_combined_net_pnl'], min(80, units)*27-2400-units*1.5-4)
            expected_interval = [0,0] if units < 80 else [27,27] if units > 80 else [0,27]
            self.assertEqual(model['minimum_attained_terminal_price_interval'], expected_interval)
            for terminal in (0, 7, 17, 26.999, 27, 27.001, 33, 50, 1000):
                direct = 80*(terminal-30)+units*max(27-terminal,0)-units*1.5-4
                segment = model['below_or_at_strike'] if terminal <= 27 else model['at_or_above_strike']
                self.assertAlmostEqual(direct, segment['slope']*terminal+segment['intercept'])
                self.assertGreaterEqual(direct+1e-9, model['minimum_combined_net_pnl'])
            for terminal in expected_interval:
                direct = 80*(terminal-30)+units*max(27-terminal,0)-units*1.5-4
                self.assertAlmostEqual(direct, model['minimum_combined_net_pnl'])
            for row in hedge['scenarios']:
                segment = model['at_or_above_strike']
                self.assertAlmostEqual(row['combined_net_pnl'],
                                       segment['slope']*row['equity_terminal_price']+segment['intercept'])

    def test_expiry_model_does_not_round_near_matching_units_or_mislabel_other_models(self):
        doc = {'shares':80, 'price':30, 'currency':'USD', 'shock_returns':[-1,0],
               'hedges':[{'id':'p','kind':'expiry_put','strike':0,'underlying_units':80+1e-9,
                          'premium_per_unit':0,'basis':'same_underlying','total_explicit_cost':0},
                         {'id':'none','kind':'none','total_explicit_cost':0},
                         {'id':'linear','kind':'short_linear','short_notional':2400,
                          'shock_sensitivity':1,'total_explicit_cost':0}]}
        results = checks.hedge_scenarios(doc)['hedges']
        model = results[0]['expiry_payoff_model']
        self.assertFalse(model['exactly_matched_underlying_units'])
        self.assertLess(model['below_or_at_strike']['slope'],0)
        self.assertEqual(model['minimum_attained_terminal_price_interval'],[0,0])
        self.assertEqual(model['minimum_combined_net_pnl'],-2400)
        self.assertNotIn('expiry_payoff_model',results[1])
        self.assertNotIn('expiry_payoff_model',results[2])

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
