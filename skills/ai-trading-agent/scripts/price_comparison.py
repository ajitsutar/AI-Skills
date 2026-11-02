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


def compare_prices(quote, references, conditional_same_basis=None):
    """Compare explicit ``value`` prices with their own flat metadata.

    quote and references need unique id; references additionally need kind from
    KINDS. Metadata DIMENSIONS may be absent. conditional_same_basis optionally
    has label and dimensions (explicit values for missing metadata only).
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
    comparisons = []
    for reference in references:
        compatibility = _compatibility(quote, reference)
        row = {'reference_id': reference['id'], 'reference_kind': reference['kind'],
               'quote': copy.deepcopy(quote), 'reference': copy.deepcopy(reference),
               'operand_units': {operand['id']: {'unit': 'currency_per_share',
                   'currency': operand.get('currency'), 'share_basis': operand.get('share_basis'),
                   'adjustment_basis': operand.get('adjustment_basis'),
                   'reported_decimals': operand.get('decimals')} for operand in (quote, reference)},
               'compatibility': compatibility,
               'primary_status': 'COMPUTED' if compatibility['compatible'] is True else 'UNRESOLVED_BASIS',
               'primary_calculations': _calculations(quote, reference) if compatibility['compatible'] is True else None,
               'conditional_sensitivity': None}
        if conditional_same_basis is not None and compatibility['compatible'] is not True:
            assumed = copy.deepcopy([quote, reference])
            for operand in assumed:
                for key, value in conditional_same_basis['dimensions'].items():
                    if not _known(operand.get(key)):
                        operand[key] = value
            checked = _compatibility(*assumed)
            row['conditional_sensitivity'] = {
                'assumption': copy.deepcopy(conditional_same_basis), 'compatibility': checked,
                'status': 'CONDITIONAL_COMPUTED' if checked['compatible'] is True else 'UNRESOLVED_BASIS',
                'calculations': _calculations(*assumed) if checked['compatible'] is True else None}
        comparisons.append(row)
    return {'method': 'typed-price-comparison-1', 'comparisons': comparisons,
            'rounding': 'Input prices retained without cents rounding; computed percentages are unrounded. Absent reporting precision remains unknown.',
            'limitations': 'Supplied price arithmetic only; no source authentication, split conversion, expected return or probability of attainment. Historical references are past prices, fair value is a valuation opinion, and forward targets are forecasts. Unknown original metadata remains unknown in every conditional sensitivity.'}
