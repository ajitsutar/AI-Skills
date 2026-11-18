"""Original pure audit of source-declared terminal-event return coverage.

No return series, event prices, effective dates, cash proceeds or provider facts
are manufactured. A series endpoint is intentionally not an inclusion input.
"""
import math


KEYS = {'event_id', 'event_source_ref', 'terminal_return', 'series_id',
        'series_coverage', 'coverage_evidence'}
EVIDENCE_KINDS = {'provider_methodology', 'event_reconciliation'}


def text(value, label):
    if (type(value) is not str or not value or value != value.strip()
            or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)):
        raise ValueError(label + ' must be nonempty trimmed text')
    return value


def assess(document):
    """Return an inclusion decision conditional on explicit event/series evidence."""
    if type(document) is not dict or set(document) != KEYS:
        raise ValueError('TERMINAL_COVERAGE_FIELDS: ' + ', '.join(sorted(KEYS)))
    event_id = text(document['event_id'], 'event_id')
    source = text(document['event_source_ref'], 'event_source_ref')
    series = document['series_id']
    if series is not None:
        text(series, 'series_id')
    value = document['terminal_return']
    if value is not None and (type(value) not in (int, float) or
                              (type(value) is float and not math.isfinite(value)) or value < -1):
        raise ValueError('terminal_return must be a finite simple-return fraction >= -1 or null')
    coverage = document['series_coverage']
    if coverage not in ('embedded', 'not_embedded', 'unknown'):
        raise ValueError('series_coverage must be embedded, not_embedded or unknown')
    rows = document['coverage_evidence']
    if type(rows) is not list:
        raise ValueError('coverage_evidence must be an array')
    evidence, seen = [], set()
    for row in rows:
        if type(row) is not dict or set(row) != {'source_ref', 'kind'}:
            raise ValueError('coverage evidence requires exactly source_ref and kind')
        ref = text(row['source_ref'], 'coverage source_ref')
        kind = text(row['kind'], 'coverage kind')
        if kind not in EVIDENCE_KINDS:
            raise ValueError('Coverage needs provider_methodology or event_reconciliation, never an endpoint date alone')
        if (ref, kind) in seen:
            raise ValueError('Duplicate coverage evidence')
        seen.add((ref, kind))
        evidence.append({'source_ref': ref, 'kind': kind})
    if coverage != 'unknown' and (series is None or not evidence):
        raise ValueError('Known coverage requires a named series and explicit event-specific evidence')

    if coverage == 'unknown':
        status, action, count = 'UNRESOLVED', 'VERIFY_EVENT_COVERAGE', None
    elif coverage == 'embedded':
        status, action, count = 'CONDITIONAL_DECISION', 'ALREADY_INCLUDED_DO_NOT_REAPPLY', 0
    elif value is None:
        status, action, count = 'UNRESOLVED', 'OBTAIN_MISSING_TERMINAL_RETURN', None
    else:
        status, action, count = 'CONDITIONAL_DECISION', 'INCLUDE_EVENT_ONCE_SEPARATELY', 1
    return {'schema_version': 1, 'status': status, 'action': action,
            'event': {'event_id': event_id, 'source_ref': source, 'terminal_return': value},
            'series_id': series, 'series_coverage': coverage, 'coverage_evidence': evidence,
            'additional_application_count': count,
            'separate_terminal_return': value if count == 1 else None,
            'return_unit': 'simple_return_fraction', 'combined_return': None,
            'source_authenticity_verified': False, 'execution_authorized': False,
            'limitation': 'Conditional audit of supplied event-specific coverage declarations, not verified provider facts or an applied return series. Endpoint dates do not establish embedding. Unknown coverage never implies zero, full loss, omission or addition. No event price, cash proceeds, chronology, denominator compatibility, point-in-time eligibility or complete return series is inferred.'}
