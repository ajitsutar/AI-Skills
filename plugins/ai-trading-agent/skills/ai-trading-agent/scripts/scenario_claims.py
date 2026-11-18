"""Objective-bound evidence over explicit finite terminal-model domains.

The evaluator is injected by financial_alignment. No source values are rewritten,
no continuous-space theorem or economic feasibility is inferred from a grid.
"""
from copy import deepcopy
from decimal import Decimal
from itertools import product
import hashlib
import json
import operator


PARAMETERS = frozenset({
    'annual_revenue_growth', 'terminal_ebit_margin', 'tax_rate',
    'net_debt_at_exit', 'annual_dilution', 'exit_ev_to_ebit',
    'cumulative_dividends_per_share',
})
OPERATORS = {'>=': operator.ge, '>': operator.gt, '<=': operator.le,
             '<': operator.lt, '==': operator.eq, '!=': operator.ne}
MEASURES = {
    'net_total_return_fraction': ('fraction', 'holding_period_return'),
    'terminal_share_price': ('currency_per_share', 'terminal_price'),
    'present_value_of_modeled_distributions': ('currency_per_share', 'present_value'),
}
MAX_COMBINATIONS = 4096


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _number(value):
    _require(not isinstance(value, bool), 'BOOLEAN_IS_NOT_NUMERIC_EVIDENCE')
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError('FINITE_NUMERIC_EVIDENCE_REQUIRED') from exc
    _require(result.is_finite(), 'FINITE_NUMERIC_EVIDENCE_REQUIRED')
    return result


def _identifiers(rows, name):
    _require(isinstance(rows, list) and rows, name + '_REQUIRED')
    _require(all(isinstance(r, dict) for r in rows), name + '_OBJECTS_REQUIRED')
    ids = [r.get('id') for r in rows]
    _require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids),
             name + '_UNIQUE_IDS_REQUIRED')


def _objective(spec, document):
    _require(spec.get('role') in {'declared_objective', 'diagnostic_comparator'},
             'EXPLICIT_OBJECTIVE_ROLE_REQUIRED')
    measure = spec.get('measure')
    if measure == 'dcf_discount_closure':
        return {'id': spec['id'], 'role': spec['role'], 'measure': measure,
                'status': 'UNAVAILABLE_DCF_MODEL_NOT_EVALUATED',
                'definition': deepcopy(spec),
                'reason': 'Terminal-multiple returns and distribution PV do not recompute an authored DCF opinion. A separate supported DCF cash-flow model and closure criterion are required.'}
    _require(measure in MEASURES, 'SUPPORTED_OBJECTIVE_MEASURE_REQUIRED')
    _require(spec.get('operator') in OPERATORS, 'OBJECTIVE_OPERATOR_REQUIRED')
    target = spec.get('target', {})
    unit, basis = MEASURES[measure]
    _require(target.get('unit') == unit and target.get('valuation_basis') == basis,
             'OBJECTIVE_TARGET_DIMENSIONS_MISMATCH')
    _require(_number(target.get('horizon_years')) == _number(document['years']),
             'OBJECTIVE_HORIZON_MISMATCH')
    if unit == 'currency_per_share':
        _require(bool(document.get('currency')) and target.get('currency') == document['currency'],
                 'OBJECTIVE_CURRENCY_MISMATCH')
    if basis == 'present_value':
        _require(bool(document.get('as_of')) and target.get('valued_at') == document['as_of'],
                 'OBJECTIVE_PRESENT_VALUE_DATE_MISMATCH')
    return {'id': spec['id'], 'role': spec['role'], 'measure': measure,
            'operator': spec['operator'], 'target': {**deepcopy(target), 'value': _number(target.get('value'))},
            'status': 'DEFINED', 'definition': deepcopy(spec)}


def _domain(document, contract):
    scenarios = document['scenarios']
    _identifiers(scenarios, 'SCENARIOS')
    domain = contract.get('domain', {})
    mode = domain.get('mode')
    if mode == 'supplied_scenarios':
        _require(len(scenarios) <= MAX_COMBINATIONS, 'FINITE_DOMAIN_LIMIT_EXCEEDED')
        return deepcopy(scenarios), {}, {
            'kind': 'SUPPLIED_ROWS', 'coverage_complete_for_declared_rows': True,
            'joint_parameter_space_exhaustive': False,
            'economic_feasibility_established': False,
            'row_count': len(scenarios), 'domain_definition': deepcopy(domain)}
    _require(mode == 'cartesian', 'EXPLICIT_FINITE_DOMAIN_MODE_REQUIRED')
    by_id = {s['id']: s for s in scenarios}
    base_id = domain.get('base_scenario_id')
    _require(base_id in by_id, 'DOMAIN_BASE_SCENARIO_REQUIRED')
    axes = domain.get('axes')
    _require(isinstance(axes, dict) and axes and set(axes) <= PARAMETERS,
             'EXPLICIT_SUPPORTED_PARAMETER_AXES_REQUIRED')
    count = 1
    normalized = {}
    for key in sorted(axes):
        values = axes[key]
        _require(isinstance(values, list) and values, 'NONEMPTY_AXIS_VALUES_REQUIRED')
        numbers = [_number(v) for v in values]
        _require(len(set(numbers)) == len(numbers), 'DUPLICATE_NUMERIC_AXIS_VALUES')
        count *= len(numbers)
        _require(count <= MAX_COMBINATIONS, 'FINITE_DOMAIN_LIMIT_EXCEEDED')
        normalized[key] = sorted(numbers)
    rows = []
    for i, values in enumerate(product(*normalized.values())):
        rows.append({**deepcopy(by_id[base_id]), **dict(zip(normalized, values)),
                     'id': 'combination:' + str(i + 1)})
    return rows, normalized, {
        'kind': 'FINITE_CARTESIAN_DOMAIN', 'base_scenario_id': base_id,
        'coverage_complete_for_declared_rows': True,
        'joint_parameter_space_exhaustive': False,
        'economic_feasibility_established': False,
        'row_count': len(rows), 'domain_definition': deepcopy(domain),
        'held_base_parameters': {k: deepcopy(v) for k, v in by_id[base_id].items()
                                 if k not in normalized and k != 'id'},
        'interpretation': 'Exhaustive only over the declared finite combinations, not continuous ranges, plausible business paths or financing constraints.'}


def _claim_result(rows, objective_id, conditions):
    matching, passing, unknown = [], [], []
    necessity_counterexamples, sufficiency_counterexamples = [], []
    for row in rows:
        condition = all(OPERATORS[c['operator']](_number(row['parameters'][c['parameter']]),
                                                _number(c['value'])) for c in conditions)
        result = row['objectives'][objective_id]['met']
        if condition:
            matching.append(row['id'])
        if result is True:
            passing.append(row['id'])
            if not condition:
                necessity_counterexamples.append(row['id'])
        if result is None:
            unknown.append(row['id'])
        if condition and result is False:
            sufficiency_counterexamples.append(row['id'])
    necessary = ('REFUTED_BY_COUNTEREXAMPLE' if necessity_counterexamples else
                 'UNDETERMINED' if unknown else
                 'NO_OBJECTIVE_SUCCESSES' if not passing else
                 'HOLDS_ON_EVALUATED_FINITE_DOMAIN')
    sufficient = ('REFUTED_BY_COUNTEREXAMPLE' if sufficiency_counterexamples else
                  'NO_CONDITION_WITNESSES' if not matching else
                  'UNDETERMINED' if set(matching) & set(unknown) else
                  'HOLDS_ON_EVALUATED_FINITE_DOMAIN')
    return {'necessary': necessary, 'sufficient': sufficient,
            'objective_success_row_ids': passing, 'condition_match_row_ids': matching,
            'unavailable_row_ids': unknown,
            'necessity_counterexample_row_ids': necessity_counterexamples,
            'sufficiency_counterexample_row_ids': sufficiency_counterexamples,
            'continuous_or_real_world_necessity_established': False}


def _frontiers(rows, axes, objective_id):
    """Report discrete adjacent evidence; never interpolate a continuous threshold."""
    output = []
    for axis in axes:
        other = [k for k in axes if k != axis]
        groups = {}
        for row in rows:
            key = tuple(row['parameters'][k] for k in other)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            group.sort(key=lambda r: r['parameters'][axis])
            values = [{'axis_value': r['parameters'][axis], 'row_id': r['id'],
                       **r['objectives'][objective_id]} for r in group]
            passing = [v['axis_value'] for v in values if v['met'] is True]
            transitions = [{'lower_row_id': a['row_id'], 'upper_row_id': b['row_id'],
                            'lower_met': a['met'], 'upper_met': b['met']}
                           for a, b in zip(values, values[1:])
                           if a['met'] is not None and b['met'] is not None and a['met'] != b['met']]
            output.append({'axis': axis, 'held_axis_values': dict(zip(other, key)),
                           'evaluated_values': values,
                           'minimum_passing_evaluated_value': min(passing) if passing else None,
                           'maximum_passing_evaluated_value': max(passing) if passing else None,
                           'adjacent_outcome_changes': transitions,
                           'continuous_threshold': None})
    return output


def analyze(document, evaluator):
    """Evaluate document['objective_evidence'] using evaluator(document, scenario)."""
    contract = deepcopy(document['objective_evidence'])
    _identifiers(contract.get('objectives'), 'OBJECTIVES')
    objectives = [_objective(o, document) for o in contract['objectives']]
    by_id = {o['id']: o for o in objectives}
    claims = contract.get('claims', [])
    _require(isinstance(claims, list), 'CLAIMS_LIST_REQUIRED')
    if claims:
        _identifiers(claims, 'CLAIMS')
    for claim in claims:
        _require(claim.get('objective_id') in by_id, 'CLAIM_OBJECTIVE_BINDING_REQUIRED')
        conditions = claim.get('conditions')
        _require(isinstance(conditions, list) and conditions, 'CLAIM_CONDITIONS_REQUIRED')
        for cond in conditions:
            _require(cond.get('parameter') in PARAMETERS and cond.get('operator') in OPERATORS,
                     'SUPPORTED_CLAIM_CONDITION_REQUIRED')
            _number(cond.get('value'))
    candidates, axes, scope = _domain(document, contract)
    rows = []
    for candidate in candidates:
        result = evaluator(deepcopy(document), deepcopy(candidate))
        observations = {}
        for obj in objectives:
            value = result.get(obj['measure']) if obj['status'] == 'DEFINED' else None
            numeric = _number(value) if value is not None else None
            target = obj['target']['value'] if obj['status'] == 'DEFINED' else None
            observations[obj['id']] = {
                'measure': obj['measure'], 'value': numeric, 'target': target,
                'difference': numeric - target if numeric is not None else None,
                'met': OPERATORS[obj['operator']](numeric, target) if numeric is not None else None,
                'status': 'EVALUATED' if numeric is not None else 'UNAVAILABLE',
            }
        rows.append({'id': candidate['id'],
                     'parameters': {k: _number(candidate[k]) for k in sorted(PARAMETERS)},
                     'model_status': result.get('status'), 'objectives': observations})
    evaluations = []
    for claim in claims:
        evaluations.append({**deepcopy(claim),
                            'joint_condition': _claim_result(rows, claim['objective_id'], claim['conditions']),
                            'individual_conditions': [
                                {'condition': deepcopy(cond), **_claim_result(rows, claim['objective_id'], [cond])}
                                for cond in claim['conditions']]})
    for obj in objectives:
        obj['passing_row_ids'] = [r['id'] for r in rows if r['objectives'][obj['id']]['met'] is True]
        obj['failing_row_ids'] = [r['id'] for r in rows if r['objectives'][obj['id']]['met'] is False]
        obj['unavailable_row_ids'] = [r['id'] for r in rows if r['objectives'][obj['id']]['met'] is None]
        obj['discrete_frontiers'] = _frontiers(rows, axes, obj['id'])
    return {'status': 'PARTIAL' if any(o['unavailable_row_ids'] for o in objectives) else 'COMPUTED',
            'scope': scope, 'objectives': objectives, 'rows': rows, 'claims': evaluations,
            'input_contract_sha256': hashlib.sha256(json.dumps(contract, sort_keys=True, default=str).encode()).hexdigest(),
            'interpretation': 'Each claim applies only to its named objective, target dimensions and declared finite domain. Counterexamples are mathematical model rows with economic feasibility unverified. No user goal, DCF closure, probability or continuous necessity is inferred.'}
