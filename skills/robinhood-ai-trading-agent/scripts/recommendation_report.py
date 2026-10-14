"""Source-bound final recommendation context; advisory only, no execution gates."""
from copy import deepcopy
import argparse
import hashlib
import json
from pathlib import Path

from report_facts import digest, pointer, strict_json
from portfolio_decision import allocation_context, TYPES


def require(condition, message):
    if not condition:
        raise ValueError(message)


def recommendation_context(document):
    """Bind original rows and computed allocation to one final context report.

    Required bindings: security_rows; allocation OR selected_symbols. Optional:
    ranking, hard_exit, scenarios, cash_benchmark, adverse_thesis, exit_plan.
    row_mapping maps named fields to relative RFC6901 pointers in each source row.
    No inferred prices, thresholds, forecasts, missing classifications or guarantees.
    """
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1,
            'SCHEMA_1_REQUIRED')
    require(document.get('deadline_mode') in {'fixed_exit', 'flexible_review', 'comparison'},
            'DEADLINE_MODE_REQUIRED')
    sources, hashes = {}, {}
    for name, record in document['sources'].items():
        raw = record['text'].encode('utf-8')
        require(hashlib.sha256(raw).hexdigest() == record['sha256'], 'SOURCE_BYTES_HASH_MISMATCH:' + name)
        sources[name] = strict_json(raw)
        hashes[name] = {'bytes_sha256': record['sha256'], 'canonical_sha256': digest(sources[name])}
    receipts = {}
    def bind(name):
        binding = document['bindings'].get(name)
        if binding is None:
            receipts[name] = {'status': 'UNBOUND'}
            return None
        require(binding['source_id'] in sources, 'UNKNOWN_BINDING_SOURCE:' + name)
        try:
            value = deepcopy(pointer(sources[binding['source_id']], binding['pointer']))
        except (KeyError, IndexError):
            receipts[name] = {**binding, 'status': 'PATH_ABSENT'}
            return None
        receipts[name] = {**binding, 'status': 'BOUND', 'value_sha256': digest(value)}
        return value
    rows = bind('security_rows')
    require(isinstance(rows, list), 'SECURITY_ROWS_REQUIRED')
    allocation = bind('allocation')
    selected = bind('selected_symbols') if allocation is None else allocation['selected_symbols']
    require(isinstance(selected, list) and selected and len(set(selected)) == len(selected),
            'NONEMPTY_UNIQUE_SELECTION_REQUIRED')
    mapping = document['row_mapping']
    require('symbol' in mapping and set(mapping) <= {
        'symbol', 'issuer_id', 'sector', 'industry', 'instrument_type', 'period',
        'dollar_volume_amount', 'dollar_volume_currency', 'dollar_volume_period', 'lookthrough'},
        'INVALID_ROW_MAPPING')
    assumptions = document.get('row_assumptions', {})
    require(isinstance(assumptions, dict) and set(assumptions) <= {'instrument_type'},
            'INVALID_ROW_ASSUMPTION')
    for field, declaration in assumptions.items():
        require(isinstance(declaration, dict) and set(declaration) == {'value', 'basis'}
                and isinstance(declaration['basis'], str) and declaration['basis'].strip(),
                'NAMED_ROW_ASSUMPTION_BASIS_REQUIRED')
        require(declaration['value'] in TYPES,
                'INVALID_INSTRUMENT_TYPE_ASSUMPTION')
    mapped, row_receipts = {}, []
    for index, original in enumerate(rows):
        values, paths = {}, {}
        for field, path in mapping.items():
            try:
                values[field] = deepcopy(pointer(original, path))
                paths[field] = {'pointer': path, 'status': 'BOUND', 'value_sha256': digest(values[field])}
            except (KeyError, IndexError):
                values[field] = None
                paths[field] = {'pointer': path, 'status': 'PATH_ABSENT'}
        for field, declaration in assumptions.items():
            if values.get(field) is None:
                values[field] = deepcopy(declaration['value'])
                paths[field] = {**paths.get(field, {'status': 'UNBOUND'}),
                                'assumption_status': 'EXPLICIT_DECLARED_ASSUMPTION',
                                'assumption': deepcopy(declaration)}
        symbol = values['symbol']
        require(isinstance(symbol, str) and symbol and symbol not in mapped, 'INVALID_OR_DUPLICATE_SOURCE_SYMBOL')
        mapped[symbol] = values
        row_receipts.append({'source_position': index, 'symbol': symbol, 'fields': paths})
    require(set(selected) <= set(mapped), 'SELECTION_OUTSIDE_SOURCE_ROWS')
    if allocation is not None:
        require(allocation['currency'] == document['currency'], 'ALLOCATION_CURRENCY_MISMATCH')
        require([r['symbol'] for r in allocation['rows']] == selected,
                'ALLOCATION_ROWS_SELECTION_MISMATCH')
        groups = [[r] for r in allocation['rows']] if allocation['mode'] == 'alternative_single_stock' else [allocation['rows']]
        denominator = allocation['budget']
    else:
        groups = [[{'symbol': s, 'reference_notional_before_fees': None} for s in selected]]
        denominator = None
    contexts = []
    for group in groups:
        context_rows = []
        for allocated in group:
            s = allocated['symbol']; observation = mapped[s]
            volume = None
            if 'dollar_volume_amount' in mapping:
                volume = {'amount': observation.get('dollar_volume_amount'),
                          'currency': observation.get('dollar_volume_currency'),
                          'unit': document.get('dollar_volume_unit'),
                          'period': observation.get('dollar_volume_period'),
                          'provenance': {'binding': receipts['security_rows'], 'symbol': s,
                                         'mapping': deepcopy(mapping),
                                         'unit_basis': document.get('dollar_volume_unit_basis', 'undeclared')}}
            context_rows.append({**{k: observation[k] for k in
                ('issuer_id', 'sector', 'industry', 'period', 'lookthrough') if k in observation},
                'id': s, 'symbol': s, 'instrument_type': observation.get('instrument_type') or 'unknown',
                'notional': allocated['reference_notional_before_fees'], 'notional_basis': 'gross_notional',
                'dollar_volume': volume, 'provenance': deepcopy(receipts['security_rows'])})
        contexts.append(allocation_context({'currency': document['currency'], 'role': document['role'],
            'denominator': {'amount': denominator, 'basis': 'supplied_allocation_budget'}, 'rows': context_rows}))
    evidence = {name: bind(name) for name in
                ('ranking', 'hard_exit', 'scenarios', 'cash_benchmark', 'adverse_thesis', 'exit_plan')}
    forced = document['deadline_mode'] == 'fixed_exit'
    result = {'schema_version': 1, 'method': 'source-bound-final-recommendation-context-1',
        'input_sha256': digest(document), 'retained_input': deepcopy(document),
        'sources': hashes, 'bindings': receipts, 'row_bindings': row_receipts,
        'row_assumptions': deepcopy(assumptions),
        'selected_symbols': deepcopy(selected), 'allocation': allocation,
        'allocation_context': contexts, 'evidence': evidence,
        'deadline_mode': document['deadline_mode'],
        'risk_interpretation': {
            'scenario_loss_bound_established': False,
            'scenario_note': 'Conditional terminal scenarios are not a maximum-loss bound; outcomes outside their range remain possible.',
            'forced_sale_note': ('A fixed-date exit can face gaps, halts or absent buyers. A stop, supplied dollar volume or modeled cost does not guarantee a fill, exit price or cash availability.' if forced else None),
            'liquidity_note': 'Supplied monetary volume and notional/volume ratios describe scale; no feasible participation rate or executable capacity is established.',
            'cash_principal_guarantee_established': False,
            'cash_note': 'The cash comparator is a model under supplied rate/cost terms. Principal guarantee, counterparty and insurance terms are not established by the return calculation.',
            'adverse_thesis_status': 'SUPPLIED_NOT_VERIFIED' if evidence['adverse_thesis'] is not None else 'UNKNOWN',
            'exit_plan_status': 'SUPPLIED_NOT_VERIFIED' if evidence['exit_plan'] is not None else 'UNKNOWN',
            'suggested_review_topics': ['Adverse earnings/guidance or balance-sheet evidence',
                'Catalyst delay or thesis invalidation', 'Deteriorating liquidity and feasibility of the fixed exit',
                'Early-exit authority and hard-exit handling; monitoring ownership'],
            'review_topics_are_advisory_not_automatic_sell_instructions': True},
        'unresolved': [name.upper() + '_UNBOUND_OR_UNKNOWN' for name, value in evidence.items() if value is None],
        'advisory_only': True, 'source_authenticity_verified': False,
        'recommendation_validated': False, 'execution_permission_evaluated': False,
        'orders_submitted': False,
        'limitation': 'Binding preserves declared sources and computed amounts, not source truth, recommendation completeness or execution feasibility. Unknown labels retain the original denominator. Alternatives remain separate.'}
    result['result_sha256'] = digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    print(json.dumps(recommendation_context(json.loads(args.input.read_text(encoding='utf-8-sig'))), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
