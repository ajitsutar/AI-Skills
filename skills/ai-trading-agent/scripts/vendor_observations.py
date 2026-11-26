"""Normalize explicit Yahoo/yfinance screening fields without changing their economic meaning."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path


LABEL = 'VENDOR_APPROXIMATION_NOT_FILING_VERIFIED'
COUNTS = ('strongBuy', 'buy', 'hold', 'sell', 'strongSell')
REVENUE_PROXIES = {'revenueQuarterlyGrowth': 'quarterly_revenue_growth', 'revenueGrowth': 'vendor_revenue_growth'}


def _number(value):
    if isinstance(value, str) and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', value):
        value = float(value)
    if type(value) not in (float, int):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def _count(value):
    if isinstance(value, str) and value.isascii() and value.isdigit() and len(value) <= 10:
        value = int(value)
    return value if type(value) is int and value >= 0 else None


def _field(row, key, unit, output_unit=None, divisor=1, positive=False):
    raw = row.get(key)
    value = _number(raw)
    valid = value is not None and (not positive or value > 0)
    return {'source_field': key, 'reported_value': raw, 'reported_unit': unit,
            'value': value / divisor if valid else None, 'unit': output_unit or unit,
            'status': 'OBSERVED' if valid else 'MISSING_OR_INVALID'}


def _rows(frame):
    if isinstance(frame, list) and all(isinstance(row, dict) for row in frame):
        return frame
    if not isinstance(frame, dict):
        raise ValueError('VENDOR_FRAME_REQUIRES_RECORDS_OR_SPLIT')
    columns, index, data = (frame.get(k) for k in ('columns', 'index', 'data'))
    if not all(isinstance(v, list) for v in (columns, index, data)):
        raise ValueError('VENDOR_FRAME_SPLIT_SCHEMA')
    if (len(index) != len(data) or not all(isinstance(c, str) for c in columns)
            or len(set(columns)) != len(columns)):
        raise ValueError('VENDOR_FRAME_DIMENSIONS')
    rows = []
    for idx, values in zip(index, data):
        if not isinstance(values, list) or len(values) != len(columns):
            raise ValueError('VENDOR_FRAME_DIMENSIONS')
        row = dict(zip(columns, values))
        if 'period' not in row:
            # The growth table may use its *index* as the fiscal bucket. A numeric
            # row index in a recommendation table never substitutes for "0m".
            row['period'] = idx
        rows.append(row)
    return rows


def _period_row(frame, period):
    matched = [r for r in _rows(frame) if r.get('period') == period]
    if len(matched) > 1:
        raise ValueError('AMBIGUOUS_VENDOR_PERIOD:' + period)
    return matched[0] if matched else {}


def normalize(document, revenue_trend_proxy=None):
    info = document.get('info', {})
    if not isinstance(info, dict):
        raise ValueError('VENDOR_INFO_OBJECT_REQUIRED')
    growth = _period_row(document.get('growth_estimates', []), '+1y')
    rec = _period_row(document.get('recommendations', []), '0m')
    growth_key = 'stockTrend' if 'stockTrend' in growth else 'stock'
    if 'stockTrend' in growth and 'stock' in growth and _number(growth['stockTrend']) != _number(growth['stock']):
        raise ValueError('CONFLICTING_VENDOR_STOCK_TREND')
    recommendations = {k: _count(rec.get(k)) for k in COUNTS}
    count_status = ('OBSERVED' if all(v is not None for v in recommendations.values())
                    else 'MISSING_OR_INVALID')
    currency = info.get('currency') or 'quote_currency_unknown'
    fields = {'debt_to_equity': _field(info, 'debtToEquity', 'percent', 'ratio', 100),
              'reference_price': _field(info, 'regularMarketPrice', currency, positive=True),
              'market_cap': _field(info, 'marketCap', currency, positive=True),
              'next_year_earnings_growth': _field(growth, growth_key, 'fraction'),
              'quarterly_revenue_growth': _field(info, 'revenueQuarterlyGrowth', 'fraction'),
              'vendor_revenue_growth': _field(info, 'revenueGrowth', 'fraction')}
    fields['next_year_earnings_growth']['requested_period'] = '+1y'
    if revenue_trend_proxy is not None and revenue_trend_proxy not in REVENUE_PROXIES:
        raise ValueError('UNSUPPORTED_REVENUE_TREND_PROXY')
    proxy = fields[REVENUE_PROXIES[revenue_trend_proxy]] if revenue_trend_proxy is not None else {}
    # The general revenueGrowth observation has no independently established
    # fiscal endpoints. Keep it separate from an absent quarterly observation.
    return {'basis': LABEL, 'fields': fields, 'component_errors': document.get('component_errors', {}),
            'source_sha256': hashlib.sha256(json.dumps(document, sort_keys=True, separators=(',', ':'),
                                            allow_nan=False).encode()).hexdigest(),
            'recommendations': {'provider_period': '0m', 'unit': 'analyst_count',
                                'counts': recommendations, 'status': count_status},
            'ttm_growth_evidence': 'TWO_COMPARABLE_TTM_PERIODS_NOT_ESTABLISHED_BY_VENDOR_GROWTH_FIELDS',
            'revenue_trend_proxy': {'source_field': revenue_trend_proxy, 'value': proxy.get('value'),
                                    'basis': LABEL, 'strict_ttm_gate_satisfied': False,
                                    'status': proxy.get('status', 'NO_PROXY_AUTHORIZED')},
            'market_cap_rescaling': 'INPUTS_AVAILABLE' if all(fields[k]['status'] == 'OBSERVED'
                    for k in ('market_cap', 'reference_price')) else 'UNAVAILABLE_MISSING_PRICE_OR_CAP'}


def contract_check():
    """Check a bundled offline schema fixture. This does not probe a provider."""
    fixture = json.loads((Path(__file__).resolve().parents[1] / 'examples' /
                          'fictional-vendor-observations.json').read_text(encoding='utf-8'))
    result = normalize(fixture)
    fields = result['fields']
    checks = {'debt_percent_to_ratio': (fields['debt_to_equity']['value'] is not None and
                                        math.isclose(fields['debt_to_equity']['value'], .37625)),
              'missing_quote_blocks_rescale': result['market_cap_rescaling'] == 'UNAVAILABLE_MISSING_PRICE_OR_CAP',
              'explicit_growth_period': fields['next_year_earnings_growth']['value'] == .12,
              'recommendation_period': result['recommendations']['counts']['sell'] == 4,
              'revenue_fields_distinct': (fields['quarterly_revenue_growth']['value'] is None
                                         and fields['vendor_revenue_growth']['value'] == .08)}
    return {'status': 'PASS' if all(checks.values()) else 'FAIL', 'scope': 'bundled offline fixtures',
            'checks': checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--revenue-trend-proxy', choices=tuple(REVENUE_PROXIES))
    args = parser.parse_args()
    print(json.dumps(normalize(json.loads(args.input.read_text(encoding='utf-8-sig')), args.revenue_trend_proxy),
                     indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
