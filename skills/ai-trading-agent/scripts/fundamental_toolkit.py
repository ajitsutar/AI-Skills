"""Offline fundamental calculations. Explicit annual inputs; no fetched or inferred forecasts."""
from __future__ import annotations
import argparse
import copy
import json
import math
import random
from pathlib import Path


def number(d, key, minimum=None, positive=False):
    if key not in d or d[key] is None:
        raise ValueError('MISSING_FIELD: ' + key)
    v = d[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError('FINITE_NUMBER_REQUIRED: ' + key)
    if positive and v <= 0 or minimum is not None and v < minimum:
        raise ValueError('OUT_OF_DOMAIN: ' + key)
    return float(v)


def fraction(d, key):
    v = number(d, key, minimum=0)
    if v > 1:
        raise ValueError('FRACTION_0_TO_1_REQUIRED: ' + key)
    return v


def ratio(a, b, label):
    if b <= 0:
        raise ValueError('POSITIVE_DENOMINATOR_REQUIRED: ' + label)
    return a / b


def result(operation, **values):
    return {'operation': operation, 'status': 'COMPUTED', 'forecast_basis': 'supplied_inputs_only', **values}


def ratios(d):
    """Each ratio independently reports missing inputs or invalid economic domains."""
    nonnegative={'current_assets','current_liabilities','cash','marketable_securities','receivables','interest_expense','revenue','cogs','average_assets'}
    n = lambda k: number(d, k, minimum=0 if k in nonnegative else None)
    formulas = {
        'roic': lambda: ratio(n('ebit') * (1-fraction(d, 'tax_rate')), n('average_invested_capital'), 'invested capital'),
        'current_ratio': lambda: ratio(n('current_assets'), n('current_liabilities'), 'current liabilities'),
        'quick_ratio': lambda: ratio(n('cash')+n('marketable_securities')+n('receivables'), n('current_liabilities'), 'current liabilities'),
        'interest_coverage': lambda: ratio(n('ebit'), n('interest_expense'), 'interest expense'),
        'gross_margin': lambda: ratio(n('revenue')-n('cogs'), n('revenue'), 'revenue'),
        'operating_margin': lambda: ratio(n('ebit'), n('revenue'), 'revenue'),
        'net_margin': lambda: ratio(n('net_income'), n('revenue'), 'revenue'),
        'asset_turnover': lambda: ratio(n('revenue'), n('average_assets'), 'average assets'),
        'equity_multiplier': lambda: ratio(n('average_assets'), n('average_equity'), 'average equity'),
        'roe': lambda: ratio(n('net_income'), n('average_equity'), 'average equity'),
        'fcf': lambda: n('cfo')-number(d, 'capex', minimum=0),
        'debt_to_equity': lambda: ratio(number(d, 'debt', minimum=0), n('equity'), 'equity'),
        'peg': lambda: ratio(ratio(number(d, 'price', positive=True), number(d, 'eps', positive=True), 'EPS'), number(d, 'eps_growth_rate', positive=True)*100, 'growth percentage points'),
    }
    values, unavailable = {}, {}
    inconsistent_liquidity = False
    if 'current_assets' in d:
        try:
            assets = number(d, 'current_assets', minimum=0)
            # A known subset already exceeding the total is inconsistent; omitted
            # components are not imputed as zero or made sufficient for a ratio.
            known = [number(d, k, minimum=0) for k in ('cash', 'marketable_securities', 'receivables') if k in d]
            inconsistent_liquidity = sum(known) > assets + 1e-9 * max(1, assets, sum(known))
        except ValueError:
            pass  # Each affected formula reports its own malformed/missing input.
    for key, fn in formulas.items():
        try:
            if inconsistent_liquidity and key in ('current_ratio', 'quick_ratio'):
                raise ValueError('INCONSISTENT_CURRENT_ASSET_COMPONENTS')
            values[key] = fn()
        except ValueError as exc:
            values[key] = None
            unavailable[key] = str(exc)
    if all(values[k] is not None for k in ('net_margin', 'asset_turnover', 'equity_multiplier')):
        values['dupont_roe'] = values['net_margin'] * values['asset_turnover'] * values['equity_multiplier']
    else:
        values['dupont_roe'] = None
    return result('ratios', ratios=values, unavailable=unavailable, status='PARTIAL' if unavailable else 'COMPUTED')


def applicability(d, allowed):
    if d.get('company_type') not in allowed:
        raise ValueError('MODEL_NOT_APPLICABLE: company_type must be ' + ', '.join(sorted(allowed)))
    if d.get('annual_periods_comparable') is not True:
        raise ValueError('COMPARABLE_ANNUAL_PERIODS_REQUIRED')


def piotroski(d):
    applicability(d, {'nonfinancial', 'public_manufacturing'})
    basis=d.get('turnover_basis')
    if basis not in ('beginning_assets','average_assets'):
        raise ValueError('EXPLICIT_TURNOVER_BASIS_REQUIRED')
    c, p = d['current'], d['prior']
    if not math.isclose(number(c,'beginning_assets',positive=True), number(p,'assets',positive=True), rel_tol=1e-9, abs_tol=1e-9):
        raise ValueError('CONSECUTIVE_COMPARABLE_ASSET_BALANCES_REQUIRED')
    def measures(x):
        start = number(x, 'beginning_assets', positive=True)
        assets = number(x, 'assets', positive=True)
        if number(x, 'current_assets', minimum=0) > assets + 1e-9 * max(1, assets):
            raise ValueError('CURRENT_ASSETS_EXCEED_TOTAL_ASSETS')
        avg = (start+assets)/2
        return {'roa': number(x, 'income_before_extraordinary')/start,
                'cfo': number(x, 'cfo')/start,
                'leverage': number(x, 'long_term_debt', minimum=0)/avg,
                'liquidity': ratio(number(x, 'current_assets', minimum=0), number(x, 'current_liabilities', minimum=0), 'current liabilities'),
                'margin': (number(x, 'sales', positive=True)-number(x, 'cogs', minimum=0))/number(x, 'sales', positive=True),
                'turnover': number(x, 'sales', positive=True)/(start if basis=='beginning_assets' else avg)}
    a, b = measures(c), measures(p)
    if type(c.get('equity_issued')) is not bool:
        raise ValueError('EXPLICIT_EQUITY_ISSUANCE_BOOLEAN_REQUIRED')
    signals = {'positive_roa': a['roa']>0, 'positive_cfo': a['cfo']>0,
               'improved_roa': a['roa']>b['roa'], 'cash_exceeds_income': a['cfo']>a['roa'],
               'lower_leverage': a['leverage']<b['leverage'], 'higher_liquidity': a['liquidity']>b['liquidity'],
               'no_equity_issued': not c['equity_issued'], 'higher_margin': a['margin']>b['margin'],
               'higher_turnover': a['turnover']>b['turnover']}
    return result('piotroski', score=sum(signals.values()), signals={k:int(v) for k,v in signals.items()},
                  turnover_basis=basis,
                  measures={'current': a, 'prior': b}, limitation='Historical accounting screen, originally high book-to-market portfolios; not a return prediction.')


def altman(d):
    applicability(d, {'public_manufacturing'})
    a = number(d, 'assets', positive=True)
    x = [number(d, 'working_capital')/a, number(d, 'retained_earnings')/a,
         number(d, 'ebit')/a, number(d, 'market_equity', minimum=0)/number(d, 'total_liabilities', positive=True),
         number(d, 'sales', minimum=0)/a]
    z = sum(v*w for v,w in zip(x, [1.2,1.4,3.3,.6,1.0]))
    return result('altman', variant='public_manufacturing_altman_2002_restatement_decimal_ratios', score=z, components=x,
                  zone='distress' if z<1.81 else 'grey' if z<=2.99 else 'historical_safe_zone',
                  limitation='Historical discriminant score; not calibrated default probability or a solvency guarantee.')


def beneish(d):
    applicability(d, {'nonfinancial', 'public_manufacturing'})
    c, p = d['current'], d['prior']
    def fields(x):
        y={k:number(x,k,minimum=0) for k in ('receivables','current_assets','net_ppe','depreciation','depreciation_amortization','sga','current_liabilities','long_term_debt','cash','current_maturities_ltd','tax_payable')}
        y.update({k:number(x,k,positive=True) for k in ('sales','assets')})
        y['cogs']=number(x,'cogs',minimum=0)
        if y['cogs']>=y['sales']:
            raise ValueError('BENEISH_POSITIVE_GROSS_MARGIN_REQUIRED')
        if y['depreciation_amortization']<y['depreciation']:
            raise ValueError('DEPRECIATION_AMORTIZATION_LESS_THAN_DEPRECIATION')
        if y['current_assets']+y['net_ppe']>y['assets'] or y['cash']>y['current_assets'] or y['current_maturities_ltd']+y['tax_payable']>y['current_liabilities']:
            raise ValueError('INCONSISTENT_BALANCE_SHEET_COMPONENTS')
        return y
    a,b=fields(c),fields(p)
    div=lambda u,v:ratio(u,v,'Beneish component')
    idx={'DSRI':div(a['receivables']/a['sales'], b['receivables']/b['sales']),
         'GMI':div((b['sales']-b['cogs'])/b['sales'], (a['sales']-a['cogs'])/a['sales']),
         'AQI':div(1-(a['current_assets']+a['net_ppe'])/a['assets'], 1-(b['current_assets']+b['net_ppe'])/b['assets']),
         'SGI':a['sales']/b['sales'],
         'DEPI':div(div(b['depreciation'],b['depreciation']+b['net_ppe']), div(a['depreciation'],a['depreciation']+a['net_ppe'])),
         'SGAI':div(a['sga']/a['sales'],b['sga']/b['sales']),
         'LVGI':div((a['current_liabilities']+a['long_term_debt'])/a['assets'], (b['current_liabilities']+b['long_term_debt'])/b['assets'])}
    delta=lambda k:a[k]-b[k]
    idx['TATA']=(delta('current_assets')-delta('cash')-delta('current_liabilities')+delta('current_maturities_ltd')+delta('tax_payable')-a['depreciation_amortization'])/a['assets']
    weights={'DSRI':.920,'GMI':.528,'AQI':.404,'SGI':.892,'DEPI':.115,'SGAI':-.172,'LVGI':-.327,'TATA':4.679}
    score=-4.840+sum(idx[k]*weights[k] for k in weights)
    return result('beneish', score=score, indices=idx, variant='eight_variable_original_balance_sheet_accruals',
                  limitation='Screening score only; no fraud verdict, probability or universal threshold. No zero-denominator imputation.')


def wacc(d):
    e=number(d,'market_equity',positive=True); debt=number(d,'market_debt',minimum=0)
    ke=number(d,'cost_equity',positive=True); kd=number(d,'pretax_cost_debt',minimum=0)
    tax=fraction(d,'tax_rate')
    return result('wacc', wacc=e/(e+debt)*ke+debt/(e+debt)*kd*(1-tax), equity_weight=e/(e+debt), debt_weight=debt/(e+debt))


def dcf(d):
    kind=d.get('cash_flow_type')
    if kind not in ('FCFF','FCFE'):
        raise ValueError('CASH_FLOW_TYPE_FCFF_OR_FCFE_REQUIRED')
    expected='WACC' if kind=='FCFF' else 'cost_of_equity'
    if d.get('discount_rate_basis')!=expected:
        raise ValueError('DISCOUNT_BASIS_MISMATCH: '+expected)
    rate=number(d,'discount_rate',positive=True); g=number(d,'terminal_growth')
    if not -1<g<rate:
        raise ValueError('TERMINAL_GROWTH_MUST_BE_GREATER_THAN_MINUS_ONE_AND_LESS_THAN_DISCOUNT_RATE')
    cash=d['annual_cash_flows']
    if not isinstance(cash,list) or not cash:
        raise ValueError('NONEMPTY_ANNUAL_CASH_FLOWS_REQUIRED')
    cash=[number({'v':v},'v') for v in cash]
    terminal=number(d,'terminal_next_cash_flow',minimum=0)
    rows=[{'year':i,'cash_flow':cf,'present_value':cf/(1+rate)**i} for i,cf in enumerate(cash,1)]
    terminal_value=terminal/(rate-g); pvterminal=terminal_value/(1+rate)**len(cash)
    stream=sum(r['present_value'] for r in rows)+pvterminal
    bridge=d['equity_bridge']
    extra=number(bridge,'excess_cash',minimum=0)+number(bridge,'nonoperating_assets',minimum=0)
    debt=number(bridge,'debt',minimum=0); claims=number(bridge,'other_claims',minimum=0)
    if kind=='FCFE' and (debt or claims):
        raise ValueError('FCFE_ALREADY_AFTER_DEBT_AND_OTHER_CLAIMS')
    equity=stream+extra-debt-claims
    return result('dcf', cash_flow_type=kind, annual=rows, terminal_value=terminal_value, terminal_present_value=pvterminal,
                  cash_flow_value=stream, enterprise_value=stream if kind=='FCFF' else None, equity_value=equity,
                  per_share=equity/number(d,'shares',positive=True), bridge=copy.deepcopy(bridge),
                  limitation='Year-end annual cash timing; terminal next-year cash must explicitly include sustainable reinvestment. Negative equity is retained.')


def reverse_dcf(d):
    """Solve constant growth of positive base CF; other assumptions stay fixed."""
    base=number(d,'base_cash_flow',positive=True); target=number(d,'target_equity_value')
    n=d['years']
    if type(n) is not int or not 1<=n<=100:
        raise ValueError('YEARS_1_TO_100_REQUIRED')
    low=number(d,'growth_low'); high=number(d,'growth_high')
    if not -1<low<high:
        raise ValueError('INVALID_GROWTH_BRACKET')
    def evaluate(g):
        job=copy.deepcopy(d['valuation'])
        job['annual_cash_flows']=[base*(1+g)**i for i in range(1,n+1)]
        job['terminal_next_cash_flow']=job['annual_cash_flows'][-1]*(1+number(job,'terminal_growth'))
        return dcf(job)['equity_value']
    if not evaluate(low)<=target<=evaluate(high):
        raise ValueError('TARGET_OUTSIDE_GROWTH_BRACKET')
    for _ in range(100):
        mid=(low+high)/2
        if evaluate(mid)<target: low=mid
        else: high=mid
    growth=(low+high)/2
    return result('reverse_dcf', implied_annual_growth=growth, implied_equity_value=evaluate(growth), target_equity_value=target,
                  limitation='Implied constant cash-flow growth conditional on all supplied assumptions; not an earnings forecast.')


def ddm(d):
    r=number(d,'cost_equity',positive=True);g=number(d,'growth')
    if not -1<g<r: raise ValueError('INVALID_GORDON_GROWTH')
    return result('ddm', per_share=number(d,'next_dividend_per_share',minimum=0)/(r-g))


def residual_income(d):
    book=number(d,'opening_book_equity',positive=True); initial=book
    r=number(d,'cost_equity',positive=True); rows=[]; value=book
    if not isinstance(d['years'],list) or not 1<=len(d['years'])<=100: raise ValueError('ONE_TO_100_ANNUAL_PERIODS_REQUIRED')
    for i,y in enumerate(d['years'],1):
        earnings=number(y,'net_income');dividend=number(y,'dividends',minimum=0)
        ri=earnings-r*book;closing=book+earnings-dividend
        rows.append({'year':i,'opening_book_equity':book,'residual_income':ri,'closing_book_equity':closing})
        value+=ri/(1+r)**i;book=closing
    tv=number(d,'terminal_residual_income_value')
    value+=tv/(1+r)**len(rows)
    return result('residual_income',equity_value=value,opening_book_equity=initial,annual=rows,
                  limitation='Clean-surplus assumption: no issuance, repurchases, OCI or other direct equity changes. Terminal RI value is supplied at final forecast date.')


def sotp(d):
    seen=set(); values=[]
    if not isinstance(d['segments'], list) or not d['segments']: raise ValueError('NONEMPTY_SEGMENTS_REQUIRED')
    for s in d['segments']:
        if not isinstance(s,dict): raise ValueError('SEGMENT_OBJECT_REQUIRED')
        if not isinstance(s.get('id'),str) or not s['id'].strip() or s['id'] in seen: raise ValueError('UNIQUE_SEGMENT_IDS_REQUIRED')
        seen.add(s['id'])
        values.append(number(s,'enterprise_value'))
    ev=sum(values)-number(d,'corporate_cost_present_value',minimum=0)
    equity=ev+number(d,'excess_cash',minimum=0)+number(d,'nonoperating_assets',minimum=0)-number(d,'debt',minimum=0)-number(d,'other_claims',minimum=0)
    return result('sotp', enterprise_value=ev,equity_value=equity,per_share=equity/number(d,'shares',positive=True),
                  limitation='All segment values are enterprise values; caller must eliminate intercompany and overlapping assets.')


def forecast(d):
    """Reconciled single-business annual model, explicit inputs, no tax loss carryforward."""
    if d.get('company_type') not in ('nonfinancial','public_manufacturing'):
        raise ValueError('FORECAST_REQUIRES_NONFINANCIAL_COMPANY')
    if d.get('tax_loss_policy')!='no_benefit': raise ValueError('TAX_LOSS_POLICY_NO_BENEFIT_REQUIRED')
    b=copy.deepcopy(d['opening']);keys=('cash','receivables','inventory','net_ppe','payables','debt','equity')
    b={k:number(b,k,minimum=None if k=='equity' else 0) for k in keys}
    def residual(x): return x['cash']+x['receivables']+x['inventory']+x['net_ppe']-x['payables']-x['debt']-x['equity']
    if abs(residual(b))>1e-8*max(1,sum(abs(v) for v in b.values())): raise ValueError('OPENING_BALANCE_SHEET_NOT_BALANCED')
    revenue=number(d,'opening_revenue',positive=True);rows=[]
    if not isinstance(d['years'],list) or not 1<=len(d['years'])<=100: raise ValueError('ONE_TO_100_ANNUAL_PERIODS_REQUIRED')
    for i,y in enumerate(d['years'],1):
        growth=number(y,'revenue_growth')
        if growth<=-1: raise ValueError('REVENUE_GROWTH_ABOVE_MINUS_ONE_REQUIRED')
        revenue*=1+growth;cogs=revenue*fraction(y,'cogs_fraction');opex=revenue*fraction(y,'opex_fraction')
        dep=number(y,'depreciation',minimum=0);capex=number(y,'capex',minimum=0)
        if dep>b['net_ppe']+capex: raise ValueError('DEPRECIATION_EXCEEDS_AVAILABLE_PPE')
        interest=b['debt']*number(y,'interest_rate',minimum=0);ebit=revenue-cogs-opex-dep
        tax=fraction(y,'tax_rate');cash_tax=max(0,ebit-interest)*tax;ni=ebit-interest-cash_tax
        ar=revenue*fraction(y,'receivables_fraction');inv=cogs*fraction(y,'inventory_fraction');ap=cogs*fraction(y,'payables_fraction')
        dwc=(ar+inv-ap)-(b['receivables']+b['inventory']-b['payables'])
        cfo=ni+dep-dwc;new_debt=number(y,'new_debt',minimum=0);repay=number(y,'debt_repayment',minimum=0)
        if repay>b['debt']+new_debt: raise ValueError('DEBT_REPAYMENT_EXCEEDS_DEBT')
        issuance=number(y,'equity_issuance',minimum=0);dividends=number(y,'dividends',minimum=0)
        cash=b['cash']+cfo-capex+new_debt-repay+issuance-dividends
        if cash< -1e-8: raise ValueError('UNFUNDED_CASH_DEFICIT: year '+str(i))
        close={'cash':cash,'receivables':ar,'inventory':inv,'net_ppe':b['net_ppe']+capex-dep,'payables':ap,
               'debt':b['debt']+new_debt-repay,'equity':b['equity']+ni+issuance-dividends}
        # Unlevered no-benefit tax avoids assuming a nonexistent tax shield in losses.
        unlevered_tax=max(0,ebit)*tax
        rows.append({'year':i,'revenue':revenue,'cogs':cogs,'opex':opex,'depreciation':dep,'ebit':ebit,'interest':interest,
                     'cash_taxes':cash_tax,'net_income':ni,'change_operating_working_capital':dwc,'cfo':cfo,
                     'capex':capex,'cash_from_investing':-capex,'cash_from_financing':new_debt-repay+issuance-dividends,
                     'new_debt':new_debt,'debt_repayment':repay,'equity_issuance':issuance,'dividends':dividends,
                     'opening_balance_sheet':copy.deepcopy(b),
                     'fcff':ebit-unlevered_tax+dep-capex-dwc,'fcfe':cfo-capex+new_debt-repay,
                     'balance_sheet':close,'balance_residual':residual(close),
                     'cash_conservation_residual':cash-(b['cash']+cfo-capex+new_debt-repay+issuance-dividends)})
        b=close
    return result('forecast',annual=rows,limitation='Simplified annual single-business model: no leases, deferred taxes, OCI, acquisitions, goodwill or loss carryforwards. Interest on opening debt; explicit financing, no hidden plug.')


def monte_carlo(d):
    count=d['draws'];seed=d['seed']
    if type(count) is not int or not 2<=count<=100000 or type(seed) is not int: raise ValueError('BOUNDED_DRAWS_AND_INTEGER_SEED_REQUIRED')
    dist=d['distributions']
    if set(dist)!= {'discount_rate','terminal_growth','cash_flow_multiplier'}: raise ValueError('THREE_EXPLICIT_DISTRIBUTIONS_REQUIRED')
    bounds={}
    for k in sorted(dist):
        v=dist[k]
        lo=number(v,'low');mode=number(v,'mode');hi=number(v,'high')
        if not lo<=mode<=hi or lo==hi: raise ValueError('TRIANGULAR_LOW_MODE_HIGH_REQUIRED: '+k)
        bounds[k]=(lo,mode,hi)
    if bounds['discount_rate'][0]<=max(0,bounds['terminal_growth'][2]) or bounds['terminal_growth'][0]<=-1 or bounds['cash_flow_multiplier'][0]<0:
        raise ValueError('DISTRIBUTION_SUPPORT_INVALID_FOR_DCF')
    rng=random.Random(seed);samples=[]
    for _ in range(count):
        z={k:rng.triangular(v[0],v[2],v[1]) for k,v in bounds.items()};job=copy.deepcopy(d['valuation'])
        job['discount_rate']=z['discount_rate'];job['terminal_growth']=z['terminal_growth']
        job['annual_cash_flows']=[number({'cf':x},'cf')*z['cash_flow_multiplier'] for x in job['annual_cash_flows']]
        job['terminal_next_cash_flow']=number(job,'terminal_next_cash_flow')*z['cash_flow_multiplier']
        samples.append(dcf(job)['equity_value'])
    samples.sort()
    def quantile(q):
        position=(len(samples)-1)*q;lo=int(position);hi=min(lo+1,len(samples)-1)
        return samples[lo]+(position-lo)*(samples[hi]-samples[lo])
    return result('monte_carlo',seed=seed,draws=count,mean_equity_value=sum(samples)/count,
                  quantiles={str(q):quantile(q) for q in (.05,.25,.5,.75,.95)},
                  distribution_assumption='Independent triangular supplied scenario assumptions; common multiplier scales all forecast and terminal CF.',
                  limitation='Scenario distribution, not calibrated probability or confidence interval; no learned forecasts.')


OPERATIONS={'ratios':ratios,'piotroski':piotroski,'altman':altman,'beneish':beneish,'wacc':wacc,'dcf':dcf,
            'reverse_dcf':reverse_dcf,'ddm':ddm,'residual_income':residual_income,'sotp':sotp,'forecast':forecast,'monte_carlo':monte_carlo}


RATIO_FIELDS=set('ebit tax_rate average_invested_capital current_assets current_liabilities cash marketable_securities receivables interest_expense revenue cogs net_income average_assets average_equity cfo capex debt equity price eps eps_growth_rate'.split())
DCF_FIELDS=set('cash_flow_type discount_rate_basis discount_rate terminal_growth annual_cash_flows terminal_next_cash_flow shares equity_bridge'.split())
PIOTROSKI_PERIOD_FIELDS=set('beginning_assets assets income_before_extraordinary cfo long_term_debt current_assets current_liabilities sales cogs'.split())
BENEISH_PERIOD_FIELDS=set('sales cogs receivables current_assets net_ppe assets depreciation depreciation_amortization sga current_liabilities long_term_debt cash current_maturities_ltd tax_payable'.split())
FORECAST_YEAR_FIELDS=set('revenue_growth cogs_fraction opex_fraction depreciation capex interest_rate tax_rate receivables_fraction inventory_fraction payables_fraction new_debt debt_repayment equity_issuance dividends'.split())
SCHEMAS={
    'ratios': RATIO_FIELDS,
    'piotroski': set('company_type annual_periods_comparable turnover_basis current prior'.split()),
    'altman': set('company_type annual_periods_comparable assets working_capital retained_earnings ebit market_equity total_liabilities sales'.split()),
    'beneish': set('company_type annual_periods_comparable current prior'.split()),
    'wacc': set('market_equity market_debt cost_equity pretax_cost_debt tax_rate'.split()),
    'dcf': DCF_FIELDS,
    'reverse_dcf': set('base_cash_flow target_equity_value years growth_low growth_high valuation'.split()),
    'ddm': set('next_dividend_per_share cost_equity growth'.split()),
    'residual_income': set('opening_book_equity cost_equity years terminal_residual_income_value'.split()),
    'sotp': set('segments corporate_cost_present_value excess_cash nonoperating_assets debt other_claims shares'.split()),
    'forecast': set('company_type tax_loss_policy opening_revenue opening years'.split()),
    'monte_carlo': set('seed draws valuation distributions'.split())}


def object_shape(value, allowed, required, path):
    if not isinstance(value, dict):
        raise ValueError('OBJECT_REQUIRED: '+path)
    unknown=set(value)-allowed
    if unknown:
        raise ValueError('UNKNOWN_FIELDS: '+path+'.'+','.join(sorted(str(k) for k in unknown)))
    missing=required-set(value)
    if missing:
        raise ValueError('MISSING_FIELD: '+path+'.'+','.join(sorted(missing)))


def object_rows(value, fields, path):
    if not isinstance(value, list) or not value:
        raise ValueError('NONEMPTY_OBJECT_LIST_REQUIRED: '+path)
    for i, row in enumerate(value):
        object_shape(row, fields, fields, f'{path}[{i}]')


def validate_schema(d):
    """Reject unsupported assumptions before calculation; metadata is explicit."""
    operation=d.get('operation')
    if operation=='piotroski' and d.get('turnover_basis') not in ('beginning_assets','average_assets'):
        raise ValueError('EXPLICIT_TURNOVER_BASIS_REQUIRED')
    fields=SCHEMAS[operation]
    common={'operation','currency','amount_unit','example_context'}
    required={'operation','currency','amount_unit'} | (set() if operation=='ratios' else fields)
    object_shape(d, fields | common, required, operation)
    if 'example_context' in d and (not isinstance(d['example_context'],str) or not d['example_context'].strip()):
        raise ValueError('NONEMPTY_CONTEXT_STRING_REQUIRED')
    if operation in ('piotroski','beneish'):
        base=PIOTROSKI_PERIOD_FIELDS if operation=='piotroski' else BENEISH_PERIOD_FIELDS
        current=base | ({'equity_issued'} if operation=='piotroski' else set())
        object_shape(d['current'],current,current,operation+'.current')
        object_shape(d['prior'],base,base,operation+'.prior')
    if operation in ('dcf','reverse_dcf','monte_carlo'):
        valuation=d if operation=='dcf' else d['valuation']
        if operation!='dcf':
            # Nested units can be repeated for clarity but never silently converted.
            object_shape(valuation,DCF_FIELDS | {'currency','amount_unit'},DCF_FIELDS,operation+'.valuation')
            for key in ('currency','amount_unit'):
                if key in valuation and valuation[key]!=d[key]:
                    raise ValueError('NESTED_VALUATION_UNIT_MISMATCH: '+key)
        bridge={'excess_cash','nonoperating_assets','debt','other_claims'}
        object_shape(valuation['equity_bridge'],bridge,bridge,operation+'.equity_bridge')
    if operation=='monte_carlo':
        fields={'discount_rate','terminal_growth','cash_flow_multiplier'}
        object_shape(d['distributions'],fields,fields,'monte_carlo.distributions')
        for key in fields:
            object_shape(d['distributions'][key],{'low','mode','high'},{'low','mode','high'},'distributions.'+key)
    if operation=='residual_income':
        object_rows(d['years'],{'net_income','dividends'},'residual_income.years')
    if operation=='sotp':
        object_rows(d['segments'],{'id','enterprise_value'},'sotp.segments')
    if operation=='forecast':
        fields={'cash','receivables','inventory','net_ppe','payables','debt','equity'}
        object_shape(d['opening'],fields,fields,'forecast.opening')
        object_rows(d['years'],FORECAST_YEAR_FIELDS,'forecast.years')


def run(d):
    if not isinstance(d,dict): raise ValueError('JSON_OBJECT_REQUIRED')
    if d.get('operation') not in OPERATIONS: raise ValueError('UNKNOWN_OPERATION')
    if any(not isinstance(d.get(k),str) or not d[k].strip() for k in ('currency','amount_unit')):
        raise ValueError('CURRENCY_AND_AMOUNT_UNIT_REQUIRED')
    validate_schema(d)
    answer=OPERATIONS[d['operation']](d)
    answer.update(currency=d['currency'],amount_unit=d['amount_unit'],formula_id='fundamental-toolkit-v1.'+d['operation'],
                  numerical_basis='IEEE754 binary64; no intermediate rounding; annual year-end timing')
    if d['operation']=='piotroski': answer['formula_id']+='.'+answer['turnover_basis']
    if 'per_share' in answer:
        answer['per_share_unit']=d['currency']+' per share'
        if d['operation'] in ('dcf','sotp'):
            answer['shares_scale_convention']='Share count uses the same scale as monetary amounts (e.g. millions of shares for monetary millions).'
    # Reject overflow rather than publish a successful result containing NaN/Infinity.
    json.dumps(answer,allow_nan=False)
    return answer


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',required=True);p.add_argument('--output')
    args=p.parse_args()
    try:
        output=run(json.loads(Path(args.input).read_text(encoding='utf-8-sig')))
        text=json.dumps(output,indent=2,allow_nan=False)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        text=json.dumps({'status':'INVALID_INPUT','error':str(exc)},indent=2)
        if args.output:
            with Path(args.output).open('x',encoding='utf-8') as stream: stream.write(text+'\n')
        else: print(text)
        raise SystemExit(2)
    if args.output:
        with Path(args.output).open('x',encoding='utf-8') as stream: stream.write(text+'\n')
    else: print(text)


if __name__=='__main__': main()
