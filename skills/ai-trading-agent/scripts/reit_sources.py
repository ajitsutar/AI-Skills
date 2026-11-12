"""Bind REIT operand records before promoting cross-measure comparisons.

Pinned bytes and supported record schemas establish only the stated association.
They do not authenticate an issuer, a trusted ingress origin, an AFFO definition,
an analyst's signed bridge recipe or completeness of the selected components.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from source_lineage import at, load_manifest

DIMENSIONS = ('entity_id', 'currency', 'unit_scale', 'period_start', 'period_end', 'holder_basis')
SINGLE = {'cfo'}  # Only the literal scalar; FFO/capex sum distinct operands.
DEPENDENCIES = {
    'ffo': ('ffo_bridge',), 'affo': ('ffo_bridge', 'affo_bridge'),
    'cfo': ('cfo',), 'gross_capex': ('gross_capex',),
    'cfo_after_gross_capex': ('cfo', 'gross_capex'),
    'ffo_minus_cfo': ('ffo_bridge', 'cfo'),
    'affo_minus_cfo_after_gross_capex': ('ffo_bridge', 'affo_bridge', 'cfo', 'gross_capex'),
    'distribution_payout_to_ffo': ('ffo_bridge', 'distributions'),
    'distribution_payout_to_affo': ('ffo_bridge', 'affo_bridge', 'distributions'),
    'distribution_payout_to_cfo_after_gross_capex': ('cfo', 'gross_capex', 'distributions'),
    'cash_after_gross_capex_and_distributions': ('cfo', 'gross_capex', 'distributions'),
}
CONCEPT_ROLES = {
    'reviewed:cfo': 'cfo', 'reviewed:parent_income': 'ffo_component',
    'reviewed:real_estate_depreciation_amortization': 'ffo_component',
    'reviewed:property_sale_gain': 'ffo_component', 'reviewed:noncontrolling_ffo_adjustment': 'ffo_component',
    'reviewed:preferred_dividends': 'ffo_component',
    'reviewed:straight_line_rent_adjustment': 'affo_adjustment',
    'reviewed:recurring_capex': 'recurring_capex',
    'reviewed:reit_property_purchases': 'gross_capex_component',
    'reviewed:reit_development_improvements': 'gross_capex_component',
    'reviewed:other_productive_capex': 'gross_capex_component',
    'reviewed:distributions_to_common': 'distributions',
}
PROPERTY_FIELDS = {
    'property_occupancy': ('occupancy', None, None),
    'largest_tenant_revenue_fraction': ('largest_tenant_concentration', 'revenue', None),
    'net_lease_expirations_next_year_fraction': ('lease_expirations', None, 'next_year'),
}
PROPERTY_METADATA = ('denominator', 'denominator_scope', 'time_anchor')


def property_text(value):
    require(value is None or isinstance(value, str), 'REIT_PROPERTY_METADATA_TEXT_REQUIRED')
    return value.strip() if value and value.strip() and value.strip().lower() != 'unknown' else None


def property_observation(source, pointer, field, value):
    """Closed field semantics only; never inherit adjacent entity/date metadata."""
    role, broad_denominator, relative_time = PROPERTY_FIELDS[field]
    record = value if isinstance(value, dict) else {'value': value}
    number = numeric(record['value']) if record.get('value') is not None else None
    require(number is None or 0 <= number <= 1, 'REIT_PROPERTY_FRACTION_RANGE')
    metadata = {key: property_text(record.get(key)) for key in PROPERTY_METADATA}
    conflicts = []
    if broad_denominator and metadata['denominator'] and metadata['denominator'].lower() != broad_denominator:
        conflicts.append('denominator')
    # The key establishes only broad revenue, not rent/GAAP/gross/net/entity/period.
    denominator = broad_denominator or metadata['denominator']
    return {'source_id': source['id'], 'source_sha256': source['sha256'],
        'source_pointer': pointer, 'source_field': field, 'schema': 'property_disclosure_v1',
        'measure_role': role, 'fraction': str(number) if number is not None else None,
        'denominator': None if conflicts else denominator,
        'denominator_scope': metadata['denominator_scope'], 'time_anchor': metadata['time_anchor'],
        'field_name_denominator': broad_denominator, 'explicit_metadata': metadata,
        'relative_time_label': relative_time, 'entity_association': None,
        'source_metadata_conflicts': conflicts,
        'association_status': 'CONFLICTING_ORIGINAL_METADATA' if conflicts else 'SUPPORTED_ORIGINAL_FIELD',
        'unresolved_fields': [key for key in PROPERTY_METADATA if (None if key == 'denominator' and conflicts else
            denominator if key == 'denominator' else metadata[key]) is None],
        'limitation': 'Original field observation only; no entity association, precise revenue definition, calendar period, source authenticity or completeness inferred.'}


def property_source_facts(sources):
    """Inspect every JSON original for exact supported keys, not prose keywords.

    Observations remain separate even when values, IDs or source bytes coincide.
    Invalid fields are retained as diagnostics rather than silently omitted.
    """
    facts = []
    def visit(source, value, pointer):
        if isinstance(value, dict):
            for key, child in value.items():
                path = pointer + '/' + key.replace('~', '~0').replace('/', '~1')
                if key in PROPERTY_FIELDS:
                    try:
                        facts.append(property_observation(source, path, key, child))
                    except (ValueError, TypeError, KeyError) as exc:
                        facts.append({'source_id': source['id'], 'source_sha256': source['sha256'],
                            'source_pointer': path, 'source_field': key, 'source_value': deepcopy(child),
                            'association_status': 'INVALID_SUPPORTED_FIELD', 'diagnostic': str(exc)})
                else:
                    visit(source, child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(source, child, pointer + '/' + str(index))
    for source in sources.values():
        if source['format'] == 'json':
            visit(source, source['document'], '')
    return facts


def bind_properties(result, document, bindings, sources):
    for index, row in enumerate(result['property_fractions']):
        pointer = '/property_fractions/' + str(index) + '/value'
        declared_row = document['property_fractions'][index]
        row['declared_metadata'] = {key: deepcopy(declared_row.get(key)) for key in PROPERTY_METADATA}
        row['declared_fraction'] = row['fraction']
        row.update(binding_status='UNBOUND', denominator=None, denominator_scope=None, time_anchor=None,
                   source_bound_fraction=None, declaration_conflicts=[], source_metadata_conflicts=[],
                   unresolved_fields=['original_binding', *PROPERTY_METADATA])
        if pointer not in bindings:
            continue
        binding = bindings[pointer]
        require(set(binding) == {'target_pointer', 'schema', 'source_id', 'record_pointer', 'field', 'sign'},
                'REIT_PROPERTY_BINDING_FIELDS')
        require(binding['schema'] == 'property_disclosure_v1', 'REIT_UNSUPPORTED_PROPERTY_SCHEMA')
        require(type(binding['sign']) is int and binding['sign'] == 1, 'REIT_PROPERTY_UNSIGNED_BINDING')
        require(binding['source_id'] in sources, 'REIT_SOURCE_OUTSIDE_ORIGINAL_MANIFEST')
        source = sources[binding['source_id']]
        require(source['format'] == 'json', 'REIT_STRUCTURED_ORIGINAL_REQUIRED')
        record = at(source['document'], binding['record_pointer'])
        field = binding['field']
        require(isinstance(field, str) and field in PROPERTY_FIELDS, 'REIT_UNSUPPORTED_PROPERTY_FIELD')
        require(isinstance(record, dict) and field in record, 'REIT_PROPERTY_ORIGINAL_FIELD_REQUIRED')
        source_pointer = binding['record_pointer'] + '/' + field
        original = property_observation(source, source_pointer, field, record[field])
        require(original['fraction'] is not None and row['fraction'] is not None and
                numeric(original['fraction']) == numeric(row['fraction']), 'REIT_PROPERTY_ORIGINAL_VALUE_MISMATCH')
        row['original_field'] = original
        row['source_bound_fraction'] = original['fraction']
        row['binding_status'] = 'BOUND'
        row['measure_role'] = original['measure_role']
        row['relative_time_label'] = original['relative_time_label']
        row['source_metadata_conflicts'] = original['source_metadata_conflicts']
        for key in PROPERTY_METADATA:
            row[key] = original[key]
            stated = property_text(declared_row.get(key))
            if stated is not None and original[key] is not None and stated.casefold() != original[key].casefold():
                row['declaration_conflicts'].append(key)
        row['unresolved_fields'] = list(original['unresolved_fields'])
        if row['declaration_conflicts'] or row['source_metadata_conflicts']:
            row['binding_status'] = 'CONFLICT'
            row['unresolved_fields'].append('metadata_conflict')
        row['interpretation'] = original['limitation']
    return result['property_fractions']


def require(value, message):
    if not value:
        raise ValueError(message)


def numeric(value):
    require(not isinstance(value, bool) and isinstance(value, (int, float, Decimal, str)), 'REIT_SOURCE_NUMBER_REQUIRED')
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('REIT_SOURCE_NUMBER_REQUIRED') from exc
    require(result.is_finite(), 'REIT_SOURCE_FINITE_NUMBER_REQUIRED')
    return result


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str, allow_nan=False).encode()


def operands(document):
    """The actual numeric leaf set, not caller-selected metadata paths."""
    rows = []
    for group, field, role in (('ffo_bridge', 'components', 'ffo_component'),
                              ('affo_bridge', 'adjustments', 'affo_adjustment'),
                              ('gross_capex', 'components', 'gross_capex_component')):
        values = (document.get(group) or {}).get(field)
        if values is not None:
            for index, row in enumerate(values):
                rows.append({'target_pointer': '/' + group + '/' + field + '/' + str(index) + '/amount',
                             'group': group, 'role': role, 'amount': row.get('amount')})
    for group, field, role in (('affo_bridge', 'recurring_capex', 'recurring_capex'),
                              ('cfo', 'amount', 'cfo'), ('distributions', 'amount', 'distributions')):
        if document.get(group) is not None:
            rows.append({'target_pointer': '/' + group + '/' + field, 'group': group,
                         'role': role, 'amount': document[group].get(field)})
    return rows


def declared(document, metadata_provenance=None):
    from financial_alignment import _reit_declared_arithmetic
    if metadata_provenance is None:
        result = _reit_declared_arithmetic(document)
    else:
        from reit_provenance import reconcile
        result = reconcile(document, metadata_provenance, _reit_declared_arithmetic)
    result['declared_calculation_status'] = result['status']
    for key, row in result['metric_ledger'].items():
        old = deepcopy(row['basis_compatibility'])
        row['declared_arithmetic_value'] = row['value'] if row['value'] is not None else row['conditional_same_basis_value']
        row.setdefault('declared_basis_compatibility', old)
        row['basis_evidence_status'] = 'DECLARED_NOT_ORIGINAL_RECORD_BOUND'
        row['source_bound_comparability'] = False
        if key in SINGLE:
            row['value_evidence_scope'] = 'DECLARED_SINGLE_MEASURE_ARITHMETIC'
            continue
        if row['value'] is not None:
            row['conditional_same_basis_value'] = row['value']
            row['value'] = None
        if row['conditional_same_basis_value'] is not None:
            row['status'] = 'UNRESOLVED_BASIS'
            row['conditional_assumption'] = 'Declared operands share entity, currency, scale, period and holder basis; original-record association is unverified.'
        if old['status'] == 'COMPATIBLE':
            row['basis_compatibility'].update(status='UNKNOWN', unknown_dimensions=list(DIMENSIONS))
    overlap = result['capex_overlap']
    if overlap['status'] == 'DECLARED_MAPPING_RECONCILED':
        result['declared_capex_mapping_arithmetic'] = deepcopy(overlap)
        overlap.update(status='UNRESOLVED_MAPPING', allocations=None,
                       reason='Declared allocation arithmetic reconciles, but original component/scope association is unbound.')
    result['source_binding'] = {'mode': 'DECLARED_ONLY', 'source_bound_comparability': False,
        'allowed_claims': ['declared_arithmetic'], 'facts': [],
        'limitation': 'Workflow SOURCE labels and matching declarations do not prove original measure scope. Quoted source labels may still be present; unbound is not absent.'}
    refresh_status(result)
    return result


def refresh_status(result):
    result['status'] = 'PARTIAL' if (result['capex_overlap']['status'] != 'DECLARED_MAPPING_RECONCILED' or
        any(row['status'] != 'COMPUTED' for row in result['metric_ledger'].values()) or
        any(row['unresolved_fields'] or row['fraction'] is None for row in result['property_fractions'])) else 'COMPUTED'


def resolve_record(binding, sources, expected_role):
    require(set(binding) == {'target_pointer', 'schema', 'source_id', 'record_pointer', 'sign'}, 'REIT_BINDING_FIELDS')
    require(type(binding['sign']) is int and binding['sign'] in (-1, 1), 'REIT_BINDING_SIGN')
    require(binding['source_id'] in sources, 'REIT_SOURCE_OUTSIDE_ORIGINAL_MANIFEST')
    source = sources[binding['source_id']]
    require(source['format'] == 'json', 'REIT_STRUCTURED_ORIGINAL_REQUIRED')
    record = at(source['document'], binding['record_pointer'])
    require(isinstance(record, dict), 'REIT_OPERAND_RECORD_REQUIRED')
    schema = binding['schema']
    if schema == 'typed_measure_v1':
        require(record.get('measure_role') == expected_role, 'REIT_SOURCE_MEASURE_ROLE_MISMATCH')
        dimensions = {key: record.get(key) for key in DIMENSIONS}
    elif schema == 'financial_transcription_v1':
        require(CONCEPT_ROLES.get(record.get('concept')) == expected_role, 'REIT_SOURCE_MEASURE_ROLE_MISMATCH')
        # A unit is the numeric denomination; decimals describes rounding, not scale.
        unit = record.get('unit')
        recognized_currency = isinstance(unit, str) and len(unit) == 3 and unit.isalpha() and unit.isupper()
        dimensions = {'entity_id': record.get('entity_id'), 'currency': unit if recognized_currency else None,
            'unit_scale': 1 if recognized_currency else None, 'period_start': record.get('period_start'),
            'period_end': record.get('period_end'), 'holder_basis': record.get('holder_basis')}
        # Do not infer common ownership for CFO/capex from nearby FFO labels.
    else:
        raise ValueError('REIT_UNSUPPORTED_SOURCE_SCHEMA')
    value = record.get('value')
    require(value is not None, 'REIT_SOURCE_VALUE_NULL_OR_MISSING')
    amount = numeric(value) * binding['sign']
    if expected_role not in ('ffo_component', 'affo_adjustment'):
        require(binding['sign'] == 1, 'REIT_UNSIGNED_OPERAND_TRANSFORM')
    for key in DIMENSIONS:
        val = dimensions[key]
        if val is None or (isinstance(val, str) and (not val.strip() or val.strip().lower() == 'unknown')):
            dimensions[key] = None
        elif key == 'unit_scale':
            dimensions[key] = str(numeric(val).normalize())
            require(numeric(val) > 0, 'REIT_POSITIVE_SOURCE_SCALE')
        else:
            require(isinstance(val, str), 'REIT_SOURCE_DIMENSION_TEXT')
    for key in ('period_start', 'period_end'):
        if dimensions[key] is not None:
            date.fromisoformat(dimensions[key])
    if dimensions['period_start'] and dimensions['period_end']:
        require(dimensions['period_start'] <= dimensions['period_end'], 'REIT_SOURCE_PERIOD_ORDER')
    currency = dimensions['currency']
    require(currency is None or (len(currency) == 3 and currency.isascii() and currency.isalpha() and currency.isupper()),
            'REIT_SOURCE_CURRENCY_REQUIRED')
    return {'source_id': binding['source_id'], 'source_sha256': source['sha256'],
        'record_pointer': binding['record_pointer'], 'schema': schema, 'source_record': deepcopy(record),
        'signed_amount': str(amount), 'declared_recipe_sign': binding['sign'], 'dimensions': dimensions,
        'measure_role': expected_role, 'association_status': 'SUPPORTED_ORIGINAL_RECORD_SCHEMA'}


def compatibility(rows):
    unknown = [key for key in DIMENSIONS if not rows or any(row.get('dimensions', {}).get(key) is None for row in rows)]
    conflicts = [key for key in DIMENSIONS if len({row.get('dimensions', {}).get(key) for row in rows
                                                 if row.get('dimensions', {}).get(key) is not None}) > 1]
    unbound = [row['target_pointer'] for row in rows if row['binding_status'] != 'BOUND']
    return {'status': 'INCOMPATIBLE' if conflicts else 'UNKNOWN' if unknown or unbound else 'COMPATIBLE',
            'unknown_dimensions': unknown, 'conflicting_dimensions': conflicts, 'unbound_operands': unbound,
            'resolved_dimensions': {key: next(iter({row.get('dimensions', {}).get(key) for row in rows}), None)
                                    if key not in unknown and key not in conflicts else None for key in DIMENSIONS}}


def declared_unit(label, currency):
    if not label or not currency or label.lower() == 'unknown':
        return None
    aliases = {currency: Decimal(1), currency + ' units': Decimal(1)}
    for suffix, scale in (('thousand', 1000), ('million', 1000000), ('billion', 1000000000)):
        aliases[currency + ' ' + suffix] = aliases[currency + ' ' + suffix + 's'] = Decimal(scale)
    return aliases.get(label)


def rendered_report(result):
    lines = ['REIT supplied-record comparison', '',
             'Values below follow the declared signed bridge recipe. This is not accounting-standard or distribution-safety certification.', '']
    for key, row in result['metric_ledger'].items():
        if row['value'] is not None:
            label = 'source-record compatible arithmetic' if row['source_bound_comparability'] else 'declared single-measure arithmetic; basis unverified'
            lines.append(key + ': ' + str(row['value']) + ' (' + label + ').')
        elif row['conditional_same_basis_value'] is not None:
            lines.append(key + ': ' + str(row['conditional_same_basis_value']) + ' (conditional same-basis arithmetic only).')
        else:
            lines.append(key + ': unavailable (' + row['status'] + ').')
        check = row['original_record_compatibility']
        lines.append('  Original basis: ' + check['status'] + '; unknown: ' + ', '.join(check['unknown_dimensions']) +
                     '; conflicts: ' + ', '.join(check['conflicting_dimensions'] + check['declared_conflicting_dimensions']) + '.')
        if check['source_declaration_conflicts']:
            lines.append('  Source/declaration conflicts: ' + ', '.join(check['source_declaration_conflicts']) + '.')
        if check['unbound_operands']:
            lines.append('  Unbound operands: ' + ', '.join(check['unbound_operands']) + '.')
        known = [key + '=' + str(value) for key, value in check['resolved_dimensions'].items() if value is not None]
        if known:
            lines.append('  Bound dimensions: ' + '; '.join(known) + '.')
        if check['unresolved_declarations']:
            lines.append('  Unresolved declared labels: ' + ', '.join(check['unresolved_declarations']) + '.')
    lines.extend(['', 'Declared property fractions and original bindings:'])
    for row in result['property_fractions']:
        lines.append(row['id'] + ': declared fraction ' + str(row['declared_fraction']) +
                     '; binding ' + row['binding_status'] + '; bound fraction ' + str(row['source_bound_fraction']) + '.')
        lines.append('  Original denominator: ' + str(row['denominator']) + '; precise denominator scope: ' +
                     str(row['denominator_scope']) + '; time anchor: ' + str(row['time_anchor']) +
                     '; unresolved: ' + ', '.join(row['unresolved_fields']) + '.')
        if row.get('original_field'):
            original = row['original_field']
            lines.append('  Source: ' + original['source_id'] + original['source_pointer'] +
                         '; declared conflicts: ' + ', '.join(row['declaration_conflicts']) +
                         '; original metadata conflicts: ' + ', '.join(row['source_metadata_conflicts']) + '.')
    lines.extend(['', 'Original property field observations (not automatically associated with declared rows or an entity):'])
    for fact in result['source_binding']['property_source_facts']:
        prefix = fact['source_id'] + fact['source_pointer'] + ': '
        if fact['association_status'] == 'INVALID_SUPPORTED_FIELD':
            lines.append(prefix + 'invalid supported field (' + fact['diagnostic'] + ').')
            continue
        lines.append(prefix + 'fraction ' + str(fact['fraction']) + '; broad denominator ' +
                     str(fact['denominator']) + '; precise denominator scope ' + str(fact['denominator_scope']) +
                     '; time anchor ' + str(fact['time_anchor']) + '; relative label ' + str(fact['relative_time_label']) + '.')
        if fact['source_metadata_conflicts']:
            lines.append('  Original metadata conflict; field-name denominator ' + str(fact['field_name_denominator']) +
                         '; explicit denominator ' + str(fact['explicit_metadata']['denominator']) + '.')
    lines.extend(['', 'Limits:'] + ['- ' + value for value in result['source_binding']['limits']])
    text = '\n'.join(lines) + '\n'
    return {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest(), 'whole_report_semantic_pass': False}


def analyze(request, manifest_path, expected_manifest_sha256, source_root=None):
    """Replay original-record association; no trusted flags or cached certificates."""
    require(isinstance(request, dict) and set(request) == {'document', 'bindings'}, 'REIT_SOURCE_REQUEST_FIELDS')
    document = request['document']
    from financial_alignment import _reit_declared_arithmetic
    raw = _reit_declared_arithmetic(document)  # Validate full arithmetic shape first.
    result = declared(document)
    sources = load_manifest(manifest_path, expected_manifest_sha256, source_root)
    require(isinstance(request['bindings'], list), 'REIT_BINDINGS_LIST_REQUIRED')
    expected = {row['target_pointer']: row for row in operands(document)}
    property_targets = {'/property_fractions/' + str(index) + '/value'
                        for index, _ in enumerate(result['property_fractions'])}
    bindings = {}
    for binding in request['bindings']:
        require(isinstance(binding, dict), 'REIT_BINDING_OBJECT_REQUIRED')
        pointer = binding.get('target_pointer')
        require(isinstance(pointer, str) and pointer in (set(expected) | property_targets) and pointer not in bindings,
                'REIT_UNKNOWN_OR_DUPLICATE_OPERAND')
        bindings[pointer] = binding
    rows = []
    group_records = set()
    for pointer, operand in expected.items():
        row = deepcopy(operand)
        row.update(binding_status='UNBOUND', dimensions={key: None for key in DIMENSIONS}, declaration_conflicts=[],
                   unresolved_declarations=[])
        if pointer in bindings:
            resolved = resolve_record(bindings[pointer], sources, row['role'])
            identity = (row['group'], resolved['source_sha256'], resolved['record_pointer'])
            require(identity not in group_records, 'REIT_DUPLICATE_ORIGINAL_WITHIN_GROUP')
            group_records.add(identity)
            require(row['amount'] is not None and numeric(row['amount']) == numeric(resolved['signed_amount']),
                    'REIT_ORIGINAL_OPERAND_VALUE_MISMATCH')
            row.update(resolved, binding_status='BOUND')
            declared_basis = (document.get(row['group']) or {}).get('basis') or {}
            for dimension in ('period_start', 'period_end', 'holder_basis'):
                stated, actual = declared_basis.get(dimension), row['dimensions'][dimension]
                if stated and stated.lower() != 'unknown' and actual is not None and stated != actual:
                    row['declaration_conflicts'].append(pointer + ':' + dimension)
            if row['dimensions']['currency'] and document['currency'] != row['dimensions']['currency']:
                row['declaration_conflicts'].append(pointer + ':currency')
            label = declared_basis.get('amount_unit')
            if label and label.lower() != 'unknown' and row['dimensions']['currency']:
                scale = declared_unit(label, row['dimensions']['currency'])
                if scale is None:
                    row['unresolved_declarations'].append(pointer + ':amount_unit')
                elif row['dimensions']['unit_scale'] is not None and scale != numeric(row['dimensions']['unit_scale']):
                    row['declaration_conflicts'].append(pointer + ':unit_scale')
        rows.append(row)
    facts, allowed = [], ['declared_arithmetic']
    for key, metric in result['metric_ledger'].items():
        dependencies = DEPENDENCIES[key]
        selected = [row for row in rows if row['group'] in dependencies]
        check = compatibility(selected)
        # An empty aggregate is an explicit declared zero/list, not source completeness.
        empty_groups = [group for group in dependencies if not any(row['group'] == group for row in selected)]
        if empty_groups and check['status'] != 'INCOMPATIBLE':
            check['status'] = 'UNKNOWN'
        check['unbound_empty_groups'] = empty_groups
        original = raw['metric_ledger'][key]
        check['missing_arithmetic_inputs'] = deepcopy(original.get('missing_components', []))
        if check['missing_arithmetic_inputs'] and check['status'] != 'INCOMPATIBLE':
            check['status'] = 'UNKNOWN'
        # Preserve both declared and original-record conflicts; do not erase a false declaration.
        declared_conflicts = original['basis_compatibility']['conflicting_dimensions']
        check['declared_conflicting_dimensions'] = declared_conflicts
        check['source_declaration_conflicts'] = [value for row in selected for value in row['declaration_conflicts']]
        check['unresolved_declarations'] = [value for row in selected for value in row['unresolved_declarations']]
        if declared_conflicts or check['source_declaration_conflicts']:
            check['status'] = 'INCOMPATIBLE'
        elif check['unresolved_declarations']:
            check['status'] = 'UNKNOWN'
        metric['original_record_compatibility'] = check
        metric['source_bound_comparability'] = check['status'] == 'COMPATIBLE'
        metric['basis_evidence_status'] = 'SOURCE_RECORD_BOUND' if check['status'] == 'COMPATIBLE' else 'UNRESOLVED_SOURCE_BASIS'
        if key not in SINGLE:
            arithmetic = original['value'] if original['value'] is not None else original['conditional_same_basis_value']
            metric['value'] = arithmetic if check['status'] == 'COMPATIBLE' else None
            metric['conditional_same_basis_value'] = arithmetic if check['status'] == 'UNKNOWN' else None
            if arithmetic is not None:
                metric['status'] = 'COMPUTED' if check['status'] == 'COMPATIBLE' else 'UNRESOLVED_BASIS'
            if metric['value'] is not None:
                metric.pop('conditional_assumption', None)
                allowed.append('source_bound_comparison:' + key)
            elif metric['conditional_same_basis_value'] is not None:
                metric['conditional_assumption'] = 'Assume common entity/currency/scale/period/holder basis for the unresolved original operands; the source records do not establish these dimensions.'
            metric['basis_compatibility'] = deepcopy(check)
        facts.append({'metric_id': key, 'value': metric['value'], 'conditional_same_basis_value': metric['conditional_same_basis_value'],
                      'source_bound_comparability': metric['source_bound_comparability'], 'compatibility': check})
    property_facts = property_source_facts(sources)
    bind_properties(result, document, bindings, sources)
    facts.extend({'property_id': row['id'], 'source_bound_fraction': row['source_bound_fraction'],
                  'binding_status': row['binding_status'], 'denominator': row['denominator'],
                  'denominator_scope': row['denominator_scope'], 'time_anchor': row['time_anchor'],
                  'unresolved_fields': row['unresolved_fields']} for row in result['property_fractions'])
    result['source_binding'] = {'mode': 'PINNED_ORIGINAL_OPERAND_RECORDS', 'request': deepcopy(request),
        'manifest_sha256': expected_manifest_sha256,
        'replay_context': {'expected_manifest_sha256': expected_manifest_sha256,
                           'sources': [{key: source[key] for key in ('id', 'path', 'sha256', 'format')}
                                       for source in sources.values()]},
        'operands': rows, 'allowed_claims': allowed, 'facts': facts, 'property_source_facts': property_facts,
        'property_scan': {'mode': 'EXACT_SUPPORTED_JSON_FIELD_NAMES',
                          'json_sources_scanned': [source['id'] for source in sources.values() if source['format'] == 'json'],
                          'unsupported_format_sources': [source['id'] for source in sources.values() if source['format'] != 'json'],
                          'complete_semantic_property_coverage': False},
        'request_sha256': hashlib.sha256(encode(request)).hexdigest(),
        'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_authenticity_verified': False, 'external_anchor_origin_verified': False,
        'limits': ['Expected manifest pin must come from outside this analysis; replacing both manifest and pin replaces the trust root.',
                   'Only fixed JSON record schemas bind operand roles and metadata. No arbitrary prose interpretation, upstream derivation authentication or source completeness.',
                   'Signed bridge recipe, selected components and issuer AFFO definition remain analyst declarations; bound dimensions do not certify an accounting standard.',
                   'No capex overlap, growth/maintenance allocation or distribution safety is established.',
                   'Unknown mapping does not prove a source label is absent. Retain explicit source labels separately.']}
    result['source_binding']['limits'].append('Property observations scan exact supported JSON keys only, without interpreting text or associating rows by value/ID. Revenue is a broad denominator; precise revenue kind, entity and time remain unknown unless bound explicitly. A next_year label does not supply a calendar-year anchor.')
    refresh_status(result)
    result['report'] = rendered_report(result)
    return result
