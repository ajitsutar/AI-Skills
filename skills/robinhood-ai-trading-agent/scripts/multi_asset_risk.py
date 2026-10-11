"""Offline cross-asset scenario valuation with explicit conventions and boundaries.

Supports spot instruments, linear futures P&L, fixed cash-flow bonds and European
vanilla option models. American/exotic options and callable bonds fail closed.
"""
from __future__ import annotations

import math
from scipy.stats import norm

from quant_common import cli, require, scalar


def european_option(spot, strike, years, volatility, rate, dividend_yield, right,
                    exercise_style='european'):
    require(exercise_style == 'european', 'AMERICAN_OR_EXOTIC_OPTION_MODEL_UNSUPPORTED')
    require(right in {'call', 'put'}, 'OPTION_RIGHT')
    s, k = scalar(spot, 'spot', 1e-12), scalar(strike, 'strike', 1e-12)
    t, vol = scalar(years, 'years', 0), scalar(volatility, 'volatility', 0)
    r, q = scalar(rate, 'rate'), scalar(dividend_yield, 'dividend_yield')
    sign = 1 if right == 'call' else -1
    if t == 0 or vol == 0:
        discounted_s, discounted_k = s*math.exp(-q*t), k*math.exp(-r*t)
        price = max(sign*(discounted_s-discounted_k), 0.)
        return {'price': price, 'delta': None, 'gamma': None, 'vega_per_1pct': None,
                'limitation': 'Expiry/zero-volatility branch; kink Greeks undefined.'}
    d1 = (math.log(s/k)+(r-q+vol*vol/2)*t)/(vol*math.sqrt(t))
    d2 = d1-vol*math.sqrt(t)
    price = sign*(s*math.exp(-q*t)*norm.cdf(sign*d1)-k*math.exp(-r*t)*norm.cdf(sign*d2))
    return {'price': float(price), 'delta': float(sign*math.exp(-q*t)*norm.cdf(sign*d1)),
            'gamma': float(math.exp(-q*t)*norm.pdf(d1)/(s*vol*math.sqrt(t))),
            'vega_per_1pct': float(s*math.exp(-q*t)*norm.pdf(d1)*math.sqrt(t)*.01),
            'limitation': 'European constant-volatility continuous-yield model; no assignment, smile, discrete-dividend or exercise decision.'}


def fixed_cashflow_bond(cashflows, zero_rates, spread=0, callable=False):
    require(callable is False, 'CALLABLE_OR_PREPAYABLE_BOND_UNSUPPORTED')
    require(cashflows and len(cashflows) == len(zero_rates), 'CASHFLOW_CURVE_ALIGNMENT')
    s = scalar(spread, 'spread')
    times = [scalar(c['years'], 'years', 1e-12) for c in cashflows]
    require(times == sorted(set(times)), 'CASHFLOW_TIMES')
    pv = [scalar(c['amount'], 'amount', 0)*math.exp(-(scalar(r, 'zero_rate')+s)*t)
          for c, r, t in zip(cashflows, zero_rates, times)]
    price = sum(pv)
    require(price > 0, 'BOND_HAS_NO_POSITIVE_CASHFLOW')
    duration = sum(t*v for t, v in zip(times, pv))/price
    convexity = sum(t*t*v for t, v in zip(times, pv))/price
    return {'dirty_model_price': price, 'continuous_parallel_duration': duration,
            'continuous_parallel_convexity': convexity, 'dv01': price*duration*.0001,
            'limitation': 'Amounts per supplied bond unit; continuous zero rates; no credit default/prepayment unless separately stressed.'}


def scenario_book(positions, scenarios, nav, base_currency):
    equity = scalar(nav, 'nav', 1e-12)
    require(positions and len({p['id'] for p in positions}) == len(positions), 'POSITION_IDS')
    require(scenarios and len({s['name'] for s in scenarios}) == len(scenarios), 'SCENARIO_IDS')
    results = []
    for scenario in scenarios:
        impacts = []
        for p in positions:
            kind = p['kind']
            qty = scalar(p['quantity'], 'quantity')
            multiplier = scalar(p['multiplier'], 'multiplier', 1e-12)
            fx = scalar(p['fx_to_base'], 'fx_to_base', 1e-12)
            if p['currency'] == base_currency:
                require(fx == 1, 'BASE_CURRENCY_FX_MUST_BE_ONE')
                fx_return = 0.
            else:
                fx_return = scalar(scenario['fx_returns'][p['currency']], 'fx_return', -.999999)
            shocked_fx = fx*(1+fx_return)
            shock = scenario['positions'][p['id']]
            if kind in {'equity', 'etf', 'spot_crypto', 'cash'}:
                mark = scalar(p['mark'], 'mark', 1e-12)
                if kind == 'etf':
                    require(p.get('leveraged_or_inverse') is False, 'PATH_DEPENDENT_FUND_UNSUPPORTED')
                ret = scalar(shock['price_return'], 'price_return', -1)
                require(kind != 'cash' or (mark == 1 and ret == 0), 'CASH_ONLY_FX_SHOCK')
                before, after = mark, mark*(1+ret)
                pnl = qty*multiplier*(after*shocked_fx-before*fx)
            elif kind == 'future':
                # Futures mark-to-market is not a funded notional balance.
                before = scalar(p['mark'], 'future_mark')
                after = before+scalar(shock['price_change'], 'price_change')
                pnl = qty*multiplier*(after-before)*shocked_fx
            elif kind == 'european_option':
                terms = p['terms']
                before = european_option(**terms)['price']
                changed = dict(terms)
                changed['spot'] *= 1+scalar(shock['spot_return'], 'spot_return', -.999999)
                changed['volatility'] += scalar(shock['volatility_change'], 'volatility_change')
                changed['rate'] += scalar(shock['rate_change'], 'rate_change')
                changed['years'] -= scalar(shock['elapsed_years'], 'elapsed_years', 0)
                require(changed['years'] >= 0, 'SCENARIO_BEYOND_OPTION_EXPIRY_REQUIRES_SETTLEMENT_MODEL')
                after = european_option(**changed)['price']
                pnl = qty*multiplier*(after*shocked_fx-before*fx)
            elif kind == 'fixed_bond':
                terms = p['terms']
                before = fixed_cashflow_bond(**terms)['dirty_model_price']
                changed = dict(terms)
                shift = scalar(shock['parallel_rate_change'], 'parallel_rate_change')
                changed['zero_rates'] = [r+shift for r in terms['zero_rates']]
                changed['spread'] = terms.get('spread', 0)+scalar(shock['spread_change'], 'spread_change')
                after = fixed_cashflow_bond(**changed)['dirty_model_price']
                pnl = qty*multiplier*(after*shocked_fx-before*fx)
            else:
                raise ValueError('UNSUPPORTED_INSTRUMENT:' + kind)
            impacts.append({'id': p['id'], 'kind': kind, 'pnl_base': pnl,
                            'base_unit_price': before, 'scenario_unit_price': after})
        loss = sum(x['pnl_base'] for x in impacts)
        results.append({'name': scenario['name'], 'pnl_base': loss, 'pnl_fraction': loss/equity,
                        'post_scenario_nav': equity+loss, 'positions': impacts})
    return {'scenarios': results, 'execution_authorized': False, 'nav_reconciled': False,
            'limitation': 'Model P&L, not liquidation bids or margin calculation. NAV/collateral must be reconciled separately. No automatic offset of cash demands or option assignment.'}


if __name__ == '__main__':
    cli({'option': european_option, 'bond': fixed_cashflow_bond, 'scenarios': scenario_book})
