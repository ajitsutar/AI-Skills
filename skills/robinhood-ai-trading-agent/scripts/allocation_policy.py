"""Deterministic advisory notionals from an explicit ordered candidate set.

This arithmetic baseline does not estimate returns, certify research, implement
broker rules, decide execution permission, or submit orders.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, localcontext
import hashlib
import json
from pathlib import Path


POLICY = {
    'id': 'ordered-candidate-equal-notional', 'version': '1.0.0',
    'input_schema_version': 1, 'output_schema_version': 1,
    'selection_precedence': ['user_selection', 'user_weights_symbols',
                             'reviewed_selection', 'requested_count_prefix', 'entire_candidate_set'],
    'default_weighting': 'equal_notional_across_every_selected_row',
    'rounding': 'whole_cents_largest_remainder_ties_in_explicit_selected_order',
    'partial_user_weights': 'retain_unallocated_cash_no_renormalization',
    'score_use': 'none_no_positive_score_filter_no_score_as_expected_return',
    'horizon_use': 'preserve_without_parsing_or_changing_it',
    'order_use': 'preserve_supplied_details_no_quantity_conversion_or_submission',
}
CENT = Decimal('0.01')
FIELDS = {'schema_version', 'currency', 'role', 'budget', 'budget_basis', 'mode',
          'candidate_set', 'requested_count', 'user_selection', 'user_weights',
          'horizon', 'order_details', 'fees', 'constraints', 'optimizer_inputs'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def decimal(value, name):
    # JSON floats have already lost their original decimal spelling. Monetary
    # strings and integers avoid importing binary-float error into this contract.
    require(type(value) in (str, int), 'DECIMAL_STRING_OR_INTEGER_REQUIRED:' + name)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('INVALID_DECIMAL:' + name) from exc
    require(result.is_finite() and result >= 0, 'FINITE_NONNEGATIVE_REQUIRED:' + name)
    return result


def identifier(value, name):
    require(isinstance(value, str) and bool(value) and value == value.strip(),
            'NONEMPTY_EXACT_IDENTIFIER_REQUIRED:' + name)
    return value


def currency_check(value, currency):
    if isinstance(value, dict):
        if 'currency' in value:
            require(value['currency'] == currency, 'CURRENCY_MISMATCH_NO_FX_MODEL')
        for child in value.values():
            currency_check(child, currency)
    elif isinstance(value, list):
        for child in value:
            currency_check(child, currency)


def selected_symbols(value, rows, label):
    require(isinstance(value, list) and bool(value), 'NONEMPTY_SELECTION_REQUIRED:' + label)
    for symbol in value:
        identifier(symbol, label)
    require(len(set(value)) == len(value), 'DUPLICATE_SELECTION:' + label)
    require(set(value) <= set(rows), 'SELECTION_OUTSIDE_CANDIDATE_SET:' + label)
    return list(value)


def source_rows(source):
    require(isinstance(source, dict), 'CANDIDATE_SET_REQUIRED')
    require(source.get('kind') in {'explicit_candidates', 'diagnostic_queue', 'reviewed_selection'},
            'CANDIDATE_SOURCE_KIND_REQUIRED')
    identifier(source.get('source_id'), 'source_id')
    rows = source.get('rows')
    require(isinstance(rows, list) and bool(rows), 'NONEMPTY_ORDERED_CANDIDATE_ROWS_REQUIRED')
    require(type(source.get('declared_count')) is int and source['declared_count'] == len(rows),
            'SOURCE_COUNT_MISMATCH')
    symbols, issuers = [], []
    for row in rows:
        require(isinstance(row, dict), 'CANDIDATE_ROW_OBJECT_REQUIRED')
        symbols.append(identifier(row.get('symbol'), 'symbol'))
        issuers.append(identifier(row.get('issuer_id'), 'issuer_id'))
        identifier(row.get('currency'), 'row_currency')
        require(row.get('primary_review_status') in {None, 'complete', 'incomplete', 'not_reviewed', 'unknown'},
                'INVALID_PRIMARY_REVIEW_STATUS')
        if 'order_details' in row:
            require(isinstance(row['order_details'], dict), 'ORDER_DETAILS_OBJECT_REQUIRED')
    # Case variants cannot be used to evade identity checks. Different supplied
    # issuer IDs are not proof of distinct issuers; authenticity stays unresolved.
    require(len({s.casefold() for s in symbols}) == len(rows), 'DUPLICATE_SECURITY_IDENTITY')
    require(len({s.casefold() for s in issuers}) == len(rows), 'DUPLICATE_ISSUER_IDENTITY')
    if source.get('universe_count') is not None:
        require(type(source['universe_count']) is int and source['universe_count'] >= len(rows),
                'INVALID_UNIVERSE_COUNT')
    if 'coverage_complete' in source:
        require(type(source['coverage_complete']) is bool, 'COVERAGE_BOOLEAN_REQUIRED')
        require(not source['coverage_complete'] or source.get('universe_count') is not None,
                'UPSTREAM_COVERAGE_UNIVERSE_COUNT_REQUIRED')
    if source.get('rows_sha256') is not None:
        require(source['rows_sha256'] == digest(rows), 'CANDIDATE_ROWS_HASH_MISMATCH')
    if source.get('source_sha256') is not None:
        value = source['source_sha256']
        require(isinstance(value, str) and len(value) == 64
                and all(c in '0123456789abcdef' for c in value), 'INVALID_SOURCE_SHA256')
    return rows


def apportioned_cents(budget_cents, weights, count):
    if weights is None:
        quotient, remainder = divmod(budget_cents, count)
        return [quotient + (i < remainder) for i in range(count)]
    exact = [Decimal(budget_cents) * weight for weight in weights]
    floors = [int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact]
    target = int(sum(exact).to_integral_value(rounding=ROUND_FLOOR))
    extras = target - sum(floors)
    order = sorted(range(count), key=lambda i: (-(exact[i] - floors[i]), i))
    for i in order[:extras]:
        floors[i] += 1
    return floors


def allocate(document):
    """Compute the versioned baseline or preserve an unsupported sizing request.

    A supplied optimizer request is retained and routed away from this default.
    Research status and unresolved arithmetic are descriptive, never live-action
    permissions. The caller remains responsible for actual mandate extraction.
    """
    require(isinstance(document, dict), 'DOCUMENT_OBJECT_REQUIRED')
    require(not (set(document) - FIELDS), 'UNKNOWN_DOCUMENT_FIELDS:' + ','.join(sorted(set(document) - FIELDS)))
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1,
            'ALLOCATION_INPUT_SCHEMA')
    currency = identifier(document.get('currency'), 'currency')
    require(len(currency) == 3 and currency.isascii() and currency.isalpha() and currency.isupper(),
            'EXPLICIT_THREE_LETTER_CURRENCY_REQUIRED')
    require(document.get('role') in {'supplied_observation', 'hypothetical_scenario', 'user_assumption'},
            'INPUT_ROLE_REQUIRED')
    currency_check(document, currency)
    budget = decimal(document.get('budget'), 'budget')
    require(budget > 0, 'POSITIVE_BUDGET_REQUIRED')
    require(document.get('budget_basis') in {'notional', 'fee_inclusive'}, 'BUDGET_BASIS_REQUIRED')
    mode = document.get('mode', 'portfolio')
    require(mode in {'portfolio', 'alternative_single_stock'}, 'ALLOCATION_MODE_REQUIRED')
    for field in ('order_details', 'constraints', 'optimizer_inputs'):
        if document.get(field) is not None:
            require(isinstance(document[field], dict), 'OBJECT_REQUIRED:' + field)
    if document.get('fees') is not None:
        require(isinstance(document['fees'], list), 'FEES_LIST_REQUIRED')
    source = document.get('candidate_set')
    rows = source_rows(source)
    by_symbol = {row['symbol']: row for row in rows}
    count = document.get('requested_count')
    require(count is None or (type(count) is int and count > 0), 'INVALID_REQUESTED_COUNT')
    user_symbols = document.get('user_selection')
    if user_symbols is not None:
        user_symbols = selected_symbols(user_symbols, by_symbol, 'user_selection')
    raw_weights = document.get('user_weights')
    weight_symbols, weight_values = None, None
    if raw_weights is not None:
        require(mode == 'portfolio', 'USER_WEIGHTS_CONFLICT_WITH_FULL_BUDGET_ALTERNATIVES')
        require(isinstance(raw_weights, list) and bool(raw_weights), 'NONEMPTY_USER_WEIGHTS_REQUIRED')
        require(all(isinstance(w, dict) and set(w) == {'symbol', 'weight'} for w in raw_weights),
                'USER_WEIGHT_RECORD_REQUIRED')
        weight_symbols = selected_symbols([w['symbol'] for w in raw_weights], by_symbol, 'user_weights')
        weight_values = {w['symbol']: decimal(w['weight'], 'weight') for w in raw_weights}
        require(user_symbols is None or set(user_symbols) == set(weight_symbols),
                'EXPLICIT_SELECTION_WEIGHT_SET_CONFLICT')
    if user_symbols is not None:
        selected, selection_basis = user_symbols, 'user_selection'
    elif weight_symbols is not None:
        selected, selection_basis = weight_symbols, 'user_weights_symbols'
    elif source['kind'] == 'reviewed_selection':
        selected, selection_basis = list(by_symbol), 'reviewed_selection'
    elif count is not None:
        selected, selection_basis = list(by_symbol)[:count], 'requested_count_prefix'
    else:
        selected, selection_basis = list(by_symbol), 'entire_candidate_set'
    numbers = [budget] + list((weight_values or {}).values())
    # Enough precision for every supplied finite decimal coefficient and exponent,
    # including multiplication/summation. Never inherit caller context rounding.
    precision = 32 + sum(len(n.as_tuple().digits) + abs(n.as_tuple().exponent) for n in numbers) + len(str(len(rows)))
    with localcontext() as context:
        context.prec = precision
        require(budget == budget.quantize(CENT), 'BUDGET_MUST_BE_WHOLE_CENTS')
        weights = [weight_values[s] for s in selected] if weight_values is not None else None
        if weights is not None:
            require(sum(weights) <= 1, 'USER_WEIGHTS_EXCEED_FULL_BUDGET')
        return _result(document, source, by_symbol, selected, selection_basis,
                       budget, weights, mode, count)


def _result(document, source, by_symbol, selected, selection_basis, budget, weights, mode, count):
    unresolved = ['ALL_IN_CASH_DEBIT_NOT_MODELED', 'BROKER_AFFORDABILITY_NOT_EVALUATED',
                  'EXPECTED_RETURNS_AND_COVARIANCE_NOT_ESTIMATED']
    if document['budget_basis'] == 'fee_inclusive':
        unresolved.append('FEE_INCLUSIVE_NOTIONAL_SIZING_UNRESOLVED')
    if document.get('fees') is not None:
        unresolved.append('SUPPLIED_FEES_RETAINED_NOT_APPLIED')
    if document.get('constraints'):
        unresolved.append('SUPPLIED_CONSTRAINTS_RETAINED_NOT_SOLVED')
    missing_review = [s for s in selected if by_symbol[s].get('primary_review_status') != 'complete']
    conditional = source['kind'] == 'diagnostic_queue' or bool(missing_review)
    if conditional:
        unresolved.append('PRIMARY_RESEARCH_NOT_VALIDATED_BY_THIS_CALCULATION')
    if source.get('coverage_complete') is not True:
        unresolved.append('FULL_UNIVERSE_COVERAGE_NOT_ESTABLISHED')
    else:
        unresolved.append('UPSTREAM_COVERAGE_DECLARATION_NOT_VERIFIED')
    optimizer_route = bool(document.get('optimizer_inputs')) and weights is None
    if optimizer_route:
        unresolved.append('OPTIMIZER_INPUTS_REQUIRE_SEPARATE_OPERATION')
    elif document.get('optimizer_inputs'):
        unresolved.append('OPTIMIZER_INPUTS_RETAINED_USER_WEIGHTS_TAKE_PRECEDENCE')
    can_label_notional = (document['budget_basis'] == 'notional'
                         and not document.get('constraints') and not optimizer_route)
    cents = (None if optimizer_route else
             [int(budget * 100)] * len(selected) if mode == 'alternative_single_stock' else
             apportioned_cents(int(budget * 100), weights, len(selected)))
    results = []
    for i, symbol in enumerate(selected):
        amount = format(Decimal(cents[i]) * CENT, '.2f') if cents is not None else None
        results.append({
            'symbol': symbol, 'issuer_id': by_symbol[symbol]['issuer_id'], 'currency': document['currency'],
            'source_position': list(by_symbol).index(symbol) + 1, 'selected_position': i + 1,
            'primary_review_status': by_symbol[symbol].get('primary_review_status'),
            'requested_weight': next((w['weight'] for w in (document.get('user_weights') or [])
                                      if w['symbol'] == symbol), None),
            'target_weight': (None if optimizer_route else '1' if mode == 'alternative_single_stock' else
                              str(weights[i]) if weights is not None else '1/' + str(len(selected))),
            'advisory_cash_amount': amount if can_label_notional else None,
            'reference_notional_before_fees': amount,
            'all_in_cash_debit': None, 'share_quantity': None,
            'order_details': deepcopy(by_symbol[symbol].get('order_details')),
            'scenario_id': 'alternative-' + str(i + 1) if mode == 'alternative_single_stock' else 'portfolio',
        })
    total = sum(cents) if cents is not None and mode == 'portfolio' else None
    totals = {'reference_portfolio_notional': format(Decimal(total) * CENT, '.2f') if total is not None else None,
              'allocated_notional_total': format(Decimal(total) * CENT, '.2f') if total is not None and can_label_notional else None,
              'reference_unallocated_notional_budget': format(budget - Decimal(total) * CENT, '.2f') if total is not None else None,
              'all_in_cash_debit': None, 'cash_affordable': None,
              'budget_per_alternative': format(budget, '.2f') if mode == 'alternative_single_stock' else None,
              'alternatives_are_mutually_exclusive': mode == 'alternative_single_stock',
              'alternative_notionals_must_not_be_summed': mode == 'alternative_single_stock'}
    defaults = {'weighting': 'equal_notional' if weights is None and mode == 'portfolio' and not optimizer_route else None,
                'selection': selection_basis if selection_basis == 'entire_candidate_set' else None}
    if 'mode' not in document:
        defaults['mode'] = 'portfolio'
    result = {
        'schema_version': 1, 'method': POLICY['id'] + '-' + POLICY['version'],
        'policy': deepcopy(POLICY), 'policy_sha256': digest(POLICY),
        'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
        'input_sha256': digest(document), 'candidate_rows_sha256': digest(source['rows']),
        'retained_input': deepcopy(document), 'currency': document['currency'], 'role': document['role'],
        'budget': format(budget, '.2f'), 'budget_basis': document['budget_basis'], 'mode': mode,
        'horizon': deepcopy(document.get('horizon')), 'order_details': deepcopy(document.get('order_details')),
        'status': ('OPTIMIZER_INPUTS_REQUIRE_SEPARATE_OPERATION' if optimizer_route else
                   'CONDITIONAL_RESEARCH_BASELINE' if conditional else 'ADVISORY_ALLOCATION_BASELINE'),
        'sizing_status': 'ADVISORY_NOTIONALS_COMPUTED' if can_label_notional else 'SIZING_UNRESOLVED',
        'selected_symbols': list(selected), 'selection_basis': selection_basis,
        'weighting_basis': 'user_weights' if weights is not None else 'full_budget_per_alternative' if mode == 'alternative_single_stock' else 'equal_notional',
        'source_kind': source['kind'], 'source_id': source['source_id'],
        'upstream_coverage_declared': source.get('coverage_complete'),
        'coverage_verified': False,
        'source_count': len(source['rows']), 'selected_count': len(selected), 'requested_count': count,
        'requested_count_met': len(selected) == count if count is not None else None,
        'count_conflict': count is not None and len(selected) != count
                          and selection_basis in {'user_selection', 'user_weights_symbols', 'reviewed_selection'},
        'count_shortfall': max(0, count - len(selected)) if count is not None else None,
        'missing_primary_review_symbols': missing_review, 'rows': results, 'totals': totals,
        'documented_defaults_used': {k: v for k, v in defaults.items() if v is not None},
        'unresolved': unresolved, 'advisory_only': True, 'calculation_only': True,
        'recommendation_validated': False, 'source_authenticity_verified': False,
        'optimization_performed': False, 'expected_return': None, 'performance_claim': None,
        'broker_rules_applied': False, 'quantity_conversion_performed': False,
        'execution_permission_evaluated': False, 'orders_submitted': False,
        'amount_semantics': 'Cent-denominated advisory notionals before fees; no assumption about broker order increments, fractional eligibility or debit.',
        'limitation': 'An illustrative deterministic allocation, not a return-maximizing strategy. Research labels are retained declarations. Missing review is not cured by equal weighting. Native host and broker tools own any user-requested execution.',
    }
    # Classifications and monetary volume supplied with the selected source
    # rows belong beside the final notionals, not only in retained_input.
    from portfolio_decision import allocation_context
    contexts = []
    groups = [[r] for r in results] if mode == 'alternative_single_stock' else [results]
    for group in groups:
        context_rows = []
        for allocated in group:
            original = by_symbol[allocated['symbol']]
            context_rows.append({
                **{k: deepcopy(original[k]) for k in
                   ('sector', 'industry', 'dollar_volume', 'lookthrough',
                    'period', 'provenance', 'classification_provenance') if k in original},
                'id': allocated['symbol'], 'symbol': allocated['symbol'],
                'issuer_id': allocated['issuer_id'], 'currency': document['currency'],
                'instrument_type': original.get('instrument_type', 'unknown'),
                'notional': allocated['reference_notional_before_fees'],
                'notional_basis': 'gross_notional',
            })
        contexts.append({'scenario_id': group[0]['scenario_id'],
                         'notional_status': result['sizing_status'],
                         'result': allocation_context({
                             'currency': document['currency'], 'role': document['role'],
                             'denominator': {'amount': result['budget'],
                                             'basis': 'supplied_notional_budget'},
                             'rows': context_rows})})
    result['allocation_context'] = contexts
    result['context_limitation'] = ('Context uses reference gross notionals before fees; '
        'unresolved final sizing is not cured. Unknown source labels/volume remain unknown. '
        'Use the source-bound recommendation report to map other retained source fields explicitly.')
    result['result_sha256'] = digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding='utf-8-sig'))
    print(json.dumps(allocate(document), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
