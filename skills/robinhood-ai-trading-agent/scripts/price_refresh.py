"""Optional, immutable price-vintage reconciliation with conservative full fallback.

No HTTP requests or hidden caches. A tail can reuse a prefix only with a current,
hash-bound native provider prefix manifest. A local old-file hash is not such a
manifest. Real adapters must establish the provider's revision contract; this
helper checks supplied evidence and cannot authenticate a publisher.
"""
import copy
from quant_data_contracts import require, digest, text, day, finite, instant, sources, bound_record, cli

CONTRACT_FIELDS = {'provider', 'security_id', 'share_class_id', 'currency', 'adjustment',
                   'schema_version', 'parser_version', 'fields', 'units'}
PRICE_FIELDS = {'open', 'close', 'adjusted_close', 'high', 'low'}
FIELDS = PRICE_FIELDS | {'volume', 'dividend', 'split_factor'}
PROOF_FIELDS = ('provider', 'security_id', 'contract_sha256', 'prefix_start', 'prefix_end',
                'prefix_rows_sha256', 'hash_algorithm', 'revision', 'checked_at')


def snapshot(value):
    contract = value['contract']
    require(set(contract) == CONTRACT_FIELDS, 'EXACT_PRICE_CONTRACT_REQUIRED')
    for key in CONTRACT_FIELDS - {'fields', 'units', 'schema_version'}:
        text(contract[key], 'CONTRACT_' + key)
    require(type(contract['schema_version']) is int and contract['schema_version'] == 1, 'PRICE_SCHEMA_VERSION')
    fields = contract['fields']
    require(isinstance(fields, list) and fields and len(set(fields)) == len(fields) and set(fields) <= FIELDS, 'PRICE_FIELDS')
    require(set(contract['units']) == set(fields) and all(isinstance(x, str) and x for x in contract['units'].values()), 'FIELD_UNITS')
    rows = value['rows']
    require(isinstance(rows, list) and rows and len(rows) <= 100000, 'BOUNDED_NONEMPTY_PRICE_ROWS')
    require(value['rows_sha256'] == digest(rows), 'PRICE_ROWS_HASH_MISMATCH')
    dates = []
    for row in rows:
        require(set(row) == {'session', 'values', 'status'}, 'EXACT_PRICE_ROW_FIELDS')
        dates.append(day(row['session']))
        require(row['status'] in {'observed', 'reference', 'modeled'}, 'PRICE_ROW_STATUS')
        require(set(row['values']) == set(fields), 'PRICE_ROW_FIELD_CONTRACT')
        for key, x in row['values'].items():
            require(x is None or finite(x), 'FINITE_OR_NULL_PRICE_VALUE')
            if x is not None:
                require(x > 0 if key in PRICE_FIELDS | {'split_factor'} else x >= 0, 'INVALID_PRICE_VALUE')
        v = row['values']
        if all(v.get(x) is not None for x in ['low', 'high']):
            require(v['low'] <= v['high'], 'OHLC_ENVELOPE')
            for x in ('open', 'close'):
                if v.get(x) is not None:require(v['low'] <= v[x] <= v['high'], 'OHLC_ENVELOPE')
    require(dates == sorted(set(dates)), 'UNIQUE_ORDERED_PRICE_SESSIONS')
    text(value['revision'], 'PRICE_REVISION')
    return contract, {r['session']: r for r in rows}


def reconcile(document):
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    require(document['mode'] in {'full', 'incremental'}, 'REFRESH_MODE')
    require(type(document['partial_fetch_opt_in']) is bool, 'EXPLICIT_PARTIAL_FETCH_OPT_IN')
    require(document['current_scope'] in {'full', 'tail'}, 'CURRENT_CAPTURE_SCOPE')
    decision = instant(document['decision_at']); acquired = instant(document['acquired_at'])
    require(acquired >= decision, 'CAPTURE_BEFORE_RESEARCH_CUTOFF')
    contract, old = snapshot(document['previous'])
    new_contract, new = snapshot(document['current'])
    require(all(contract[k] == new_contract[k] for k in ('security_id', 'share_class_id')), 'SECURITY_IDENTITY_MISMATCH_NO_SUCCESSOR_SPLICE')
    require(max(new) <= acquired.date().isoformat(), 'FUTURE_PRICE_SESSION')
    expected = document['expected_sessions']
    require(expected and expected == sorted(set(map(day, expected))), 'EXPECTED_SESSION_CALENDAR')
    require(all(x in expected for x in new), 'CAPTURE_OUTSIDE_REQUESTED_GRID')
    source_map = sources(document.get('sources', []))
    base = {'schema_version': 1, 'input_sha256': digest(document), 'method': 'revision_aware_price_reconciliation_v1',
            'mode_requested': document['mode'], 'previous_rows_sha256': document['previous']['rows_sha256'],
            'current_rows_sha256': document['current']['rows_sha256'], 'source_authenticity_verified': False,
            'source_vintages_preserved': True, 'mutates_input': False,
            'limits': ['Reconciliation checks supplied normalized rows and a declared native provider prefix contract, not publisher authenticity.',
                       'No old bytes or outputs are modified. Changed dates invalidate declared dependencies; semantic source review remains necessary.',
                       'No source supplies an unchanged-prefix revision manifest merely because a local file has a hash. Without current evidence, fetch full history.',
                       'This operation performs no download, broker action, signal calculation or assertion of commercial data rights.']}
    def fallback(reason):
        return {**base, 'status': 'FULL_FETCH_REQUIRED', 'reason': reason, 'rows': None,
                'actual_prefix_reuse': False, 'invalidated_artifact_ids': [], 'invalidation_status': 'UNDETERMINED_UNTIL_FULL_REPRESENTATION'}
    equal_contract = digest(contract) == digest(new_contract)
    overlap_changes = sorted(x for x in set(old) & set(new) if digest(old[x]) != digest(new[x]))
    reuse = False; proof_hash = None
    if document['current_scope'] == 'full':
        if set(new) != set(expected):return fallback('FULL_CAPTURE_HAS_SESSION_GAPS')
        merged = new
        changed = sorted(x for x in set(old) | set(new) if x not in old or x not in new or digest(old[x]) != digest(new[x]))
        if not equal_contract:
            changed = sorted(set(old) | set(new))
    else:
        if document['mode'] != 'incremental' or not document['partial_fetch_opt_in']:
            return fallback('PARTIAL_FETCH_NOT_EXPLICITLY_SELECTED')
        if not equal_contract:return fallback('PRICE_REPRESENTATION_CONTRACT_CHANGED')
        if overlap_changes:return fallback('OVERLAP_REVISED_FETCH_FULL_HISTORY')
        prefix_end = max(old)
        prefix_dates = [x for x in expected if x <= prefix_end]
        if set(old) != set(prefix_dates):return fallback('PREVIOUS_PREFIX_NOT_COMPLETE_FOR_REQUEST')
        proof = document.get('prefix_proof')
        if proof is None:return fallback('CURRENT_PROVIDER_PREFIX_PROOF_MISSING')
        try:
            values = bound_record(proof, source_map, PROOF_FIELDS)
            src = source_map[proof['source_id']]
            if src['source_role'] != 'native_json':return fallback('PREFIX_PROOF_NOT_NATIVE_PROVIDER_REPRESENTATION')
            checked = instant(values['checked_at'])
            valid = (values['provider'] == contract['provider'] and values['security_id'] == contract['security_id']
                     and values['contract_sha256'] == digest(contract) and values['prefix_start'] == min(old)
                     and values['prefix_end'] == prefix_end and values['prefix_rows_sha256'] == document['previous']['rows_sha256']
                     and values['hash_algorithm'] == 'canonical-json-sha256-v1'
                     and values['revision'] == document['current']['revision'] and decision <= checked <= acquired
                     and instant(src['retrieved_at']) >= checked and instant(src['retrieved_at']) <= acquired)
        except (KeyError, ValueError, TypeError):
            return fallback('PREFIX_PROOF_INVALID_OR_UNRESOLVED')
        if not valid:return fallback('CURRENT_PROVIDER_PREFIX_PROOF_MISMATCH_OR_STALE')
        merged = {**old, **new}
        if set(merged) != set(expected):return fallback('MERGED_SESSION_GRID_INCOMPLETE')
        changed = sorted(set(new) - set(old)); reuse = True; proof_hash = src['body_sha256']
    rows = [copy.deepcopy(merged[x]) for x in expected]
    invalidated = []
    artifacts = document.get('derived_artifacts', [])
    require(len({x['id'] for x in artifacts}) == len(artifacts), 'DUPLICATE_DERIVED_ARTIFACT')
    for artifact in artifacts:
        start, end = day(artifact['source_start']), day(artifact['source_end'])
        require(start <= end, 'DEPENDENCY_INTERVAL_ORDER')
        if any(start <= x <= end for x in changed):invalidated.append(artifact['id'])
    return {**base, 'status': 'RECONCILED_INCREMENTAL' if reuse else 'RECONCILED_FULL',
            'rows': rows, 'rows_sha256': digest(rows), 'contract': copy.deepcopy(new_contract),
            'revision': document['current']['revision'], 'actual_prefix_reuse': reuse,
            'prefix_proof_body_sha256': proof_hash, 'changed_or_added_sessions': changed,
            'earliest_changed_or_added_session': min(changed) if changed else None,
            'invalidated_artifact_ids': invalidated, 'invalidation_status': 'DECLARED_DEPENDENCIES_CHECKED',
            'old_row_count': len(old), 'downloaded_row_count': len(new), 'retained_row_count': len(rows),
            'network_saving_measured': False}


if __name__ == '__main__':
    cli(reconcile)
