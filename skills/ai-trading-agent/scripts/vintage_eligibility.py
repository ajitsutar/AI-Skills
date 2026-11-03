"""Original source-declared vintage bounds audit; no acquisition or timestamp inference.

assess(document) accepts exactly value_id, source_ref, precision, as_of,
first_publication, superseded_at, basis_from, basis_until. Precision is date or
timestamp, shared by all supplied bounds. The four bounds may be null; missing
first publication is unresolved. Date publication boundaries have unknown
intraday timing. Basis boundaries instead encode an explicitly supplied inclusive
start/exclusive end convention, never an inferred corporate-action convention.
"""
from datetime import date, datetime
import re

from point_in_time_data import timestamp


KEYS = {'value_id', 'source_ref', 'precision', 'as_of', 'first_publication',
        'superseded_at', 'basis_from', 'basis_until'}
BOUNDS = ('first_publication', 'superseded_at', 'basis_from', 'basis_until')


def assess(document):
    """Intersect supplied publication and basis bounds, preserving unresolved days."""
    if type(document) is not dict or set(document) != KEYS:
        raise ValueError('VINTAGE_FIELDS_REQUIRED: ' + ', '.join(sorted(KEYS)))
    for key in ('value_id', 'source_ref'):
        value = document[key]
        if (type(value) is not str or not value or value != value.strip()
                or any(ord(c) < 32 for c in value)):
            raise ValueError(key + ' must be nonempty trimmed source identity text')
    precision = document['precision']
    if precision not in ('date', 'timestamp'):
        raise ValueError('precision must be date or timestamp')

    def parse(value):
        if precision == 'timestamp':
            return datetime.fromisoformat(timestamp(value).replace('Z', '+00:00'))
        if type(value) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value):
            raise ValueError('date precision requires YYYY-MM-DD; no mixed precision')
        return date.fromisoformat(value)

    cutoff = parse(document['as_of'])
    parsed = {key: None if document[key] is None else parse(document[key]) for key in BOUNDS}
    first, next_release = parsed['first_publication'], parsed['superseded_at']
    if first is not None and next_release is not None:
        if next_release < first or (precision == 'timestamp' and next_release == first):
            raise ValueError('supersession must follow first publication; equal dates remain ambiguous')
    start, end = parsed['basis_from'], parsed['basis_until']
    if start is not None and end is not None and end <= start:
        raise ValueError('basis_until must follow basis_from')

    # Every constraint is retained even if another already rules the value out.
    constraints = []
    for key in BOUNDS:
        bound = parsed[key]
        publication = key in ('first_publication', 'superseded_at')
        lower = key in ('first_publication', 'basis_from')
        operator = '>=' if lower else '<'
        if publication and precision == 'date' and lower:
            operator = '>'
        if bound is None:
            result = 'UNRESOLVED' if key == 'first_publication' else 'NOT_DECLARED'
        elif publication and precision == 'date' and cutoff == bound:
            result = 'UNRESOLVED'
        elif (cutoff >= bound if lower else cutoff < bound):
            result = 'SATISFIED'
        else:
            result = 'VIOLATED'
        constraints.append({'bound': key, 'source_value': document[key],
                            'required_comparison': operator, 'result': result})
    results = {c['result'] for c in constraints}
    status = ('INELIGIBLE' if 'VIOLATED' in results else
              'UNRESOLVED' if 'UNRESOLVED' in results else 'CONDITIONAL_ELIGIBLE')
    return {'schema_version': 1, 'status': status,
            'eligible_under_supplied_bounds': status == 'CONDITIONAL_ELIGIBLE',
            'value_id': document['value_id'], 'source_ref': document['source_ref'],
            'precision': precision, 'as_of': document['as_of'],
            'bounds': {key: document[key] for key in BOUNDS}, 'constraints': constraints,
            'bound_conventions': {'publication': 'Date boundary days unresolved; timestamps use [first, next).',
                                  'basis': 'Caller-declared [basis_from, basis_until); null means no bound supplied.'},
            'limitation': 'Supplied bounds only. A null upper bound is not proof that no later revision exists. Date mode assumes a common source calendar and does not establish a timezone, intraday availability, a trading session, source authenticity, complete revision history or point-in-time research readiness.'}
