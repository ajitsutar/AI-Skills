"""Chronological validation, tail loss, dependent-return inference and trial control.

Original implementations of published methods; sources and assumptions are in
references/quant-research.md. Diagnostics do not promote a strategy or prove alpha.
"""
from __future__ import annotations

import math
import re
import numpy as np
from scipy.stats import norm

from quant_common import cli, integer, require, scalar, series, timestamp, vector


def purged_walk_forward(samples, min_train, test_size, gap_seconds=0):
    """Expanding prior-only folds; labels/features must be known before each test.

    Purging uses the latest of label_end and feature_available_at. Gap is an
    explicit time embargo BEFORE test; no future observations ever enter training.
    """
    integer(min_train, 'min_train', 2)
    integer(test_size, 'test_size', 1)
    gap = scalar(gap_seconds, 'gap_seconds', 0)
    require(len({s['id'] for s in samples}) == len(samples), 'DUPLICATE_SAMPLE')
    starts = [timestamp(s['start']) for s in samples]
    require(starts == sorted(set(starts)), 'SAMPLES_NOT_CHRONOLOGICAL')
    ends = [timestamp(s['label_end']) for s in samples]
    available = [timestamp(s['feature_available_at']) for s in samples]
    require(all(b >= a and f <= a for a, b, f in zip(starts, ends, available)),
            'LABEL_OR_FEATURE_LOOKAHEAD')
    folds = []
    for i in range(min_train, len(samples), test_size):
        train = [j for j in range(i) if (starts[i] - max(ends[j], available[j])).total_seconds() > gap]
        test = list(range(i, min(i + test_size, len(samples))))
        if len(train) < min_train:
            continue
        folds.append({'train': [samples[j]['id'] for j in train],
                      'test': [samples[j]['id'] for j in test],
                      'purged': [samples[j]['id'] for j in range(i) if j not in train]})
    require(folds, 'NO_VALID_FOLDS')
    return {'folds': folds, 'gap_seconds': gap, 'split_policy': 'EXPANDING_PRIOR_ONLY',
            'limitation': 'Split indexes only; fit preprocessing/features inside each train fold. Reserve a separate untouched final test.'}


def tail_risk(returns, confidence=.975):
    """Empirical quantile and integrated worst-tail loss with fractional boundary."""
    x = vector(returns, 'returns', minimum=-1)
    alpha = scalar(confidence, 'confidence', .5, .9999)
    losses = np.sort(-x)[::-1]
    mass = (1 - alpha) * len(x)
    full = int(math.floor(mass))
    fraction = mass - full
    total = float(losses[:full].sum())
    if fraction > 1e-12:
        total += fraction * float(losses[full])
    es = total / mass
    var = float(np.quantile(-x, alpha, method='inverted_cdf'))
    wealth = np.r_[1., np.cumprod(1 + x)]
    peaks = np.maximum.accumulate(wealth)
    return {'confidence': alpha, 'observations': len(x), 'effective_tail_observations': mass,
            'loss_var': var, 'loss_expected_shortfall': es,
            'max_drawdown': float(np.max(1 - wealth / peaks)),
            'total_return': float(wealth[-1] - 1),
            'warning': 'Sparse empirical tail' if mass < 20 else None,
            'units': 'input_period_return_decimal',
            'limitation': 'Negative loss denotes gain; no square-root-of-time scaling or guarantee against unseen losses.'}


def hac_mean(returns, lags):
    """Bartlett/Newey-West long-run variance of mean, normal approximation."""
    x = vector(returns, 'returns')
    n = len(x)
    require(n >= 3, 'INSUFFICIENT_OBSERVATIONS')
    integer(lags, 'lags', 0, n - 2)
    centered = x - x.mean()
    long_var = float(centered @ centered) / n
    for lag in range(1, lags + 1):
        long_var += 2 * (1 - lag / (lags + 1)) * float(centered[lag:] @ centered[:-lag]) / n
    se = math.sqrt(max(0., long_var) / n)
    require(se > 0, 'DEGENERATE_MEAN_VARIANCE')
    z = float(x.mean()) / se
    return {'mean': float(x.mean()), 'standard_error_hac': se, 'lags': lags,
            'z': z, 'two_sided_p': float(2 * norm.sf(abs(z))),
            'ci95': [float(x.mean() - norm.ppf(.975) * se), float(x.mean() + norm.ppf(.975) * se)],
            'limitation': 'Asymptotic inference; lags and return frequency must be fixed before inspecting significance.'}


def holm(p_values, alpha=.05):
    require(isinstance(p_values, dict) and p_values, 'TRIALS_REQUIRED')
    threshold = scalar(alpha, 'alpha', .000001, .999999)
    ordered = sorted((scalar(p, 'p_value', 0, 1), name) for name, p in p_values.items())
    adjusted, previous = {}, 0.
    for i, (p, name) in enumerate(ordered):
        previous = max(previous, min(1., (len(ordered) - i) * p))
        adjusted[name] = {'raw_p': p, 'holm_p': previous, 'reject': previous <= threshold}
    return {'trials': adjusted, 'alpha': threshold,
            'limitation': 'Familywise correction requires the complete prespecified trial family; omitted variants invalidate interpretation.'}


def sharpe_evidence(returns, trial_sharpes, effective_trials, iid_assumption_justified=False):
    """PSR/DSR on unannualized excess returns; Pearson kurtosis, sample std.

    Not a posterior probability of profit. Serial dependence violates the simple
    PSR formula; report diagnostics but withhold interpretable probability then.
    """
    x = vector(returns, 'excess_returns')
    require(len(x) >= 20, 'SHARPE_SAMPLE_TOO_SHORT')
    trials = vector(trial_sharpes, 'all_trial_sharpes')
    count = scalar(effective_trials, 'effective_trials', 1, len(trials))
    require(count == 1 or count >= 2, 'EFFECTIVE_TRIALS_MUST_BE_ONE_OR_AT_LEAST_TWO')
    require(type(iid_assumption_justified) is bool, 'IID_FLAG_REQUIRED')
    std = float(x.std(ddof=1))
    require(std > 0, 'ZERO_VARIANCE')
    sr = float(x.mean()) / std
    centered = x - x.mean()
    popvar = float(np.mean(centered**2))
    skew = float(np.mean(centered**3) / popvar**1.5)
    kurt = float(np.mean(centered**4) / popvar**2)
    denominator = 1 - skew * sr + (kurt - 1) * sr**2 / 4
    require(denominator > 0, 'INVALID_SHARPE_VARIANCE')
    if count == 1:
        hurdle = 0.
    else:
        require(len(trials) >= 2, 'MULTIPLE_TRIALS_REQUIRED')
        euler = .5772156649015329
        hurdle = float(trials.std(ddof=1)) * ((1-euler)*norm.ppf(1-1/count) + euler*norm.ppf(1-1/(count*math.e)))
    scale = math.sqrt((len(x)-1)/denominator)
    return {'sharpe_per_period': sr, 'skewness': skew, 'pearson_kurtosis': kurt,
            'selection_hurdle_per_period': float(hurdle), 'effective_trials': count,
            'reported_variants': len(trials),
            'psr_iid_diagnostic': float(norm.cdf(sr * scale)),
            'dsr_iid_diagnostic': float(norm.cdf((sr - hurdle) * scale)),
            'inference_usable': iid_assumption_justified,
            'limitation': 'Same frequency/net excess-return units for all trials. Effective trial count needs independent justification; no automatic promotion.'}


def block_bootstrap(returns, block_length, replications=1000, seed=0):
    """Circular moving-block bootstrap of mean; explicitly seeded and bounded."""
    x = vector(returns, 'returns')
    n = len(x)
    integer(block_length, 'block_length', 1, max(1, n // 2))
    integer(replications, 'replications', 100, 100000)
    integer(seed, 'seed', 0)
    require(n >= 20, 'BOOTSTRAP_SAMPLE_TOO_SHORT')
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(replications):
        starts = rng.integers(0, n, size=math.ceil(n / block_length))
        indices = ((starts[:, None] + np.arange(block_length)) % n).ravel()[:n]
        means.append(float(x[indices].mean()))
    return {'mean': float(x.mean()), 'mean_percentile_ci95': np.quantile(means, [.025, .975]).tolist(),
            'seed': seed, 'block_length': block_length, 'replications': replications,
            'limitation': 'Percentile interval under approximate stationarity, not probability of future profit; disclose block-length sensitivity.'}


def factor_attribution(observations, factor_names, lags=0):
    dates, y = series(observations, 'excess_return', 20)
    require(factor_names and len(set(factor_names)) == len(factor_names), 'FACTOR_NAMES')
    X = np.array([[1.] + [scalar(r['factors'][f], f) for f in factor_names] for r in observations])
    n, k = X.shape
    integer(lags, 'lags', 0, n-2)
    require(n > k + 2 and np.linalg.matrix_rank(X) == k, 'RANK_DEFICIENT_FACTORS')
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    residual = y - X @ beta
    scores = X * residual[:, None]
    meat = scores.T @ scores
    for lag in range(1, lags + 1):
        cross = scores[lag:].T @ scores[:-lag]
        meat += (1 - lag / (lags + 1)) * (cross + cross.T)
    bread = np.linalg.inv(X.T @ X)
    cov = bread @ meat @ bread * n / (n-k)
    se = np.sqrt(np.maximum(0., np.diag(cov)))
    total = float(np.sum((y-y.mean())**2))
    return {'observations': n, 'coefficients': dict(zip(['intercept']+factor_names, beta.tolist())),
            'standard_errors_hac': dict(zip(['intercept']+factor_names, se.tolist())),
            'r_squared': None if total == 0 else 1-float(residual @ residual)/total,
            'residual_std_per_period': float(np.std(residual, ddof=k)), 'lags': lags,
            'limitation': 'Ex-post exposures, not causal alpha or return forecasts. Factors/excess returns must share timestamps, currency and units.'}


def promotion_evidence(evidence, criteria):
    """Recompute selected strategy tests from the COMPLETE supplied trial family.

    OOS returns must be net of costs and a matching benchmark. Human/source review
    is still needed to establish that the trial registry and data are authentic.
    """
    integer(criteria['minimum_observations'], 'minimum_observations', 20)
    cutoff = scalar(criteria['max_holm_p'], 'max_holm_p', .000001, .1)
    require(evidence.get('units') == 'net_excess_return_decimal', 'NET_EXCESS_UNITS_REQUIRED')
    def sha256(value):
        return isinstance(value, str) and bool(re.fullmatch('[0-9a-f]{64}', value))
    require(evidence.get('all_variants_disclosed') is True and sha256(evidence.get('trial_registry_sha256')), 'COMPLETE_TRIAL_REGISTRY_REQUIRED')
    hashes = evidence.get('input_data_hashes')
    require(isinstance(hashes, list) and hashes and all(sha256(h) for h in hashes), 'RETAINED_MARKET_DATA_REQUIRED')
    trials = evidence['trials']
    require(trials and len({t['id'] for t in trials}) == len(trials), 'UNIQUE_TRIAL_IDS')
    start, end = timestamp(evidence['test_start']), timestamp(evidence['test_end'])
    require(timestamp(evidence['parameters_frozen_at']) < start < end, 'QUANT_TEST_CHRONOLOGY')
    outputs, arrays, reference = {}, {}, None
    for trial in trials:
        dates, values = series(trial['observations'], 'return', criteria['minimum_observations'])
        require(dates[0] >= start and dates[-1] <= end, 'RETURNS_OUTSIDE_TEST_WINDOW')
        require(reference is None or dates == reference, 'TRIAL_RETURNS_NOT_ALIGNED')
        reference = dates
        arrays[trial['id']] = values.tolist()
        outputs[trial['id']] = hac_mean(values.tolist(), criteria['hac_lags'])
    selected = evidence['selected_trial']
    require(selected in outputs, 'SELECTED_TRIAL_MISSING')
    family = holm({name: out['two_sided_p'] for name, out in outputs.items()}, cutoff)
    bootstrap = block_bootstrap(arrays[selected], criteria['bootstrap_block_length'],
                               criteria['bootstrap_replications'], criteria['bootstrap_seed'])
    reasons = []
    if outputs[selected]['mean'] <= 0:
        reasons.append('NONPOSITIVE_NET_EXCESS_MEAN')
    if not family['trials'][selected]['reject']:
        reasons.append('MULTIPLE_TESTING_CRITERION_FAILED')
    if bootstrap['mean_percentile_ci95'][0] <= 0:
        reasons.append('BLOCK_BOOTSTRAP_LOWER_BOUND_NOT_POSITIVE')
    return {'quantitative_criteria_passed': not reasons, 'reasons': reasons,
            'selected_trial': selected, 'hac': outputs[selected], 'holm': family, 'bootstrap': bootstrap,
            'execution_authorized': False,
            'limitation': 'Predeclared criteria and full trial records required. Statistical acceptance is not alpha proof or live authorization.'}


if __name__ == '__main__':
    cli({'folds': purged_walk_forward, 'tail': tail_risk, 'hac': hac_mean,
         'holm': holm, 'sharpe': sharpe_evidence, 'bootstrap': block_bootstrap,
         'factors': factor_attribution, 'promotion': promotion_evidence})
