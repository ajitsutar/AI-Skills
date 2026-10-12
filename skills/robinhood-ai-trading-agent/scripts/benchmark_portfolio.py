"""Benchmark-aware long-only allocation from externally calibrated alpha.

Offline research proposal only. Validates numeric feasibility, not the truth of
calibration evidence. Dimensionless VQM scores are explicitly not accepted alpha.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from deterministic_rank import digest
from price_audit import timestamp


def require(condition, message):
    if not condition:
        raise ValueError(message)


def construct(document):
    calibration = document.get('calibration')
    if not calibration:
        return {'status': 'CALIBRATION_REQUIRED', 'weights': None,
                'strong_buy_available': False, 'execution_authorized': False,
                'reason': 'The shipped VQM profile is uncalibrated; do not turn ranks into return forecasts'}
    require(calibration.get('units') == 'holding_period_excess_total_return_decimal', 'ALPHA_UNITS')
    for field in ('profile_sha256', 'horizon_id', 'benchmark_id', 'management_mode'):
        require(calibration.get(field) and calibration[field] == document.get(field), 'CALIBRATION_MISMATCH:' + field)
    require(calibration['management_mode'] in {'fixed_hold', 'monthly_rebalanced', 'rolling_review'}, 'MANAGEMENT_MODE')
    require(timestamp(calibration['frozen_at']) < timestamp(calibration['test_start'])
            < timestamp(calibration['test_end']) <= timestamp(document['as_of']), 'CALIBRATION_CHRONOLOGY')
    require(isinstance(calibration.get('evidence'), list) and calibration['evidence']
            and all(isinstance(x, str) and x.strip() for x in calibration['evidence']), 'CALIBRATION_EVIDENCE')
    assets = document['assets']
    require(assets and len({a['symbol'] for a in assets}) == len(assets), 'ASSET_IDENTIFIERS')
    symbols = [a['symbol'] for a in assets]
    require(document.get('covariance_symbols') == symbols, 'COVARIANCE_ORDER')
    require(document.get('covariance_horizon_id') == document['horizon_id'], 'COVARIANCE_HORIZON')
    def vector(key):
        require(all(type(a[key]) in (int, float) for a in assets), 'NUMERIC_ASSET_FIELD:' + key)
        arr = np.array([a[key] for a in assets], dtype=float)
        require(np.isfinite(arr).all(), 'NONFINITE:' + key)
        return arr
    alpha, benchmark, previous, costs, upper = [vector(k) for k in
        ('alpha', 'benchmark_weight', 'previous_weight', 'one_way_cost', 'max_weight')]
    require(np.all(benchmark >= 0) and np.all(previous >= 0) and np.all(costs >= 0)
            and np.all(upper >= 0) and np.all(upper <= 1), 'INVALID_WEIGHT_OR_COST')
    require(abs(benchmark.sum() - 1) < 1e-9 and abs(previous.sum() - 1) < 1e-9, 'WEIGHTS_MUST_SUM_TO_ONE')
    for i, asset in enumerate(assets):
        require(type(asset.get('eligible')) is bool, 'ELIGIBILITY_REQUIRED')
        if not asset['eligible']:
            upper[i] = 0
        for field in ('issuer', 'sector'):
            require(isinstance(asset.get(field), str) and asset[field], 'EXPOSURE_MAPPING_REQUIRED')
        require(isinstance(asset.get('themes'), list) and all(isinstance(t, str) and t for t in asset['themes'])
                and len(set(asset['themes'])) == len(asset['themes']), 'THEME_MAPPING_REQUIRED')
    sigma = np.array(document['covariance'], dtype=float)
    n = len(assets)
    require(sigma.shape == (n, n) and np.isfinite(sigma).all()
            and np.allclose(sigma, sigma.T, rtol=0, atol=1e-12), 'COVARIANCE_INVALID')
    require(np.linalg.eigvalsh(sigma).min() >= -1e-12, 'COVARIANCE_NOT_PSD')
    policy = document['constraints']
    for key in ('risk_aversion', 'issuer_cap', 'sector_active_cap', 'theme_cap', 'turnover_cap'):
        require(type(policy.get(key)) in (int, float) and np.isfinite(policy[key]) and policy[key] >= 0, 'INVALID_CONSTRAINT:' + key)
    require(policy['risk_aversion'] > 0, 'RISK_AVERSION_MUST_BE_POSITIVE')
    require(all(policy[k] <= 1 for k in ('issuer_cap', 'sector_active_cap', 'theme_cap', 'turnover_cap')), 'CONSTRAINT_RANGE')
    # Explicit turnover auxiliaries avoid a nondifferentiable absolute-value objective.
    def objective(x):
        active = x[:n] - benchmark
        return -active @ alpha + policy['risk_aversion'] * (active @ sigma @ active) / 2 + costs @ x[n:]
    constraints = [{'type': 'eq', 'fun': lambda x: x[:n].sum() - 1},
        {'type': 'ineq', 'fun': lambda x: x[n:] - (x[:n] - previous)},
        {'type': 'ineq', 'fun': lambda x: x[n:] + (x[:n] - previous)},
        {'type': 'ineq', 'fun': lambda x: policy['turnover_cap'] - x[n:].sum() / 2}]
    for field in ('issuer', 'sector'):
        for group in sorted({a[field] for a in assets}):
            mask = np.array([a[field] == group for a in assets], dtype=float)
            if field == 'issuer':
                constraints.append({'type': 'ineq', 'fun': lambda x, m=mask: policy['issuer_cap'] - m @ x[:n]})
            else:
                constraints.extend([{'type': 'ineq', 'fun': lambda x, m=mask, sign=sign:
                    policy['sector_active_cap'] - sign * (m @ (x[:n] - benchmark))} for sign in (-1, 1)])
    for theme in sorted({t for a in assets for t in a['themes']}):
        mask = np.array([theme in a['themes'] for a in assets], dtype=float)
        constraints.append({'type': 'ineq', 'fun': lambda x, m=mask: policy['theme_cap'] - m @ x[:n]})
    start = np.minimum(previous, upper)
    result = minimize(objective, np.r_[start, np.abs(start - previous)], method='SLSQP',
        bounds=[(0, float(v)) for v in upper] + [(0, 1)] * n, constraints=constraints,
        options={'maxiter': 2000, 'ftol': 1e-12})
    violations = [float(np.max(np.abs(c['fun'](result.x)))) if c['type'] == 'eq'
                  else max(0., float(-np.min(c['fun'](result.x)))) for c in constraints]
    if not result.success or max(violations) > 1e-7:
        return {'status': 'NO_VERIFIED_FEASIBLE_SOLUTION', 'weights': None,
                'solver_message': str(result.message), 'max_constraint_violation': max(violations),
                'execution_authorized': False, 'strong_buy_available': False}
    weights = result.x[:n]
    turnover = np.abs(weights - previous)
    return {'status': 'RESEARCH_PROPOSAL', 'weights': dict(zip(symbols, weights.tolist())),
            'active_weights': dict(zip(symbols, (weights - benchmark).tolist())),
            'modeled_active_return': float((weights - benchmark) @ alpha),
            'modeled_cost': float(costs @ turnover), 'one_way_turnover': float(turnover.sum() / 2),
            'tracking_volatility': float(np.sqrt(max(0., (weights - benchmark) @ sigma @ (weights - benchmark)))),
            'input_sha256': digest(document), 'max_constraint_violation': max(violations),
            'calibration_evidence_status': 'DECLARED_NOT_VERIFIED',
            'strong_buy_available': False, 'execution_authorized': False,
            'limitations': 'No shares, orders, tax-lot optimization or live authority. Review liquidity, observed whole/fractional quantity increments and broker risk gates separately. Solver weights can differ at floating-point tolerance across platforms.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    result = construct(json.loads(args.input.read_text(encoding='utf-8-sig')))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result['status'] != 'RESEARCH_PROPOSAL':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
