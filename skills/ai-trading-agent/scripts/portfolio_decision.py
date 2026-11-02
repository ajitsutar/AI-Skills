"""Source-bound, advisory budget sizing and allocation context calculations.

Only the existing planning_alignment.trade_costs helper sizes quantities. These
functions have no network, broker, permission, order or source-verification logic.
"""
from copy import deepcopy
from decimal import Context, Decimal, localcontext
import hashlib

import planning_alignment
from quant_common import digest, require


ZERO = Decimal(0)
BASES = {'midpoint', 'bid', 'ask', 'last', 'other', 'unknown'}
TYPES = {'equity', 'fund', 'cash', 'other', 'unknown'}
DIMENSIONS = ('issuer_id', 'sector', 'industry')


def _number(value, name, minimum=0):
    return None if value is None else planning_alignment.amount(value, name, minimum)


def _id(value, name):
    require(isinstance(value, str) and bool(value.strip()) and value == value.strip(),
            'EXACT_NONEMPTY_IDENTIFIER_REQUIRED:' + name)
    return value


def _records(value, name):
    require(isinstance(value, list), 'ARRAY_REQUIRED:' + name)
    require(all(isinstance(row, dict) for row in value), 'OBJECT_ROWS_REQUIRED:' + name)
    ids = [_id(row.get('id'), name + '.id') for row in value]
    require(len(set(ids)) == len(ids), 'UNIQUE_IDS_REQUIRED:' + name)
    return value


def _header(document):
    require(isinstance(document, dict), 'DOCUMENT_OBJECT_REQUIRED')
    _id(document.get('currency'), 'currency')
    require(document.get('role') in {'supplied_observation', 'hypothetical_scenario', 'user_assumption'},
            'INPUT_ROLE_REQUIRED')


def _precision(document):
    # Independent of a caller's Decimal context, including rounding/traps.
    def size(value):
        if isinstance(value, dict):
            return sum(size(v) for v in value.values())
        if isinstance(value, list):
            return sum(size(v) for v in value)
        if isinstance(value, (int, float, str)) and not isinstance(value, bool):
            try:
                number = Decimal(str(value))
                if number.is_finite():
                    parts = number.as_tuple()
                    return len(parts.digits) + abs(parts.exponent)
            except Exception:
                pass
        return 0
    return 64 + size(document)


def _finish(document, method, **result):
    def clean(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value
    return clean({'method': method + '-1', 'currency': document['currency'],
                  'input_role': document['role'], 'input_sha256': digest(document),
                  'retained_input': deepcopy(document), 'advisory_only': True,
                  'source_authenticity_verified': False, **result})


def _friction(document):
    unresolved = []
    basis = document.get('price_basis')
    require(basis is None or basis in BASES, 'INVALID_PRICE_BASIS')
    costs = document.get('costs')
    if costs is None:
        unresolved.append('COSTS_NOT_SUPPLIED')
        applied = None
    else:
        applied = deepcopy(_records(costs, 'costs'))
        for cost in applied:
            value = _number(cost.get('amount'), 'cost.amount')
            unit, phase = cost.get('unit'), cost.get('phase')
            require(unit is None or unit in {'per_share', 'per_order', 'bps_notional', 'per_round_trip'},
                    'INVALID_COST_UNIT')
            require(phase is None or phase in {'entry', 'exit', 'each_side', 'round_trip'}, 'INVALID_COST_PHASE')
            if value is None or unit is None or phase is None:
                unresolved.append('INCOMPLETE_COST:' + cost['id'])
            if unit == 'per_round_trip':
                require(phase in {None, 'round_trip'}, 'ROUND_TRIP_COST_PHASE_CONFLICT')
                require(cost.get('charged_at') in {None, 'entry', 'exit'}, 'INVALID_ROUND_TRIP_CHARGE_TIME')
                if cost.get('charged_at') is None:
                    unresolved.append('ROUND_TRIP_CHARGE_TIME_UNKNOWN:' + cost['id'])
            elif unit is not None:
                require(phase != 'round_trip', 'ROUND_TRIP_COST_UNIT_REQUIRED')
            if cost.get('kind') in {'quoted_full_spread', 'one_way_slippage'}:
                unresolved.append('PRICE_FRICTION_REQUIRES_SEPARATE_FIELD:' + cost['id'])
            if cost.get('currency', document['currency']) != document['currency']:
                unresolved.append('COST_CURRENCY_MISMATCH:' + cost['id'])

    quote = document.get('quoted_spread')
    quote_unknowns = []
    if quote is not None:
        require(isinstance(quote, dict), 'QUOTED_SPREAD_OBJECT_REQUIRED')
        value = _number(quote.get('amount'), 'quoted_spread.amount')
        require(quote.get('unit') in {None, 'bps', 'price_per_share'}, 'INVALID_QUOTED_SPREAD_UNIT')
        reference = quote.get('reference_price_basis')
        require(reference is None or reference in BASES, 'INVALID_QUOTE_REFERENCE_BASIS')
        _number(quote.get('reference_price'), 'quoted_spread.reference_price', '0.000000000001')
        if value is None or quote.get('unit') is None:
            quote_unknowns.append('INCOMPLETE_QUOTED_SPREAD')
        if reference in {None, 'unknown'}:
            quote_unknowns.append('QUOTE_REFERENCE_PRICE_BASIS_UNKNOWN')

    model = document.get('modeled_slippage')
    slippage_status = 'NOT_SUPPLIED'
    if 'modeled_slippage' in document and model is None:
        slippage_status = 'UNRESOLVED'
        unresolved.append('MODELED_SLIPPAGE_UNKNOWN')
    elif model is not None:
        require(isinstance(model, dict), 'MODELED_SLIPPAGE_OBJECT_REQUIRED')
        model_id = _id(model.get('id'), 'modeled_slippage.id')
        value = _number(model.get('amount'), 'modeled_slippage.amount')
        unit, phase = model.get('unit'), model.get('phase')
        require(unit in {None, 'per_share', 'bps_notional'}, 'INVALID_SLIPPAGE_UNIT')
        require(phase in {None, 'entry', 'exit', 'each_side'}, 'INVALID_SLIPPAGE_PHASE')
        require(model.get('convention') in {None, 'one_way', 'unknown'}, 'ONE_WAY_MODEL_REQUIRED')
        reference = model.get('reference_price_basis')
        require(reference is None or reference in BASES, 'INVALID_SLIPPAGE_REFERENCE_BASIS')
        overlap = model.get('overlap')
        require(overlap in {None, 'independent', 'included_in_costs', 'unknown'}, 'INVALID_SLIPPAGE_OVERLAP')
        model_unknowns = []
        if value is None or unit is None or phase is None or model.get('convention') != 'one_way':
            model_unknowns.append('ONE_WAY_SLIPPAGE_MODEL_INCOMPLETE')
        if basis in {None, 'unknown'} or reference in {None, 'unknown'}:
            model_unknowns.append('SLIPPAGE_REFERENCE_PRICE_BASIS_UNKNOWN')
        elif basis != reference:
            model_unknowns.append('SLIPPAGE_REFERENCE_PRICE_BASIS_MISMATCH')
        elif basis == 'other' and (not document.get('price_reference_description') or
                                  document.get('price_reference_description') != model.get('price_reference_description')):
            model_unknowns.append('OTHER_PRICE_REFERENCE_DESCRIPTION_UNRESOLVED')
        if model.get('currency', document['currency']) != document['currency']:
            model_unknowns.append('SLIPPAGE_CURRENCY_MISMATCH')
        if overlap in {None, 'unknown'}:
            model_unknowns.append('SLIPPAGE_COST_OVERLAP_UNKNOWN')
        if overlap == 'included_in_costs':
            ids = model.get('overlapping_cost_ids')
            if not ids:
                model_unknowns.append('OVERLAPPING_COST_IDS_UNKNOWN')
            else:
                require(isinstance(ids, list) and all(isinstance(i, str) for i in ids), 'OVERLAPPING_COST_IDS_REQUIRED')
                require(len(set(ids)) == len(ids), 'DUPLICATE_OVERLAPPING_COST_IDS')
                if applied is not None:
                    require(set(ids) <= {c['id'] for c in applied}, 'OVERLAPPING_COST_ID_NOT_SUPPLIED')
                    selected = [c for c in applied if c['id'] in ids]
                    required_phases = {'entry', 'exit'} if phase == 'each_side' else {phase}
                    for needed in required_phases - {None}:
                        covering = [c for c in selected if c.get('phase') in {needed, 'each_side'} or
                                    (c.get('phase') == 'round_trip' and c.get('charged_at') == needed)]
                        if not covering:
                            model_unknowns.append('SLIPPAGE_INCLUSION_PHASE_NOT_COVERED:' + needed)
                        elif value is not None and value > 0 and all(
                                c.get('amount') is not None and Decimal(str(c['amount'])) == 0
                                for c in covering):
                            model_unknowns.append('POSITIVE_SLIPPAGE_INCLUDED_ONLY_IN_ZERO_COSTS:' + needed)
        elif overlap == 'independent':
            require(not model.get('overlapping_cost_ids'), 'INDEPENDENT_SLIPPAGE_WITH_OVERLAPPING_COST_IDS')
            if applied is not None:
                require(model_id not in {c['id'] for c in applied}, 'DUPLICATE_SLIPPAGE_COST_ID')
                if not model_unknowns:
                    applied.append({'id': model_id, 'amount': model['amount'], 'unit': unit, 'phase': phase})
        unresolved.extend(model_unknowns)
        slippage_status = ('UNRESOLVED' if model_unknowns else 'ALREADY_INCLUDED_NO_EXTRA_CHARGE'
                           if overlap == 'included_in_costs' else 'EXPLICIT_ONE_WAY_MODEL')
    return {'status': 'INPUTS_UNRESOLVED' if unresolved else 'EXPLICIT_COST_MODEL',
            'price_basis': basis, 'quoted_full_spread': deepcopy(quote),
            'quote_unknowns': quote_unknowns, 'quoted_spread_added_to_costs': False,
            'modeled_slippage': deepcopy(model), 'modeled_slippage_status': slippage_status,
            'applied_costs': None if unresolved else applied, 'unresolved': unresolved,
            'cost_scope': 'Only explicitly supplied modeled costs; omitted frictions are not observed zero.'}


def friction_context(document):
    """Keep a full-spread observation separate from an explicit one-way cost model."""
    _header(document)
    with localcontext(Context(prec=_precision(document))):
        return _finish(document, 'price-friction-context', **_friction(document))


def budget_sizing(document):
    """Compose trade_costs for explicit cash budgets and quantity increments.

    mode=portfolio requires each row's budget; mode=alternatives gives each row
    the document budget independently. Neither mode chooses weights or securities.
    quantity_scenarios are separate whole/fractional increment assumptions.
    """
    _header(document)
    with localcontext(Context(prec=_precision(document))):
        return _budget_sizing(document)


def source_budget_sizing(document):
    """Map a complete retained fee/slippage source to every selected price row.

    The source's cost_assumptions has fee_per_trade and one_way_slippage_bps.
    Explicit RFC6901 bindings select that object and its declared currency from
    retained UTF-8 JSON bytes. Existing budget_sizing performs all arithmetic.
    Unknown quote bases stay unresolved; named basis sensitivities are separate.
    """
    from report_facts import pointer, strict_json
    _header(document)
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1,
            'SOURCE_BUDGET_SCHEMA_1_REQUIRED')
    source = document.get('cost_source')
    require(isinstance(source, dict) and isinstance(source.get('text'), str),
            'FULL_COST_SOURCE_TEXT_REQUIRED')
    require(source.get('role') in {'supplied_observation', 'hypothetical_scenario', 'user_assumption'},
            'COST_SOURCE_ROLE_REQUIRED')
    require(source.get('provenance') is not None, 'COST_SOURCE_PROVENANCE_REQUIRED')
    raw = source['text'].encode('utf-8')
    require(hashlib.sha256(raw).hexdigest() == source.get('sha256'), 'COST_SOURCE_BYTES_HASH_MISMATCH')
    retained = strict_json(raw)
    bindings = document.get('cost_bindings')
    require(isinstance(bindings, dict) and set(bindings) == {'cost_assumptions', 'currency'},
            'EXPLICIT_COST_AND_CURRENCY_BINDINGS_REQUIRED')
    assumptions = deepcopy(pointer(retained, bindings['cost_assumptions']))
    currency = pointer(retained, bindings['currency'])
    require(isinstance(currency, str) and currency == document['currency'], 'COST_SOURCE_CURRENCY_MISMATCH')
    require(isinstance(assumptions, dict) and set(assumptions) <=
            {'fee_per_trade', 'one_way_slippage_bps'}, 'UNSUPPORTED_COST_ASSUMPTION_SCHEMA')
    # Missing/null amounts remain missing, never implicit zero. Validate known
    # amounts here even when unknown price basis would otherwise prevent sizing.
    _number(assumptions.get('fee_per_trade'), 'fee_per_trade')
    _number(assumptions.get('one_way_slippage_bps'), 'one_way_slippage_bps')
    rows = _records(document.get('rows'), 'rows')
    scenarios = _records(document.get('quantity_scenarios'), 'quantity_scenarios')
    require(rows and scenarios, 'EXPLICIT_ROWS_AND_QUANTITY_SCENARIOS_REQUIRED')
    for scenario in scenarios:
        require(scenario.get('quantity_basis') in {'whole_shares', 'fractional_shares'}
                and scenario.get('quantity_step') is not None, 'EXPLICIT_QUANTITY_SCENARIO_REQUIRED')
    for row in rows:
        require(type(row.get('entry_orders')) is int and row['entry_orders'] > 0,
                'EXPLICIT_ENTRY_ORDER_COUNT_REQUIRED')
        require(not set(row) & {'costs', 'modeled_slippage'}, 'ROW_COST_OVERRIDE_NOT_SUPPORTED')
        require(row.get('price_basis') is None or row['price_basis'] in BASES, 'INVALID_PRICE_BASIS')
    provenance = {'source_bytes_sha256': source['sha256'], 'source_role': source['role'],
                  'source_provenance': deepcopy(source['provenance']),
                  'source_field_pointers': [{'field': key, 'pointer': value} for key, value in bindings.items()]}
    def mapped(sensitivity=None):
        derived = {key: deepcopy(document.get(key)) for key in
                   ('currency', 'role', 'mode', 'budget', 'quantity_scenarios')}
        derived['rows'] = []
        for original in rows:
            row = deepcopy(original)
            if sensitivity is not None and row.get('price_basis') in {None, 'unknown'}:
                row['price_basis'] = sensitivity['price_basis']
                row['price_reference_description'] = sensitivity.get('price_reference_description')
            basis = row.get('price_basis')
            row['costs'] = [{'id': 'source-fee-per-trade', 'amount': assumptions.get('fee_per_trade'),
                             'unit': 'per_order', 'phase': 'entry', 'currency': currency,
                             'provenance': deepcopy(provenance)}]
            row['modeled_slippage'] = {
                'id': 'source-one-way-slippage', 'amount': assumptions.get('one_way_slippage_bps'),
                'unit': 'bps_notional', 'phase': 'entry', 'convention': 'one_way',
                'reference_price_basis': basis, 'price_reference_description': row.get('price_reference_description'),
                'overlap': 'independent', 'currency': currency, 'provenance': deepcopy(provenance)}
            derived['rows'].append(row)
        return derived
    primary = budget_sizing(mapped())
    sensitivities = _records(document.get('sensitivities', []), 'sensitivities')
    separate = []
    for sensitivity in sensitivities:
        basis = sensitivity.get('price_basis')
        require(basis in BASES - {'unknown'}, 'EXPLICIT_SENSITIVITY_REFERENCE_BASIS_REQUIRED')
        if basis == 'other':
            require(isinstance(sensitivity.get('price_reference_description'), str)
                    and bool(sensitivity['price_reference_description'].strip()),
                    'SENSITIVITY_REFERENCE_DESCRIPTION_REQUIRED')
        separate.append({'id': sensitivity['id'], 'basis_assumption': deepcopy(sensitivity),
                         'scope': 'unknown_source_price_bases_only',
                         'status_label': 'CONDITIONAL_REFERENCE_BASIS_SENSITIVITY',
                         'result': budget_sizing(mapped(sensitivity))})
    return _finish(document, 'source-bound-cash-budget-sizing',
                   status=primary['status'], primary_result=primary, sensitivities=separate,
                   cost_source={'retained_document': retained, 'bytes_sha256': source['sha256'],
                                'canonical_sha256': digest(retained), 'role': source['role'],
                                'provenance': deepcopy(source['provenance']), 'bindings': deepcopy(bindings),
                                'cost_assumptions': assumptions, 'currency': currency},
                   selected_row_ids=[r['id'] for r in rows],
                   cost_mapping={'fee_per_trade': 'per_order entry fee times explicit entry_orders',
                                 'one_way_slippage_bps': 'one-way entry bps_notional; independent of per-trade fee',
                                 'quoted_full_spread': 'observation only; never added as another charge'},
                   limitation='All rows retain both supplied cost components. Unknown price basis does not become last; named sensitivities do not replace the unresolved primary result. No selection, weights, budget or broker capability is changed.')


def _budget_sizing(document):
    mode = document.get('mode')
    require(mode in {'portfolio', 'alternatives'}, 'PORTFOLIO_OR_ALTERNATIVES_MODE_REQUIRED')
    budget = _number(document.get('budget'), 'budget')
    rows = _records(document.get('rows'), 'rows')
    scenarios = _records(document.get('quantity_scenarios'), 'quantity_scenarios')
    require(bool(rows) and bool(scenarios), 'EXPLICIT_ROWS_AND_QUANTITY_SCENARIOS_REQUIRED')
    row_budgets = []
    for row in rows:
        supplied = _number(row.get('budget'), 'row.budget')
        if mode == 'alternatives':
            require(supplied is None or budget is None or supplied == budget, 'ALTERNATIVE_BUDGET_CONFLICT')
            row_budgets.append(budget)
        else:
            row_budgets.append(supplied)
    allocated = sum((b for b in row_budgets if b is not None), ZERO)
    if mode == 'portfolio' and budget is not None:
        require(allocated <= budget, 'ROW_BUDGET_SUM_EXCEEDS_PORTFOLIO_BUDGET')
    result_scenarios = []
    for scenario in scenarios:
        basis = scenario.get('quantity_basis')
        require(basis in {None, 'whole_shares', 'fractional_shares'}, 'INVALID_QUANTITY_BASIS')
        step = _number(scenario.get('quantity_step'), 'quantity_step', '0.000000000001')
        if step is not None and basis == 'whole_shares':
            require(step == step.to_integral_value(), 'WHOLE_SHARE_INCREMENT_MUST_BE_INTEGER')
        results = []
        for row, row_budget in zip(rows, row_budgets):
            friction = _friction({**row, 'currency': document['currency']})
            unknowns = list(friction['unresolved'])
            price = _number(row.get('price'), 'price', '0.000000000001')
            for missing, code in ((budget is None, 'TOTAL_BUDGET_UNKNOWN'),
                                  (row_budget is None, 'ROW_BUDGET_UNKNOWN'),
                                  (price is None, 'PRICE_UNKNOWN'),
                                  (step is None, 'QUANTITY_INCREMENT_UNKNOWN'),
                                  (basis is None, 'QUANTITY_BASIS_UNKNOWN')):
                if missing:
                    unknowns.append(code)
            if row.get('currency', document['currency']) != document['currency']:
                unknowns.append('ROW_CURRENCY_MISMATCH')
            orders = row.get('entry_orders')
            require(orders is None or (type(orders) is int and orders >= 1), 'INVALID_ENTRY_ORDER_COUNT')
            if orders is None and friction['applied_costs'] is not None and any(
                    c['unit'] == 'per_order' and c['phase'] in {'entry', 'each_side'}
                    for c in friction['applied_costs']):
                unknowns.append('ENTRY_ORDER_COUNT_UNKNOWN')
            result = {'id': row['id'], 'symbol': row.get('symbol'), 'requested_cash_budget': row_budget,
                      'price': price, 'quantity_basis': basis, 'quantity_step': step,
                      'friction_context': friction, 'provenance': deepcopy(row.get('provenance')),
                      'period': deepcopy(row.get('period')), 'unresolved': unknowns,
                      'status': 'INPUTS_UNRESOLVED' if unknowns else 'COMPUTED',
                      'quantity': None, 'gross_notional': None, 'modeled_entry_cost': None,
                      'modeled_cash_debit': None, 'budget_remainder': None}
            if not unknowns:
                call = {'currency': document['currency'], 'role': document['role'], 'side': 'buy',
                        'price': str(price), 'quantity': '0', 'entry_orders': orders,
                        'costs': friction['applied_costs'], 'budget': str(row_budget), 'quantity_step': str(step)}
                sized = planning_alignment.trade_costs(call)
                # Quote the helper's quantity with the same costs. No second
                # sizing algorithm or reconstructed fee arithmetic lives here.
                call['quantity'] = sized['max_affordable_quantity']
                quote = planning_alignment.trade_costs(call)
                result.update(quantity=quote['quantity'], gross_notional=quote['gross_notional'],
                              modeled_entry_cost=quote['entry_cost'], modeled_cash_debit=quote['entry_cash_debit'],
                              budget_remainder=quote['budget_remainder'], trade_cost_result=quote)
            results.append(result)
        computed = all(r['status'] == 'COMPUTED' for r in results)
        totals = None
        if mode == 'portfolio':
            debit = sum((Decimal(r['modeled_cash_debit']) for r in results), ZERO) if computed else None
            totals = {'gross_notional': sum((Decimal(r['gross_notional']) for r in results), ZERO) if computed else None,
                      'modeled_entry_cost': sum((Decimal(r['modeled_entry_cost']) for r in results), ZERO) if computed else None,
                      'modeled_cash_debit': debit, 'budget_remainder': budget - debit if debit is not None else None,
                      'allocated_row_budgets': allocated if all(b is not None for b in row_budgets) else None,
                      'unassigned_cash_budget': budget - allocated if budget is not None and all(b is not None for b in row_budgets) else None}
        result_scenarios.append({'id': scenario['id'], 'quantity_basis': basis, 'quantity_step': step,
                                 'status': 'COMPUTED' if computed else 'INPUTS_UNRESOLVED',
                                 'rows': results, 'portfolio_totals': totals})
    for index, scenario in enumerate(result_scenarios):
        path = f'/scenarios/{index}'
        for position, row in enumerate(scenario['rows']):
            row_path = path + f'/rows/{position}'
            row['conclusion_facts'] = _sizing_conclusion_facts(
                row, row['requested_cash_budget'], row_path, row_path + '/requested_cash_budget',
                document['currency'], scenario['id'],
                'mutually_exclusive_alternative' if mode == 'alternatives' else 'portfolio_row_cash_envelope')
        if scenario['portfolio_totals'] is not None:
            totals = scenario['portfolio_totals']
            totals['conclusion_facts'] = _sizing_conclusion_facts(
                totals, budget, path + '/portfolio_totals', '/requested_cash_budget',
                document['currency'], scenario['id'], 'combined_portfolio')
    return _finish(document, 'explicit-budget-sizing', mode=mode, requested_cash_budget=budget,
                   status='COMPUTED' if all(s['status'] == 'COMPUTED' for s in result_scenarios) else 'INPUTS_UNRESOLVED',
                   scenarios=result_scenarios, alternatives_are_mutually_exclusive=mode == 'alternatives',
                   alternatives_must_not_be_summed=mode == 'alternatives',
                   limitation='Supplied long-buy cash budgets and modeled costs only; quantity increments are assumptions, not broker capabilities.')


def _sizing_conclusion_facts(values, budget, path, budget_pointer, currency, scenario_id, scope):
    """Project completed sizing values; do not infer cash from exposure context."""
    facts = {'requested_cash_budget': {'value': budget, 'unit': 'currency_amount',
                                      'result_pointer': budget_pointer}}
    for key in ('gross_notional', 'modeled_entry_cost', 'modeled_cash_debit', 'budget_remainder'):
        facts[key] = {'value': values[key], 'unit': 'currency_amount', 'result_pointer': path + '/' + key}
    complete = all(fact['value'] is not None for fact in facts.values())
    residual = None
    if complete:
        numbers = {key: Decimal(str(fact['value'])) for key, fact in facts.items()}
        residual = numbers['requested_cash_budget'] - numbers['gross_notional'] - numbers['modeled_entry_cost'] - numbers['budget_remainder']
    return {'scope': scope, 'scenario_id': scenario_id, 'currency': currency,
            'pointer_scope': 'Pointers are relative to this helper result, not its wrapper or another scenario.',
            'facts': facts, 'budget_reconciliation_residual': residual,
            'reconciliation_status': 'INPUTS_UNRESOLVED' if not complete else 'RECONCILED' if residual == ZERO else 'MISMATCH',
            'identity': 'requested_cash_budget = gross_notional + modeled_entry_cost + budget_remainder',
            'interpretation': 'Gross notional is the modeled position exposure. Entry costs are not invested exposure. Budget remainder is unspent cash within this cash envelope; it is not embedded fund cash or a statement about the whole account.',
            'comparison_scope': 'Alternative rows and quantity scenarios are mutually exclusive. A portfolio row is only its own cash envelope; combined totals include unassigned budget cash.',
            'investment_dominance_established': False,
            'limitation': 'These are fixed-input modeled amounts, not executed fills, broker capabilities, a future-value forecast or evidence that one investment is superior.'}


def _label(value):
    if value is None or (isinstance(value, str) and value.casefold() == 'unknown'):
        return None
    return _id(value, 'classification')


def _dollar_volume(row, notional, currency):
    observation = row.get('dollar_volume')
    unknowns = []
    ratio = None
    if observation is None:
        unknowns.append('DOLLAR_VOLUME_NOT_SUPPLIED')
    else:
        require(isinstance(observation, dict), 'DOLLAR_VOLUME_OBJECT_REQUIRED')
        value = _number(observation.get('amount'), 'dollar_volume.amount')
        if observation.get('currency') is None:
            unknowns.append('DOLLAR_VOLUME_CURRENCY_UNKNOWN')
        elif observation['currency'] != currency:
            unknowns.append('DOLLAR_VOLUME_CURRENCY_MISMATCH_NO_FX_MODEL')
        if observation.get('unit') not in {'currency_per_day', 'currency_per_session', 'currency_over_period'}:
            unknowns.append('DOLLAR_VOLUME_UNIT_UNKNOWN_OR_NOT_MONETARY')
        if value is None:
            unknowns.append('DOLLAR_VOLUME_AMOUNT_UNKNOWN')
        elif value == 0:
            unknowns.append('ZERO_DOLLAR_VOLUME_RATIO_UNDEFINED')
        if notional is None:
            unknowns.append('GROSS_NOTIONAL_UNKNOWN')
        if not unknowns:
            ratio = notional / value
    return {'observation': deepcopy(observation), 'notional_to_supplied_dollar_volume': ratio,
            'ratio_unit': ('days' if observation['unit'] == 'currency_per_day' else
                           'sessions' if observation['unit'] == 'currency_per_session' else
                           'fraction_of_period_volume') if ratio is not None else None,
            'period_known': bool(observation and observation.get('period') is not None),
            'provenance_known': bool(observation and observation.get('provenance') is not None),
            'status': 'COMPUTED' if ratio is not None else 'INPUTS_UNRESOLVED',
            'unresolved': unknowns, 'feasible_participation_rate': None,
            'source_freshness_verified': False}


def allocation_context(document):
    """Aggregate supplied long notionals without changing their account denominator.

    Industry/issuer/sector labels and recursive fund weights are supplied source
    facts. Missing exposure and source coverage remain separate from known cash.
    """
    _header(document)
    with localcontext(Context(prec=_precision(document))):
        return _allocation_context(document)


def _allocation_context(document):
    denominator = document.get('denominator')
    require(denominator is None or isinstance(denominator, dict), 'DENOMINATOR_OBJECT_REQUIRED')
    denominator = denominator or {}
    declared = _number(denominator.get('amount'), 'denominator.amount', '0.000000000001')
    denominator_unknowns = []
    if declared is None:
        denominator_unknowns.append('DENOMINATOR_AMOUNT_UNKNOWN')
    basis = denominator.get('basis')
    if basis is None or (isinstance(basis, str) and
                         (not basis.strip() or basis.strip().casefold() == 'unknown')):
        denominator_unknowns.append('DENOMINATOR_BASIS_UNKNOWN')
    else:
        _id(basis, 'denominator.basis')
    if denominator.get('currency', document['currency']) != document['currency']:
        denominator_unknowns.append('DENOMINATOR_CURRENCY_MISMATCH')
    divisor = declared if not denominator_unknowns else None
    rows = _records(document.get('rows'), 'rows')
    exposures = {key: {'groups': {}, 'unknown_notional': ZERO, 'non_applicable_cash_notional': ZERO,
                       'unknown_contributors': []} for key in DIMENSIONS}
    coverage, output_rows, unquantified = [], [], []
    known_total = ZERO
    fund_total, fund_leaf, fund_cash, fund_unknown = ZERO, ZERO, ZERO, ZERO

    def frac(value):
        return value / divisor if divisor is not None else None

    def source(record, path, value, ancestors):
        return {'path': path, 'notional': value, 'period': deepcopy(record.get('period')),
                'provenance': deepcopy(record.get('provenance')),
                'classification_provenance': deepcopy(record.get('classification_provenance')),
                'lookthrough_source_chain': deepcopy(ancestors)}

    def leaf(record, value, path, ancestors, kind):
        item = source(record, path, value, ancestors)
        for dimension in DIMENSIONS:
            target = exposures[dimension]
            label = _label(record.get(dimension)) if kind not in {'unknown', 'fund'} else None
            if kind == 'cash':
                target['non_applicable_cash_notional'] += value
            elif label is None:
                target['unknown_notional'] += value
                target['unknown_contributors'].append(deepcopy(item))
            else:
                group = target['groups'].setdefault(label, {'notional': ZERO, 'contributors': []})
                group['notional'] += value
                group['contributors'].append(deepcopy(item))

    def expand(record, value, path, ancestors):
        kind = record.get('instrument_type') or 'unknown'
        require(kind in TYPES, 'INVALID_INSTRUMENT_TYPE')
        if kind != 'fund':
            leaf(record, value, path, ancestors, kind)
            if kind == 'unknown':
                return ZERO, ZERO, value
            return (ZERO, value, ZERO) if kind == 'cash' else (value, ZERO, ZERO)
        holdings = record.get('lookthrough')
        require(holdings is None or isinstance(holdings, dict), 'LOOKTHROUGH_OBJECT_REQUIRED')
        if holdings is None or holdings.get('constituents') is None:
            leaf(record, value, path, ancestors, 'fund')
            coverage.append({'path': path, 'fund_notional': value, 'supplied_constituent_weight': None,
                             'uncovered_notional': value, 'terminal_nonfund_notional': ZERO,
                             'embedded_cash_notional': ZERO, 'opaque_fund_notional': value,
                             'source': deepcopy(holdings), 'unresolved': ['FUND_CONSTITUENTS_UNKNOWN']})
            return ZERO, ZERO, value
        constituents = _records(holdings['constituents'], 'constituents')
        weights = [_number(c.get('weight'), 'constituent.weight') for c in constituents]
        require(all(w is None or w <= 1 for w in weights), 'CONSTITUENT_WEIGHT_EXCEEDS_ONE')
        supplied = sum((w for w in weights if w is not None), ZERO)
        require(supplied <= 1, 'FUND_CONSTITUENT_WEIGHTS_EXCEED_ONE')
        residual = value * (1 - supplied)
        leaves, cash, opaque = ZERO, ZERO, residual
        chain = ancestors + [{'path': path, 'period': deepcopy(holdings.get('period')),
                              'provenance': deepcopy(holdings.get('provenance'))}]
        for constituent, weight in zip(constituents, weights):
            if weight is not None:
                add = expand(constituent, value * weight, path + [constituent['id']], chain)
                leaves += add[0]; cash += add[1]; opaque += add[2]
        if residual:
            leaf({'period': holdings.get('period'), 'provenance': holdings.get('provenance')},
                 residual, path + ['uncovered_weight'], chain, 'unknown')
        unknown_weights = [c['id'] for c, w in zip(constituents, weights) if w is None]
        coverage.append({'path': path, 'fund_notional': value, 'supplied_constituent_weight': supplied,
                         'uncovered_notional': residual, 'terminal_nonfund_notional': leaves,
                         'embedded_cash_notional': cash, 'opaque_fund_notional': opaque,
                         'source': {'period': deepcopy(holdings.get('period')), 'provenance': deepcopy(holdings.get('provenance'))},
                         'unknown_weight_constituent_ids': unknown_weights,
                         'unresolved': ['CONSTITUENT_WEIGHTS_UNKNOWN'] if unknown_weights else []})
        return leaves, cash, opaque

    for row in rows:
        value = _number(row.get('notional'), 'row.notional')
        unknowns = []
        if value is None:
            unknowns.append('NOTIONAL_UNKNOWN')
        if row.get('notional_basis') != 'gross_notional':
            unknowns.append('GROSS_NOTIONAL_BASIS_NOT_ESTABLISHED')
        if row.get('currency', document['currency']) != document['currency']:
            unknowns.append('ROW_CURRENCY_MISMATCH_NO_FX_MODEL')
        kind = row.get('instrument_type') or 'unknown'
        require(kind in TYPES, 'INVALID_INSTRUMENT_TYPE')
        usable = value if not unknowns else None
        if usable is None:
            unquantified.append({'id': row['id'], 'unresolved': unknowns})
        else:
            known_total += usable
            notional_source = [{'path': [row['id']], 'source_role': 'top_level_notional',
                                'period': deepcopy(row.get('period')), 'provenance': deepcopy(row.get('provenance'))}]
            leaf_value, cash_value, unknown_value = expand(row, usable, [row['id']], notional_source)
            if kind == 'fund':
                fund_total += usable; fund_leaf += leaf_value; fund_cash += cash_value; fund_unknown += unknown_value
        output_rows.append({'id': row['id'], 'symbol': row.get('symbol'), 'gross_notional': usable,
                            'fraction_of_denominator': frac(usable) if usable is not None else None,
                            'instrument_type': kind, 'period': deepcopy(row.get('period')),
                            'provenance': deepcopy(row.get('provenance')), 'unresolved': unknowns,
                            'dollar_volume_context': _dollar_volume(row, usable, document['currency'])})
    for dimension, target in exposures.items():
        target['groups'] = dict(sorted(target['groups'].items()))
        classified = sum((g['notional'] for g in target['groups'].values()), ZERO)
        for group in target['groups'].values():
            group['fraction_of_denominator'] = frac(group['notional'])
        target.update(classified_notional=classified, unknown_fraction_of_denominator=frac(target['unknown_notional']),
                      non_applicable_cash_fraction_of_denominator=frac(target['non_applicable_cash_notional']),
                      unquantified_row_ids=[r['id'] for r in unquantified],
                      conservation_residual=known_total - classified - target['unknown_notional'] - target['non_applicable_cash_notional'])
    unquantified_funds = [r['id'] for r in rows if r.get('instrument_type') == 'fund'
                         and r['id'] in {u['id'] for u in unquantified}]
    unknown_weight_paths = [r['path'] for r in coverage if r.get('unknown_weight_constituent_ids')]
    fund_coverage_resolved = not unquantified_funds and not unknown_weight_paths
    issuer_exposure = exposures['issuer_id']
    known_issuer_ids = sorted(label for label, group in issuer_exposure['groups'].items()
                              if group['notional'] > ZERO)
    unresolved_issuer_weights = [r['path'] for r in coverage
                                 if r.get('unknown_weight_constituent_ids') and r['fund_notional'] > ZERO]
    issuer_count_complete = not (issuer_exposure['unknown_notional'] or unquantified or
                                unresolved_issuer_weights)
    issuer_summary = {
        'distinct_known_issuer_ids': known_issuer_ids,
        'distinct_known_issuer_count': len(known_issuer_ids),
        'total_distinct_issuer_count': len(known_issuer_ids) if issuer_count_complete else None,
        'count_status': 'COMPLETE_WITHIN_SUPPLIED_ROWS' if issuer_count_complete else 'KNOWN_LOWER_BOUND_ONLY',
        'known_issuer_notional': issuer_exposure['classified_notional'],
        'unknown_issuer_notional': issuer_exposure['unknown_notional'],
        'non_applicable_cash_notional': issuer_exposure['non_applicable_cash_notional'],
        'unquantified_row_ids': [row['id'] for row in unquantified],
        'unknown_weight_fund_paths': unresolved_issuer_weights,
        'count_scope': 'Distinct supplied terminal issuer labels with positive gross notional; repeated share classes merge. Cash, fund wrappers and zero exposure do not add issuers. Unknown exposure can overlap known issuers or contain additional issuers.',
        'correlation_established': False,
        'risk_or_diversification_ranking_established': False,
        'limitation': 'Counts describe supplied identities and exposure coverage only. They do not establish return correlation, independence, risk reduction, diversification quality, source truth or coverage beyond supplied rows.'}
    conclusion_facts = {
        'scope': 'supplied_allocation_rows_and_original_denominator',
        'currency': document['currency'],
        'pointer_scope': 'Pointers are relative to this helper result, not its source adapter wrapper.',
        'facts': {key: {'value': issuer_summary[key], 'unit': unit,
                        'result_pointer': '/issuer_identity_summary/' + key}
                  for key, unit in (
                      ('distinct_known_issuer_count', 'count'), ('total_distinct_issuer_count', 'count'),
                      ('count_status', 'status'), ('known_issuer_notional', 'currency_amount'),
                      ('unknown_issuer_notional', 'currency_amount'),
                      ('non_applicable_cash_notional', 'currency_amount'))},
        'denominator': {'observation': deepcopy(document.get('denominator')),
                        'result_pointer': '/denominator/observation', 'unresolved': denominator_unknowns},
        'outside_cash': None, 'entry_cost': None,
        'cash_limitation': 'Allocation context does not establish entry costs or outside cash. The denominator difference is not cash. Embedded and explicit cash in supplied rows are separate from unspent sizing budget.',
        'count_interpretation': 'Known count describes only mapped positive terminal issuer labels. An unknown total cannot be replaced with the known lower bound. More known labels or fuller disclosure do not establish broader actual diversification than another portfolio.',
        'comparative_diversification_established': False, 'relative_risk_established': False,
        'correlation_established': False, 'investment_dominance_established': False,
        'limitation': 'No comparative investment conclusion follows from these identity and coverage facts alone.'}
    conclusion_facts['facts']['known_gross_notional'] = {
        'value': known_total, 'unit': 'currency_amount', 'result_pointer': '/known_gross_notional'}
    conclusion_facts['facts']['total_gross_notional'] = {
        'value': None if unquantified else known_total, 'unit': 'currency_amount',
        'result_pointer': '/total_gross_notional'}
    return _finish(document, 'source-bound-allocation-context',
                   status='PARTIAL_CONTEXT' if denominator_unknowns or unquantified or not fund_coverage_resolved or any(
                       e['unknown_notional'] for e in exposures.values()) else 'COMPUTED_CONTEXT',
                   denominator={'observation': deepcopy(document.get('denominator')), 'unresolved': denominator_unknowns},
                   rows=output_rows, exposures=exposures, issuer_identity_summary=issuer_summary,
                   conclusion_facts=conclusion_facts,
                   known_gross_notional=known_total,
                   total_gross_notional=None if unquantified else known_total,
                   unquantified_rows=unquantified,
                   denominator_difference=declared - known_total if divisor is not None and not unquantified else None,
                   denominator_difference_is_cash=False,
                   fund_lookthrough={'known_top_level_fund_notional': fund_total,
                                     'terminal_nonfund_notional': fund_leaf, 'embedded_cash_notional': fund_cash,
                                     'opaque_or_uncovered_fund_notional': fund_unknown,
                                     'terminal_coverage_fraction': (fund_leaf + fund_cash) / fund_total if fund_total and fund_coverage_resolved else None,
                                     'coverage_status': 'INPUTS_UNRESOLVED' if not fund_coverage_resolved else
                                                        'NO_KNOWN_FUND_NOTIONAL' if not fund_total else
                                                        'PARTIAL' if fund_unknown else 'COMPLETE_SUPPLIED_WEIGHTS',
                                     'unquantified_fund_row_ids': unquantified_funds,
                                     'unknown_weight_fund_paths': unknown_weight_paths,
                                     'fund_records': coverage,
                                     'conservation_residual': fund_total - fund_leaf - fund_cash - fund_unknown},
                   limitation='Declared long notionals, classifications and fund weights only. No denominator renormalization, source freshness inference, liquidity cutoff or feasible participation estimate.')
