"""Fresh public-data acquisition for the public VQM research queue. No broker.

Every run gets a new output directory. Provider data are research proxies, not
point-in-time audited financials. Never reuse another model's data for a test of
independent acquisition. A supplied universe JSON supports other equity universes.
Unspecified universes cover U.S. exchange-listed stocks, including listed ADRs.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import importlib.metadata
import hashlib
import io
import json
import copy
from pathlib import Path
import threading
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from public_research import digest, profile, incomplete_components
from listed_universe import DIRECTORIES, build_universe
from trading_calendar import sessions
from incremental_research import PartialFetch

_request_lock = threading.Lock()
_next_request = 0.0
_provider_paused = False


def request_call(call):
    """Bound rate-limited retries; never rotate accounts, proxies or identities."""
    global _next_request, _provider_paused
    for attempt in range(2):
        with _request_lock:
            if _provider_paused:
                raise RuntimeError('PROVIDER_PAUSED_AFTER_REPEATED_RATE_LIMIT; resume later')
            wait = max(0, _next_request - time.monotonic())
            _next_request = max(time.monotonic(), _next_request) + .2
        if wait:
            time.sleep(wait)
        try:
            return call()
        except Exception as exc:
            if 'RateLimit' not in type(exc).__name__ and 'Too Many Requests' not in str(exc):
                raise
            with _request_lock:
                _next_request = max(_next_request, time.monotonic() + 60)
                if attempt:
                    _provider_paused = True
            if attempt:
                raise


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, indent=2, allow_nan=False)


def frame(value, price=False):
    if value is None or value.empty:
        return {'index': [], 'columns': [], 'data': []}
    value = value.copy()
    if price:
        value.index = value.index.strftime('%Y-%m-%d')
    else:
        value.columns = [v.date().isoformat() if hasattr(v, 'date') else str(v) for v in value.columns]
    return json.loads(value.to_json(orient='split'))


def xlsx_rows(raw):
    """Read cell values only from the first workbook sheet; no macro execution."""
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(io.BytesIO(raw)) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            tree = ET.fromstring(archive.read('xl/sharedStrings.xml'))
            strings = [''.join(x.itertext()) for x in tree.findall('m:si', ns)]
        tree = ET.fromstring(archive.read('xl/worksheets/sheet1.xml'))
        rows = []
        for row in tree.findall('.//m:row', ns):
            values = {}
            for cell in row.findall('m:c', ns):
                key = ''.join(c for c in cell.attrib['r'] if c.isalpha())
                value = cell.find('m:v', ns)
                text = value.text if value is not None else ''
                if cell.attrib.get('t') == 's':
                    text = strings[int(text)]
                elif cell.attrib.get('t') == 'inlineStr':
                    text = ''.join(cell.find('m:is', ns).itertext())
                values[key] = text
            rows.append(values)
        return rows


def universe_spec(preset=None, supplied=None):
    if preset and supplied:
        raise ValueError('CHOOSE_PRESET_OR_CUSTOM_UNIVERSE')
    if supplied:
        data = json.loads(supplied.read_text(encoding='utf-8-sig'))
        return {'kind': 'custom', 'input_sha256': digest(data)}
    return {'kind': 'preset', 'name': preset or 'us-listed'}


def acquire_universe(folder, supplied=None, preset=None, price_date=None):
    import pandas as pd
    import requests
    spec = universe_spec(preset, supplied)
    if supplied:
        data = json.loads(supplied.read_text(encoding='utf-8-sig'))
        # Explicit input format: {universe_id, source, rows:[{symbol,issuer_id,name}]}.
        rows = data['rows']
        evidence = {'source': data['source'], 'input_sha256': digest(data), 'retrieved_at': now(),
                    'universe_id': data['universe_id'], 'source_type': 'user_supplied_dated_universe'}
    elif spec['name'] == 'us-listed':
        if not price_date:
            raise ValueError('PRICE_DATE_REQUIRED_FOR_DIRECTORY_FRESHNESS')
        documents = {}
        for kind, url in DIRECTORIES.items():
            response = requests.get(url, timeout=40); response.raise_for_status()
            documents[kind] = response.content
            (folder / (kind + '.txt')).write_bytes(response.content)
        listing = build_universe(documents, price_date,
            datetime.now(ZoneInfo('America/New_York')).date().isoformat())
        rows, evidence = listing['rows'], listing['evidence']
        evidence['retrieved_at'] = now()
    elif spec['name'] == 'sp500':
        url = 'https://stockanalysis.com/list/sp-500-stocks/'
        response = requests.get(url, timeout=40); response.raise_for_status()
        (folder / 'constituents.html').write_bytes(response.content)
        tables = pd.read_html(io.StringIO(response.text))
        candidates = [t for t in tables if 'Symbol' in t.columns and 'Company Name' in t.columns]
        if len(candidates) != 1:
            raise ValueError('Constituent table schema changed; do not guess')
        rows = [{'symbol': str(r['Symbol']), 'name': str(r['Company Name']),
                 'issuer_id': 'name:' + ' '.join(str(r['Company Name']).casefold().split())}
                for r in candidates[0].to_dict(orient='records')]
        if not 450 <= len(rows) <= 550:
            raise ValueError('Unexpected S&P universe size; review membership source')
        evidence = {'source': url, 'retrieved_at': now(), 'source_type': 'dated_vendor_constituents',
            'universe_id': 'SP500', 'content_sha256': hashlib.sha256(response.content).hexdigest(),
            'issuer_identity_basis': 'Exact normalized constituent company name, not an SEC-certified identifier'}
        spy_url = 'https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx'
        try:
            response = requests.get(spy_url, timeout=40); response.raise_for_status()
            (folder / 'spy-holdings.xlsx').write_bytes(response.content)
            records = xlsx_rows(response.content)
            headers = [r for r in records if 'Ticker' in r.values()]
            if len(headers) != 1:
                raise ValueError('SPY Ticker header missing or ambiguous')
            column = next(k for k, v in headers[0].items() if v == 'Ticker')
            header_index = records.index(headers[0])
            tickers = {r[column].strip().replace('-', '.') for r in records[header_index + 1:]
                       if r.get(column, '').strip() and r[column].strip() not in {'-', 'USD'}
                       and len(r[column]) <= 12}
            observed = {r['symbol'].replace('-', '.') for r in rows}
            evidence['fund_proxy_check'] = {'source': spy_url, 'retrieved_at': now(),
                'missing_from_fund': sorted(observed - tickers), 'fund_extras': sorted(tickers - observed),
                'header_metadata': records[:header_index],
                'note': 'SPY is a fund proxy. Residuals, cash and effective membership changes need explicit review; differences never silently change the universe.'}
        except Exception as exc:
            evidence['fund_proxy_check'] = {'source': spy_url, 'status': 'UNAVAILABLE', 'error': str(exc)}
    else:
        raise ValueError('UNKNOWN_UNIVERSE_PRESET:' + str(spec))
    symbols = [r['symbol'] for r in rows]
    if len(set(symbols)) != len(symbols) or not rows or any(not r.get('issuer_id') for r in rows):
        raise ValueError('Unique securities and nonempty issuer IDs required')
    data = {'rows': sorted(rows, key=lambda r: r['symbol']), 'evidence': evidence}
    save(folder / 'universe.json', data)
    return data


def fetch_row(identity, grid, folder, prior=None, reusable=None, source_checks=None):
    import yfinance as yf
    symbol = identity['symbol']
    provider_symbol = identity.get('provider_symbol', symbol.replace('.', '-'))
    # Safe filenames even for a listed issuer named CON, AUX or another Windows device.
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.\-]{0,39}', provider_symbol):
        raise ValueError('PROVIDER_SYMBOL_MAPPING_UNRESOLVED:' + symbol)
    result = copy.deepcopy(prior) if prior else {**identity, 'provider_symbol': provider_symbol, 'retrieved_at': now(),
        'source': 'https://finance.yahoo.com/quote/' + provider_symbol + '/', 'errors': []}
    needed = incomplete_components(result) if prior else None
    result['errors'] = [e for e in result['errors'] if e['component'] not in
                       {'info', 'income', 'balance', 'cashflow', 'history'}]
    ticker = yf.Ticker(provider_symbol)
    for key, call in (
        ('info', ticker.get_info),
        ('income', lambda: frame(ticker.get_income_stmt(freq='quarterly'))),
        ('balance', lambda: frame(ticker.get_balance_sheet(freq='quarterly'))),
        ('cashflow', lambda: frame(ticker.get_cash_flow(freq='quarterly'))),
        ('history', lambda: frame(ticker.history(start=grid[0]['date'],
            end=(datetime.fromisoformat(grid[-1]['date']) + timedelta(days=1)).date().isoformat(),
            auto_adjust=False, repair=False, actions=True, raise_errors=True, timeout=20), price=True)),
    ):
        if (reusable and key in reusable
                and (not result.get('info', {}).get('financialCurrency')
                     or result['info']['financialCurrency'] ==
                     reusable[key]['source_check']['metadata']['currency'])):
            retained = reusable[key]
            result[key] = retained['value']
            result.setdefault('component_retrieved_at', {})[key] = retained['retrieved_at']
            result.setdefault('component_source_checks', {})[key] = retained['source_check']
            result.setdefault('component_acquisition', {})[key] = retained['provenance']
            continue
        if needed is not None and key not in needed:
            continue
        try:
            value = request_call(call)
            if key != 'info' and not value.get('index'):
                raise ValueError('EMPTY_PROVIDER_RESPONSE:' + key)
            if key == 'info':
                allowed = ('currency', 'financialCurrency', 'marketCap', 'enterpriseValue',
                    'regularMarketPrice', 'regularMarketTime', 'sector', 'industry', 'forwardPE', 'quoteType')
                value = {k: value.get(k) for k in allowed}
                result.update(sector=value.get('sector'), industry=value.get('industry'))
                if (result.get('security_type') == 'unresolved_security_type'
                        and result.get('provider_equity_resolution_allowed') is True
                        and value.get('quoteType') == 'EQUITY'):
                    result['directory_security_type'] = result['security_type']
                    result['security_type'] = 'provider_confirmed_equity'
                    result['security_type_basis'] = 'Yahoo EQUITY confirmation; common/ADR subtype and issuer identity still need primary review'
            result[key] = value
            result.setdefault('component_retrieved_at', {})[key] = now()
            result.setdefault('component_acquisition', {})[key] = {'acquisition': 'fresh_network_pull'}
        except Exception as exc:
            result['errors'].append({'component': key, 'error': type(exc).__name__ + ':' + str(exc)})
            result[key] = {} if key == 'info' else {'index': [], 'columns': [], 'data': []}
    result['completed_at'] = now()
    if source_checks:
        source_checks.attach_current_checks(result, result['completed_at'])
    save(folder / 'raw' / ('security-' + provider_symbol + '.json'), result)
    return result


def recover_checkpoints(folder, universe):
    prior, corrupt = {}, []
    for raw_folder in [folder / 'raw'] + sorted(folder.glob('retry-*/raw')):
        for path in sorted(raw_folder.glob('*.json')):
            try:
                row = json.loads(path.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # An interrupted write is retained as evidence and fetched anew.
                corrupt.append({'path': str(path.relative_to(folder)),
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
                continue
            prior[row['symbol']] = row
    identities = {r['symbol']: r for r in universe['rows']}
    if any(s not in identities or r.get('issuer_id') != identities[s]['issuer_id'] for s, r in prior.items()):
        raise ValueError('RESUME_CHECKPOINT_UNIVERSE_MISMATCH')
    return prior, corrupt


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--decision-at', required=True, help='Timezone-bearing research decision timestamp')
    parser.add_argument('--hold', required=True, help='Explicit holding-period descriptor, e.g. P1Y; no fixed maximum')
    parser.add_argument('--prompt-file', type=Path, required=True)
    universe_args = parser.add_mutually_exclusive_group()
    universe_args.add_argument('--universe', type=Path, help='Explicit dated custom universe JSON')
    universe_args.add_argument('--universe-preset', choices=('us-listed', 'sp500'),
        help='Default for a new run: us-listed. An omitted selection on resume retains the frozen universe.')
    parser.add_argument('--universe-only', action='store_true', help='Freeze and audit membership; do not fetch prices/financials or claim a completed stock screen')
    parser.add_argument('--resume', action='store_true', help='Retry failed components of this run, preserving old snapshots')
    parser.add_argument('--partial-fetch', action='store_true', help='Opt in to source-checked statement reuse from an explicit sealed bundle; full fetch remains default')
    parser.add_argument('--reuse-from', type=Path, help='Explicit portable parent research-library root; no hidden cache discovery')
    parser.add_argument('--reuse-manifest', type=Path, help='Sealed research_memory manifest covering exactly one parent snapshot and its source-index evidence')
    parser.add_argument('--freshness-receipt', type=Path, help='Current source-index observations; can also bind source checks during a full fetch')
    parser.add_argument('--workers', type=int, default=4, choices=range(1, 5))
    return parser


def main():
    args = argument_parser().parse_args()
    if args.resume and (args.partial_fetch or args.reuse_from or args.reuse_manifest or args.freshness_receipt):
        raise ValueError('RESUME_AND_NEW_RUN_SOURCE_CHECKS_ARE_DISTINCT')
    if not args.partial_fetch and (args.reuse_from or args.reuse_manifest):
        raise ValueError('PARENT_REUSE_REQUIRES_EXPLICIT_PARTIAL_FETCH')
    decision = datetime.fromisoformat(args.decision_at.replace('Z', '+00:00'))
    if decision.tzinfo is None:
        raise ValueError('decision-at needs timezone')
    if not args.hold.strip():
        raise ValueError('Holding period required')
    folder = args.output.resolve()
    if not args.resume:
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'raw').mkdir()
    grid = [s for s in sessions((decision.date() - timedelta(days=550)).isoformat(), decision.date().isoformat())
            if datetime.fromisoformat(s['close']) <= decision][-253:]
    if len(grid) != 253:
        raise ValueError('Need 253 completed XNYS sessions')
    prompt = args.prompt_file.read_text(encoding='utf-8-sig').strip()
    contract = {'profile': profile(), 'profile_sha256': digest(profile()), 'defined_at': now(),
        'acquisition_code_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
            for name in ('public_research_fetch.py', 'listed_universe.py', 'incremental_research.py')},
        'decision_at': args.decision_at, 'price_date': grid[-1]['date'], 'prompt': prompt,
        'prompt_sha256': digest(prompt), 'hold': args.hold, 'acquisition': 'independent_fresh_network_pull',
        'universe_selection': universe_spec(args.universe_preset, args.universe),
        'historical_information_certified': False,
        'timing_note': 'Prices are frozen to the last completed session. Financial/provider facts are obtained now; historical publication and restatement timing are not certified. This is not a point-in-time backtest.'}
    prior = {}
    output_folder = folder
    if args.resume:
        old_contract = json.loads((folder / 'contract-before-fetch.json').read_text(encoding='utf-8'))
        if ('acquisition_code_sha256' in old_contract
                and old_contract['acquisition_code_sha256'] != contract['acquisition_code_sha256']):
            raise ValueError('RESUME_ACQUISITION_CODE_MISMATCH: use saved collector or start a new run')
        for key in ('profile_sha256', 'price_date', 'prompt_sha256', 'hold'):
            if old_contract[key] != contract[key]:
                raise ValueError('RESUME_CONTRACT_MISMATCH:' + key)
        if args.universe is not None or args.universe_preset is not None:
            if old_contract.get('universe_selection') != contract['universe_selection']:
                raise ValueError('RESUME_CONTRACT_MISMATCH:universe_selection')
        contract = old_contract
        universe = json.loads((folder / 'universe.json').read_text(encoding='utf-8'))
        # Recover finished per-security checkpoints even if a long collection was interrupted.
        prior, corrupt = recover_checkpoints(folder, universe)
        attempt = len(list(folder.glob('retry-*'))) + 1
        output_folder = folder / ('retry-%03d' % attempt)
        output_folder.mkdir(exist_ok=False); (output_folder / 'raw').mkdir()
        save(output_folder / 'resume-receipt.json', {'started_at': now(), 'prior_checkpoints_sha256': digest(prior),
            'corrupt_checkpoints_retained': corrupt,
            'contract_sha256': digest(contract), 'scope': 'Only failed acquisition components; no ranking-based retries'})
    else:
        if args.partial_fetch:
            contract['acquisition'] = 'explicit_optional_partial_fetch'
        save(folder / 'contract-before-fetch.json', contract)
        universe = acquire_universe(folder, args.universe, args.universe_preset, grid[-1]['date'])
    print('Universe', len(universe['rows']), 'securities; close', grid[-1]['date'], flush=True)
    if args.universe_only:
        print('MEMBERSHIP_ONLY: no financial/price screen performed', flush=True)
        return
    rows = []
    checks = None
    if args.partial_fetch or args.freshness_receipt:
        checks = PartialFetch(args.reuse_from, args.reuse_manifest, args.freshness_receipt,
                              output_folder, args.decision_at,
                              baseline_only=not args.partial_fetch)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = []
        for identity in universe['rows']:
            old = prior.get(identity['symbol'])
            if old is not None and not incomplete_components(old):
                rows.append(old)
            else:
                reusable = checks.choose(identity, contract['profile_sha256'], now()) if args.partial_fetch else None
                futures.append(pool.submit(fetch_row, identity, grid, output_folder, old,
                                           reusable, checks))
        for future in as_completed(futures):
            rows.append(future.result())
            if len(rows) % 25 == 0 or len(rows) == len(universe['rows']):
                print('Acquired', len(rows), '/', len(universe['rows']), flush=True)
    snapshot = {'schema_version': 1, 'profile_sha256': contract['profile_sha256'],
        'price_date': grid[-1]['date'], 'session_dates': [s['date'] for s in grid],
        'mandate': {'universe': universe['evidence']['universe_id'], 'hold': args.hold,
                    'prompt_sha256': contract['prompt_sha256']},
        'contract': contract, 'universe_evidence': universe['evidence'],
        'universe_symbols': sorted(r['symbol'] for r in rows), 'rows': sorted(rows, key=lambda r: r['symbol']),
        'completed_at': now(), 'dependencies': {n: importlib.metadata.version(n)
            for n in ('yfinance', 'pandas', 'exchange_calendars')}}
    if checks:
        acquisition_receipt = checks.receipt(rows)
        save(output_folder / 'partial-fetch-receipt.json', acquisition_receipt)
        snapshot['partial_fetch'] = acquisition_receipt
    snapshot['essential_acquisition_errors'] = sum(any(e['component'] in
        {'info', 'income', 'balance', 'cashflow', 'history'} for e in r['errors']) for r in rows)
    save(output_folder / 'snapshot.json', snapshot)
    print('Saved snapshot; no ranking viewed during acquisition:', digest(snapshot), flush=True)


if __name__ == '__main__':
    main()
