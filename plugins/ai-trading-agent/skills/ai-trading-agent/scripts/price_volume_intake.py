"""Pure daily OHLCV CSV intake with explicit columns, calendar and share bases."""
from collections import Counter
from copy import deepcopy
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import re


def require(ok, message):
    if not ok:
        raise ValueError(message)


def instant(value):
    require(type(value) is str, 'AWARE_BAR_CLOCK_REQUIRED')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None, 'AWARE_BAR_CLOCK_REQUIRED')
    return parsed.astimezone(timezone.utc)


def number(value, positive=False):
    require(type(value) is str and 0 < len(value) <= 100, 'BAR_NUMBER_REQUIRED')
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError('BAR_NUMBER_REQUIRED') from error
    require(result.is_finite() and (result > 0 if positive else result >= 0), 'BAR_NUMBER_RANGE')
    return result


def parse(document, text):
    fields = {'date', 'open', 'high', 'low', 'close', 'volume'}
    columns = document.get('columns')
    require(type(columns) is dict and fields <= set(columns) <= fields | {'adjusted_close'}
            and all(type(v) is str and v for v in columns.values())
            and len(set(columns.values())) == len(columns), 'EXPLICIT_UNIQUE_OHLCV_COLUMNS_REQUIRED')
    context = document.get('bar_context')
    require(type(context) is dict, 'EXPLICIT_BAR_CONTEXT_REQUIRED')
    for key in ('feed_id', 'currency', 'price_basis', 'volume_basis', 'adjustment_basis', 'comparison_group'):
        require(type(context.get(key)) is str and context[key].strip(), 'BAR_CONTEXT_' + key.upper())
    require(context.get('volume_unit') == 'shares', 'EXPLICIT_SHARE_VOLUME_UNIT_REQUIRED')
    roles = {'current', 'baseline', 'benchmark'}
    require(context.get('role') in roles, 'EXPLICIT_BAR_ROLE_REQUIRED')
    by_session = context.get('role_by_session', {})
    require(type(by_session) is dict and all(type(k) is str and v in roles for k, v in by_session.items()),
            'EXPLICIT_SESSION_ROLES_REQUIRED')
    sessions = context.get('sessions')
    require(type(sessions) is dict and 0 < len(sessions) <= 100000, 'DECLARED_SESSION_CALENDAR_REQUIRED')
    ticker = document.get('ticker')
    require(type(ticker) is str and ticker.strip(), 'EXPLICIT_BAR_TICKER_REQUIRED')
    delimiter = document.get('delimiter', ',')
    require(type(delimiter) is str and len(delimiter) == 1, 'SINGLE_CSV_DELIMITER_REQUIRED')
    try:
        table = list(csv.reader(io.StringIO(text.lstrip('\ufeff')), delimiter=delimiter, strict=True))
    except csv.Error as error:
        raise ValueError('MALFORMED_BAR_CSV') from error
    require(table and len(table[0]) == len(set(table[0])) and set(columns.values()) <= set(table[0]),
            'UNIQUE_REQUIRED_BAR_HEADERS')
    headers = table[0]
    values = [(i, row) for i, row in enumerate(table[1:], 2) if row]
    require(0 < len(values) <= 100000, 'BOUNDED_NONEMPTY_DAILY_BARS_REQUIRED')
    raw_flags = [p['raw_complete'] for p in (document, document.get('source', {}))
                 if type(p) is dict and 'raw_complete' in p]
    complete = bool(raw_flags) and all(type(v) is bool and v for v in raw_flags)
    rows, issues = [], []
    observed_dates = []
    for line, raw in values:
        payload = dict(source_format='daily_bars_csv', source_line_number=line,
                       raw_fields=deepcopy(raw), source_headers=list(headers),
                       session_date=None, price_basis=context['price_basis'],
                       volume_basis=context['volume_basis'], adjustment_basis=context['adjustment_basis'],
                       feed_id=context['feed_id'], currency=context['currency'],
                       comparison_group=context['comparison_group'], role=context['role'],
                       volume_unit='shares', adjustment_verification='DECLARED_NOT_CERTIFIED')
        for key in ('issuer_id', 'share_class'):
            if key in context:
                payload[key] = deepcopy(context[key])
        error = None
        try:
            require(len(raw) == len(headers), 'BAR_ROW_WIDTH')
            record = dict(zip(headers, raw))
            day = record[columns['date']]
            require(re.fullmatch(r'\d{4}-\d{2}-\d{2}', day) is not None, 'ISO_BAR_SESSION_DATE_REQUIRED')
            date.fromisoformat(day)
            payload['session_date'] = day
            payload['role'] = by_session.get(day, context['role'])
            require(type(sessions.get(day)) is dict, 'BAR_SESSION_NOT_IN_DECLARED_CALENDAR')
            declared = sessions[day]
            start, end = instant(declared.get('start_at')), instant(declared.get('end_at'))
            require(start < end and start.date().isoformat() == end.date().isoformat() == day,
                    'SAME_UTC_DAY_US_BAR_SESSION_REQUIRED')
            cutoff = instant(document.get('as_of'))
            available = instant(document.get('available_at') or document.get('source', {}).get('retrieved_at'))
            require(end <= min(cutoff, available), 'UNFINISHED_OR_FUTURE_BAR_SESSION')
            parsed = {k: number(record[columns[k]], k != 'volume') for k in fields - {'date'}}
            require(parsed['low'] <= min(parsed[k] for k in ('open', 'close', 'high'))
                    and max(parsed[k] for k in ('open', 'close', 'low')) <= parsed['high'], 'BAR_OHLC_ENVELOPE')
            payload.update({k: str(v) for k, v in parsed.items()})
            payload.update(start_price=str(parsed['open']), end_price=str(parsed['close']))
            payload.update(start_at=declared['start_at'], end_at=declared['end_at'], session_id=day)
            if 'adjusted_close' in columns:
                value = record[columns['adjusted_close']]
                payload['adjusted_close'] = None if not value.strip() else str(number(value, True))
            require(complete, 'BAR_COMPLETE_TRANSPORT_NOT_DECLARED')
        except (ValueError, KeyError, TypeError) as failure:
            error = str(failure)
            issues.append(dict(code='ROW_PARSE_ERROR', row=line, detail=error))
        observed_dates.append(payload['session_date'])
        for facet in ('cumulative', 'daily_volume'):
            row = dict(kind='bar', ticker=ticker, payload=dict(deepcopy(payload), bar_type=facet))
            if error:
                row['parse_error'] = error
            rows.append(row)
    duplicates = {day for day, count in Counter(observed_dates).items() if day is not None and count > 1}
    if duplicates:
        issues.append(dict(code='DUPLICATE_BAR_SESSIONS', sessions=sorted(duplicates)))
        for row in rows:
            if row['payload']['session_date'] in duplicates:
                row['parse_error'] = 'DUPLICATE_BAR_SESSION'
    return rows, dict(source_rows=len(values), emitted_rows=len(rows),
        raw_transport_complete_declared=complete, paired_facets_share_source_row=True,
        facet_rule='Cumulative OHLCV is for interval flow; daily_volume is for ADV. Never sum both facets.',
        calendar_basis='EXPLICIT_CALLER_CALENDAR_NOT_AUTHENTICATED',
        market_tape_complete=False, executable_quote=False,
        downstream_partition_required=len(rows) > 10000), issues
