"""Original supplied-data scenario/trend/pair calculations; no live trading or ARMA.

Every request field is explicit. No dependencies beyond the Python standard library.
Formulas and model limits: references/time-series-toolkit.md.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re


def require(test, message):
    if not test:
        raise ValueError(message)


def unique_object(pairs):
    """Reject ambiguous JSON records before any fields can be overwritten."""
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY:' + key)
        result[key] = value
    return result


def shape(value, required):
    require(isinstance(value, dict), 'OBJECT_REQUIRED')
    require(set(value) == set(required), 'EXACT_FIELDS_REQUIRED:' + ','.join(sorted(set(required) ^ set(value))))


def number(value, name, minimum=None, positive=False):
    require(type(value) in (int, float), 'JSON_NUMBER_REQUIRED:' + name)
    try:
        v = float(value)
    except (ValueError, OverflowError):
        raise ValueError('FINITE_REQUIRED:' + name) from None
    require(math.isfinite(v), 'FINITE_REQUIRED:' + name)
    require(minimum is None or v >= minimum, 'BELOW_MINIMUM:' + name)
    require(not positive or v > 0, 'POSITIVE_REQUIRED:' + name)
    return v


def integer(value, name, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, 'INTEGER_RANGE:' + name)
    return value


def label(value, name):
    require(isinstance(value, str) and value.strip() == value and bool(value), 'LABEL_REQUIRED:' + name)
    return value


def instant(value):
    # Fixed UTC representation avoids permissive fromisoformat offset normalization.
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value) is not None,
            'UTC_TIMESTAMP_REQUIRED')
    try:
        return datetime.fromisoformat(value[:-1] + '+00:00')
    except ValueError:
        raise ValueError('INVALID_TIMESTAMP') from None


def finite_output(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'NUMERIC_OVERFLOW_OR_UNDERFLOW')
    elif isinstance(value, dict):
        for v in value.values(): finite_output(v)
    elif isinstance(value, list):
        for v in value: finite_output(v)


def ordered_rows(rows, fields, as_of):
    require(isinstance(rows, list) and rows, 'NONEMPTY_ROWS_REQUIRED')
    previous, converted = None, []
    for row in rows:
        shape(row, ('timestamp', 'available_at', *fields))
        at, available = instant(row['timestamp']), instant(row['available_at'])
        require(previous is None or at > previous, 'STRICT_TIME_ORDER_REQUIRED')
        require(at <= available <= as_of, 'ROW_AVAILABILITY_OR_CUTOFF')
        previous = at
        converted.append((at, available, {key:number(row[key], key) for key in fields}))
    return converted


def gbm(d):
    shape(d, ('symbol','price_unit','price_basis','initial_price','parameters_available_at','start_at',
              'mu','sigma','horizon_years','steps','paths','seed','year_basis','distribution','measure',
              'risk_free_rate','dividend_yield','as_of'))
    for key in ('symbol','price_unit','price_basis'): label(d[key], key)
    as_of, start = instant(d['as_of']), instant(d['start_at'])
    require(instant(d['parameters_available_at']) <= as_of == start, 'SCENARIO_START_MUST_EQUAL_AS_OF')
    require(d['year_basis'] == 'ACT_365_FIXED_SECONDS', 'YEAR_BASIS_UNSUPPORTED')
    require(d['distribution'] == 'independent_standard_normal_log_increments', 'DISTRIBUTION_UNSUPPORTED')
    require(d['measure'] in ('real_world_scenario','risk_neutral'), 'MEASURE_REQUIRED')
    mu, sigma = number(d['mu'],'mu'), number(d['sigma'],'sigma',0)
    if d['measure'] == 'risk_neutral':
        rate, div = number(d['risk_free_rate'],'risk_free_rate'), number(d['dividend_yield'],'dividend_yield',0)
        require(math.isclose(mu, rate-div, rel_tol=1e-12, abs_tol=1e-12), 'RISK_NEUTRAL_MU_MUST_EQUAL_RATE_MINUS_YIELD')
    else:
        require(d['risk_free_rate'] is None and d['dividend_yield'] is None, 'REAL_WORLD_RATE_FIELDS_MUST_BE_NULL')
    s0, horizon = number(d['initial_price'],'initial_price',positive=True), number(d['horizon_years'],'horizon_years',positive=True)
    steps, paths = integer(d['steps'],'steps',1,100000), integer(d['paths'],'paths',1,100000)
    seed = integer(d['seed'],'seed',0,2**63-1)
    require(paths * (steps+1) <= 1000000, 'PATH_CELL_LIMIT')
    dt = horizon/steps
    require(dt > 0, 'TIME_STEP_UNDERFLOW')
    drift, diffusion = (mu-0.5*sigma*sigma)*dt, sigma*math.sqrt(dt)
    rng = random.Random(seed)
    # Original fixed Box-Muller transform, no cached partner: two random() calls per step.
    # random()'s documented reproducible sequence is isolated from ambient state.
    generated = []
    for _ in range(paths):
        path = [s0]
        for _ in range(steps):
            u, v = 1.0-rng.random(), rng.random()
            z = math.sqrt(-2*math.log(u))*math.cos(2*math.pi*v)
            next_price = path[-1]*math.exp(drift+diffusion*z)
            require(math.isfinite(next_price) and next_price > 0, 'PATH_OVERFLOW_OR_UNDERFLOW')
            path.append(next_price)
        generated.append(path)
    terminal = [path[-1] for path in generated]
    expected = s0*math.exp(mu*horizon)
    variance = s0*s0*math.exp(2*mu*horizon)*math.expm1(sigma*sigma*horizon)
    require(math.isfinite(expected) and expected > 0, 'EXPECTED_PRICE_OVERFLOW_OR_UNDERFLOW')
    require(math.isfinite(variance) and (sigma == 0 or variance > 0), 'VARIANCE_OVERFLOW_OR_UNDERFLOW')
    end = start+timedelta(seconds=horizon*365*86400)
    return {'method':'exact-gbm-step-box-muller-mt19937-v1','paths':generated,
            'time_offsets_years':[i*dt for i in range(steps+1)],'end_at':end.isoformat().replace('+00:00','Z'),
            'expected_terminal_price':expected,'terminal_price_variance':variance,
            'sample_terminal_mean':math.fsum(terminal)/paths,
            'rng':'Python random.Random(seed).random; uncached Box-Muller; path-major',
            'python_version':platform.python_version(),'assumptions':'Constant arithmetic price drift and volatility; independent Gaussian increments; positive lognormal prices; no jumps, costs or parameter estimation.',
            'limitation':'Scenario distribution under supplied assumptions, not a fitted prediction or actual market probability. Negative-price instruments unsupported.'}


def trend(d):
    shape(d, ('symbol','value_unit','price_basis','time_unit','method','as_of','rows'))
    for key in ('symbol','value_unit','price_basis'): label(d[key],key)
    require(d['time_unit'] in ('second','hour','day'), 'TIME_UNIT_UNSUPPORTED')
    require(d['method']=='backward_secant_midpoint_acceleration', 'TREND_METHOD_UNSUPPORTED')
    rows = ordered_rows(d['rows'], ('value',), instant(d['as_of']))
    seconds = {'second':1.,'hour':3600.,'day':86400.}[d['time_unit']]
    result, previous_velocity = [], None
    for i,(at,available,values) in enumerate(rows):
        velocity, acceleration = None, None
        if i:
            interval=(at-rows[i-1][0]).total_seconds()/seconds
            velocity=(values['value']-rows[i-1][2]['value'])/interval
        if i>1:
            midpoint_interval=(at-rows[i-2][0]).total_seconds()/(2*seconds)
            acceleration=(velocity-previous_velocity)/midpoint_interval
        result.append({'timestamp':d['rows'][i]['timestamp'],'velocity':velocity,'acceleration':acceleration,
                       'available_at':max(r[1] for r in rows[max(0,i-2):i+1]).isoformat().replace('+00:00','Z')})
        previous_velocity=velocity
    return {'method':d['method'],'rows':result,'velocity_unit':d['value_unit']+'/'+d['time_unit'],
            'acceleration_unit':d['value_unit']+'/'+d['time_unit']+'^2',
            'limitation':'Causal backward interval slope and difference of adjacent secant slopes at their midpoints; attached to current observation, not an exact continuous derivative. No smoothing or interpolation.'}


def pair_ols(d):
    shape(d, ('x_symbol','y_symbol','x_unit','y_unit','price_basis','train_cutoff','as_of',
              'standard_deviation','minimum_x_variance','minimum_spread_std','train_rows','test_rows'))
    for key in ('x_symbol','y_symbol','x_unit','y_unit','price_basis'): label(d[key],key)
    require(d['x_symbol'] != d['y_symbol'],'DISTINCT_PAIR_SYMBOLS_REQUIRED')
    require(d['standard_deviation']=='population_training_residual', 'STD_CONVENTION_UNSUPPORTED')
    cutoff, as_of = instant(d['train_cutoff']), instant(d['as_of'])
    require(cutoff <= as_of,'TRAIN_CUTOFF_AFTER_AS_OF')
    train=ordered_rows(d['train_rows'],('x','y'),cutoff)
    test=ordered_rows(d['test_rows'],('x','y'),as_of)
    require(len(train)>=3,'THREE_TRAIN_ROWS_REQUIRED')
    require(test[0][0] > cutoff,'TEST_MUST_FOLLOW_TRAIN_CUTOFF')
    min_var=number(d['minimum_x_variance'],'minimum_x_variance',positive=True)
    min_sd=number(d['minimum_spread_std'],'minimum_spread_std',positive=True)
    xs=[row[2]['x'] for row in train];ys=[row[2]['y'] for row in train]
    xm,ym=math.fsum(xs)/len(xs),math.fsum(ys)/len(ys)
    centered_x=[x-xm for x in xs]
    denominator=math.fsum(x*x for x in centered_x)
    require(denominator/len(xs)>=min_var,'INSUFFICIENT_X_VARIANCE')
    beta=math.fsum(x*(y-ym) for x,y in zip(centered_x,ys))/denominator
    alpha=ym-beta*xm
    # Centered arithmetic reduces cancellation; equivalent to y-alpha-beta*x.
    residuals=[(y-ym)-beta*(x-xm) for x,y in zip(xs,ys)]
    mean=math.fsum(residuals)/len(residuals)
    sd=math.sqrt(math.fsum((r-mean)**2 for r in residuals)/len(residuals))
    require(sd>=min_sd,'INSUFFICIENT_TRAIN_RESIDUAL_STD')
    applied=[]
    for original,(_,_,row) in zip(d['test_rows'],test):
        residual=(row['y']-ym)-beta*(row['x']-xm)
        applied.append({'timestamp':original['timestamp'],'available_at':original['available_at'],
                        'spread':residual,'z_score':(residual-mean)/sd})
    return {'method':'train-only-intercept-ols-population-residual-z-v1','alpha':alpha,'beta':beta,
            'beta_unit':d['y_unit']+'/'+d['x_unit'],'spread_unit':d['y_unit'],
            'train_x_mean':xm,'train_y_mean':ym,'train_residuals':residuals,
            'train_residual_mean':mean,'train_residual_population_std':sd,'test_rows':applied,
            'train_observations':len(train),'train_cutoff':d['train_cutoff'],
            'limitation':'Descriptive fixed-pair spread normalization only. No cointegration/stationarity test, pair selection, predictive claim, trades, short borrow, costs or execution replay.'}


def run(document):
    shape(document, ('schema_version','operation','inputs'))
    require(type(document['schema_version']) is int and document['schema_version']==1,'SCHEMA_VERSION_1_REQUIRED')
    operations={'gbm':gbm,'trend':trend,'pair_ols':pair_ols}
    require(isinstance(document['operation'],str) and document['operation'] in operations,'OPERATION_UNSUPPORTED')
    try:
        result=operations[document['operation']](document['inputs'])
        finite_output(result)
    except (OverflowError,ZeroDivisionError):
        raise ValueError('NUMERIC_OVERFLOW_OR_UNDERFLOW') from None
    result.update({'schema_version':1,'operation':document['operation'],'status':'OFFLINE_RESEARCH_CALCULATED',
                   'input_sha256':hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
                   'execution_authorized':False,'production_qualified':False})
    return result


OPERATIONS={'run':run}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:
        require(args.output.resolve()!=args.input.resolve(),'OUTPUT_INPUT_ALIAS')
    result=run(json.loads(args.input.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_object))
    rendered=json.dumps(result,indent=2,allow_nan=False)+'\n'
    if args.output:
        with args.output.open('x',encoding='utf-8') as stream: stream.write(rendered)
    else:
        print(rendered,end='')


if __name__=='__main__':main()
