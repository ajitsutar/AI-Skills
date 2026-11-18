"""Deterministic, stock-relative unusual-move research diagnostic.

This is an advisory observation, not a return forecast or trading strategy.
It compares the latest completed regular-session bar's absolute open-to-close
return with a nearest-rank empirical percentile from prior complete sessions.
No spread, dollar-price, GARCH, or fixed percentage limit is used.

``evaluate_volatility(context, now)`` returns JSON-safe evidence and an optional
observation refresh time. It never requires authorization, pauses an order or
decides whether execution is permitted. No broker workflow depends on this result.
Source/calendar assertions are audited inputs, not independent verification by
this offline function. Missing evidence means data unavailable, never normal.

Context fields: symbol; optional config; source; sessions; bars; current_bar.
Source requires symbol, provider, evidence_ref, retrieved_at (or as_of), basis
(unadjusted or split_adjusted), interval_minutes, corporate_actions_verified=True.
Optional sessions are chronological {session_id, open, close} calendar records;
otherwise the existing exchange calendar derives them locally. Bars contain
start/end/open/close; optional session_id/symbol/basis must match their source.
Historical gaps, interpolated bars, overnight intervals, and partial intervals are excluded, never
interpolated or rescaled. Only the configured minimum valid sample count is
required; coverage is disclosed. The current bar is supplied separately. The
entire current session is excluded from the historical distribution.

CLI: JSON stdin {"context": {...}, "now": "...+00:00"}; JSON stdout result.
Exit 0 returns an advisory result, including unusual moves or unavailable evidence.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException, ROUND_CEILING, localcontext
import hashlib
import json
import sys


DEFAULT_CONFIG = {
    'lookback_sessions': 20,
    'interval_minutes': 5,
    'percentile': '99',
    'min_samples': 100,
    'max_age_seconds': 900,
    'exchange': 'XNYS',
}


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('Timestamp must include its timezone')
    return value.astimezone(timezone.utc)


def _decimal(value):
    if isinstance(value, bool):
        raise ValueError('Boolean is not a numeric value')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('Numeric values must be finite')
    return result


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' must be a nonempty string')
    return value


def _number_text(value):
    return format(value.normalize(), 'f') if value else '0'


def normalize_config(supplied=None):
    """Return the exact normalized configuration to bind to approval."""
    if supplied is None:
        supplied = {}
    if not isinstance(supplied, dict):
        raise ValueError('config must be an object')
    if set(supplied) - set(DEFAULT_CONFIG):
        raise ValueError('Unknown volatility configuration field')
    config = dict(DEFAULT_CONFIG, **supplied)
    for key in ('lookback_sessions', 'interval_minutes', 'min_samples', 'max_age_seconds'):
        number = _decimal(config[key])
        if number <= 0 or number != number.to_integral_value():
            raise ValueError(key + ' must be a positive integer')
        config[key] = int(number)
    percentile = _decimal(config['percentile'])
    if not 0 < percentile <= 100:
        raise ValueError('percentile must be greater than zero and at most 100')
    config['percentile'] = _number_text(percentile)
    config['exchange'] = _text(config['exchange'], 'exchange')
    return config


def _bar(raw, source, sessions, interval, *, historical=False):
    if not isinstance(raw, dict):
        raise ValueError('Each bar must be an object')
    if raw.get('symbol', source['symbol']) != source['symbol']:
        raise ValueError('Bar symbol does not match source')
    if raw.get('basis', source['basis']) != source['basis']:
        raise ValueError('Bar adjustment basis does not match source')
    start, end = _time(raw['start']), _time(raw['end'])
    opened, closed = _decimal(raw['open']), _decimal(raw['close'])
    if opened <= 0 or closed <= 0:
        raise ValueError('Bar prices must be positive')
    if 'interpolated' in raw and type(raw['interpolated']) is not bool:
        raise ValueError('Bar interpolated flag must be Boolean')
    if raw.get('interpolated') is True:
        if historical:
            return None
        raise ValueError('Interpolated current bar contains no observed interval movement')
    if raw.get('complete', True) is not True:
        if historical:
            return None
        raise ValueError('Incomplete bar cannot establish current volatility')
    matching = [key for key, (opened_at, closed_at) in sessions.items()
                if opened_at <= start < end <= closed_at]
    if not matching:
        if historical:
            return None
        raise ValueError('Bar is outside a single regular session')
    session_id = matching[0]
    if raw.get('session_id', session_id) != session_id:
        raise ValueError('Bar session_id does not match its exchange-calendar timestamps')
    session_open, session_close = sessions[session_id]
    if (end - start != interval or start < session_open or end > session_close
            or (start - session_open) % interval != timedelta(0)):
        if historical:
            return None
        raise ValueError('Bar is not an exact within-session interval')
    return session_id, start, end, (closed / opened - 1) * 100


def evaluate_volatility(context, now):
    """Return an advisory volatility observation without any I/O.

    This is advisory research and never permits or blocks execution.
    ``within_historical_range`` describes the analytical threshold. ``excessive_volatility`` is
    an observed move strictly above the stock's empirical threshold.
    ``data_unavailable`` calls for corrected/fresh data, not a high-vol claim.
    Reason messages contain validation facts and never dump input payloads.
    """
    evidence = {'method': 'absolute_interval_return_nearest_rank',
                'interpretation': 'Execution observation; not a prediction of profit or loss.'}
    try:
        with localcontext() as arithmetic:
            arithmetic.prec = 50
            result = _evaluate(context, now, evidence)
            result.update(advisory_only=True, enforces_execution=False)
            return result
    except (KeyError, TypeError, ValueError, DecimalException, OverflowError, ZeroDivisionError,
            ImportError) as exc:
        reason = ('Missing required field: ' + str(exc.args[0])) if isinstance(exc, KeyError) else str(exc)
        return {'within_historical_range': None, 'status': 'data_unavailable', 'reasons': [reason],
                'evidence': evidence, 'observation_refresh_after': None, 'advisory_only': True, 'enforces_execution': False}


def _evaluate(context, now, evidence):
    if not isinstance(context, dict):
        raise ValueError('Volatility context must be an object')
    now = _time(now)
    symbol = _text(context['symbol'], 'symbol')
    config = normalize_config(context.get('config', {}))
    evidence.update(symbol=symbol, config=config,
                    config_hash=hashlib.sha256(json.dumps(config, sort_keys=True,
                                                         separators=(',', ':')).encode()).hexdigest())
    interval = timedelta(minutes=config['interval_minutes'])
    maximum_age = timedelta(seconds=config['max_age_seconds'])
    source = context['source']
    if not isinstance(source, dict):
        raise ValueError('source must be an object')
    if source['symbol'] != symbol:
        raise ValueError('Source symbol does not match requested instrument')
    if source['basis'] not in ('unadjusted', 'split_adjusted'):
        raise ValueError('Source adjustment basis must be unadjusted or split_adjusted')
    if source.get('corporate_actions_verified') is not True:
        raise ValueError('Corporate-action comparability has not been verified')
    if _decimal(source['interval_minutes']) != config['interval_minutes']:
        raise ValueError('Source interval does not match configured interval')
    retrieved = _time(source.get('retrieved_at', source.get('as_of')))
    evidence['source'] = {key: _text(source[key], key)
                          for key in ('provider', 'evidence_ref', 'basis')}
    evidence['source']['retrieved_at'] = retrieved.isoformat()
    if not timedelta(0) <= now - retrieved < maximum_age:
        raise ValueError('Source retrieval is future-dated or stale')

    raw_sessions = context.get('sessions')
    if raw_sessions is None:
        from trading_calendar import sessions as calendar_sessions
        # Calendar lookup is local. The range is generously larger than N
        # trading sessions; only the last N real sessions enter the baseline.
        start_date = (now - timedelta(days=max(60, config['lookback_sessions'] * 3))).date()
        raw_sessions = calendar_sessions(start_date, now.date(), config['exchange'])
        raw_sessions = [dict(row, session_id=row['date']) for row in raw_sessions]
        evidence['calendar_source'] = 'exchange_calendars/' + config['exchange']
    else:
        evidence['calendar_source'] = source.get('calendar_evidence_ref', 'caller_supplied_session_records')
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise ValueError('sessions must be a nonempty chronological list')
    sessions, previous_close = {}, None
    for session in raw_sessions:
        if not isinstance(session, dict):
            raise ValueError('Each session must be an object')
        session_id = _text(session.get('session_id', session.get('date')), 'session_id')
        opened, closed = _time(session['open']), _time(session['close'])
        if (session_id in sessions or opened >= closed
                or previous_close is not None and opened < previous_close):
            raise ValueError('Sessions are duplicate, overlapping, or not chronological')
        sessions[session_id] = opened, closed
        previous_close = closed

    current = _bar(context['current_bar'], source, sessions, interval)
    current_id, _, current_end, current_move = current
    session_open, session_close = sessions[current_id]
    if not session_open <= now < session_close:
        raise ValueError('Current regular session is not open')
    expected_end = session_open + ((now - session_open) // interval) * interval
    if expected_end == session_open:
        raise ValueError('No completed interval exists yet in the current session')
    if current_end != expected_end or current_end > retrieved:
        raise ValueError('Current bar is not the latest completed interval available at retrieval')
    if not timedelta(0) <= now - current_end < maximum_age:
        raise ValueError('Current interval is future-dated or stale')

    historical = [key for key, (_, end) in sessions.items() if end <= session_open]
    selected = historical[-config['lookback_sessions']:]
    grouped = {key: [] for key in selected}
    rows = context['bars']
    if not isinstance(rows, list):
        raise ValueError('bars must be a chronological list')
    previous_end, excluded_intervals, outside_window = None, 0, 0
    for raw in rows:
        record = _bar(raw, source, sessions, interval, historical=True)
        if record is None:
            excluded_intervals += 1
            continue
        session_id, start, end, _ = record
        if end > now or end > retrieved:
            raise ValueError('Historical input contains a future-dated interval')
        if previous_end is not None and start < previous_end:
            raise ValueError('Historical bars are duplicate, overlapping, or not chronological')
        previous_end = end
        if session_id in grouped:
            grouped[session_id].append(record)
        else:
            outside_window += 1

    samples, expected_total, coverage = [], 0, []
    for session_id in selected:
        opened, closed = sessions[session_id]
        expected_count = (closed - opened) // interval
        records = grouped[session_id]
        expected_total += expected_count
        coverage.append({'session_id': session_id, 'expected_intervals': expected_count,
                         'observed_intervals': len(records)})
        for _, _, _, move in records:
            samples.append(abs(move))
    evidence.update(sample_count=len(samples), coverage=coverage,
                    expected_intervals=expected_total,
                    missing_intervals=expected_total - len(samples),
                    excluded_noncomparable_intervals=excluded_intervals,
                    excluded_current_or_outside_window_intervals=outside_window)
    if len(samples) < config['min_samples']:
        raise ValueError('Historical sample count is below configured minimum')
    samples.sort()
    rank = int((Decimal(len(samples)) * Decimal(config['percentile']) / 100)
               .to_integral_value(rounding=ROUND_CEILING))
    threshold, actual = samples[rank - 1], abs(current_move)
    unusual = actual > threshold
    deadline = min(current_end + interval, current_end + maximum_age,
                   retrieved + maximum_age, session_close)
    evidence.update(current_move_pct=_number_text(current_move),
                    current_absolute_move_pct=_number_text(actual),
                    threshold_pct=_number_text(threshold), sample_count=len(samples),
                    percentile_rank=rank, baseline_sessions=selected,
                    current_session=current_id, current_bar_end=current_end.isoformat(),
                    baseline_first_start=min(row[1] for records in grouped.values() for row in records).isoformat(),
                    baseline_last_end=max(row[2] for records in grouped.values() for row in records).isoformat(),
                    current_session_excluded=True, overnight_returns_excluded=True,
                    zero_baseline_threshold=(threshold == 0))
    reasons = ['Latest completed interval exceeds the stock-specific historical percentile.'] if unusual else []
    if unusual and threshold == 0:
        reasons = ['Historical percentile is zero; a nonzero current move exceeds that baseline.']
    return {'within_historical_range': not unusual, 'status': 'excessive_volatility' if unusual else 'normal',
            'reasons': reasons, 'evidence': evidence, 'observation_refresh_after': deadline.isoformat()}


def main():
    try:
        payload = json.load(sys.stdin)
        result = evaluate_volatility(payload['context'], payload['now'])
    except (KeyError, TypeError, ValueError) as exc:
        result = {'within_historical_range': None, 'status': 'data_unavailable', 'reasons': [str(exc)],
                  'evidence': {}, 'observation_refresh_after': None, 'advisory_only': True, 'enforces_execution': False}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
