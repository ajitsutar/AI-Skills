"""Pure, source-scoped market-flow and short-position evidence diagnostics.

No network, trading authority, calibrated prediction or investor-identification
inference is implemented here. See references/market-flow.md for the contract.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import math


LIMITS = [
    'Source identity, rights and supplied observations are declarations, not authenticated facts.',
    'Missing observations are unknown, never zero or evidence of no activity.',
    'Feeds are analyzed separately; overlapping feeds must not be summed.',
    'Print size and quote location do not establish aggressor, investor identity, open/close intent or information advantage.',
    'Dated short interest, borrow-provider snapshots and daily short volume measure different populations and times.',
    'No squeeze probability, causal confirmation, trading recommendation or execution authority is produced.',
]


def _number(value, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('FINITE_NUMBER_REQUIRED')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('FINITE_NUMBER_REQUIRED') from exc
    if not result.is_finite() or not math.isfinite(float(result)):
        raise ValueError('FINITE_NUMBER_REQUIRED')
    if minimum is not None and result < Decimal(str(minimum)):
        raise ValueError('NUMBER_BELOW_MINIMUM')
    if maximum is not None and result > Decimal(str(maximum)):
        raise ValueError('NUMBER_ABOVE_MAXIMUM')
    return result


def _positive(value):
    result = _number(value, 0)
    if result == 0:
        raise ValueError('POSITIVE_NUMBER_REQUIRED')
    return result


def _value(value):
    if value is None:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('RESULT_OUT_OF_FINITE_RANGE')
    return result


def _time(value):
    if not isinstance(value, str) or 'T' not in value:
        raise ValueError('EXACT_TIMESTAMP_REQUIRED')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('EXACT_TIMESTAMP_REQUIRED') from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return result


def _day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError('ISO_DATE_REQUIRED')
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('ISO_DATE_REQUIRED') from exc


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('NONEMPTY_SCOPE_REQUIRED')
    return value


def _volume_basis(value):
    """An absent or explicitly unresolved declaration cannot establish a match."""
    if not isinstance(value, str) or not value.strip():
        return None
    if value.strip().casefold() in {'unknown', 'unresolved', 'unspecified', 'n/a', 'na', '--', '?'}:
        return None
    return value


def _identity(record):
    p = record['payload']
    return (record.get('ticker'), p.get('issuer_id'), p.get('share_class'))


def _complete_identity(record):
    return all(isinstance(x, str) and x.strip() for x in _identity(record))


def _issue(issues, record, code):
    issues.append({'record_id': record.get('id'), 'code': code})


def _base(document, kind):
    # Lazy import keeps ownership of common revisions and eligibility in module A.
    from market_sources import normalize
    normalized = normalize(document)
    settings = document.get('settings', {})
    if not isinstance(settings, dict):
        raise ValueError('SETTINGS_OBJECT_REQUIRED')
    return normalized, settings, _time(normalized['as_of']), {
        'schema_version': 1, 'kind': kind, 'as_of': normalized['as_of'],
        'execution_authorized': False, 'issues': deepcopy(normalized.get('issues', [])),
        'limitations': list(LIMITS), 'evidence': normalized,
    }


def _observed(record, observed, cutoff):
    if observed > cutoff or observed > _time(record['available_at']):
        raise ValueError('OBSERVATION_AFTER_CUTOFF_OR_AVAILABILITY')


def _deduplicate(records, kind, issues):
    groups = {}
    for record in records:
        p = record['payload']
        if record['kind'] != kind or not record['eligible']:
            continue
        try:
            feed = _text(p.get('feed_id'))
            if kind == 'trade':
                key = (_text(record.get('ticker')), feed, _text(p.get('trade_id')))
                status = p.get('status', 'original')
                if status not in {'original', 'corrected'}:
                    raise ValueError('FEED_STATUS_REQUIRES_COMMON_REVISION_ENVELOPE')
                if status == 'corrected' and record.get('action') != 'replace':
                    raise ValueError('CORRECTION_REQUIRES_REPLACE_ENVELOPE')
            else:
                if p.get('bar_type') != 'cumulative':
                    continue
                key = (_text(record.get('ticker')), feed, _text(p.get('start_at')), _text(p.get('end_at')),
                       _text(p.get('session_id')), _text(p.get('comparison_group')))
            groups.setdefault(key, []).append(record)
        except ValueError as exc:
            _issue(issues, record, str(exc))
    result = []
    for grouped in groups.values():
        try:
            payloads = {json.dumps(x['payload'], sort_keys=True, allow_nan=False) for x in grouped}
        except (ValueError, TypeError):
            for record in grouped:
                _issue(issues, record, 'JSON_FINITE_PAYLOAD_REQUIRED')
            continue
        if len(payloads) > 1:
            for record in grouped:
                _issue(issues, record, 'CONFLICTING_FEED_IDENTITY_REQUIRES_REVISION')
            continue
        chosen = min(grouped, key=lambda x: x['id'])
        result.append(chosen)
        for record in grouped:
            if record is not chosen:
                _issue(issues, record, 'DUPLICATE_WITHIN_FEED_NOT_COUNTED')
    return result


def _quote(record, event, price, settings, issues):
    p = record['payload']
    result = {'bid': None, 'ask': None, 'spread': None, 'spread_bps': None,
              'quote_age_seconds': None, 'execution_location': 'UNKNOWN',
              'age_exceeds_declared_limit': None}
    if not any(p.get(k) is not None for k in ('bid', 'ask', 'quote_at')):
        return result
    try:
        bid, ask, observed = _positive(p.get('bid')), _positive(p.get('ask')), _time(p.get('quote_at'))
        if ask < bid:
            raise ValueError('CROSSED_QUOTE')
        if observed > event:
            raise ValueError('QUOTE_AFTER_TRADE')
        age = Decimal(str((event - observed).total_seconds()))
        midpoint = (ask + bid) / 2
        location = ('LOCKED_QUOTE' if bid == ask else 'ABOVE_ASK' if price > ask else
                    'AT_ASK' if price == ask else 'BELOW_BID' if price < bid else
                    'AT_BID' if price == bid else 'BETWEEN')
        result.update(bid=_value(bid), ask=_value(ask), spread=_value(ask - bid),
                      spread_bps=_value((ask - bid) / midpoint * 10000),
                      quote_age_seconds=_value(age), execution_location=location)
        if settings.get('max_quote_age_seconds') is not None:
            result['age_exceeds_declared_limit'] = age > _number(settings['max_quote_age_seconds'], 0)
            if result['age_exceeds_declared_limit']:
                result['execution_location'] = 'UNKNOWN_STALE_UNDER_DECLARED_LIMIT'
    except (ValueError, TypeError, OverflowError) as exc:
        _issue(issues, record, 'UNUSABLE_QUOTE: ' + str(exc))
    return result


def analyze(document):
    """Compare actual prints and supplied cumulative windows within each feed."""
    normalized, settings, cutoff, out = _base(document, 'MARKET_FLOW')
    threshold = settings.get('print_percentile_threshold')
    threshold = _number(threshold, 0, 100) if threshold is not None else None
    if settings.get('max_quote_age_seconds') is not None:
        _number(settings['max_quote_age_seconds'], 0)
    trades, bars = [], []
    for record in _deduplicate(normalized['records'], 'trade', out['issues']):
        p = record['payload']
        try:
            event = _time(p.get('event_at')); _observed(record, event, cutoff)
            quantity, price = _positive(p.get('quantity')), _positive(p.get('price'))
            if p.get('quantity_unit') != 'shares' or p.get('role') not in {'current', 'baseline'}:
                raise ValueError('TRADE_UNIT_OR_ROLE_UNSUPPORTED')
            key = (_identity(record), p['feed_id'], _text(p.get('currency')),
                   p['quantity_unit'], _text(p.get('comparison_group')))
            trades.append((record, key, event, quantity, price))
        except (ValueError, TypeError, OverflowError) as exc:
            _issue(out['issues'], record, 'UNUSABLE_TRADE: ' + str(exc))
    out['prints'] = []
    for record, key, event, quantity, price in trades:
        p = record['payload']
        baseline = [x for x in trades if x[1] == key and x[0]['payload']['role'] == 'baseline' and x[2] < event]
        n = len(baseline) if p['role'] == 'current' else 0
        percentile = Decimal(sum(x[3] <= quantity for x in baseline)) / n * 100 if n else None
        notional = quantity * price
        notional_rank = Decimal(sum(x[3] * x[4] <= notional for x in baseline)) / n * 100 if n else None
        out['prints'].append({
            'record_id': record['id'], 'ticker': record.get('ticker'), 'issuer_id': p.get('issuer_id'),
            'share_class': p.get('share_class'), 'feed_id': p['feed_id'], 'role': p['role'],
            'quantity': _value(quantity), 'quantity_unit': 'shares', 'price': _value(price),
            'notional': _value(notional), 'currency': p['currency'], 'event_at': p['event_at'],
            'baseline_record_ids': [x[0]['id'] for x in baseline] if n else [], 'baseline_count': n,
            'quantity_percentile': _value(percentile), 'notional_percentile': _value(notional_rank),
            'percentile_convention': '100 * count(baseline <= current) / baseline_count',
            'declared_large_print_flag': percentile >= threshold if percentile is not None and threshold is not None else None,
            'aggressor_side': 'UNKNOWN', 'investor_identity': 'UNKNOWN', 'open_close_intent': 'UNKNOWN',
            'quote_context': _quote(record, event, price, settings, out['issues']),
        })
    for record in _deduplicate(normalized['records'], 'bar', out['issues']):
        p = record['payload']
        try:
            start, end = _time(p.get('start_at')), _time(p.get('end_at'))
            _observed(record, end, cutoff)
            if end <= start or p.get('role') not in {'current', 'baseline', 'benchmark'}:
                raise ValueError('BAR_INTERVAL_OR_ROLE_INVALID')
            currency, group = _text(p.get('currency')), _text(p.get('comparison_group'))
            _text(p.get('session_id'))
            volume = _number(p['volume'], 0) if p.get('volume') is not None else None
            if p['role'] != 'benchmark' and (volume is None or p.get('volume_unit') != 'shares'):
                raise ValueError('SHARE_VOLUME_REQUIRED')
            basis = _volume_basis(p.get('volume_basis'))
            if p['role'] != 'benchmark' and basis is None:
                _issue(out['issues'], record, 'RELATIVE_VOLUME_BASIS_UNKNOWN_OR_UNRESOLVED')
            key = (_identity(record), p['feed_id'], currency, group, p.get('volume_unit'),
                   basis, (end - start).total_seconds(),
                   start.timetz().isoformat(), end.timetz().isoformat())
            bars.append((record, key, start, end, volume))
        except (ValueError, TypeError, OverflowError) as exc:
            _issue(out['issues'], record, 'UNUSABLE_BAR: ' + str(exc))
    index = {x[0]['id']: x for x in bars}
    out['cumulative_bars'] = []
    for record, key, start, end, volume in bars:
        p = record['payload']
        basis = _volume_basis(p.get('volume_basis'))
        baseline = [x for x in bars if basis is not None and x[1] == key and x[0]['payload']['role'] == 'baseline'
                    and x[3] < start and x[0]['payload']['session_id'] != p['session_id']]
        sessions = [x[0]['payload']['session_id'] for x in baseline]
        if len(set(sessions)) != len(sessions):
            _issue(out['issues'], record, 'AMBIGUOUS_BASELINE_SESSION_NOT_POOLED')
            baseline = []
        mean = sum((x[4] for x in baseline), Decimal(0)) / len(baseline) if baseline else None
        rvol = volume / mean if p['role'] == 'current' and volume is not None and mean is not None and mean > 0 else None
        rvol_status = ('NOT_CURRENT' if p['role'] != 'current' else
                       'VOLUME_BASIS_UNKNOWN_OR_UNRESOLVED' if basis is None else
                       'NO_COMPARABLE_BASELINE' if mean is None else
                       'ZERO_BASELINE_VOLUME' if mean == 0 else
                       'COMPUTED_FROM_MATCHED_DECLARED_BASIS')
        own_return, benchmark_return, relative_return = None, None, None
        benchmark_id = p.get('benchmark_record_id')
        try:
            if p.get('start_price') is not None or p.get('end_price') is not None:
                own_return = (_positive(p.get('end_price')) / _positive(p.get('start_price')) - 1) * 100
            if benchmark_id is not None:
                other = index.get(benchmark_id)
                if other is None:
                    raise ValueError('BENCHMARK_UNAVAILABLE')
                bp = other[0]['payload']
                if (bp['role'] != 'benchmark' or (start, end) != (other[2], other[3]) or
                        p['currency'] != bp['currency'] or not p.get('price_basis') or
                        p['price_basis'] != bp.get('price_basis')):
                    raise ValueError('BENCHMARK_WINDOW_CURRENCY_OR_PRICE_BASIS_MISMATCH')
                benchmark_return = (_positive(bp.get('end_price')) / _positive(bp.get('start_price')) - 1) * 100
                relative_return = own_return - benchmark_return if own_return is not None else None
        except (ValueError, TypeError, OverflowError) as exc:
            _issue(out['issues'], record, 'UNUSABLE_PRICE_CONTEXT: ' + str(exc))
        out['cumulative_bars'].append({
            'record_id': record['id'], 'ticker': record.get('ticker'), 'issuer_id': p.get('issuer_id'),
            'share_class': p.get('share_class'), 'feed_id': p['feed_id'], 'role': p['role'],
            'start_at': p['start_at'], 'end_at': p['end_at'], 'elapsed_seconds': (end - start).total_seconds(),
            'volume': _value(volume), 'volume_unit': p.get('volume_unit'),
            'volume_basis': deepcopy(p.get('volume_basis')),
            'baseline_record_ids': [x[0]['id'] for x in baseline] if p['role'] == 'current' else [],
            'baseline_sessions': len(baseline) if p['role'] == 'current' else 0,
            'baseline_mean_volume': _value(mean) if p['role'] == 'current' else None,
            'relative_volume': _value(rvol), 'relative_volume_status': rvol_status,
            'return_percent': _value(own_return),
            'benchmark_record_id': benchmark_id, 'benchmark_return_percent': _value(benchmark_return),
            'benchmark_relative_return_percent': _value(relative_return),
        })
    out['declared_settings'] = deepcopy(settings)
    out['summary'] = {'eligible_trade_count': len(trades), 'eligible_bar_count': len(bars),
                      'feed_count': len({x[0]['payload']['feed_id'] for x in trades + bars})}
    out['limitations'] += [
        'comparison_group declares a comparable print filter/market/session and adjustment convention; it is not independently certified.',
        'Empirical ranks describe only retained prior baseline prints, not the whole market or a calibrated tail probability.',
        'Relative volume requires an explicit resolved matching volume basis and uses supplied prior sessions at exactly the same elapsed window; no full-day extrapolation.',
        'Benchmark-relative return is a difference in percentage points over identical windows, not causal alpha.',
    ]
    return out


def _adv(record, index, cutoff):
    p = record['payload']; requested = p.get('adv_record_ids')
    result = {'average_daily_volume': None, 'window_start': None, 'window_end': None,
              'record_ids': [], 'sessions_observed': 0, 'window_coverage': 'UNKNOWN',
              'days_to_cover': None, 'conditional_days_to_cover': None,
              'share_adjustment_comparability': 'UNKNOWN',
              'supplied_volume_arithmetic_mean': None, 'unreconciled_share_count_quotient': None}
    if requested is None:
        return result
    if not isinstance(requested, list) or not requested or len(set(requested)) != len(requested):
        raise ValueError('UNIQUE_ADV_RECORD_IDS_REQUIRED')
    window = p.get('adv_window')
    if not isinstance(window, dict):
        raise ValueError('DECLARED_ADV_WINDOW_REQUIRED')
    start, end = _day(window.get('start_date')), _day(window.get('end_date'))
    observed_date = _day(p.get('settlement_date') or p.get('measurement_date'))
    if start > end or end > observed_date:
        raise ValueError('ADV_WINDOW_AFTER_SHORT_INTEREST_MEASUREMENT')
    volumes, sessions, feeds, bases = [], [], set(), []
    for rid in requested:
        other = index.get(rid)
        if other is None or other['kind'] != 'bar':
            raise ValueError('ADV_RECORD_UNAVAILABLE')
        bp = other['payload']; day = _day(bp.get('session_date'))
        if (bp.get('bar_type') != 'daily_volume' or bp.get('volume_unit') != 'shares' or
                not _complete_identity(record) or _identity(other) != _identity(record) or
                not start <= day <= end or day > _time(other['available_at']).date()):
            raise ValueError('ADV_SCOPE_DATE_OR_UNIT_MISMATCH')
        volumes.append(_number(bp.get('volume'), 0)); sessions.append(day.isoformat())
        feeds.add(_text(bp.get('feed_id')))
        bases.append(bp.get('adjustment_basis'))
    if len(feeds) != 1 or len(set(sessions)) != len(sessions):
        raise ValueError('ADV_OVERLAPPING_FEEDS_OR_DUPLICATE_SESSIONS_NOT_POOLED')
    expected = window.get('expected_sessions')
    coverage = 'UNVERIFIED_SUPPLIED_SESSIONS_ONLY'
    if expected is not None:
        if not isinstance(expected, list) or not expected or len(set(expected)) != len(expected):
            raise ValueError('UNIQUE_EXPECTED_ADV_SESSIONS_REQUIRED')
        if any(not start <= _day(x) <= end for x in expected):
            raise ValueError('EXPECTED_ADV_SESSION_OUTSIDE_WINDOW')
        coverage = 'COMPLETE_DECLARED_SESSIONS' if set(sessions) == set(expected) else 'INCOMPLETE_DECLARED_SESSIONS'
    average = sum(volumes, Decimal(0)) / len(volumes)
    dtc = _number(p['short_interest_shares'], 0) / average if average > 0 else None
    declared = [p.get('adjustment_basis')] + bases
    known = all(isinstance(v, str) and v.strip() for v in declared)
    comparable = known and all(v == declared[0] for v in declared)
    compatibility = 'MATCHED_DECLARED_SHARE_BASIS' if comparable else 'MISMATCH' if known else 'UNKNOWN'
    result.update(average_daily_volume=_value(average) if comparable else None,
                  supplied_volume_arithmetic_mean=_value(average),
                  share_adjustment_comparability=compatibility,
                  declared_daily_share_bases=bases, short_interest_share_basis=p.get('adjustment_basis'),
                  window_start=start.isoformat(), window_end=end.isoformat(),
                  record_ids=requested, sessions_observed=len(sessions), feed_id=next(iter(feeds)),
                  window_coverage=coverage,
                  conditional_days_to_cover=_value(dtc) if comparable else None,
                  unreconciled_share_count_quotient=_value(dtc) if not comparable else None,
                  days_to_cover=_value(dtc) if coverage == 'COMPLETE_DECLARED_SESSIONS' and comparable else None)
    return result


def _reported_days_to_cover(record, issues):
    """Preserve parser's explicit reported field and the legacy supplied alias."""
    p = record['payload']
    supplied = {k: deepcopy(p[k]) for k in ('reported_days_to_cover', 'days_to_cover') if k in p}
    try:
        parsed = [_number(v, 0) if v is not None else None for v in supplied.values()]
        if len(parsed) == 2 and parsed[0] != parsed[1]:
            raise ValueError('CONFLICTING_PROVIDER_REPORTED_DAYS_TO_COVER_ALIASES')
        return _value(parsed[0]) if parsed else None, supplied
    except (ValueError, TypeError, OverflowError) as exc:
        _issue(issues, record, 'UNUSABLE_PROVIDER_REPORTED_DAYS_TO_COVER: ' + str(exc))
        return None, supplied


def positioning(document):
    """Keep dated positions, stock-lending scopes, short flow and fails separate."""
    normalized, settings, cutoff, out = _base(document, 'MARKET_POSITIONING')
    active = [x for x in normalized['records'] if x['eligible']]
    index = {x['id']: x for x in active}
    out.update(short_interest=[], borrow=[], short_sale_volume=[], failures_to_deliver=[])
    for record in active:
        p = record['payload']; kind = record['kind']
        try:
            if kind == 'short_interest':
                measurement = _day(p.get('settlement_date') or p.get('measurement_date'))
                if measurement > cutoff.date() or measurement > _time(record['available_at']).date():
                    raise ValueError('SHORT_INTEREST_MEASUREMENT_AFTER_CUTOFF_OR_AVAILABILITY')
                shares = _number(p.get('short_interest_shares'), 0)
                reported_dtc, dtc_fields = _reported_days_to_cover(record, out['issues'])
                row = {'record_id': record['id'], 'ticker': record.get('ticker'),
                       'issuer_id': p.get('issuer_id'), 'share_class': p.get('share_class'),
                       'measurement_date': measurement.isoformat(), 'settlement_date': p.get('settlement_date'),
                       'available_at': record['available_at'], 'source_id': record['source']['id'],
                       'measurement_age_days': (cutoff.date() - measurement).days,
                       'measure_basis': p.get('measure_basis', 'UNKNOWN'),
                       'measurement_scope': p.get('measurement_scope'), 'adjustment_basis': p.get('adjustment_basis'),
                       'short_interest_shares': _value(shares), 'short_interest_percent_float': None,
                       'float_record_id': p.get('float_record_id'), 'float_shares': None,
                       'float_effective_date': None, 'float_measure_basis': None,
                       'provider_reported_days_to_cover': reported_dtc,
                       'provider_reported_days_to_cover_fields': dtc_fields,
                       'provider_reported_average_daily_volume': p.get('average_daily_volume')}
                if p.get('float_record_id') is not None:
                    other = index.get(p['float_record_id'])
                    try:
                        if other is None or other['kind'] != 'float':
                            raise ValueError('FLOAT_RECORD_UNAVAILABLE')
                        fp = other['payload']; effective = _day(fp.get('effective_date'))
                        if (not _complete_identity(record) or _identity(other) != _identity(record) or
                                fp.get('share_basis') != 'float' or effective > measurement or
                                effective > _time(other['available_at']).date() or not p.get('adjustment_basis') or
                                p['adjustment_basis'] != fp.get('adjustment_basis')):
                            raise ValueError('FLOAT_ISSUER_CLASS_DATE_OR_ADJUSTMENT_MISMATCH')
                        floating = _positive(fp.get('float_shares'))
                        row.update(float_shares=_value(floating), float_effective_date=effective.isoformat(),
                                   float_measure_basis=fp.get('measure_basis', 'UNKNOWN'),
                                   short_interest_percent_float=_value(shares / floating * 100))
                    except (ValueError, TypeError, OverflowError) as exc:
                        _issue(out['issues'], record, 'UNUSABLE_FLOAT: ' + str(exc))
                try:
                    row['adv'] = _adv(record, index, cutoff)
                except (ValueError, TypeError, OverflowError) as exc:
                    row['adv'] = {'average_daily_volume': None, 'days_to_cover': None,
                                  'conditional_days_to_cover': None, 'window_coverage': 'UNUSABLE'}
                    _issue(out['issues'], record, 'UNUSABLE_ADV: ' + str(exc))
                out['short_interest'].append(row)
            elif kind == 'borrow':
                observed = _time(p.get('observed_at')); _observed(record, observed, cutoff)
                provider, scope = _text(p.get('provider')), _text(p.get('provider_scope'))
                row = {'record_id': record['id'], 'ticker': record.get('ticker'), 'issuer_id': p.get('issuer_id'),
                       'share_class': p.get('share_class'), 'provider': provider, 'provider_scope': scope,
                       'observed_at': p['observed_at'], 'fee_rate_annual_percent': None,
                       'shares_available': None, 'utilization_percent': None}
                for field in ['fee_rate_annual_percent', 'shares_available', 'utilization_percent']:
                    if p.get(field) is not None:
                        row[field] = _value(_number(p[field], 0 if field != 'fee_rate_annual_percent' else None,
                                                    100 if field == 'utilization_percent' else None))
                out['borrow'].append(row)
            elif kind == 'short_sale_volume':
                day = _day(p.get('trade_date'))
                if day > cutoff.date() or day > _time(record['available_at']).date() or p.get('volume_unit') != 'shares':
                    raise ValueError('SHORT_VOLUME_DATE_OR_UNIT_INVALID')
                short, total = _number(p.get('short_volume'), 0), _number(p.get('total_volume'), 0)
                exempt = _number(p['short_exempt_volume'], 0) if p.get('short_exempt_volume') is not None else None
                if short > total or exempt is not None and exempt > short:
                    raise ValueError('SHORT_VOLUME_COMPONENTS_INVALID')
                out['short_sale_volume'].append({'record_id': record['id'], 'ticker': record.get('ticker'),
                    'trade_date': p['trade_date'], 'short_volume': _value(short),
                    'short_exempt_volume': _value(exempt), 'total_volume': _value(total),
                    'reported_short_volume_ratio': _value(short / total) if total > 0 else None,
                    'coverage': p.get('coverage', 'UNKNOWN'), 'market': p.get('market'),
                    'short_exempt_already_in_short_volume': True, 'outstanding_short_position_change': None})
            elif kind == 'ftd':
                day = _day(p.get('settlement_date'))
                if day > cutoff.date() or day > _time(record['available_at']).date():
                    raise ValueError('FAILS_SETTLEMENT_AFTER_CUTOFF_OR_AVAILABILITY')
                out['failures_to_deliver'].append({'record_id': record['id'], 'ticker': record.get('ticker'),
                    'settlement_date': p['settlement_date'], 'quantity': _value(_number(p.get('quantity'), 0)),
                    'balance_semantics': p.get('balance_semantics', 'UNKNOWN'),
                    'naked_shorting_established': False, 'forced_buy_in_date': None})
        except (ValueError, TypeError, OverflowError) as exc:
            _issue(out['issues'], record, 'UNUSABLE_POSITIONING_RECORD: ' + str(exc))
    out['limitations'] += [
        'Short-interest measurement/settlement date is separate from publication, retrieval and availability; it is not a live position.',
        'Percent float uses an explicitly linked same-issuer/class dated float and matching adjustment basis; dilution and later floats must not be backfilled.',
        'Days to cover is short shares divided by average daily share volume, not a deadline or prediction. Incomplete/unverified supplied sessions stay conditional.',
        'Borrow availability, fees and utilization describe only the named provider scope; no market-wide zero, locate, borrow approval or executable quote is inferred.',
        'FINRA short volume includes short-exempt volume; the daily reported subset is not short interest, directional net flow or proof of a new bearish position.',
        'FTD quantities are dated balances, never summed across dates; long and short sales can fail. No naked-shorting proof or countdown is inferred.',
    ]
    return out


def squeeze(document):
    """Evidence triage using explicitly supplied, uncalibrated screening rules."""
    normalized, settings, cutoff, out = _base(document, 'SQUEEZE_EVIDENCE')
    criteria = settings.get('squeeze_criteria', {})
    permitted = {'min_short_interest_percent_float', 'min_days_to_cover',
                 'min_relative_volume', 'min_benchmark_relative_return_percent'}
    if not isinstance(criteria, dict) or set(criteria) - permitted:
        raise ValueError('UNSUPPORTED_SQUEEZE_CRITERIA')
    rules = {k: _number(v, 0) for k, v in criteria.items()}
    flow, positions = analyze(document), positioning(document)
    out['issues'] += flow['issues'] + positions['issues']
    out.update(criteria=deepcopy(criteria), assessments=[], retrospective_short_interest_changes=[], reported_covering=[])
    position_fields = {'min_short_interest_percent_float': 'short_interest_percent_float', 'min_days_to_cover': 'days_to_cover'}
    for si in positions['short_interest']:
        identity = (si['ticker'], si['issuer_id'], si['share_class'])
        complete = all(isinstance(x, str) and x.strip() for x in identity)
        checks = []
        for name, field in position_fields.items():
            if name in rules:
                value = si['adv']['days_to_cover'] if field == 'days_to_cover' else si[field]
                checks.append({'criterion': name, 'value': value, 'threshold': _value(rules[name]),
                               'met': _number(value) >= rules[name] if value is not None else None})
        candidate = (bool(checks) and complete and _number(si['short_interest_shares']) > 0
                     and si['measure_basis'] in {'official_reported', 'vendor_estimate'}
                     and all(x['met'] is True for x in checks))
        contexts = []
        for bar in flow['cumulative_bars']:
            if bar['role'] != 'current' or (bar['ticker'], bar['issuer_id'], bar['share_class']) != identity:
                continue
            if _day(si['measurement_date']) > _time(bar['end_at']).date():
                out['issues'].append({'record_id': bar['record_id'],
                                      'code': 'SHORT_INTEREST_MEASUREMENT_AFTER_FLOW_WINDOW'})
                continue
            volume, relative = bar['relative_volume'], bar['benchmark_relative_return_percent']
            v_rule, r_rule = rules.get('min_relative_volume'), rules.get('min_benchmark_relative_return_percent')
            pressure = (candidate and v_rule is not None and r_rule is not None and volume is not None and relative is not None
                        and _number(volume) > 1 and _number(relative) > 0 and _number(volume) >= v_rule and _number(relative) >= r_rule)
            contexts.append({'record_id': bar['record_id'], 'feed_id': bar['feed_id'],
                             'relative_volume': volume, 'benchmark_relative_return_percent': relative,
                             'declared_pressure_rules_met': bool(pressure)})
        state = ('DEVELOPING_PRESSURE_HEURISTIC' if any(x['declared_pressure_rules_met'] for x in contexts) else
                 'DATED_POSITIONING_CANDIDATE' if candidate else 'INSUFFICIENT_EVIDENCE')
        out['assessments'].append({'short_interest_record_id': si['record_id'], 'ticker': si['ticker'],
                                  'issuer_id': si['issuer_id'], 'share_class': si['share_class'],
                                  'state': state, 'measure_basis': si['measure_basis'],
                                  'measurement_date': si['measurement_date'], 'measurement_age_days': si['measurement_age_days'],
                                  'positioning_checks': checks, 'flow_contexts': contexts,
                                  'squeeze_confirmed': False, 'probability': None, 'causal_covering_confirmed': False})
    groups = {}
    for si in positions['short_interest']:
        key = (si['ticker'], si['issuer_id'], si['share_class'], si['source_id'], si['measure_basis'],
               si['measurement_scope'], si['adjustment_basis'])
        if all(isinstance(x, str) and x.strip() for x in key) and si['measure_basis'] in {'official_reported', 'vendor_estimate'}:
            groups.setdefault(key, []).append(si)
    raw_index = {x['id']: x for x in normalized['records'] if x['eligible']}
    for items in groups.values():
        dates = [x['measurement_date'] for x in items]
        if len(set(dates)) != len(dates):
            out['issues'].append({'code': 'AMBIGUOUS_SHORT_INTEREST_VINTAGE_NOT_COMPARED', 'record_ids': [x['record_id'] for x in items]})
            continue
        ordered = sorted(items, key=lambda x: x['measurement_date'])
        for earlier, later in zip(ordered, ordered[1:]):
            delta = (_number(raw_index[later['record_id']]['payload']['short_interest_shares']) -
                     _number(raw_index[earlier['record_id']]['payload']['short_interest_shares']))
            out['retrospective_short_interest_changes'].append({
                'earlier_record_id': earlier['record_id'], 'later_record_id': later['record_id'],
                'ticker': later['ticker'], 'measure_basis': later['measure_basis'], 'net_short_share_change': _value(delta),
                'classification': 'REPORTED_NET_SHORT_REDUCTION' if delta < 0 else 'NO_REPORTED_NET_SHORT_REDUCTION',
                'gross_covering_volume': None, 'price_move_cause_confirmed': False})
    for record in normalized['records']:
        if not record['eligible'] or record['kind'] != 'disclosure':
            continue
        p = record['payload']
        if p.get('event_type') != 'short_covering_disclosure':
            continue
        try:
            event = _time(p.get('event_at')); _observed(record, event, cutoff)
            if not _complete_identity(record):
                raise ValueError('COVERING_ISSUER_CLASS_REQUIRED')
            covered = _positive(p.get('covered_shares')); _text(p.get('text_evidence'))
            position_scope = _text(p.get('position_scope'))
            out['reported_covering'].append({'record_id': record['id'], 'ticker': record.get('ticker'),
                'event_at': p['event_at'], 'source_reported_covered_shares': _value(covered),
                'position_scope': position_scope,
                'classification': 'RETROSPECTIVE_SOURCE_REPORTED_COVERING',
                'source_authenticity_verified': False, 'market_wide_covering_confirmed': False,
                'price_move_cause_confirmed': False})
        except (ValueError, TypeError, OverflowError) as exc:
            _issue(out['issues'], record, 'UNUSABLE_COVERING_DISCLOSURE: ' + str(exc))
    out['limitations'] += [
        'No screening thresholds are supplied by default. Caller rules are disclosed heuristics, not calibrated probabilities, permissions or necessary/sufficient squeeze conditions.',
        'Developing pressure requires a dated positioning rule plus both above-baseline volume and positive benchmark-relative price under the declared rules; this still does not establish covering.',
        'A comparable decline in dated net short interest is retrospective net reduction, not gross covering volume or proof covering caused a price rise.',
        'A typed covering disclosure is retained only as a source-reported event, not authenticated identity, market-wide confirmation or proof of causality.',
        'No dealer inventory, options opening/closing intent or gamma squeeze is inferred; options volume/open interest alone cannot establish those facts.',
    ]
    return out
