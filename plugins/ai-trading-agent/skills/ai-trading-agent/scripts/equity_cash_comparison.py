"""Same-entry-capital equity/cash counterfactual using existing local helpers."""
from copy import deepcopy
from decimal import Decimal, localcontext
import hashlib

from cash_benchmark import review_cash_benchmark
from financial_alignment import price_scenarios
from planning_alignment import amount, cash_projection
from quant_common import digest, require, timestamp
from report_facts import pointer, strict_json



BENCHMARK_OBSERVATION_ROLES = frozenset({'supplied_observation', 'supplied_observations'})
BENCHMARK_SOURCE_FIELDS = ('observed_at', 'rate_or_return', 'instrument', 'currency')
BENCHMARK_PATHS = tuple('/document/cash_benchmark/' + name for name in BENCHMARK_SOURCE_FIELDS) + (
    '/document/equity_document/currency', '/document/cash_document/currency')


def benchmark_provenance(arguments, bindings):
    """Retain actual workflow bindings, including ancestor source/assumption bindings.

    Byte lineage is not authentication, publication timing, or assurance that an
    upstream supplied record is itself an original observation.
    """
    records = []
    for path in BENCHMARK_PATHS:
        candidates = [b for b in bindings if path == b['target_pointer']
                      or path.startswith(b['target_pointer'] + '/')]
        binding = deepcopy(max(candidates, key=lambda b: len(b['target_pointer']))) if candidates else {'kind': 'UNBOUND'}
        if binding['kind'] == 'SOURCE':
            binding['effective_source_pointer'] = binding['source_pointer'] + path[len(binding['target_pointer']):]
        records.append({'path': path, 'binding': binding})
    return {'schema_version': 1, 'records': records}


def cash_applicability(document, provenance):
    """Keep source-date applicability separate from conditional money arithmetic."""
    benchmark = document.get('cash_benchmark')
    cash = document['cash_document']; equity = document['equity_document']
    reasons = []
    if not isinstance(benchmark, dict):
        reasons.append('CASH_BENCHMARK_DATING_REQUIRED')
        benchmark = {}
    research_as_of = provenance.get('research_as_of') if isinstance(provenance, dict) else None
    resolved = {'as_of': research_as_of or document.get('as_of'), 'entry_at': equity['entry_at'], 'exit_at': equity['exit_at']}
    if research_as_of is not None:
        try:
            if timestamp(document.get('as_of')) != timestamp(research_as_of):
                reasons.append('CASH_RESEARCH_CUTOFF_DIFFERS_FROM_WORKFLOW_CONTRACT')
        except (ValueError, TypeError, AttributeError):
            reasons.append('CASH_RESEARCH_CUTOFF_UNKNOWN_OR_INVALID')
    if not benchmark.get('observed_at'):
        reasons.append('CASH_RATE_OBSERVATION_DATE_UNKNOWN')
    if not document.get('as_of'):
        reasons.append('RESEARCH_AS_OF_UNKNOWN')
    if benchmark.get('max_age_seconds') is None:
        reasons.append('CASH_FRESHNESS_POLICY_UNASSESSED')
    for field in ('instrument', 'methodology'):
        if not isinstance(benchmark.get(field), str) or not benchmark[field].strip():
            reasons.append('CASH_BENCHMARK_' + field.upper() + '_REQUIRED')
    normalized = deepcopy(benchmark)
    try:
        if benchmark.get('rate_or_return') is not None:
            normalized['rate_or_return'] = float(amount(benchmark['rate_or_return']))
        if (benchmark.get('rate_or_return') is None or cash.get('annual_effective_rate') is None
                or amount(benchmark['rate_or_return']) != amount(cash['annual_effective_rate'])):
            reasons.append('CASH_BENCHMARK_RATE_DIFFERS_OR_UNKNOWN')
    except (ValueError, TypeError, OverflowError):
        reasons.append('CASH_BENCHMARK_RATE_INVALID')
    if benchmark.get('basis') != 'annual_effective' or benchmark.get('day_count') != cash.get('day_count'):
        reasons.append('CASH_BENCHMARK_BASIS_DIFFERS_OR_UNKNOWN')
    if benchmark.get('currency') != cash.get('currency'):
        reasons.append('CASH_BENCHMARK_CURRENCY_DIFFERS_OR_UNKNOWN')
    try:
        review = review_cash_benchmark(normalized, resolved)
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        review = {'status': 'UNVERIFIED', 'holding_period_return': None,
                  'reasons': ['CASH_BENCHMARK_UNVERIFIED: invalid or missing timestamp'],
                  'inputs': normalized}
    if review['status'] != 'CALCULATED_ASSUMPTION':
        reasons.extend(review['reasons'])
    require(provenance is None or (isinstance(provenance, dict) and provenance.get('schema_version') == 1),
            'CASH_BENCHMARK_PROVENANCE_SCHEMA_REQUIRED')
    records = provenance.get('records', []) if isinstance(provenance, dict) else []
    require(isinstance(records, list), 'CASH_BENCHMARK_PROVENANCE_RECORDS_REQUIRED')
    require(all(isinstance(r, dict) and r.get('path') in BENCHMARK_PATHS for r in records)
            and len({r['path'] for r in records}) == len(records), 'CASH_BENCHMARK_PROVENANCE_PATHS_INVALID')
    indexed = {r['path']: r['binding'] for r in records}
    quote_records = []
    for path in BENCHMARK_PATHS:
        binding = indexed.get(path, {})
        require(isinstance(binding, dict), 'CASH_BENCHMARK_PROVENANCE_BINDING_REQUIRED')
        source_bound = (binding.get('kind') == 'SOURCE' and binding.get('source_role') in BENCHMARK_OBSERVATION_ROLES
                        and binding.get('source_id') and binding.get('source_sha256')
                        and isinstance(binding.get('effective_source_pointer'), str))
        if not source_bound:
            reasons.append('SOURCE_BOUND_CASH_METADATA_REQUIRED: ' + path)
        elif path.startswith('/document/cash_benchmark/'):
            quote_records.append((binding['source_id'], binding['source_sha256'],
                                  binding['effective_source_pointer'].rsplit('/', 1)[0]))
    if len(quote_records) == len(BENCHMARK_SOURCE_FIELDS) and len(set(quote_records)) != 1:
        reasons.append('CASH_OBSERVATION_NOT_BOUND_TO_SAME_RATE_RECORD')
    return {'status': 'UNRESOLVED' if reasons else 'SOURCE_BOUND_DATED_ASSUMPTION',
            'reasons': reasons, 'benchmark_review': review, 'provenance': deepcopy(provenance),
            'rate_observation_freshness_is_not_future_rate_guarantee': True,
            'source_authenticity_verified': False, 'future_rate_guaranteed': False,
            'limitation': 'Source bindings retain supplied record lineage only. A fresh rate observation does not guarantee the projected future rate; methodology and horizon adjustment remain explicit assumptions.'}


def equity_cash_comparison(document, benchmark_provenance=None):
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
    cash_dating = cash_applicability(document, benchmark_provenance)
    primary_resolved = (not cash_unknown and cash_dating['status'] != 'UNRESOLVED'
                        and all(r['status'] != 'UNRESOLVED' for r in applicability))
    return {'schema_version': 1, 'method': 'same-capital-equity-cash-comparison-1',
        'currency': equity['currency'], 'input_role': 'hypothetical_scenario', 'input_sha256': digest(document),
        'retained_input': deepcopy(document), 'capital_basis': 'one initial equity share including modeled entry cost',
        'entry_cash': entry_cash, 'cash_principal_role': 'hypothetical_scenario',
        'derived_cash_document': cash, 'equity_result': calculated_equity, 'cash_result': calculated_cash,
        'source': source_info, 'terminal_applicability': applicability,
        'cash_calculation_unresolved': cash_unknown, 'cash_applicability': cash_dating,
        'cash_unresolved': cash_unknown + cash_dating['reasons'],
        'status': 'SOURCE_BOUND_CONDITIONAL_COMPARISON' if primary_resolved else 'PRIMARY_APPLICABILITY_UNRESOLVED',
        'primary_comparison': {'rows': conditional_rows, 'role': 'hypothetical_scenario'} if primary_resolved else None,
        'conditional_price_sensitivity': {'rows': conditional_rows, 'role': 'hypothetical_scenario',
            'assumption': 'Apply the supplied terminal prices at the requested exact exit solely as a conditional sensitivity; equity/cash source timing and currency assumptions are not repaired; the supplied cash rate is held constant only for this projection.'},
        'cash_principal_guarantee_established': False, 'source_authenticity_verified': False,
        'advisory_only': True, 'execution_permission_evaluated': False,
        'limitation': 'Existing helper arithmetic only. Same-capital cash is a counterfactual, never observed cash. Terminal scenario applicability, source authenticity, future outcome and cash guarantee are distinct; this adapter establishes no execution gate or selection.'}
