"""Original, offline, bounded derivatives research calculations; no execution APIs."""
from __future__ import annotations

import argparse
import copy
from datetime import date, datetime, timezone
from decimal import Decimal, Context, DecimalException, DivisionByZero, InvalidOperation, Overflow, ROUND_HALF_UP, localcontext
import json
import math
from pathlib import Path
import re


def exact(obj, fields):
    if not isinstance(obj, dict):
        raise ValueError('OBJECT_REQUIRED')
    unknown = set(obj) - set(fields)
    missing = set(fields) - set(obj)
    if unknown:
        raise ValueError('UNKNOWN_FIELDS: ' + ','.join(sorted(unknown)))
    if missing:
        raise ValueError('MISSING_FIELDS: ' + ','.join(sorted(missing)))


def num(obj, key, low=None, positive=False):
    value = obj[key]
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('FINITE_NUMBER_REQUIRED: ' + key)
    if (low is not None and value < low) or (positive and value <= 0):
        raise ValueError('OUT_OF_DOMAIN: ' + key)
    return float(value)


def integer(obj, key, low, high):
    value = obj[key]
    if type(value) is not int or not low <= value <= high:
        raise ValueError('INTEGER_OUT_OF_DOMAIN: ' + key)
    return value


def choice(obj, key, values):
    if obj[key] not in values:
        raise ValueError('UNSUPPORTED_' + key.upper())
    return obj[key]


def iso(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('ISO_DATE_REQUIRED')
    return date.fromisoformat(value)


def instant(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)',value):
        raise ValueError('EXACT_AWARE_TIMESTAMP_REQUIRED')
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(timezone.utc)


def currency(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z]{3}', value):
        raise ValueError('THREE_LETTER_CURRENCY_REQUIRED')
    return value


OPTION_FIELDS = ('spot', 'strike', 'time_years', 'risk_free_rate', 'dividend_yield',
                 'volatility', 'steps', 'right', 'exercise', 'dividend_model', 'rate_compounding')


def option_parameters(d):
    exact(d, OPTION_FIELDS)
    s, k = num(d, 'spot', positive=True), num(d, 'strike', positive=True)
    t = num(d, 'time_years', low=0)
    r, q = num(d, 'risk_free_rate'), num(d, 'dividend_yield', low=0)
    v = num(d, 'volatility', low=0)
    n = integer(d, 'steps', 1, 1000)
    right = choice(d, 'right', ('call', 'put'))
    exercise = choice(d, 'exercise', ('american', 'european'))
    choice(d, 'dividend_model', ('continuous_yield',))
    choice(d, 'rate_compounding', ('continuous',))
    # Explicit computational domain; do not silently truncate extreme trees.
    if t > 100 or abs(r) > 5 or q > 5 or v > 5:
        raise ValueError('OPTION_COMPUTATIONAL_DOMAIN_EXCEEDED')
    return s, k, t, r, q, v, n, right, exercise


def _price(d):
    s, k, t, r, q, v, n, right, exercise = option_parameters(d)
    payoff = (lambda x: max(x-k, 0.0)) if right == 'call' else (lambda x: max(k-x, 0.0))
    if t == 0:
        return payoff(s), None, 'expiry_intrinsic'
    dt = t / n
    if v == 0:
        # Risk-neutral deterministic path; American exercise only at declared grid dates.
        dates = range(n+1) if exercise == 'american' else (n,)
        values = [math.exp(-r*i*dt)*payoff(s*math.exp((r-q)*i*dt)) for i in dates]
        return max(values), None, 'zero_volatility_deterministic_grid'
    a = v * math.sqrt(dt)
    u, down = math.exp(a), math.exp(-a)
    p = (math.exp((r-q)*dt)-down)/(u-down)
    if not 0 <= p <= 1:
        raise ValueError('CRR_ARBITRAGE_GRID: increase steps or change volatility bracket')
    if abs(math.log(s)) + n*a > 650:
        raise ValueError('TREE_NUMERIC_RANGE_EXCEEDED')
    discount = math.exp(-r*dt)
    values = [payoff(s*math.exp((2*j-n)*a)) for j in range(n+1)]
    for i in range(n-1, -1, -1):
        next_values = []
        for j in range(i+1):
            continuation = discount*((1-p)*values[j]+p*values[j+1])
            if exercise == 'american':
                continuation = max(continuation, payoff(s*math.exp((2*j-i)*a)))
            next_values.append(continuation)
        values = next_values
    return values[0], p, 'crr_grid'


def option_crr(d):
    value, p, branch = _price(d)
    return {'status': 'COMPUTED', 'formula_id': 'CRR_CONTINUOUS_YIELD_GRID_V1',
            'value_per_underlying_unit': value, 'risk_neutral_up_probability': p,
            'branch': branch, 'exercise_dates': 'grid_dates' if d['exercise']=='american' else 'expiry_only',
            'steps': d['steps'], 'discrete_cash_dividends_supported': False,
            'convergence_verified': False}


def implied_volatility(d):
    exact(d, ('option', 'market_price', 'volatility_lower', 'volatility_upper', 'price_tolerance', 'max_iterations'))
    base = d['option']
    # Volatility is the unknown, not a second conflicting supplied field.
    exact(base, tuple(k for k in OPTION_FIELDS if k != 'volatility'))
    target = num(d, 'market_price', low=0)
    lo, hi = num(d, 'volatility_lower', positive=True), num(d, 'volatility_upper', positive=True)
    tol = num(d, 'price_tolerance', positive=True)
    iterations = integer(d, 'max_iterations', 1, 100)
    if not lo < hi <= 5:
        raise ValueError('INVALID_VOLATILITY_BRACKET')
    spec = {**base, 'volatility': lo}
    s, k, t, r, q, _, n, right, exercise = option_parameters(spec)
    out = {'formula_id': 'CRR_BRACKETED_IV_V1', 'implied_volatility': None,
           'price_tolerance': tol, 'initial_volatility_bracket': [lo,hi], 'iterations': 0,
           'uniqueness_proven': False}
    if t == 0:
        intrinsic = max(s-k,0) if right=='call' else max(k-s,0)
        return {**out, 'status': 'NOT_IDENTIFIABLE_AT_EXPIRY' if abs(target-intrinsic)<=tol else 'PRICE_INCONSISTENT_AT_EXPIRY',
                'intrinsic':intrinsic}
    # Bounds allow negative rates. American bounds maximize discounted exercise cashflow envelope.
    if exercise == 'american':
        lower = max(s-k,0) if right=='call' else max(k-s,0)
        upper = s if right=='call' else k*math.exp(max(-r*t,0))
    else:
        ds, dk = s*math.exp(-q*t), k*math.exp(-r*t)
        lower = max(ds-dk,0) if right=='call' else max(dk-ds,0)
        upper = ds if right=='call' else dk
    out['economic_price_bounds'] = [lower,upper]
    if target < lower-tol or target > upper+tol:
        return {**out,'status':'PRICE_OUTSIDE_ECONOMIC_BOUNDS'}
    p_lo = _price(spec)[0]
    p_hi = _price({**base,'volatility':hi})[0]
    out['bracket_prices'] = [p_lo,p_hi]
    if p_hi < p_lo:
        return {**out,'status':'NON_MONOTONE_BRACKET'}
    if target < p_lo-tol or target > p_hi+tol:
        return {**out,'status':'PRICE_OUTSIDE_VOLATILITY_BRACKET'}
    if abs(p_hi-p_lo)<=tol or abs(target-p_lo)<=tol or abs(target-p_hi)<=tol:
        return {**out,'status':'BOUNDARY_OR_FLAT_PRICE_NOT_IDENTIFIED'}
    for i in range(1,iterations+1):
        mid = (lo+hi)/2
        value = _price({**base,'volatility':mid})[0]
        if value < p_lo-tol or value > p_hi+tol:
            return {**out,'status':'NON_MONOTONE_BRACKET','iterations':i}
        residual = value-target
        if abs(residual)<=tol:
            return {**out,'status':'CONVERGED','implied_volatility':mid,'repriced_value':value,
                    'price_residual':residual,'final_volatility_bracket':[lo,hi],'iterations':i}
        if residual < 0:
            lo,p_lo=mid,value
        else:
            hi,p_hi=mid,value
    return {**out,'status':'MAX_ITERATIONS','repriced_value':value,'price_residual':residual,
            'final_volatility_bracket':[lo,hi],'iterations':iterations}


def fx_forward(d):
    exact(d, ('spot_domestic_per_foreign','domestic_currency','foreign_currency','domestic_rate',
              'foreign_rate','time_years','compounding'))
    domestic, foreign = currency(d['domestic_currency']), currency(d['foreign_currency'])
    if domestic == foreign:
        raise ValueError('DISTINCT_CURRENCIES_REQUIRED')
    spot = num(d,'spot_domestic_per_foreign',positive=True)
    rd,rf,t = num(d,'domestic_rate'),num(d,'foreign_rate'),num(d,'time_years',low=0)
    method=choice(d,'compounding',('simple','continuous'))
    if method=='simple':
        if 1+rd*t<=0 or 1+rf*t<=0:
            raise ValueError('POSITIVE_ACCUMULATION_FACTORS_REQUIRED')
        forward=spot*(1+rd*t)/(1+rf*t)
    else:
        forward=spot*math.exp((rd-rf)*t)
    if not math.isfinite(forward) or forward<=0:
        raise ValueError('FORWARD_NUMERIC_DOMAIN_EXCEEDED')
    return {'status':'COMPUTED','formula_id':'FX_COVERED_INTEREST_'+method.upper()+'_V1',
            'forward_domestic_per_foreign':forward,'forward_points':forward-spot,
            'quote_unit':domestic+'/'+foreign,'spot_forecast':False,
            'basis_credit_funding_spreads_and_transaction_costs_included':False}


def bond_cashflows(d):
    exact(d, ('par','settlement_date','cashflows','cashflows_complete','noncallable_fixed',
              'yield_rate','compounding_per_year','discount_day_count','accrual'))
    par=num(d,'par',positive=True)
    settlement=iso(d['settlement_date'])
    if d['cashflows_complete'] is not True or d['noncallable_fixed'] is not True:
        raise ValueError('EXPLICIT_COMPLETE_NONCALLABLE_FIXED_CASHFLOWS_REQUIRED')
    choice(d,'discount_day_count',('ACT365F',))
    y=num(d,'yield_rate')
    m=integer(d,'compounding_per_year',1,365)
    if 1+y/m<=0:
        raise ValueError('POSITIVE_DISCOUNT_BASE_REQUIRED')
    flows=d['cashflows']
    if not isinstance(flows,list) or not 1<=len(flows)<=1000:
        raise ValueError('ONE_TO_1000_CASHFLOWS_REQUIRED')
    present=[]
    previous=settlement
    for flow in flows:
        exact(flow,('date','amount'))
        day=iso(flow['date'])
        if day<=previous:
            raise ValueError('STRICTLY_INCREASING_FUTURE_CASHFLOW_DATES_REQUIRED')
        previous=day
        amount=num(flow,'amount',positive=True)
        t=(day-settlement).days/365
        factor=(1+y/m)**(-m*t)
        if not math.isfinite(factor) or factor<=0:
            raise ValueError('DISCOUNT_FACTOR_NUMERIC_DOMAIN_EXCEEDED')
        present.append({'date':flow['date'],'amount':amount,'time_years':t,'discount_factor':factor,'present_value':amount*factor})
    accrual=d['accrual']
    if not isinstance(accrual,dict) or 'method' not in accrual:
        raise ValueError('ACCRUAL_METHOD_REQUIRED')
    method=choice(accrual,'method',('supplied_amount','ACT365F','ACT360'))
    if method=='supplied_amount':
        exact(accrual,('method','amount'))
        accrued=num(accrual,'amount',low=0)
    else:
        exact(accrual,('method','annual_coupon_rate','last_coupon_date','next_coupon_date'))
        rate=num(accrual,'annual_coupon_rate',low=0)
        last,nxt=iso(accrual['last_coupon_date']),iso(accrual['next_coupon_date'])
        if not last<=settlement<nxt or nxt!=iso(flows[0]['date']):
            raise ValueError('CURRENT_COUPON_PERIOD_MUST_END_AT_FIRST_CASHFLOW')
        accrued=par*rate*(settlement-last).days/(365 if method=='ACT365F' else 360)
    dirty=math.fsum(x['present_value'] for x in present)
    if accrued>dirty:
        raise ValueError('ACCRUED_EXCEEDS_DIRTY_VALUE')
    return {'status':'COMPUTED','formula_id':'FIXED_CASHFLOW_PV_ACT365F_V1','cashflows':present,
            'dirty_value':dirty,'accrued_interest':accrued,'clean_value':dirty-accrued,
            'dirty_price_per_100_par':100*dirty/par,'clean_price_per_100_par':100*(dirty-accrued)/par,
            'accrual_method':method,'credit_default_model_included':False,
            'cashflow_completeness':'caller_asserted_not_independently_verified'}


def futures_pnl(d):
    exact(d,('signed_contracts','multiplier','price_unit','entry_at','entry_price','settlements',
             'fees','settlement_method','rounding','currency_decimals','terminal_state'))
    quantity=integer(d,'signed_contracts',-1000000000,1000000000)
    if quantity==0:
        raise ValueError('NONZERO_POSITION_REQUIRED')
    multiplier=num(d,'multiplier',positive=True)
    entry=num(d,'entry_price')
    fee=num(d,'fees',low=0)
    choice(d,'settlement_method',('variation_margin',))
    rounding=choice(d,'rounding',('unrounded_research','per_contract_half_up'))
    decimals=integer(d,'currency_decimals',0,8)
    terminal=choice(d,'terminal_state',('open','closed','cash_settled','physical_delivery_pending'))
    if not isinstance(d['price_unit'],str) or not re.fullmatch(r'[A-Z]{3}/[A-Za-z][A-Za-z0-9_-]*',d['price_unit']):
        raise ValueError('PRICE_UNIT_CURRENCY_PER_UNDERLYING_REQUIRED')
    previous_at=instant(d['entry_at'])
    settlements=d['settlements']
    if not isinstance(settlements,list) or not 1<=len(settlements)<=10000:
        raise ValueError('ONE_TO_10000_SETTLEMENTS_REQUIRED')
    ledger=[]
    # Decimal avoids losing the half-cent decision to binary floating point.
    with localcontext(Context(prec=50,rounding=ROUND_HALF_UP,Emin=-999,Emax=999,
                              capitals=1,clamp=0,flags=[],traps=[InvalidOperation,DivisionByZero,Overflow])):
        quantum=Decimal(1).scaleb(-decimals)
        def contract_money(price):
            money=Decimal(str(price))*Decimal(str(multiplier))
            return money.quantize(quantum,rounding=ROUND_HALF_UP) if rounding=='per_contract_half_up' else money
        previous_money=contract_money(entry)
        total=Decimal(0)
        for i,row in enumerate(settlements):
            exact(row,('at','price'))
            at=instant(row['at'])
            if at<previous_at or (i>0 and at==previous_at):
                raise ValueError('SETTLEMENT_TIMESTAMPS_MUST_INCREASE_FROM_ENTRY')
            price=num(row,'price')
            money=contract_money(price)
            variation=(money-previous_money)*quantity
            total+=variation
            ledger.append({'at':row['at'],'settlement_price':price,'variation_cash':float(variation),
                           'cumulative_variation_cash':float(total)})
            previous_at,previous_money=at,money
        gross=float(total)
        net=float(total-Decimal(str(fee)))
    return {'status':'COMPUTED','formula_id':'FIXED_FUTURES_VARIATION_V1','ledger':ledger,
            'gross_pnl':gross,'fees':fee,'net_pnl':net,'rounding':rounding,
            'terminal_state':terminal,'physical_delivery_completed':False,
            'margin_interest_funding_and_delivery_costs_included':False}


OPERATIONS = {name:globals()[name] for name in ('option_crr','implied_volatility','fx_forward','bond_cashflows','futures_pnl')}


def run(document):
    exact(document,('schema_version','action','operation','currency','information_cutoff','inputs_available_at','inputs'))
    if type(document['schema_version']) is not int or document['schema_version']!=1:
        raise ValueError('SCHEMA_VERSION_1_REQUIRED')
    if document['action']!='research':
        raise ValueError('RESEARCH_ACTION_ONLY')
    op=document['operation']
    if not isinstance(op,str) or op not in OPERATIONS:
        raise ValueError('UNKNOWN_OPERATION')
    unit=currency(document['currency'])
    cutoff=instant(document['information_cutoff'])
    available=instant(document['inputs_available_at'])
    if available>cutoff:
        raise ValueError('INPUTS_AFTER_INFORMATION_CUTOFF')
    inputs=copy.deepcopy(document['inputs'])
    try:
        output=OPERATIONS[op](inputs)
        if op=='fx_forward' and inputs['domestic_currency']!=unit:
            raise ValueError('DOMESTIC_CURRENCY_MUST_MATCH_OUTPUT')
        if op=='futures_pnl' and inputs['price_unit'].split('/')[0]!=unit:
            raise ValueError('PRICE_CURRENCY_MUST_MATCH_OUTPUT')
        if op=='futures_pnl' and (instant(inputs['entry_at'])>available or any(instant(row['at'])>available for row in inputs['settlements'])):
            raise ValueError('FUTURES_OBSERVATION_AFTER_INPUT_AVAILABILITY')
        output={'schema_version':1,'action':'research','operation':op,'currency':unit,
                'information_cutoff':document['information_cutoff'],'inputs_available_at':document['inputs_available_at'],
                'input_availability_basis':'caller_asserted_not_independently_verified',
                'resolved_inputs':inputs,**output}
        json.dumps(output,allow_nan=False)
        return output
    except (OverflowError,ZeroDivisionError,DecimalException) as exc:
        raise ValueError('NUMERIC_DOMAIN_EXCEEDED') from exc


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    def unique_object(pairs):
        result={}
        for key,value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY: '+key)
            result[key]=value
        return result
    result=run(json.loads(Path(args.input).read_text(encoding='utf-8-sig'),object_pairs_hook=unique_object))
    with Path(args.output).open('x',encoding='utf-8') as handle:
        json.dump(result,handle,indent=2,allow_nan=False)
        handle.write('\n')


if __name__=='__main__':
    main()
