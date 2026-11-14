"""Offline, scope-bound institutional evidence and workflow-value assessment.

Replays existing assessors and checks retained local artifacts. No source, host,
model or broker calls; no enterprise certification or execution permission.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from decimal import Decimal, Context, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_EVEN, Subnormal, Underflow, localcontext
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat

import platform_readiness
import release_acceptance
import source_strategy_readiness

MAX_BYTES = 16 * 1024 * 1024
KINDS = {'platform', 'data', 'rights', 'review_packet', 'governance', 'operations', 'value', 'implementation'}
GOVERNANCE_CHECKS = ('classification', 'approved_model_routes', 'access_separation',
    'retention_and_deletion', 'permitted_data_use', 'confidential_data_negative_test')
OPERATING_CHECKS = ('named_support_owner', 'source_and_model_change_monitoring',
    'incident_response_drill', 'restart_recovery', 'rollback_drill', 'deployment_change_review')
IMPLEMENTATION_CHECKS = ('cost_and_borrow_basis', 'liquidity_and_capacity', 'observed_vs_assumed_execution')
BENEFITS = {'automated_quality', 'human_productivity', 'alpha'}
SENSITIVE_KEYS = {'user_agent', 'authorization', 'password', 'access_token', 'refresh_token',
                  'api_key', 'cookie', 'cookies', 'secret', 'private_key'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def exact(value, fields, name):
    require(type(value) is dict and set(value) == set(fields), 'EXACT_FIELDS:' + name)


def text(value, name):
    require(type(value) is str and bool(value.strip()), 'NONEMPTY_TEXT:' + name)
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def sha(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None, 'SHA256_REQUIRED')
    return value


def clock(value):
    return platform_readiness.clock(value)


def _clean(value, depth=0):
    require(depth <= 64, 'JSON_NESTING_LIMIT')
    if isinstance(value, dict):
        require(not SENSITIVE_KEYS.intersection(str(k).lower() for k in value), 'CONTACT_OR_CREDENTIAL_CONFIGURATION_NOT_ALLOWED')
        for item in value.values():
            _clean(item, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _clean(item, depth + 1)
    elif isinstance(value, float):
        require(math.isfinite(value), 'NONFINITE_NUMBER')
    else:
        require(value is None or type(value) in (str, int, bool), 'JSON_VALUE_REQUIRED')


def _pairs(rows):
    result = {}
    for key, value in rows:
        require(key not in result, 'DUPLICATE_JSON_KEY:' + key)
        result[key] = value
    return result


def _json(raw):
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=_pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError('NONFINITE_JSON:' + x)))
    except RecursionError as error:
        raise ValueError('JSON_NESTING_LIMIT') from error
    _clean(value)
    return value


def _path(root, name, directory=False):
    text(name, 'artifact.path')
    require('\\' not in name and ':' not in name, 'RELATIVE_FORWARD_SLASH_PATH_REQUIRED')
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and all(p not in ('', '.', '..') for p in name.split('/')), 'ARTIFACT_PATH_ESCAPE')
    original = Path(root).absolute()
    require(not any(p.lower() == 'private-runtime' or p.lower() == 'sec-contact.json'
        or (p.lower().startswith('private-') and 'config' in p.lower())
        for p in (*original.parts, *relative.parts)), 'PRIVATE_CONTACT_CONFIGURATION_EXCLUDED')
    require(all(not _reparse(p) for p in (original, *original.parents)),
        'REPARSE_EVIDENCE_ROOT_REJECTED')
    base = original.resolve(strict=True)
    require(base.is_dir(), 'REGULAR_EVIDENCE_ROOT_REQUIRED')
    candidate = base
    for part in relative.parts:
        candidate /= part
        require(not _reparse(candidate), 'REPARSE_ARTIFACT_REJECTED')
    require(candidate.resolve(strict=True).is_relative_to(base), 'ARTIFACT_OUTSIDE_ROOT')
    require(candidate.is_dir() if directory else stat.S_ISREG(candidate.stat().st_mode), 'REGULAR_ARTIFACT_REQUIRED')
    return candidate


def _reparse(path):
    # lstat exposes the reparse bit on Windows/3.11 too; isjunction requires 3.12.
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def artifact(root, ref, decode=True):
    exact(ref, ('path', 'sha256'), 'artifact')
    sha(ref['sha256'])
    path = _path(root, ref['path'])
    require(path.stat().st_size <= MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
    raw = path.read_bytes()
    require(len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == ref['sha256'], 'ARTIFACT_HASH_MISMATCH')
    value = _json(raw) if decode else None
    if decode:
        _clean(value)
    return value


def _scope(scope):
    exact(scope, ('id', 'description', 'host_id', 'mode', 'asset_classes', 'package_sha256',
        'runtime_sha256', 'intended_use', 'claimed_benefits', 'data_contract_sha256',
        'universe_mode', 'data_policy', 'source_rights_map', 'review_protocol_sha256', 'value_protocol_sha256'), 'scope')
    for key in ('id', 'description', 'host_id'):
        text(scope[key], key)
    require(scope['mode'] in platform_readiness.MODES, 'DEPLOYMENT_MODE')
    assets = scope['asset_classes']
    require(type(assets) is list and assets and len(set(assets)) == len(assets)
        and set(assets) <= set(platform_readiness.ASSETS), 'EXPLICIT_UNIQUE_ASSETS')
    for key in ('package_sha256', 'runtime_sha256', 'data_contract_sha256', 'review_protocol_sha256', 'value_protocol_sha256'):
        sha(scope[key])
    rights_map = scope['source_rights_map']
    require(type(rights_map) is dict and rights_map and all(type(k) is str and k.strip()
        and type(v) is str and v.strip() for k, v in rights_map.items()), 'EXPLICIT_SOURCE_RIGHTS_MAP')
    require(scope['intended_use'] in ('personal_research', 'commercial_internal', 'redistribution'), 'INTENDED_USE')
    benefits = scope['claimed_benefits']
    require(type(benefits) is list and len(benefits) == 1
        and set(benefits) <= BENEFITS, 'EXPLICIT_UNIQUE_BENEFITS')
    require(scope['universe_mode'] in ('historical_membership', 'current_roster'), 'UNIVERSE_MODE')
    require(scope['data_policy'] in ('strict_observed', 'declared_scenario'), 'EXPLICIT_DATA_POLICY')


def _bindings(value, scope, as_of):
    require(value['scope_sha256'] == digest(scope), 'DIFFERENT_SCOPE')
    require(value['package_sha256'] == scope['package_sha256']
        and value['runtime_sha256'] == scope['runtime_sha256'], 'DIFFERENT_PACKAGE_OR_RUNTIME')
    require(clock(value['observed_at']) <= as_of < clock(value['valid_until']), 'FUTURE_OR_EXPIRED_EVIDENCE')


def _controls(value, scope, as_of, root, required):
    exact(value, ('schema_version', 'scope_sha256', 'package_sha256', 'runtime_sha256',
        'observed_at', 'valid_until', 'owner', 'checks'), 'control_evidence')
    require(type(value['schema_version']) is int and value['schema_version'] == 1, 'SCHEMA_VERSION')
    _bindings(value, scope, as_of)
    text(value['owner'], 'owner')
    require(type(value['checks']) is list and len(value['checks']) <= 100, 'BOUNDED_CHECKS')
    seen, missing, failed = set(), [], []
    for row in value['checks']:
        exact(row, ('id', 'outcome', 'reviewer', 'evidence'), 'control_check')
        require(row['id'] in required and row['id'] not in seen, 'UNKNOWN_OR_DUPLICATE_CHECK')
        seen.add(row['id'])
        text(row['reviewer'], 'reviewer')
        require(row['outcome'] in ('pass', 'fail', 'not_run'), 'CONTROL_OUTCOME')
        require(type(row['evidence']) is list and 0 < len(row['evidence']) <= 100, 'RETAINED_CHECK_EVIDENCE_REQUIRED')
        for ref in row['evidence']:
            artifact(root, ref, decode=False)
        if row['outcome'] != 'pass':
            failed.append(row['id'])
    missing = sorted(set(required) - seen)
    return {'complete': not missing and not failed, 'missing_checks': missing,
        'failed_or_unrun_checks': sorted(failed), 'owner': value['owner'],
        'outcomes_are_reviewer_declarations': True}


def _nonnegative(value, name, integer=False, nullable=False):
    if value is None and nullable:
        return None
    require((type(value) is int if integer else type(value) in (str, int, float))
        and not isinstance(value, bool), 'NUMERIC_VALUE:' + name)
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError('INVALID_DECIMAL:' + name) from error
    require(result.is_finite() and result >= 0, 'FINITE_NONNEGATIVE:' + name)
    require(len(result.as_tuple().digits) <= 40 and -30 <= result.as_tuple().exponent <= 30
        and result.adjusted() <= 30, 'SUPPORTED_METRIC_PRECISION_OR_RANGE:' + name)
    return result


def value_scope_identity(scope):
    """Stable deployment identity before the value protocol's own pin is known."""
    return {k: copy.deepcopy(v) for k, v in scope.items() if k != 'value_protocol_sha256'}


def _packets(reference, scope, as_of, root):
    exact(reference, ('packets',), 'review_packet_reference')
    require(type(reference['packets']) is list and 0 < len(reference['packets']) <= 1000, 'BOUNDED_REVIEW_PACKETS')
    import review_packet
    verified, case_ids, roster = [], set(), None
    for item in reference['packets']:
        exact(item, ('packet_directory', 'packet_sha256'), 'review_packet_item')
        directory = _path(root, item['packet_directory'], directory=True)
        native = review_packet.verify(directory, sha(item['packet_sha256']))
        require(clock(native['review_at']) <= as_of, 'FUTURE_REVIEW_PACKET')
        require(native['adopted_protocol_sha256'] == scope['review_protocol_sha256']
            and any(r.get('role') == 'adopted_protocol' and r.get('sha256') == scope['review_protocol_sha256']
                for r in native.get('bound_evidence', [])), 'REVIEW_PROTOCOL_BINDING_MISMATCH')
        protocol_refs = [r for r in native['bound_evidence'] if r['role'] == 'adopted_protocol']
        require(len(protocol_refs) == 1, 'UNIQUE_REVIEW_PROTOCOL_REQUIRED')
        ingress = artifact(directory, {'path': 'ingress.json', 'sha256': native['manifest_sha256']})
        sources = [r for r in ingress['sources'] if r['id'] == protocol_refs[0]['source_id']]
        require(len(sources) == 1 and sources[0]['sha256'] == scope['review_protocol_sha256'], 'PROTOCOL_INGRESS_BINDING_MISMATCH')
        protocol = artifact(directory / 'sealed', {'path': sources[0]['path'], 'sha256': sources[0]['sha256']})
        expected_context = {'scope_id': scope['id'], 'host_id': scope['host_id'],
            'package_sha256': scope['package_sha256'], 'runtime_sha256': scope['runtime_sha256'],
            'data_contract_sha256': scope['data_contract_sha256']}
        require(all(protocol.get(k) == v for k, v in expected_context.items()), 'REVIEW_DEPLOYMENT_CONTEXT_MISMATCH')
        registered = native['registered_case_ids']
        require(type(registered) is list and registered and len(set(registered)) == len(registered), 'REVIEW_REGISTERED_ROSTER_REQUIRED')
        if roster is None:
            roster = set(registered)
        require(set(registered) == roster, 'REVIEW_ROSTER_CONFLICT')
        require(native['case_id'] not in case_ids and native['case_id'] in roster, 'DUPLICATE_OR_UNREGISTERED_REVIEW_CASE')
        case_ids.add(native['case_id'])
        verified.append(native)
    missing = sorted(roster - case_ids)
    return {'complete': not missing and all(p['dispatch_ready'] is True and p['integrity_status'] == 'VERIFIED' for p in verified),
        'registered_case_ids': sorted(roster), 'missing_review_case_ids': missing, 'packets': verified}


def value_comparison(document, scope, as_of, root, packet_reference):
    """Matched, declared review metrics. Never authenticates human activity or alpha."""
    context = Context(prec=100, rounding=ROUND_HALF_EVEN, Emin=-999, Emax=999,
        flags=[], traps=[InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal])
    with localcontext(context):
        return _value_comparison(document, scope, as_of, root, packet_reference)


def _value_comparison(document, scope, as_of, root, packet_reference):
    exact(document, ('schema_version', 'protocol', 'observations'), 'value_comparison')
    require(type(document['schema_version']) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    protocol = document['protocol']
    exact(protocol, ('id', 'scope_sha256', 'review_protocol_sha256', 'registered_at', 'measurement_kind',
        'expected_case_ids', 'evaluation_units', 'criterion'), 'value_protocol')
    require(digest(protocol) == scope['value_protocol_sha256'], 'VALUE_PROTOCOL_PIN_MISMATCH')
    text(protocol['id'], 'protocol.id')
    require(protocol['scope_sha256'] == digest(value_scope_identity(scope)), 'VALUE_SCOPE_MISMATCH')
    require(protocol['review_protocol_sha256'] == scope['review_protocol_sha256'], 'VALUE_REVIEW_PROTOCOL_MISMATCH')
    packet_result = _packets(packet_reference, scope, as_of, root)
    packets = {p['packet_sha256']: p for p in packet_result['packets']}
    registered = clock(protocol['registered_at'])
    require(registered <= as_of, 'FUTURE_PROTOCOL')
    require(protocol['measurement_kind'] in ('automated_proxy', 'human_reported'), 'MEASUREMENT_KIND')
    ids = protocol['expected_case_ids']
    require(type(ids) is list and 0 < len(ids) <= 1000 and all(type(x) is str and x for x in ids)
        and len(set(ids)) == len(ids), 'FROZEN_UNIQUE_ROSTER')
    require(set(ids) == set(packet_result['registered_case_ids']), 'VALUE_REVIEW_ROSTER_MISMATCH')
    units = protocol['evaluation_units']
    require(type(units) is dict and set(units) == set(ids), 'FROZEN_EVALUATION_UNITS')
    for targets in units.values():
        require(type(targets) is list and 0 < len(targets) <= 10000 and all(type(u) is str and u for u in targets)
            and len(set(targets)) == len(targets), 'UNIQUE_EVALUATION_UNITS')
    criterion = protocol['criterion']
    exact(criterion, ('metric', 'direction', 'minimum_improvement'), 'value_criterion')
    directions = {'material_errors': 'lower', 'decision_checks': 'higher', 'total_seconds': 'lower', 'cost_usd': 'lower'}
    metric = criterion['metric']
    require(metric in directions and criterion['direction'] == directions[metric], 'BENEFIT_METRIC_DIRECTION')
    threshold = _nonnegative(criterion['minimum_improvement'], 'minimum_improvement')
    claim = scope['claimed_benefits'][0]
    kind_fits = (claim == 'automated_quality' and metric in ('material_errors', 'decision_checks') or
        claim == 'human_productivity' and protocol['measurement_kind'] == 'human_reported' and metric in ('total_seconds', 'cost_usd'))
    require(type(document['observations']) is list and len(document['observations']) <= 1000, 'BOUNDED_OBSERVATIONS')
    seen, rows, unexpected = set(), [], []
    for observation in document['observations']:
        exact(observation, ('id', 'reviewer', 'review_packet_sha256', 'common_inputs', 'packet_frozen_at', 'baseline', 'assisted'), 'value_observation')
        oid = text(observation['id'], 'observation.id')
        require(oid not in seen, 'DUPLICATE_OBSERVATION')
        seen.add(oid)
        text(observation['reviewer'], 'reviewer')
        # Preserve the unexpected ID without including its outcomes in any mean.
        if oid not in ids:
            unexpected.append(oid)
            continue
        pin = sha(observation['review_packet_sha256'])
        require(pin in packets and packets[pin]['case_id'] == oid, 'VALUE_CASE_PACKET_BINDING_MISMATCH')
        packet = packets[pin]
        common = artifact(root, observation['common_inputs'])
        require(digest(common) == packet['common_input_sha256'], 'VALUE_COMMON_INPUT_MANIFEST_MISMATCH')
        frozen = clock(observation['packet_frozen_at'])
        require(registered <= clock(packet['review_at']) <= frozen <= as_of, 'VALUE_PACKET_OUTSIDE_PROTOCOL')
        arms, coverage = {}, {}
        for name in ('baseline', 'assisted'):
            arm = observation[name]
            exact(arm, ('captured_at', 'common_input_sha256', 'output', 'reviewed_unit_ids', 'material_errors',
                'decision_checks', 'work_seconds', 'review_seconds', 'correction_seconds', 'cost_usd'), 'value_arm')
            require(frozen < clock(arm['captured_at']) <= as_of, 'VALUE_CAPTURE_OUTSIDE_PROTOCOL')
            require(arm['common_input_sha256'] == packet['common_input_sha256'], 'VALUE_ARM_INPUT_MISMATCH')
            artifact(root, arm['output'], decode=False)
            reviewed = arm['reviewed_unit_ids']
            require(type(reviewed) is list and all(type(u) is str for u in reviewed)
                and len(set(reviewed)) == len(reviewed) and set(reviewed) <= set(units[oid]), 'REVIEWED_UNIT_IDS')
            coverage[name] = len(reviewed)
            arms[name] = {key: _nonnegative(arm[key], key, integer=key in ('material_errors', 'decision_checks'),
                nullable=key in ('work_seconds', 'review_seconds', 'correction_seconds', 'cost_usd'))
                for key in ('material_errors', 'decision_checks', 'work_seconds', 'review_seconds', 'correction_seconds', 'cost_usd')}
            require(arms[name]['material_errors'] <= len(reviewed) and arms[name]['decision_checks'] <= len(reviewed), 'REVIEW_COUNTS_EXCEED_DENOMINATOR')
            phases = [arms[name][key] for key in ('work_seconds', 'review_seconds', 'correction_seconds')]
            arms[name]['total_seconds'] = sum(phases, Decimal(0)) if all(x is not None for x in phases) else None
        complete_coverage = all(n == len(units[oid]) for n in coverage.values())
        before, after = arms['baseline'][metric], arms['assisted'][metric]
        improvement = None if not complete_coverage or before is None or after is None else before - after if directions[metric] == 'lower' else after - before
        rows.append({'id': oid, 'expected_review_units': len(units[oid]), 'reviewed_units': coverage,
            'comparison_status': 'MATCHED_DECLARED_COVERAGE' if complete_coverage else 'INCOMPARABLE_REVIEW_COVERAGE',
            'baseline': {k: str(v) if v is not None else None for k, v in arms['baseline'].items()},
            'assisted': {k: str(v) if v is not None else None for k, v in arms['assisted'].items()},
            'improvement': str(improvement) if improvement is not None else None})
    missing = sorted(set(ids) - seen)
    measured = [Decimal(row['improvement']) for row in rows if row['improvement'] is not None]
    mean = sum(measured, Decimal(0)) / len(measured) if measured else None
    complete = not missing and len(measured) == len(ids) and packet_result['complete'] and kind_fits
    return {'complete': complete, 'status': 'DESCRIPTIVE_MATCHED_REVIEW_EVIDENCE' if complete else 'UNASSESSED',
        'measurement_kind': protocol['measurement_kind'], 'full_roster_denominator': len(ids),
        'comparable_cases': len(measured), 'missing_ids': missing, 'unexpected_ids_excluded': unexpected,
        'cases': rows, 'mean_declared_improvement': str(mean) if mean is not None else None,
        'declared_criterion_met': mean >= threshold if complete and mean is not None else None,
        'measurement_kind_and_metric_match_claim': kind_fits, 'human_activity_authenticated': False,
        'alpha_assessed': False, 'causal_time_saving_established': False,
        'seconds_semantics': 'SUM_OF_DECLARED_HUMAN_ACTIVE_PHASES' if protocol['measurement_kind'] == 'human_reported' else 'SUM_OF_DECLARED_MACHINE_PHASE_DURATIONS',
        'metric_scope': 'One prespecified benefit claim, fixed review units and complete registered cohort; not general institutional value.',
        'reviewer_counts_are_declarations': True}


def assess(document, evidence_root):
    exact(document, ('schema_version', 'as_of', 'scope', 'components'), 'acceptance')
    require(type(document['schema_version']) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    _clean(document)
    as_of, scope = clock(document['as_of']), document['scope']
    _scope(scope)
    require(type(document['components']) is list and len(document['components']) <= len(KINDS), 'BOUNDED_COMPONENTS')
    required = {'platform', 'data', 'rights', 'review_packet', 'governance', 'operations', 'value'}
    if scope['mode'] != 'research':
        required.add('implementation')
    references = {}
    for component in document['components']:
        exact(component, ('kind', 'artifact'), 'component')
        require(component['kind'] in KINDS and component['kind'] not in references, 'UNKNOWN_OR_DUPLICATE_COMPONENT')
        references[component['kind']] = component['artifact']
    seen, results, inputs = set(), [], {}
    for component in document['components']:
        exact(component, ('kind', 'artifact'), 'component')
        kind = component['kind']
        require(kind in KINDS and kind not in seen, 'UNKNOWN_OR_DUPLICATE_COMPONENT')
        seen.add(kind)
        try:
            value = artifact(evidence_root, component['artifact'])
            inputs[kind] = value
            if kind == 'platform':
                require(clock(value['as_of']) == as_of, 'PLATFORM_CUTOFF_MISMATCH')
                require(all(value['host'][k] == scope[k] for k in ('package_sha256', 'runtime_sha256'))
                    and value['host']['id'] == scope['host_id'], 'PLATFORM_DEPLOYMENT_MISMATCH')
                require({r['asset_class'] for r in value['requests']} == set(scope['asset_classes'])
                    and all(r['mode'] == scope['mode'] and r['scope_id'] == scope['id']
                        and r['scope_description'] == scope['description'] for r in value['requests']), 'PLATFORM_SCOPE_MISMATCH')
                native = platform_readiness.assess(value)
                detail = {'complete': native['catalog_evidence_complete'],
                    'request_statuses': [r['evidence_status'] for r in native['results']],
                    'native_input_sha256': native['input_sha256']}
            elif kind == 'data':
                require(digest(value['study_request']) == scope['data_contract_sha256'], 'DATA_CONTRACT_MISMATCH')
                require(scope['universe_mode'] in value['study_request']['study_modes'], 'DATA_UNIVERSE_MISMATCH')
                require(all(clock(d[key]) <= as_of for d in value['study_request']['decisions']
                    for key in ('decision_at', 'valuation_at', 'execution_at')), 'FUTURE_DATA_STUDY_CUTOFF')
                data_sources = value['security_contract']['sources'] + value['feature_contract']['sources'] + [value['observation_archive']['source']]
                require(all(clock(s['retrieved_at']) <= as_of for s in data_sources), 'FUTURE_DATA_CAPTURE')
                require(set(scope['source_rights_map']) == {s['id'] for s in data_sources}, 'INCOMPLETE_SOURCE_RIGHTS_MAP')
                native = source_strategy_readiness.assess(value)
                chosen = [s for s in native['studies'] if s['universe_mode'] == scope['universe_mode']]
                flag = 'strict_observed_grid_complete' if scope['data_policy'] == 'strict_observed' else 'declared_policy_grid_complete'
                detail = {'complete': bool(chosen) and all(s[flag] for s in chosen),
                    'status': native['status'], 'requested_universe_mode': scope['universe_mode'],
                    'native_input_sha256': native['input_sha256'],
                    'historical_universe_completeness_certified': False}
            elif kind == 'rights':
                require(clock(value['as_of']) == as_of and value['intended_use'] == scope['intended_use'], 'RIGHTS_SCOPE_OR_CUTOFF_MISMATCH')
                native = release_acceptance.rights_inventory(value)
                detail = {'complete': native['inventory_complete'], 'sources': native['sources'],
                    'rights_granted': False, 'legal_compliance_certified': False}
            elif kind == 'review_packet':
                native = _packets(value, scope, as_of, evidence_root)
                detail = {'complete': native['complete'], 'registered_case_ids': native['registered_case_ids'],
                    'missing_review_case_ids': native['missing_review_case_ids'],
                    'packets': [{'case_id': p['case_id'], 'status': p['status'], 'review_at': p['review_at'],
                        'packet_sha256': p['packet_sha256'], 'criterion_coverage': p['criterion_coverage']}
                        for p in native['packets']]}
            elif kind in ('governance', 'operations', 'implementation'):
                checks = GOVERNANCE_CHECKS if kind == 'governance' else OPERATING_CHECKS if kind == 'operations' else IMPLEMENTATION_CHECKS
                detail = _controls(value, scope, as_of, evidence_root, checks)
            else:
                require('review_packet' in references, 'VALUE_REQUIRES_REVIEW_PACKET_COMPONENT')
                packet_reference = artifact(evidence_root, references['review_packet'])
                detail = value_comparison(value, scope, as_of, evidence_root, packet_reference)
            results.append({'kind': kind, 'status': 'RETAINED_SCOPE_EVIDENCE_COMPLETE' if detail['complete'] else 'GAPS_OR_UNASSESSED',
                'artifact': copy.deepcopy(component['artifact']), 'result': detail})
        except (ValueError, KeyError, TypeError, IndexError, OSError, UnicodeError, OverflowError, RecursionError) as error:
            results.append({'kind': kind, 'status': 'FAILED_RETAINED_COMPONENT',
                'artifact': copy.deepcopy(component['artifact']), 'error_type': type(error).__name__, 'error': str(error)})
    if 'data' in inputs and 'rights' in inputs:
        try:
            source_rows = inputs['data']['security_contract']['sources'] + inputs['data']['feature_contract']['sources'] + [inputs['data']['observation_archive']['source']]
            rights_rows = {r['id']: r for r in inputs['rights']['sources']}
            for source in source_rows:
                mapped = scope['source_rights_map'][source['id']]
                require(mapped in rights_rows and rights_rows[mapped]['source_url'] == source['uri'], 'DATA_RIGHTS_SOURCE_IDENTITY_MISMATCH')
        except (KeyError, TypeError, ValueError) as error:
            results.append({'kind': 'data_rights_binding', 'status': 'FAILED_RETAINED_COMPONENT',
                'error_type': type(error).__name__, 'error': str(error)})
    missing = sorted(required - seen)
    complete = not missing and all(r['status'] == 'RETAINED_SCOPE_EVIDENCE_COMPLETE' for r in results)
    return {'schema_version': 1, 'method': 'institutional_acceptance_v1', 'as_of': document['as_of'],
        'scope': copy.deepcopy(scope), 'scope_sha256': digest(scope), 'input_sha256': digest(document),
        'status': 'DECLARED_SCOPE_EVIDENCE_COMPLETE' if complete else 'DEPLOYMENT_EVIDENCE_GAPS',
        'catalog_evidence_complete': complete, 'required_components': sorted(required), 'missing_components': missing,
        'components': results, 'execution_authorized': False, 'external_permissions_changed': False,
        'production_readiness_certified': False, 'profitability_established': False,
        'limits': ['Scope-bound local artifact verification and replay of existing assessors only; no enterprise, legal or investment certification.',
            'Control outcomes, ownership, reviewer metrics, rights and honest availability remain supplied declarations; hashes do not authenticate them.',
            'No source, host, model, broker or identity provider is contacted; firm access/retention/DLP controls must be actually enforced by its deployment.',
            'Current-roster and historical-membership coverage stay distinct; a supplied grid cannot certify all-market completeness.',
            'Automated proxy comparisons do not prove human productivity, causal time savings or alpha. Missing observations are not zeros.',
            'Sensitive-key/path exclusions are bounded input hygiene, not discovery or redaction of every possible secret in arbitrary content.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        require(args.input.stat().st_size <= MAX_BYTES, 'INPUT_SIZE_LIMIT')
        result = assess(_json(args.input.read_bytes()), args.evidence_root)
        raw = json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        if args.output:
            require(args.output.resolve() != args.input.resolve(), 'PRESERVE_INPUT')
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(raw)
        else:
            print(raw, end='')
        return 0 if result['catalog_evidence_complete'] else 2
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, OverflowError) as error:
        parser.exit(2, 'institutional_acceptance: ' + str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
