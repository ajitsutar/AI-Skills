"""Bounded descriptive metadata fitness; no acquisition or dataset certification.

HISTORICAL_DESCRIPTOR_V1 has no aliases. Recognition is field-role presence,
never enclosing names, identifiers, dates or expected analytical conclusions.
"""
from datetime import date, datetime

PROFILE = 'HISTORICAL_DESCRIPTOR_V1'
FIELDS = ('history_range', 'roster_snapshot_at', 'constituents', 'revised_download_at',
          'row_first_available_at', 'historical_membership', 'revision_vintages')
MAX_DEPTH = 8
MAX_NODES = 4096
MAX_DESCRIPTORS = 32
MAX_SCOPE_INVENTORY = 64
MAX_FIELD_JSON_BYTES = 16384
CERTIFICATIONS = {'source_authenticity_verified': False, 'point_in_time_complete_certified': False,
    'historical_universe_completeness_certified': False, 'no_lookahead_verified': False,
    'execution_authorized': False}
LIMITS = [
    'Only the documented descriptive metadata profile in the bound clock-source document is assessed.',
    'No row-level availability, historical membership, complete vintage chain or source authenticity is verified.',
    'No historical study, return calculation, acquisition or account action is performed.',
    'No supported descriptor does not mean no activity, no evidence or complete request coverage.',
    'Original field values use explicitly typed JSON text; numbers inside that text retain exact source tokens.',
]


def require(condition, code):
    if not condition: raise ValueError(code)


def pointer(parent, key):
    return parent + '/' + str(key).replace('~', '~0').replace('/', '~1')


def exact_codec():
    # Lazy import avoids a market_sources_report -> final_report import cycle.
    # This unchanged object codec preserves original numeric tokens, not floats.
    from request_coverage import exact_original_document, encode_objects
    return exact_original_document, encode_objects


def value_kind(value):
    if value is None: return 'null'
    if type(value) is bool: return 'boolean'
    if isinstance(value, str): return 'string'
    if isinstance(value, list): return 'array'
    if isinstance(value, dict): return 'object'
    return 'number'  # The strict original codec's private number-token value.


def original_field(source, field_pointer, present, value, encode):
    result = {'source_ref': {'source_id': source['id'], 'pointer': field_pointer},
        'source_sha256': source['sha256'], 'source_pointer_exists': present}
    if not present:
        return result
    result.update(original_value_kind=value_kind(value), encoding='EXACT_ORIGINAL_JSON_TEXT')
    try:
        raw = encode(value).rstrip(b'\n')
        require(len(raw) <= MAX_FIELD_JSON_BYTES, 'FIELD_JSON_SIZE_BOUND')
        result.update(original_json=raw.decode('utf8'), projection_status='EXACT_JSON_TEXT_RETAINED')
    except ValueError as error:
        result.update(projection_status='NOT_PROJECTED_BOUND', projection_limit=str(error))
    return result


def iso_day(value):
    return isinstance(value, str) and date.fromisoformat(value).isoformat() == value


def timestamp_state(value):
    if not isinstance(value, str): return 'MALFORMED', 'TIMEZONE_AWARE_TIMESTAMP_REQUIRED'
    try:
        if 'T' not in value:
            return ('INSUFFICIENT_PRECISION', 'DATE_ONLY_NOT_AN_INSTANT') if iso_day(value) else ('MALFORMED', 'INVALID_TIMESTAMP')
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None: return 'INSUFFICIENT_PRECISION', 'TIMEZONE_NOT_DECLARED'
        return 'DECLARED_VALUE', 'DECLARED_TIMESTAMP_NOT_AUTHENTICATED'
    except (ValueError, OverflowError):
        return 'MALFORMED', 'INVALID_TIMESTAMP'


def field_state(name, present, value):
    if not present: return 'ABSENT', 'FIELD_NOT_SUPPLIED'
    if value is None: return 'NULL', 'EXPLICIT_NULL_UNKNOWN'
    if value == '' or isinstance(value, (list, dict)) and not value:
        return 'EMPTY_DECLARATION', 'EMPTY_DOES_NOT_PROVE_ABSENCE'
    if type(value) is bool:
        return 'UNSUPPORTED_STRUCTURE', 'BOOLEAN_TRUE_NOT_EVIDENCE' if value else 'BOOLEAN_FALSE_NOT_EVIDENCE'
    if name == 'history_range':
        try:
            if not isinstance(value, list) or len(value) != 2 or not all(iso_day(v) for v in value):
                return 'MALFORMED', 'TWO_ISO_CALENDAR_DATES_REQUIRED'
            if value[0] > value[1]: return 'MALFORMED', 'CONTRADICTORY_HISTORY_INTERVAL'
            return 'DECLARED_VALUE', 'DESCRIPTIVE_PERIOD_NOT_OBSERVATION_COVERAGE'
        except (ValueError, TypeError): return 'MALFORMED', 'INVALID_HISTORY_INTERVAL'
    if name in ('roster_snapshot_at', 'revised_download_at'):
        return timestamp_state(value)
    if name == 'constituents':
        valid = isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)
        if not valid: return 'MALFORMED', 'NONEMPTY_STRING_MEMBER_LIST_REQUIRED'
        if len(set(value)) != len(value): return 'MALFORMED', 'DUPLICATE_DECLARED_MEMBERS'
        return 'DECLARED_VALUE', 'DECLARED_NAMES_WITHOUT_IDENTITY_OR_HISTORY_VERIFICATION'
    if isinstance(value, (dict, list)):
        return 'PRESENT_UNVERIFIED', 'DECLARED_STRUCTURE_NOT_ROW_LEVEL_VERIFICATION'
    if name == 'row_first_available_at' and isinstance(value, str):
        state, detail = timestamp_state(value)
        if state == 'DECLARED_VALUE': return state, 'GLOBAL_TIMESTAMP_NOT_PER_ROW_KNOWLEDGE'
        if state == 'INSUFFICIENT_PRECISION': return state, detail
        return 'UNSUPPORTED_STRUCTURE', 'UNSUPPORTED_AVAILABILITY_DECLARATION'
    return 'MALFORMED', 'SUPPORTED_EVIDENCE_OBJECT_OR_LIST_REQUIRED'


def descriptor(source, path, value, encode):
    fields = {}
    for name in FIELDS:
        present = name in value
        original = original_field(source, pointer(path, name), present, value.get(name), encode)
        state, detail = field_state(name, present, value.get(name))
        fields[name] = {**original, 'state': state, 'detail': detail}
    findings = []

    def finding(code, names, text):
        findings.append({'code': code, 'field_pointers': [pointer(path, n) for n in names], 'meaning': text})

    membership = fields['historical_membership']['state']
    if 'roster_snapshot_at' in value or 'constituents' in value:
        finding('HISTORICAL_UNIVERSE_SUPPORT_NOT_ESTABLISHED', ['roster_snapshot_at', 'constituents', 'historical_membership'],
            'The supplied snapshot does not establish membership throughout the declared history. '
            'Historical use of this selection would be conditioned on the supplied roster; '
            'historical-membership declaration state is ' + membership + '. '
            'No complete historical universe or measured survivorship bias is established.')
    else:
        finding('HISTORICAL_UNIVERSE_EVIDENCE_NOT_VERIFIED', ['historical_membership'],
            'Historical-membership declaration state is ' + membership + '; this metadata-only audit does not '
            'verify membership intervals or universe completeness.')
    availability = fields['row_first_available_at']['state']
    finding('NO_LOOKAHEAD_SUPPORT_NOT_ESTABLISHED', ['row_first_available_at'],
        'First-availability declaration state is ' + availability + '. The descriptor does not verify when '
        'each observation was knowable at earlier decisions. A global timestamp, download time or nonempty '
        'declaration does not establish row-level availability or no-look-ahead support.')
    vintages = fields['revision_vintages']['state']
    if 'revised_download_at' in value:
        finding('REVISION_AWARE_HISTORY_NOT_ESTABLISHED', ['revised_download_at', 'revision_vintages'],
            'The revised-download timestamp declaration does not establish earlier available versions. '
            'Revision-vintage declaration state is ' + vintages + '; this metadata-only audit does not '
            'reconstruct or establish earlier decision-time values. Actual value changes are not inferred.')
    else:
        finding('VINTAGE_COMPLETENESS_NOT_VERIFIED', ['revision_vintages'],
            'Revision-vintage declaration state is ' + vintages + '; a complete historical version chain '
            'is not verified. No revised-download event is inferred from another field.')
    bad = [name for name, row in fields.items() if row['state'] in ('MALFORMED', 'INSUFFICIENT_PRECISION', 'UNSUPPORTED_STRUCTURE')]
    projection_limited = [name for name, row in fields.items() if row.get('projection_status') == 'NOT_PROJECTED_BOUND']
    for name in bad:
        finding('FIELD_METADATA_LIMIT', [name], name + ': ' + fields[name]['state'] + ' / ' + fields[name]['detail'] + '. No replacement value is inferred.')
    for name in projection_limited:
        finding('FIELD_PROJECTION_BOUND', [name], 'Exact original value remains bound at this source pointer; display projection exceeded its bound and was omitted, not rounded.')
    declared = all(row['state'] in ('DECLARED_VALUE', 'PRESENT_UNVERIFIED') for row in fields.values())
    status = ('PARTIAL_OR_MALFORMED_METADATA' if bad or projection_limited else
              'DECLARATIONS_PRESENT_UNVERIFIED' if declared else 'METADATA_LIMITS_IDENTIFIED')
    extras = [pointer(path, name) for name in value if name not in FIELDS]
    if len(extras) > MAX_SCOPE_INVENTORY:
        status = 'PARTIAL_OR_MALFORMED_METADATA'
        finding('UNASSESSED_INVENTORY_BOUND', [], 'Additional unassessed fields remain bound in the original source; their displayed pointer inventory is truncated.')
    return {'profile': PROFILE, 'source_ref': {'source_id': source['id'], 'pointer': path},
        'source_sha256': source['sha256'], 'status': status, 'fields': fields, 'findings': findings,
        'unassessed_field_pointers': extras[:MAX_SCOPE_INVENTORY],
        'unassessed_field_count': len(extras), 'unassessed_inventory_truncated': len(extras) > MAX_SCOPE_INVENTORY,
        **CERTIFICATIONS}


def audit_bound_context(corpus, as_of_ref):
    """Audit the whole original clock source; no new caller selector or override."""
    common = {'method': 'source-metadata-fitness-1', 'profile': PROFILE, 'descriptors': [],
        'limits': LIMITS, **CERTIFICATIONS, 'whole_request_completeness_verified': False}
    counters = {'objects_visited': 0, 'arrays_visited': 0, 'nodes_visited': 0, 'descriptors_recognized': 0,
        'descriptors_with_limits': 0, 'unassessed_field_count': 0, 'traversal_truncated': False}
    common['traversal'] = {**counters, 'bounds': {'max_depth': MAX_DEPTH, 'max_nodes': MAX_NODES, 'max_descriptors': MAX_DESCRIPTORS}}
    if as_of_ref is None:
        return {**common, 'status': 'NO_BOUND_CONTEXT', 'scope': 'No external context was selected; unrelated corpus sources were not searched.'}
    require(isinstance(as_of_ref, dict) and set(as_of_ref) == {'source_id', 'pointer'}, 'EXACT_CLOCK_SOURCE_REFERENCE_REQUIRED')
    sid = as_of_ref['source_id']
    require(isinstance(sid, str) and sid in corpus.sources, 'CLOCK_SOURCE_OUTSIDE_CORPUS')
    entry = corpus.sources[sid]
    require(entry['format'] == 'json', 'ORIGINAL_JSON_CONTEXT_REQUIRED')
    decode, encode = exact_codec()
    original = decode(entry['raw'])
    from source_lineage import at
    at(original, as_of_ref['pointer'])  # Preserve the actual bound clock pointer.
    source = {'id': sid, 'sha256': entry['sha256']}
    common['source_binding'] = {**source, 'path': entry['path'], 'scope_pointer': '', 'clock_pointer': as_of_ref['pointer']}
    stack, rows, inspected, skipped = [iter([('', original, 0)])], [], [], []
    skipped_count = 0
    def skip(path, reason):
        nonlocal skipped_count
        skipped_count += 1
        counters['traversal_truncated'] = True
        if len(skipped) < MAX_SCOPE_INVENTORY: skipped.append({'pointer': path, 'reason': reason})
    def children(path, value, depth):
        items = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in items: yield pointer(path, key), child, depth + 1
    while stack:
        try: path, value, depth = next(stack[-1])
        except StopIteration:
            stack.pop(); continue
        if counters['nodes_visited'] >= MAX_NODES:
            skip(path, 'MAX_NODES'); break
        counters['nodes_visited'] += 1
        if depth > MAX_DEPTH:
            skip(path, 'MAX_DEPTH')
            continue
        if isinstance(value, dict):
            counters['objects_visited'] += 1
            recognized = 'history_range' in value and ('roster_snapshot_at' in value or 'revised_download_at' in value)
            if len(inspected) < MAX_SCOPE_INVENTORY: inspected.append({'pointer': path, 'profile_matched': recognized})
            if recognized:
                counters['descriptors_recognized'] += 1
                if len(rows) >= MAX_DESCRIPTORS:
                    skip(path, 'MAX_DESCRIPTORS'); break
                row = descriptor(source, path, value, encode); rows.append(row)
                counters['descriptors_with_limits'] += 1
                counters['unassessed_field_count'] += row['unassessed_field_count']
            stack.append(children(path, value, depth))
        elif isinstance(value, list):
            counters['arrays_visited'] += 1
            stack.append(children(path, value, depth))
    common['traversal'].update(counters)
    inventory_truncated = counters['objects_visited'] > len(inspected) or skipped_count > len(skipped)
    common.update(descriptors=rows, inspected_object_scopes=inspected, skipped_scopes=skipped,
        scope_inventory_truncated=inventory_truncated,
        skipped_scope_count=skipped_count)
    status = ('PARTIAL_METADATA_AUDIT' if counters['traversal_truncated'] or inventory_truncated else 'NO_SUPPORTED_DESCRIPTOR' if not rows else
              'PARTIAL_OR_MALFORMED_METADATA' if any(r['status'] == 'PARTIAL_OR_MALFORMED_METADATA' for r in rows) else
              'METADATA_LIMITS_IDENTIFIED' if any(r['status'] == 'METADATA_LIMITS_IDENTIFIED' for r in rows) else
              'DECLARATIONS_PRESENT_UNVERIFIED')
    return {**common, 'status': status, 'scope': 'Metadata-only profile audit of the whole bound clock-source JSON document; not whole-corpus or whole-request analysis.'}
