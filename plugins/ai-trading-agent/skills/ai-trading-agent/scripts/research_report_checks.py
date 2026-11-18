"""Arithmetic and definition checks on research claims; never investment approval."""
from decimal import Decimal
from public_research import number, positive


def pe_claim(price, eps, displayed_pe, fiscal_period, basis):
    """Recompute from the exact displayed operands, never vendor forwardPE."""
    p, e = positive(number(price), 'price'), positive(number(eps), 'eps')
    computed = p / e
    definition_complete = bool(isinstance(fiscal_period, str) and fiscal_period.strip()
                               and isinstance(basis, str) and basis.strip())
    return {'computed_pe': str(computed), 'definition_complete': definition_complete,
            'matches_display': abs(number(displayed_pe) - computed) <= Decimal('0.05'),
            'meaning': 'Price divided by this fiscal-period EPS, not automatically NTM'}


def revision(current, past, current_period, past_period):
    """Same fiscal bucket required; signed changes crossing zero are not percentages."""
    a, b = number(current), number(past)
    if current_period != past_period or not current_period:
        raise ValueError('REVISION_PERIOD_MISMATCH')
    if b <= 0:
        return {'change': str(a - b), 'fraction': None, 'reason': 'NONPOSITIVE_BASE'}
    return {'change': str(a - b), 'fraction': str(a / b - 1), 'period': current_period}


def scenario_checks(entry_price, cases):
    """Reject absent stresses/definitions as incomplete, rather than fabricate a bear."""
    price = positive(number(entry_price), 'entry_price')
    issues, derived = [], {}
    for name in ('bear', 'central', 'bull'):
        case = cases.get(name, {})
        try:
            metric = number(case['earnings_or_cashflow_per_share'])
            scale = positive(number(case['exit_parameter']), 'exit_parameter')
            if case['valuation_method'] == 'multiple':
                target = metric * scale
            elif case['valuation_method'] == 'yield':
                if scale > 1:
                    raise ValueError('YIELD_MUST_BE_FRACTION')
                target = metric / scale
            else:
                raise ValueError('UNSUPPORTED_VALUATION_METHOD')
            if not case.get('period') or not case.get('basis') or not case.get('multiple_or_yield_rationale'):
                issues.append(name + ':MISSING_PERIOD_BASIS_OR_VALUATION_RATIONALE')
            derived[name] = {'target': str(target), 'price_return': str(target / price - 1)}
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            issues.append(name + ':' + str(exc))
    if len(derived) == 3:
        targets = [number(derived[n]['target']) for n in ('bear', 'central', 'bull')]
        if targets != sorted(targets):
            issues.append('SCENARIOS_NOT_ORDERED')
        if targets[0] >= price:
            issues.append('NO_PRICE_DOWNSIDE_STRESS; add a separately justified adverse sensitivity')
    return {'arithmetic': derived, 'issues': issues, 'complete': not issues,
            'valuation_validated': False, 'execution_authorized': False}
