"""Cost-aware constrained research allocation for linear, cash-funded instruments.

No orders, leverage permission, alpha calibration or nonlinear derivative sizing.
The fixed public stock-discovery ranking is not changed by this optional allocator.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize, linprog
from copy import deepcopy
from types import SimpleNamespace

from quant_common import cli, covariance, digest, require, scalar, timestamp, vector


def _linear_minimum_risk_problem(assets, previous, low, high, capacity, p, scenarios):
    """Equivalent long-only zero-cost constraints, with constant rows eliminated.

    This is used only after the caller has validated the original document. It
    does not relax requested constraints. The original functions remain the
    final feasibility audit, including nonlinear variance/tracking caps.
    """
    n = len(assets); net = p['net_target']; initial_cash = bool(np.all(previous == 0))
    size = n if initial_cash else 2*n
    rows, bounds_rhs, constants = [], [], []
    def add(coefficients, bound, name):
        row = np.zeros(size); row[:len(coefficients)] = coefficients
        if np.all(row[n:] == 0) and np.all(row[:n] == row[0]):
            margin = float(bound-row[0]*net)
            constants.append({'name': name, 'slack': margin})
            if margin < -1e-12:
                rows.append(np.zeros(size)); bounds_rhs.append(margin)
        else:
            rows.append(row); bounds_rhs.append(float(bound))
    add(np.ones(n), p['gross_cap'], 'gross_cap')
    add(np.ones(n), 1-p['cash_floor']-p['collateral_reserve'], 'cash_floor')
    if initial_cash:
        add(np.ones(n), p['gross_turnover_cap'], 'turnover_cap')
        bounds = list(zip(low, np.minimum(high, capacity)))
    else:
        bounds = list(zip(low, high))+[(0., float(c)) for c in capacity]
        add(np.r_[np.zeros(n), np.ones(n)], p['gross_turnover_cap'], 'turnover_cap')
        for i in range(n):
            row = np.zeros(size); row[i] = 1; row[n+i] = -1
            add(row, previous[i], 'positive_trade')
            row = np.zeros(size); row[i] = -1; row[n+i] = -1
            add(row, -previous[i], 'negative_trade')
    for issuer in sorted({a['issuer'] for a in assets}):
        add(np.array([a['issuer'] == issuer for a in assets], float), p['issuer_gross_cap'], 'issuer:'+issuer)
    for group, cap in sorted(p['group_gross_caps'].items()):
        add(np.array([group in a['groups'] for a in assets], float), cap, 'group:'+group)
    for s in scenarios:
        add(-np.asarray(s['returns'], float), s['max_loss_fraction'], 'scenario:'+s['name'])
    return {'n': n, 'size': size, 'initial_cash': initial_cash, 'bounds': bounds,
            'a_ub': np.asarray(rows) if rows else np.empty((0, size)),
            'b_ub': np.asarray(bounds_rhs), 'a_eq': np.r_[np.ones(n), np.zeros(size-n)][None, :],
            'b_eq': np.array([net]), 'eliminated_constant_rows': constants}


def _lp(problem, objective):
    return linprog(objective, A_ub=problem['a_ub'] if len(problem['a_ub']) else None,
                   b_ub=problem['b_ub'] if len(problem['b_ub']) else None,
                   A_eq=problem['a_eq'], b_eq=problem['b_eq'], bounds=problem['bounds'], method='highs')


def _minimum_risk_certificate(problem, weights, sigma, risk_aversion):
    gradient = np.r_[risk_aversion*(sigma @ weights), np.zeros(problem['size']-len(weights))]
    result = _lp(problem, gradient)
    if not result.success:
        return {'status': 'NOT_ESTABLISHED', 'reason': 'LINEAR_WITNESS_FAILED', 'solver_message': str(result.message)}
    gap = float(gradient[:len(weights)] @ weights-result.fun)
    # Ignoring any nonlinear variance cap enlarges the witness set. A zero gap
    # on that superset is still a sufficient certificate; a positive gap is not.
    return {'status': 'CONDITIONAL_MINIMUM_CERTIFIED' if gap <= 1e-8 else 'NOT_ESTABLISHED',
            'convex_objective_gap_upper_bound': max(0., gap), 'raw_directional_gap': gap,
            'certificate_tolerance': 1e-8,
            'method': 'Independent HiGHS linear-program minimization of the convex quadratic gradient over original linear constraints.',
            'scope': 'Conditional on supplied covariance, zero costs, long-only bounds and constraints; not validation of forecast accuracy or investment performance.'}


def _reduced_minimum_risk(problem, sigma, p, assets):
    n, size = problem['n'], problem['size']
    start = _lp(problem, np.zeros(size))
    if not start.success:
        return None, {'status': 'LINEAR_FEASIBILITY_FAILED', 'message': str(start.message)}
    constraints = [{'type': 'eq', 'fun': lambda x: problem['a_eq'] @ x-problem['b_eq'],
                    'jac': lambda x: problem['a_eq']}]
    if len(problem['a_ub']):
        constraints.append({'type': 'ineq', 'fun': lambda x: problem['b_ub']-problem['a_ub'] @ x,
                            'jac': lambda x: -problem['a_ub']})
    if 'volatility_cap' in p:
        volatility_cap = p['volatility_cap']
        constraints.append({'type': 'ineq', 'fun': lambda x: volatility_cap**2-x[:n] @ sigma @ x[:n],
                            'jac': lambda x: np.r_[-2*(sigma @ x[:n]), np.zeros(size-n)]})
    if 'tracking_volatility_cap' in p:
        tracking_cap = p['tracking_volatility_cap']; benchmark = np.array([a['benchmark_weight'] for a in assets])
        constraints.append({'type': 'ineq', 'fun': lambda x: tracking_cap**2-(x[:n]-benchmark) @ sigma @ (x[:n]-benchmark),
                            'jac': lambda x: np.r_[-2*(sigma @ (x[:n]-benchmark)), np.zeros(size-n)]})
    answer = minimize(lambda x: float(p['risk_aversion']*(x[:n] @ sigma @ x[:n])/2), start.x,
                      jac=lambda x: np.r_[p['risk_aversion']*(sigma @ x[:n]), np.zeros(size-n)],
                      bounds=problem['bounds'], constraints=constraints, method='SLSQP',
                      options={'maxiter': 2000, 'ftol': 1e-12})
    return answer, {'status': 'REDUCED_LONG_ONLY_ZERO_COST_ATTEMPT', 'success': bool(answer.success),
                    'message': str(answer.message), 'constraint_relaxation': False,
                    'eliminated_constant_rows': problem['eliminated_constant_rows']}


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
    attempts = [{'method': 'original_auxiliary_formulation', 'success': bool(result.success),
                 'message': str(result.message)}]
    certificate = {'status': 'NOT_APPLICABLE', 'reason': 'Certificate is implemented only for zero-cost long-only minimum-risk objectives.'}
    can_certify = objective_name == 'minimum_risk' and np.all(low >= 0) and not np.any(np.r_[costs, impact, borrow])
    linear_problem = _linear_minimum_risk_problem(assets, previous, low, high, capacity, p, scenarios) if can_certify else None
    if can_certify and np.isfinite(result.x[:n]).all():
        certificate = _minimum_risk_certificate(linear_problem, result.x[:n], sigma, risk_aversion)
        attempts[0]['independent_optimality_certificate'] = certificate
    # SLSQP can return success at a non-optimal vertex when redundant boundary
    # inequalities frustrate its search. A success flag is not the certificate.
    if can_certify and (not result.success or certificate['status'] != 'CONDITIONAL_MINIMUM_CERTIFIED'):
        reduced, receipt = _reduced_minimum_risk(linear_problem, sigma, p, assets)
        attempts.append(receipt)
        if reduced is not None:
            reduced_w = reduced.x[:n]
            reduced_certificate = _minimum_risk_certificate(linear_problem, reduced_w, sigma, risk_aversion)
            result = SimpleNamespace(x=np.r_[reduced_w, abs(reduced_w), abs(reduced_w-previous)],
                                     success=bool(reduced.success or reduced_certificate['status'] == 'CONDITIONAL_MINIMUM_CERTIFIED'),
                                     message=str(reduced.message))
    # Audit the ACTUAL weights, not potentially loose solver auxiliary variables.
    w = result.x[:n]
    actual = np.r_[w, abs(w), abs(w-previous)]
    if not np.isfinite(actual).all():
        return {'status': 'NO_VERIFIED_FEASIBLE_SOLUTION', 'weights': None,
                'solver_message': 'NONFINITE_SOLVER_RESULT', 'max_violation': None,
                'solver_attempts': attempts,
                'execution_authorized': False}
    violations = [float(np.max(abs(c['fun'](actual)))) if c['type'] == 'eq' else
                  max(0., float(-np.min(c['fun'](actual)))) for c in constraints]
    violations += [max(0., float(np.max(low-w))), max(0., float(np.max(w-high))),
                   max(0., float(np.max(abs(w-previous)-capacity)))]
    valid = result.success and np.isfinite(actual).all() and max(violations) <= 1e-7
    if not valid:
        return {'status': 'NO_VERIFIED_FEASIBLE_SOLUTION', 'weights': None,
                'solver_message': str(result.message), 'max_violation': max(violations),
                'solver_attempts': attempts, 'execution_authorized': False}
    if can_certify:
        certificate = _minimum_risk_certificate(linear_problem, w, sigma, risk_aversion)
    variance = float(w @ sigma @ w)
    eigenvalues = np.linalg.eigvalsh(sigma)
    positive_min = float(eigenvalues.min())
    condition = float(eigenvalues.max()/positive_min) if positive_min > 1e-15 else None
    risk_detail = {'variance_over_covariance_horizon': variance,
                   'variance_contribution_fraction': dict(zip(ids, (w*(sigma @ w)/variance).tolist())) if variance > 1e-20 else None,
                   'covariance_min_eigenvalue': positive_min, 'covariance_condition_number': condition,
                   'covariance_warning': 'SINGULAR_OR_ILL_CONDITIONED' if condition is None or condition > 1e8 else None}
    slack = {'cash_floor': float(1-w.sum()-cost(actual)-cash_floor-reserve),
             'gross_cap': float(gross-abs(w).sum()), 'turnover_cap': float(turnover-abs(w-previous).sum())}
    slack.update({'upper:'+s: float(high[i]-w[i]) for i, s in enumerate(ids)})
    slack.update({'lower:'+s: float(w[i]-low[i]) for i, s in enumerate(ids)})
    for group, limit in p['group_gross_caps'].items():
        slack['group:'+group] = float(limit-sum(abs(w[i]) for i, a in enumerate(assets) if group in a['groups']))
    for issuer in sorted({a['issuer'] for a in assets}):
        slack['issuer:'+issuer] = float(issuer_cap-sum(abs(w[i]) for i, a in enumerate(assets) if a['issuer'] == issuer))
    for scenario in scenarios:
        slack['stress:'+scenario['name']] = float(scenario['max_loss_fraction']+np.array(scenario['returns']) @ w-cost(actual))
    slack_units = {key: 'fraction_of_portfolio_notional' for key in slack}
    if 'volatility_cap' in p:
        slack['variance_cap_squared'] = float(p['volatility_cap']**2-variance)
        slack_units['variance_cap_squared'] = 'variance_over_covariance_horizon'
    if 'tracking_volatility_cap' in p:
        delta = w-v('benchmark_weight')
        slack['tracking_variance_cap_squared'] = float(p['tracking_volatility_cap']**2-delta @ sigma @ delta)
        slack_units['tracking_variance_cap_squared'] = 'variance_over_covariance_horizon'
    return {'status': 'RESEARCH_PROPOSAL', 'weights': dict(zip(ids, w.tolist())),
            'gross_exposure': float(abs(w).sum()), 'net_exposure': float(w.sum()),
            'gross_turnover': float(abs(w-previous).sum()), 'estimated_cost_fraction': float(cost(actual)),
            'cash_after_modeled_cost': float(1-w.sum()-cost(actual)),
            'free_cash_after_collateral_reserve': float(1-w.sum()-cost(actual)-reserve),
            'volatility_over_covariance_horizon': float(np.sqrt(max(0., w @ sigma @ w))),
            'modeled_return': float(alpha @ w) if objective_name == 'robust_return' else None,
            'scenario_pnl_fraction': {s['name']: float(np.array(s['returns']) @ w-cost(actual)) for s in scenarios},
            'max_violation': max(violations), 'input_sha256': digest(document),
            'solver_attempts': attempts, 'original_constraint_validation_tolerance': 1e-7,
            'constraint_slacks': slack, 'binding_constraints': [name for name, value in slack.items() if abs(value) <= 1e-7],
            'constraint_slack_units': slack_units,
            'risk_diagnostics': risk_detail, 'independent_optimality_certificate': certificate,
            'execution_authorized': False, 'calibration_verified': False,
            'limitation': 'Continuous planning weights. Borrow/recall, collateral, taxes, lots and actual settlement need separate broker checks. Covariance horizon is explicit; no automatic annualization.'}


def sensitivity(document):
    """Prespecified risk/cap alternatives; retain changes, never choose a winner."""
    base = document['base']
    cases = document.get('covariance_scenarios', [])
    cap_cases = document.get('constraint_scenarios', [])
    require(isinstance(cases, list) and isinstance(cap_cases, list) and 0 < len(cases)+len(cap_cases) <= 20,
            'ONE_TO_TWENTY_SENSITIVITY_CASES')
    all_cases = cases+cap_cases
    require(all(isinstance(c.get('id'), str) and c['id'] for c in all_cases) and
            len({c['id'] for c in all_cases}) == len(all_cases), 'UNIQUE_SENSITIVITY_IDS')
    baseline = construct(base); output = []
    ids = base['covariance_ids']
    for case in cases:
        require(case['covariance_ids'] == ids and case['horizon_id'] == base['horizon_id'], 'SENSITIVITY_BASIS_MISMATCH')
        candidate = deepcopy(base)
        candidate['covariance'] = case['covariance']
        candidate['risk_estimated_at'] = case['estimated_at']
        result = construct(candidate)
        difference = None; fixed_risk = None
        if baseline['weights'] is not None:
            w = np.array([baseline['weights'][s] for s in ids])
            sigma = covariance(case['covariance'], len(ids))
            fixed_risk = float(np.sqrt(max(0., w @ sigma @ w)))
            if result['weights'] is not None:
                difference = float(sum(abs(result['weights'][s]-baseline['weights'][s]) for s in ids))
        output.append({'id': case['id'], 'result': result, 'gross_weight_change_from_baseline': difference,
                       'baseline_weights_volatility_under_case_covariance': fixed_risk})
    constraint_outputs = []
    allowed = {'gross_cap', 'gross_turnover_cap', 'cash_floor', 'issuer_gross_cap',
               'group_gross_caps', 'volatility_cap', 'tracking_volatility_cap'}
    for case in cap_cases:
        require(set(case) <= {'id', 'constraint_overrides', 'asset_max_weights'}, 'UNSUPPORTED_CONSTRAINT_CASE_FIELD')
        overrides = case.get('constraint_overrides', {})
        asset_caps = case.get('asset_max_weights', {})
        require(isinstance(overrides, dict) and isinstance(asset_caps, dict) and bool(overrides or asset_caps),
                'EXPLICIT_CAP_VARIANT_REQUIRED')
        require(set(overrides) <= allowed, 'UNSUPPORTED_CONSTRAINT_OVERRIDE')
        require(set(asset_caps) <= set(ids), 'UNKNOWN_ASSET_CAP')
        candidate = deepcopy(base); changes = []
        for key, value in overrides.items():
            if key == 'group_gross_caps':
                require(isinstance(value, dict), 'GROUP_CAP_OVERRIDES_OBJECT')
                for group, cap in value.items():
                    require(isinstance(group, str) and bool(group), 'GROUP_CAP_IDENTIFIER_REQUIRED')
                    scalar(cap, 'group_cap', 0, 4)
                    before = candidate['constraints']['group_gross_caps'].get(group)
                    candidate['constraints']['group_gross_caps'][group] = cap
                    if before != cap:changes.append({'field': 'constraints/group_gross_caps/'+group, 'before': before, 'after': cap})
            else:
                scalar(value, key, 0, 4)
                before = candidate['constraints'].get(key)
                candidate['constraints'][key] = value
                if before != value:changes.append({'field': 'constraints/'+key, 'before': before, 'after': value})
        for asset in candidate['assets']:
            if asset['id'] in asset_caps:
                cap = scalar(asset_caps[asset['id']], 'asset_max_weight', 0, 1)
                before = asset['max_weight'];asset['max_weight'] = cap
                if before != cap:changes.append({'field': 'assets/'+asset['id']+'/max_weight', 'before': before, 'after': cap})
        result = construct(candidate)
        difference = (float(sum(abs(result['weights'][s]-baseline['weights'][s]) for s in ids))
                      if result['weights'] is not None and baseline['weights'] is not None else None)
        constraint_outputs.append({'id': case['id'], 'changed_fields': changes, 'hypothesis_changed': bool(changes),
                                   'new_registry_attempt_required_for_research_claim': bool(changes),
                                   'result': result, 'gross_weight_change_from_baseline': difference})
    return {'status': 'COVARIANCE_SENSITIVITY_COMPARISON', 'input_sha256': digest(document),
            'comparison_scope': 'prespecified_covariance_and_constraint_scenarios',
            'baseline': baseline, 'cases': output, 'constraint_cases': constraint_outputs,
            'selected_case': None, 'execution_authorized': False,
            'registry_note': 'Changed cap hypotheses require a distinct disclosed research attempt before making selection/performance claims; this is not a trade-approval requirement.',
            'limitation': 'Prespecified sensitivity is not evidence of forward performance. Covariance cases retain baseline constraints; cap cases explicitly retain every changed field. No post-hoc winner is selected.'}


if __name__ == '__main__':
    cli({'construct': construct, 'sensitivity': sensitivity})
