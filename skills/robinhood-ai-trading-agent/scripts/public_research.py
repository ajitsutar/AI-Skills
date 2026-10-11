"""Replayable public-data VQM discovery. Not filing eligibility or order execution.

The acquisition adapter is public_research_fetch.py. This module uses only local
JSON and never imports code from an input or follows its URLs.
"""
from __future__ import annotations

import argparse
import calendar
import copy
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / 'profiles/public-vqm-discovery-v1.json'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def profile():
    return json.loads(PROFILE.read_text(encoding='utf-8'))


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError('MISSING_NUMBER')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('NONFINITE_NUMBER')
    return result


def positive(value, field):
    if value <= 0:
        raise ValueError('NONPOSITIVE:' + field)
    return value


def nonnegative(value, field):
    if value < 0:
        raise ValueError('NEGATIVE:' + field)
    return value


def require(value, message):
    if not value:
        raise ValueError(message)


def table(value):
    cols, idx, values = value['columns'], value['index'], value['data']
    require(len(set(idx)) == len(idx) == len(values), 'DUPLICATE_OR_MISSING_TABLE_ROWS')
    dates = [str(x)[:10] for x in cols]
    require(len(set(dates)) == len(dates), 'DUPLICATE_TABLE_PERIODS')
    require(all(len(row) == len(dates) for row in values), 'RAGGED_TABLE')
    return {name: dict(zip(dates, row)) for name, row in zip(idx, values)}


def history(value, grid):
    cols, dates, values = value['columns'], value['index'], value['data']
    require(len(set(cols)) == len(cols), 'DUPLICATE_HISTORY_COLUMNS')
    require(len(set(dates)) == len(dates) == len(values), 'DUPLICATE_HISTORY_DATES')
    require(all(len(row) == len(cols) for row in values), 'RAGGED_HISTORY')
    rows = {d: dict(zip(cols, row)) for d, row in zip(dates, values)}
    require(all(d in rows for d in grid), 'MISSING_HISTORY_SESSIONS')
    return rows


def adapter(row):
    sector, industry = row.get('sector'), row.get('industry')
    require(isinstance(sector, str) and sector and isinstance(industry, str) and industry,
            'MISSING_TAXONOMY')
    if industry.startswith('REIT - Mortgage'):
        return 'other_financial'
    if industry.startswith('REIT -'):
        return 'equity_reit'
    if industry.startswith('Banks -'):
        return 'bank'
    if industry.startswith('Insurance -') or industry == 'Insurance Brokers':
        return 'insurer' if industry != 'Insurance Brokers' else 'other_financial'
    if sector == 'Financial Services':
        return 'other_financial'
    return 'corporate'


def midrank(value, population):
    return 2 * (sum(v < value for v in population) + Decimal('.5') *
        sum(v == value for v in population)) / len(population) - 1


def serialize(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize(v) for v in value]
    return value


def raw_metrics(row, prices, grid, cutoff):
    p = profile()
    kind = adapter(row)
    require(kind not in {'bank', 'equity_reit'}, 'SPECIALIZED_COMPONENTS_UNAVAILABLE:' + kind)
    info = row['info']
    require(info.get('currency') == info.get('financialCurrency') == 'USD', 'CURRENCY_NOT_USD')
    inc, bal, cf = (table(row[k]) for k in ('income', 'balance', 'cashflow'))
    periods = sorted({d for values in inc.values() for d in values if d <= str(cutoff)}, reverse=True)[:4]
    require(len(periods) == 4, 'FOUR_QUARTERS_REQUIRED')
    end = date.fromisoformat(periods[0])
    require(0 <= (cutoff - end).days <= p['max_financial_period_age_days'], 'STALE_FINANCIAL_PERIOD')
    require(all(60 <= (date.fromisoformat(periods[i]) - date.fromisoformat(periods[i + 1])).days <= 120
                for i in range(3)), 'NONCONSECUTIVE_QUARTERS')
    prior_target = date(end.year - 1, end.month, min(end.day, calendar.monthrange(end.year - 1, end.month)[1]))
    prior_candidates = sorted({d for values in bal.values() for d in values
        if abs((date.fromisoformat(d) - prior_target).days) <= p['prior_balance_tolerance_days']},
        key=lambda d: (abs((date.fromisoformat(d) - prior_target).days), d))
    require(bool(prior_candidates), 'PRIOR_BALANCE_MISSING')
    prior = prior_candidates[0]
    audit = {'period_end': periods[0], 'quarter_ends': periods, 'prior_balance_date': prior, 'fields': {}}

    def stock(name, when=periods[0]):
        value = number(bal[name][when]); audit['fields'][name + '@' + when] = value
        return value

    def flow(name, source=inc):
        legs = [number(source[name][d]) for d in periods]
        audit['fields'][name] = dict(zip(periods, legs))
        return sum(legs)

    close = positive(number(prices[grid[-1]]['Close']), 'close')
    cap = positive(number(info.get('marketCap')), 'market_cap')
    reference_price = positive(number(info.get('regularMarketPrice')), 'reference_price')
    bridged_cap = cap * close / reference_price
    debt = nonnegative(stock('TotalDebt'), 'debt')
    assets = positive(stock('TotalAssets'), 'assets')
    if kind == 'corporate':
        cash = nonnegative(stock('CashAndCashEquivalents'), 'cash')
        avg = (assets + positive(stock('TotalAssets', prior), 'prior_assets')) / 2
        income, cfo = flow('NetIncome'), flow('OperatingCashFlow', cf)
        # Validate each outflow, not merely its sum; never use abs to mask signs.
        capex_legs = [nonnegative(-number(cf['CapitalExpenditure'][d]), 'capex') for d in periods]
        audit['fields']['gross_capex'] = dict(zip(periods, capex_legs))
        ev = positive(number(info.get('enterpriseValue')) + bridged_cap - cap, 'enterprise_value')
        values = [flow('OperatingIncome') / ev, (cfo - sum(capex_legs)) / bridged_cap]
        quality = [income / avg, (cfo - income) / avg, -(debt - cash) / assets]
    else:
        equity = positive(stock('CommonStockEquity'), 'equity')
        avg = (equity + positive(stock('CommonStockEquity', prior), 'prior_equity')) / 2
        income = flow('NetIncomeCommonStockholders')
        values = [income / bridged_cap, equity / bridged_cap]
        quality = [income / avg, equity / assets, -debt / equity]
    adjusted = [positive(number(prices[d]['Adj Close']), 'adjusted_close') for d in grid]
    audit.update(close=close, market_cap_proxy=bridged_cap,
        momentum_dates=[grid[0], grid[-22]], momentum_prices=[adjusted[0], adjusted[-22]])
    return kind, values, quality, adjusted[-22] / adjusted[0] - 1, audit


def calculate(snapshot, count):
    with localcontext() as context:
        context.prec = 40
        return _calculate(snapshot, count)


def incomplete_components(row):
    """Provider libraries can swallow failures and return empty frames."""
    missing = {e.get('component') for e in row.get('errors', [])
               if e.get('component') in {'info', 'income', 'balance', 'cashflow', 'history'}}
    if not row.get('info') or not any(row['info'].values()):
        missing.add('info')
    for key in ('income', 'balance', 'cashflow', 'history'):
        value = row.get(key, {})
        if not value.get('index') or not value.get('columns') or not value.get('data'):
            missing.add(key)
    return missing


def blocking_components(row, grid):
    """Financial failures cannot change a documented history-ineligible result."""
    missing = incomplete_components(row)
    if not missing or 'history' in missing:
        return missing
    try:
        history(row['history'], grid)
    except ValueError as exc:
        # This is a successful nonempty price response, not a failed request.
        # Missing required sessions unconditionally excludes this share class.
        if str(exc) == 'MISSING_HISTORY_SESSIONS':
            return set()
    except (KeyError, TypeError):
        pass
    return missing


def _calculate(snapshot, count):
    require(type(count) is int and count > 0, 'COUNT_MUST_BE_POSITIVE_INTEGER')
    p = profile()
    require(snapshot.get('schema_version') == 1, 'UNSUPPORTED_SCHEMA')
    require(snapshot.get('profile_sha256') == digest(p), 'PROFILE_HASH_MISMATCH')
    cutoff = date.fromisoformat(snapshot['price_date'])
    grid = snapshot['session_dates']
    require(len(grid) == 253 and grid == sorted(set(grid)) and grid[-1] == str(cutoff), 'SESSION_GRID_INVALID')
    if snapshot.get('fictional') is not True:
        from trading_calendar import sessions
        expected = [s['date'] for s in sessions((cutoff - timedelta(days=550)).isoformat(), str(cutoff))][-253:]
        require(grid == expected, 'SESSION_GRID_NOT_XNYS')
    symbols = snapshot['universe_symbols']
    require(len(symbols) == len(set(symbols)) > 0, 'UNIVERSE_INVALID')
    rows = snapshot['rows']
    require(len(rows) == len(symbols) and {r['symbol'] for r in rows} == set(symbols), 'UNIVERSE_COVERAGE_MISMATCH')
    transport_errors = sum(any('RateLimit' in e.get('error', '') or 'PROVIDER_PAUSED' in e.get('error', '')
        or 'Too Many Requests' in e.get('error', '') for e in r.get('errors', [])
        if e.get('component') in {'info', 'income', 'balance', 'cashflow', 'history'}) for r in rows)
    acquisition_errors = sum(bool(incomplete_components(r)) for r in rows)
    blocking_errors = sum(bool(blocking_components(r, grid)) for r in rows)
    groups = defaultdict(list)
    for row in rows:
        require(isinstance(row.get('issuer_id'), str) and row['issuer_id'], 'ISSUER_ID_MISSING')
        groups[row['issuer_id']].append(row)
    excluded, raw, audits = [], [], []
    for issuer, classes in sorted(groups.items()):
        try:
            liquid = []
            for row in classes:
                prices = history(row['history'], grid)
                adv = sum(positive(number(prices[d]['Close']), 'close') *
                    nonnegative(number(prices[d]['Volume']), 'volume') for d in grid[-20:]) / 20
                liquid.append((positive(adv, 'adv20'), row, prices))
            adv, row, prices = sorted(liquid, key=lambda t: (-t[0], t[1]['symbol']))[0]
            for _, duplicate, _ in liquid:
                if duplicate is not row:
                    excluded.append({'symbol': duplicate['symbol'], 'issuer_id': issuer,
                        'reason': 'DUPLICATE_CLASS', 'representative': row['symbol']})
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            excluded.extend({'symbol': r['symbol'], 'issuer_id': issuer,
                'reason': 'CLASS_SELECTION:' + str(exc)} for r in classes)
            continue
        try:
            kind, v, q, m, audit = raw_metrics(row, prices, grid, cutoff)
            raw.append({'symbol': row['symbol'], 'issuer_id': issuer, 'adapter': kind,
                'sector': row['sector'], 'industry': row['industry'],
                'value_raw': v, 'quality_raw': q, 'momentum_raw': m})
            audits.append({'symbol': row['symbol'], 'adv20': adv, 'source_sha256': digest(row), **audit})
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            excluded.append({'symbol': row['symbol'], 'issuer_id': issuer, 'reason': 'INPUT:' + str(exc)})
    scored = []
    for row in raw:
        for key in ('industry', 'sector', None):
            peers = [r for r in raw if r['adapter'] == row['adapter'] and (key is None or r[key] == row[key])]
            if len(peers) >= p['peer_minimum']:
                break
        if len(peers) < p['peer_minimum']:
            excluded.append({'symbol': row['symbol'], 'issuer_id': row['issuer_id'], 'reason': 'PEERS_BELOW_MINIMUM'})
            continue
        v = sum(midrank(row['value_raw'][i], [r['value_raw'][i] for r in peers]) for i in range(2)) / 2
        q = sum(midrank(row['quality_raw'][i], [r['quality_raw'][i] for r in peers]) for i in range(3)) / 3
        m = midrank(row['momentum_raw'], [r['momentum_raw'] for r in raw])
        scored.append({**row, 'peer_level': key or 'adapter', 'peers': sorted(r['symbol'] for r in peers),
            'value': v, 'quality': q, 'momentum': m, 'score': (v + q + m) / 3})
    scored.sort(key=lambda r: (-r['score'], r['symbol']))
    queue = [{'rank': i + 1, 'symbol': r['symbol'], 'issuer_id': r['issuer_id'],
              'score': r['score'], 'review_status': 'UNREVIEWED'} for i, r in enumerate(scored)]
    return serialize({'schema_version': 1, 'profile': p, 'profile_sha256': digest(p),
        'fictional': snapshot.get('fictional') is True,
        'snapshot_sha256': digest(snapshot), 'price_date': str(cutoff), 'mandate': snapshot['mandate'],
        'status': 'RESEARCH_QUEUE_ONLY', 'input_assurance': p['assurance'],
        'universe_securities': len(rows), 'unique_issuers': len(groups), 'scored_issuers': len(scored),
        'provider_limited_issuers': transport_errors,
        'acquisition_failure_securities': acquisition_errors,
        'ranking_relevant_acquisition_failures': blocking_errors,
        'full_universe_scored': len(scored) == len(groups), 'requested_count': count,
        'research_candidates': queue[:count], 'review_queue': queue, 'scores': scored,
        'exclusions': sorted(excluded, key=lambda r: r['symbol']), 'field_audit': audits,
        'eligible_buys': [], 'buy_eligibility': 'NOT_ESTABLISHED', 'strong_buy_available': False,
        'execution_authorized': False})


def review_frontier(result, reviewed_symbols):
    """Coverage only, never eligibility: a lower reviewed name cannot leapfrog a gap."""
    queue = [r['symbol'] for r in result['review_queue']]
    require(len(reviewed_symbols) == len(set(reviewed_symbols)), 'DUPLICATE_REVIEW')
    require(set(reviewed_symbols) <= set(queue), 'REVIEW_OUTSIDE_QUEUE')
    reviewed = set(reviewed_symbols)
    frontier = next((i for i, s in enumerate(queue) if s not in reviewed), len(queue))
    return {'contiguous_reviewed_count': frontier, 'next_to_review': queue[frontier:frontier + 1],
        'out_of_order_reviews': [s for s in queue[frontier:] if s in reviewed],
        'candidate_review_complete': frontier >= min(result['requested_count'], len(queue)),
        'buy_eligibility': 'USE_SEPARATE_PRIMARY_AND_HORIZON_GATES'}


def make_bundle(snapshot, count):
    snapshot = copy.deepcopy(snapshot)
    result = calculate(snapshot, count)
    code = hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
    return {'schema_version': 1, 'input': snapshot, 'result': result,
        'input_sha256': digest(snapshot), 'result_sha256': digest(result), 'scorer_sha256': code}


def verify(bundle):
    require(bundle.get('schema_version') == 1, 'BUNDLE_SCHEMA')
    require(digest(bundle['input']) == bundle['input_sha256'], 'INPUT_HASH_MISMATCH')
    require(digest(bundle['result']) == bundle['result_sha256'], 'RESULT_HASH_MISMATCH')
    replay = make_bundle(bundle['input'], bundle['result']['requested_count'])
    require(replay == bundle, 'REPLAY_MISMATCH')
    return {'status': 'REPLAY_MATCH', 'input_sha256': bundle['input_sha256']}


def compare(left, right):
    verify(left); verify(right)
    a, b = left['result'], right['result']
    count = a['requested_count']
    require(count == b['requested_count'], 'COUNT_MISMATCH')
    require(a['profile_sha256'] == b['profile_sha256'], 'PROFILE_MISMATCH')
    require(a['price_date'] == b['price_date'] and a['mandate'] == b['mandate'], 'MANDATE_OR_DATE_MISMATCH')
    require(sorted(left['input']['universe_symbols']) == sorted(right['input']['universe_symbols']), 'UNIVERSE_MISMATCH')
    sets = [{r['issuer_id'] for r in x['research_candidates']} for x in (a, b)]
    complete = all(len(s) == count for s in sets)
    common = sorted(sets[0] & sets[1])
    maps = [{r['issuer_id']: r for r in x['scores']} for x in (a, b)]
    differences = [{'issuer_id': i, 'left': maps[0][i]['score'], 'right': maps[1][i]['score']}
        for i in sorted(set(maps[0]) & set(maps[1])) if maps[0][i]['score'] != maps[1][i]['score']]
    status = ('PASS' if len(common) * 5 >= count * 4 else 'FAIL') if complete else 'INCOMPLETE_LISTS'
    if a['ranking_relevant_acquisition_failures'] or b['ranking_relevant_acquisition_failures']:
        status = 'INCOMPLETE_ACQUISITION'
    return {'status': status,
        'test_scope': 'FICTIONAL_CONFORMANCE_ONLY' if a['fictional'] or b['fictional'] else 'PUBLIC_RESEARCH_CANDIDATES_NOT_BUY_ELIGIBILITY', 'requested_count': count,
        'common_issuers': common, 'overlap': len(common) / count, 'threshold': .8,
        'same_order': [r['issuer_id'] for r in a['research_candidates']] == [r['issuer_id'] for r in b['research_candidates']],
        'same_input': left['input_sha256'] == right['input_sha256'],
        'same_universe': sorted(left['input']['universe_symbols']) == sorted(right['input']['universe_symbols']),
        'score_differences': differences, 'exclusion_agreement': a['exclusions'] == b['exclusions'],
        'buy_recommendation_alignment': 'NOT_TESTED',
        'independent_acquisition': 'VERIFY_SOURCE_RECEIPTS_AND_ACTUAL_MODEL_EXECUTION',
        'limitations': 'One-run overlap is not expected returns, a guarantee of future agreement, or proof of independent execution.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    rank = sub.add_parser('rank'); rank.add_argument('input', type=Path); rank.add_argument('output', type=Path)
    rank.add_argument('--count', type=int, required=True)
    check = sub.add_parser('verify'); check.add_argument('input', type=Path)
    cmp = sub.add_parser('compare'); cmp.add_argument('left', type=Path); cmp.add_argument('right', type=Path)
    args = parser.parse_args()
    read = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
    if args.command == 'rank':
        bundle = make_bundle(read(args.input), args.count)
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(bundle, output, indent=2, allow_nan=False)
        result = {k: bundle['result'][k] for k in ('status', 'scored_issuers', 'unique_issuers', 'research_candidates', 'buy_eligibility')}
    elif args.command == 'verify':
        result = verify(read(args.input))
    else:
        result = compare(read(args.left), read(args.right))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
