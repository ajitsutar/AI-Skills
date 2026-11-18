"""Explicit research metadata, temporal ranges and independent evidence states.

Pure JSON-compatible diagnostics. Inputs are caller declarations, not verified
facts; no text is interpreted as instructions and no external resources are read.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re


OPERAND_DIMENSIONS = (
    'security_id', 'issuer_id', 'currency', 'fiscal_period', 'share_basis',
    'accounting_basis', 'strategy_scope',
)
EVIDENCE_FACTS = (
    'fee_quote_present', 'borrow_available', 'review_completed',
    'selection_recorded', 'raw_residual_measured', 'causal_attribution_supported',
    'proposal_recorded', 'adjudication_recorded', 'standalone_financials_present',
)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _known_metadata(value):
    _require(value is None or isinstance(value, str), 'DIMENSION_TEXT_OR_NULL_REQUIRED')
    return _text(value) and value.strip().lower() != 'unknown'


def operand_compatibility(operands, required_dimensions):
    """Compare exact, explicitly selected metadata dimensions across operands.

    operands: list of at least two objects with unique nonblank ``id`` and flat
    dimension keys from OPERAND_DIMENSIONS. Missing/null/blank/"unknown" values
    remain unknown. ``not_applicable`` is an explicit caller assertion, not an
    inferred default. required_dimensions is a nonempty unique list of keys.
    """
    _require(isinstance(operands, list) and len(operands) >= 2 and
             all(isinstance(row, dict) for row in operands), 'AT_LEAST_TWO_OPERANDS_REQUIRED')
    _require(all(_text(row.get('id')) for row in operands) and
             len({row['id'] for row in operands}) == len(operands), 'UNIQUE_OPERAND_IDS_REQUIRED')
    _require(isinstance(required_dimensions, list) and required_dimensions and
             all(isinstance(key, str) and key in OPERAND_DIMENSIONS for key in required_dimensions) and
             len(set(required_dimensions)) == len(required_dimensions), 'EXPLICIT_UNIQUE_DIMENSIONS_REQUIRED')
    # Validate supplied supported metadata even when it is outside this check.
    for operand in operands:
        for dimension in OPERAND_DIMENSIONS:
            _known_metadata(operand.get(dimension))
    rows, conflicts, unknown = [], [], []
    for dimension in required_dimensions:
        values = [{'operand_id': row['id'], 'value': row.get(dimension),
                   'known': _known_metadata(row.get(dimension))} for row in operands]
        missing = [row['operand_id'] for row in values if not row['known']]
        distinct = {row['value'] for row in values if row['known']}
        conflict = len(distinct) > 1
        status = 'CONFLICT' if conflict else 'UNKNOWN' if missing else 'MATCH'
        if conflict:
            conflicts.append(dimension)
        if missing:
            unknown.append(dimension)
        rows.append({'dimension': dimension, 'status': status, 'operands': values,
                     'unknown_operand_ids': missing})
    return {
        'status': 'INCOMPATIBLE' if conflicts else 'UNKNOWN_COMPATIBILITY' if unknown else 'COMPATIBLE',
        'compatible': False if conflicts else None if unknown else True,
        'required_dimensions': list(required_dimensions), 'dimension_checks': rows,
        'mismatched_dimensions': conflicts, 'unknown_dimensions': unknown,
        'supplied_but_unchecked_dimensions': [key for key in OPERAND_DIMENSIONS
            if key not in required_dimensions and any(key in row for row in operands)],
        'limitations': 'Exact declared metadata only. No identity resolution, currency conversion, '
                      'split adjustment, period alignment, arithmetic or source verification is performed. '
                      'The caller must select every dimension needed by the calculation.',
    }


def _offset(value):
    _require(isinstance(value, str) and bool(re.fullmatch(r'[+-]\d{2}:\d{2}', value)),
             'EXPLICIT_FIXED_UTC_OFFSET_REQUIRED')
    hours, minutes = int(value[1:3]), int(value[4:6])
    _require(hours <= 23 and minutes <= 59, 'INVALID_UTC_OFFSET')
    # RFC 3339 -00:00 denotes an unknown local offset, not a known UTC offset.
    _require(value != '-00:00', 'UNKNOWN_UTC_OFFSET')
    return timezone(timedelta(minutes=(hours * 60 + minutes) * (1 if value[0] == '+' else -1)))


def _temporal(value):
    original, declared_offset = value, None
    if isinstance(value, dict):
        _require(set(value) <= {'value', 'utc_offset'} and 'value' in value,
                 'TEMPORAL_OBJECT_KEYS_MUST_BE_VALUE_AND_UTC_OFFSET')
        declared_offset = value.get('utc_offset')
        value = value['value']
    if value is None or (isinstance(value, str) and not value.strip()):
        return {'status': 'UNRESOLVED', 'input': original, 'reason': 'TEMPORAL_VALUE_MISSING'}
    _require(isinstance(value, str), 'TEMPORAL_TEXT_REQUIRED')
    try:
        match = re.fullmatch(r'(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?', value)
        if match:
            year, month, day = match.groups()
            lower = date(int(year), int(month or 1), int(day or 1))
            if day:
                precision, upper = 'day', lower + timedelta(days=1)
            elif month:
                precision = 'month'
                upper = date(lower.year + (lower.month == 12), lower.month % 12 + 1, 1)
            else:
                precision, upper = 'year', date(lower.year + 1, 1, 1)
            domain = 'civil_calendar'
            if declared_offset is not None:
                offset = _offset(declared_offset)
                lower = datetime.combine(lower, datetime.min.time(), offset).astimezone(timezone.utc)
                upper = datetime.combine(upper, datetime.min.time(), offset).astimezone(timezone.utc)
                domain = 'utc_instant'
            return {'status': 'PARSED', 'input': original, 'precision': precision,
                    'domain': domain, 'lower': lower, 'upper': upper, 'upper_inclusive': False}
        _require(declared_offset is None, 'TIMESTAMP_MUST_CARRY_ITS_OWN_OFFSET')
        _require(bool(re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})', value)),
            'ISO_DATE_OR_OFFSET_TIMESTAMP_REQUIRED')
        if not value.endswith('Z'):
            _offset(value[-6:])
        instant = datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)
        return {'status': 'PARSED', 'input': original, 'precision': 'instant',
                'domain': 'utc_instant', 'lower': instant, 'upper': instant, 'upper_inclusive': True}
    except (ValueError, OverflowError) as exc:
        return {'status': 'UNRESOLVED', 'input': original, 'reason': str(exc)}


def _public_range(value):
    return {key: item.isoformat() if isinstance(item, (date, datetime)) else item
            for key, item in value.items()}


def event_window(event, start, end):
    """Relate a possible event range to an inclusive declared calendar window.

    Values are ISO YYYY, YYYY-MM, YYYY-MM-DD or an offset timestamp. An optional
    {value, utc_offset} object gives a calendar value an explicit fixed offset.
    Calendar end periods are included in full; timestamp endpoints are included.
    Calendar bounds express uncertainty, never an invented event day or time.
    """
    parsed = {name: _temporal(value) for name, value in
              (('event', event), ('start', start), ('end', end))}
    result = {'status': 'UNRESOLVED', 'ranges': {key: _public_range(value) for key, value in parsed.items()},
              'window': None, 'reasons': [],
              'limitations': 'Relations describe the supplied temporal ranges only. OVERLAP does not '
                             'establish that the event occurs inside the window. Calendar bounds are '
                             'not observed timestamps. Fixed offsets do not infer named-zone or daylight-saving rules.'}
    result['reasons'] = [key + ':' + value['reason'] for key, value in parsed.items()
                         if value['status'] != 'PARSED']
    if result['reasons']:
        return result
    if len({value['domain'] for value in parsed.values()}) != 1:
        result['reasons'] = ['MIXED_CALENDAR_AND_INSTANT_DOMAINS_REQUIRE_EXPLICIT_OFFSETS']
        return result
    observed, first, last = parsed['event'], parsed['start'], parsed['end']
    lower, upper, inclusive = first['lower'], last['upper'], last['upper_inclusive']
    if lower > upper or (lower == upper and not inclusive):
        result['reasons'] = ['EMPTY_OR_REVERSED_WINDOW']
        return result
    result['window'] = {'lower': lower.isoformat(), 'upper': upper.isoformat(),
                        'upper_inclusive': inclusive, 'domain': first['domain']}
    if observed['upper'] < lower or (observed['upper'] == lower and not observed['upper_inclusive']):
        result['status'] = 'DEFINITELY_BEFORE'
    elif observed['lower'] > upper or (observed['lower'] == upper and not inclusive):
        result['status'] = 'DEFINITELY_AFTER'
    elif observed['lower'] >= lower and (observed['upper'] < upper or
            (observed['upper'] == upper and (inclusive or not observed['upper_inclusive']))):
        result['status'] = 'CONTAINED'
    else:
        result['status'] = 'OVERLAP'
    return result


def evidence_states(observations):
    """Assess independently referenced boolean facts per caller-defined subject.

    Each observation has unique id, subject_id, fact in EVIDENCE_FACTS, boolean
    or null value, and optional evidence_refs (list of nonblank literal strings).
    A reference is retained but neither opened nor verified. There are no
    cross-fact mappings: observed fees, reviews and residuals imply no other fact.
    """
    _require(isinstance(observations, list) and all(isinstance(row, dict) for row in observations),
             'OBSERVATION_LIST_REQUIRED')
    _require(all(_text(row.get('id')) for row in observations) and
             len({row['id'] for row in observations}) == len(observations), 'UNIQUE_OBSERVATION_IDS_REQUIRED')
    grouped = {}
    for row in observations:
        _require(_text(row.get('subject_id')), 'EXPLICIT_SUBJECT_ID_REQUIRED')
        _require(isinstance(row.get('fact'), str) and row['fact'] in EVIDENCE_FACTS, 'SUPPORTED_FACT_REQUIRED')
        _require('value' in row and (row['value'] is None or type(row['value']) is bool),
                 'EXPLICIT_BOOLEAN_OR_NULL_REQUIRED')
        refs = row.get('evidence_refs', [])
        _require(isinstance(refs, list) and all(_text(ref) for ref in refs), 'EVIDENCE_REFERENCE_LIST_REQUIRED')
        grouped.setdefault(row['subject_id'], {}).setdefault(row['fact'], []).append(row)
    subjects = []
    for subject_id, facts in grouped.items():
        states = {}
        for fact in EVIDENCE_FACTS:
            rows = facts.get(fact, [])
            declared = {row['value'] for row in rows if row['value'] is not None}
            referenced = {row['value'] for row in rows if row['value'] is not None and row.get('evidence_refs')}
            # Retain contradictory explicit declarations even if one lacks refs.
            status = ('CONFLICT' if len(declared) > 1 else 'REFERENCED_TRUE' if True in referenced
                      else 'REFERENCED_FALSE' if False in referenced else 'UNKNOWN')
            states[fact] = {
                'status': status, 'value': True if status == 'REFERENCED_TRUE' else
                                         False if status == 'REFERENCED_FALSE' else None,
                'observation_ids': [row['id'] for row in rows],
                'unknown_observation_ids': [row['id'] for row in rows if row['value'] is None],
                'unreferenced_observation_ids': [row['id'] for row in rows if not row.get('evidence_refs')],
                'evidence_refs': list(dict.fromkeys(ref for row in rows for ref in row.get('evidence_refs', []))),
            }
        subjects.append({'subject_id': subject_id, 'states': states})
    return {'status': 'ASSESSED', 'subjects': subjects, 'cross_fact_inference_applied': False,
            'source_authenticity_verified': False,
            'limitations': 'Boolean declarations and literal references only; references are not read or '
                          'verified and do not prove the fact. In particular, a referenced causal-attribution '
                          'declaration is not validation of identification, assumptions or causality. '
                          'Subject IDs must distinguish the intended entity, period and scope.'}
