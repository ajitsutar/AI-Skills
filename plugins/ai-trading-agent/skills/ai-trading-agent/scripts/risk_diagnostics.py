"""Current-position distribution and conditional-variance diagnostics, not backtests.

Inputs have explicit units, dates, weight denominator and data/model flags. No NAV,
expected return, goal probability, normal-tail extrapolation or trade is generated.
"""
from __future__ import annotations
import math
from decimal import Decimal, localcontext
import numpy as np
from quant_common import covariance, digest, integer, require, scalar, timestamp, vector


def _contract(d):
    symbols = d['symbols']
    require(isinstance(symbols, list) and symbols and all(isinstance(s, str) and s.strip() == s and s for s in symbols)
            and len(set(symbols)) == len(symbols), 'UNIQUE_SYMBOLS_REQUIRED')
    require(isinstance(d['currency'], str) and bool(d['currency']), 'CURRENCY_REQUIRED')
    require(isinstance(d['period_label'], str) and bool(d['period_label'].strip()), 'PERIOD_LABEL_REQUIRED')
    require(d['weight_basis'] == 'fraction_of_supplied_notional', 'WEIGHT_DENOMINATOR_REQUIRED')
    require(set(d['weights']) == set(symbols), 'WEIGHT_UNIVERSE_MISMATCH')
    weights = vector([d['weights'][s] for s in symbols], 'weight', len(symbols), 0)
    require(float(weights.sum()) <= 1+1e-12, 'UNLEVERED_WEIGHTS_REQUIRED')
    notional = scalar(d['notional'], 'notional', 1e-12)
    at = timestamp(d['as_of'])
    return symbols, weights, notional, at


def empirical_tail(document):
    """Fractional-boundary expected shortfall from aligned current-weight shocks."""
    symbols, w, notional, at = _contract(document)
    require(document['return_basis'] == 'simple_total_return_decimal', 'SIMPLE_TOTAL_RETURN_UNITS_REQUIRED')
    rows = document['observations']
    require(isinstance(rows, list) and len(rows) >= 3, 'AT_LEAST_THREE_OBSERVATIONS')
    dates = [timestamp(r['timestamp']) for r in rows]
    require(dates == sorted(set(dates)) and dates[-1] <= at, 'ALIGNED_OBSERVATIONS_BEFORE_AS_OF')
    values = []
    for row in rows:
        require(set(row['returns']) == set(symbols), 'RETURN_UNIVERSE_MISMATCH')
        values.append(vector([row['returns'][s] for s in symbols], 'simple_return', len(symbols), -1))
    x = np.asarray(values)
    with np.errstate(over='ignore', invalid='ignore'):
        shock_returns = x @ w
        dispersion = float(shock_returns.std(ddof=1))
    require(np.isfinite(shock_returns).all() and math.isfinite(dispersion), 'NONFINITE_SHOCK_AGGREGATE')
    losses = -shock_returns
    ordered = np.sort(losses)[::-1]
    levels = document['confidence_levels']
    require(isinstance(levels, list) and levels, 'CONFIDENCE_LEVELS_REQUIRED')
    levels = [scalar(level, 'confidence', .5, .99999) for level in levels]
    require(len(set(levels)) == len(levels), 'UNIQUE_CONFIDENCE_LEVELS')
    sparse = integer(document.get('minimum_effective_tail_observations', 20), 'minimum_tail_count', 1)
    results = []
    for level in levels:
        level = scalar(level, 'confidence', .5, .99999)
        mass = len(losses)*(1-level)
        # Rounded exact boundaries prevent platform floating-point noise from
        # assigning a spurious tiny mass to an additional order statistic.
        if abs(mass-round(mass)) < 1e-12:
            mass = float(round(mass))
        whole = int(math.floor(mass)); fraction = mass-whole
        with np.errstate(over='ignore', invalid='ignore'):
            tail_sum = float(ordered[:whole].sum())
        if fraction > 0:
            tail_sum += fraction*float(ordered[whole])
        es = tail_sum/mass
        var = float(np.quantile(losses, level, method='inverted_cdf'))
        require(all(math.isfinite(v) for v in (es, var, es*notional, var*notional)), 'NONFINITE_TAIL_AGGREGATE')
        results.append({'confidence': level, 'loss_var_fraction': var,
                        'loss_expected_shortfall_fraction': es,
                        'loss_var_notional': var*notional, 'loss_expected_shortfall_notional': es*notional,
                        'effective_tail_observations': mass,
                        'tail_order_statistics_used': whole+int(fraction > 0),
                        'sparse_tail_warning': mass < sparse})
    return {'status': 'COMPUTED_CURRENT_WEIGHT_SHOCK_DISTRIBUTION', 'input_sha256': digest(document),
            'as_of': document['as_of'], 'currency': document['currency'], 'notional': notional,
            'period_label': document['period_label'],
            'weight_basis': document['weight_basis'], 'invested_weight': float(w.sum()),
            'cash_weight_assumed_zero_shock': max(0., 1-float(w.sum())),
            'observations': len(rows), 'first_observation': rows[0]['timestamp'], 'last_observation': rows[-1]['timestamp'],
            'empirical_standard_deviation_fraction': dispersion,
            'minimum_effective_tail_observations': sparse, 'tails': results,
            'method': 'Empirical inverse-CDF VaR and integrated worst-tail mean with fractional boundary mass.',
            'limitations': ['A current-position shock distribution, not executed portfolio performance or a strategy backtest.',
                           'No missing rows are filled; supplied alignment does not independently verify complete exchange sessions.',
                           'Sparse tails and changing market regimes limit inference. These are not future loss bounds.',
                           'Signed loss can be negative when even the estimated adverse tail is a gain.',
                           'No multi-period scaling, tax, transaction costs, cash yield or goal probability.'],
            'execution_authorized': False}


def _spending_goal(document, cash, notional, path_periods):
    """A withdrawal sensitivity, independent of an unestablished probability."""
    goal = document['spending_goal']
    fields = {'kind', 'amount', 'currency', 'horizon_periods', 'period_label', 'withdrawal_timing'}
    require(isinstance(goal, dict) and set(goal) == fields, 'SPENDING_GOAL_FIELDS_REQUIRED')
    require(goal['kind'] == 'withdrawal', 'WITHDRAWAL_GOAL_REQUIRED')
    require(goal['currency'] == document['currency'], 'SPENDING_GOAL_CURRENCY_MISMATCH')
    require(goal['period_label'] == document['period_label'], 'SPENDING_GOAL_PERIOD_MISMATCH')
    require(goal['withdrawal_timing'] == 'end_of_horizon', 'END_OF_HORIZON_WITHDRAWAL_REQUIRED')
    amount = scalar(goal['amount'], 'spending_goal_amount', 0)
    horizon = integer(goal['horizon_periods'], 'spending_goal_horizon', 1)
    # Decimal source values keep exact cash-equals-withdrawal boundaries from
    # changing solely because binary subtraction rounded the residual weight.
    with localcontext() as context:
        context.prec = 50
        target = Decimal(str(goal['amount']))
        balance = cash - target
        fraction = target / notional
    remaining, target_fraction = float(balance), float(fraction)
    require(all(math.isfinite(v) for v in (remaining, target_fraction)), 'NONFINITE_SPENDING_GOAL_AGGREGATE')
    return {'kind': goal['kind'], 'amount': amount, 'currency': goal['currency'],
            'horizon_periods': horizon, 'period_label': goal['period_label'],
            'withdrawal_timing': goal['withdrawal_timing'],
            'target_fraction_of_notional': target_fraction,
            'goal_horizon_within_variance_path': horizon <= path_periods,
            'cash_only_sensitivity': {
                'cash_before_withdrawal': float(cash), 'cash_after_withdrawal': remaining,
                'shortfall': max(0., -remaining), 'covered_under_assumptions': balance >= 0,
                'assumptions': ['Modeled residual cash remains unchanged through the withdrawal.',
                                'That cash is accessible and uncommitted at withdrawal.',
                                'No intervening cash flows, costs, taxes or cash yield are modeled.'],
                'interpretation': 'A negative balance is an arithmetic shortfall, not borrowing authority.'},
            'actual_available_cash': None, 'funding_established': False,
            'probability': None, 'probability_status': 'NOT_ESTABLISHED',
            'limitations': ['Residual cash is a model convention, not verified settled or spendable funds.',
                           'Cash-only coverage does not require earning the withdrawal as investment profit.',
                           'Conditional variance supplies neither a calibrated terminal distribution nor a funding probability, even within its path.',
                           'A goal beyond the supplied variance path does not extend that path or justify risk extrapolation.']}


def conditional_portfolio(document):
    """Aggregate per-period marginal variance paths with explicit fixed correlation."""
    symbols, w, notional, at = _contract(document)
    require(timestamp(document['forecast_origin']) <= at and timestamp(document['correlation_as_of']) <= timestamp(document['forecast_origin']),
            'RISK_INPUT_AFTER_AS_OF')
    variance_basis = document['variance_basis']
    correlation_basis = document['correlation_return_basis']
    allowed = {'log_return_decimal', 'simple_total_return_decimal'}
    require(variance_basis in allowed and correlation_basis in allowed, 'EXPLICIT_RETURN_BASIS_REQUIRED')
    approximation = variance_basis != correlation_basis
    require(not approximation or document.get('cross_basis_approximation_acknowledged') is True,
            'CROSS_BASIS_APPROXIMATION_NOT_DECLARED')
    require(document['correlation_ids'] == symbols, 'CORRELATION_ORDER_REQUIRED')
    correlation = covariance(document['correlation'], len(symbols))
    require(np.allclose(np.diag(correlation), 1, rtol=0, atol=1e-12) and
            np.max(abs(correlation)) <= 1+1e-12, 'CORRELATION_MATRIX_REQUIRED')
    require(set(document['variance_paths']) == set(symbols), 'VARIANCE_UNIVERSE_MISMATCH')
    require(set(document['model_flags']) == set(symbols) and
            all(isinstance(document['model_flags'][s], list) and
                all(isinstance(f, str) for f in document['model_flags'][s]) for s in symbols), 'MODEL_FLAGS_REQUIRED')
    require(document['variance_units'] == 'decimal_return_squared_per_period', 'VARIANCE_UNITS_REQUIRED')
    paths = [vector(document['variance_paths'][s], 'variance', minimum=0) for s in symbols]
    require(len({len(x) for x in paths}) == 1, 'COMMON_FORECAST_PATH_LENGTH_REQUIRED')
    count = len(paths[0]); marginal = np.sqrt(np.asarray(paths))
    periods = scalar(document['periods_per_year'], 'periods_per_year', 1)
    horizons = document['horizons']
    require(isinstance(horizons, list) and horizons, 'HORIZONS_REQUIRED')
    for h in horizons:integer(h, 'horizon', 1, count)
    require(len(set(horizons)) == len(horizons), 'UNIQUE_HORIZONS')
    daily = []
    for step in range(count):
        loading = w*marginal[:, step]
        with np.errstate(over='ignore', invalid='ignore'):
            variance = float(loading @ correlation @ loading)
        require(math.isfinite(variance), 'NONFINITE_CONDITIONAL_VARIANCE')
        require(variance >= -1e-12, 'NEGATIVE_PORTFOLIO_VARIANCE')
        daily.append(max(0., variance))
    output = []
    for h in horizons:
        integer(h, 'horizon', 1, count)
        cumulative = math.sqrt(sum(daily[:h]))
        require(all(math.isfinite(v) for v in (cumulative, cumulative*notional, cumulative*math.sqrt(periods/h))),
                'NONFINITE_CONDITIONAL_AGGREGATE')
        output.append({'periods': h, 'cumulative_sigma_fraction': cumulative,
                       'cumulative_sigma_notional': cumulative*notional,
                       'average_period_sigma_fraction': cumulative/math.sqrt(h),
                       'annualized_average_sigma_fraction': cumulative*math.sqrt(periods/h)})
    with localcontext() as context:
        context.prec = 50
        invested = sum((Decimal(str(document['weights'][s])) for s in symbols), Decimal(0))
        cash_weight = max(Decimal(0), Decimal(1) - invested)
        source_notional = Decimal(str(document['notional']))
        cash = cash_weight * source_notional
    require(math.isfinite(float(cash)), 'NONFINITE_CONDITIONAL_CASH')
    result = {'status': 'CONDITIONAL_RISK_SCENARIO', 'input_sha256': digest(document),
            'currency': document['currency'], 'notional': notional, 'weight_basis': document['weight_basis'],
            'as_of': document['as_of'], 'periods_per_year': periods,
            'period_label': document['period_label'], 'forecast_origin': document['forecast_origin'],
            'correlation_as_of': document['correlation_as_of'],
            'cross_basis_approximation': approximation,
            'invested_weight': float(invested), 'cash_weight_assumed_zero_shock': float(cash_weight),
            'modeled_cash_notional': float(cash), 'actual_available_cash': None,
            'available_variance_periods': count,
            'variance_per_period_decimal_squared': daily, 'horizons': output,
            'retained_model_flags': document['model_flags'],
            'calibration_established': False, 'execution_authorized': False,
            'limitations': ['Marginal forecasts plus fixed correlations are not a fitted multivariate volatility model.',
                           'Aggregation assumes zero cross-period innovation covariance; observed serial dependence may invalidate this.',
                           'Input model failures and warnings remain failures/warnings; aggregation does not rehabilitate them.',
                           'Sigma is not a loss bound. No Gaussian probability band, expected return, goal probability or strategy backtest is emitted.',
                           'Cash weight has zero modeled short-horizon variance. Notional, costs and tax are not updated during the horizon.',
                           'Residual cash is measured on the full supplied notional without renormalizing invested weights; its actual availability is unknown.']}
    if 'spending_goal' in document:
        result['spending_goal'] = _spending_goal(document, cash, source_notional, count)
    return result
