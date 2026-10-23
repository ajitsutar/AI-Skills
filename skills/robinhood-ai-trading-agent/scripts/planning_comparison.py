"""Source-bound alternatives and date-only settlement/transfer scenarios."""
from copy import deepcopy
from datetime import date
from decimal import Context, Decimal, localcontext
from itertools import combinations
import re

from planning_alignment import amount, finish
from quant_common import require


DIMENSIONS = ('metric', 'unit', 'basis')


def _allocation_direction_comparisons(rows):
    """Compare each target distance to an explicit peer, never an implicit baseline.

    Called only on source_alternatives' common projection convention. Different
    post-flow equity amounts are valid denominators; unidentified equity is not.
    Identified-assets sensitivities never substitute for primary weights.
    """
    facts, pairs = [], []
    for index, row in enumerate(rows):
        for ai, allocation in enumerate(row['allocations']):
            pointer = f'/alternatives/{index}/allocations/{ai}'
            drift = allocation['target_drift']
            drift = amount(drift) if drift is not None else None
            facts.append({'alternative_id': row['id'], 'asset_id': allocation['asset_id'],
                          'result_pointer': pointer, 'target_date': row['target_date'],
                          'denominator_pointer': f'/alternatives/{index}/denominator',
                          'denominator_basis': row['denominator_basis'],
                          'signed_drift': drift,
                          'absolute_drift': abs(drift) if drift is not None else None,
                          'position_relative_to_target': None if drift is None else
                              'BELOW_TARGET' if drift < 0 else 'ABOVE_TARGET' if drift > 0 else 'AT_TARGET'})
    for (li, left), (ri, right) in combinations(enumerate(rows), 2):
        lm = {a['asset_id']: (i, a) for i, a in enumerate(left['allocations'])}
        rm = {a['asset_id']: (i, a) for i, a in enumerate(right['allocations'])}
        for asset in dict.fromkeys(list(lm) + list(rm)):
            unknown, mismatch = [], []
            operands = []
            for index, row, mapping in ((li, left, lm), (ri, right, rm)):
                ai, allocation = mapping.get(asset, (None, {}))
                operands.append({'alternative_id': row['id'],
                                 'allocation_pointer': None if ai is None else f'/alternatives/{index}/allocations/{ai}',
                                 'denominator_pointer': f'/alternatives/{index}/denominator',
                                 'denominator': row['denominator'],
                                 'target_date': row['target_date'],
                                 'denominator_basis': row['denominator_basis'],
                                 'target_weight': allocation.get('target_weight'),
                                 'actual_weight': allocation.get('post_flow_weight'),
                                 'signed_drift': allocation.get('target_drift')})
                for key in ('denominator', 'target_weight', 'actual_weight', 'signed_drift',
                            'target_date', 'denominator_basis'):
                    if operands[-1][key] is None or operands[-1][key] == '':
                        unknown.append(f'{row["id"]}:{key}')
                if row['denominator'] is not None and amount(row['denominator']) <= 0:
                    unknown.append(f'{row["id"]}:nonpositive_denominator')
            a, b = operands
            for key in ('target_date', 'denominator_basis', 'target_weight'):
                av, bv = a[key], b[key]
                if av is not None and bv is not None:
                    equal = amount(av) == amount(bv) if key == 'target_weight' else av == bv
                    if not equal:
                        mismatch.append(key)
            resolved = not unknown and not mismatch
            delta = abs(amount(a['signed_drift'])) - abs(amount(b['signed_drift'])) if resolved else None
            weight_delta = amount(a['actual_weight']) - amount(b['actual_weight']) if resolved else None
            pairs.append({'left_alternative_id': left['id'], 'right_alternative_id': right['id'],
                          'asset_id': asset, 'operands': operands,
                          'status': 'INCOMPARABLE' if mismatch else 'UNRESOLVED' if unknown else 'COMPUTED',
                          'unknown_dimensions': unknown, 'mismatched_dimensions': mismatch,
                          'absolute_drift_delta_left_minus_right': delta,
                          'weight_delta_left_minus_right': weight_delta,
                          'left_target_distance_relative_to_right': None if delta is None else
                              'CLOSER' if delta < 0 else 'FARTHER' if delta > 0 else 'EQUAL_DISTANCE',
                          'left_weight_relative_to_right': None if weight_delta is None else
                              'LOWER' if weight_delta < 0 else 'HIGHER' if weight_delta > 0 else 'EQUAL',
                          'unit': 'fraction_of_each_alternative_post_flow_net_equity'})
    return {'schema_version': 1, 'allocation_facts': facts, 'pairwise': pairs,
            'default_baseline_alternative': None, 'selected_alternative': None,
            'closest_alternative_rank_computed': False,
            'interpretation': 'CLOSER/FARTHER is relative only to the named right comparator for this asset. It is not movement from the opening portfolio, a closest-among-all rank, or an overall allocation improvement. Higher weight is separate from target distance.',
            'limitations': ['Primary post-flow net equity only; identified-assets sensitivities do not resolve unknown denominators.',
                           'Each operand preserves its own denominator; all alternatives share the source projection convention.',
                           'Exact Decimal distances are compared before display rounding; no preference or execution condition is inferred.']}


def _alternative_coverage_audit(document, rows):
    """Inventory declared trades and actually included samples, not viability.

    Quantities are native asset units. Matching quantities across assets are a
    sampling diagnostic, never equivalent proceeds, exposure, tax lots or risk.
    """
    def escape(value):
        return str(value).replace('~', '~0').replace('/', '~1')
    holdings = document['source'].get('baseline_rebalance', {}).get('holdings', {})
    held, unknown_held, zero = [], [], []
    for asset, value in holdings.items():
        (unknown_held if value is None else held if amount(value) > 0 else zero).append(asset)
    observations, samples, unknown_samples, alternative_samples = [], {}, [], []
    for ai, alternative in enumerate(document['alternatives']):
        audit = rows[ai]['projection_receipt']['projection'].get('flow_audit', [])
        by_id = {flow['id']: (index, flow) for index, flow in enumerate(audit)}
        totals = {}
        for fi, flow in enumerate(alternative.get('scenario_flows', [])):
            if flow.get('kind') != 'trade':
                continue
            trade = flow.get('trade') or {}
            asset, side, quantity = flow.get('asset_id'), trade.get('side'), trade.get('quantity')
            audit_index, evaluated = by_id.get(flow.get('id'), (None, {}))
            included = evaluated.get('included')
            observation = {'alternative_id': alternative['id'], 'flow_id': flow.get('id'),
                           'asset_id': asset, 'side': side, 'quantity': deepcopy(quantity),
                           'date': flow.get('date'), 'state': flow.get('state'),
                           'input_pointer': f'/retained_input/alternatives/{ai}/scenario_flows/{fi}',
                           'projection_audit_pointer': None if audit_index is None else
                               f'/alternatives/{ai}/projection_receipt/projection/flow_audit/{audit_index}',
                           'included_in_projection': included,
                           'exclusion_reasons': deepcopy(evaluated.get('exclusion_reasons')),
                           'lot_selection_established_by_audit': False}
            observations.append(observation)
            if side != 'sell' or included is not True:
                continue
            group = totals.setdefault(asset, {'asset_id': asset, 'known_quantity_sum': Decimal(0),
                                             'unknown_quantity': False, 'flow_pointers': []})
            group['flow_pointers'].append(observation['input_pointer'])
            if quantity is None:
                group['unknown_quantity'] = True
                unknown_samples.append(deepcopy(observation))
                continue
            value = amount(quantity)
            group['known_quantity_sum'] += value
            if value > 0:
                samples.setdefault(asset, {}).setdefault(value, []).append(deepcopy(observation))
        for group in totals.values():
            alternative_samples.append({'alternative_id': alternative['id'], **group,
                                        'total_sale_quantity': None if group['unknown_quantity'] else group['known_quantity_sum'],
                                        'basis': 'Sum of included sell quantities for this asset in this alternative; buys are not netted.'})
    sampled_assets = list(samples)
    quantity_groups = []
    quantities = sorted({quantity for values in samples.values() for quantity in values})
    for quantity in quantities:
        represented = [asset for asset in held if quantity in samples.get(asset, {})]
        if not represented:
            continue
        missing = [asset for asset in held if asset not in represented]
        quantity_groups.append({'quantity': quantity, 'sampled_source_held_asset_ids': represented,
                                'quantity_scope': 'Individual included sell flow, not an aggregate or equivalent-cash lot.',
                                'source_held_asset_ids_without_this_known_sample': missing,
                                'sampled_for_strict_subset_of_known_held_assets': bool(missing),
                                'observation_pointers': [item['input_pointer'] for asset in represented
                                                         for item in samples[asset][quantity]],
                                'economic_equivalence_established': False})
    return {'schema_version': 1,
            'source_held_universe': [{'asset_id': asset, 'opening_quantity': deepcopy(value),
                                      'source_pointer': '/retained_input/source/baseline_rebalance/holdings/' + escape(asset)}
                                     for asset, value in holdings.items()],
            'known_positive_held_asset_ids': held, 'unknown_opening_quantity_asset_ids': unknown_held,
            'zero_opening_quantity_asset_ids': zero,
            'omitted_held_asset_ids': [asset for asset in held if asset not in sampled_assets],
            'omission_meaning': 'No positive known included sale-quantity sample; declared unknown/excluded sales remain in observations.',
            'sampled_assets_outside_known_positive_opening_holdings': [asset for asset in sampled_assets if asset not in held],
            'trade_observations': observations, 'unknown_quantity_sale_samples': unknown_samples,
            'known_positive_sale_quantities_by_asset': [
                {'asset_id': asset, 'quantities': sorted(values),
                 'quantity_scope': 'Individual included sell flows in native asset units'} for asset, values in samples.items()],
            'per_alternative_asset_sale_totals': alternative_samples,
            'sale_quantity_sample_groups': quantity_groups,
            'asymmetric_known_quantity_samples': any(group['sampled_for_strict_subset_of_known_held_assets'] for group in quantity_groups),
            'full_asset_quantity_search_established': False,
            'exclusive_feasible_funder_claim_supported': False,
            'limitations': ['Observed samples only; omitted assets or quantities are not infeasible or rejected.',
                           'Buys, zero sales, excluded flows and unknown quantities do not establish a positive known sale sample.',
                           'Native asset quantities are not comparable dollar proceeds; share classes and asset IDs are not merged.',
                           'A multi-trade alternative is a combined scenario, not evidence each sale independently funds the goal.',
                           'This audit does not validate lot selection, tax treatment, liquidity, timing, funding adequacy or feasibility.',
                           'Even symmetric samples do not establish exhaustive quantity coverage or a uniquely feasible funder.']}


def _source_context_evidence_inventory(source):
    """Retain explicit source fields without promoting assumptions to live quotes."""
    def escape(value):
        return str(value).replace('~', '~0').replace('/', '~1')
    def field(parent, key, base, role):
        present = isinstance(parent, dict) and key in parent
        value = parent[key] if present else None
        pointer = base + '/' + escape(key)
        return {'field': key, 'state': 'ABSENT' if not present else
                    'SUPPLIED_NULL' if value is None else 'SUPPLIED_VALUE',
                'value': deepcopy(value), 'source_pointer': pointer if present else None,
                'inspected_pointer': pointer, 'evidence_role': role,
                'current_executable_terms_established': False}
    root = '/retained_input/source'
    baseline = source.get('baseline_rebalance')
    baseline_fields = [{**field(baseline, key, root + '/baseline_rebalance',
                               'supplied_baseline_configuration_or_state'),
                        'owning_scope_pointer': root + '/baseline_rebalance',
                        'task_applicability': 'NOT_ESTABLISHED_BY_SOURCE_RECORD',
                        'user_authorization_inferred': False,
                        'broker_requirement_inferred': False}
                       for key in baseline] if isinstance(baseline, dict) else []
    prices = baseline.get('prices') if isinstance(baseline, dict) else None
    holdings = baseline.get('holdings') if isinstance(baseline, dict) else None
    price_keys = list(prices) if isinstance(prices, dict) else []
    if isinstance(holdings, dict):
        price_keys = list(dict.fromkeys(list(holdings) + price_keys))
    price_rows = [field(prices, asset, root + '/baseline_rebalance/prices',
                        'supplied_analytical_mark') for asset in price_keys]
    costs = source.get('cost_assumptions')
    cost_keys = list(dict.fromkeys(['fee_per_trade', 'one_way_slippage_bps'] +
                                  (list(costs) if isinstance(costs, dict) else [])))
    cost_rows = [field(costs, name, root + '/cost_assumptions', 'supplied_cost_assumption')
                 for name in cost_keys]
    conventions = []
    convention_keys = {'opening_account', 'opening_convention', 'opening_conventions',
                       'opening_state', 'opening_state_convention'}
    def visit(value, pointer):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in convention_keys:
                    conventions.append(field(value, key, pointer, 'literal_opening_convention_uninterpreted'))
                else:
                    visit(child, pointer + '/' + escape(key))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, pointer + '/' + str(index))
    visit(source, root)
    return {'schema_version': 1,
            'scope': 'Supplied baseline_rebalance configuration/state, its literal source description, baseline prices, cost_assumptions and literal opening conventions; no inventory of all market, fee or task-authorization evidence.',
            'price_collection': field(baseline, 'prices', root + '/baseline_rebalance', 'supplied_analytical_marks'),
            'baseline_source_fields': baseline_fields,
            'baseline_source_description': field(source, 'baseline_source', root, 'literal_source_description'),
            'analytical_price_fields': price_rows,
            'cost_collection': field(source, 'cost_assumptions', root, 'supplied_cost_assumptions'),
            'cost_assumption_fields': cost_rows,
            'source_metadata': [field(source, key, root, 'source_document_metadata') for key in ('currency', 'as_of')],
            'opening_convention_fields': conventions,
            'opening_convention_field_names_inspected': sorted(convention_keys),
            'opening_conventions_interpreted': False,
            'supplied_analytical_price_asset_ids': [row['field'] for row in price_rows if row['state'] == 'SUPPLIED_VALUE'],
            'supplied_cost_assumption_field_names': [row['field'] for row in cost_rows if row['state'] == 'SUPPLIED_VALUE'],
            'current_executable_prices_verified': False, 'current_broker_fee_quotes_verified': False,
            'limitations': ['Supplied zero is a value; null is explicitly unknown and absent means only the inspected field is absent.',
                           'Baseline settings belong to their retained source scope; this inventory does not establish their applicability to the current task, infer user authorization or impose broker requirements.',
                           'An explicit user instruction remains authoritative separately; source configuration alone does not require an override. Source descriptions remain literal, with no automatic example classification.',
                           'Analytical marks and cost assumptions are supplied evidence, not authenticated current executable quotes or broker terms.',
                           'Source document currency and date are retained as metadata, not automatically assigned to individual quotes or treated as execution timestamps.',
                           'An absent nested field under a null or non-object collection does not establish absent evidence elsewhere; collection values remain retained.',
                           'Opening convention records are literal structured-key matches, not parsed instructions or assertions that scenarios share an opening state.',
                           'No supplied values are applied to calculations or used to invent missing marks, costs or opening-state reconciliations.']}


def source_alternatives(document):
    """Compare full dated ledgers on one supplied date/denominator convention.

    document has source_projection arguments plus alternatives[{id,scenario_flows}].
    Alternative-specific dates, marks, residual/liability policies or objectives
    are not allowed. Targets/identities/fund overlap come from the retained source.
    No issuer-maximization objective or preferred sale is constructed.
    """
    from portfolio_projection import source_projection, _precision
    with localcontext(Context(prec=64 + _precision(document))):
        alternatives = _rows(document.get('alternatives'), 'alternatives')
        source = document.get('source')
        require(isinstance(source, dict), 'SOURCE_OBJECT_REQUIRED')
        identities = {**source.get('identities', {}), **source.get('other_identity', {})}
        funds = {row['symbol']: row for row in source.get('funds', [])}
        targets = source.get('baseline_rebalance', {}).get('targets', {})
        employer_symbol = source.get('employer', {}).get('symbol')
        employer_id = identities.get(employer_symbol, {}).get('issuer_id')
        rows = []
        for alternative in alternatives:
            require(set(alternative) <= {'id', 'scenario_flows'}, 'ALTERNATIVE_MUST_SHARE_PROJECTION_BASIS')
            bound = {k: deepcopy(v) for k, v in document.items() if k != 'alternatives'}
            bound['scenario_flows'] = deepcopy(alternative.get('scenario_flows', []))
            receipt = source_projection(bound)
            projection = receipt['projection']
            values = {row['asset_id']: amount(row['market_value']) if row['market_value'] is not None else None
                      for row in projection['position_values']}
            equity = amount(projection['net_equity']) if projection['net_equity'] is not None else None
            identified = amount(projection['identified_assets']) if projection['identified_assets'] is not None else None
            def weight(value, denominator):
                return value / denominator if value is not None and denominator is not None and denominator > 0 else None
            allocations = []
            for asset in dict.fromkeys(list(values) + list(targets)):
                value = values.get(asset, Decimal(0))
                actual = weight(value, equity)
                target = amount(targets[asset]) if targets.get(asset) is not None else None
                sensitivity = weight(value, identified)
                allocations.append({'asset_id': asset, 'market_value': value, 'target_weight': target,
                                    'post_flow_weight': actual,
                                    'target_drift': actual - target if actual is not None and target is not None else None,
                                    'identified_assets_weight_sensitivity': sensitivity,
                                    'identified_assets_target_drift_sensitivity': sensitivity - target
                                    if sensitivity is not None and target is not None else None})
            exposure, unknown_overlap = Decimal(0), []
            if employer_id is None:
                unknown_overlap.append('employer_identity')
            for asset, value in values.items():
                if value == 0:
                    continue
                if value is None:
                    unknown_overlap.append(asset)
                    continue
                if asset in funds:
                    fund = funds[asset]
                    coverage = fund.get('holdings_coverage')
                    if coverage is None or amount(coverage) < 1:
                        unknown_overlap.append(asset)
                    for component in fund.get('holdings', []):
                        identity = identities.get(component.get('symbol'), {})
                        if identity.get('issuer_id') == employer_id and employer_id is not None:
                            exposure += value * amount(component['weight'])
                        elif not identity.get('issuer_id') and identity.get('kind') != 'cash':
                            unknown_overlap.append(component.get('symbol'))
                elif identities.get(asset, {}).get('issuer_id') == employer_id and employer_id is not None:
                    exposure += value
                elif not identities.get(asset, {}).get('issuer_id'):
                    unknown_overlap.append(asset)
            # The unclassified residual could contain employer exposure. Never
            # silently promote the known numerator to complete account exposure.
            if projection['other_assets_value'] is None or amount(projection['other_assets_value']) != 0:
                unknown_overlap.append('unclassified_other_assets')
            rows.append({'id': alternative['id'], 'target_date': projection['target_date'],
                         'denominator': equity, 'denominator_basis': 'same-target-date post-flow net equity',
                         'identified_assets_sensitivity_denominator': identified,
                         'allocations': allocations, 'cash': projection['cash'],
                         'tax_reserve': projection['tax_reserve'],
                         'known_employer_exposure': exposure,
                         'known_employer_fraction': weight(exposure, equity),
                         'identified_assets_employer_fraction_sensitivity': weight(exposure, identified),
                         'complete_employer_exposure': exposure if not unknown_overlap else None,
                         'unresolved_employer_overlap': list(dict.fromkeys(unknown_overlap)),
                         'projection_receipt': receipt})
        return finish(document, 'planning-source-alternatives', status='DATED_ALTERNATIVES_COMPARED',
                      alternatives=rows, selected_alternative=None, objective_weights=None,
                      allocation_direction_comparisons=_allocation_direction_comparisons(rows),
                      alternative_coverage_audit=_alternative_coverage_audit(document, rows),
                      source_context_evidence_inventory=_source_context_evidence_inventory(source),
                      proposal_contract={
                          'mode': 'PREFERENCE_FREE_CONDITIONAL_PROPOSAL',
                          'comparison_alternative_ids': [row['id'] for row in rows],
                          'default_preferred_funder': None,
                          'selected_alternative': None,
                          'input_order_is_priority': False,
                          'inferred_liquidity_tax_concentration_priority': False,
                          'self_chosen_objective_weights_allowed_as_default': False,
                          'conditional_proposal_without_favorite_is_valid': True,
                          'absent_explicit_user_priorities':
                              'Compare all viable funding alternatives and conditional priority branches; nominate no default favorite.',
                          'conditional_priority_branch_rule':
                              'Describe which supplied alternative facts matter if the user prioritizes a criterion, without assigning that priority to the user.',
                          'viability_rule':
                              'Use explicit separately computed funding, timing, lot and liquidity evidence; unknown viability is retained, not assumed or excluded.',
                          'supplied_preference_rule':
                              'Preserve explicit user criteria/priorities separately; this operation implements no preference optimizer or automatic selection.',
                          'execution_effect': 'Advisory proposal contract only; no order or execution prerequisite.'},
                      input_order_is_priority=False, retained_input=deepcopy(document),
                      limitations=['Target drift and employer fractions use each alternative post-flow equity on the shared target date.',
                                   'Identified-assets weights are labeled sensitivities, not complete-account weights.',
                                   'Known issuer exposure can be a lower bound; unclassified residuals remain unknown.',
                                   'No criterion direction, preference, tax law or uniquely optimal sale is inferred.'])


def settlement_transfer_sweep(document):
    """Enumerate every supplied sale date through the deadline, including earlier paths.

    Uses settlement_transfer_paths for each date; never chooses a priority/date.
    When source is supplied, business_dates are bound to its cash_conventions
    test_business_dates and cannot be narrowed by the caller.
    """
    bound = deepcopy(document)
    if document.get('source') is not None:
        source = document['source']
        require(isinstance(source, dict), 'SOURCE_OBJECT_REQUIRED')
        dates = source.get('cash_conventions', {}).get('test_business_dates')
        if 'business_dates' in document:
            require(document['business_dates'] == dates, 'SOURCE_CALENDAR_MUST_NOT_BE_NARROWED')
        bound['business_dates'] = deepcopy(dates)
    dates = bound.get('business_dates')
    require(isinstance(dates, list) and bool(dates), 'LISTED_BUSINESS_DATES_REQUIRED')
    parsed = [_day(value, 'business_dates') for value in dates]
    require(all(a < b for a, b in zip(parsed, parsed[1:])), 'STRICTLY_INCREASING_UNIQUE_BUSINESS_DATES')
    deadline = _day(document.get('spendable_deadline'), 'spendable_deadline')
    results = []
    for sale in dates:
        if _day(sale, 'business_dates') <= deadline:
            result = settlement_transfer_paths({**bound, 'sale_date': sale})
            results.append({'sale_date': sale, 'settlement_date': result['settlement_date'], 'paths': result['paths']})
    reference = None
    for result in results:
        path = next((path for path in result['paths'] if path['id'] == 'next_listed_day_initiation'
                     and path['date_relation_to_deadline'] == 'BEFORE_DEADLINE_DATE'
                     and path['status'] != 'EXCLUDED_BY_EXPLICIT_ASSUMPTION'), None)
        if path is not None:
            reference = {'sale_date': result['sale_date'], 'path': deepcopy(path),
                         'reference_only': True, 'selected': False,
                         'basis': 'Earliest supplied sale date with next-listed-day initiation and modeled arrival strictly before deadline.',
                         'same_day_acceptance_assumed': False,
                         'description': 'Conditional date-accounting example; no recommended trade date, available-cash claim or arrival guarantee.'}
            break
    summaries = []
    for result in results:
        uncovered = [bool(path['missing_calendar_dates_for']) for path in result['paths']]
        summaries.append({'sale_date': result['sale_date'],
                          'calendar_uncovered_for_all_paths': all(uncovered),
                          'calendar_coverage_mixed': any(uncovered) and not all(uncovered),
                          'has_modeled_arrival_on_deadline': any(path['date_relation_to_deadline'] ==
                              'ON_DEADLINE_DATE_INTRADAY_UNRESOLVED' for path in result['paths']),
                          'status_for_entire_date': None,
                          'path_statuses': [{key: deepcopy(path[key]) for key in
                              ('id', 'status', 'settlement_date', 'transfer_initiation_date', 'arrival_date',
                               'date_relation_to_deadline', 'missing_calendar_dates_for', 'conditions')}
                              for path in result['paths']]})
    # Preserve the existential question (any modeled path) separately from a
    # selected example or a guarantee. Missing coverage is not impossibility.
    groups = {key: [] for key in ('before_deadline', 'on_deadline', 'after_deadline',
                                  'unresolved_calendar', 'excluded_by_assumption')}
    on_or_before_dates = []
    no_modeled_on_or_before_dates = []
    for index, result in enumerate(results):
        has_path = False
        for path_index, path in enumerate(result['paths']):
            if path['status'] == 'EXCLUDED_BY_EXPLICIT_ASSUMPTION':
                group = 'excluded_by_assumption'
            elif path['missing_calendar_dates_for']:
                group = 'unresolved_calendar'
            else:
                group = {'BEFORE_DEADLINE_DATE': 'before_deadline',
                         'ON_DEADLINE_DATE_INTRADAY_UNRESOLVED': 'on_deadline',
                         'AFTER_DEADLINE_DATE': 'after_deadline'}[path['date_relation_to_deadline']]
            groups[group].append({'sale_date': result['sale_date'], 'path_id': path['id'],
                                  'result_pointer': f'/sale_dates/{index}/paths/{path_index}'})
            has_path = has_path or group in {'before_deadline', 'on_deadline'}
        (on_or_before_dates if has_path else no_modeled_on_or_before_dates).append(result['sale_date'])
    timing_summary = {
        'basis': 'All supplied sale dates and all modeled initiation paths; explicit exclusions respected.',
        'paths_by_deadline_relation': groups,
        'sale_dates_with_any_conditional_arrival_on_or_before_deadline': on_or_before_dates,
        'sale_dates_without_modeled_arrival_on_or_before_deadline': no_modeled_on_or_before_dates,
        'no_modeled_arrival_means_impossible': False,
        'guaranteed_sale_dates': [],
        'selected_sale_date': None,
        'conditions_pointer': '/sale_dates',
        'limitations': ['An on-deadline date is conditional on intraday spendability, not excluded or guaranteed.',
                        'An earlier reference example does not exhaust the possible timing paths.',
                        'Missing calendar coverage does not prove an arrival is late or impossible.']}
    return finish(document, 'planning-settlement-transfer-sweep', status='DATE_PATHS_MODELED',
                  sale_dates=results, sale_date_summaries=summaries, reference_path=reference,
                  timing_summary=timing_summary,
                  selected_sale_date=None, calendar_extended=False,
                  guaranteed_spendable_by_deadline=False, retained_input=deepcopy(document),
                  limitations=['Every supplied sale date on/before the deadline is evaluated; earlier paths are retained.',
                               'Earlier conditional arrival is not a guarantee or an inferred user priority.',
                               'Same-day acceptance and deadline-time spendability remain explicitly conditional.',
                               'Coverage and acceptance are path-specific; mixed timing paths cannot be collapsed into a whole-sale-date status.'])


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
