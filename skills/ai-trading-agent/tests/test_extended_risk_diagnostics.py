"""Fictional numerical identities and adverse cases, not market validation."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import garch_volatility as garch
import risk_diagnostics as risk
import quant_portfolio as portfolio


def allocation():
    return {'assets': [{'id': s, 'issuer': s, 'groups': ['all'], 'currency': 'USD',
                       'instrument_model': 'cash_funded_linear', 'eligible': True,
                       'previous_weight': 0, 'min_weight': 0, 'max_weight': .6,
                       'one_way_cost': 0, 'impact_coefficient': 0, 'borrow_cost_per_period': 0,
                       'max_trade_weight': 1} for s in ['A', 'B', 'C']],
            'currency': 'USD', 'horizon_id': 'P1Y', 'covariance_horizon_id': 'P1Y',
            'risk_estimated_at': '2026-01-01T00:00:00Z', 'decision_at': '2026-01-02T00:00:00Z',
            'covariance_ids': ['A', 'B', 'C'], 'covariance': [[.04, 0, 0], [0, .09, 0], [0, 0, .16]],
            'objective': 'minimum_risk', 'constraints': {'net_target': .9, 'gross_cap': .9,
                'gross_turnover_cap': .9, 'cash_floor': .1, 'collateral_reserve': 0,
                'risk_aversion': 1, 'issuer_gross_cap': .6, 'group_gross_caps': {'all': .9}},
            'scenarios': [{'name': 'decline', 'returns': [-.4, -.4, -.4], 'max_loss_fraction': .36}]}


def tail_input():
    return {'symbols': ['A'], 'weights': {'A': 1.}, 'currency': 'USD', 'notional': 1000,
            'period_label': 'one_trading_day',
            'weight_basis': 'fraction_of_supplied_notional', 'as_of': '2026-01-10T00:00:00Z',
            'return_basis': 'simple_total_return_decimal', 'confidence_levels': [.625],
            'observations': [{'timestamp': f'2026-01-0{i+1}T00:00:00Z', 'returns': {'A': r}}
                             for i, r in enumerate([-.4, -.2, .1, .2])]}


def conditional_input():
    return {'symbols': ['A', 'B'], 'weights': {'A': .5, 'B': .5}, 'currency': 'USD',
            'period_label': 'one_trading_day', 'correlation_ids': ['A', 'B'],
            'notional': 1000, 'weight_basis': 'fraction_of_supplied_notional',
            'as_of': '2026-01-10T00:00:00Z', 'forecast_origin': '2026-01-09T00:00:00Z',
            'correlation_as_of': '2026-01-09T00:00:00Z',
            'variance_basis': 'simple_total_return_decimal', 'correlation_return_basis': 'simple_total_return_decimal',
            'correlation': [[1, .25], [.25, 1]],
            'variance_units': 'decimal_return_squared_per_period',
            'variance_paths': {'A': [.0004, .0004], 'B': [.0009, .0009]},
            'model_flags': {'A': [], 'B': ['ILL_CONDITIONED_MODEL']},
            'periods_per_year': 252, 'horizons': [1, 2]}


class GarchExtensions(unittest.TestCase):
    def setUp(self):
        self.x = np.random.default_rng(51).normal(size=360)

    def test_normal_default_matches_explicit_normal(self):
        a = garch.model_specification('garch', self.x).fix([.1, .1, .8])
        b = garch.model_specification('garch', self.x, 'normal').fix([.1, .1, .8])
        np.testing.assert_array_equal(garch.analytic_variance(a, 5), garch.analytic_variance(b, 5))

    def test_student_t_recursion_uses_unit_variance_innovations(self):
        fixed = garch.model_specification('garch', self.x, 't').fix([.1, .1, .8, 5])
        first = .1+.1*self.x[-1]**2+.8*fixed.conditional_volatility[-1]**2
        np.testing.assert_allclose(garch.analytic_variance(fixed, 3), [first, .1+.9*first, .19+.81*first])

    def test_actual_student_t_fit_and_holdout_are_finite(self):
        rng=np.random.default_rng(701);value=0.;variance=.625;observations=[]
        for _ in range(650):
            variance=.05+.06*value*value+.86*variance
            value=np.sqrt(variance)*rng.standard_t(8)*np.sqrt(6/8)
            observations.append(value)
        fit=garch.fit_model('garch',observations,'t')
        self.assertIn('nu',fit.params)
        self.assertTrue(np.all(garch.forecast(fit,21)>0))
        result=garch.holdout_validation(observations,'garch',610,40,'t')
        self.assertEqual(result['status'],'ok')
        self.assertTrue(np.isfinite(result['qlike']) and np.isfinite(result['ewma_qlike']))

    def test_student_t_finite_variance_is_not_finite_fourth_moment(self):
        fixed = garch.model_specification('garch', self.x, 't').fix([.1, .1, .8, 3])
        result = garch.residual_diagnostics(fixed)
        self.assertTrue(result['conditional_second_moment_finite'])
        self.assertFalse(result['innovation_fourth_moment_finite'])
        self.assertIn('STUDENT_T_FOURTH_MOMENT_NOT_FINITE', result['flags'])
        self.assertFalse(result['diagnostics_passed'])

    def test_nonfinite_second_moment_rejected(self):
        fixed = garch.model_specification('garch', self.x).fix([.1, .1, .8])
        pars = fixed.params.copy(); pars['nu'] = 2
        bad = SimpleNamespace(convergence_flag=0, params=pars, conditional_volatility=fixed.conditional_volatility,
                              loglikelihood=fixed.loglikelihood, model=fixed.model)
        with self.assertRaisesRegex(ValueError, 'nu greater'):
            garch.require_usable_fit(bad)

    def test_ewma_is_causal_and_matches_independent_recursion(self):
        pars = SimpleNamespace(params=[.1, .1, .8])
        changed = self.x.copy(); changed[305] = 25
        with patch('garch_volatility.fit_model', return_value=pars):
            a = garch.holdout_validation(self.x, 'garch', 300, 30)
            b = garch.holdout_validation(changed, 'garch', 300, 30)
        np.testing.assert_array_equal(a['ewma_predicted_variance_percent_squared'][:6],
                                      b['ewma_predicted_variance_percent_squared'][:6])
        self.assertNotEqual(a['ewma_predicted_variance_percent_squared'][6], b['ewma_predicted_variance_percent_squared'][6])
        state = self.x[:300].var(ddof=1)
        for r in self.x[:300]:state=.94*state+.06*r*r
        self.assertAlmostEqual(a['ewma_predicted_variance_percent_squared'][0], state)

    def test_autocorrelated_standardized_residuals_flagged(self):
        fixed = garch.model_specification('garch', self.x).fix([.1, .1, .8])
        z = np.sin(np.arange(360)*.08)
        mock = SimpleNamespace(params=fixed.params, model=fixed.model, std_resid=z)
        self.assertIn('STANDARDIZED_RESIDUAL_AUTOCORRELATION', garch.residual_diagnostics(mock)['flags'])

    def test_bad_distribution_and_decay_rejected(self):
        with self.assertRaises(ValueError):garch.model_specification('garch', self.x, 'unknown')
        with self.assertRaises(ValueError):garch.holdout_validation(self.x, 'garch', 300, 30, ewma_decay=1)


class DistributionDiagnostics(unittest.TestCase):
    def test_finite_inputs_cannot_emit_overflowed_risk(self):
        d=tail_input()
        for row in d['observations']:row['returns']['A']=1e308
        with self.assertRaisesRegex(ValueError,'NONFINITE_SHOCK_AGGREGATE'):risk.empirical_tail(d)
        d=tail_input();d['notional']=1e308
        for row in d['observations']:row['returns']['A']=10.
        with self.assertRaisesRegex(ValueError,'NONFINITE_TAIL_AGGREGATE'):risk.empirical_tail(d)
        d=conditional_input();d['weights']={'A':1.,'B':0.};d['variance_paths']['A']=[1e308,1e308]
        with self.assertRaisesRegex(ValueError,'NONFINITE_CONDITIONAL_AGGREGATE'):risk.conditional_portfolio(d)

    def test_fractional_tail_identity_without_nav(self):
        out = risk.empirical_tail(tail_input()); tail = out['tails'][0]
        self.assertAlmostEqual(tail['loss_expected_shortfall_fraction'], (.4+.5*.2)/1.5)
        self.assertAlmostEqual(tail['loss_var_fraction'], .2)
        self.assertEqual(tail['effective_tail_observations'], 1.5)
        self.assertTrue(tail['sparse_tail_warning'])
        self.assertNotIn('curve', out);self.assertNotIn('total_return', out)

    def test_cash_and_notional_denominators(self):
        d = tail_input();d['weights']['A'] = .5
        t = risk.empirical_tail(d)['tails'][0]
        self.assertAlmostEqual(t['loss_expected_shortfall_notional'], 1000*(.4+.1)/1.5*.5)

    def test_future_unaligned_or_impossible_returns_rejected(self):
        d=tail_input();d['as_of']='2026-01-01T00:00:00Z'
        with self.assertRaises(ValueError):risk.empirical_tail(d)
        d=tail_input();d['observations'][1]['returns']={'B':.1}
        with self.assertRaises(ValueError):risk.empirical_tail(d)
        d=tail_input();d['observations'][0]['returns']['A']=-1.01
        with self.assertRaises(ValueError):risk.empirical_tail(d)

    def test_conditional_variance_units_and_warning_preservation(self):
        out=risk.conditional_portfolio(conditional_input())
        self.assertAlmostEqual(out['horizons'][0]['cumulative_sigma_fraction'], .02)
        self.assertAlmostEqual(out['horizons'][1]['cumulative_sigma_notional'], 1000*np.sqrt(.0008))
        self.assertEqual(out['retained_model_flags']['B'], ['ILL_CONDITIONED_MODEL'])
        self.assertFalse(out['calibration_established'])

    def test_cross_basis_cannot_be_silent(self):
        d=conditional_input();d['variance_basis']='log_return_decimal'
        with self.assertRaises(ValueError):risk.conditional_portfolio(d)
        d['cross_basis_approximation_acknowledged']=True
        self.assertTrue(risk.conditional_portfolio(d)['cross_basis_approximation'])

    def test_invalid_correlation_units_and_horizon_rejected(self):
        for k,v in [('correlation',[[1,1.2],[1.2,1]]),('variance_units','percent_squared'),('horizons',[3])]:
            d=conditional_input();d[k]=v
            with self.assertRaises(ValueError):risk.conditional_portfolio(d)


class ConditionalSpendingGoal(unittest.TestCase):
    def request(self, amount=250, horizon=8):
        document = conditional_input()
        document.update(notional=2000, weights={'A': .3, 'B': .4})
        document['spending_goal'] = {'kind': 'withdrawal', 'amount': amount,
                                    'currency': 'USD', 'horizon_periods': horizon,
                                    'period_label': document['period_label'],
                                    'withdrawal_timing': 'end_of_horizon'}
        return document

    def test_cash_denominator_and_goal_beyond_path(self):
        document = self.request(); before = copy.deepcopy(document)
        out = risk.conditional_portfolio(document); goal = out['spending_goal']
        self.assertEqual(document, before)
        self.assertEqual((out['invested_weight'], out['cash_weight_assumed_zero_shock']), (.7, .3))
        self.assertEqual(out['modeled_cash_notional'], 600)
        self.assertIsNone(out['actual_available_cash'])
        self.assertEqual(out['available_variance_periods'], 2)
        self.assertFalse(goal['goal_horizon_within_variance_path'])
        self.assertEqual([h['periods'] for h in out['horizons']], [1, 2])
        cash = goal['cash_only_sensitivity']
        self.assertEqual((cash['cash_before_withdrawal'], cash['cash_after_withdrawal'], cash['shortfall']), (600, 350, 0))
        self.assertTrue(cash['covered_under_assumptions'])
        self.assertEqual(goal['target_fraction_of_notional'], .125)
        self.assertEqual(len(cash['assumptions']), 3)
        self.assertIsNone(goal['actual_available_cash'])
        self.assertIsNone(goal['probability'])
        self.assertFalse(goal['funding_established'])

    def test_equal_zero_and_shortfall_boundaries(self):
        for amount, remaining, covered in [(0, 600, True), (600, 0, True), (750, -150, False)]:
            with self.subTest(amount=amount):
                cash = risk.conditional_portfolio(self.request(amount))['spending_goal']['cash_only_sensitivity']
                self.assertEqual(cash['cash_after_withdrawal'], remaining)
                self.assertEqual(cash['shortfall'], max(0, -remaining))
                self.assertEqual(cash['covered_under_assumptions'], covered)
        for weights, cash in [({'A': 1, 'B': 0}, 0), ({'A': 0, 'B': 0}, 2000)]:
            document = self.request(); document['weights'] = weights
            self.assertEqual(risk.conditional_portfolio(document)['modeled_cash_notional'], cash)
        document = self.request(200); document['weights'] = {'A': .6, 'B': .3}
        self.assertEqual(risk.conditional_portfolio(document)['spending_goal']['cash_only_sensitivity']['cash_after_withdrawal'], 0)

    def test_optional_goal_does_not_change_risk_or_rehabilitate_models(self):
        document = self.request(horizon=1)
        legacy = copy.deepcopy(document); del legacy['spending_goal']
        a, b = risk.conditional_portfolio(document), risk.conditional_portfolio(legacy)
        self.assertNotIn('spending_goal', b)
        self.assertEqual(a['horizons'], b['horizons'])
        self.assertEqual(a['variance_per_period_decimal_squared'], b['variance_per_period_decimal_squared'])
        self.assertEqual(a['retained_model_flags'], document['model_flags'])
        self.assertFalse(a['calibration_established'])
        self.assertTrue(a['spending_goal']['goal_horizon_within_variance_path'])
        self.assertIsNone(a['spending_goal']['probability'])
        self.assertFalse(a['execution_authorized'])
        document['variance_basis'] = 'log_return_decimal'
        with self.assertRaisesRegex(ValueError, 'CROSS_BASIS_APPROXIMATION_NOT_DECLARED'):
            risk.conditional_portfolio(document)
        document['cross_basis_approximation_acknowledged'] = True
        self.assertTrue(risk.conditional_portfolio(document)['cross_basis_approximation'])
        document['correlation_ids'] = ['B', 'A']
        with self.assertRaisesRegex(ValueError, 'CORRELATION_ORDER_REQUIRED'):
            risk.conditional_portfolio(document)

    def test_goal_schema_units_and_finite_arithmetic(self):
        invalid = [('amount', True), ('amount', -1), ('amount', float('inf')),
                   ('amount', float('nan')), ('horizon_periods', 0), ('horizon_periods', True),
                   ('horizon_periods', 1.5), ('currency', 'EUR'), ('period_label', 'calendar_day'),
                   ('kind', 'investment_profit'), ('withdrawal_timing', 'start_of_horizon'),
                   ('unsupported_extra', 1)]
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                document = self.request(); document['spending_goal'][field] = value
                with self.assertRaises(ValueError): risk.conditional_portfolio(document)
        for goal in (None, [], {}, {'amount': 1}):
            document = self.request(); document['spending_goal'] = goal
            with self.assertRaises(ValueError): risk.conditional_portfolio(document)
        document = self.request(1e308); document['notional'] = 1e-12
        with self.assertRaisesRegex(ValueError, 'NONFINITE_SPENDING_GOAL_AGGREGATE'):
            risk.conditional_portfolio(document)

    def test_source_bound_workflow_retains_goal_and_replays(self):
        import quant_report
        import research_workflow as workflow
        document = self.request(); raw = quant_report.encoded(document)
        plan = {'schema_version': 1, 'network_mode': 'offline',
                'contract': {'prompt': 'Assess this fictional withdrawal and conditional risk.',
                             'purpose': 'offline test', 'base_currency': 'USD',
                             'horizon_id': 'P8TRADINGD', 'as_of': document['as_of']},
                'sources': [{'id': 'request', 'path': 'request.json', 'sha256': workflow.sha(raw),
                             'format': 'json', 'role': 'supplied_risk_and_spending_request'}],
                'jobs': [{'id': 'risk', 'operation': 'risk.conditional_portfolio',
                          'arguments': {'document': {'$source': {'id': 'request', 'pointer': ''}}}}],
                'claims': [], 'requirements': []}
        artifacts = workflow.build(quant_report.encoded(plan), {'request.json': raw}.__getitem__)
        arguments = json.loads(artifacts['jobs/0000/arguments.json'])
        self.assertEqual(arguments['document'], document)
        result = json.loads(artifacts['result.json'])['jobs'][0]['result']
        self.assertEqual(result['spending_goal']['cash_only_sensitivity']['cash_after_withdrawal'], 350)
        self.assertEqual(result['input_sha256'], risk.digest(document))
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name, content in artifacts.items():
                target = folder / name; target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self.assertEqual(workflow.verify(folder)['status'], 'WORKFLOW_REPLAY_AND_REPORT_MATCH')


class AllocationDiagnostics(unittest.TestCase):
    def test_cap_sensitivity_is_explicit_retains_infeasible_and_preserves_base(self):
        d=allocation();before=copy.deepcopy(d)
        req={'base':d,'constraint_scenarios':[
            {'id':'stock_cap','asset_max_weights':{'A':.3}},
            {'id':'infeasible','constraint_overrides':{'group_gross_caps':{'all':.5}}}]}
        out=portfolio.sensitivity(req)
        self.assertEqual(d,before);self.assertIsNone(out['selected_case'])
        a,b=out['constraint_cases']
        self.assertLessEqual(a['result']['weights']['A'],.3000001)
        self.assertGreater(a['gross_weight_change_from_baseline'],.1)
        self.assertTrue(a['new_registry_attempt_required_for_research_claim'])
        self.assertEqual(a['changed_fields'],[{'field':'assets/A/max_weight','before':.6,'after':.3}])
        self.assertEqual(b['result']['status'],'NO_VERIFIED_FEASIBLE_SOLUTION')
        self.assertIsNone(b['result']['weights'])

    def test_cap_sensitivity_cannot_replace_objective_or_original_net_target(self):
        for field in ['objective','net_target','collateral_reserve']:
            with self.assertRaisesRegex(ValueError,'UNSUPPORTED_CONSTRAINT_OVERRIDE'):
                portfolio.sensitivity({'base':allocation(),'constraint_scenarios':[
                    {'id':'forbidden','constraint_overrides':{field:0}}]})

    def test_redundant_boundaries_and_closed_form(self):
        d=allocation();out=portfolio.construct(d)
        self.assertEqual(out['status'],'RESEARCH_PROPOSAL')
        expected=.9*(1/np.array([.04,.09,.16]))/sum(1/np.array([.04,.09,.16]))
        np.testing.assert_allclose(list(out['weights'].values()),expected,atol=2e-6)
        self.assertEqual(out['independent_optimality_certificate']['status'],'CONDITIONAL_MINIMUM_CERTIFIED')
        self.assertAlmostEqual(sum(out['risk_diagnostics']['variance_contribution_fraction'].values()),1)

    def test_failed_original_solver_has_verified_reduced_retry(self):
        original=portfolio.minimize;calls=[]
        def initial_failure(fun,x,*args,**kwargs):
            calls.append(1)
            if len(calls)==1:return SimpleNamespace(x=np.asarray(x),success=False,message='synthetic redundant-boundary failure')
            return original(fun,x,*args,**kwargs)
        with patch('quant_portfolio.minimize',side_effect=initial_failure):out=portfolio.construct(allocation())
        self.assertEqual(out['status'],'RESEARCH_PROPOSAL')
        self.assertEqual(len(out['solver_attempts']),2)
        self.assertFalse(out['solver_attempts'][1]['constraint_relaxation'])
        self.assertAlmostEqual(out['cash_after_modeled_cost'],.1)

    def test_true_infeasibility_not_repaired_away(self):
        d=allocation();d['constraints']['group_gross_caps']['all']=.5
        out=portfolio.construct(d)
        self.assertEqual(out['status'],'NO_VERIFIED_FEASIBLE_SOLUTION');self.assertIsNone(out['weights'])

    def test_original_volatility_cap_still_enforced(self):
        d=allocation();d['constraints']['volatility_cap']=.001
        out=portfolio.construct(d)
        self.assertEqual(out['status'],'NO_VERIFIED_FEASIBLE_SOLUTION')

    def test_singular_covariance_disclosed(self):
        d=allocation();d['covariance'][0][0]=0
        out=portfolio.construct(d)
        self.assertEqual(out['risk_diagnostics']['covariance_warning'],'SINGULAR_OR_ILL_CONDITIONED')

    def test_sensitivity_retains_all_cases_without_selecting_winner(self):
        d=allocation();other=[[.16,0,0],[0,.09,0],[0,0,.04]]
        req={'base':d,'covariance_scenarios':[{'id':'alternate','covariance':other,'covariance_ids':['A','B','C'],
              'horizon_id':'P1Y','estimated_at':'2026-01-01T00:00:00Z'}]}
        out=portfolio.sensitivity(req)
        self.assertIsNone(out['selected_case']);self.assertGreater(out['cases'][0]['gross_weight_change_from_baseline'],.1)
        req['covariance_scenarios'][0]['estimated_at']='2027-01-01T00:00:00Z'
        with self.assertRaises(ValueError):portfolio.sensitivity(req)


if __name__=='__main__':unittest.main()
