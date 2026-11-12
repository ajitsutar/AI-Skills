"""REIT metadata roles, separate from arithmetic and source-scope authentication.

Workflows derive these records from their retained bindings. A direct caller's
records remain declarations; neither this module nor a SOURCE label authenticates
the selected source's meaning or an upstream derivation graph.
"""
from copy import deepcopy
import re

from quant_common import require
from planning_alignment import finish


BASIS_FIELDS = ('amount_unit', 'period_start', 'period_end', 'holder_basis')
GROUPS = ('ffo_bridge', 'affo_bridge', 'cfo', 'gross_capex', 'distributions', 'recurring_capex_mapping')
PROPERTY_FIELDS = ('denominator', 'time_anchor')


def metadata_paths(document):
    require(isinstance(document, dict), 'REIT_DOCUMENT_OBJECT_REQUIRED')
    paths = ['/document/' + group + '/basis/' + field for group in GROUPS for field in BASIS_FIELDS]
    rows = document.get('property_fractions')
    if isinstance(rows, list):
        paths.extend('/document/property_fractions/' + str(i) + '/' + field
                     for i in range(len(rows)) for field in PROPERTY_FIELDS)
    return paths


def derive(arguments, bindings):
    """Use the nearest enclosing actual workflow binding, never inferred scope."""
    require(isinstance(arguments, dict) and isinstance(bindings, list), 'REIT_BINDINGS_REQUIRED')
    require(all(isinstance(b, dict) and isinstance(b.get('target_pointer'), str) for b in bindings),
            'REIT_BINDING_TARGET_REQUIRED')
    require(len({b['target_pointer'] for b in bindings}) == len(bindings), 'REIT_DUPLICATE_BINDING_TARGET')
    result = {}
    for pointer in metadata_paths(arguments.get('document')):
        enclosing = [b for b in bindings if pointer == b['target_pointer'] or pointer.startswith(b['target_pointer'] + '/')]
        result[pointer] = deepcopy(max(enclosing, key=lambda b: len(b['target_pointer']))) if enclosing else {'kind': 'UNBOUND'}
    validate(arguments['document'], result)
    return result


def validate(document, provenance):
    require(isinstance(provenance, dict) and set(provenance) == set(metadata_paths(document)),
            'COMPLETE_REIT_METADATA_PROVENANCE_REQUIRED')
    for pointer, record in provenance.items():
        require(isinstance(record, dict) and record.get('kind') in {'SOURCE', 'ASSUMPTION', 'UNBOUND'},
                'REIT_METADATA_PROVENANCE_KIND_REQUIRED')
        kind = record['kind']
        if kind == 'UNBOUND':
            require(set(record) == {'kind'}, 'REIT_UNBOUND_RECORD_FIELDS')
            continue
        target = record.get('target_pointer')
        require(isinstance(target, str) and (pointer == target or pointer.startswith(target + '/')),
                'REIT_METADATA_BINDING_TARGET_MISMATCH')
        if kind == 'ASSUMPTION':
            require(set(record) == {'target_pointer', 'kind', 'reason', 'value'}
                    and isinstance(record['reason'], str) and record['reason'].strip(), 'REIT_ASSUMPTION_RECORD_REQUIRED')
        else:
            require(set(record) == {'target_pointer', 'kind', 'source_id', 'source_pointer', 'source_role',
                                    'source_sha256', 'selected_value_sha256'}, 'REIT_SOURCE_RECORD_FIELDS')
            require(all(isinstance(record[k], str) and record[k].strip() for k in ('source_id', 'source_role')),
                    'REIT_SOURCE_ID_AND_ROLE_REQUIRED')
            require(isinstance(record['source_pointer'], str) and (not record['source_pointer'] or record['source_pointer'].startswith('/')),
                    'REIT_SOURCE_POINTER_REQUIRED')
            require(all(isinstance(record[k], str) and re.fullmatch('[0-9a-f]{64}', record[k]) for k in ('source_sha256', 'selected_value_sha256')),
                    'REIT_SOURCE_HASH_REQUIRED')


def reconcile(document, provenance, calculate):
    """Keep direct arithmetic intact; apply roles only to metadata compatibility."""
    validate(document, provenance)
    declared = calculate(document)
    primary_document = deepcopy(document)
    fields = []
    for group in GROUPS:
        original = document.get(group)
        if not isinstance(original, dict) or not isinstance(original.get('basis'), dict):
            continue  # Preserve the legacy missing/malformed-input behavior.
        for field in BASIS_FIELDS:
            pointer = '/document/' + group + '/basis/' + field
            record = provenance[pointer]
            value = original['basis'].get(field)
            if record['kind'] != 'SOURCE':
                primary_document[group]['basis'][field] = None
            fields.append({'argument_pointer': pointer, 'declared_value': deepcopy(value),
                           'primary_value': deepcopy(primary_document[group]['basis'].get(field)),
                           'binding': deepcopy(record)})
    for i, row in enumerate(document.get('property_fractions') or []):
        for field in PROPERTY_FIELDS:
            pointer = '/document/property_fractions/' + str(i) + '/' + field
            record = provenance[pointer]
            if record['kind'] != 'SOURCE':
                primary_document['property_fractions'][i][field] = None
            fields.append({'argument_pointer': pointer, 'declared_value': deepcopy(row.get(field)),
                           'primary_value': deepcopy(primary_document['property_fractions'][i].get(field)),
                           'binding': deepcopy(record)})
    result = calculate(primary_document)
    for key, metric in result['metric_ledger'].items():
        original = declared['metric_ledger'][key]
        metric['declared_basis_compatibility'] = deepcopy(original['basis_compatibility'])
        # Removing unsupported labels must never silently repair conflicting declarations.
        if original['basis_compatibility']['status'] == 'INCOMPATIBLE':
            metric['conditional_same_basis_value'] = None
            metric.pop('conditional_assumption', None)
            metric['conditional_value_withheld_reason'] = 'Declared basis conflicts remain unresolved; no alternative matching basis is inferred.'
    if document.get('recurring_capex_mapping') is not None:
        result['capex_overlap']['declared_mapping'] = deepcopy(document['recurring_capex_mapping'])
        result['capex_overlap']['declared_basis_compatibility'] = deepcopy(declared['capex_overlap'].get('basis_compatibility'))
    for i, row in enumerate(result['property_fractions']):
        row['source_record'] = deepcopy(document['property_fractions'][i])
        row['declared_metadata'] = {key: deepcopy(declared['property_fractions'][i][key]) for key in PROPERTY_FIELDS}
        row['metadata_bindings'] = {key: deepcopy(provenance['/document/property_fractions/' + str(i) + '/' + key]) for key in PROPERTY_FIELDS}
    result['metadata_evidence'] = {
        'mode': 'EXPLICIT_BINDING_RECORDS', 'fields': fields,
        'declared_document': deepcopy(document),
        'provenance': deepcopy(provenance),
        'primary_rule': 'Only SOURCE-bound metadata enters primary basis/property fields; ASSUMPTION and UNBOUND remain unresolved.',
        'limitation': 'Workflow dispatch derives records from actual retained bindings and rejects caller-injected provenance. Direct API records are caller declarations. SOURCE proves selected bytes/pointer only, not source truth, relevant measurement scope or upstream derivation lineage. Raw amounts retain their declared arithmetic; this guard classifies metadata, not every numeric input.'}
    result['primary_metadata_input_sha256'] = result['input_sha256']
    header = {'method', 'currency', 'input_role', 'input_sha256', 'advisory_only', 'source_authenticity_verified'}
    return finish(document, 'reit-cross-measure-reconciliation', **{key: value for key, value in result.items() if key not in header})
