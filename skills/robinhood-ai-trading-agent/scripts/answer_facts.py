"""Fixed semantic sentences from replay-verified, retained offline results.

This deliberately small vocabulary does not accept caller labels, units, values
or prose. Unknown operations remain unavailable. Verification checks the
installed helpers and canonical artifacts, not source truth or model adherence.
All implementation is original; no external dependencies are introduced.
"""
from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
import json
import re

import report_facts

VERSION = 'answer-facts-1'

# (result field, semantic label, scenario, unit kind). A field's meaning cannot
# be overridden by claim IDs, user metadata, requested captions or cost IDs.
TRADE_FIELDS = (
    ('quantity', 'selected quantity', 'selected_order', 'shares'),
    ('gross_notional', 'gross notional before costs', 'selected_order', 'currency'),
    ('transaction_cost', 'aggregate transaction cost', 'selected_order', 'currency'),
    ('entry_cost', 'aggregate entry cost', 'selected_order', 'currency'),
    ('entry_cash_debit', 'entry cash debit including costs', 'selected_order', 'currency'),
    ('sale_net_proceeds', 'sale net proceeds after costs', 'selected_order', 'currency'),
    ('exit_cost', 'aggregate exit cost', 'selected_order_round_trip', 'currency'),
    ('exit_net_proceeds', 'exit net proceeds after costs', 'selected_order_round_trip', 'currency'),
    ('total_cost', 'aggregate round-trip cost', 'selected_order_round_trip', 'currency'),
    ('gross_pnl', 'profit or loss before costs', 'selected_order_round_trip', 'currency'),
    ('net_pnl', 'profit or loss after costs', 'selected_order_round_trip', 'currency'),
    ('max_affordable_quantity', 'maximum affordable quantity', 'maximum_affordable_order', 'shares'),
    ('affordable_cash_debit', 'cash debit including costs', 'maximum_affordable_order', 'currency'),
    ('budget_remainder', 'budget remainder after costs', 'maximum_affordable_order', 'currency'),
    ('minimum_quantity_at_increment', 'minimum increment-sized quantity', 'required_proceeds_order', 'shares'),
    ('sized_net_proceeds', 'sale net proceeds after costs', 'required_proceeds_order', 'currency'),
)
COST_UNITS = {
    'per_share': ('cost per share', 'currency_per_share'),
    'per_order': ('cost per order', 'currency_per_order'),
    'bps_notional': ('cost rate on notional', 'basis_points_of_notional'),
    'per_round_trip': ('cost per round trip', 'currency_per_round_trip'),
}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    return str(value) if number.is_finite() else None


def _project(result, result_hash, artifact='result.json'):
    """Internal projection; external callers must use project_verified."""
    facts, jobs = [], []
    bindings = {row['job_id']: row['arguments'] for row in result['bindings']}
    for index, job in enumerate(result['jobs']):
        base = f'/jobs/{index}/result'
        value = job.get('result')
        row = {'job_id': job['id'], 'operation': job['operation'],
               'computation_status': job['status'], 'result_pointer': base,
               'nested_states': copy.deepcopy(job.get('nested_states', [])),
               'unsupported_or_unprojected_fields': []}
        jobs.append(row)
        if job['status'] != 'COMPUTED':
            row['projection_status'] = 'UNAVAILABLE_JOB_NOT_COMPUTED'
            row['reason'] = job.get('reason')
            continue
        if job['operation'] != 'planning.trade_costs' or not isinstance(value, dict):
            row['projection_status'] = 'UNAVAILABLE_OPERATION_MAPPING'
            continue
        currency = value.get('currency')
        currency_valid = isinstance(currency, str) and re.fullmatch('[A-Z]{3}', currency)
        projected = set()

        def emit(pointer, actual, semantic, scenario, unit_kind, extra=None):
            numeric = _number(actual)
            status = ('UNAVAILABLE_NULL' if actual is None else
                      'UNAVAILABLE_NONNUMERIC' if numeric is None else
                      'UNAVAILABLE_CURRENCY' if unit_kind.startswith('currency') and not currency_valid
                      else 'AVAILABLE')
            unit = (currency + unit_kind[len('currency'):] if currency_valid and
                    unit_kind.startswith('currency') else unit_kind)
            fact = {'job_id': job['id'], 'operation': job['operation'],
                    'semantic_label': semantic, 'scenario': scenario,
                    'input_role': value.get('input_role'), 'unit': unit,
                    'status': status, 'value': copy.deepcopy(actual),
                    'source': {'artifact': artifact, 'sha256': result_hash,
                               'pointer': base + pointer},
                    'input_bindings': copy.deepcopy(bindings.get(job['id'], []))}
            if extra:
                fact.update(extra)
            # JSON quoting keeps supplied job IDs and values data, never prose
            # instructions or a place to substitute arbitrary semantic labels.
            label = f'Job {json.dumps(job["id"], ensure_ascii=False)}; {scenario}; {semantic}'
            fact['sentence'] = (label + ' = ' + numeric + ' ' + unit + '.' if status == 'AVAILABLE'
                                else label + ' is unavailable (' + status + ').')
            facts.append(fact)
            projected.add(pointer)

        for field, semantic, scenario, unit in TRADE_FIELDS:
            if field in value:
                emit('/' + field, value[field], semantic, scenario, unit)
        for collection, scenario in (('entry_cost_records', 'selected_order_transaction_cost_parameter'),
                                     ('exit_cost_records', 'selected_order_exit_cost_parameter')):
            for ordinal, cost in enumerate(value.get(collection, [])):
                if not isinstance(cost, dict) or cost.get('unit') not in COST_UNITS:
                    continue
                semantic, unit = COST_UNITS[cost['unit']]
                emit(f'/{collection}/{ordinal}/amount', cost.get('amount'), semantic, scenario, unit,
                     {'parameter_index': ordinal, 'declared_cost_id': cost.get('id'),
                      'declared_phase': cost.get('phase'), 'is_aggregate_cost': False})
        row['projection_status'] = 'FIXED_FIELDS_PROJECTED'
        # Use the same leaf traversal as the workflow, including null fields.
        import research_contracts
        row['unsupported_or_unprojected_fields'] = [base + pointer for pointer in
            research_contracts.leaves(value) if pointer not in projected]
    return {'schema_version': 1, 'projection_version': VERSION,
            'result_sha256': result_hash, 'facts': facts, 'jobs': jobs,
            'coverage': copy.deepcopy(result['coverage']),
            'free_form_commentary_verified': False, 'whole_answer_pass': False,
            'limits': [
                'Only installed fixed semantic mappings are projected; other fields remain in the authoritative result.',
                'A cost parameter rate is not its aggregate monetary contribution; the selected order is distinct from the maximum affordable order.',
                'Amounts retain their original decimal spelling; no rounding, unit conversion or annualization is inferred.',
                'Verified replay establishes local consistency, not source truth, investment correctness, complete prompt coverage or model adherence.',
                'Artifacts are local files. Download or upload by any host has not been observed.']}


def project_verified(directory):
    """Run the complete verifier before extracting any answer-ready values."""
    import research_workflow as workflow
    directory = report_facts.local_path(directory)
    # Accept either a standalone retained run or execute's root, with paths
    # relative to the exact supplied artifact directory in both cases.
    execution_root = (directory / 'completion.json').is_file()
    run_directory = directory / 'run' if execution_root else directory
    artifact = 'run/result.json' if execution_root else 'result.json'
    verification = workflow.verify(run_directory)
    raw = (run_directory / 'result.json').read_bytes()
    projected = _project(workflow.read_result(raw), workflow.sha(raw), artifact=artifact)
    projected['verification'] = verification
    return projected


def verify_projection(directory, raw):
    """Reject changed numerical values, labels, units, scenarios or pointers."""
    import research_workflow as workflow
    expected = project_verified(directory)
    actual = report_facts.strict_json(raw)
    if workflow.encode(actual) != workflow.encode(expected):
        raise ValueError('FIXED_ANSWER_FACTS_MISMATCH')
    return {'status': 'FIXED_ANSWER_FACTS_MATCH', 'free_form_commentary_verified': False}


def text_projection(facts):
    lines = ['Fixed answer facts from verified retained results',
             'Local consistency only; these sentences do not verify other prose.', '']
    for row in facts['jobs']:
        lines.append('Job ' + json.dumps(row['job_id']) + ': ' + row['computation_status'] +
                     '; ' + row['projection_status'] + '.')
    for fact in facts['facts']:
        source = fact['source']
        lines.extend(['', fact['sentence'],
                      'Evidence: ' + source['artifact'] + '#' + source['pointer'] +
                      '; SHA-256 ' + source['sha256'] + '.'])
    lines.extend(['', *facts['limits']])
    return '\n'.join(lines) + '\n'
