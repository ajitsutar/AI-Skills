"""Retained permitted options activity and dated float-share intake; no network.

The host assistant maps the user's retained source into this internal contract.
Source identity/rights and reported fields remain declarations, not verification.
"""
from copy import deepcopy
import csv
import hashlib
import io
import json
import re

import market_sources
import market_flow


CONTRACT_FIELDS = ('contract_id', 'underlying_id', 'expiry', 'strike', 'right',
                   'multiplier', 'currency', 'premium_unit', 'deliverable')
ADAPTERS = {'options_chain_csv': 'option_chain', 'options_prints_csv': 'option_print',
            'float_shares_csv': 'float'}
LIMITS = [
    'Only retained supplied or permitted source observations are analyzed; no subscription, network feed or broker action is implemented.',
    'Source authenticity, permission declarations and completeness are not certified.',
    'Actual-print premium is price times contracts times the explicitly reported premium multiplier, before fees; it is not underlying notional, delta exposure or investor capital at risk.',
    'Bid, ask and midpoint are quote references, never actual trades or total traded premium; chain last-price fields are retained only as source fields.',
    'Volume is dated activity; open interest is a separately dated outstanding contract count. Neither establishes opening/closing intent, buyer aggressor, beneficial owner or bullishness.',
    'No dealer inventory, dealer gamma exposure, gamma squeeze, causal squeeze confirmation or calibrated probability is inferred.',
    'Missing observations remain unknown. Different feeds and chain snapshots are not pooled into activity totals.',
]


def _require(ok, code):
    if not ok:
        raise ValueError(code)


def _text(value):
    _require(type(value) is str and bool(value.strip()), 'NONEMPTY_FIELD_REQUIRED')
    return value


def _count(value):
    number = market_flow._number(value, 0)
    _require(number == number.to_integral_value(), 'INTEGER_CONTRACT_COUNT_REQUIRED')
    return number


def _contract(payload):
    for field in CONTRACT_FIELDS:
        _require(payload.get(field) is not None, 'MISSING_CONTRACT_' + field.upper())
    for field in ('contract_id', 'underlying_id', 'deliverable'):
        _text(payload[field])
        _require(market_flow._resolved_basis(payload[field]) is not None, 'UNRESOLVED_CONTRACT_' + field.upper())
    _require(payload['right'] in ('call', 'put'), 'RIGHT_MUST_BE_CALL_OR_PUT')
    _require(type(payload['currency']) is str and re.fullmatch('[A-Z]{3}', payload['currency']),
             'EXPLICIT_CURRENCY_REQUIRED')
    _require(payload['premium_unit'] == 'currency_per_multiplier_unit', 'EXPLICIT_PREMIUM_UNIT_REQUIRED')
    market_flow._day(payload['expiry'])
    market_flow._positive(payload['strike'])
    market_flow._positive(payload['multiplier'])
    return {field: deepcopy(payload[field]) for field in CONTRACT_FIELDS}


def _identity(payload):
    contract = _contract(payload)
    # Numeric spellings 50 and 50.0 describe the same strike/multiplier.
    return tuple(market_flow._number(contract[key]) if key in ('strike', 'multiplier')
                 else contract[key] for key in CONTRACT_FIELDS)


def _observed(record, field, cutoff):
    value = market_flow._time(record['payload'].get(field))
    _require(value <= cutoff and value <= market_flow._time(record['available_at']),
             'OBSERVATION_AFTER_CUTOFF_OR_AVAILABILITY')
    _require(value.date() <= market_flow._day(record['payload']['expiry']), 'OBSERVATION_AFTER_EXPIRY_DATE')
    return value


def _quote(payload, event=None):
    result = {'bid': None, 'ask': None, 'midpoint': None, 'quote_at': payload.get('quote_at'),
              'quote_age_seconds': None, 'print_location': 'UNKNOWN', 'executed_trade': False}
    if all(payload.get(key) is None for key in ('bid', 'ask', 'quote_at')):
        return result
    bid, ask = market_flow._number(payload.get('bid'), 0), market_flow._number(payload.get('ask'), 0)
    at = market_flow._time(payload.get('quote_at'))
    _require(ask >= bid, 'CROSSED_QUOTE')
    if event is not None:
        _require(at <= event, 'QUOTE_AFTER_OBSERVATION')
        result['quote_age_seconds'] = (event - at).total_seconds()
    result.update(bid=market_flow._value(bid), ask=market_flow._value(ask),
                  midpoint=market_flow._value((bid + ask) / 2))
    return result


def _issue(result, record, code):
    result['issues'].append({'record_id': record.get('id'), 'code': code})


def _revision_ambiguities(records):
    """Eligible revision forks stay unknown instead of silently adding leaves."""
    by_id = {r['id']: r for r in records}
    edges, children = {}, {}
    for row in records:
        parent = by_id.get(row.get('supersedes'))
        if row.get('kind') not in ('option_print', 'option_chain') or not parent:
            continue
        if row.get('action') not in ('replace', 'cancel'):
            continue
        disallowed = set(row.get('exclusion_reasons', [])) - {
            'SUPERSEDED_BY_AVAILABLE_REVISION', 'CANCELLED_BY_AVAILABLE_REVISION', 'CANCELLATION_ENVELOPE'}
        if disallowed:
            continue
        children.setdefault(parent['id'], []).append(row['id'])
        edges.setdefault(parent['id'], set()).add(row['id'])
        edges.setdefault(row['id'], set()).add(parent['id'])
    ambiguous = set()
    for rid, leaves in children.items():
        if len(leaves) < 2:
            continue
        pending = [rid]
        while pending:
            current = pending.pop()
            if current not in ambiguous:
                ambiguous.add(current)
                pending.extend(edges.get(current, []))
    return ambiguous


def analyze(document):
    """Analyze common option_print/option_chain envelopes at one exact cutoff."""
    evidence = market_sources.normalize(document)
    cutoff = market_flow._time(evidence['as_of'])
    settings = document.get('settings', {})
    _require(type(settings) is dict, 'SETTINGS_OBJECT_REQUIRED')
    max_quote_age = (market_flow._number(settings['max_quote_age_seconds'], 0)
                     if settings.get('max_quote_age_seconds') is not None else None)
    result = {'schema_version': 1, 'kind': 'OPTIONS_ACTIVITY', 'as_of': evidence['as_of'],
              'prints': [], 'chains': [], 'issues': deepcopy(evidence['issues']),
              'evidence': evidence, 'limitations': list(LIMITS), 'execution_authorized': False}
    ambiguous = _revision_ambiguities(evidence['records'])
    groups, contracts = {}, {}
    for row in evidence['records']:
        if row['kind'] not in ('option_print', 'option_chain'):
            continue
        if not row['eligible']:
            _issue(result, row, 'INELIGIBLE_OPTION_RECORD: ' + ';'.join(row.get('exclusion_reasons') or []))
            continue
        if row['id'] in ambiguous:
            _issue(result, row, 'UNRESOLVED_OPTION_REVISION_GRAPH')
            continue
        try:
            payload = row['payload']
            _require(payload.get('status', 'original') in ('original', 'corrected'),
                     'CANCEL_OR_UNKNOWN_STATUS_REQUIRES_COMMON_REVISION_ENVELOPE')
            _require(payload.get('status') != 'corrected' or row.get('action') == 'replace',
                     'CORRECTION_REQUIRES_REPLACE_ENVELOPE')
            identity = _identity(payload)
            _text(row.get('ticker'))
            feed = _text(payload.get('feed_id'))
            event_field = 'event_at' if row['kind'] == 'option_print' else 'observed_at'
            event = _observed(row, event_field, cutoff)
            key = (row['ticker'], feed, row['kind'], payload['contract_id'],
                   _text(payload.get('print_id')) if row['kind'] == 'option_print' else payload['observed_at'])
            contracts.setdefault((row['ticker'], feed, payload['contract_id']), []).append((row, identity))
            groups.setdefault(key, []).append((row, event))
        except (ValueError, TypeError, OverflowError) as error:
            _issue(result, row, 'UNUSABLE_OPTION_RECORD: ' + str(error))
    conflict_ids = set()
    for members in contracts.values():
        if len({identity for _, identity in members}) > 1:
            conflict_ids.update(row['id'] for row, _ in members)
    for members in groups.values():
        if any(row['id'] in conflict_ids for row, _ in members):
            for row, _ in members:
                _issue(result, row, 'CONFLICTING_CONTRACT_IDENTITY')
            continue
        if len({json.dumps(row['payload'], sort_keys=True, allow_nan=False) for row, _ in members}) > 1:
            for row, _ in members:
                _issue(result, row, 'CONFLICTING_OPTION_FEED_IDENTITY_REQUIRES_REVISION')
            continue
        record, event = min(members, key=lambda item: item[0]['id'])
        for duplicate, _ in members:
            if duplicate is not record:
                _issue(result, duplicate, 'DUPLICATE_WITHIN_FEED_NOT_COUNTED')
        p = record['payload']
        try:
            row = {'record_id': record['id'], 'ticker': record['ticker'], 'feed_id': p['feed_id'],
                   'contract': _contract(p), 'source_id': record['source']['id'],
                   'available_at': record['available_at'], 'aggressor_side': 'UNKNOWN',
                   'open_close_intent': 'UNKNOWN', 'dealer_position': 'UNKNOWN',
                   'underlying_exposure': None}
            try:
                row['quote'] = _quote(p, event)
                age = row['quote']['quote_age_seconds']
                row['quote']['age_exceeds_declared_limit'] = (
                    market_flow._number(age, 0) > max_quote_age
                    if age is not None and max_quote_age is not None else None)
            except (ValueError, TypeError, OverflowError) as error:
                row['quote'] = {'bid': None, 'ask': None, 'midpoint': None,
                                'print_location': 'UNKNOWN', 'executed_trade': False}
                _issue(result, record, 'UNUSABLE_OPTION_QUOTE: ' + str(error))
            if record['kind'] == 'option_print':
                _require(p.get('quantity_unit') == 'contracts', 'CONTRACT_QUANTITY_UNIT_REQUIRED')
                quantity = _count(p.get('contracts'))
                _require(quantity > 0, 'POSITIVE_PRINT_CONTRACTS_REQUIRED')
                price = market_flow._number(p.get('price'), 0)
                _require(p.get('price_basis') == 'actual_print', 'ACTUAL_PRINT_PRICE_BASIS_REQUIRED')
                row.update(print_id=p['print_id'], event_at=p['event_at'], contracts=market_flow._value(quantity),
                           price=market_flow._value(price), price_basis='actual_print',
                           actual_print_premium=market_flow._value(price * quantity * market_flow._positive(p['multiplier'])),
                           premium_currency=p['currency'], fees_included=False)
                quote = row['quote']
                if quote.get('bid') is not None:
                    bid, ask = market_flow._number(p['bid']), market_flow._number(p['ask'])
                    quote['print_location'] = ('LOCKED_QUOTE' if bid == ask else 'ABOVE_ASK' if price > ask else
                                              'AT_ASK' if price == ask else 'BELOW_BID' if price < bid else
                                              'AT_BID' if price == bid else 'BETWEEN')
                    if quote.get('age_exceeds_declared_limit'):
                        quote['print_location'] = 'UNKNOWN_STALE_UNDER_DECLARED_LIMIT'
                result['prints'].append(row)
            else:
                row.update(observed_at=p['observed_at'], volume_contracts=None, volume_date=p.get('volume_date'),
                           open_interest_contracts=None, open_interest_date=p.get('open_interest_date'),
                           volume_to_dated_open_interest=None, ratio_semantics='DATED_ACTIVITY_OVER_SEPARATE_POSITION_SNAPSHOT',
                           actual_print_premium=None, last_price=deepcopy(p.get('last_price')),
                           last_price_semantics='RETAINED_SOURCE_FIELD_NOT_AN_IDENTIFIED_PRINT')
                for field, dayfield in (('volume_contracts', 'volume_date'),
                                        ('open_interest_contracts', 'open_interest_date')):
                    if p.get(field) is None:
                        continue
                    count = _count(p[field]); row[field] = market_flow._value(count)
                    try:
                        day = market_flow._day(p.get(dayfield))
                        _require(day <= event.date(), 'MEASUREMENT_AFTER_OBSERVATION')
                    except (ValueError, TypeError) as error:
                        row[dayfield] = None
                        _issue(result, record, 'UNUSABLE_' + dayfield.upper() + ': ' + str(error))
                if (row['volume_date'] and row['open_interest_date'] and row['volume_contracts'] is not None
                        and row['open_interest_contracts'] is not None and row['open_interest_contracts'] > 0):
                    row['volume_to_dated_open_interest'] = market_flow._value(
                        _count(p['volume_contracts']) / _count(p['open_interest_contracts']))
                result['chains'].append(row)
        except (ValueError, TypeError, OverflowError) as error:
            _issue(result, record, 'UNUSABLE_OPTION_RECORD: ' + str(error))
    result['summary'] = {'eligible_print_count': len(result['prints']), 'eligible_chain_count': len(result['chains']),
                         'pooled_premium': None, 'squeeze_confirmed': False}
    return result


def parse(document):
    """Parse explicit source-column mappings without guessing a vendor schema."""
    _require(type(document) is dict and document.get('adapter') in ADAPTERS, 'SUPPORTED_OPTIONS_ADAPTER_REQUIRED')
    text = document.get('text')
    _require(type(text) is str and len(text.encode('utf8')) <= market_sources.MAX_BYTES, 'BOUNDED_SOURCE_TEXT_REQUIRED')
    columns = document.get('columns')
    _require(type(columns) is dict and columns and all(type(k) is str and type(v) is str for k, v in columns.items())
             and len(set(columns.values())) == len(columns), 'EXPLICIT_UNIQUE_COLUMNS_REQUIRED')
    source = deepcopy(document.get('source'))
    _require(type(source) is dict, 'SOURCE_OBJECT_REQUIRED')
    available = document.get('available_at')
    if available is None:
        available = source.get('retrieved_at')
        source['availability_basis'] = 'first_observed_snapshot'
    prefix = document.get('id_prefix')
    if prefix is None:
        prefix = 'retained-options:' + hashlib.sha256(json.dumps(
            [document['adapter'], source, text], sort_keys=True).encode('utf8')).hexdigest()[:24]
    _text(prefix)
    reader = csv.DictReader(io.StringIO(text), delimiter=document.get('delimiter', ','))
    _require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames)
             and all(header in reader.fieldnames for header in columns.values()), 'SOURCE_HEADERS_MISSING_OR_DUPLICATE')
    records = []
    for index, raw in enumerate(reader):
        _require(index < market_sources.MAX_RECORDS, 'TOO_MANY_SOURCE_ROWS')
        payload = {key: raw.get(header) if raw.get(header) != '' else None for key, header in columns.items()}
        ticker = payload.pop('ticker', None)
        envelope = {'id': prefix + ':' + str(index), 'kind': ADAPTERS[document['adapter']],
                    'ticker': ticker, 'available_at': available, 'source': deepcopy(source), 'payload': payload}
        payload['raw_fields'] = deepcopy(raw)
        if None in raw or any(value is None for value in raw.values()):
            envelope['parse_error'] = 'DELIMITED_ROW_WIDTH_MISMATCH'
        if envelope['kind'] == 'float':
            try:
                _require(payload.get('share_basis') == 'float' and payload.get('quantity_unit') == 'shares',
                         'REPORTED_FLOAT_SHARE_COUNT_REQUIRED')
                market_flow._positive(payload.get('float_shares'))
                market_flow._day(payload.get('effective_date'))
                for field in ('issuer_id', 'share_class', 'measure_basis'):
                    _text(payload.get(field))
            except (ValueError, TypeError) as error:
                envelope['parse_error'] = str(error)
        records.append(envelope)
    evidence = market_sources.normalize({'schema_version': document.get('schema_version'),
                                         'as_of': document.get('as_of'), 'records': records})
    evidence['adapter'] = document['adapter']
    evidence['source_text_sha256'] = hashlib.sha256(text.encode('utf8')).hexdigest()
    evidence['columns'] = deepcopy(columns)
    evidence['limitations'] += list(LIMITS)
    return evidence


def bind_float(document):
    """Bind explicit dated float operands, delegating every squeeze calculation."""
    linked = deepcopy(document)
    links = linked.pop('float_links', None)
    _require(type(links) is list and len(links) <= market_sources.MAX_RECORDS, 'EXPLICIT_FLOAT_LINKS_REQUIRED')
    evidence = market_sources.normalize(linked)
    index = {}
    for row in linked['records']:
        index.setdefault(row.get('id'), []).append(row)
    seen = set()
    for link in links:
        _require(type(link) is dict and set(link) == {'short_interest_record_id', 'float_record_id'},
                 'EXACT_FLOAT_LINK_FIELDS_REQUIRED')
        sid, fid = link['short_interest_record_id'], link['float_record_id']
        _text(sid); _text(fid)
        _require(sid not in seen and len(index.get(sid, [])) == 1 and len(index.get(fid, [])) == 1,
                 'UNIQUE_FLOAT_AND_SHORT_INTEREST_RECORDS_REQUIRED')
        seen.add(sid)
        short, floating = index[sid][0], index[fid][0]
        _require(short.get('kind') == 'short_interest' and floating.get('kind') == 'float', 'FLOAT_LINK_KIND_MISMATCH')
        _require(floating['payload'].get('quantity_unit') in (None, 'shares'),
                 'FLOAT_LINK_CONTRADICTORY_QUANTITY_UNIT')
        previous = short['payload'].get('float_record_id')
        _require(previous in (None, fid), 'CONFLICTING_EXISTING_FLOAT_LINK')
        short['payload']['float_record_id'] = fid
    positions = market_flow.positioning(linked)
    squeeze = market_flow.squeeze(linked)
    return {'kind': 'DATED_FLOAT_BINDING', 'schema_version': 1, 'as_of': evidence['as_of'],
            'float_links': deepcopy(links), 'document': linked, 'positioning': positions, 'squeeze': squeeze,
            'limitations': ['Explicit links do not certify source meaning. Existing positioning validates dated same-issuer/class float and adjustment compatibility.',
                           'Shares outstanding, market capitalization and currency-valued SEC public float are not float share counts. No automatic substitution is performed.',
                           'Unknown, ineligible or incompatible float evidence stays unknown in existing squeeze calculations.'],
            'execution_authorized': False}
