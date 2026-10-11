"""Versioned, replayable offline quant jobs with an explicit operation allowlist.

No input-supplied imports, expressions, executable code, URLs or order actions.
Cross-model agreement means identical inputs/contracts plus verified calculations.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
from pathlib import Path
from numpy.linalg import LinAlgError

import investment_ops
import multi_asset_risk
import primary_financial_data
import quant_portfolio
import quant_validation
import portfolio_backtest
import manager_monitor
from quant_common import digest, require

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = {
    'validation.folds': quant_validation.purged_walk_forward,
    'validation.tail': quant_validation.tail_risk,
    'validation.hac': quant_validation.hac_mean,
    'validation.holm': quant_validation.holm,
    'validation.sharpe': quant_validation.sharpe_evidence,
    'validation.bootstrap': quant_validation.block_bootstrap,
    'validation.factors': quant_validation.factor_attribution,
    'validation.promotion': quant_validation.promotion_evidence,
    'portfolio.construct': quant_portfolio.construct,
    'risk.option': multi_asset_risk.european_option,
    'risk.bond': multi_asset_risk.fixed_cashflow_bond,
    'risk.scenarios': multi_asset_risk.scenario_book,
    'ops.cash_ladder': investment_ops.cash_ladder,
    'ops.shortfall': investment_ops.implementation_shortfall,
    'ops.xirr': investment_ops.xirr,
    'ops.attribution': investment_ops.brinson,
    'data.sec_extract': primary_financial_data.extract,
    'data.coverage': primary_financial_data.coverage_plan,
    'backtest.portfolio': portfolio_backtest.simulate,
    'monitor.assess': manager_monitor.assess,
}
MODULES = ('quant_workbench.py', 'quant_common.py', 'quant_validation.py',
           'quant_portfolio.py', 'multi_asset_risk.py', 'investment_ops.py',
           'primary_financial_data.py', 'price_audit.py', 'financial_normalize.py',
           'filing_extract.py', 'deterministic_rank.py', 'portfolio_backtest.py', 'manager_monitor.py')


def implementation_hash():
    sources = {f: (ROOT/'scripts'/f).read_text(encoding='utf-8') for f in MODULES}
    sources['financial-normalization-v1.json'] = (ROOT/'profiles/financial-normalization-v1.json').read_text(encoding='utf-8')
    return digest(sources)


def run(document):
    require(document.get('schema_version') == 1, 'WORKBENCH_SCHEMA')
    contract = document['contract']
    require(set(contract) >= {'prompt', 'purpose', 'base_currency', 'horizon_id', 'as_of'}, 'CONTRACT_REQUIRED')
    require(all(isinstance(contract[k], str) and contract[k].strip() for k in
                ('prompt', 'purpose', 'base_currency', 'horizon_id', 'as_of')), 'CONTRACT_FIELDS')
    from price_audit import timestamp
    timestamp(contract['as_of'])
    jobs = document['jobs']
    require(jobs and len({j['id'] for j in jobs}) == len(jobs), 'UNIQUE_JOB_IDS')
    results = []
    for job in jobs:
        require(job['operation'] in OPERATIONS, 'OPERATION_NOT_ALLOWED:'+job['operation'])
        require(isinstance(job['inputs'], dict), 'JOB_INPUT_OBJECT_REQUIRED')
        try:
            inputs = job['inputs']
            if job['operation'] == 'portfolio.construct':
                require(inputs['document']['horizon_id'] == contract['horizon_id'] and
                        inputs['document']['currency'] == contract['base_currency'], 'WORKBENCH_PORTFOLIO_CONTRACT')
                require(timestamp(inputs['document']['decision_at']) <= timestamp(contract['as_of']), 'FUTURE_DECISION')
            if job['operation'] == 'data.sec_extract':
                require(timestamp(inputs['information_cutoff']) <= timestamp(contract['as_of']), 'FUTURE_INFORMATION_CUTOFF')
            if job['operation'] == 'validation.factors':
                require(all(timestamp(r['timestamp']) <= timestamp(contract['as_of']) for r in inputs['observations']), 'FUTURE_OBSERVATIONS')
            if job['operation'] == 'validation.promotion':
                require(timestamp(inputs['evidence']['test_end']) <= timestamp(contract['as_of']), 'FUTURE_TEST_EVIDENCE')
            if job['operation'] in {'monitor.assess', 'ops.cash_ladder'}:
                require(timestamp(inputs['as_of']) <= timestamp(contract['as_of']), 'FUTURE_STATE_SNAPSHOT')
            if job['operation'] == 'backtest.portfolio':
                require(all(timestamp(r['end']) <= timestamp(contract['as_of']) for r in inputs['document']['periods']), 'FUTURE_BACKTEST_DATA')
            result = OPERATIONS[job['operation']](**job['inputs'])
            result['execution_authorized'] = False
            results.append({'id': job['id'], 'operation': job['operation'], 'status': 'COMPUTED', 'result': result})
        except LinAlgError as exc:
            results.append({'id': job['id'], 'operation': job['operation'], 'status': 'CALCULATION_FAILED',
                            'reason': 'NUMERICAL_ERROR:'+str(exc), 'execution_authorized': False})
        except (ValueError, KeyError, TypeError, OverflowError, ZeroDivisionError) as exc:
            results.append({'id': job['id'], 'operation': job['operation'], 'status': 'REJECTED_INPUT',
                            'reason': type(exc).__name__+':'+str(exc), 'execution_authorized': False})
    return {'schema_version': 1, 'skill_version': (ROOT/'VERSION').read_text().strip(),
            'implementation_sha256': implementation_hash(), 'input_sha256': digest(document),
            'contract_sha256': digest(contract), 'results': results,
            'execution_authorized': False,
            'limitation': 'Execution success is not evidence validity, investment performance or model approval.'}


def differences(left, right, path='$', absolute=1e-8, relative=1e-7):
    if type(left) in (float, int) and type(right) in (float, int):
        return [] if math.isclose(left, right, abs_tol=absolute, rel_tol=relative) else [path]
    if type(left) != type(right):
        return [path]
    if isinstance(left, dict):
        if set(left) != set(right):
            return [path+':keys']
        return [p for k in sorted(left) for p in differences(left[k], right[k], path+'.'+k, absolute, relative)]
    if isinstance(left, list):
        if len(left) != len(right):
            return [path+':length']
        return [p for i, (a, b) in enumerate(zip(left, right)) for p in differences(a, b, path+'['+str(i)+']', absolute, relative)]
    return [] if left == right else [path]


def freeze(document):
    result = run(document)
    return {'input': document, 'result': result, 'result_sha256': digest(result),
            'environment': {n: importlib.metadata.version(n) for n in ('numpy', 'scipy')}}


def verify(bundle):
    require(bundle['result_sha256'] == digest(bundle['result']), 'RESULT_HASH_MISMATCH')
    require(bundle['result']['implementation_sha256'] == implementation_hash(), 'IMPLEMENTATION_MISMATCH')
    actual = run(bundle['input'])
    mismatches = differences(actual, bundle['result'])
    require(not mismatches, 'REPLAY_MISMATCH:'+','.join(mismatches[:10]))
    return {'status': 'REPLAY_MATCH', 'input_sha256': actual['input_sha256'],
            'jobs_verified': len(actual['results']), 'execution_authorized': False}


def compare(left, right):
    verify(left)
    verify(right)
    require(left['result']['input_sha256'] == right['result']['input_sha256'], 'DIFFERENT_INPUTS_NOT_A_CALCULATION_COMPATIBILITY_TEST')
    mismatches = differences(left['result'], right['result'])
    return {'status': 'MATCH' if not mismatches else 'MISMATCH', 'differences': mismatches,
            'jobs_compared': len(left['result']['results']), 'absolute_tolerance': 1e-8,
            'relative_tolerance': 1e-7, 'execution_authorized': False,
            'limitation': 'Tests calculation/rejection compatibility only; does not test model-selected data, narrative, strategy alpha or future investment results.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'verify', 'compare'])
    parser.add_argument('input', type=Path)
    parser.add_argument('other', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    document = json.loads(args.input.read_text(encoding='utf-8-sig'))
    if args.command == 'run':
        result = freeze(document)
    elif args.command == 'verify':
        result = verify(document)
    else:
        require(args.other is not None, 'SECOND_BUNDLE_REQUIRED')
        result = compare(document, json.loads(args.other.read_text(encoding='utf-8-sig')))
    if args.output:
        require(not args.output.resolve().is_relative_to(ROOT), 'OUTPUT_OUTSIDE_SKILL_REQUIRED')
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write('\n')
    else:
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
