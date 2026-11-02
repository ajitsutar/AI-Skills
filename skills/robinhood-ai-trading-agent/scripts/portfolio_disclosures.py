"""Normalize retained public disclosures for on-demand research; no network or I/O.

Source review and security identities are caller declarations, not authenticated by
this adapter. Numeric ranges remain ranges, and 13F weights describe only a basket.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import xml.etree.ElementTree as ET

from price_audit import timestamp
from quant_common import digest, integer, require


def _text(value, name):
    require(isinstance(value, str) and bool(value.strip()), 'TEXT_REQUIRED:' + name)
    return value.strip()


def _money(value, name):
    require(not isinstance(value, bool), 'INVALID_NUMBER:' + name)
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError('INVALID_NUMBER:' + name) from exc
    require(result.is_finite() and result >= 0, 'INVALID_NUMBER:' + name)
    return result


def _meta(row, subject_id):
    result = {key: _text(row[key], key) for key in
              ('event_id', 'source_ref', 'event_at', 'published_at', 'available_at')}
    result['subject_id'] = subject_id
    result['revision'] = integer(row['revision'], 'revision')
    require(type(row['withdrawn']) is bool, 'WITHDRAWN_BOOLEAN_REQUIRED')
    result['withdrawn'] = row['withdrawn']
    event, published, available = [timestamp(result[key]) for key in
                                    ('event_at', 'published_at', 'available_at')]
    require(event <= published <= available, 'INVALID_INFORMATION_CLOCKS')
    if row.get('retrieved_at') is not None:
        require(timestamp(row['retrieved_at']) >= available, 'RETRIEVAL_PRECEDES_AVAILABILITY')
        result['retrieved_at'] = row['retrieved_at']
    return result


def _identity(cusip, when, as_of, mappings):
    matches = []
    for mapping in mappings:
        if mapping['cusip'] != cusip:
            continue
        valid_from = timestamp(mapping['valid_from'])
        valid_to = timestamp(mapping['valid_to']) if mapping.get('valid_to') else None
        known = timestamp(mapping['available_at'])
        require(valid_to is None or valid_to > valid_from, 'INVALID_IDENTITY_INTERVAL')
        _text(mapping['source_ref'], 'identity.source_ref')
        _text(mapping['security_id'], 'identity.security_id')
        if valid_from <= when and (valid_to is None or when < valid_to) and known <= as_of:
            matches.append(mapping)
    require(len(matches) <= 1, 'AMBIGUOUS_SECURITY_MAPPING:' + cusip)
    return matches[0] if matches else None


def _field(node, name, default=None):
    found = [el.text.strip() if el.text else '' for el in node.iter()
             if el.tag.rsplit('}', 1)[-1] == name]
    require(len(found) <= 1, 'DUPLICATE_XML_FIELD:' + name)
    if not found:
        require(default is not None, 'MISSING_XML_FIELD:' + name)
        return default
    return found[0]


def _sec(document, as_of, subject_id):
    source = document['source']
    record = _meta(source, subject_id)
    form = source['form']
    require(form in ('13F-HR', '13F-HR/A', '13F-NT', '13F-NT/A'), 'UNSUPPORTED_13F_FORM')
    if timestamp(record['available_at']) > as_of:
        return [], ['DISCLOSURE_NOT_YET_AVAILABLE'], [], 'unavailable'
    if form.startswith('13F-NT'):
        return [], ['NOTICE_ONLY_FOLLOW_REPORTING_MANAGER_NOT_LIQUIDATION'], [], 'unavailable'
    amendment = source['amendment_type']
    require(amendment in ('none', 'restatement', 'new_holdings'), 'UNKNOWN_AMENDMENT_TYPE')
    require((form.endswith('/A') and amendment != 'none') or
            (not form.endswith('/A') and amendment == 'none'), 'FORM_AMENDMENT_MISMATCH')
    if amendment == 'new_holdings':
        return [], ['SUPPLEMENTAL_AMENDMENT_REQUIRES_EXPLICIT_BASE_RECONCILIATION'], [], 'unavailable'
    require(source['currency'] == 'USD', '13F_VALUES_REQUIRE_USD')
    require(source['value_unit'] in ('USD', 'USD_thousands'), 'EXPLICIT_13F_VALUE_UNIT_REQUIRED')
    factor = Decimal(1000) if source['value_unit'] == 'USD_thousands' else Decimal(1)
    _text(document['information_table_xml'], 'information_table_xml')
    xml = document['information_table_xml']
    require(len(xml.encode('utf-8')) <= 16_000_000, 'XML_SIZE_LIMIT')
    require('<!DOCTYPE' not in xml.upper() and '<!ENTITY' not in xml.upper(), 'XML_DECLARATIONS_NOT_SUPPORTED')
    require(hashlib.sha256(xml.encode('utf-8')).hexdigest() == source['table_sha256'], 'TABLE_HASH_MISMATCH')
    root = ET.fromstring(xml)
    entries = [node for node in root.iter() if node.tag.rsplit('}', 1)[-1] == 'infoTable']
    require(bool(entries), 'EMPTY_INFORMATION_TABLE')
    expected_count = integer(source['expected_table_entry_count'], 'expected_table_entry_count', 1)
    expected_total = _money(source['expected_table_value'], 'expected_table_value') * factor
    excluded, positions, warnings, total = [], [], [], Decimal(0)
    mapping_known = timestamp(record['available_at'])
    for index, node in enumerate(entries):
        cusip = _text(_field(node, 'cusip'), 'cusip')
        value = _money(_field(node, 'value'), 'table.value') * factor
        total += value
        row = {'row': index, 'cusip': cusip, 'reported_value_usd': str(value),
               'name_of_issuer': _field(node, 'nameOfIssuer'),
               'title_of_class': _field(node, 'titleOfClass'),
               'share_or_principal_type': _field(node, 'sshPrnamtType'),
               'reported_quantity': str(_money(_field(node, 'sshPrnamt'), 'table.quantity'))}
        put_call = _field(node, 'putCall', '')
        if put_call or row['share_or_principal_type'] != 'SH':
            row['reason'] = 'OPTION_OR_NON_SHARE_EXCLUDED_FROM_COMMON_BASKET'
            row['put_call'] = put_call or None
            excluded.append(row)
            continue
        mapping = _identity(cusip, timestamp(record['event_at']), as_of, document['security_map'])
        if mapping is None:
            row['reason'] = 'UNRESOLVED_SECURITY_IDENTITY'
            excluded.append(row)
            warnings.append('UNRESOLVED_SECURITY_IDENTITY:' + cusip)
            continue
        mapping_known = max(mapping_known, timestamp(mapping['available_at']))
        if mapping['asset_type'] != 'common_stock':
            row['reason'] = 'NON_COMMON_ASSET_EXCLUDED'
            excluded.append(row)
            continue
        positions.append({'security_id': mapping['security_id'], 'asset_type': 'common_stock',
                          'eligible_common': True, 'market_value': str(value), 'cusip': cusip,
                          'identity_source_ref': mapping['source_ref'],
                          'reported_quantity': row['reported_quantity']})
    if len(entries) != expected_count or total != expected_total:
        warnings.append('COVER_PAGE_TABLE_TOTAL_OR_ENTRY_COUNT_MISMATCH')
    complete = (source.get('reported_table_complete') is True and
                source.get('source_reviewed') is True and not warnings)
    if source.get('reported_table_complete') is not True:
        warnings.append('TABLE_COMPLETENESS_UNCONFIRMED')
    if source.get('source_reviewed') is not True:
        warnings.append('SOURCE_REVIEW_UNCONFIRMED')
    record.update(positions=positions, complete_reported_basket=complete, currency='USD',
                  available_at=mapping_known.isoformat(), form=form,
                  amendment_type=amendment, reported_table_value_usd=str(total),
                  table_sha256=source['table_sha256'],
                  included_managers=source.get('included_managers', []))
    warnings.append('WEIGHTS_ARE_REPORTED_COMMON_BASKET_NOT_TOTAL_MANAGER_NAV')
    return [record], warnings, excluded, 'normalized' if complete else 'partial'


def _events(document, as_of, subject_id):
    records, excluded, warnings = [], [], []
    recommendation = document['kind'] == 'public_recommendations'
    for index, source in enumerate(document['events']):
        record = _meta(source, subject_id)
        if timestamp(record['available_at']) > as_of:
            excluded.append({'row': index, 'event_id': record['event_id'], 'reason': 'NOT_YET_AVAILABLE'})
            continue
        action = source['action']
        if action not in ('BUY', 'SELL', 'PARTIAL_SELL'):
            excluded.append({'row': index, 'event_id': record['event_id'], 'reason': 'UNSUPPORTED_OR_UNCLEAR_ACTION'})
            continue
        security = _text(source['security_id'], 'security_id')
        common = source.get('asset_type') == 'common_stock' and source.get('identity_reviewed') is True
        reviewed = source.get('source_reviewed') is True
        record.update(security_id=security, action='SELL' if action == 'PARTIAL_SELL' else action,
                      sale_scope='partial' if action == 'PARTIAL_SELL' else source.get('sale_scope', 'unknown'),
                      eligible_common=common, qualifying=reviewed and common,
                      asset_type=source.get('asset_type'), owner=source.get('owner'))
        require(record['sale_scope'] in ('full', 'partial', 'unknown'), 'INVALID_SALE_SCOPE')
        if recommendation:
            record['qualifying'] = (record['qualifying'] and source.get('speaker_verified') is True
                                    and source.get('recommendation_verified') is True
                                    and source.get('source_context') == 'original_recommendation')
            record['speaker'] = source.get('speaker')
            record['horizon'] = source.get('horizon', 'unspecified')
            if not record['qualifying']:
                warnings.append('RECOMMENDATION_NOT_QUALIFIED:' + record['event_id'])
        else:
            _text(source['owner'], 'owner')
            amount_range = source.get('amount_range')
            if amount_range is not None:
                require(isinstance(amount_range, dict), 'AMOUNT_RANGE_OBJECT_REQUIRED')
                low = _money(amount_range['lower'], 'range.lower')
                high = _money(amount_range['upper'], 'range.upper') if amount_range.get('upper') is not None else None
                require(high is None or high >= low, 'INVALID_AMOUNT_RANGE')
                record['amount_range'] = {'lower': str(low), 'upper': str(high) if high is not None else None,
                                          'currency': _text(amount_range['currency'], 'range.currency')}
            else:
                record['amount_range'] = None
            record['exact_quantity'] = None
            record['actual_portfolio_weight'] = None
            warnings.append('TRANSACTION_RANGE_IS_NOT_HOLDINGS_WEIGHT:' + record['event_id'])
        records.append(record)
    # Identical records are idempotent. Contradictory revisions are retained for
    # the engine to freeze rather than silently choosing the last encountered row.
    unique = {}
    for record in records:
        signature = _semantic_digest(record)
        if signature not in unique or timestamp(record['available_at']) < timestamp(unique[signature]['available_at']):
            unique[signature] = record
    records = sorted(unique.values(), key=lambda row: (timestamp(row['available_at']), row['event_id'], row['revision']))
    groups = defaultdict(list)
    for row in records:
        groups[(row['event_id'], row['revision'])].append(row)
    conflicts = [event_id for (event_id, _), rows in groups.items() if len(rows) > 1]
    warnings.extend('CONFLICTING_REVISION:' + event_id for event_id in sorted(set(conflicts)))
    status = 'partial' if conflicts or any(not row['qualifying'] for row in records) else 'normalized'
    return records, warnings, excluded, status if records else 'unavailable'


def normalize(document):
    """Return engine-compatible records from explicitly reviewed retained inputs."""
    as_of = timestamp(document['as_of'])
    subject = _text(document['subject_id'], 'subject_id')
    kind = document['kind']
    require(kind in ('sec_13f', 'public_transactions', 'public_recommendations'), 'UNKNOWN_DISCLOSURE_KIND')
    if kind == 'sec_13f':
        records, warnings, excluded, status = _sec(document, as_of, subject)
    else:
        records, warnings, excluded, status = _events(document, as_of, subject)
    return {'status': status, 'as_of': document['as_of'], 'subject_id': subject,
            'records': records, 'warnings': sorted(set(warnings)), 'excluded_rows': excluded,
            'input_sha256': digest(document), 'source_authenticity': 'caller_review_declarations_not_independently_verified',
            'refresh_mode': 'on_demand'}


def _semantic_digest(row):
    # The event/publication clocks are immutable source content. A later fetch
    # changes retrieval/availability observations, not a filing's economic facts.
    return digest({key: value for key, value in row.items() if key not in ('available_at', 'retrieved_at')})


def changes(document):
    """Pure refresh comparison; return a new checkpoint for host-controlled storage.

    An initial baseline is not a mass alert. Incomplete refreshes never remove
    known events. Withdrawal must be an explicit newer revision.
    """
    result = normalize(document['current'])
    previous = document.get('previous')
    if previous is not None:
        require(previous.get('schema_version') == 1 and isinstance(previous.get('events'), dict), 'CHECKPOINT_SCHEMA_MISMATCH')
        require(previous['subject_id'] == result['subject_id'], 'CHECKPOINT_SUBJECT_MISMATCH')
        require(previous['kind'] == document['current']['kind'], 'CHECKPOINT_KIND_MISMATCH')
        require(timestamp(previous['as_of']) <= timestamp(result['as_of']), 'CHECKPOINT_TIME_REVERSED')
        for key, saved in previous['events'].items():
            _text(key, 'checkpoint.event_id')
            integer(saved['revision'], 'checkpoint.revision')
            require(len(saved['sha256']) == 64 and all(c in '0123456789abcdef' for c in saved['sha256']), 'CHECKPOINT_HASH_INVALID')
            require(type(saved['withdrawn']) is bool, 'CHECKPOINT_WITHDRAWN_INVALID')
            require(timestamp(saved['first_available_at']) <= timestamp(previous['as_of']), 'CHECKPOINT_FUTURE_EVENT')
    state = dict(previous['events']) if previous else {}
    new, updated, conflicts = [], [], []
    groups = defaultdict(list)
    for row in result['records']:
        groups[row['event_id']].append(row)
    for key, rows in groups.items():
        revision = max(row['revision'] for row in rows)
        candidates = [row for row in rows if row['revision'] == revision]
        if len({_semantic_digest(row) for row in candidates}) != 1:
            conflicts.append(key)
            continue
        row = candidates[0]
        key = row['event_id']
        signature = _semantic_digest(row)
        old = state.get(key)
        if old and row['revision'] < old['revision']:
            continue
        if old and row['revision'] == old['revision']:
            if signature != old['sha256']:
                conflicts.append(key)
            continue
        if old is None:
            new.append(key)
        else:
            updated.append(key)
        state[key] = {'revision': row['revision'], 'sha256': signature, 'withdrawn': row['withdrawn'],
                      'first_available_at': row['available_at'], 'first_recorded_at': result['as_of']}
    # The proposed checkpoint is emitted, never written; conflicts are not an
    # authorized overwrite of the last known good event version.
    conflict_evidence = dict((previous or {}).get('unresolved_conflicts', {}))
    for key in conflicts:
        conflict_evidence[key] = {'observed_at': result['as_of'],
                                  'revision': max(row['revision'] for row in groups[key]),
                                  'records_sha256': sorted({_semantic_digest(row) for row in groups[key]})}
    for key in new + updated:
        if key not in conflicts and key in conflict_evidence and state[key]['revision'] > conflict_evidence[key]['revision']:
            conflict_evidence.pop(key, None)
    status = 'conflict' if conflict_evidence else result['status']
    last_success = result['as_of'] if status == 'normalized' else (previous or {}).get('last_successful_as_of')
    baseline = (previous or {}).get('last_successful_as_of') is None
    return {'status': status, 'normalized': result,
            'baseline_created': baseline, 'new_event_ids': [] if baseline else sorted(set(new)),
            'updated_event_ids': [] if baseline else sorted(set(updated)),
            'conflicting_event_ids': sorted(set(conflicts)),
            'checkpoint': {'schema_version': 1, 'subject_id': result['subject_id'],
                           'kind': document['current']['kind'],
                           'as_of': result['as_of'], 'last_attempt_status': status,
                           'last_successful_as_of': last_success,
                           'unresolved_conflicts': conflict_evidence, 'events': state}}


def refresh_checkpoint(current, checkpoint_path):
    """Explicit CLI-only mutation, atomic replace and fail-fast owned lock.

    No timed loop or scheduler. An existing lock is not silently broken; the host
    must reconcile the interrupted run before removing it.
    """
    import os
    import tempfile
    from pathlib import Path
    path = Path(checkpoint_path).resolve()
    require(path.parent.is_dir(), 'CHECKPOINT_PARENT_REQUIRED')
    require(not Path(checkpoint_path).is_symlink(), 'CHECKPOINT_SYMLINK_NOT_SUPPORTED')
    lock = path.with_name(path.name + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temporary = None
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(str(os.getpid()))
        prior = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        result = changes({'current': current, 'previous': prior})
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(result['checkpoint'], stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        return result
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description='On-demand normalization of retained disclosure JSON; no fetch or orders')
    parser.add_argument('input', type=Path)
    parser.add_argument('--operation', choices=('normalize', 'changes'), default='normalize')
    parser.add_argument('--checkpoint', type=Path, help='Explicit on-demand checkpoint write; accepts normalization input')
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding='utf-8-sig'))
    require(args.checkpoint is None or args.operation == 'normalize', 'CHECKPOINT_REQUIRES_NORMALIZATION_INPUT')
    result = refresh_checkpoint(payload, args.checkpoint) if args.checkpoint else globals()[args.operation](payload)
    print(json.dumps(result, indent=2, allow_nan=False))
