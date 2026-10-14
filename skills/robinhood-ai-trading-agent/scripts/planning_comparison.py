"""Source-bound alternatives and date-only settlement/transfer scenarios."""
from copy import deepcopy
from datetime import date
from decimal import Context, Decimal, localcontext
from itertools import combinations
import re

from planning_alignment import amount, finish
from quant_common import require


DIMENSIONS = ('metric', 'unit', 'basis')


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
    return finish(document, 'planning-settlement-transfer-sweep', status='DATE_PATHS_MODELED',
                  sale_dates=results, sale_date_summaries=summaries, reference_path=reference,
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
