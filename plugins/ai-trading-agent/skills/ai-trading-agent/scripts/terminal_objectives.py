"""Always-visible objective-specific projection of executed terminal diagnostics.

This module projects existing kernel results. It does not add scenario values,
derive a user objective or treat a return comparator as a DCF model.
"""
from copy import deepcopy
from decimal import Decimal
import json


def label(value):
    return json.dumps(str(value), ensure_ascii=False)


def summarize(document, scenarios, sensitivities, diagnostics):
    objective_id = 'AFTER_COST_CAPITAL_PRESERVATION'
    rows = []
    lines = [
        '# Terminal-model objective diagnostics',
        'Built-in diagnostic: after-cost holding-period return >= 0. '
        'This is not an inferred investment target, benchmark outperformance or DCF discount closure.',
        'Horizon: ' + str(document['years']) + ' years. Inputs are declared model assumptions; '
        'probabilities and economic feasibility are not established.',
    ]
    for kind, values in [('supplied_scenario', scenarios), ('declared_sensitivity', sensitivities)]:
        for row in values:
            value = row.get('net_total_return_fraction')
            met = Decimal(str(value)) >= 0 if value is not None else None
            rows.append({'id': row['id'], 'kind': kind, 'objective_id': objective_id,
                         'net_total_return_fraction': value, 'met': met,
                         'kernel_status': row['status']})
            lines.append('- ' + label(row['id']) + ' (' + kind + '): after-cost return fraction ' +
                         ('unavailable' if value is None else str(value)) +
                         '; zero-return comparator ' + ('unavailable' if met is None else 'met' if met else 'not met') + '.')
    probes = []
    for index, diagnostic in enumerate(diagnostics):
        probe = diagnostic.get('above_probe')
        if not probe:
            continue
        relation = probe.get('exact_retained_operand_relation')
        met = relation in ('AT_TARGET', 'ABOVE_TARGET') if relation in ('AT_TARGET', 'ABOVE_TARGET', 'BELOW_TARGET') else None
        result = {'base_scenario_id': diagnostic['base_scenario_id'],
                  'objective_id': objective_id, 'diagnostic_pointer': '/conditional_exit_multiple_diagnostics/' + str(index),
                  'kind': 'DERIVED_MATHEMATICAL_PROBE_NOT_SUPPLIED_FORECAST',
                  'varied_parameter': diagnostic['varied_parameter'], 'parameter_value': deepcopy(probe['multiple']),
                  'held_assumptions': deepcopy(diagnostic['held_assumptions']),
                  'net_total_return_fraction': probe.get('net_total_return_fraction'),
                  'exact_relation': relation, 'met': met,
                  'plausibility_or_financing_established': False}
        probes.append(result)
        lines.append('- Derived probe from ' + label(result['base_scenario_id']) + ': exit EV/EBIT ' +
                     str(probe['multiple']['value']) + ', all other row inputs held fixed; after-cost return fraction ' +
                     str(result['net_total_return_fraction']) + ', exact proceeds relation ' + str(relation) +
                     '. This tests only the zero-return comparator; it is not a plausible-multiple forecast or DCF closure test.')
    lines.extend([
        'DCF discount closure: unavailable here. No authored DCF cash-flow model or closure criterion was evaluated.',
        'No general joint necessary or sufficient business conditions are established by these rows. '
        'A successful derived probe is an alternative mathematical path for this named comparator only. '
        'Any proposed necessity claim requires its own explicit objective, conditions and counterexample assessment.',
    ])
    return {'objective_id': objective_id, 'objective_role': 'diagnostic_comparator',
            'measure': 'net_total_return_fraction', 'operator': '>=', 'target': 0,
            'horizon_years': document['years'], 'user_objective_inferred': False,
            'rows': rows, 'derived_probes': probes,
            'dcf_discount_closure': {'status': 'UNAVAILABLE_DCF_MODEL_NOT_EVALUATED'},
            'general_joint_conditions_established': False,
            'report': '\n\n'.join(lines) + '\n'}
