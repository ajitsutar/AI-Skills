"""Numerical identities, economic constraints and adverse-input regression tests."""
import copy
import json
import math
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import investment_ops as ops
import multi_asset_risk as risk
import primary_financial_data as primary
import quant_portfolio as portfolio
import quant_validation as validation
import quant_workbench as workbench
import portfolio_backtest
import manager_monitor

# Deliberately synthetic contact, assembled to keep the export scanner strict.
FICTIONAL_CONTACT = 'contact' + '@' + 'example.invalid'


def allocation():
    return {'assets': [{'id': s, 'issuer': s, 'groups': ['stocks'], 'currency': 'USD',
                       'instrument_model': 'cash_funded_linear', 'eligible': True,
                       'previous_weight': .4, 'min_weight': 0, 'max_weight': .8,
                       'one_way_cost': 0, 'impact_coefficient': 0, 'borrow_cost_per_period': 0,
                       'max_trade_weight': 1} for s in ['A', 'B']],
            'currency': 'USD', 'horizon_id': 'P1Y', 'covariance_horizon_id': 'P1Y',
            'risk_estimated_at': '2026-10-09T20:00:00Z', 'decision_at': '2026-10-10T12:00:00Z',
            'covariance_ids': ['A', 'B'], 'covariance': [[.04, 0], [0, .09]],
            'objective': 'minimum_risk',
            'constraints': {'net_target': .8, 'gross_cap': .8, 'gross_turnover_cap': 1,
                'cash_floor': .1, 'collateral_reserve': 0, 'risk_aversion': 1,
                'issuer_gross_cap': .8, 'group_gross_caps': {'stocks': .8}},
            'scenarios': [{'name': 'selloff', 'returns': [-.3, -.3], 'max_loss_fraction': .3}]}


class QuantValidationTests(unittest.TestCase):
    def test_tail_fractional_boundary(self):
        result = validation.tail_risk([-.4, -.2, .1, .2], .625)
        self.assertAlmostEqual(result['loss_expected_shortfall'], (.4+.5*.2)/1.5)
        self.assertGreaterEqual(result['loss_expected_shortfall'], result['loss_var'])
        self.assertAlmostEqual(result['max_drawdown'], .52)

    def test_first_period_loss_drawdown(self):
        self.assertAlmostEqual(validation.tail_risk([-.2, .3])['max_drawdown'], .2)

    def test_bankruptcy_drawdown(self):
        self.assertEqual(validation.tail_risk([.1, -1, .4])['max_drawdown'], 1)

    def test_loss_below_total_capital_rejected(self):
        with self.assertRaises(ValueError):
            validation.tail_risk([-1.2, .1])

    def test_hac_detects_serial_dependence(self):
        x = np.repeat([-.03, .04, -.02, .03], 20).tolist()
        self.assertGreater(validation.hac_mean(x, 6)['standard_error_hac'],
                           validation.hac_mean(x, 0)['standard_error_hac'])

    def test_holm_known_family(self):
        out = validation.holm({'a': .01, 'b': .04, 'c': .03})['trials']
        self.assertAlmostEqual(out['a']['holm_p'], .03)
        self.assertAlmostEqual(out['b']['holm_p'], .06)
        self.assertFalse(out['b']['reject'])

    def test_sharpe_penalizes_search(self):
        x = [.02, -.01, .01, -.02, .005]*20
        one = validation.sharpe_evidence(x, [.1], 1)
        many = validation.sharpe_evidence(x, [-.2, -.1, 0, .1, .2]*20, 100)
        self.assertLess(many['dsr_iid_diagnostic'], one['dsr_iid_diagnostic'])
        self.assertFalse(many['inference_usable'])

    def test_sharpe_constant_returns_rejected(self):
        with self.assertRaises(ValueError):
            validation.sharpe_evidence([0]*20, [0], 1)

    def test_bootstrap_seed_and_dependence_blocks(self):
        x = [.01, -.02, .03, -.01]*30
        self.assertEqual(validation.block_bootstrap(x, 5, 100, 5), validation.block_bootstrap(x, 5, 100, 5))
        self.assertNotEqual(validation.block_bootstrap(x, 5, 100, 5), validation.block_bootstrap(x, 5, 100, 6))

    def test_purging_keeps_label_horizon_out(self):
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        samples = [{'id': str(i), 'start': (start+timedelta(days=i)).isoformat(),
                    'feature_available_at': (start+timedelta(days=i-1)).isoformat(),
                    'label_end': (start+timedelta(days=i+3)).isoformat()} for i in range(20)]
        out = validation.purged_walk_forward(samples, 4, 2, 86400)
        for fold in out['folds']:
            first = int(fold['test'][0])
            self.assertTrue(all(int(j)+4 < first for j in fold['train']))

    def test_feature_lookahead_rejected(self):
        with self.assertRaises(ValueError):
            validation.purged_walk_forward([{'id': 'a', 'start': '2020-01-01T00:00:00Z',
                'feature_available_at': '2020-01-02T00:00:00Z', 'label_end': '2020-01-03T00:00:00Z'}], 2, 1)

    def test_factor_known_exposure(self):
        start = datetime(2020, 1, 1, tzinfo=timezone.utc)
        x = np.sin(np.arange(50))*.02
        rows = [{'timestamp': (start+timedelta(days=i)).isoformat(), 'excess_return': float(.001+2*f),
                 'factors': {'market': float(f)}} for i, f in enumerate(x)]
        out = validation.factor_attribution(rows, ['market'], 3)
        self.assertAlmostEqual(out['coefficients']['market'], 2)
        self.assertAlmostEqual(out['coefficients']['intercept'], .001)

    def test_factor_collinearity_rejected(self):
        rows = [{'timestamp': f'2020-01-{i:02d}T00:00:00Z', 'excess_return': .01,
                 'factors': {'constant': .01}} for i in range(1, 25)]
        with self.assertRaises(ValueError):
            validation.factor_attribution(rows, ['constant'])


class AllocationTests(unittest.TestCase):
    def test_inverse_variance_closed_form(self):
        result = portfolio.construct(allocation())
        self.assertEqual(result['status'], 'RESEARCH_PROPOSAL')
        self.assertAlmostEqual(result['weights']['A'], .8*.09/.13, places=5)
        self.assertAlmostEqual(result['weights']['B'], .8*.04/.13, places=5)

    def test_issuer_cap_enforced(self):
        doc = allocation()
        doc['constraints']['issuer_gross_cap'] = .4
        self.assertAlmostEqual(portfolio.construct(doc)['weights']['A'], .4, places=6)

    def test_group_infeasibility_not_relaxed(self):
        doc = allocation()
        doc['constraints']['group_gross_caps']['stocks'] = .5
        self.assertEqual(portfolio.construct(doc)['status'], 'NO_VERIFIED_FEASIBLE_SOLUTION')

    def test_capacity_blocks_rebalance(self):
        doc = allocation()
        for a in doc['assets']:
            a['max_trade_weight'] = 0
        out = portfolio.construct(doc)
        self.assertEqual(out['status'], 'RESEARCH_PROPOSAL')
        self.assertAlmostEqual(out['weights']['A'], .4, places=6)

    def test_cash_floor_includes_cost(self):
        doc = allocation()
        doc['constraints']['cash_floor'] = .2
        doc['assets'][0]['eligible'] = False
        doc['assets'][0]['one_way_cost'] = .01
        self.assertEqual(portfolio.construct(doc)['status'], 'NO_VERIFIED_FEASIBLE_SOLUTION')

    def test_psd_checked(self):
        doc = allocation()
        doc['covariance'] = [[.04, .4], [.4, .09]]
        with self.assertRaises(ValueError):
            portfolio.construct(doc)

    def test_units_and_horizon_checked(self):
        doc = allocation()
        doc['covariance_horizon_id'] = 'P1D'
        with self.assertRaises(ValueError):
            portfolio.construct(doc)

    def test_no_vqm_score_as_alpha(self):
        doc = allocation()
        doc['objective'] = 'robust_return'
        doc['calibration'] = {'units': 'vqm_score'}
        with self.assertRaises(ValueError):
            portfolio.construct(doc)

    def test_stress_bound_can_make_infeasible(self):
        doc = allocation()
        doc['scenarios'][0]['max_loss_fraction'] = .1
        self.assertEqual(portfolio.construct(doc)['status'], 'NO_VERIFIED_FEASIBLE_SOLUTION')

    def test_shorting_requires_borrow(self):
        doc = allocation()
        doc['assets'][0]['min_weight'] = -.1
        with self.assertRaises(ValueError):
            portfolio.construct(doc)


class MultiAssetTests(unittest.TestCase):
    def test_standard_option_and_put_call_parity(self):
        args = dict(spot=100, strike=100, years=1, volatility=.2, rate=.05, dividend_yield=0)
        call = risk.european_option(**args, right='call')
        put = risk.european_option(**args, right='put')
        self.assertAlmostEqual(call['price'], 10.45058357, places=7)
        self.assertAlmostEqual(call['price']-put['price'], 100-100*math.exp(-.05))

    def test_option_greeks_finite_difference(self):
        args = dict(spot=100, strike=110, years=.5, volatility=.3, rate=.03, dividend_yield=.01, right='put')
        mid = risk.european_option(**args)
        up = risk.european_option(**{**args, 'spot': 100.01})['price']
        down = risk.european_option(**{**args, 'spot': 99.99})['price']
        self.assertAlmostEqual((up-down)/.02, mid['delta'], places=6)

    def test_american_options_not_mispriced_as_european(self):
        with self.assertRaises(ValueError):
            risk.european_option(100, 100, 1, .2, .05, 0, 'call', 'american')

    def test_expired_option_intrinsic(self):
        self.assertEqual(risk.european_option(110, 100, 0, .2, .05, 0, 'call')['price'], 10)

    def test_zero_coupon_duration(self):
        out = risk.fixed_cashflow_bond([{'years': 5, 'amount': 100}], [.04])
        self.assertAlmostEqual(out['dirty_model_price'], 100*math.exp(-.2))
        self.assertEqual(out['continuous_parallel_duration'], 5)
        self.assertEqual(out['continuous_parallel_convexity'], 25)

    def test_callable_bond_rejected(self):
        with self.assertRaises(ValueError):
            risk.fixed_cashflow_bond([{'years': 5, 'amount': 100}], [.04], callable=True)

    def test_spot_currency_cross_term(self):
        p = [{'id': 'E', 'kind': 'equity', 'quantity': 10, 'multiplier': 1,
              'currency': 'EUR', 'fx_to_base': 1.1, 'mark': 100}]
        s = [{'name': 'down', 'positions': {'E': {'price_return': -.1}}, 'fx_returns': {'EUR': -.1}}]
        result = risk.scenario_book(p, s, 2000, 'USD')['scenarios'][0]
        self.assertAlmostEqual(result['pnl_base'], -209)

    def test_futures_negative_prices_and_notional_not_cash(self):
        p = [{'id': 'F', 'kind': 'future', 'quantity': 2, 'multiplier': 100,
              'currency': 'USD', 'fx_to_base': 1, 'mark': 10}]
        s = [{'name': 'negative', 'positions': {'F': {'price_change': -30}}, 'fx_returns': {}}]
        self.assertEqual(risk.scenario_book(p, s, 10000, 'USD')['scenarios'][0]['pnl_base'], -6000)

    def test_missing_shock_never_zero_filled(self):
        with self.assertRaises(KeyError):
            risk.scenario_book([{'id': 'F', 'kind': 'future', 'quantity': 1, 'multiplier': 1,
                'currency': 'USD', 'fx_to_base': 1, 'mark': 10}], [{'name': 'x', 'positions': {}}], 100, 'USD')


class OperationsTests(unittest.TestCase):
    def test_reserved_fill_does_not_charge_cash_twice(self):
        event = {'id': 'fill', 'currency': 'USD', 'amount': -40, 'reservation_release': 40,
                 'confirmed': True, 'evidence': 'matched order hold', 'available_at': '2026-10-12T09:00:00Z'}
        out = ops.cash_ladder('2026-10-09T20:00:00Z', {'USD': 100}, {'USD': 40}, [event], {'USD': 50})
        self.assertEqual(out['ending_available']['USD'], 60)
        self.assertEqual(out['remaining_reservations']['USD'], 0)
        self.assertEqual(out['status'], 'PROJECTED_COVERED')

    def test_reservation_cannot_be_released_twice(self):
        events = [{'id': str(i), 'currency': 'USD', 'amount': -40, 'reservation_release': 40,
                   'confirmed': True, 'evidence': 'hold', 'available_at': '2026-10-12T09:00:00Z'} for i in range(2)]
        with self.assertRaisesRegex(ValueError, 'RESERVATION_ALREADY'):
            ops.cash_ladder('2026-10-09T20:00:00Z', {'USD': 100}, {'USD': 40}, events, {'USD': 0})

    def test_credit_cannot_release_reservation(self):
        event = {'id': 'sale', 'currency': 'USD', 'amount': 40, 'reservation_release': 40,
                 'confirmed': True, 'evidence': 'sale', 'available_at': '2026-10-12T09:00:00Z'}
        with self.assertRaisesRegex(ValueError, 'MATCHING_DEBIT'):
            ops.cash_ladder('2026-10-09T20:00:00Z', {'USD': 100}, {'USD': 40}, [event], {'USD': 0})

    def test_no_unsettled_or_unconfirmed_credit_spending(self):
        out = ops.cash_ladder('2026-10-09T20:00:00Z', {'USD': 100}, {'USD': 20},
          [{'id': 'sale', 'currency': 'USD', 'amount': 200, 'confirmed': False, 'evidence': 'planned', 'available_at': '2026-10-12T09:00:00Z'},
           {'id': 'buy', 'currency': 'USD', 'amount': -100, 'confirmed': False, 'evidence': 'planned debit', 'available_at': '2026-10-12T10:00:00Z'}], {'USD': 10})
        self.assertEqual(out['status'], 'SHORTFALL')
        self.assertEqual(out['ignored_unconfirmed_credits'], ['sale'])

    def test_cash_equal_time_conservative_order(self):
        events = [{'id': 'a', 'currency': 'USD', 'amount': 100, 'confirmed': True, 'evidence': 'receipt', 'available_at': '2026-10-12T09:00:00Z'},
                  {'id': 'b', 'currency': 'USD', 'amount': -100, 'confirmed': True, 'evidence': 'liability', 'available_at': '2026-10-12T09:00:00Z'}]
        out = ops.cash_ladder('2026-10-09T20:00:00Z', {'USD': 50}, {'USD': 0}, events, {'USD': 0})
        self.assertEqual(out['timeline'][0]['id'], 'b')
        self.assertEqual(out['status'], 'SHORTFALL')

    def test_buy_shortfall_decomposition(self):
        out = ops.implementation_shortfall('buy', 100, 10, 10.1, 11,
                                         [{'id': 'a', 'quantity': 80, 'price': 10.2}], 1)
        self.assertAlmostEqual(out['total_shortfall'], 37)

    def test_sell_shortfall_sign(self):
        out = ops.implementation_shortfall('sell', 10, 100, 99, 95, [{'id': 'a', 'quantity': 10, 'price': 98}], 0)
        self.assertEqual(out['total_shortfall'], 20)

    def test_overfill_rejected(self):
        with self.assertRaises(ValueError):
            ops.implementation_shortfall('buy', 1, 10, 10, 10, [{'id': 'a', 'quantity': 2, 'price': 10}])

    def test_xirr_known_one_year(self):
        out = ops.xirr([{'at': '2025-01-01T00:00:00Z', 'amount': -100}, {'at': '2026-01-01T00:00:00Z', 'amount': 110}])
        self.assertAlmostEqual(out['annual_xirr'], .1, places=10)

    def test_xirr_ambiguous_roots_not_selected(self):
        out = ops.xirr([{'at': '2024-01-01T00:00:00Z', 'amount': -100},
                        {'at': '2025-01-01T00:00:00Z', 'amount': 230}, {'at': '2026-01-01T00:00:00Z', 'amount': -132}])
        self.assertIsNone(out['annual_xirr'])

    def test_brinson_reconciles(self):
        out = ops.brinson([{'name': 'a', 'portfolio_weight': .7, 'benchmark_weight': .5, 'portfolio_return': .12, 'benchmark_return': .1},
                          {'name': 'b', 'portfolio_weight': .3, 'benchmark_weight': .5, 'portfolio_return': .03, 'benchmark_return': .05}])
        self.assertAlmostEqual(out['reconciliation_error'], 0)


class PrimaryDataTests(unittest.TestCase):
    def fixture(self):
        return {'cik': 123, 'facts': {'us-gaap': {'Assets': {'units': {'USD': [
            {'filed': '2026-08-01', 'end': '2026-06-30', 'val': 100, 'accn': '0000000123-26-000001', 'form': '10-Q'},
            {'filed': '2026-10-10', 'end': '2026-06-30', 'val': 90, 'accn': '0000000123-26-000002', 'form': '10-Q/A'}]}}}}}

    def test_future_amendment_not_leaked(self):
        out = primary.extract(self.fixture(), '123', '2026-10-09T20:00:00Z',
                              [{'name': 'assets', 'namespace': 'us-gaap', 'tag': 'Assets', 'unit': 'USD'}])
        self.assertEqual([r['value'] for r in out['facts']], [100])
        self.assertFalse(out['filing_eligibility_established'])

    def test_same_day_date_only_withheld(self):
        out = primary.extract(self.fixture(), '123', '2026-08-01T20:00:00Z',
                              [{'name': 'assets', 'namespace': 'us-gaap', 'tag': 'Assets', 'unit': 'USD'}])
        self.assertFalse(out['facts'])

    def test_known_amendments_retained_for_review(self):
        out = primary.extract(self.fixture(), '123', '2026-10-11T20:00:00Z',
                              [{'name': 'assets', 'namespace': 'us-gaap', 'tag': 'Assets', 'unit': 'USD'}])
        self.assertEqual(len(out['facts']), 2)

    def test_entity_mismatch(self):
        with self.assertRaises(ValueError):
            primary.extract(self.fixture(), '124', '2026-10-09T20:00:00Z', [])

    def test_sec_fetch_denial_not_retried_or_bypassed(self):
        session = Mock()
        session.get.return_value.status_code = 403
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                primary.fetch('123', 'Research '+FICTIONAL_CONTACT, Path(d)/'fetch', session)
        self.assertEqual(session.get.call_count, 1)

    def test_sec_fetch_retains_bytes_no_contact(self):
        session = Mock()
        response = session.get.return_value
        response.status_code = 200
        response.content = b'{"cik":123}'
        response.json.return_value = {'cik': 123}
        with tempfile.TemporaryDirectory() as d:
            out = primary.fetch('123', 'Research '+FICTIONAL_CONTACT, Path(d)/'fetch', session)
            self.assertNotIn(FICTIONAL_CONTACT, json.dumps(out))
            self.assertEqual((Path(d)/'fetch/companyfacts.json').read_bytes(), response.content)


class ReplayTests(unittest.TestCase):
    def test_retained_campaign_survives_json_roundtrip_and_baseline_operations(self):
        doc = json.loads((ROOT/'examples/fictional-quant-campaign.json').read_text())
        bundle = json.loads(json.dumps(workbench.freeze(doc), allow_nan=False))
        self.assertEqual(workbench.verify(bundle)['jobs_verified'], len(doc['jobs']))
        # This retained campaign predates the source-aware adapters. Keep its
        # numerical inputs unchanged and its baseline coverage assertion exact.
        source_operations = {'planning.source_roles', 'planning.source_projection',
                             'planning.source_alternatives', 'planning.settlement_transfer_sweep',
                             'planning.recommendation_context', 'evidence.price_comparison',
                             'planning.source_budget_sizing', 'planning.employer_diversification_baseline',
                             'financial.equity_cash_comparison', 'planning.source_allocation_context'}
        self.assertTrue(source_operations <= set(workbench.OPERATIONS))
        self.assertEqual({j['operation'] for j in doc['jobs']},
                         set(workbench.OPERATIONS) - source_operations - set(workbench.ANALYSIS_OPERATIONS) - set(workbench.MULTIASSET_OPERATIONS))

    def fixture(self):
        return {'schema_version': 1, 'contract': {'prompt': 'Fictional risk review', 'purpose': 'compatibility',
            'base_currency': 'USD', 'horizon_id': 'P1Y', 'as_of': '2026-10-11T00:00:00Z'},
            'jobs': [{'id': 'tail', 'operation': 'validation.tail', 'inputs': {'returns': [-.1, .2, .05]}}]}

    def test_frozen_replay(self):
        bundle = workbench.freeze(self.fixture())
        self.assertEqual(workbench.verify(bundle)['status'], 'REPLAY_MATCH')
        self.assertEqual(workbench.compare(bundle, copy.deepcopy(bundle))['status'], 'MATCH')

    def test_modified_result_rejected(self):
        bundle = workbench.freeze(self.fixture())
        bundle['result']['results'][0]['result']['total_return'] = 999
        with self.assertRaises(ValueError):
            workbench.verify(bundle)

    def test_arbitrary_operation_not_executed(self):
        doc = self.fixture()
        doc['jobs'][0]['operation'] = 'os.system'
        with self.assertRaises(ValueError):
            workbench.run(doc)

    def test_nan_cannot_get_pass(self):
        doc = self.fixture()
        doc['jobs'][0]['inputs']['returns'] = [float('nan')]
        with self.assertRaises(ValueError):
            workbench.run(doc)

    def test_expected_rejection_is_replayable(self):
        doc = self.fixture()
        doc['jobs'][0]['inputs']['returns'] = [-2]
        bundle = workbench.freeze(doc)
        self.assertEqual(bundle['result']['results'][0]['status'], 'REJECTED_INPUT')
        self.assertEqual(workbench.verify(bundle)['status'], 'REPLAY_MATCH')

    def test_future_cash_snapshot_rejected(self):
        doc = self.fixture()
        doc['jobs'] = [{'id': 'cash', 'operation': 'ops.cash_ladder', 'inputs': {
            'as_of': '2027-01-01T00:00:00Z', 'settled_balances': {'USD': 100},
            'reservations': {'USD': 0}, 'events': [], 'floors': {'USD': 0}}}]
        out = workbench.run(doc)['results'][0]
        self.assertEqual(out['status'], 'REJECTED_INPUT')
        self.assertIn('FUTURE_STATE_SNAPSHOT', out['reason'])

    def test_numerical_failure_is_explicit_and_other_jobs_continue(self):
        doc = self.fixture()
        doc['jobs'].append({'id': 'other', 'operation': 'validation.holm',
                            'inputs': {'p_values': {'A': .01}}})
        failure = Mock(side_effect=np.linalg.LinAlgError('SVD did not converge'))
        with patch.dict(workbench.OPERATIONS, {'validation.tail': failure}):
            out = workbench.run(doc)
        self.assertEqual(out['results'][0]['status'], 'CALCULATION_FAILED')
        self.assertNotIn('result', out['results'][0])
        self.assertEqual(out['results'][1]['status'], 'COMPUTED')
        self.assertFalse(out['execution_authorized'])


class ManagerTests(unittest.TestCase):
    def backtest(self):
        return {'symbols': ['A'], 'initial_equity': 100, 'initial_weights': [.5],
          'cash_floor': .1, 'return_basis': 'total_return_decimal',
          'universe_evidence': 'FICTIONAL', 'corporate_action_evidence': 'FICTIONAL',
          'periods': [{'start': '2020-01-02T00:00:00Z', 'end': '2020-01-03T00:00:00Z',
            'returns': {'A': .1}, 'tradable': {'A': True}, 'cash_return': .01, 'benchmark_return': .05,
            'decision': {'known_at': '2020-01-01T23:00:00Z', 'weights': [.8], 'evidence_hash': 'fictional'},
            'one_way_costs': [.01], 'impact_coefficients': [0], 'max_trade_values': [100]}]}

    def test_portfolio_cash_and_cost_accounting(self):
        out = portfolio_backtest.simulate(self.backtest())
        self.assertAlmostEqual(out['costs_paid'], .3)
        self.assertAlmostEqual(out['curve'][0]['equity'], 80*1.1+19.7*1.01)
        self.assertFalse(out['validated_for_live'])

    def test_portfolio_same_interval_signal_rejected(self):
        doc = self.backtest()
        doc['periods'][0]['decision']['known_at'] = doc['periods'][0]['start']
        with self.assertRaises(ValueError):
            portfolio_backtest.simulate(doc)

    def test_portfolio_halt_cannot_fill(self):
        doc = self.backtest()
        doc['periods'][0]['tradable']['A'] = False
        with self.assertRaises(ValueError):
            portfolio_backtest.simulate(doc)

    def test_portfolio_capacity_not_ignored(self):
        doc = self.backtest()
        doc['periods'][0]['max_trade_values'] = [1]
        with self.assertRaises(ValueError):
            portfolio_backtest.simulate(doc)

    def test_portfolio_missing_return_no_survivorship_substitution(self):
        doc = self.backtest()
        doc['periods'][0]['returns'] = {}
        with self.assertRaises(ValueError):
            portfolio_backtest.simulate(doc)

    def test_monitor_stale_reconciliation_and_volatility(self):
        out = manager_monitor.assess('2026-10-10T00:00:00Z', '2026-10-09T00:00:00Z',
            [.1, -.1]*30, 252, .2, .5, 40, 2,
            {'minimum_observations': 30, 'max_age_seconds': 60, 'minimum_coverage': .9,
             'max_realized_to_forecast_volatility': 1.5, 'max_cost_bps': 20, 'max_reconciliation_difference': .01})
        self.assertEqual(out['status'], 'ADVISORY_RISK_ALERT')
        self.assertFalse(out['enforces_execution'])
        self.assertEqual(len(out['reasons']), 5)
        self.assertFalse(out['automatic_retuning_allowed'])

    def test_monitor_cannot_pass_tiny_sample(self):
        out = manager_monitor.assess('2026-10-10T00:00:00Z', '2026-10-10T00:00:00Z',
            [.001], 252, .2, 1, 0, 0,
            {'minimum_observations': 30, 'max_age_seconds': 60, 'minimum_coverage': .9,
             'max_realized_to_forecast_volatility': 1.5, 'max_cost_bps': 20, 'max_reconciliation_difference': .01})
        self.assertIn('INSUFFICIENT_MONITOR_HISTORY', out['reasons'])

    def test_recomputed_promotion_and_missing_trial(self):
        t0 = datetime(2020, 1, 1, tzinfo=timezone.utc)
        evidence = {'units': 'net_excess_return_decimal', 'all_variants_disclosed': True,
           'trial_registry_sha256': 'f'*64, 'input_data_hashes': ['a'*64],
           'parameters_frozen_at': '2019-12-31T00:00:00Z', 'test_start': t0.isoformat(),
           'test_end': '2020-05-01T00:00:00Z', 'selected_trial': 'a',
           'trials': [{'id': 'a', 'observations': [{'timestamp': (t0+timedelta(days=i)).isoformat(),
                    'return': .01 if i%2 else .02} for i in range(100)]}]}
        criteria = {'minimum_observations': 60, 'hac_lags': 2, 'max_holm_p': .05,
                    'bootstrap_block_length': 5, 'bootstrap_replications': 100, 'bootstrap_seed': 42}
        self.assertTrue(validation.promotion_evidence(evidence, criteria)['quantitative_criteria_passed'])
        evidence['all_variants_disclosed'] = False
        with self.assertRaises(ValueError):
            validation.promotion_evidence(evidence, criteria)


if __name__ == '__main__':
    unittest.main()
