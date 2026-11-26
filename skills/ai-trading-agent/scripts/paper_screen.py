"""Offline earnings-calendar and low expected-shortfall screens on retained observations."""
from datetime import date
import math
import statistics
from zoneinfo import ZoneInfo

from evidence_semantics import event_window
from news_sources import stamp


def require(condition, message):
    if not condition:
        raise ValueError(message)


def day(value):
    parsed = date.fromisoformat(value)
    require(parsed.isoformat() == value, 'ISO_DAY_REQUIRED')
    return parsed


def named(value):
    return isinstance(value, str) and bool(value.strip())


def symbols(document):
    rows = document['candidates']
    require(isinstance(rows, list) and rows and all(isinstance(row, dict) and named(row.get('symbol')) for row in rows),
            'NONEMPTY_CANDIDATE_LIST_REQUIRED')
    require(len(rows) == len({row['symbol'] for row in rows}), 'DUPLICATE_SYMBOL')
    return rows


def available(observation, cutoff):
    return (named(observation.get('source_ref')) and named(observation.get('observed_at')) and
            stamp(observation['observed_at']) <= cutoff)


def calendar_observation(source, cutoff, start, end):
    require(isinstance(source, dict) and named(source.get('upstream')), 'CALENDAR_SOURCE_LINEAGE_REQUIRED')
    raw = source.get('vendor_calendar', {})
    require(isinstance(raw, dict), 'VENDOR_CALENDAR_OBJECT_REQUIRED')
    # yfinance can supply a list of endpoints for one estimates window. The
    # entire span is possible, including dates between its endpoints.
    dates = source.get('next_dates', raw.get('Earnings Date', []))
    if dates is None:
        dates = []
    if dates == '[]':
        dates = []
    require(isinstance(dates, list), 'CALENDAR_DATE_LIST_REQUIRED')
    statuses = [event_window(value, start, end)['status'] for value in dates]
    conflict = (any(s in ('CONTAINED', 'OVERLAP') for s in statuses) or
                ('DEFINITELY_BEFORE' in statuses and 'DEFINITELY_AFTER' in statuses))
    past = source.get('past_dates')
    require(past is None or isinstance(past, list), 'PAST_DATE_LIST_REQUIRED')
    history = {day(value) for value in (past or [])}
    if named(source.get('observed_at')):
        captured_day = stamp(source['observed_at']).date()
        require(all(value <= captured_day for value in history), 'FUTURE_DATE_IN_EARNINGS_HISTORY')
    span = source.get('coverage')
    covered = (isinstance(span, dict) and day(span['from']) <= day(start) and
               day(span['through']) >= day(end))
    return {'upstream': source['upstream'], 'source_ref': source.get('source_ref'),
            'observed_at': source.get('observed_at'), 'available': available(source, cutoff),
            'past_count': len(history), 'next_dates': dates, 'window_relations': statuses,
            'possible_inside': conflict, 'clear_coverage': covered and 'UNRESOLVED' not in statuses}


def calendar_completeness(document):
    """Evaluate a prespecified earnings exclusion, separately for each candidate."""
    start, end = document['window_start'], document['window_end']
    require(day(start) <= day(end), 'REVERSED_EXCLUSION_WINDOW')
    cutoff = stamp(document['as_of'])
    output, blocking = [], []
    for row in symbols(document):
        symbol, checked = row['symbol'], []
        errors = []
        for role in ('vendor', 'confirmation'):
            source = row.get(role)
            if source is None:
                continue
            try:
                result = calendar_observation(source, cutoff, start, end)
                checked.append({'role': role, **result})
            except (ValueError, KeyError, TypeError) as exc:
                errors.append(role + ': ' + str(exc))
        by_role = {v['role']: v for v in checked if v['available']}
        vendor, other = by_role.get('vendor'), by_role.get('confirmation')
        vendor_upstream = (row.get('vendor') or {}).get('upstream') if isinstance(row.get('vendor'), dict) else None
        independent = bool(other and named(vendor_upstream) and
                           other['upstream'].strip().casefold() != vendor_upstream.strip().casefold())
        if any(v['possible_inside'] for v in by_role.values()):
            reason = 'POSSIBLE_EARNINGS_IN_WINDOW'
        elif errors or any('UNRESOLVED' in v['window_relations'] for v in by_role.values()):
            reason = 'UNRESOLVED_CALENDAR_OBSERVATION'
        elif vendor and vendor['past_count'] and (vendor['clear_coverage'] or
                vendor['window_relations'] and all(s == 'DEFINITELY_AFTER' for s in vendor['window_relations'])):
            reason = 'REVIEWED_VENDOR_COVERAGE'
        elif independent and other['clear_coverage'] and row['confirmation'].get('window_reviewed_clear') is True:
            reason = 'INDEPENDENT_SOURCE_CONFIRMED_WINDOW_CLEAR'
        else:
            reason = 'MISSING_HISTORY_OR_UNCONFIRMED_WINDOW'
        passed = reason in ('REVIEWED_VENDOR_COVERAGE', 'INDEPENDENT_SOURCE_CONFIRMED_WINDOW_CLEAR')
        if not passed:
            blocking.append(symbol)
        output.append({'symbol': symbol, 'eligible': passed, 'reason': reason,
                       'reviews': checked, 'input_errors': errors})
    return {'status': 'BLOCKED' if blocking else 'PASS', 'blocking_symbols': blocking,
            'candidates': output, 'as_of': document['as_of'], 'window_start': start, 'window_end': end,
            'scope': 'Adopted research exclusion. Source coverage and independence are supplied declarations.'}


ACTION_STATES = {'no_indicator', 'unknown', 'pending_merger', 'pending_acquisition', 'tender_offer', 'spac'}


def low_es_screen(document):
    """Guard the common price window and observed corporate actions before ranking."""
    from quant_validation import tail_risk
    from paper_pricing import exchange_close
    cutoff = stamp(document['as_of'])
    sessions = document['sessions']
    require(isinstance(sessions, list) and len(sessions) == 64 and
            all(day(s) for s in sessions) and sessions == sorted(set(sessions)),
            '64_UNIQUE_ORDERED_COMPLETED_SESSIONS_REQUIRED')
    if not named(document.get('calendar_ref')):
        raise ValueError('EXCHANGE_CALENDAR_REFERENCE_REQUIRED')
    zone = ZoneInfo(document.get('session_timezone', 'America/New_York'))
    last_close = exchange_close({**document, 'session': sessions[-1]}, day(sessions[-1]), zone)
    require(last_close <= cutoff, 'TARGET_SESSION_NOT_CLOSED_AT_DECISION')
    cap = document.get('max_beta')
    bases = {row['price_basis'] for row in symbols(document) if named(row.get('price_basis'))}
    require(len(bases) <= 1, 'COMMON_PRICE_BASIS_REQUIRED')
    if cap is not None:
        require(type(cap) in (int, float) and math.isfinite(cap), 'FINITE_BETA_LIMIT_REQUIRED')
    results = []
    for row in symbols(document):
        reasons = []
        reviews = {}
        for kind in ('issuer_profile', 'deal_news'):
            review = row.get(kind) or {}
            require(isinstance(review, dict), 'REVIEW_OBJECT_REQUIRED')
            state = review.get('status', 'unknown')
            require(state in ACTION_STATES, 'UNKNOWN_CORPORATE_ACTION_STATUS')
            if not available(review, cutoff) or state == 'unknown':
                reasons.append(kind + ':unresolved')
            elif state != 'no_indicator':
                reasons.append(kind + ':' + state)
            elif stamp(review['observed_at']).date() != cutoff.date():
                reasons.append(kind + ':stale_clearance')
            if kind == 'issuer_profile' and available(review, cutoff):
                # Shell-company classification is evidence for review, not proof
                # of a SPAC. A specific, sourced, contemporaneous resolution can
                # distinguish an ordinary listed company from that search hit.
                industry = review.get('industry')
                if isinstance(industry, str) and industry.strip().casefold() == 'shell companies':
                    resolution = review.get('classification_review') or {}
                    if not (isinstance(resolution, dict) and resolution.get('status') == 'operating_company'
                            and available(resolution, cutoff) and named(resolution.get('rationale'))):
                        reasons.append('SHELL_COMPANY_CLASSIFICATION_REQUIRES_REVIEW')
            reviews[kind] = review
        bars = row.get('bars', [])
        require(isinstance(bars, list) and all(isinstance(b, dict) for b in bars), 'BAR_LIST_REQUIRED')
        # Missing bars, repeats and stale sessions do not become low-volatility returns.
        series_observed = available(row, cutoff) and stamp(row['observed_at']) >= last_close
        if not series_observed:
            reasons.append('PRICE_CAPTURE_MISSING_OR_OUTSIDE_SESSION_WINDOW')
        complete = (named(row.get('price_basis')) and
                    [b.get('date') for b in bars] == sessions and
                    all(type(b.get('close')) in (float, int) and math.isfinite(b['close']) and b['close'] > 0
                        and type(b.get('volume')) in (float, int) and math.isfinite(b['volume']) and b['volume'] > 0
                        and b.get('carried', False) is False for b in bars))
        spread = None
        if not complete:
            reasons.append('MISSING_OR_UNTRADED_SESSION_OR_UNKNOWN_BASIS')
        else:
            closes = [b['close'] for b in bars]
            tail = closes[-63:]
            spread = (max(tail) - min(tail)) / statistics.median(tail)
            if spread < .01:
                reasons.append('NARROW_63_SESSION_CLOSE_RANGE')
        beta = row.get('beta')
        if cap is not None and not reasons:
            if type(beta) not in (int, float) or not math.isfinite(beta) or not named(row.get('beta_ref')):
                reasons.append('BETA_UNAVAILABLE')
            elif beta >= cap:
                reasons.append('BETA_AT_OR_ABOVE_LIMIT')
        risk = None
        if not reasons:
            returns = [b/a-1 for a, b in zip(closes, closes[1:])]
            risk = tail_risk(returns, .95)['loss_expected_shortfall']
        results.append({'symbol': row['symbol'], 'eligible': not reasons, 'reasons': reasons,
                        'range_fraction': spread, 'loss_expected_shortfall': risk, 'reviews': reviews,
                        'price_source_ref': row.get('source_ref'), 'price_basis': row.get('price_basis'),
                        'price_observed_at': row.get('observed_at'),
                        'beta': beta, 'beta_ref': row.get('beta_ref')})
    ranked = sorted((r for r in results if r['eligible']), key=lambda r: (r['loss_expected_shortfall'], r['symbol']))
    return {'as_of': document['as_of'], 'sessions': sessions, 'calendar_ref': document['calendar_ref'],
            'latest_session_close_at': last_close.isoformat(),
            'candidates': results, 'ranked_symbols': [r['symbol'] for r in ranked],
            'limitation': 'Narrow traded range is a diagnostic, not proof of a deal. Status reviews and session grid are supplied.'}


def acquire_vendor_calendars(document):
    """Explicit optional network operation. Never assigns historical availability."""
    from datetime import datetime, timezone
    from public_research_fetch import NetworkPolicyError, require_network, request_call

    require_network()
    import yfinance as yf
    results = []
    for row in symbols(document):
        ticker = yf.Ticker(row.get('provider_symbol') or row['symbol'].replace('.', '-'))
        errors, dates, history = [], [], []
        try:
            calendar = request_call(lambda: ticker.calendar)
            require(isinstance(calendar, dict), 'UNRECOGNIZED_VENDOR_CALENDAR')
            for value in calendar.get('Earnings Date') or []:
                dates.append(day(str(value)[:10]).isoformat())
        except NetworkPolicyError:
            raise
        except Exception as exc:
            errors.append('calendar: ' + str(exc))
        try:
            frame = request_call(lambda: ticker.get_earnings_dates(limit=12))
            if frame is not None:
                today = datetime.now(timezone.utc).date()
                for when, item in frame.iterrows():
                    reported = item.get('Reported EPS')
                    session = day(str(when)[:10])
                    if session <= today and reported is not None and math.isfinite(float(reported)):
                        history.append(session.isoformat())
        except NetworkPolicyError:
            raise
        except Exception as exc:
            errors.append('history: ' + str(exc))
        results.append({'symbol': row['symbol'], 'vendor': {
            'upstream': 'Yahoo Finance', 'source_ref': 'yfinance:' + str(ticker.ticker),
            'observed_at': datetime.now(timezone.utc).isoformat(), 'next_dates': dates,
            'past_dates': sorted(set(history)), 'coverage': None, 'acquisition_errors': errors}})
    return {'candidates': results, 'scope': 'Current reported observations. A successful request alone cannot certify a clear future window.'}


def main():
    import argparse
    import json
    from pathlib import Path
    from analyst_revisions import estimate_revision_signal
    from analyst_sources import provider_consensus_batch

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('acquire-calendar', 'calendar', 'low-es', 'revisions', 'provider-consensus'))
    parser.add_argument('input', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--source-root', type=Path)
    args = parser.parse_args()
    def unique_object(pairs):
        result = dict(pairs)
        require(len(result) == len(pairs), 'DUPLICATE_JSON_KEY')
        return result
    data = json.loads(args.input.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object)
    if args.operation == 'provider-consensus':
        if not args.manifest or not args.manifest_sha256:
            parser.error('provider-consensus requires --manifest and --manifest-sha256')
        result = provider_consensus_batch(data, args.manifest, args.manifest_sha256, args.source_root)
    else:
        run = {'acquire-calendar': acquire_vendor_calendars, 'calendar': calendar_completeness,
               'low-es': low_es_screen, 'revisions': estimate_revision_signal}[args.operation]
        result = run(data)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

