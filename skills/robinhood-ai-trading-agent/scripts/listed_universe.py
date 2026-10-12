"""Current U.S. exchange listings; security classification is not buy eligibility.

Nasdaq Trader publishes both directories. Keep all source rows and classifications
so a missing/unsupported stock can never silently disappear from coverage.
"""
from collections import Counter
import csv
from datetime import datetime
import hashlib
import io
import re

DIRECTORIES = {
    'nasdaqlisted': 'https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt',
    'otherlisted': 'https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt',
}
COMMON = r'\b(?:common (?:stock|shares?|units?)|capital stock|ord(?:inary)? (?:stock|shares?)|shares? of beneficial interest|new york registry shares?)\b'
ADR = r'\b(?:american deposit[ao]ry (?:shares?|receipts?)|ADRs?|ADSs?)\b'
ALLOWED_TYPES = {'common_equity', 'listed_adr'}


def parse_directory(text, kind, minimum_date, today):
    """Fail on malformed/stale snapshots, rather than shrink to the surviving file."""
    if kind not in DIRECTORIES:
        raise ValueError('UNKNOWN_DIRECTORY')
    lines = text.lstrip('\ufeff').splitlines()
    lines = [line for line in lines if line.strip()]
    footers = [i for i, line in enumerate(lines) if line.startswith('File Creation Time:')]
    if footers != [len(lines) - 1]:
        raise ValueError('DIRECTORY_FOOTER_MISSING_OR_MISPLACED:' + kind)
    stamp = lines[-1].split('|')[0].removeprefix('File Creation Time:').strip()
    try:
        created = datetime.strptime(stamp, '%m%d%Y%H:%M')
    except ValueError as exc:
        raise ValueError('DIRECTORY_TIMESTAMP_INVALID:' + kind) from exc
    if not minimum_date <= created.date().isoformat() <= today:
        raise ValueError('DIRECTORY_STALE_OR_FUTURE:' + kind + ':' + stamp)
    reader = csv.DictReader(io.StringIO('\n'.join(lines[:-1])), delimiter='|')
    required = {'Security Name', 'ETF', 'Test Issue'} | (
        {'Symbol', 'Market Category', 'Financial Status', 'NextShares'} if kind == 'nasdaqlisted'
        else {'ACT Symbol', 'Exchange', 'CQS Symbol', 'NASDAQ Symbol'})
    if not required <= set(reader.fieldnames or []):
        raise ValueError('DIRECTORY_SCHEMA_CHANGED:' + kind)
    records = list(reader)
    if not records or any(None in r or any(v is None for v in r.values()) for r in records):
        raise ValueError('DIRECTORY_EMPTY_OR_RAGGED:' + kind)
    seen = set()
    for record in records:
        symbol = record['Symbol' if kind == 'nasdaqlisted' else 'ACT Symbol'].strip()
        if not symbol or symbol in seen or not record['Security Name'].strip():
            raise ValueError('DIRECTORY_IDENTITY_INVALID:' + kind)
        seen.add(symbol)
        if record['ETF'] not in {'Y', 'N'} or record['Test Issue'] not in {'Y', 'N'}:
            raise ValueError('DIRECTORY_FLAGS_CHANGED:' + kind + ':' + symbol)
        if kind == 'otherlisted' and not record['Exchange'].strip():
            raise ValueError('DIRECTORY_EXCHANGE_MISSING:' + symbol)
    return records, {'file_creation_time_raw': stamp, 'file_creation_date': created.date().isoformat(),
        'timestamp_timezone': 'Not asserted by this adapter; freshness validated by date',
        'source_rows': len(records)}


def security_type(record):
    name = ' '.join(record['Security Name'].split())
    if record['Test Issue'] == 'Y':
        return 'test_issue'
    if record['ETF'] == 'Y' or record.get('NextShares') == 'Y':
        return 'fund'
    # Type phrases, not loose words: Preferred Bank and Warrant Holdings can be companies.
    if re.search(r'\b(?:preferred (?:stock|shares?|securities|units?|limited|series|class)|preference (?:shares?|units?|securities)|pfd)\b', name, re.I):
        return 'preferred_security'
    if re.search(r'\b(?:senior|subordinated|unsecured|exchange.traded) notes?\b|\b(?:debentures?|ETNs?)\b|\bnotes? (?:initially )?due\b|\bmortgage bonds?\b', name, re.I):
        return 'debt_security'
    if re.search(r'\bunits?\b.*\b(?:consist|compris|includ|warrant|right)|\s-\sunits?\.?$|\b(?:corporate|tangible equity) units?\b', name, re.I):
        return 'bundled_unit'
    if re.search(r'\s(?:redeemable )?(?:warrants?|rights?)(?:\.?$|,|\s(?:each|to|exercisable|expiring)\b)', name, re.I):
        return 'warrant_or_right'
    if re.search(r'\bfund(?:\s|,|$)', name, re.I):
        return 'fund'
    if re.search(ADR, name, re.I):
        return 'listed_adr'
    if re.search(COMMON, name, re.I):
        return 'common_equity'
    return 'unresolved_security_type'


def issuer_name(name):
    # Explicit heuristic, retained with source text; never claim an SEC/LEI identity.
    base = name.split(' - ', 1)[0]
    if base == name:
        match = re.search(ADR + '|' + COMMON, name, re.I)
        if match:
            base = name[:match.start()]
        base = re.sub(r'\s+(?:\(new\)\s*)?(?:class|cl[.])\s+\S+\s*$', '', base, flags=re.I)
        base = re.sub(r'\s+\(?new\)?\s*$', '', base, flags=re.I)
    return ' '.join(base.strip(' ,.-').casefold().split())


def build_universe(documents, minimum_date, today):
    if set(documents) != set(DIRECTORIES):
        raise ValueError('BOTH_US_LISTING_DIRECTORIES_REQUIRED')
    rows, inventory, sources, symbols = [], [], [], set()
    for kind in sorted(DIRECTORIES):
        raw = documents[kind]
        records, receipt = parse_directory(raw.decode('utf-8-sig'), kind, minimum_date, today)
        sources.append({'source': DIRECTORIES[kind], 'content_sha256': hashlib.sha256(raw).hexdigest(), **receipt})
        for record in records:
            symbol = record['Symbol' if kind == 'nasdaqlisted' else 'ACT Symbol'].strip()
            if symbol in symbols:
                raise ValueError('CROSS_DIRECTORY_DUPLICATE:' + symbol)
            symbols.add(symbol)
            kind_ = security_type(record)
            exchange = 'Q' if kind == 'nasdaqlisted' else record['Exchange'].strip()
            status = 'included_for_screening' if kind_ in ALLOWED_TYPES else (
                'classification_unresolved' if kind_ == 'unresolved_security_type' else 'outside_stock_universe')
            item = {'symbol': symbol, 'name': record['Security Name'].strip(),
                'listing_exchange_code': exchange, 'security_type': kind_, 'status': status,
                'directory': kind, 'source_record': record}
            inventory.append(item)
            # Retain ambiguous instruments for provider equity confirmation before scoring.
            if status != 'outside_stock_universe':
                if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,19}', symbol):
                    item['status'] = 'classification_unresolved'
                    item['reason'] = 'PROVIDER_SYMBOL_MAPPING_UNRESOLVED'
                    continue
                base = issuer_name(item['name'])
                rows.append({'symbol': symbol, 'provider_symbol': symbol.replace('.', '-'),
                    'name': item['name'], 'issuer_id': 'directory-name:' + (base or symbol.casefold()),
                    'listing_exchange_code': exchange, 'security_type': kind_,
                    'security_type_basis': 'Nasdaq Trader flags and security description; verify during review',
                    'financial_status': record.get('Financial Status'),
                    'provider_equity_resolution_allowed': not bool(re.search(
                        r'\b(?:deposit[ao]ry|preferred|preference|pfd|notes?|bonds?|units?|trust|fund|certificates?|ZONES)\b',
                        item['name'], re.I)),
                    'directory_source': DIRECTORIES[kind]})
    if not rows:
        raise ValueError('NO_STOCK_CANDIDATES_IN_DIRECTORIES')
    if len({r['provider_symbol'] for r in rows}) != len(rows):
        raise ValueError('AMBIGUOUS_PROVIDER_SYMBOL_MAPPING')
    evidence = {'universe_id': 'US_EXCHANGE_LISTED_STOCKS',
        'source_type': 'official_listing_directories', 'sources': sources,
        'scope': 'U.S. primary exchange-listed common equity and listed ADRs, including foreign issuers; OTC and foreign-only listings are outside this default',
        'membership_not_certified': 'Current directory snapshot, not point-in-time historical membership or proof every new listing is present',
        'issuer_identity_basis': 'Heuristic normalized directory issuer name, not SEC-certified; reconcile finalist identities and ADR share ratios before investment review',
        'directory_record_count': len(inventory), 'screening_record_count': len(rows),
        'listing_exchange_counts': dict(sorted(Counter(r['listing_exchange_code'] for r in inventory).items())),
        'security_type_counts': dict(sorted(Counter(r['security_type'] for r in inventory).items())),
        'classification_unresolved_count': sum(r['status'] == 'classification_unresolved' for r in inventory),
        'inventory': sorted(inventory, key=lambda r: r['symbol'])}
    # Codes are retained verbatim, including new exchanges; no hard-coded exchange whitelist.
    return {'rows': sorted(rows, key=lambda r: r['symbol']), 'evidence': evidence}
