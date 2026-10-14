"""Offline forward-observation admissibility; declarations never prove live observation."""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import math
from pathlib import Path

from quant_common import digest, require
from price_audit import timestamp
from report_facts import pointer, strict_json

ROOT = Path(__file__).resolve().parents[1]


def implementation_hash():
    return digest({name: (ROOT / 'scripts' / name).read_text(encoding='utf-8') for name in
                   ('forward_evidence.py', 'quant_common.py', 'price_audit.py', 'report_facts.py')})


def clock(value):
    """Coarse dates can show contradictions; only exact timestamps can qualify."""
    try:
        return timestamp(value), True
    except (ValueError, TypeError, AttributeError):
        try:
            require(isinstance(value, str) and len(value) == 10, 'DATE_REQUIRED')
            return date.fromisoformat(value), False
        except (ValueError, TypeError):
            return None, False


def before(left, right):
    if left is None or right is None:
        return False
    if hasattr(left, 'hour') and hasattr(right, 'hour'):
        return left < right
    a = left.date() if hasattr(left, 'hour') else left
    b = right.date() if hasattr(right, 'hour') else right
    return a < b


def bound_text(evidence):
    if not isinstance(evidence, dict) or not isinstance(evidence.get('source_text'), str):
        return None, 'EVIDENCE_BYTES_MISSING'
    raw = evidence['source_text'].encode('utf-8')
    if not raw or hashlib.sha256(raw).hexdigest() != evidence.get('sha256'):
        return None, 'EVIDENCE_HASH_MISMATCH'
    return raw, None


def implementation_evidence(descriptor):
    if not isinstance(descriptor, dict):
        return {'status': 'NOT_ESTABLISHED', 'reasons': ['IMPLEMENTATION_DESCRIPTOR_MISSING']}
    raw, error = bound_text(descriptor.get('source_evidence'))
    reasons = [error] if error else []
    if not isinstance(descriptor.get('implementation_sha256'), str):
        reasons.append('IMPLEMENTATION_IDENTITY_MISSING')
    elif raw is not None and hashlib.sha256(raw).hexdigest() != descriptor['implementation_sha256']:
        reasons.append('IMPLEMENTATION_SOURCE_HASH_MISMATCH')
    for field in ('strategy_id', 'execution_rule'):
        if not isinstance(descriptor.get(field), str) or not descriptor[field]:
            reasons.append(field.upper() + '_MISSING')
    if not clock(descriptor.get('known_at'))[1]:
        reasons.append('IMPLEMENTATION_KNOWN_AT_EXACT_TIMESTAMP_MISSING')
    return {'status': 'SOURCE_BYTES_BOUND' if not reasons else 'NOT_ESTABLISHED',
            'reasons': reasons, 'implementation_sha256': descriptor.get('implementation_sha256'),
            'strategy_id': descriptor.get('strategy_id'), 'execution_rule': descriptor.get('execution_rule'),
            'known_at': descriptor.get('known_at'),
            'limitation': 'Hash-bound supplied code text is not evidence it executed or generated the claimed fills.'}


def assess(document):
    require(isinstance(document, dict), 'FORWARD_DOCUMENT_REQUIRED')
    protocol = document.get('protocol', {})
    require(isinstance(protocol, dict), 'PROTOCOL_OBJECT_REQUIRED')
    observations = document.get('observations', [])
    require(isinstance(observations, list) and all(isinstance(r, dict) for r in observations), 'OBSERVATION_OBJECTS_REQUIRED')
    cut, cut_exact = clock(document.get('as_of'))
    start, start_exact = clock(protocol.get('start'))
    end, end_exact = clock(protocol.get('end'))
    frozen, frozen_exact = clock(protocol.get('frozen_at'))
    protocol_reasons = []
    for field, exact in (('AS_OF', cut_exact), ('PROTOCOL_START', start_exact),
                         ('PROTOCOL_END', end_exact), ('PROTOCOL_FROZEN_AT', frozen_exact)):
        if not exact:
            protocol_reasons.append(field + '_EXACT_TIMESTAMP_MISSING')
    if before(end, start):
        protocol_reasons.append('PROTOCOL_WINDOW_REVERSED')
    if before(start, frozen):
        protocol_reasons.append('PROTOCOL_FROZEN_AFTER_START')
    if before(cut, frozen):
        protocol_reasons.append('PROTOCOL_FROZEN_AFTER_AS_OF')
    minimum = protocol.get('minimum_observations')
    if type(minimum) is not int or minimum < 1:
        minimum = None
        protocol_reasons.append('MINIMUM_OBSERVATIONS_MISSING_OR_INVALID')
    declared = document.get('implementations', {})
    require(isinstance(declared, dict), 'IMPLEMENTATIONS_OBJECT_REQUIRED')
    implementations = {role: implementation_evidence(declared.get(role)) for role in ('champion', 'challenger')}
    both_bound = all(r['status'] == 'SOURCE_BYTES_BOUND' for r in implementations.values())
    same_code = (implementations['champion'].get('implementation_sha256') ==
                 implementations['challenger'].get('implementation_sha256')) if both_bound else None
    configuration_differences = []
    a, b = declared.get('champion', {}), declared.get('challenger', {})
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in ('source_evidence', 'implementation_sha256') and a.get(key) != b.get(key):
                configuration_differences.append({'field': key, 'champion': a.get(key), 'challenger': b.get(key)})
    rows, admitted = [], []
    id_counts = {}
    for row in observations:
        if isinstance(row.get('id'), str):
            id_counts[row['id']] = id_counts.get(row['id'], 0) + 1
    for index, row in enumerate(observations):
        reasons = list(protocol_reasons)
        row_id = row.get('id')
        if not isinstance(row_id, str) or not row_id:
            reasons.append('OBSERVATION_ID_MISSING')
        elif id_counts[row_id] > 1:
            reasons.append('DUPLICATE_OBSERVATION_ID')
        decision, de = clock(row.get('decision_at'))
        outcome, oe = clock(row.get('outcome_at'))
        available, ae = clock(row.get('available_at'))
        for field, exact in (('DECISION_AT', de), ('OUTCOME_AT', oe), ('AVAILABLE_AT', ae)):
            if not exact:
                reasons.append(field + '_EXACT_TIMESTAMP_MISSING')
        # Check outcome as well as decision: date-only old observations still
        # reveal a pre-window contradiction without inventing intraday timing.
        if before(decision, start) or before(outcome, start):
            reasons.append('BEFORE_PROTOCOL_WINDOW')
        if before(end, decision) or before(end, outcome):
            reasons.append('AFTER_PROTOCOL_WINDOW')
        if before(decision, frozen):
            reasons.append('DECISION_BEFORE_PREREGISTRATION')
        if before(outcome, decision):
            reasons.append('OUTCOME_BEFORE_DECISION')
        elif de and oe and outcome == decision:
            reasons.append('OUTCOME_NOT_AFTER_DECISION')
        if before(available, outcome):
            reasons.append('AVAILABLE_BEFORE_OUTCOME')
        if before(cut, available) or before(cut, outcome) or before(cut, decision):
            reasons.append('NOT_AVAILABLE_AS_OF')
        if row.get('data_kind') != 'forward_paper_observation':
            reasons.append('NOT_DECLARED_FORWARD_PAPER_OBSERVATION')
        if document.get('data_kind') not in (None, 'forward_paper_observation') or document.get('fictional') is True:
            reasons.append('PARENT_DATA_NOT_FORWARD_OBSERVATION')
        for field in ('champion_net_return', 'challenger_net_return'):
            value = row.get(field)
            if type(value) not in (int, float) or not math.isfinite(value):
                reasons.append(field.upper() + '_MISSING_OR_INVALID')
        identities = row.get('implementation_sha256', {})
        if not isinstance(identities, dict):
            identities = {}
        for role, info in implementations.items():
            if info['status'] != 'SOURCE_BYTES_BOUND':
                reasons.append(role.upper() + '_IMPLEMENTATION_NOT_ESTABLISHED')
            elif identities.get(role) != info['implementation_sha256']:
                reasons.append(role.upper() + '_IMPLEMENTATION_MISMATCH')
            known, _ = clock(info.get('known_at'))
            if before(decision, known) or before(frozen, known):
                reasons.append(role.upper() + '_IMPLEMENTATION_KNOWN_AFTER_FREEZE_OR_DECISION')
        raw, evidence_error = bound_text(row.get('evidence'))
        if evidence_error:
            reasons.append(evidence_error)
        else:
            try:
                retained = pointer(strict_json(raw), row['evidence'].get('pointer', ''))
                payload = {k: v for k, v in row.items() if k != 'evidence'}
                if digest(retained) != digest(payload):
                    reasons.append('OBSERVATION_EVIDENCE_MISMATCH')
            except (ValueError, KeyError, TypeError, IndexError):
                reasons.append('OBSERVATION_EVIDENCE_INVALID')
        reasons = sorted(set(reasons))
        item = {'index': index, 'id': row_id, 'status': 'ADMISSIBLE_DECLARATION' if not reasons else 'NOT_ADMISSIBLE',
                'reasons': reasons, 'source_pointer': '/observations/' + str(index)}
        rows.append(item)
        if not reasons:
            admitted.append(index)
    count = len(admitted)
    return {'status': 'ASSESSED', 'method': 'forward-observation-admissibility-1',
            'implementation_sha256': implementation_hash(), 'input_sha256': digest(document),
            'protocol': copy.deepcopy(protocol), 'protocol_reasons': protocol_reasons,
            'rows': rows, 'supplied_observations': len(observations),
            'admissible_declared_forward_count': count, 'admissible_indices': admitted,
            'minimum_observations': minimum,
            'additional_admissible_observations_needed': max(0, minimum - count) if minimum is not None else None,
            'minimum_count_met': count >= minimum if minimum is not None else None,
            'implementations': implementations,
            'implementation_comparison': 'SAME_SUPPLIED_CODE_BYTES' if same_code is True else
                                         'DIFFERENT_SUPPLIED_CODE_BYTES' if same_code is False else 'NOT_ESTABLISHED',
            'configuration_differences': configuration_differences,
            'declared_change_list': copy.deepcopy(document.get('changes')),
            'change_list_completeness': 'NOT_ESTABLISHED_BY_HASH_OR_ENTRY_STRINGS',
            'fill_agreement': 'NOT_ESTABLISHED', 'forecast_calibration': 'NOT_EVALUATED',
            'performance_comparison': 'NOT_COMPUTED_BY_ADMISSIBILITY_CHECK',
            'genuine_forward_proven': False,
            'limits': ['Admissibility checks supplied timing, kind, hashes and exact retained payload consistency only.',
                       'Date-only evidence may establish contradictions but cannot establish exact decision/availability times.',
                       'Synthetic or retrospective rows never count; matching prose entry strings do not establish implementation agreement.',
                       'Supplied source text and timestamps may be fabricated; no independent observation, execution or source authentication.',
                       'Counts are research evidence summaries and impose no trading execution condition.'],
            'execution_authorized': False}


def paper_study(document, as_of):
    """Lossless adapter for a declared strategy/paper-study fixture; no time filling."""
    require(isinstance(document, dict), 'PAPER_STUDY_REQUIRED')
    base = document.get('base_strategy', {})
    criteria = document.get('prespecified_criteria', {})
    require(isinstance(base, dict) and isinstance(criteria, dict), 'STUDY_CONTRACT_REQUIRED')
    supplied = document.get('paper_observations', [])
    require(isinstance(supplied, list) and all(isinstance(r, dict) for r in supplied), 'OBSERVATION_OBJECTS_REQUIRED')
    rows = []
    for index, row in enumerate(supplied):
        rows.append({**copy.deepcopy(row), 'id': row.get('id', 'supplied-row-' + str(index)),
                     'decision_at': row.get('decision_at'), 'outcome_at': row.get('outcome_at', row.get('date')),
                     'available_at': row.get('available_at', row.get('available_after')),
                     'data_kind': row.get('data_kind', document.get('data_kind'))})
    canonical = {'as_of': as_of, 'data_kind': document.get('data_kind'), 'fictional': document.get('fictional'),
                 'protocol': {'start': base.get('paper_start'), 'end': base.get('paper_end'),
                 'frozen_at': document.get('frozen_at'), 'minimum_observations': criteria.get('minimum_paper_observations')},
                 'observations': rows, 'implementations': {role: copy.deepcopy(document.get(role, {}))
                                                          for role in ('champion', 'challenger')},
                 'changes': copy.deepcopy(document.get('changes'))}
    result = assess(canonical)
    result.update(study_input_sha256=digest(document), canonical_input=canonical,
                  source_mapping={'protocol/start': '/base_strategy/paper_start', 'protocol/end': '/base_strategy/paper_end',
                                  'protocol/frozen_at': '/frozen_at', 'protocol/minimum_observations': '/prespecified_criteria/minimum_paper_observations',
                                  'observations': '/paper_observations'},
                  declared_base_entry=base.get('entry'),
                  entry_rule_strings={role: document[role].get('entry') if isinstance(document.get(role), dict) else None
                                      for role in ('champion', 'challenger')})
    return result
