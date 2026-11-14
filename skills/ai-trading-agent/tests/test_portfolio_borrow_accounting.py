"""Synthetic holding-period cost identities; no market or broker connections."""
import copy
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import quant_portfolio as portfolio
import quant_workbench as workbench
import report_facts


def allocation(objective='minimum_risk', cap=.02, previous=0, borrow=.02):
    return {
        'assets': [{'id': 'S', 'issuer': 'S', 'groups': [], 'currency': 'USD',
                    'instrument_model': 'cash_funded_linear', 'eligible': True,
                    'previous_weight': previous, 'min_weight': -.5, 'max_weight': 0,
                    'one_way_cost': 0, 'impact_coefficient': 0,
                    'borrow_cost_per_period': borrow, 'max_trade_weight': 1,
                    'borrow_available': True, 'borrow_evidence': 'synthetic period declaration',
                    'expected_return': -.04, 'return_uncertainty': .001}],
        'currency': 'USD', 'horizon_id': 'P1M', 'covariance_horizon_id': 'P1M',
        'risk_estimated_at': '2026-01-01T00:00:00Z', 'decision_at': '2026-01-02T00:00:00Z',
        'covariance_ids': ['S'], 'covariance': [[.01]], 'objective': objective,
        'calibration': {'units': 'holding_period_total_return_decimal', 'horizon_id': 'P1M',
                        'currency': 'USD', 'frozen_at': '2025-01-01T00:00:00Z',
                        'test_start': '2025-02-01T00:00:00Z', 'test_end': '2025-12-01T00:00:00Z',
                        'evidence': 'synthetic', 'all_trials_evidence': 'synthetic'},
        'constraints': {'net_target': -.5, 'gross_cap': .5, 'gross_turnover_cap': 1,
                        'cash_floor': 0, 'collateral_reserve': .1, 'risk_aversion': 1,
                        'issuer_gross_cap': .5, 'group_gross_caps': {}},
        'scenarios': [{'name': 'flat', 'returns': [0], 'max_loss_fraction': cap}]}


def job(document):
    return {'schema_version': 1, 'contract': {'prompt': 'Synthetic period cost reconciliation',
            'purpose': 'software regression', 'base_currency': 'USD', 'horizon_id': 'P1M',
            'as_of': '2026-01-03T00:00:00Z'}, 'jobs': [
            {'id': 'allocation', 'operation': 'portfolio.construct', 'inputs': {'document': document}}]}


class PeriodBorrowAccountingTests(unittest.TestCase):
    def test_moderate_borrow_breaches_flat_loss_cap_both_objectives(self):
        for objective in ('minimum_risk', 'robust_return'):
            with self.subTest(objective=objective):
                result = portfolio.construct(allocation(objective, cap=.005))
                self.assertEqual(result['status'], 'NO_VERIFIED_FEASIBLE_SOLUTION')
                self.assertIsNone(result['weights'])
                self.assertGreaterEqual(result['max_violation'], .005-1e-7)

    def test_success_flag_cannot_bypass_actual_borrow_constraint(self):
        # Audit real weights independently of both the solver flag and its auxiliaries.
        fake = SimpleNamespace(x=np.array([-.5, 0, 0]), success=True, message='synthetic')
        with patch.object(portfolio, 'minimize', return_value=fake):
            result = portfolio.construct(allocation(cap=.005))
        self.assertEqual(result['status'], 'NO_VERIFIED_FEASIBLE_SOLUTION')
        self.assertAlmostEqual(result['max_violation'], .005)

    def test_loose_cap_net_cost_cash_and_slack_identity_both_objectives(self):
        for objective in ('minimum_risk', 'robust_return'):
            with self.subTest(objective=objective):
                document = allocation(objective)
                original = copy.deepcopy(document)
                result = portfolio.construct(document)
                self.assertEqual(document, original)
                self.assertEqual(result['status'], 'RESEARCH_PROPOSAL')
                self.assertAlmostEqual(result['holding_period_borrow_cost_fraction'], .01)
                self.assertEqual(result['entry_transaction_cost_fraction'], 0)
                self.assertAlmostEqual(result['estimated_cost_fraction'], .01)
                self.assertAlmostEqual(result['scenario_pnl_fraction']['flat'], -.01)
                self.assertAlmostEqual(result['constraint_slacks']['stress:flat'], .01)
                self.assertAlmostEqual(result['cash_after_entry_cost'], 1.5)
                self.assertAlmostEqual(result['cash_after_modeled_cost'], 1.5)
                self.assertAlmostEqual(result['free_cash_after_collateral_reserve'], 1.4)
                self.assertAlmostEqual(result['cash_after_period_borrow_reserve'], 1.49)
                self.assertAlmostEqual(result['free_cash_after_collateral_and_borrow_reserve'], 1.39)
                self.assertAlmostEqual(result['constraint_slacks']['cash_floor_after_borrow_reserve'], 1.39)
                if objective == 'robust_return':
                    self.assertAlmostEqual(result['modeled_return'], .02)
                    self.assertAlmostEqual(result['modeled_net_return'], .01)
                else:
                    self.assertIsNone(result['modeled_net_return'])

    def test_existing_short_pays_borrow_without_turnover(self):
        document = allocation(previous=-.5)
        document['assets'][0].update(one_way_cost=.1, impact_coefficient=.1, max_trade_weight=0)
        result = portfolio.construct(document)
        self.assertEqual(result['status'], 'RESEARCH_PROPOSAL')
        self.assertEqual(result['gross_turnover'], 0)
        self.assertEqual(result['entry_transaction_cost_fraction'], 0)
        self.assertAlmostEqual(result['scenario_pnl_fraction']['flat'], -.01)

    def test_one_way_and_impact_costs_preserve_their_formula(self):
        document = allocation('robust_return', cap=.1)
        document['assets'][0].update(one_way_cost=.004, impact_coefficient=.006)
        result = portfolio.construct(document)
        entry = .004*.5 + .006*.5**1.5
        self.assertEqual(result['status'], 'RESEARCH_PROPOSAL')
        self.assertAlmostEqual(result['entry_transaction_cost_fraction'], entry)
        self.assertAlmostEqual(result['estimated_cost_fraction'], entry+.01)
        self.assertAlmostEqual(result['cash_after_entry_cost'], 1.5-entry)
        self.assertAlmostEqual(result['scenario_pnl_fraction']['flat'], -entry-.01)
        self.assertAlmostEqual(result['modeled_net_return'], .02-entry-.01)

    def test_zero_borrow_and_all_long_controls(self):
        zero = portfolio.construct(allocation(cap=.005, borrow=0))
        self.assertEqual(zero['status'], 'RESEARCH_PROPOSAL')
        self.assertEqual(zero['scenario_pnl_fraction']['flat'], 0)
        document = allocation()
        document['assets'][0].update(min_weight=0, max_weight=.5)
        document['constraints'].update(net_target=.5, collateral_reserve=0)
        result = portfolio.construct(document)
        self.assertEqual(result['status'], 'RESEARCH_PROPOSAL')
        self.assertEqual(result['holding_period_borrow_cost_fraction'], 0)
        self.assertAlmostEqual(result['cash_after_entry_cost'], .5)

    def test_mixed_exposure_costs_follow_short_units_and_actual_trades(self):
        for objective in ('minimum_risk', 'robust_return'):
            document = allocation(objective, cap=.2, previous=-.5)
            document['assets'][0].update(max_trade_weight=0, one_way_cost=.1)
            long_asset = dict(document['assets'][0], id='L', issuer='L', previous_weight=.4,
                              min_weight=0, max_weight=.5, borrow_cost_per_period=.5,
                              expected_return=.1, one_way_cost=.2)
            document['assets'].append(long_asset)
            document['covariance_ids'] = ['S', 'L']
            document['covariance'] = [[.01, 0], [0, .04]]
            document['constraints'].update(net_target=-.1, gross_cap=1)
            document['scenarios'][0]['returns'] = [.1, -.2]
            result = portfolio.construct(document)
            self.assertEqual(result['status'], 'RESEARCH_PROPOSAL')
            self.assertAlmostEqual(result['holding_period_borrow_cost_fraction'], .01)
            self.assertEqual(result['entry_transaction_cost_fraction'], 0)
            self.assertAlmostEqual(result['scenario_pnl_fraction']['flat'], -.14)
            self.assertAlmostEqual(result['constraint_slacks']['stress:flat'], .06)
            if objective == 'robust_return':
                self.assertAlmostEqual(result['modeled_net_return'], .05)

    def test_cash_floor_reserves_borrow_but_reports_entry_cash_separately(self):
        document = allocation()
        document['constraints'].update(cash_floor=.2, collateral_reserve=1.295)
        self.assertEqual(portfolio.construct(document)['status'], 'NO_VERIFIED_FEASIBLE_SOLUTION')
        document['constraints']['collateral_reserve'] = 1.28
        result = portfolio.construct(document)
        self.assertEqual(result['status'], 'RESEARCH_PROPOSAL')
        self.assertAlmostEqual(result['constraint_slacks']['cash_floor'], .02)
        self.assertAlmostEqual(result['constraint_slacks']['cash_floor_after_borrow_reserve'], .01)

    def test_workbench_freeze_and_report_facts_retain_net_values(self):
        bundle = workbench.freeze(job(allocation('robust_return')))
        self.assertEqual(workbench.verify(bundle)['status'], 'REPLAY_MATCH')
        result = bundle['result']['results'][0]['result']
        self.assertAlmostEqual(result['modeled_net_return'], .01)
        raw = json.dumps(bundle).encode()
        projection = report_facts.project(raw, 'quant')
        values = {row['source']['pointer']: row['value'] for row in projection['facts']}
        for field in ('estimated_cost_fraction', 'holding_period_borrow_cost_fraction',
                      'modeled_net_return', 'free_cash_after_collateral_and_borrow_reserve'):
            self.assertEqual(values['/result/results/0/result/'+field], result[field])


if __name__ == '__main__':
    unittest.main()
