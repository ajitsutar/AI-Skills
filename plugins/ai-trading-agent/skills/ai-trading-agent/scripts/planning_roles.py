"""Declared planning roles and a non-allocating comparison convention.

These helpers interpret typed declarations, not natural language or account truth.
They neither select a strategy nor derive quantities, reservations or buying power.
"""
from copy import deepcopy
from planning_alignment import amount, finish
from quant_common import require


SOURCE_ROLES = {'supplied_observation', 'hypothetical_scenario', 'user_assumption', 'unknown'}
SEMANTIC_ROLES = {'observation', 'maximum', 'minimum', 'target', 'pending', 'scenario', 'unknown'}
PENDING_STATES = {'unknown', 'reserved', 'open_position', 'proposed', 'cancelled'}
DIMENSIONS = ('metric', 'unit', 'scope', 'basis')


def source_roles(document):
    """Interpret the retained planning source without filling ambiguous bases.

    document={currency,role,source,source_ref,source_role,checks?}. Supported
    source fields are capital/contribution and trade.cash/maximum_planned_loss/
    pending_exposure. A loss basis exists only when explicitly declared in
    trade.maximum_planned_loss_basis; separate costs do not declare that basis.
    """
    source = document.get('source')
    require(isinstance(source, dict), 'SOURCE_OBJECT_REQUIRED')
    source_currencies = [source[key] for key in ('currency', 'base_currency') if key in source]
    require(source_currencies and all(value == document['currency'] for value in source_currencies),
            'SOURCE_CURRENCY_REQUIRED_OR_MISMATCH_NO_FX')
    ref = _text(document.get('source_ref'), 'source_ref')
    role = document.get('source_role')
    require(role in SOURCE_ROLES, 'SOURCE_ROLE_REQUIRED')
    trade = source.get('trade', {})
    require(isinstance(trade, dict), 'TRADE_SOURCE_OBJECT_REQUIRED')
    records = []
    for owner, key, pointer, semantic, metric, basis in (
        (source, 'capital', '/capital', 'observation', 'capital', None),
        (source, 'contribution', '/contribution', 'scenario', 'contribution', None),
        (trade, 'cash', '/trade/cash', 'observation', 'cash', None),
        (trade, 'maximum_planned_loss', '/trade/maximum_planned_loss', 'maximum',
         'planned_loss', trade.get('maximum_planned_loss_basis')),
        (trade, 'pending_exposure', '/trade/pending_exposure', 'pending', 'exposure', None)):
        if key not in owner:
            continue
        records.append({'id': key, 'value': deepcopy(owner[key]), 'source_ref': ref + pointer,
                        'source_role': role, 'semantic_role': semantic, 'metric': metric,
                        'unit': document['currency'], 'scope': 'trade' if owner is trade else 'planning',
                        'basis': basis})
    bound = {**document, 'records': records}
    result = input_roles(bound)
    return finish(document, 'planning-source-roles', status='INTERPRETED',
                  records=result['records'], checks=result['checks'], retained_input=deepcopy(document),
                  actual_portfolio_inferred=False, selected_quantity=None, selected_allocation=None,
                  loss_basis_inferred_from_costs=False,
                  limitations=result['limitations'] + ['Separate cost fields never resolve an unspecified loss-ceiling basis.'])


def _text(value, name):
    require(isinstance(value, str) and bool(value.strip()), 'TEXT_REQUIRED:' + name)
    return value


def _rows(value, name):
    require(isinstance(value, list) and all(isinstance(x, dict) for x in value), 'OBJECT_ARRAY_REQUIRED:' + name)
    ids = [_text(x.get('id'), name + '.id') for x in value]
    require(len(ids) == len(set(ids)), 'UNIQUE_IDS_REQUIRED:' + name)
    return value


# Explicit known numeric dimensions only; unfamiliar custom units remain declarations.
BOOLEAN_INCOMPATIBLE_UNITS = {
    'usd', 'eur', 'gbp', 'jpy', 'cad', 'aud', 'chf', 'cny', 'inr',
    'currency', 'money', 'dollars', 'shares', 'share', 'count', 'percent',
    'percentage', '%', 'bps', 'basis_points', 'fraction', 'ratio',
    'days', 'hours', 'seconds', 'years', 'number', 'integer', 'decimal',
}


def _record(record, currency=None):
    require(isinstance(record, dict), 'RECORD_OBJECT_REQUIRED')
    _text(record.get('id'), 'record.id')
    source = record.get('source_role', 'unknown')
    role = record.get('semantic_role', 'unknown')
    require(source in SOURCE_ROLES, 'INVALID_SOURCE_ROLE')
    require(role in SEMANTIC_ROLES, 'INVALID_SEMANTIC_ROLE')
    for key in DIMENSIONS:
        require(record.get(key) is None or isinstance(record[key], str), 'TEXT_METADATA_REQUIRED:' + key)
    state = record.get('pending_state', 'unknown')
    require(state in PENDING_STATES, 'INVALID_PENDING_STATE')
    require(role == 'pending' or 'pending_state' not in record, 'PENDING_STATE_REQUIRES_PENDING_ROLE')
    present = 'value' in record
    known = present and record['value'] is not None
    # bool subclasses int in Python; validate its declared unit before numeric logic.
    if known and isinstance(record['value'], bool):
        unit = (record.get('unit') or '').strip().casefold()
        declared_currency = currency.strip().casefold() if isinstance(currency, str) else None
        require(not unit or (unit not in BOOLEAN_INCOMPATIBLE_UNITS and unit != declared_currency),
                'BOOLEAN_VALUE_UNIT_MISMATCH:' + record['id'])
    if known and role in {'maximum', 'minimum', 'target'}:
        amount(record['value'], 'constraint')
    return {**deepcopy(record), 'source_role': source, 'semantic_role': role,
            'value_presence': 'absent' if not present else 'explicit_null' if not known else 'supplied',
            'is_observed_state': known and source == 'supplied_observation' and role == 'observation',
            'comparison_relation': {'maximum': 'le', 'minimum': 'ge', 'target': 'eq'}.get(role),
            'pending_state': state if role == 'pending' else None,
            'pending_accounting_effect': 'unresolved' if role == 'pending' and state == 'unknown' else
                                         'declared_state_only_no_automatic_cash_adjustment' if role == 'pending' else None}


def input_roles(document):
    """Retain records[{id, value?, source_role, semantic_role, metric/unit/scope/basis?}].

    Optional checks[{id, constraint_id, candidate:{value, metric, unit, scope, basis}}]
    compare a candidate to a declared maximum/minimum/target with exact boundaries.
    Missing/mismatched dimensions stay unresolved. No candidate or size is inferred.
    """
    records = [_record(row, document.get('currency')) for row in _rows(document.get('records'), 'records')]
    by_id = {row['id']: row for row in records}
    checks = []
    for check in _rows(document.get('checks', []), 'checks'):
        constraint = by_id.get(check.get('constraint_id'))
        require(constraint is not None, 'UNKNOWN_CONSTRAINT_ID')
        require(constraint['comparison_relation'] is not None, 'BOUND_OR_TARGET_REQUIRED')
        candidate = check.get('candidate')
        require(isinstance(candidate, dict), 'CANDIDATE_OBJECT_REQUIRED')
        for key in DIMENSIONS:
            require(candidate.get(key) is None or isinstance(candidate[key], str), 'TEXT_METADATA_REQUIRED:' + key)
        unknown = [key for key in DIMENSIONS if not (candidate.get(key) or '').strip()
                   or not (constraint.get(key) or '').strip()]
        mismatch = [key for key in DIMENSIONS if key not in unknown and candidate[key] != constraint[key]]
        known_values = candidate.get('value') is not None and constraint.get('value') is not None
        left = amount(candidate['value'], 'candidate') if candidate.get('value') is not None else None
        right = amount(constraint['value'], 'constraint') if constraint.get('value') is not None else None
        relation = constraint['comparison_relation']
        comparable = known_values and not unknown and not mismatch
        checks.append({**deepcopy(check), 'relation': relation,
                       'status': 'INCOMPARABLE' if mismatch else 'UNRESOLVED' if not comparable else 'CHECKED',
                       'satisfies_declared_relation': ({'le': left <= right, 'ge': left >= right, 'eq': left == right}[relation]
                                                      if comparable else None),
                       'unknown_dimensions': unknown, 'mismatched_dimensions': mismatch,
                       'missing_value': not known_values,
                       'constraint_source_role': constraint['source_role']})
    return finish(document, 'planning-input-roles', status='INTERPRETED', records=records, checks=checks,
                  retained_input=deepcopy(document), actual_portfolio_inferred=False,
                  selected_quantity=None, selected_allocation=None,
                  limitations=['Roles and comparability are caller declarations; bind them to the supplied source.',
                               'A maximum is an inequality, not an amount to spend or a loss target.',
                               'Pending amounts never establish a new trade, reservation or cash deduction by themselves.',
                               'An explicit empty scenario ledger does not establish observed empty holdings.'])


def reference_comparison(document):
    """Compare requested sleeves in input order without assigning weights or sizes.

    sleeves[{id, exposure_model?:long_linear_price|not_applicable|unknown,
             allocation_record?, holdings_record?, return_observations_record?}].
    Records use input_roles syntax. Optional shocks[{id, return_fraction}] apply
    only to the explicit long_linear_price reference, on ONE currency unit of
    hypothetical exposed notional. No default shocks, cash yield or strategy model.
    """
    sleeves = _rows(document.get('sleeves'), 'sleeves')
    require(bool(sleeves), 'AT_LEAST_ONE_COMPARISON_REQUIRED')
    shocks = _rows(document.get('shocks', []), 'shocks')
    parsed_shocks = [(row['id'], amount(row.get('return_fraction'), 'shock', -1)) for row in shocks]
    result = []
    for sleeve in sleeves:
        model = sleeve.get('exposure_model', 'unknown')
        require(model in {'long_linear_price', 'not_applicable', 'unknown'}, 'INVALID_REFERENCE_EXPOSURE_MODEL')
        records = {key: _record(sleeve[key], document.get('currency')) if sleeve.get(key) is not None else None
                   for key in ('allocation_record', 'holdings_record', 'return_observations_record')}
        for key in ('holdings_record', 'return_observations_record'):
            record = records[key]
            require(record is None or record.get('value') is None or isinstance(record['value'], list),
                    'LIST_VALUE_REQUIRED:' + key)
        allocation, holdings, returns = (records[key] for key in records)
        # Per-unit price P&L equals the supplied return, so no portfolio engine,
        # turnover, costs, horizon or holding inference is involved.
        scenarios = [{'id': sid, 'return_fraction': shock, 'price_pnl_per_currency_unit': shock}
                     for sid, shock in parsed_shocks] if model == 'long_linear_price' else []
        result.append({'id': sleeve['id'], 'exposure_model': model, **records,
                       'observed_allocation': deepcopy(allocation.get('value')) if allocation and allocation['is_observed_state'] else None,
                       'observed_holdings_available': bool(holdings and holdings['is_observed_state']),
                       'supplied_return_observations_present': bool(returns and returns.get('value')),
                       'reference_notional': '1' if model == 'long_linear_price' else None,
                       'reference_relation': 'price_pnl / exposed_notional = supplied_price_return'
                                             if model == 'long_linear_price' else None,
                       'reference_scenarios': scenarios,
                       'scenario_status': 'COMPUTED' if scenarios else 'NO_SHOCKS_SUPPLIED' if model == 'long_linear_price'
                                          else 'NOT_APPLICABLE' if model == 'not_applicable' else 'UNKNOWN_MODEL',
                       'performance_estimate': None, 'recommended_allocation': None})
    return finish(document, 'planning-reference-comparison', status='COMPARED',
                  convention='declared-capabilities-and-unit-price-exposure-1', sleeves=result,
                  retained_input=deepcopy(document), selected_allocation=None,
                  limitations=['One currency unit is an analytical denominator, not an investment or sleeve weight.',
                               'Labels do not establish strategy rules, exposure model, actual holdings, returns or covariance.',
                               'No shocks or quantities are supplied by default; use source scenarios before supplemental sensitivities.',
                               'Price effects omit costs, yield, flows and taxes; not_applicable does not mean zero total risk.',
                               'Supplied records and empty lists are declarations, not authenticated account observations.'])
