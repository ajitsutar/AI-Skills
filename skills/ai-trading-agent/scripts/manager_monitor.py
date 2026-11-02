"""Explicit operational/model-monitor thresholds; no automatic strategy retuning."""
from __future__ import annotations

from quant_common import cli, integer, require, scalar, timestamp, vector


def assess(as_of, observations_at, returns, periods_per_year, forecast_volatility,
           coverage, execution_cost_bps, reconciliation_difference, limits):
    now, observed = timestamp(as_of), timestamp(observations_at)
    require(now >= observed, 'FUTURE_MONITOR_OBSERVATION')
    samples = vector(returns, 'net_returns', minimum=-1)
    integer(limits['minimum_observations'], 'minimum_observations', 3)
    annualization = scalar(periods_per_year, 'periods_per_year', 1)
    forecast = scalar(forecast_volatility, 'forecast_volatility', 1e-12)
    covered = scalar(coverage, 'coverage', 0, 1)
    cost = scalar(execution_cost_bps, 'execution_cost_bps')
    difference = abs(scalar(reconciliation_difference, 'reconciliation_difference'))
    max_age = scalar(limits['max_age_seconds'], 'max_age_seconds', 0)
    min_coverage = scalar(limits['minimum_coverage'], 'minimum_coverage', 0, 1)
    max_ratio = scalar(limits['max_realized_to_forecast_volatility'], 'volatility_ratio', 1)
    max_cost = scalar(limits['max_cost_bps'], 'max_cost_bps', 0)
    max_difference = scalar(limits['max_reconciliation_difference'], 'max_difference', 0)
    reasons = []
    if (now-observed).total_seconds() > max_age:
        reasons.append('STALE_MONITOR')
    if len(samples) < limits['minimum_observations']:
        reasons.append('INSUFFICIENT_MONITOR_HISTORY')
    if covered < min_coverage:
        reasons.append('COVERAGE_BELOW_MANDATE')
    realized = float(samples.std(ddof=1)*annualization**.5) if len(samples) > 1 else None
    if realized is not None and realized/forecast > max_ratio:
        reasons.append('VOLATILITY_MODEL_UNDERPREDICTION')
    if cost > max_cost:
        reasons.append('EXECUTION_COST_BREACH')
    if difference > max_difference:
        reasons.append('RECONCILIATION_BREAK')
    return {'status': 'ADVISORY_RISK_ALERT' if reasons else 'CHECKED_METRICS_WITHIN_LIMITS',
            'advisory_only': True, 'enforces_execution': False,
            'reasons': reasons, 'realized_volatility': realized,
            'realized_to_forecast_ratio': None if realized is None else realized/forecast,
            'automatic_retuning_allowed': False, 'execution_authorized': False,
            'limitation': 'Research diagnostics require matched frequency and window. Alerts neither authorize nor block native host/broker orders.'}


if __name__ == '__main__':
    cli({'assess': assess})
