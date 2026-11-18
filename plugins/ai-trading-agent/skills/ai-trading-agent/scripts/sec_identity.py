"""Pure intake of retained SEC symbol tables and conservative CIK mappings.

The tables describe a current SEC snapshot, not historical membership, security
classification, a complete exchange universe or authenticated source truth.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import re
from urllib.parse import urlsplit


def require(ok, message):
    if not ok:
        raise ValueError(message)


def complete(document):
    declarations = [obj['raw_complete'] for obj in (document, document.get('source', {}))
                    if isinstance(obj, dict) and 'raw_complete' in obj]
    return bool(declarations) and all(type(x) is bool and x for x in declarations)


def strict_json(text):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'SEC_IDENTITY_DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=object_pairs)


def parse(document, text):
    data = document.get('data')
    if data is None:
        data = strict_json(text)
    elif text.strip():
        require(json.dumps(data, sort_keys=True) == json.dumps(strict_json(text), sort_keys=True),
                'SEC_IDENTITY_DATA_TEXT_CONFLICT')
    require(type(data) is dict and data, 'SEC_IDENTITY_OBJECT_REQUIRED')
    if 'fields' in data or 'data' in data:
        fields, values = data.get('fields'), data.get('data')
        require(type(fields) is list and all(type(f) is str for f in fields)
                and len(fields) == len(set(fields))
                and {'cik', 'name', 'ticker', 'exchange'} <= set(fields)
                and type(values) is list, 'SEC_EXCHANGE_TABLE_SCHEMA_REQUIRED')
        raw = [(i, value, fields) for i, value in enumerate(values)]
        format_name = 'exchange_table'
    else:
        require(all(type(k) is str and re.fullmatch(r'0|[1-9]\d*', k) for k in data),
                'SEC_TICKER_OBJECT_NUMERIC_KEYS_REQUIRED')
        raw = [(k, data[k], None) for k in sorted(data, key=int)]
        format_name = 'numeric_key_object'
    require(0 < len(raw) <= 200000, 'BOUNDED_NONEMPTY_SEC_IDENTITY_ROWS_REQUIRED')
    rows, issues = [], []
    transport_complete = complete(document)
    for index, value, fields in raw:
        payload = dict(source_format='sec_company_tickers', table_format=format_name,
                       source_row_key=index, raw_fields=deepcopy(value),
                       cik=None, issuer_name=None, exchange=None,
                       security_type='UNKNOWN_FROM_THIS_TABLE')
        row = dict(kind='disclosure', ticker=None, payload=payload)
        try:
            if fields is not None:
                require(type(value) is list and len(value) == len(fields), 'SEC_IDENTITY_ROW_WIDTH')
                record = dict(zip(fields, value))
                cik, name, symbol, exchange = [record[k] for k in ('cik', 'name', 'ticker', 'exchange')]
                payload['source_headers'] = list(fields)
            else:
                require(type(value) is dict and {'cik_str', 'ticker', 'title'} <= set(value),
                        'SEC_IDENTITY_ROW_FIELDS')
                cik, name, symbol, exchange = value['cik_str'], value['title'], value['ticker'], None
            require(type(cik) is int and 0 < cik < 10**10, 'SEC_IDENTITY_POSITIVE_INTEGER_CIK')
            payload['cik'] = str(cik)
            require(type(name) is str and name.strip(), 'SEC_IDENTITY_NAME_REQUIRED')
            payload['issuer_name'] = name
            require(type(symbol) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,31}', symbol),
                    'SEC_IDENTITY_SYMBOL_REQUIRED')
            row['ticker'] = symbol
            require(exchange is None or type(exchange) is str and exchange.strip(),
                    'SEC_IDENTITY_EXCHANGE_INVALID')
            payload['exchange'] = exchange
            require(transport_complete, 'SEC_IDENTITY_COMPLETE_TRANSPORT_NOT_DECLARED')
        except (ValueError, TypeError, KeyError) as error:
            row['parse_error'] = str(error)
            issues.append(dict(code='ROW_PARSE_ERROR', row=index, detail=str(error)))
        rows.append(row)
    metadata = dict(table_format=format_name, source_rows=len(raw), emitted_rows=len(rows),
                    raw_transport_complete_declared=transport_complete,
                    exchange_counts=dict(Counter(str(r['payload']['exchange']) for r in rows)),
                    current_snapshot_only=True, security_classification_verified=False,
                    complete_universe_verified=False, downstream_partition_required=len(rows) > 10000)
    return rows, metadata, issues


def identity_map(document):
    """One retained snapshot; never choose among share classes or source vintages."""
    import market_sources
    require(type(document) is dict and type(document.get('schema_version')) is int
            and document['schema_version'] == 1, 'SCHEMA_VERSION_REQUIRED')
    exchanges = document.get('allowed_exchanges')
    require(type(exchanges) is list and 0 < len(exchanges) <= 50
            and all(type(x) is str and x.strip() for x in exchanges)
            and len(exchanges) == len(set(exchanges)), 'EXPLICIT_UNIQUE_EXCHANGE_SCOPE_REQUIRED')
    normalized = market_sources.normalize(dict(schema_version=1, as_of=document.get('as_of'),
                                                records=document.get('records')))
    rows = normalized['records']
    require(rows, 'NONEMPTY_IDENTITY_RECORDS_REQUIRED')
    vintages = set()
    grouped, owners = defaultdict(list), defaultdict(set)
    ungrouped = []
    for row in rows:
        payload, source = row.get('payload', {}), row.get('source', {})
        require(type(payload) is dict and type(source) is dict, 'IDENTITY_RECORD_OBJECTS_REQUIRED')
        require(payload.get('source_format') == 'sec_company_tickers', 'SEC_IDENTITY_RECORDS_ONLY')
        url = urlsplit(source.get('url', ''))
        require(url.scheme == 'https' and url.hostname == 'www.sec.gov'
                and url.path in ('/files/company_tickers.json', '/files/company_tickers_exchange.json')
                and not url.query and not url.fragment, 'EXACT_SEC_IDENTITY_SOURCE_REQUIRED')
        digest = source.get('raw_sha256')
        require(type(digest) is str and re.fullmatch(r'[0-9a-f]{64}', digest), 'IDENTITY_RAW_HASH_REQUIRED')
        require(type(source.get('id')) is str and type(source.get('retrieved_at')) in (str, type(None)),
                'IDENTITY_SNAPSHOT_DECLARATION_REQUIRED')
        vintages.add((source.get('id'), source['url'], source.get('retrieved_at'), digest))
        cik, ticker = payload.get('cik'), row.get('ticker')
        if type(cik) is str and re.fullmatch(r'[1-9]\d{0,9}', cik):
            grouped[cik].append(row)
            if type(ticker) is str and ticker:
                owners[ticker].add(cik)
        else:
            ungrouped.append(row['id'])
    require(len(vintages) == 1, 'ONE_IDENTITY_SNAPSHOT_REQUIRED')
    resolved, unresolved = {}, []
    for cik, group in sorted(grouped.items(), key=lambda x: int(x[0])):
        candidates = sorted({r['ticker'] for r in group if type(r.get('ticker')) is str})
        reasons = []
        if any(not r['eligible'] for r in group):
            reasons.append('IDENTITY_ROWS_UNUSABLE_AT_CUTOFF')
        if len(candidates) != 1:
            reasons.append('MULTIPLE_OR_MISSING_SHARE_CLASS_SYMBOLS')
        if len(group) != len(candidates):
            reasons.append('DUPLICATE_IDENTITY_ROWS')
        if any(len(owners[t]) != 1 for t in candidates):
            reasons.append('SYMBOL_MATCHES_MULTIPLE_CIKS')
        if any(r['payload'].get('exchange') not in exchanges for r in group):
            reasons.append('EXCHANGE_OUTSIDE_OR_UNKNOWN_UNDER_DECLARED_SCOPE')
        if reasons:
            unresolved.append(dict(cik=cik, candidate_symbols=candidates, reasons=reasons,
                source_record_ids=[r['id'] for r in group]))
            continue
        row = group[0]
        resolved[cik] = dict(ticker=row['ticker'], available_at=row['available_at'],
            source=deepcopy(row['source']), source_record_id=row['id'],
            issuer_name=row['payload']['issuer_name'], exchange=row['payload']['exchange'],
            identity_scope='UNIQUE_DECLARED_CURRENT_SEC_CIK_SYMBOL_NOT_SECURITY_CLASSIFICATION')
    return dict(schema_version=1, kind='SEC_CIK_SYMBOL_MAPPING', as_of=document['as_of'],
        allowed_exchanges=deepcopy(exchanges), cik_symbol_mapping=resolved,
        resolved_ciks=len(resolved), unresolved_ciks=unresolved, ungrouped_record_ids=ungrouped,
        records_seen=len(rows), source_raw_sha256=next(iter(vintages))[3],
        source_snapshot_authenticated=False, historical_membership_verified=False,
        complete_us_listed_universe_verified=False, execution_authorized=False,
        limitation='An explicit current SEC identity snapshot and exchange scope resolve only unique declarations; ambiguous, malformed, future and out-of-scope identities remain unresolved.')
