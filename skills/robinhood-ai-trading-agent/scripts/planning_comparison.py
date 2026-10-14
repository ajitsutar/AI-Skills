"""Source-bound alternatives and date-only settlement/transfer scenarios."""
from copy import deepcopy
from datetime import date
from itertools import combinations
import re

from planning_alignment import amount, finish
from quant_common import require


DIMENSIONS = ('metric', 'unit', 'basis')


def _text(value, name):
    require(isinstance(value, str) and bool(value.strip()), 'TEXT_REQUIRED:' + name)
    return value


def _rows(value, name):
    require(isinstance(value, list) and value and all(isinstance(row, dict) for row in value),
            'NONEMPTY_OBJECT_ARRAY_REQUIRED:' + name)
    ids = [_text(row.get('id'), name + '.id') for row in value]
    require(len(ids) == len(set(ids)), 'UNIQUE_IDS_REQUIRED:' + name)
    return value


def alternative_comparison(document):
    """Pareto comparisons of explicitly declared metrics, with no optimization.

    criteria[{id,metric,unit,basis,direction:minimize|maximize}];
    alternatives[{id,values:{criterion_id:number|null|dimensioned_record}}].
    Scalars use the shared criterion dimensions. Dimensioned records must contain
    value, metric, unit and basis; missing or mismatched dimensions do not compare.
    """
    require(not any(key in document for key in ('weights', 'user_priority', 'priority')),
            'PREFERENCE_POLICY_NOT_IMPLEMENTED')
    criteria = deepcopy(_rows(document.get('criteria'), 'criteria'))
    for criterion in criteria:
        for key in DIMENSIONS:
            _text(criterion.get(key), key)
        require(criterion.get('direction') in {'minimize', 'maximize'}, 'CRITERION_DIRECTION_REQUIRED')
        require(not any(key in criterion for key in ('weight', 'weights', 'priority', 'user_priority')), 'PREFERENCE_POLICY_NOT_IMPLEMENTED')
    alternatives = _rows(document.get('alternatives'), 'alternatives')
    criterion_ids = {criterion['id'] for criterion in criteria}
    normalized = []
    for alternative in alternatives:
        values = alternative.get('values')
        require(isinstance(values, dict), 'CRITERION_VALUES_REQUIRED')
        require(set(values) <= criterion_ids, 'UNDECLARED_CRITERION_VALUE')
        cells = {}
        for criterion in criteria:
            raw = values.get(criterion['id'])
            record = raw if isinstance(raw, dict) else {'value': raw, **{k: criterion[k] for k in DIMENSIONS}}
            unknown = [k for k in DIMENSIONS if not isinstance(record.get(k), str) or not record[k].strip()]
            mismatched = [k for k in DIMENSIONS if k not in unknown and record[k] != criterion[k]]
            value = amount(record['value'], 'criterion') if record.get('value') is not None else None
            cells[criterion['id']] = {'value': value, **{k: record.get(k) for k in DIMENSIONS},
                                     'comparable': value is not None and not unknown and not mismatched,
                                     'unknown_dimensions': unknown, 'mismatched_dimensions': mismatched}
        normalized.append({'id': alternative['id'], 'values': cells})
    pairs, dominated, unresolved = [], set(), set()
    for left, right in combinations(normalized, 2):
        better_left, better_right, equal, unknown = [], [], [], []
        for criterion in criteria:
            cid = criterion['id']; a, b = left['values'][cid], right['values'][cid]
            if not (a['comparable'] and b['comparable']):
                unknown.append(cid)
            elif a['value'] == b['value']:
                equal.append(cid)
            elif (a['value'] < b['value']) == (criterion['direction'] == 'minimize'):
                better_left.append(cid)
            else:
                better_right.append(cid)
        winner = None
        if unknown:
            relation = 'INDETERMINATE'
            unresolved.update((left['id'], right['id']))
        elif better_left and not better_right:
            relation, winner = 'LEFT_DOMINATES', left['id']; dominated.add(right['id'])
        elif better_right and not better_left:
            relation, winner = 'RIGHT_DOMINATES', right['id']; dominated.add(left['id'])
        elif not better_left and not better_right:
            relation = 'EQUIVALENT_ON_DECLARED_CRITERIA'
        else:
            relation = 'TRADEOFF'
        pairs.append({'left_id': left['id'], 'right_id': right['id'], 'relation': relation,
                      'dominant_id': winner, 'left_favored_criteria': better_left,
                      'right_favored_criteria': better_right, 'equal_criteria': equal,
                      'unresolved_criteria': unknown,
                      'conditional_tradeoffs': [
                          {'alternative_id': row['id'], 'favored_if_prioritizing_only': favored,
                           'qualification': 'Criterion-local preference only; no overall selection or weights.'}
                          for row, favored in ((left, better_left), (right, better_right)) if favored]})
    incomplete = {row['id'] for row in normalized if not all(v['comparable'] for v in row['values'].values())}
    unresolved.update(incomplete)
    survivors = [row['id'] for row in normalized if row['id'] not in dominated]
    return finish(document, 'planning-alternative-comparison', status='COMPARED', criteria=criteria,
                  alternatives=normalized, pairwise=pairs,
                  non_dominated_ids=[x for x in survivors if x not in unresolved],
                  indeterminate_ids=[x for x in survivors if x in unresolved],
                  not_proven_dominated_ids=survivors,
                  dominated_ids=[row['id'] for row in normalized if row['id'] in dominated],
                  selected_alternative=None, objective_weights=None, input_order_is_priority=False,
                  retained_input=deepcopy(document),
                  limitations=['Dominance requires every declared criterion to be known and comparable for that pair.',
                               'Unknown values are neither favorable nor grounds for exclusion.',
                               'Non-dominated is not an optimized winner; unresolved comparisons remain indeterminate.',
                               'All dates, valuation denominators, cost and tax conventions belong in the supplied metric basis.',
                               'Source order is retained solely for presentation; no criteria or alternatives receive default priority.'])


def _day(value, name):
    require(isinstance(value, str) and re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) is not None,
            'DATE_ONLY_REQUIRED:' + name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('INVALID_DATE:' + name) from exc


def settlement_transfer_paths(document):
    """Advance only through supplied business_dates; never extend a calendar.

    Lags count listed-date transitions, with zero meaning the same listed date.
    A date-only deadline is a date comparison, never a spendability guarantee.
    Optional same_day_transfer_assumption={accepted:bool,basis:nonempty_text}
    declares whether settlement-day initiation is assumed possible.
    """
    raw_dates = document.get('business_dates')
    require(isinstance(raw_dates, list) and bool(raw_dates), 'LISTED_BUSINESS_DATES_REQUIRED')
    days = [_day(value, 'business_dates') for value in raw_dates]
    require(all(a < b for a, b in zip(days, days[1:])), 'STRICTLY_INCREASING_UNIQUE_BUSINESS_DATES')
    sale = _day(document.get('sale_date'), 'sale_date')
    deadline = _day(document.get('spendable_deadline'), 'spendable_deadline')
    require(sale in days, 'SALE_DATE_MUST_BE_LISTED')
    for key in ('settlement_lag', 'transfer_lag'):
        require(type(document.get(key)) is int and document[key] >= 0, 'NONNEGATIVE_INTEGER_LAG:' + key)
    assumption = document.get('same_day_transfer_assumption')
    if assumption is not None:
        require(isinstance(assumption, dict) and type(assumption.get('accepted')) is bool,
                'EXPLICIT_SAME_DAY_TRANSFER_ASSUMPTION_REQUIRED')
        _text(assumption.get('basis'), 'same_day_transfer_assumption.basis')
    sale_index = days.index(sale)
    settlement_index = sale_index + document['settlement_lag']
    def at(index):
        return days[index].isoformat() if index < len(days) else None
    settlement = at(settlement_index)
    paths = []
    for offset, name in ((0, 'same_day_initiation'), (1, 'next_listed_day_initiation')):
        initiation = at(settlement_index + offset)
        arrival = at(settlement_index + offset + document['transfer_lag'])
        excluded = offset == 0 and assumption is not None and not assumption['accepted']
        missing = [key for key, value in (('settlement_date', settlement), ('transfer_initiation_date', initiation),
                                          ('arrival_date', arrival)) if value is None]
        relation = None if arrival is None else ('BEFORE_DEADLINE_DATE' if _day(arrival, 'arrival') < deadline else
                                                'ON_DEADLINE_DATE_INTRADAY_UNRESOLVED' if _day(arrival, 'arrival') == deadline else
                                                'AFTER_DEADLINE_DATE')
        conditions = ['Supplied business-date sequence and settlement/transfer lags apply.',
                      'Transfer is initiated and accepted on the modeled initiation date; arrival is spendable as modeled.']
        if offset == 0:
            conditions.append('Settlement completes before transfer acceptance cutoff on the same date.')
        if arrival == deadline.isoformat():
            conditions.append('Arrival becomes spendable before the deadline time; no times were supplied.')
        paths.append({'id': name, 'settlement_date': settlement, 'transfer_initiation_date': initiation,
                      'arrival_date': arrival, 'date_relation_to_deadline': relation,
                      'status': 'EXCLUDED_BY_EXPLICIT_ASSUMPTION' if excluded else
                                'UNRESOLVED_CALENDAR_COVERAGE' if missing else
                                'POSSIBLE_INTRADAY_ACCEPTANCE_UNKNOWN' if offset == 0 and assumption is None else
                                'CONDITIONAL_DATE_PATH',
                      'same_day_acceptance_assumption': deepcopy(assumption) if offset == 0 else None,
                      'missing_calendar_dates_for': missing, 'conditions': conditions,
                      'guaranteed_spendable_by_deadline': False})
    return finish(document, 'planning-settlement-transfer-paths', status='DATE_PATHS_MODELED',
                  sale_date=sale.isoformat(), settlement_date=settlement, spendable_deadline=deadline.isoformat(),
                  paths=paths, retained_input=deepcopy(document), calendar_extended=False,
                  actual_calendar_verified=False, broker_availability_verified=False,
                  limitations=['Only supplied listed-date transitions are counted; omitted dates are not reconstructed.',
                               'Settlement, transfer initiation and spendable arrival are separate events.',
                               'Date-only same-day ordering and deadline-time acceptance are not guaranteed.',
                               'Conditional paths are analytical scenarios, not observed broker or bank availability.'])
