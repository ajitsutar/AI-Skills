"""Same-entry-capital equity/cash counterfactual using existing local helpers."""
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib

from financial_alignment import price_scenarios
from planning_alignment import amount, cash_projection
from quant_common import digest, require, timestamp
from report_facts import pointer, strict_json


def equity_cash_comparison(document):
    """Compare one initial share's modeled outlay with hypothetical cash.

    Terminal prices without a source-bound matching timestamp and price bridge
    produce only a separately labeled conditional price sensitivity.
    """
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1,
            'COMPARISON_SCHEMA_1_REQUIRED')
    equity = deepcopy(document['equity_document'])
    cash = deepcopy(document['cash_document'])
    require(isinstance(equity.get('provenance'), dict) and equity['provenance'], 'EQUITY_PROVENANCE_REQUIRED')
    require(isinstance(cash.get('provenance'), dict) and cash['provenance'], 'CASH_PROVENANCE_REQUIRED')
    require(equity.get('role') in {'supplied_observation', 'hypothetical_scenario', 'user_assumption'},
            'EQUITY_ROLE_REQUIRED')
    require(cash.get('role') in {'supplied_observation', 'hypothetical_scenario', 'user_assumption'},
            'CASH_SOURCE_ROLE_REQUIRED')
    require(equity.get('currency') and equity['currency'] == cash.get('currency'), 'MATCHED_CURRENCIES_REQUIRED')
    require(equity.get('quantity') is None or amount(equity['quantity']) == 1, 'ONE_INITIAL_SHARE_CONTRACT_REQUIRED')
    require(timestamp(equity['entry_at']) == timestamp(cash['start_at'])
            and timestamp(equity['exit_at']) == timestamp(cash['end_at']), 'MATCHED_EXACT_INTERVAL_REQUIRED')
    calculated_equity = price_scenarios(equity)
    outlays = {r['entry_outlay_per_share'] for r in calculated_equity['scenarios']}
    require(len(outlays) == 1, 'SHARED_EQUITY_ENTRY_OUTLAY_REQUIRED')
    entry_cash = next(iter(outlays))
    require(amount(entry_cash) > 0, 'POSITIVE_ENTRY_CASH_REQUIRED')
    if cash.get('opening_cash') is not None:
        require(amount(cash['opening_cash']) == amount(entry_cash), 'SUPPLIED_CASH_PRINCIPAL_DIFFERS_FROM_EQUITY_OUTLAY')
    cash['opening_cash'] = entry_cash
    cash['role'] = 'hypothetical_scenario'
    cash['provenance'] = {**cash['provenance'],
        'opening_cash_basis': 'derived from financial_alignment.price_scenarios entry_outlay_per_share for one initial share',
        'source_declared_role': document['cash_document']['role'],
        'counterfactual_role': 'hypothetical_scenario'}
    cash_unknown = [name.upper() + '_UNKNOWN' for name in
                    ('annual_effective_rate', 'day_count', 'floor', 'events', 'fee') if cash.get(name) is None]
    if cash.get('day_count') not in {None, 'ACT/365F'}:
        cash_unknown.append('CASH_DAY_COUNT_UNSUPPORTED_BY_PROJECTION')
    fee = amount(cash['fee'], 'cash.fee', 0) if cash.get('fee') is not None else None
    if fee is not None and fee > 0 and cash.get('fee_at') is None:
        cash_unknown.append('CASH_FEE_TIME_UNKNOWN')
    if cash.get('events'):
        cash_unknown.append('EXTERNAL_CASH_FLOWS_PREVENT_SAME_CAPITAL_ENDPOINT_COMPARISON')
    calculated_cash = None
    if not cash_unknown:
        if fee > 0:
            at = timestamp(cash['fee_at'])
            require(timestamp(cash['start_at']) <= at <= timestamp(cash['end_at']), 'CASH_FEE_OUTSIDE_INTERVAL')
            cash['events'] = [{'id': 'declared-comparator-fee', 'at': cash['fee_at'],
                               'amount': str(-fee), 'kind': 'withdrawal', 'confirmed': True}]
        calculated_cash = cash_projection(cash)
        if calculated_cash['ending_cash'] is None:
            cash_unknown.append('CASH_PROJECTION_UNFUNDED')
    source_info = None
    retained_source = None
    if document.get('source_utf8') is not None:
        raw = document['source_utf8'].encode('utf-8')
        require(hashlib.sha256(raw).hexdigest() == document.get('source_sha256'), 'TERMINAL_SOURCE_BYTES_HASH_MISMATCH')
        require(document.get('source_ref') and document.get('source_role') in
                {'supplied_observation', 'hypothetical_scenario', 'user_assumption'}, 'TERMINAL_SOURCE_PROVENANCE_ROLE_REQUIRED')
        retained_source = strict_json(raw)
        source_info = {'ref': document['source_ref'], 'role': document['source_role'],
                       'bytes_sha256': document['source_sha256'], 'canonical_sha256': digest(retained_source)}
    time_binding = document.get('terminal_time_pointer')
    price_bindings = document.get('terminal_price_pointers', {})
    require(isinstance(price_bindings, dict), 'TERMINAL_PRICE_POINTERS_OBJECT_REQUIRED')
    applicability = []
    for scenario in equity['scenarios']:
        identifier = scenario['id']; reasons = []; source_time = None; source_price = None
        time_path = time_binding.get(identifier) if isinstance(time_binding, dict) else time_binding
        price_path = price_bindings.get(identifier)
        if retained_source is None or time_path is None or price_path is None:
            reasons.append('SOURCE_BOUND_TERMINAL_TIME_AND_PRICE_BRIDGE_REQUIRED')
        else:
            require(isinstance(time_path, str) and isinstance(price_path, str), 'TERMINAL_JSON_POINTERS_REQUIRED')
            # A calendar close elsewhere in the packet is not evidence that this
            # particular terminal price belongs at that time. Bind sibling fields
            # in the same source scenario/bridge record.
            if time_path.rsplit('/', 1)[0] != price_path.rsplit('/', 1)[0]:
                reasons.append('TERMINAL_TIME_NOT_BOUND_TO_SAME_PRICE_BRIDGE_RECORD')
            try:
                source_time = pointer(retained_source, time_path)
                source_price = pointer(retained_source, price_path)
                if source_time is None:
                    reasons.append('SOURCE_TERMINAL_TIME_UNKNOWN')
                elif timestamp(source_time) != timestamp(equity['exit_at']):
                    reasons.append('SOURCE_TERMINAL_TIME_DIFFERS_FROM_REQUESTED_EXIT')
                if source_price is None or amount(source_price) != amount(scenario['terminal_price']):
                    reasons.append('SOURCE_TERMINAL_PRICE_DIFFERS_OR_UNKNOWN')
            except (KeyError, IndexError, TypeError, ValueError):
                reasons.append('SOURCE_TERMINAL_BINDING_ABSENT_OR_INVALID')
        applicability.append({'id': identifier, 'status': 'UNRESOLVED' if reasons else 'SOURCE_BOUND_SCENARIO_AT_REQUESTED_EXIT',
            'reasons': reasons, 'source_time': deepcopy(source_time), 'source_price': deepcopy(source_price),
            'time_pointer': time_path, 'price_pointer': price_path,
            'source_authenticity_verified': False, 'price_is_observed_future_outcome': False})
    conditional_rows = []
    with localcontext() as precision:
        precision.prec = 64
        capital = amount(entry_cash)
        cash_terminal = (amount(calculated_cash['ending_cash']) if calculated_cash is not None
                         and calculated_cash['ending_cash'] is not None else None)
        cash_return = cash_terminal / capital - 1 if cash_terminal is not None else None
        for row in calculated_equity['scenarios']:
            equity_return = amount(row['net_total_return_fraction'])
            equity_terminal = amount(row['net_terminal_proceeds_plus_dividends'])
            conditional_rows.append({'id': row['id'], 'entry_cash': entry_cash,
                'equity_terminal_proceeds': str(equity_terminal),
                'equity_return_fraction': row['net_total_return_fraction'],
                'equity_return_percent': str(equity_return * 100),
                'cash_terminal_same_capital': str(cash_terminal) if cash_terminal is not None else None,
                'cash_return_fraction': str(cash_return) if cash_return is not None else None,
                'cash_return_percent': str(cash_return * 100) if cash_return is not None else None,
                'excess_over_cash_percentage_points': str((equity_return-cash_return)*100) if cash_return is not None else None,
                'terminal_dollar_difference': str(equity_terminal-cash_terminal) if cash_terminal is not None else None})
    primary_resolved = not cash_unknown and all(r['status'] != 'UNRESOLVED' for r in applicability)
    return {'schema_version': 1, 'method': 'same-capital-equity-cash-comparison-1',
        'currency': equity['currency'], 'input_role': 'hypothetical_scenario', 'input_sha256': digest(document),
        'retained_input': deepcopy(document), 'capital_basis': 'one initial equity share including modeled entry cost',
        'entry_cash': entry_cash, 'cash_principal_role': 'hypothetical_scenario',
        'derived_cash_document': cash, 'equity_result': calculated_equity, 'cash_result': calculated_cash,
        'source': source_info, 'terminal_applicability': applicability, 'cash_unresolved': cash_unknown,
        'status': 'SOURCE_BOUND_CONDITIONAL_COMPARISON' if primary_resolved else 'PRIMARY_APPLICABILITY_UNRESOLVED',
        'primary_comparison': {'rows': conditional_rows, 'role': 'hypothetical_scenario'} if primary_resolved else None,
        'conditional_price_sensitivity': {'rows': conditional_rows, 'role': 'hypothetical_scenario',
            'assumption': 'Apply the supplied terminal prices at the requested exact exit solely as a conditional sensitivity; source timing is not repaired.'},
        'cash_principal_guarantee_established': False, 'source_authenticity_verified': False,
        'advisory_only': True, 'execution_permission_evaluated': False,
        'limitation': 'Existing helper arithmetic only. Same-capital cash is a counterfactual, never observed cash. Terminal scenario applicability, source authenticity, future outcome and cash guarantee are distinct; this adapter establishes no execution gate or selection.'}
