"""Versioned, replayable offline quant jobs with an explicit operation allowlist.

No input-supplied imports, expressions, executable code, URLs or order actions.
Cross-model agreement means identical inputs/contracts plus verified calculations.
"""
from __future__ import annotations

import argparse
import copy
import importlib.metadata
import inspect
import json
import math
import platform
from pathlib import Path
from numpy.linalg import LinAlgError

import investment_ops
import multi_asset_risk
import primary_financial_data
import quant_portfolio
import quant_validation
import portfolio_backtest
import manager_monitor
import analysis_checks
import planning_alignment
import financial_alignment
import strategy_research
import forward_evidence
import evidence_semantics
import ranking_alignment
import allocation_policy
import portfolio_decision
import planning_roles
import portfolio_projection
import planning_comparison
import flow_normalization
import price_comparison
import recommendation_report
import employer_reference
import equity_cash_comparison
import source_exposure
import technical_toolkit
import fundamental_toolkit
import sentiment_toolkit
import factor_research
import derivatives_toolkit
import paper_exchange
import platform_readiness
import time_series_toolkit
from quant_common import digest, require

ROOT = Path(__file__).resolve().parents[1]


def technical_analysis(request, data_available_at):
    """Bind completed-bar availability explicitly, including open-labelled/date-only bars."""
    from price_audit import timestamp
    available = timestamp(data_available_at)
    for bar in technical_toolkit.validate_bars(request['bars']):
        stamp = bar['timestamp']
        if len(stamp) == 10:
            require(stamp <= available.date().isoformat(), 'BAR_DATE_AFTER_DATA_AVAILABILITY')
        else:
            require(timestamp(stamp) <= available, 'BAR_AFTER_DATA_AVAILABILITY')
    if 'depth_snapshot' in request:
        require(timestamp(request['depth_snapshot']['as_of']) <= available, 'DEPTH_AFTER_DATA_AVAILABILITY')
    result = technical_toolkit.analyze(request)
    result['data_available_at'] = data_available_at
    result['availability_basis'] = 'Caller-declared completed-bar availability, not inferred from open timestamps or independently verified.'
    return result


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
    'data.normalize_flows': flow_normalization.normalize_flows,
    'backtest.portfolio': portfolio_backtest.simulate,
    'monitor.assess': manager_monitor.assess,
    'analysis.covariance_comparison': analysis_checks.covariance_comparison,
    'analysis.hedge_scenarios': analysis_checks.hedge_scenarios,
    'analysis.compare_claim': analysis_checks.compare_claim,
    'planning.trade_costs': planning_alignment.trade_costs,
    'planning.allocate': allocation_policy.allocate,
    'planning.budget_sizing': portfolio_decision.budget_sizing,
    'planning.source_budget_sizing': portfolio_decision.source_budget_sizing,
    'planning.allocation_context': portfolio_decision.allocation_context,
    'planning.source_allocation_context': source_exposure.source_allocation_context,
    'planning.friction_context': portfolio_decision.friction_context,
    'planning.input_roles': planning_roles.input_roles,
    'planning.source_roles': planning_roles.source_roles,
    'planning.reference_comparison': planning_roles.reference_comparison,
    'planning.dated_projection': portfolio_projection.dated_projection,
    'planning.source_projection': portfolio_projection.source_projection,
    'planning.tax_sensitivity': portfolio_projection.tax_sensitivity,
    'planning.alternative_comparison': planning_comparison.alternative_comparison,
    'planning.source_alternatives': planning_comparison.source_alternatives,
    'planning.employer_diversification_baseline': employer_reference.employer_diversification_baseline,
    'financial.equity_cash_comparison': equity_cash_comparison.equity_cash_comparison,
    'planning.settlement_transfer_paths': planning_comparison.settlement_transfer_paths,
    'planning.settlement_transfer_sweep': planning_comparison.settlement_transfer_sweep,
    'planning.cash_plan': planning_alignment.cash_plan,
    'planning.cash_projection': planning_alignment.cash_projection,
    'planning.vest_reconciliation': planning_alignment.vest_reconciliation,
    'planning.portfolio_reconciliation': planning_alignment.portfolio_reconciliation,
    'planning.cash_reconciliation': planning_alignment.cash_reconciliation,
    'planning.trade_history_costs': planning_alignment.trade_history_costs,
    'planning.session_pnl': planning_alignment.session_pnl,
    'financial.owner_cash_bridge': financial_alignment.owner_cash_bridge,
    'financial.acquisition_cash': financial_alignment.acquisition_cash,
    'financial.terminal_scenarios': financial_alignment.terminal_scenarios,
    'financial.price_scenarios': financial_alignment.price_scenarios,
    'financial.corporate_action_return': financial_alignment.corporate_action_return,
    'backtest.dual_sma': strategy_research.dual_sma,
    'backtest.dual_sma_variants': strategy_research.dual_sma_variants,
    'backtest.opening_range': strategy_research.opening_range,
    'validation.forward_observations': forward_evidence.assess,
    'validation.paper_study_forward': forward_evidence.paper_study,
    'evidence.operand_compatibility': evidence_semantics.operand_compatibility,
    'evidence.event_window': evidence_semantics.event_window,
    'evidence.states': evidence_semantics.evidence_states,
    'evidence.price_comparison': price_comparison.compare_prices,
    'planning.recommendation_context': recommendation_report.recommendation_context,
    'ranking.route': ranking_alignment.route_ranking,
    'ranking.replay': ranking_alignment.replay_ranking,
    'ranking.compare': ranking_alignment.compare_rankings,
}
ANALYSIS_OPERATIONS = {
    'technical.analyze': technical_analysis,
    'fundamental.calculate': fundamental_toolkit.run,
    'sentiment.analyze': sentiment_toolkit.analyze,
    'sentiment.trend': sentiment_toolkit.trend,
    'sentiment.fuse': sentiment_toolkit.fuse,
    'sentiment.calibrate': sentiment_toolkit.calibrate,
    'sentiment.backtest': sentiment_toolkit.backtest,
    **factor_research.OPERATIONS,
}
OPERATIONS.update(ANALYSIS_OPERATIONS)
MULTIASSET_OPERATIONS = {
    'derivatives.calculate': derivatives_toolkit.run,
    'paper.replay': paper_exchange.replay,
    'platform.assess': platform_readiness.assess,
    'timeseries.run': time_series_toolkit.run,
}
OPERATIONS.update(MULTIASSET_OPERATIONS)
MODULES = ('quant_workbench.py', 'quant_common.py', 'quant_validation.py',
           'quant_portfolio.py', 'multi_asset_risk.py', 'investment_ops.py',
           'primary_financial_data.py', 'price_audit.py', 'financial_normalize.py',
           'filing_extract.py', 'deterministic_rank.py', 'portfolio_backtest.py', 'manager_monitor.py',
           'analysis_checks.py', 'planning_alignment.py', 'financial_alignment.py',
           'portfolio_analytics.py', 'accounting_tools.py', 'strategy_research.py',
           'strategy_lab.py', 'risk_engine.py', 'forward_evidence.py', 'report_facts.py',
           'research_analytics.py', 'evidence_semantics.py', 'ranking_alignment.py',
           'vqm_research.py', 'public_research.py', 'research_bundle.py', 'screen_review.py',
           'horizon_review.py', 'cash_benchmark.py', 'trading_calendar.py', 'allocation_policy.py',
           'portfolio_decision.py', 'planning_roles.py', 'portfolio_projection.py', 'planning_comparison.py',
           'flow_normalization.py', 'price_comparison.py', 'recommendation_report.py', 'employer_reference.py',
           'equity_cash_comparison.py', 'source_exposure.py', 'technical_toolkit.py',
           'fundamental_toolkit.py', 'sentiment_toolkit.py', 'factor_research.py',
           'derivatives_toolkit.py', 'paper_exchange.py', 'platform_readiness.py', 'time_series_toolkit.py')


def implementation_hash():
    sources = {f: (ROOT/'scripts'/f).read_text(encoding='utf-8') for f in MODULES}
    sources['financial-normalization-v1.json'] = (ROOT/'profiles/financial-normalization-v1.json').read_text(encoding='utf-8')
    sources['report-facts-v2.json'] = (ROOT/'profiles/report-facts-v2.json').read_text(encoding='utf-8')
    for name in ('vqm-fundamental-v1.json', 'public-vqm-discovery-v1.json'):
        sources[name] = (ROOT/'profiles'/name).read_text(encoding='utf-8')
    return digest(sources)


def operation_catalog():
    """Describe actual allowlisted interfaces; no guessed model-specific defaults."""
    operations = {}
    for name, function in sorted(OPERATIONS.items()):
        parameters = inspect.signature(function).parameters
        operations[name] = {
            'required': [k for k, p in parameters.items() if p.default is inspect.Parameter.empty],
            'defaults': {k: p.default for k, p in parameters.items() if p.default is not inspect.Parameter.empty}}
    return {'implementation_sha256': implementation_hash(), 'operations': operations,
            'scope': 'Offline computations only; required observations are not supplied by these defaults.'}


def resolved_inputs(operation, inputs):
    require(operation in OPERATIONS, 'OPERATION_NOT_ALLOWED:'+operation)
    require(isinstance(inputs, dict), 'JOB_INPUT_OBJECT_REQUIRED')
    bound = inspect.signature(OPERATIONS[operation]).bind(**inputs)
    bound.apply_defaults()
    resolved = copy.deepcopy(dict(bound.arguments))
    if operation == 'technical.analyze':
        resolved['request'] = technical_toolkit.resolve_request(resolved['request'])
    if operation.startswith('sentiment.'):
        resolved['document'] = sentiment_toolkit.resolve_document(operation.split('.')[1], resolved['document'])
    return resolved


def prepare(document):
    """Make helper defaults explicit before models compute or exchange a job."""
    result = copy.deepcopy(document)
    require(result.get('schema_version') == 1, 'WORKBENCH_SCHEMA')
    jobs = result.get('jobs')
    require(isinstance(jobs, list) and jobs and
            len({j['id'] for j in jobs}) == len(jobs), 'UNIQUE_JOB_IDS')
    for job in jobs:
        job['inputs'] = resolved_inputs(job['operation'], job['inputs'])
    return result


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
            inputs = resolved_inputs(job['operation'], job['inputs'])
            if job['operation'] in MULTIASSET_OPERATIONS:
                payload = inputs['document']
                if job['operation'] in ('paper.replay', 'platform.assess'):
                    require(timestamp(payload['as_of']) <= timestamp(contract['as_of']), 'FUTURE_MULTI_ASSET_CUTOFF')
                if job['operation'] == 'paper.replay':
                    require(payload['base_currency'] == contract['base_currency'], 'PAPER_CURRENCY_MISMATCH')
                if job['operation'] == 'derivatives.calculate':
                    require(payload['currency'] == contract['base_currency'], 'DERIVATIVES_CURRENCY_MISMATCH')
                    require(timestamp(payload['information_cutoff']) <= timestamp(contract['as_of']), 'FUTURE_DERIVATIVES_CUTOFF')
                if job['operation'] == 'timeseries.run':
                    require(timestamp(payload['inputs']['as_of']) <= timestamp(contract['as_of']), 'FUTURE_TIME_SERIES_CUTOFF')
            if job['operation'] in ANALYSIS_OPERATIONS:
                cutoff = timestamp(contract['as_of'])
                if job['operation'] == 'technical.analyze':
                    require(timestamp(inputs['data_available_at']) <= cutoff, 'FUTURE_TECHNICAL_DATA')
                if job['operation'] == 'fundamental.calculate':
                    require(inputs['d']['currency'] == contract['base_currency'], 'FUNDAMENTAL_CURRENCY_MISMATCH')
                if job['operation'] in ('factor.normalize', 'sentiment.analyze', 'sentiment.fuse'):
                    payload = inputs.get('document',inputs)
                    require(timestamp(payload['as_of']) <= cutoff, 'FUTURE_ANALYSIS_CUTOFF')
                if job['operation'] == 'factor.fama_french':
                    require(all(timestamp(r['timestamp']) <= cutoff for r in inputs['rows']), 'FUTURE_FACTOR_OBSERVATION')
                if job['operation'] == 'sentiment.trend':
                    require(all(timestamp(t) <= cutoff for t in inputs['document']['cutoffs']), 'FUTURE_TREND_CUTOFF')
                if job['operation'] == 'sentiment.backtest':
                    require(all(timestamp(r['end']) <= cutoff for r in inputs['document']['periods']), 'FUTURE_BACKTEST_DATA')
                if job['operation'] == 'sentiment.calibrate':
                    require(all(timestamp(r['predicted_at']) <= cutoff and timestamp(r['label_available_at']) <= cutoff
                                for r in inputs['document']['rows']), 'FUTURE_CALIBRATION_DATA')
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
            if job['operation'] in {'backtest.dual_sma', 'backtest.dual_sma_variants',
                                     'backtest.opening_range', 'validation.paper_study_forward'}:
                require(timestamp(inputs['as_of']) <= timestamp(contract['as_of']), 'FUTURE_ANALYSIS_CUTOFF')
            if job['operation'] in {'validation.forward_observations', 'planning.cash_plan',
                                     'planning.vest_reconciliation', 'planning.session_pnl'}:
                if inputs['document'].get('as_of') is not None:
                    require(timestamp(inputs['document']['as_of']) <= timestamp(contract['as_of']), 'FUTURE_STATE_SNAPSHOT')
            result = OPERATIONS[job['operation']](**inputs)
            result['execution_authorized'] = False
            results.append({'id': job['id'], 'operation': job['operation'], 'status': 'COMPUTED', 'result': result,
                            'resolved_inputs_sha256': digest(inputs),
                            'defaults_used': {k: v for k, v in inputs.items() if k not in job['inputs']}})
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
    versions = {}
    for name in ('numpy', 'scipy', 'pandas', 'arch', 'exchange_calendars', 'tzdata'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = 'UNAVAILABLE'
    return {'input': document, 'result': result, 'result_sha256': digest(result),
            'environment': {**versions, 'python': platform.python_version(),
                            'platform': platform.system(), 'machine': platform.machine()}}


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
    parser.add_argument('command', choices=['operations', 'prepare', 'run', 'verify', 'compare'])
    parser.add_argument('input', nargs='?', type=Path)
    parser.add_argument('other', nargs='?', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command != 'operations':
        require(args.input is not None, 'INPUT_REQUIRED')
        document = json.loads(args.input.read_text(encoding='utf-8-sig'))
    if args.command == 'operations':
        result = operation_catalog()
    elif args.command == 'prepare':
        result = prepare(document)
    elif args.command == 'run':
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
