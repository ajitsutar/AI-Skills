"""Explicit research arithmetic and claim comparisons; no broker actions or gates.

Inputs are declarations, not authenticated observations. These checks cannot
establish causality, validate arbitrary prose, or supply missing market evidence.
"""
from __future__ import annotations

import math
import numpy as np

from quant_common import require


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'FINITE_NUMBER_REQUIRED')
    return float(value)


def covariance_comparison(document):
    """Compare same-order covariance matrices without inventing a scale story."""
    ids = document['asset_ids']
    require(isinstance(ids, list) and ids and len(set(ids)) == len(ids), 'UNIQUE_ASSET_IDS')
    matrices = []
    for key in ('base', 'alternative'):
        raw = document[key]
        require(isinstance(raw, list) and all(isinstance(r, list) for r in raw), 'MATRIX_REQUIRED')
        array = np.array([[number(v) for v in row] for row in raw], dtype=float)
        require(array.shape == (len(ids), len(ids)), 'COVARIANCE_DIMENSION')
        require(np.allclose(array, array.T, rtol=1e-10, atol=1e-12), 'SYMMETRIC_COVARIANCE_REQUIRED')
        require(np.all(np.diag(array) >= 0), 'NONNEGATIVE_VARIANCES_REQUIRED')
        require(np.min(np.linalg.eigvalsh(array)) >= -1e-12, 'PSD_COVARIANCE_REQUIRED')
        matrices.append(array)
    base, alternative = matrices
    rows = [{'asset_id': name, 'base_variance': float(base[i, i]),
             'alternative_variance': float(alternative[i, i]),
             'variance_multiplier': float(alternative[i, i]/base[i, i]) if base[i, i] else None}
            for i, name in enumerate(ids)]
    pairs = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            pairs.append({'numerator_asset': ids[i], 'denominator_asset': ids[j],
                          'base_variance_ratio': float(base[i, i]/base[j, j]) if base[j, j] else None,
                          'alternative_variance_ratio': float(alternative[i, i]/alternative[j, j]) if alternative[j, j] else None})
    largest = np.unravel_index(np.argmax(np.abs(base)), base.shape)
    scale = float(alternative[largest]/base[largest]) if base[largest] != 0 else None
    scaled_absolute_tolerance = 1e-12*float(np.max(np.abs(alternative)))
    pure_scale = bool(scale is not None and math.isfinite(scale) and scale >= 0 and
                      np.allclose(alternative, base*scale, atol=scaled_absolute_tolerance, rtol=1e-10))
    return {'status': 'COMPUTED', 'variances': rows, 'variance_ratios': pairs,
            'pure_nonnegative_scale': pure_scale, 'common_scale': scale if pure_scale else None,
            'scale_test_relative_tolerance': 1e-10, 'scale_test_absolute_tolerance': scaled_absolute_tolerance,
            'measurement_period': document.get('measurement_period'),
            'observation_frequency': document.get('observation_frequency'),
            'interpretation': 'Matrix arithmetic only. Stable fitted weights do not prove unchanged relative risk or identify a causal mechanism.'}


def hedge_scenarios(document):
    """Long equity plus explicit expiry-put or short-linear hedge economics.

    A linear hedge's sensitivity is an assumption, not an estimated beta.
    Option results are expiry payoff, never a pre-expiry price or Greek.
    """
    shares, price = number(document['shares']), number(document['price'])
    require(shares > 0 and price > 0, 'POSITIVE_EQUITY_POSITION')
    currency = document['currency']
    require(isinstance(currency, str) and bool(currency), 'CURRENCY_REQUIRED')
    shocks = [number(x) for x in document['shock_returns']]
    require(shocks and min(shocks) >= -1, 'VALID_EQUITY_SHOCKS')
    notional = shares*price
    results, seen = [], set()
    for hedge in document['hedges']:
        name, kind = hedge['id'], hedge['kind']
        require(isinstance(name, str) and name and name not in seen, 'UNIQUE_HEDGE_IDS')
        seen.add(name)
        fees = number(hedge['total_explicit_cost'])
        require(fees >= 0, 'NONNEGATIVE_EXPLICIT_COST')
        premium, sensitivity = 0.0, None
        if kind == 'expiry_put':
            strike, units, premium_per_unit = (number(hedge[k]) for k in ('strike', 'underlying_units', 'premium_per_unit'))
            require(strike >= 0 and units > 0 and premium_per_unit >= 0, 'VALID_PUT_INPUTS')
            require(hedge['basis'] == 'same_underlying', 'PUT_BASIS_MODEL_REQUIRED')
            premium = units*premium_per_unit
        elif kind == 'short_linear':
            hedge_notional, sensitivity = number(hedge['short_notional']), number(hedge['shock_sensitivity'])
            require(hedge_notional >= 0, 'NONNEGATIVE_SHORT_NOTIONAL')
        else:
            require(kind == 'none', 'UNSUPPORTED_HEDGE_MODEL')
        rows = []
        for shock in shocks:
            terminal_price = price*(1+shock)
            equity_pnl = notional*shock
            if kind == 'expiry_put':
                payoff = max(strike-terminal_price, 0)*units
            elif kind == 'short_linear':
                payoff = -hedge_notional*sensitivity*shock
            else:
                payoff = 0.0
            hedge_pnl = payoff-premium-fees
            rows.append({'shock_return': shock, 'equity_terminal_price': terminal_price,
                         'equity_pnl': equity_pnl, 'hedge_payoff_before_cost': payoff,
                         'premium': premium, 'total_explicit_cost': fees,
                         'hedge_net_pnl': hedge_pnl, 'combined_net_pnl': equity_pnl+hedge_pnl,
                         'combined_pnl_fraction_of_initial_equity': (equity_pnl+hedge_pnl)/notional})
        linear_offset = hedge_notional*sensitivity if kind == 'short_linear' else 0 if kind == 'none' else None
        results.append({'id': name, 'kind': kind, 'scenarios': rows,
                        'linear_hedge_offset': linear_offset,
                        'linear_residual_equity_sensitivity': notional-linear_offset if linear_offset is not None else None,
                        'linear_residual_fraction': (notional-linear_offset)/notional if linear_offset is not None else None})
    return {'status': 'COMPUTED', 'currency': currency, 'equity_notional': notional, 'hedges': results,
            'denominator': 'initial equity shares * initial equity price; excludes any additional premium/collateral funding',
            'limitations': ['Expiry scenario assumptions are not probabilities or guaranteed fills.',
                            'Linear residual sensitivity is not a bound on losses; actual basis can differ.',
                            'Borrow availability, margin, collateral and pre-expiry option value are not established.']}


def compare_claim(document):
    """Check one explicitly typed comparison, leaving absent comparability unknown.

    Each operand has value, unit, denominator, basis, horizon, observation_frequency and
    measurement_period. Null metadata does not mean equal metadata. A caller can
    explicitly declare 'not_applicable' for a dimension that is inapplicable.
    """
    left, right = document['left'], document['right']
    relation = document['relation']
    require(relation in ('lt', 'le', 'gt', 'ge', 'eq'), 'SUPPORTED_RELATION_REQUIRED')
    a, b = number(left['value']), number(right['value'])
    fields = ('unit', 'denominator', 'basis', 'horizon', 'observation_frequency', 'measurement_period')
    require(all(operand.get(key) is None or isinstance(operand[key], str)
                for operand in (left, right) for key in fields), 'METADATA_TEXT_REQUIRED')
    unknown = [key for key in fields if not (left.get(key) or '').strip() or not (right.get(key) or '').strip()]
    mismatch = [key for key in fields if key not in unknown and left[key] != right[key]]
    abs_tol = number(document.get('absolute_tolerance', 1e-8))
    rel_tol = number(document.get('relative_tolerance', 1e-7))
    require(abs_tol >= 0 and rel_tol >= 0, 'NONNEGATIVE_TOLERANCE')
    comparisons = {'lt': a < b, 'le': a <= b, 'gt': a > b, 'ge': a >= b,
                   'eq': abs(a-b) <= abs_tol + rel_tol*max(abs(a), abs(b))}
    return {'status': 'INCOMPARABLE' if mismatch else 'UNKNOWN_COMPARABILITY' if unknown else 'CHECKED',
            'relation': relation, 'left_value': a, 'right_value': b,
            'typed_comparison': None if unknown or mismatch else comparisons[relation],
            'arithmetic_comparison_without_metadata': comparisons[relation],
            'unknown_dimensions': unknown, 'mismatched_dimensions': mismatch,
            'absolute_tolerance': abs_tol, 'relative_tolerance': rel_tol,
            'inequalities_use_exact_boundary': True,
            'limitations': 'Declared operands and metadata only; source authenticity, causality and prose not checked.'}
