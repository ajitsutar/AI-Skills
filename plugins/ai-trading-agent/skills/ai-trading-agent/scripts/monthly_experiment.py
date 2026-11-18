"""Offline causal monthly targets and hash-bound staged research selection.

No prices are downloaded and no accounting engine or historical AI selector is
invented. Calendar, source authenticity and supplied availability remain claims.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

from quant_common import digest, integer, require, scalar, timestamp


MODES = ('fixed_adaptive', 'fixed_equal', 'reselection')
SCORE = {'cagr': .5, 'sharpe': .25, 'max_drawdown': .25}


def _symbols(values):
    require(isinstance(values, list) and values and
            all(isinstance(s, str) and s.strip() == s and s for s in values)
            and len(set(values)) == len(values), 'UNIQUE_NONEMPTY_SYMBOLS')
    return list(values)


def capped_inverse_volatility(document):
    """Long-only inverse-volatility waterfill; caps and cash are pre-fee targets."""
    vols = document['volatilities']
    require(isinstance(vols, dict) and vols, 'VOLATILITIES_REQUIRED')
    _symbols(list(vols))
    vols = {s: scalar(v, 'volatility', 0) for s, v in vols.items()}
    require(all(v > 0 for v in vols.values()), 'POSITIVE_VOLATILITY_REQUIRED')
    budget = scalar(document.get('equity_weight', .99), 'equity_weight', 0, 1)
    cap = scalar(document.get('cap', .15), 'cap', 0, 1)
    require(budget > 0 and cap > 0 and len(vols)*cap >= budget,
            'INFEASIBLE_POSITIVE_WEIGHT_CAP')
    remaining, weights, left = sorted(vols), {}, budget
    while remaining:
        # Scale by minimum volatility, avoiding overflow in 1/tiny-volatility.
        smallest = min(vols[s] for s in remaining)
        inverse = {s: smallest/vols[s] for s in remaining}
        total = math.fsum(inverse.values())
        proposal = {s: left*inverse[s]/total for s in remaining}
        capped = [s for s in remaining if proposal[s] > cap]
        if not capped:
            weights.update(proposal)
            break
        for s in capped:
            weights[s] = cap
        remaining = [s for s in remaining if s not in capped]
        left = budget-math.fsum(weights.values())
    residual = budget-math.fsum(weights.values())
    for s in sorted(weights):
        if 0 <= weights[s]+residual <= cap:
            weights[s] += residual
            break
    require(all(0 < w <= cap+1e-12 for w in weights.values()) and
            abs(math.fsum(weights.values())-budget) < 1e-12,
            'WEIGHT_NUMERICAL_RESOLUTION_FAILED')
    return {'method': 'capped_inverse_volatility_waterfill',
            'weights': {s: weights[s] for s in sorted(weights)},
            'equity_weight': budget, 'cash_weight_before_fees': 1-budget,
            'cap_before_fees': cap, 'input_sha256': digest(document),
            'continuous_cap_or_post_fee_cash_floor': False,
            'limitation': 'Targets only. Native portfolio accounting must fund costs and enforce the supplied post-trade cash floor; volatility is not a return forecast.'}


def _calendar(rows):
    require(isinstance(rows, list) and len(rows) >= 2, 'EXTENDED_SESSION_CALENDAR_REQUIRED')
    dates, closes = [], []
    for row in rows:
        day = date.fromisoformat(row['session_date']).isoformat()
        close = timestamp(row['close_utc'])
        # Exchange-local session dates may differ from UTC dates.
        require(abs((close.date()-date.fromisoformat(day)).days) <= 1, 'SESSION_CLOSE_DATE_MISMATCH')
        dates.append(day)
        closes.append(close)
    require(dates == sorted(set(dates)) and closes == sorted(set(closes)),
            'UNIQUE_INCREASING_CALENDAR_REQUIRED')
    return dates, closes


def monthly_targets(document):
    """Fixed-stock targets at declared month ends, executable next-session close.

    Complete calendar through the following month is required; future calendar
    rows are allowed, future price observations are not. No return series is built.
    """
    mode = document['composition_mode']
    require(mode in MODES, 'EXPLICIT_COMPOSITION_MODE_REQUIRED')
    require(mode != 'reselection', 'RESELECTION_REQUIRES_RETAINED_SELECTOR_AND_MEMBERSHIP')
    symbols = _symbols(document['symbols'])
    days, closes = _calendar(document['calendar'])
    require(document.get('calendar_evidence'), 'CALENDAR_EVIDENCE_REQUIRED')
    cutoff = timestamp(document['as_of'])
    start, end = date.fromisoformat(document['start']).isoformat(), date.fromisoformat(document['end']).isoformat()
    require(start <= end and end <= cutoff.date().isoformat(), 'INVALID_TARGET_WINDOW')
    require(days[-1][:7] > end[:7], 'CALENDAR_MUST_EXTEND_INTO_FOLLOWING_MONTH')
    lookback = integer(document.get('lookback', 60), 'lookback', 2)
    ddof = integer(document.get('ddof', 1), 'ddof', 0, lookback-1)
    equity = scalar(document.get('equity_weight', .99), 'equity_weight', 0, 1)
    cap = scalar(document.get('cap', .15), 'cap', 0, 1)
    lag = integer(document.get('decision_delay_seconds', 1), 'decision_delay_seconds', 1)
    require(equity > 0 and cap > 0 and len(symbols)*cap >= equity, 'INFEASIBLE_POSITIVE_WEIGHT_CAP')
    rows, indices = {}, {day:i for i, day in enumerate(days)}
    for row in document['observations']:
        day = row['session_date']
        require(day in indices and day not in rows, 'DUPLICATE_OR_NONSESSION_PRICE')
        close, available = closes[indices[day]], timestamp(row['available_at'])
        require(close <= available <= cutoff, 'PRICE_AVAILABILITY_OUTSIDE_CUTOFF')
        require(set(row['prices']) == set(symbols), 'FIXED_PRICE_UNIVERSE_MISMATCH')
        prices = {s: scalar(row['prices'][s], 'price', 0) for s in symbols}
        require(all(p > 0 for p in prices.values()), 'POSITIVE_PRICES_REQUIRED')
        rows[day] = (prices, available)
    decisions, failures = [], []
    for i in range(len(days)-1):
        if not (start <= days[i] <= end and days[i][:7] != days[i+1][:7]):
            continue
        known = closes[i]+timedelta(seconds=lag)
        try:
            require(known <= cutoff and known < closes[i+1], 'DECISION_AFTER_CUTOFF_OR_EXECUTION')
            require(i >= lookback, 'INSUFFICIENT_LOOKBACK_CALENDAR')
            required = days[i-lookback:i+1]
            require(all(day in rows for day in required), 'MISSING_LOOKBACK_PRICE')
            require(all(rows[day][1] <= known for day in required), 'LOOKBACK_NOT_AVAILABLE_AT_DECISION')
            returns = {s: [rows[required[j]][0][s]/rows[required[j-1]][0][s]-1
                           for j in range(1,len(required))] for s in symbols}
            vols = {}
            for s, values in returns.items():
                require(all(math.isfinite(v) for v in values), 'NONFINITE_RETURN')
                mean = math.fsum(values)/lookback
                vols[s] = math.sqrt(math.fsum((v-mean)**2 for v in values)/(lookback-ddof))
            if mode == 'fixed_equal':
                weights = {s: equity/len(symbols) for s in symbols}
            else:
                weights = capped_inverse_volatility({'volatilities':vols, 'equity_weight':equity, 'cap':cap})['weights']
            used = [{'session_date':day, 'prices':rows[day][0],
                     'available_at':rows[day][1].isoformat()} for day in required]
            decisions.append({'formation_date':days[i], 'known_at':known.isoformat(),
                'execution_date':days[i+1], 'execution_close_utc':closes[i+1].isoformat(),
                'symbols':symbols, 'weights':[weights[s] for s in symbols],
                'volatilities':vols, 'lookback':lookback, 'ddof':ddof,
                'cash_weight_before_fees':1-equity, 'cap_before_fees':cap,
                'source_window_sha256':digest(used), 'state':'PENDING' if closes[i+1]>cutoff else 'EXECUTABLE_PAST_TARGET',
                'return_earning_starts_at_execution_close':True})
        except (ValueError, OverflowError) as exc:
            failures.append({'formation_date':days[i], 'reason':str(exc), 'symbols':symbols})
    return {'status':'COMPLETE_TARGETS' if decisions and not failures else 'INCOMPLETE_TARGETS',
        'composition_mode':mode, 'symbols':symbols, 'decisions':decisions, 'failures':failures,
        'input_sha256':digest(document), 'as_of':document['as_of'],
        'calendar_and_source_authenticity_verified':False, 'accounting_performed':False,
        'limitation':'Use native backtest.portfolio with decisions at interval start equal to execution close. Existing holdings earn through that close; new targets earn only the subsequent interval. Missing formations remain failures, never silent substitutions. No actual fills, cash interest, taxes or fee funding are calculated here.'}


def _window(value):
    start, end = date.fromisoformat(value['start']), date.fromisoformat(value['end'])
    require(start < end, 'INVALID_STAGE_WINDOW')
    return {'start':start.isoformat(), 'end':end.isoformat()}


def freeze_experiment(document):
    """Freeze full design before computing performance; signature is not a timestamp authority."""
    d = copy.deepcopy(document)
    require(d['composition_mode'] in MODES, 'EXPLICIT_COMPOSITION_MODE_REQUIRED')
    candidates = d['candidates']
    require(isinstance(candidates, list) and candidates, 'CANDIDATES_REQUIRED')
    ids = _symbols([r['candidate_id'] for r in candidates])
    for row in candidates:
        _symbols(row['symbols'])
    counts = d.get('counts', {'screen':10,'finalists':5,'selected':2})
    for key in ('screen','finalists','selected'):
        integer(counts[key], key, 1)
    require(counts['screen']==len(ids) and counts['screen']>=counts['finalists']>=counts['selected'], 'STAGE_COUNT_MISMATCH')
    d['counts'] = counts
    for key in ('screen_window','final_window'):
        d[key] = _window(d[key])
    require(isinstance(d['weighting_rule'], dict) and d['weighting_rule'], 'WEIGHTING_RULE_REQUIRED')
    for key in ('benchmark','execution_convention','cash_treatment','tax_treatment','universe_vintage','source_contract'):
        require(d.get(key), 'DESIGN_FIELD_REQUIRED:'+key)
    d['base_one_way_cost_bps'] = scalar(d['base_one_way_cost_bps'], 'base_one_way_cost_bps', 0)
    require(isinstance(d['stress_one_way_cost_bps'], list), 'COST_SENSITIVITIES_REQUIRED')
    d['stress_one_way_cost_bps'] = [scalar(v,'stress_one_way_cost_bps',0) for v in d['stress_one_way_cost_bps']]
    timestamp(d['sealed_at'])
    require('score' not in d or d['score']==SCORE, 'UNSUPPORTED_EXPLICIT_SCORE')
    require('tie_break' not in d or d['tie_break']==['lower_annual_gross_turnover','candidate_id'],
            'UNSUPPORTED_EXPLICIT_TIE_BREAK')
    d['score'] = dict(SCORE)
    d['tie_break'] = ['lower_annual_gross_turnover','candidate_id']
    overlap = max(d['screen_window']['start'],d['final_window']['start']) <= min(d['screen_window']['end'],d['final_window']['end'])
    return {'status':'FROZEN_EXPERIMENT', 'contract':d, 'contract_sha256':digest(d),
        'windows_overlap':overlap, 'untouched_holdout_established':False,
        'precommitment_timing_independently_verified':False,
        'limitation':'Hashes bind supplied design, not proof no one saw outcomes. Current constituents, source vintage, prior knowledge, trial selection and overlapping periods retain retrospective/hindsight limitations.'}


def _rank(rows):
    n, scores, percentiles = len(rows), {}, {}
    for row in rows:
        score, parts = Fraction(0), {}
        for key, sign, weight in [('cagr',1,Fraction(1,2)),('sharpe',1,Fraction(1,4)),('max_drawdown',-1,Fraction(1,4))]:
            v = sign*row['metrics'][key]
            values = [sign*r['metrics'][key] for r in rows]
            percentile = ((Fraction(sum(x<v for x in values)) + Fraction(sum(x==v for x in values)-1,2))/(n-1)) if n>1 else Fraction(0)
            parts[key], score = float(percentile), score+weight*percentile
        scores[row['candidate_id']],percentiles[row['candidate_id']] = score,parts
    ordered = sorted(rows,key=lambda r:(-scores[r['candidate_id']],r['metrics']['annual_gross_turnover'],r['candidate_id']))
    return [{**r,'rank':i+1,'composite_score':float(scores[r['candidate_id']]),
        'exact_score':str(scores[r['candidate_id']]),'percentiles':percentiles[r['candidate_id']]} for i,r in enumerate(ordered)]


def rank_stage(document):
    """Rank one completed stage, retaining failures and a sealed shortlist dependency."""
    frozen = {k:v for k,v in document['frozen'].items() if k!='execution_authorized'}
    require(document['frozen'].get('execution_authorized',False) is False, 'RESEARCH_ONLY_RECEIPT')
    require(frozen['contract_sha256']==digest(frozen['contract']), 'FROZEN_CONTRACT_HASH_MISMATCH')
    require(freeze_experiment(frozen['contract'])==frozen, 'INVALID_FROZEN_CONTRACT')
    contract, stage = frozen['contract'], document['stage']
    require(stage in ('screen','final'), 'STAGE_REQUIRED')
    sealed = timestamp(document['sealed_at'])
    require(sealed >= timestamp(contract['sealed_at']), 'STAGE_BEFORE_FREEZE')
    expected = [r['candidate_id'] for r in contract['candidates']]
    parent_hash = None
    if stage == 'final':
        parent = {k:v for k,v in document['screen_receipt'].items() if k!='execution_authorized'}
        require(document['screen_receipt'].get('execution_authorized',False) is False, 'RESEARCH_ONLY_RECEIPT')
        require(parent['receipt_sha256']==digest({k:v for k,v in parent.items() if k!='receipt_sha256'}), 'SHORTLIST_HASH_MISMATCH')
        require(parent['stage']=='screen' and parent['status']=='RANKED_STAGE' and
                parent['contract_sha256']==frozen['contract_sha256'], 'SHORTLIST_CONTRACT_MISMATCH')
        # Recompute the parent score from its preserved records, not only its hash.
        replay = rank_stage({'frozen':frozen,'stage':'screen','results':parent['attempts'],'sealed_at':parent['sealed_at']})
        require(replay==parent, 'SHORTLIST_REPLAY_MISMATCH')
        opened = timestamp(document['final_data_opened_at'])
        require(timestamp(parent['sealed_at']) < opened <= sealed, 'FINAL_DATA_MUST_FOLLOW_SHORTLIST')
        expected, parent_hash = parent['selected_ids'],parent['receipt_sha256']
    rows = copy.deepcopy(document['results'])
    require(isinstance(rows,list) and len(rows)==len(expected) and
            set(_symbols([r['candidate_id'] for r in rows]))==set(expected), 'ALL_EXPECTED_ATTEMPTS_REQUIRED')
    window = contract['screen_window' if stage=='screen' else 'final_window']
    require(date.fromisoformat(window['end']) <= sealed.date(), 'STAGE_WINDOW_AFTER_SEAL')
    computed, failures = [], []
    candidates = {r['candidate_id']:r for r in contract['candidates']}
    for row in rows:
        require(row['window']==window, 'STAGE_WINDOW_MISMATCH')
        require(row['one_way_cost_bps']==contract['base_one_way_cost_bps'], 'STAGE_COST_MISMATCH')
        if row['status'] != 'COMPUTED':
            require(row['status'] in ('FAILED','UNPRICEABLE') and row.get('reason'), 'FAILED_ATTEMPT_REASON_REQUIRED')
            failures.append(row)
            continue
        for field in ('result_sha256','accounting_input_sha256'):
            require(isinstance(row.get(field),str) and len(row[field])==64 and
                    all(c in '0123456789abcdef' for c in row[field]), 'RESULT_OR_ACCOUNTING_INPUT_HASH_REQUIRED')
        expected_contract = {'experiment_contract_sha256':frozen['contract_sha256'],
                             'symbols':candidates[row['candidate_id']]['symbols']}
        for field in ('weighting_rule','execution_convention','cash_treatment','tax_treatment','benchmark','source_contract'):
            expected_contract[field] = contract[field]
        require(row.get('result_contract')==expected_contract, 'RESULT_DESIGN_OR_COMPOSITION_MISMATCH')
        m=row['metrics']
        for key in ('cagr','sharpe','max_drawdown','annual_gross_turnover'):
            scalar(m[key],key,0 if key in ('max_drawdown','annual_gross_turnover') else None)
        require(m['max_drawdown']<=1, 'DRAWDOWN_POSITIVE_LOSS_FRACTION_REQUIRED')
        computed.append(row)
    ranked = _rank(computed)
    count = contract['counts']['finalists' if stage=='screen' else 'selected']
    status = 'RANKED_STAGE' if len(ranked)>=count else 'INSUFFICIENT_VALID_CANDIDATES'
    out = {'status':status,'stage':stage,'contract_sha256':frozen['contract_sha256'],
        'sealed_at':document['sealed_at'],'attempts':rows,'ranked':ranked,'failures':failures,
        'selected_ids':[r['candidate_id'] for r in ranked[:count]] if status=='RANKED_STAGE' else [],
        'screen_receipt_sha256':parent_hash,'windows_overlap':frozen['windows_overlap'],
        'untouched_holdout_established':False,'input_source_authenticity_verified':False,
        'limitation':'Ranks supplied after-cost metrics, not forecasts or a whole-universe optimum. All failed attempts remain visible. Supplied result hashes identify records; source-bound workflow must bind their actual bytes.'}
    if stage=='final':
        out['final_data_opened_at']=document['final_data_opened_at']
    out['receipt_sha256']=digest(out)
    return out


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['weights','targets','freeze','rank'])
    parser.add_argument('input',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    require(not args.output.resolve().is_relative_to(Path(__file__).resolve().parents[1]), 'OUTPUT_OUTSIDE_SKILL_REQUIRED')
    document=json.loads(args.input.read_text(encoding='utf-8-sig'))
    result={'weights':capped_inverse_volatility,'targets':monthly_targets,'freeze':freeze_experiment,'rank':rank_stage}[args.command](document)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')


if __name__=='__main__':
    main()
