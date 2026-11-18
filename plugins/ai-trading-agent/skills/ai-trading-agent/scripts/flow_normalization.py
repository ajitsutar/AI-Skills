"""Map explicitly reviewed supplied observations into the installed normalizer.

This is an offline mapping route, not a source authenticator or a second TTM
implementation. Source bytes, caller declarations and unresolved mappings remain
in the returned replay artifact. No aliases, precision or review are inferred.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json

from deterministic_rank import digest, number
from filing_extract import numeric
from financial_normalize import normalize, policy, quantum, require, nonempty
from report_facts import pointer


def normalize_flows(document):
    """Return mapped normalization-schema-1 input plus its deterministic result.

    See references/flow-normalization.md for the observation mapping contract.
    Snapshot schema 2 is a separate downstream scoring envelope.
    """
    require(document.get('flow_mapping_schema_version') == 1, 'FLOW_MAPPING_SCHEMA')
    supplied = copy.deepcopy(document)
    selected_policy = policy()
    policy_hash = digest(selected_policy)
    allowed = set(selected_policy['tags']) | set(selected_policy['reviewed_concepts'])
    mappings = supplied.get('metric_mappings', {})
    require(isinstance(mappings, dict), 'METRIC_MAPPINGS_OBJECT_REQUIRED')
    issues, sources, source_ids = [], [], set()
    for declaration in supplied.get('sources', []):
        source = copy.deepcopy(declaration)
        sid = source.get('source_id')
        require(nonempty(sid) and sid not in source_ids, 'DUPLICATE_OR_MISSING_SOURCE_ID')
        source_ids.add(sid)
        try:
            require(('source_text' in source) != ('source_bytes_base64' in source), 'EXACT_SOURCE_BYTES_REQUIRED')
            if 'source_text' in source:
                require(isinstance(source['source_text'], str), 'SOURCE_TEXT_REQUIRED')
                raw = source['source_text'].encode('utf-8')
            else:
                raw = base64.b64decode(source['source_bytes_base64'], validate=True)
            actual_hash = hashlib.sha256(raw).hexdigest()
            require(source.get('content_sha256', actual_hash) == actual_hash, 'SOURCE_BYTES_HASH_MISMATCH')
            source['content_sha256'] = actual_hash
        except (ValueError, TypeError, UnicodeError) as exc:
            issues.append({'source_id': sid, 'reason': str(exc)})
            continue
        # Preserve supplied declarations exactly; absence never becomes verified.
        source.setdefault('verification', {'status': 'unverified'})
        sources.append(source)
    usable_sources = {s['source_id'] for s in sources}
    issuers = copy.deepcopy(supplied.get('issuers', []))
    issuer_entities = {i['issuer_id']: i['entity_id'] for i in issuers}
    observations = copy.deepcopy(supplied.get('observations', []))
    bindings = []
    # Select values from retained JSON bytes rather than reconstructing a new
    # observation and guessing precision from an integer's representation.
    for binding in supplied.get('observation_bindings', []):
        require(isinstance(binding, dict) and set(binding) == {'source_id', 'record', 'fields'},
                'EXPLICIT_OBSERVATION_BINDING_REQUIRED')
        require(isinstance(binding['record'], dict) and isinstance(binding['fields'], dict),
                'BINDING_RECORD_AND_FIELDS_REQUIRED')
        require('source_id' not in binding['fields'], 'BINDING_SOURCE_ID_MUST_BE_DECLARATION')
        require('decimals' not in binding['record'], 'PRECISION_MUST_BIND_SOURCE_FIELD_OR_SEPARATE_SENSITIVITY')
        require(not set(binding['record']).intersection(binding['fields']), 'BINDING_FIELD_OVERRIDE_FORBIDDEN')
        row = copy.deepcopy(binding['record'])
        require('source_id' not in row or row['source_id'] == binding['source_id'], 'BINDING_SOURCE_CONFLICT')
        row['source_id'] = binding['source_id']
        receipt = {'record_id': row.get('record_id'), 'source_id': binding['source_id'], 'fields': []}
        try:
            source = next(s for s in sources if s['source_id'] == binding['source_id'])
            raw = (source['source_text'].encode('utf-8') if 'source_text' in source else
                   base64.b64decode(source['source_bytes_base64'], validate=True))
            original = json.loads(raw.decode('utf-8'))
            receipt['source_content_sha256'] = source['content_sha256']
            for field, path in binding['fields'].items():
                require(nonempty(field), 'BINDING_FIELD_NAME_REQUIRED')
                try:
                    row[field] = copy.deepcopy(pointer(original, path))
                    receipt['fields'].append({'field': field, 'source_pointer': path, 'status': 'BOUND'})
                except (KeyError, IndexError):
                    # In particular, missing decimals cannot be reconstructed
                    # from value=11 or display_text="11".
                    receipt['fields'].append({'field': field, 'source_pointer': path, 'status': 'ABSENT'})
            observations.append(row)
        except (StopIteration, ValueError, TypeError, UnicodeError) as exc:
            issues.append({'record_id': row.get('record_id'), 'reason': 'SOURCE_BINDING_FAILED', 'detail': str(exc)})
        bindings.append(receipt)
    records = []
    for observation in observations:
        row = copy.deepcopy(observation)
        try:
            require(row.get('source_id') in usable_sources, 'SOURCE_BYTES_UNAVAILABLE')
            require(row.get('issuer_id') in issuer_entities and
                    row.get('entity_id') == issuer_entities[row['issuer_id']], 'EXPLICIT_ISSUER_ENTITY_MAPPING_REQUIRED')
            metric = row.get('metric')
            require(nonempty(metric) and metric in mappings, 'METRIC_MAPPING_REQUIRED')
            mapping = mappings[metric]
            require(isinstance(mapping, dict) and mapping.get('concept') in allowed, 'UNKNOWN_MAPPED_CONCEPT')
            review = copy.deepcopy(mapping.get('review', {}))
            require(review.get('status') == 'reviewed' and nonempty(review.get('basis_evidence')), 'MAPPING_REVIEW_REQUIRED')
            require(review.get('policy_sha256', policy_hash) == policy_hash, 'MAPPING_POLICY_MISMATCH')
            # This binds an explicit caller review to the current policy, not an
            # invented canonical review or an authentication claim.
            review.setdefault('policy_sha256', policy_hash)
            require(nonempty(row.get('source_pointer')) and nonempty(row.get('quote')), 'SOURCE_POINTER_AND_QUOTE_REQUIRED')
            require(row.get('unit') == 'USD', 'EXPLICIT_USD_UNIT_REQUIRED')
            require('decimals' in row, 'REPORTING_PRECISION_REQUIRED')
            quantum(row['decimals'])
            require(('value' in row) != ('display_text' in row), 'EXACTLY_ONE_REPORTED_VALUE_REQUIRED')
            if 'value' in row:
                require(not any(k in row for k in ('scale', 'sign', 'format')), 'DISPLAY_TRANSFORMS_REQUIRE_DISPLAY_TEXT')
                number(row['value'])
            else:
                numeric({k: str(row[k]) for k in ('format', 'scale', 'sign', 'decimals') if k in row}, row['display_text'])
            concept = mapping['concept']
            if concept in selected_policy['required_bases']:
                require(nonempty(mapping.get('basis')), 'EXPLICIT_ACCOUNTING_BASIS_REQUIRED')
            row['concept'] = 'reviewed:' + concept
            row['review'] = review
            row['locator'] = row['source_pointer']
            if 'basis' in mapping:
                require('basis' not in row or row['basis'] == mapping['basis'],
                        'OBSERVATION_MAPPING_BASIS_CONFLICT')
                row['basis'] = mapping['basis']
            elif 'basis' in row:
                # Basis is part of the reviewed metric mapping, not a silent
                # observation override.
                raise ValueError('ACCOUNTING_BASIS_MUST_BE_IN_MAPPING')
            records.append(row)
        except (ValueError, KeyError, TypeError) as exc:
            issues.append({'record_id': row.get('record_id'), 'metric': row.get('metric'), 'reason': str(exc)})
    normalization_input = {
        'schema_version': 1, 'policy_sha256': policy_hash,
        'information_cutoff': supplied['information_cutoff'],
        'sources': sources, 'issuers': issuers, 'documents': [], 'transcriptions': records,
    }
    # All duration selection, duplicate reconciliation, amendment conflicts,
    # cutoff filtering, accounting bases and evidence readiness are delegated.
    result = normalize(normalization_input)
    sensitivities = []
    labels = set()
    for sensitivity in supplied.get('precision_sensitivities', []):
        require(isinstance(sensitivity, dict) and set(sensitivity) == {'label', 'decimals', 'record_ids'},
                'NAMED_PRECISION_SENSITIVITY_REQUIRED')
        require(nonempty(sensitivity['label']) and sensitivity['label'] not in labels,
                'UNIQUE_PRECISION_SENSITIVITY_LABEL_REQUIRED')
        labels.add(sensitivity['label'])
        quantum(sensitivity['decimals'])
        selected = sensitivity['record_ids']
        require(isinstance(selected, list) and selected and all(nonempty(rid) for rid in selected) and
                len(set(selected)) == len(selected), 'EXPLICIT_PRECISION_SENSITIVITY_RECORD_IDS_REQUIRED')
        by_id = {row.get('record_id'): row for row in observations}
        require(all(rid in by_id and 'decimals' not in by_id[rid] for rid in selected),
                'SENSITIVITY_ONLY_FOR_ABSENT_SOURCE_PRECISION')
        scenario = copy.deepcopy(supplied)
        scenario.pop('observation_bindings', None)
        scenario.pop('precision_sensitivities', None)
        scenario['observations'] = copy.deepcopy(observations)
        for row in scenario['observations']:
            if row.get('record_id') in selected:
                row['decimals'] = sensitivity['decimals']
        computed = normalize_flows(scenario)
        sensitivities.append({'label': sensitivity['label'], 'assumption': copy.deepcopy(sensitivity),
            'evidence_status': 'EXPLICIT_PRECISION_ASSUMPTION_NOT_SOURCE_REPORTED',
            'status': computed['status'], 'normalization_input': computed['normalization_input'],
            'normalization': computed['normalization'], 'mapping_issues': computed['mapping_issues']})
    return {
        'flow_mapping_schema_version': 1,
        'mapping_input': supplied, 'mapping_input_sha256': digest(supplied),
        'normalization_input': normalization_input, 'normalization': result,
        'mapping_issues': issues,
        'source_bindings': bindings, 'precision_sensitivities': sensitivities,
        'status': 'MAPPING_REQUIRED' if issues else result['status'],
        'execution_authorized': False,
        'limitations': 'Caller source and mapping reviews are retained declarations, not independently authenticated. Missing mappings are mapping work, not proof of missing financial data. Normalization input uses schema 1; the downstream scoring snapshot uses schema 2. Latest public period remains unresolved without an explicit supported review.',
    }
