"""Typed price comparisons with separate reference and quote denominators.

Offline caller-supplied arithmetic only. Unknown operand metadata is preserved;
an explicit conditional assumption never upgrades the primary calculation.
"""
from __future__ import annotations

import copy
import math

from evidence_semantics import operand_compatibility


KINDS = {'fair_value', 'forward_target', 'historical_high', 'historical_low'}
DIMENSIONS = ('security_id', 'issuer_id', 'currency', 'share_basis', 'adjustment_basis')


def _positive(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('POSITIVE_FINITE_PRICE_REQUIRED')
    return value


def _known(value):
    if value is not None and not isinstance(value, str):
        raise ValueError('PRICE_METADATA_TEXT_OR_NULL_REQUIRED')
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() != 'unknown'


def _compatibility(quote, reference):
    result = operand_compatibility([quote, reference], list(DIMENSIONS[:-1]))
    values = [quote.get('adjustment_basis'), reference.get('adjustment_basis')]
    known = [_known(value) for value in values]
    mismatch = all(known) and values[0] != values[1]
    unknown = [row['id'] for row, ok in zip((quote, reference), known) if not ok]
    result['dimension_checks'].append({'dimension': 'adjustment_basis',
        'status': 'CONFLICT' if mismatch else 'UNKNOWN' if unknown else 'MATCH',
        'operands': [{'operand_id': row['id'], 'value': value, 'known': ok}
                     for row, value, ok in zip((quote, reference), values, known)],
        'unknown_operand_ids': unknown})
    result['required_dimensions'].append('adjustment_basis')
    if mismatch:
        result['mismatched_dimensions'].append('adjustment_basis')
    if unknown:
        result['unknown_dimensions'].append('adjustment_basis')
    result['status'] = ('INCOMPATIBLE' if result['mismatched_dimensions'] else
                        'UNKNOWN_COMPATIBILITY' if result['unknown_dimensions'] else 'COMPATIBLE')
    result['compatible'] = False if result['mismatched_dimensions'] else None if result['unknown_dimensions'] else True
    return result


def _calculations(quote, reference):
    q, r = quote['value'], reference['value']
    discount, appreciation = (r - q) / r * 100, (r - q) / q * 100
    if not math.isfinite(discount) or not math.isfinite(appreciation):
        raise ValueError('NONFINITE_PRICE_COMPARISON_RESULT')
    return {
        'quote_discount_relative_to_reference_pct': {
            'value': discount, 'unit': 'percent',
            'formula': '100 * (reference - quote) / reference',
            'denominator_operand_id': reference['id'], 'denominator_value': r,
            'meaning': 'Quote is this percent below the reference; negative means above.'},
        'price_change_from_quote_to_reference_pct': {
            'value': appreciation, 'unit': 'percent',
            'formula': '100 * (reference - quote) / quote',
            'denominator_operand_id': quote['id'], 'denominator_value': q,
            'meaning': 'Price appreciation from quote to reference; negative means decline.'},
    }


def _basis_operands(operands, basis_provenance):
    """Keep source-bound assumptions out of primary compatibility operands."""
    primary = copy.deepcopy(operands)
    assumed = []
    if basis_provenance is None:
        return primary, assumed
    expected = {prefix + '/' + dimension for prefix in
                ['/quote', *['/references/' + str(i) for i in range(len(operands) - 1)]]
                for dimension in DIMENSIONS}
    if not isinstance(basis_provenance, dict) or set(basis_provenance) != expected:
        raise ValueError('COMPLETE_PRICE_BASIS_PROVENANCE_REQUIRED')
    for i, operand in enumerate(primary):
        prefix = '/quote' if i == 0 else '/references/' + str(i - 1)
        for dimension in DIMENSIONS:
            pointer = prefix + '/' + dimension
            evidence = basis_provenance[pointer]
            if not isinstance(evidence, dict) or evidence.get('kind') not in {'SOURCE', 'ASSUMPTION', 'UNBOUND'}:
                raise ValueError('PRICE_BASIS_PROVENANCE_KIND_REQUIRED')
            if evidence['kind'] != 'SOURCE':
                value = operand.get(dimension)
                operand[dimension] = None
                if evidence['kind'] == 'ASSUMPTION' and _known(value):
                    assumed.append({'operand_id': operand['id'], 'dimension': dimension,
                                    'value': value, 'argument_pointer': pointer,
                                    'evidence': copy.deepcopy(evidence)})
    return primary, assumed


def compare_prices(quote, references, conditional_same_basis=None, basis_provenance=None):
    """Compare explicit ``value`` prices with their own flat metadata.

    quote and references need unique id; references additionally need kind from
    KINDS. Metadata DIMENSIONS may be absent. conditional_same_basis optionally
    has label and dimensions (explicit values for missing metadata only).
    Source-bound workflows supply complete basis_provenance, keyed by argument
    pointer; assumptions remain separate from primary operands. Direct calls
    without provenance retain caller-supplied arithmetic, not verified sources.
    """
    if not isinstance(quote, dict) or not isinstance(references, list) or not all(isinstance(r, dict) for r in references):
        raise ValueError('QUOTE_OBJECT_AND_REFERENCE_LIST_REQUIRED')
    operands = [quote, *references]
    if any(not _known(r.get('id')) for r in operands) or len({r['id'] for r in operands}) != len(operands):
        raise ValueError('UNIQUE_PRICE_OPERAND_IDS_REQUIRED')
    for row in operands:
        _positive(row.get('value'))
        for dimension in DIMENSIONS:
            _known(row.get(dimension))
    if any(r.get('kind') not in KINDS for r in references):
        raise ValueError('TYPED_PRICE_REFERENCE_REQUIRED')
    if conditional_same_basis is not None:
        if (not isinstance(conditional_same_basis, dict) or
            set(conditional_same_basis) != {'label', 'dimensions'} or
            not _known(conditional_same_basis['label']) or
            not isinstance(conditional_same_basis['dimensions'], dict) or
            not conditional_same_basis['dimensions'] or
            any(k not in DIMENSIONS or not _known(v) for k, v in conditional_same_basis['dimensions'].items())):
            raise ValueError('EXPLICIT_NAMED_BASIS_ASSUMPTION_REQUIRED')
    primary_operands, assumed_fields = _basis_operands(operands, basis_provenance)
    primary_quote = primary_operands[0]
    comparisons = []
    for index, reference in enumerate(references):
        primary_reference = primary_operands[index + 1]
        compatibility = _compatibility(primary_quote, primary_reference)
        scoped_assumptions = [r for r in assumed_fields if r['operand_id'] in {quote['id'], reference['id']}]
        row = {'reference_id': reference['id'], 'reference_kind': reference['kind'],
               'quote': copy.deepcopy(quote), 'reference': copy.deepcopy(reference),
               'primary_operands': {'quote': copy.deepcopy(primary_quote), 'reference': copy.deepcopy(primary_reference)},
               'basis_evidence_mode': 'SOURCE_BOUND_PROVENANCE' if basis_provenance is not None else 'CALLER_SUPPLIED_UNVERIFIED',
               'assumed_basis_fields': copy.deepcopy(scoped_assumptions),
               'operand_units': {operand['id']: {'unit': 'currency_per_share',
                   'currency': operand.get('currency'), 'share_basis': operand.get('share_basis'),
                   'adjustment_basis': operand.get('adjustment_basis'),
                   'reported_decimals': operand.get('decimals')} for operand in (quote, reference)},
               'compatibility': compatibility,
               'primary_status': 'COMPUTED' if compatibility['compatible'] is True else 'UNRESOLVED_BASIS',
               'primary_calculations': _calculations(primary_quote, primary_reference) if compatibility['compatible'] is True else None,
               'conditional_sensitivity': None}
        if (conditional_same_basis is not None or scoped_assumptions) and compatibility['compatible'] is not True:
            assumed = copy.deepcopy([primary_quote, primary_reference])
            assumption_conflicts = []
            for field in scoped_assumptions:
                operand = next(r for r in assumed if r['id'] == field['operand_id'])
                operand[field['dimension']] = field['value']
                if (conditional_same_basis is not None and field['dimension'] in conditional_same_basis['dimensions'] and
                        conditional_same_basis['dimensions'][field['dimension']] != field['value']):
                    assumption_conflicts.append({'operand_id': field['operand_id'], 'dimension': field['dimension'],
                        'source_bound_assumption': field['value'],
                        'conditional_same_basis_assumption': conditional_same_basis['dimensions'][field['dimension']]})
            if conditional_same_basis is not None:
                for operand in assumed:
                    for key, value in conditional_same_basis['dimensions'].items():
                        if not _known(operand.get(key)):
                            operand[key] = value
            checked = _compatibility(*assumed)
            row['conditional_sensitivity'] = {
                'assumption': copy.deepcopy(conditional_same_basis) if conditional_same_basis is not None else
                    {'label': 'Declared source-bound basis assumptions', 'operand_fields': copy.deepcopy(scoped_assumptions)},
                'source_bound_assumptions': copy.deepcopy(scoped_assumptions), 'compatibility': checked,
                'assumption_conflicts': assumption_conflicts,
                'status': 'CONDITIONAL_COMPUTED' if checked['compatible'] is True and not assumption_conflicts else 'UNRESOLVED_BASIS',
                'calculations': _calculations(*assumed) if checked['compatible'] is True and not assumption_conflicts else None}
        if compatibility['compatible'] is not True:
            row['basis_diagnostic'] = 'Supply source-bound metadata for unresolved primary dimensions; declared assumptions support only the separately labeled conditional sensitivity. Conflicting source dimensions remain unresolved.'
        comparisons.append(row)
    return {'method': 'typed-price-comparison-1', 'comparisons': comparisons,
            'rounding': 'Input prices retained without cents rounding; computed percentages are unrounded. Absent reporting precision remains unknown.',
            'limitations': 'Supplied price arithmetic only; no source authentication, split conversion, expected return or probability of attainment. Historical references are past prices, fair value is a valuation opinion, and forward targets are forecasts. Unknown original metadata remains unknown in every conditional sensitivity.'}
