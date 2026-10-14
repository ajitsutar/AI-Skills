"""Map explicitly reviewed supplied observations into the installed normalizer.

This is an offline mapping route, not a source authenticator or a second TTM
implementation. Source bytes, caller declarations and unresolved mappings remain
in the returned replay artifact. No aliases, precision or review are inferred.
"""
from __future__ import annotations

import base64
import copy
import hashlib

from deterministic_rank import digest, number
from filing_extract import numeric
from financial_normalize import normalize, policy, quantum, require, nonempty


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
    records = []
    for observation in supplied.get('observations', []):
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
    return {
        'flow_mapping_schema_version': 1,
        'mapping_input': supplied, 'mapping_input_sha256': digest(supplied),
        'normalization_input': normalization_input, 'normalization': result,
        'mapping_issues': issues,
        'status': 'MAPPING_REQUIRED' if issues else result['status'],
        'execution_authorized': False,
        'limitations': 'Caller source and mapping reviews are retained declarations, not independently authenticated. Missing mappings are mapping work, not proof of missing financial data. Normalization input uses schema 1; the downstream scoring snapshot uses schema 2. Latest public period remains unresolved without an explicit supported review.',
    }
