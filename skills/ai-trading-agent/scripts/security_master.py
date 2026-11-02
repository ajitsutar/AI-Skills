"""Source-pointer-bound security episodes and point-in-time feature adapters.

No download, inferred issuer continuity, current-roster backfill or license grant.
Source bodies are supplied JSON or explicitly labeled reviewed extractions.
"""
import copy
from datetime import datetime
from quant_data_contracts import require, digest, text, day, sources, bound_record, timestamp, instant, cli
import point_in_time_data

ENTITY_FIELDS = ('issuer_id', 'share_class_id', 'instrument_type', 'currency')
EPISODE_FIELDS = ('issuer_id', 'share_class_id', 'kind', 'value', 'start_inclusive', 'end_exclusive', 'announced_at', 'available_at', 'revision_id')
FEATURE_FIELDS = tuple(sorted(point_in_time_data.RECORD_KEYS))


def snapshot(document):
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    cutoff = timestamp(document['as_of'])
    on = day(document['on'])
    require(on <= cutoff[:10], 'FUTURE_EFFECTIVE_DATE_NOT_HISTORICAL_SNAPSHOT')
    smap = sources(document['sources'])
    entities = {}
    for row in document['entities']:
        sid = text(row['security_id'], 'SECURITY_ID_REQUIRED')
        require(sid not in entities, 'DUPLICATE_SECURITY_ID')
        fields = bound_record(row, smap, ENTITY_FIELDS)
        for k, v in fields.items():
            text(v, k)
        require(fields['instrument_type'] in {'equity', 'etf', 'benchmark'}, 'SECURITY_TYPE')
        require(len(fields['currency']) == 3 and fields['currency'].isascii() and fields['currency'].isalpha() and fields['currency'].isupper(), 'CURRENCY_REQUIRED')
        entities[sid] = {'security_id': sid, **fields, 'source_id': row['source_id'],
                         'source_body_sha256': smap[row['source_id']]['body_sha256']}
    require(bool(entities), 'ENTITIES_REQUIRED')
    identities = [(r['issuer_id'], r['share_class_id']) for r in entities.values()]
    require(len(set(identities)) == len(identities), 'DUPLICATE_PERMANENT_IDENTITY')
    selected, versions, rejected = {}, {}, []
    for row in document['episodes']:
        sid = row['security_id']; eid = text(row['episode_id'], 'EPISODE_ID_REQUIRED')
        require(sid in entities, 'UNKNOWN_SECURITY_ID')
        fields = bound_record(row, smap, EPISODE_FIELDS)
        require(all(fields[k] == entities[sid][k] for k in ('issuer_id', 'share_class_id')),
                'EPISODE_SUBJECT_IDENTITY_MISMATCH')
        require(fields['kind'] in {'listing', 'membership', 'symbol'}, 'EPISODE_KIND')
        text(fields['value'], 'EPISODE_VALUE'); text(fields['revision_id'], 'REVISION_ID')
        start = day(fields['start_inclusive'])
        end = fields['end_exclusive']
        require(end is None or day(end) > start, 'EPISODE_INTERVAL')
        known = timestamp(fields['available_at']); announced = timestamp(fields['announced_at'])
        require(instant(known) >= instant(announced), 'AVAILABILITY_BEFORE_ANNOUNCEMENT')
        fields.update(available_at=known, announced_at=announced)
        invariant = (sid, fields['kind'], fields['value'])
        previous = versions.setdefault(eid, {'identity': invariant, 'revision_ids': set(), 'times': set()})
        require(previous['identity'] == invariant, 'EPISODE_IDENTITY_CHANGED_ACROSS_REVISIONS')
        require(fields['revision_id'] not in previous['revision_ids'], 'DUPLICATE_EPISODE_REVISION')
        require(known not in previous['times'], 'AMBIGUOUS_REVISION_AVAILABILITY')
        previous['revision_ids'].add(fields['revision_id']); previous['times'].add(known)
        if instant(known) > instant(cutoff):
            rejected.append({'episode_id': eid, 'revision_id': fields['revision_id'], 'reason': 'NOT_AVAILABLE_AT_AS_OF'})
            continue
        candidate = {'security_id': sid, 'episode_id': eid, **fields, 'source_id': row['source_id'],
                     'source_body_sha256': smap[row['source_id']]['body_sha256']}
        if eid not in selected or instant(known) > instant(selected[eid]['available_at']):
            selected[eid] = candidate
    active = [r for r in selected.values() if r['start_inclusive'] <= on and
              (r['end_exclusive'] is None or on < r['end_exclusive'])]
    # More than one contemporary listing/symbol episode is ambiguous in this narrow schema.
    for sid in entities:
        for kind in ('listing', 'symbol'):
            require(sum(r['security_id'] == sid and r['kind'] == kind for r in active) <= 1,
                    'AMBIGUOUS_ACTIVE_' + kind.upper())
    symbol_owner = {}
    for r in active:
        if r['kind'] == 'symbol':
            require(r['value'] not in symbol_owner, 'SIMULTANEOUS_SYMBOL_REUSE')
            symbol_owner[r['value']] = r['security_id']
    rows = []
    for sid, entity in entities.items():
        episodes = [r for r in active if r['security_id'] == sid]
        rows.append({**entity, 'active_episodes': episodes,
                     'listing_status': 'SOURCE_BOUND_ACTIVE' if any(r['kind'] == 'listing' for r in episodes) else 'NOT_ESTABLISHED_ACTIVE',
                     'membership_values': sorted({r['value'] for r in episodes if r['kind'] == 'membership'}),
                     'symbol_values': [r['value'] for r in episodes if r['kind'] == 'symbol']})
    return {'schema_version': 1, 'method': 'source_bound_security_episodes_v1', 'as_of': cutoff, 'on': on,
            'rows': rows, 'selected_episode_revisions': list(selected.values()), 'future_revisions_excluded': rejected,
            'input_sha256': digest(document), 'source_pointer_checks_passed': True,
            'historical_universe_complete': False, 'source_authenticity_verified': False,
            'limits': ['Internal security IDs bind supplied issuer/share-class identities; source truth and exhaustive historical membership are not certified.',
                       'Absence of an active episode is not proof of nonmembership or delisting.',
                       'A revised interval is used only after its supplied publication/availability time; retrieval time is not substituted for publication.',
                       'Corporate conversion requires a separate security and event ledger, not a rename inferred from a ticker or issuer name.']}


def adapt_records(document):
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    smap = sources(document['sources'])
    records, provenance = [], []
    for index, row in enumerate(document['records']):
        fields = bound_record(row, smap, FEATURE_FIELDS)
        records.append(fields)
        provenance.append({'record_index': index, 'source_id': row['source_id'],
                           'source_role': smap[row['source_id']]['source_role'],
                           'source_body_sha256': smap[row['source_id']]['body_sha256'],
                           'bindings': copy.deepcopy(row['bindings'])})
    dataset = {'schema_version': 1, 'dataset_id': text(document['dataset_id'], 'DATASET_ID'),
               'source': {'name': 'Source-bound supplied records',
                          'license': 'Not established by pointer verification',
                          'uri': 'urn:source-bound:' + digest(document['sources'])}, 'records': records}
    result = point_in_time_data.snapshot({'as_of': document['as_of'], 'dataset': dataset})
    master = None
    if document.get('security_contract') is not None:
        master = snapshot(document['security_contract'])
        require(instant(master['as_of']) == instant(document['as_of']), 'SECURITY_MASTER_AS_OF_MISMATCH')
        identities = {r['security_id'] for r in master['rows']}
        require(all(r['instrument_id'] in identities for r in records), 'FEATURE_SECURITY_NOT_IN_MASTER')
    return {'method': 'source_bound_feature_adapter_v1', 'dataset': dataset, 'snapshot': result,
            'provenance': provenance, 'input_sha256': digest(document), 'source_pointer_checks_passed': True,
            'identity_link_status': 'SOURCE_BOUND_IDENTIFIERS_MATCHED' if master else 'NOT_CHECKED',
            'security_master_input_sha256': master['input_sha256'] if master else None,
            'source_authenticity_verified': False, 'coverage_complete': False,
            'limits': ['All event, availability, unit and revision fields resolve to supplied source pointers; semantic extraction still needs review.',
                       'Later restatements do not replace earlier as-of records. No missing feature or availability is inferred.',
                       'The adapter does not acquire data, establish commercial data rights, or certify a complete universe.']}


if __name__ == '__main__':
    cli(lambda d: adapt_records(d) if d.get('operation') == 'features' else snapshot(d))
