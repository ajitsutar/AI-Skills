"""Cost-aware constrained research allocation for linear, cash-funded instruments.

No orders, leverage permission, alpha calibration or nonlinear derivative sizing.
The fixed public stock-discovery ranking is not changed by this optional allocator.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize

from quant_common import cli, covariance, digest, require, scalar, timestamp, vector


def construct(document):
    assets = document['assets']
    n = len(assets)
    require(0 < n <= 500 and len({a['id'] for a in assets}) == n, 'ASSET_IDS')
    ids = [a['id'] for a in assets]
    require(document['covariance_ids'] == ids, 'COVARIANCE_ORDER')
    require(document['horizon_id'] == document['covariance_horizon_id'], 'COVARIANCE_HORIZON')
    require(document['currency'] and document['horizon_id'], 'CURRENCY_AND_HORIZON')
    require(timestamp(document['risk_estimated_at']) <= timestamp(document['decision_at']), 'FUTURE_RISK_ESTIMATE')
    for a in assets:
        require(a['instrument_model'] == 'cash_funded_linear', 'NONLINEAR_OR_MARGINED_INSTRUMENT_REQUIRES_SEPARATE_MODEL')
        require(a['currency'] == document['currency'], 'BASE_CURRENCY_RETURNS_REQUIRED')
        require(a.get('issuer') and isinstance(a.get('groups'), list), 'EXPOSURE_MAPPING_REQUIRED')
        require(type(a.get('eligible')) is bool, 'ELIGIBILITY_REQUIRED')
    def v(key, minimum=None):
        return vector([a[key] for a in assets], key, n, minimum)
    previous, low, high = v('previous_weight'), v('min_weight'), v('max_weight')
    costs, impact, borrow, capacity = [v(key, 0) for key in
        ('one_way_cost', 'impact_coefficient', 'borrow_cost_per_period', 'max_trade_weight')]
    require(np.all(low <= high), 'REVERSED_WEIGHT_BOUNDS')
    require(np.all(low <= 0) and np.all(high >= 0), 'BOUNDS_MUST_ALLOW_EXIT')
    require(np.all(capacity <= 2), 'TRADE_CAPACITY_RANGE')
    for i, a in enumerate(assets):
        if not a['eligible']:
            low[i] = high[i] = 0
        if low[i] < 0:
            require(a.get('borrow_available') is True and a.get('borrow_evidence'), 'SHORT_BORROW_EVIDENCE_REQUIRED')
    sigma = covariance(document['covariance'], n)
    p = document['constraints']
    net = scalar(p['net_target'], 'net_target', -2, 1)
    gross = scalar(p['gross_cap'], 'gross_cap', 0, 4)
    turnover = scalar(p['gross_turnover_cap'], 'gross_turnover_cap', 0, 4)
    cash_floor = scalar(p['cash_floor'], 'cash_floor', 0, 1)
    reserve = scalar(p['collateral_reserve'], 'collateral_reserve', 0, 2)
    risk_aversion = scalar(p['risk_aversion'], 'risk_aversion', 1e-12)
    issuer_cap = scalar(p['issuer_gross_cap'], 'issuer_gross_cap', 0, 4)
    require(gross >= abs(net), 'GROSS_BELOW_ABSOLUTE_NET')
    require(not np.any(low < 0) or reserve > 0, 'SHORTS_REQUIRE_EXPLICIT_COLLATERAL_RESERVE')
    alpha = np.zeros(n)
    uncertainty = np.zeros(n)
    objective_name = document['objective']
    require(objective_name in {'minimum_risk', 'robust_return'}, 'UNKNOWN_OBJECTIVE')
    if objective_name == 'robust_return':
        calibration = document['calibration']
        require(calibration['units'] == 'holding_period_total_return_decimal', 'RETURN_UNITS')
        require(calibration['horizon_id'] == document['horizon_id'] and
                calibration['currency'] == document['currency'], 'CALIBRATION_CONTRACT')
        require(timestamp(calibration['frozen_at']) < timestamp(calibration['test_start']) <
                timestamp(calibration['test_end']) <= timestamp(document['decision_at']), 'CALIBRATION_CHRONOLOGY')
        require(calibration.get('evidence') and calibration.get('all_trials_evidence'), 'CALIBRATION_EVIDENCE_REQUIRED')
        alpha, uncertainty = v('expected_return'), v('return_uncertainty', 0)
    # w, u>=abs(w), t>=abs(w-previous): smooth convex formulation.
    def cost(x):
        return costs @ x[2*n:] + impact @ (x[2*n:] ** 1.5)
    def objective(x):
        w, u = x[:n], x[n:2*n]
        return float(risk_aversion * (w @ sigma @ w) / 2 - alpha @ w +
                     uncertainty @ u + cost(x) + borrow @ ((u-w)/2))
    constraints = [
        {'type': 'eq', 'fun': lambda x: x[:n].sum()-net},
        {'type': 'ineq', 'fun': lambda x: x[n:2*n]-x[:n]},
        {'type': 'ineq', 'fun': lambda x: x[n:2*n]+x[:n]},
        {'type': 'ineq', 'fun': lambda x: x[2*n:]-(x[:n]-previous)},
        {'type': 'ineq', 'fun': lambda x: x[2*n:]+(x[:n]-previous)},
        {'type': 'ineq', 'fun': lambda x: gross-x[n:2*n].sum()},
        {'type': 'ineq', 'fun': lambda x: turnover-x[2*n:].sum()},
        {'type': 'ineq', 'fun': lambda x: 1-x[:n].sum()-cost(x)-cash_floor-reserve}]
    for issuer in sorted({a['issuer'] for a in assets}):
        mask = np.array([a['issuer'] == issuer for a in assets], float)
        constraints.append({'type': 'ineq', 'fun': lambda x, m=mask: issuer_cap-m @ x[n:2*n]})
    for group, limit in sorted(p['group_gross_caps'].items()):
        cap = scalar(limit, 'group_cap', 0, 4)
        mask = np.array([group in a['groups'] for a in assets], float)
        require(mask.any(), 'UNKNOWN_CONSTRAINT_GROUP:' + group)
        constraints.append({'type': 'ineq', 'fun': lambda x, m=mask, c=cap: c-m @ x[n:2*n]})
    scenarios = document['scenarios']
    require(scenarios, 'STRESS_SCENARIOS_REQUIRED')
    require(len({s['name'] for s in scenarios}) == len(scenarios), 'DUPLICATE_SCENARIO')
    for s in scenarios:
        shock = vector(s['returns'], 'scenario_returns', n, -1)
        cap = scalar(s['max_loss_fraction'], 'max_loss_fraction', 0)
        constraints.append({'type': 'ineq', 'fun': lambda x, r=shock, c=cap: c+r @ x[:n]-cost(x)})
    if 'volatility_cap' in p:
        cap = scalar(p['volatility_cap'], 'volatility_cap', 0)
        constraints.append({'type': 'ineq', 'fun': lambda x: cap**2-x[:n] @ sigma @ x[:n]})
    if 'tracking_volatility_cap' in p:
        benchmark = v('benchmark_weight')
        cap_te = scalar(p['tracking_volatility_cap'], 'tracking_volatility_cap', 0)
        constraints.append({'type': 'ineq', 'fun': lambda x: cap_te**2-(x[:n]-benchmark) @ sigma @ (x[:n]-benchmark)})
    start = np.clip(previous, low, high)
    bounds = list(zip(low, high)) + [(0, gross)]*n + [(0, c) for c in capacity]
    result = minimize(objective, np.r_[start, abs(start), np.minimum(abs(start-previous), capacity)],
                      method='SLSQP', bounds=bounds, constraints=constraints,
                      options={'maxiter': 2000, 'ftol': 1e-12})
    # Audit the ACTUAL weights, not potentially loose solver auxiliary variables.
    w = result.x[:n]
    actual = np.r_[w, abs(w), abs(w-previous)]
    if not np.isfinite(actual).all():
        return {'status': 'NO_VERIFIED_FEASIBLE_SOLUTION', 'weights': None,
                'solver_message': 'NONFINITE_SOLVER_RESULT', 'max_violation': None,
                'execution_authorized': False}
    violations = [float(np.max(abs(c['fun'](actual)))) if c['type'] == 'eq' else
                  max(0., float(-np.min(c['fun'](actual)))) for c in constraints]
    violations += [max(0., float(np.max(low-w))), max(0., float(np.max(w-high))),
                   max(0., float(np.max(abs(w-previous)-capacity)))]
    valid = result.success and np.isfinite(actual).all() and max(violations) <= 1e-7
    if not valid:
        return {'status': 'NO_VERIFIED_FEASIBLE_SOLUTION', 'weights': None,
                'solver_message': str(result.message), 'max_violation': max(violations), 'execution_authorized': False}
    return {'status': 'RESEARCH_PROPOSAL', 'weights': dict(zip(ids, w.tolist())),
            'gross_exposure': float(abs(w).sum()), 'net_exposure': float(w.sum()),
            'gross_turnover': float(abs(w-previous).sum()), 'estimated_cost_fraction': float(cost(actual)),
            'cash_after_modeled_cost': float(1-w.sum()-cost(actual)),
            'free_cash_after_collateral_reserve': float(1-w.sum()-cost(actual)-reserve),
            'volatility_over_covariance_horizon': float(np.sqrt(max(0., w @ sigma @ w))),
            'modeled_return': float(alpha @ w) if objective_name == 'robust_return' else None,
            'scenario_pnl_fraction': {s['name']: float(np.array(s['returns']) @ w-cost(actual)) for s in scenarios},
            'max_violation': max(violations), 'input_sha256': digest(document),
            'execution_authorized': False, 'calibration_verified': False,
            'limitation': 'Continuous planning weights. Borrow/recall, collateral, taxes, lots and actual settlement need separate broker checks. Covariance horizon is explicit; no automatic annualization.'}


if __name__ == '__main__':
    cli({'construct': construct})
