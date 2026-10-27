"""Conditional ratio evidence; incomplete dollar exposure is not a ratio bound.

Relations describe each supplied operand relative to its complete target value.
They are explicit caller assertions, not facts inferred from a missing ledger.
This module has no data retrieval, execution or advice-selection side effects.
"""
from decimal import Context, localcontext

from planning_alignment import amount
from quant_common import require


COMPLETENESS = {'COMPLETE', 'INCOMPLETE', 'UNKNOWN'}
RELATIONS = {'EXACT', 'LOWER_BOUND', 'UPPER_BOUND', 'UNKNOWN'}


def ratio_evidence(numerator, denominator, *, numerator_completeness,
                   denominator_completeness, numerator_relation='UNKNOWN',
                   denominator_relation='UNKNOWN', assumptions=()):
    """Return a nonnegative ratio and only the bound justified by its operands.

For a complete target N >= 0 and D > 0, n <= N and d >= D imply
n/d <= N/D; n >= N and d <= D imply n/d >= N/D. The same direction
on both operands does not establish a ratio bound. A computed ratio may
exceed one when its denominator is net equity; it is not clamped.
"""
    require(isinstance(assumptions, (tuple, list)) and
            all(isinstance(item, str) and item.strip() for item in assumptions),
            'RATIO_ASSUMPTIONS_MUST_BE_NONEMPTY_STRINGS')
    operands = []
    for name, value, completeness, relation in (
            ('numerator', numerator, numerator_completeness, numerator_relation),
            ('denominator', denominator, denominator_completeness, denominator_relation)):
        require(isinstance(completeness, str) and completeness in COMPLETENESS, 'RATIO_COMPLETENESS_' + name)
        require(isinstance(relation, str) and relation in RELATIONS, 'RATIO_RELATION_' + name)
        if completeness == 'COMPLETE':
            require(value is not None, 'RATIO_COMPLETE_VALUE_REQUIRED_' + name)
            require(relation in {'UNKNOWN', 'EXACT'}, 'RATIO_COMPLETE_RELATION_' + name)
            relation = 'EXACT'
        else:
            require(relation != 'EXACT', 'RATIO_EXACT_REQUIRES_COMPLETE_' + name)
        if value is None:
            require(relation == 'UNKNOWN', 'RATIO_MISSING_VALUE_HAS_NO_BOUND_' + name)
            parsed = None
        else:
            parsed = amount(value, 'ratio_' + name, 0)
            require(name != 'denominator' or parsed > 0, 'RATIO_POSITIVE_DENOMINATOR_REQUIRED')
        require(relation not in {'LOWER_BOUND', 'UPPER_BOUND'} or bool(assumptions),
                'RATIO_BOUND_ASSUMPTIONS_REQUIRED')
        operands.append({'value': parsed, 'completeness': completeness, 'relation': relation})
    n, d = operands
    status, ratio = 'UNKNOWN', None
    if n['value'] is not None and d['value'] is not None:
        # Preserve significant supplied digits, independently of global context.
        precision = 64 + sum(len(x['value'].as_tuple().digits) for x in operands)
        with localcontext(Context(prec=precision)):
            ratio = n['value'] / d['value']
        nr, dr = n['relation'], d['relation']
        if nr == dr == 'EXACT':
            status = 'EXACT'
        elif nr in {'EXACT', 'LOWER_BOUND'} and dr in {'EXACT', 'UPPER_BOUND'}:
            status = 'LOWER_BOUND'
        elif nr in {'EXACT', 'UPPER_BOUND'} and dr in {'EXACT', 'LOWER_BOUND'}:
            status = 'UPPER_BOUND'
    return {'schema_version': 1, 'ratio': ratio, 'unit': 'fraction',
            'bound_status': status,
            'value_role': 'UNAVAILABLE' if ratio is None else
                          'SENSITIVITY_ONLY' if status == 'UNKNOWN' else 'CONDITIONAL_RATIO',
            'numerator': n, 'denominator': d,
            'assumptions': ['Complete target numerator is nonnegative and target denominator is strictly positive.',
                            'Both operands refer to the same date, currency, scope and valuation basis.',
                            *assumptions],
            'assumptions_externally_verified': False,
            'interpretation': 'UNKNOWN supports no upper or lower ratio claim. A lower bound on dollar exposure alone does not establish a lower concentration bound.'}
