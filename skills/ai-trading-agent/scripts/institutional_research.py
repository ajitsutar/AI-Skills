"""Point-in-time event research protocol, decision briefs and prospective review.

The three workbench functions are pure. Explicit CLI journal/capture commands
retain local bytes; they perform no network, scheduling, account or broker action.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

MAX_BYTES = 50 * 1024 * 1024
MAX_RECORDS = 10000
HF = {
    'HF01': 'Define workflow', 'HF02': 'Qualify data and rights',
    'HF03': 'Decision-ready briefs', 'HF04': 'Portfolio impact',
    'HF05': 'Prospective usefulness study', 'HF06': 'Costs, liquidity and capacity',
    'HF07': 'Recurring operation dependability', 'HF08': 'Actual host acceptance',
    'HF09': 'Independent methodology challenge', 'HF10': 'Target deployment operations and integrations'}
LIMITS = [
    'Supplied records, source identities, rights and clocks are declarations; hashes do not authenticate them.',
    'Coverage is supplied eligible records only; requested U.S.-listed discovery scope is not live full-universe coverage.',
    'Public prints and short-position proxies do not establish trader identity, intent, a squeeze probability or causation.',
    'Software and synthetic demos do not establish profitable alpha, observed prospective research results, commercial rights or host acceptance.',
    'Research findings are advisory and add no execution gate or authorization.']


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def _digest(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _workflow_protocol(operation):
    """Accept the current workflow contract while retaining older callers."""
    @wraps(operation)
    def compatible(document):
        if not isinstance(document, dict):
            return operation(document)
        has_workflow = 'workflow' in document
        declared_evaluation = document.get('evaluation')
        has_current_identity = isinstance(declared_evaluation, dict) and any(
            key in declared_evaluation for key in ('workflow_id', 'workflow_sha256'))
        if not has_workflow and not has_current_identity:
            return operation(document)
        translated = deepcopy(document)
        if has_workflow:
            _require(isinstance(document['workflow'], dict), 'WORKFLOW_OBJECT_REQUIRED')
            _require('pilot' not in translated or _digest(translated['pilot']) == _digest(translated['workflow']),
                     'CONFLICTING_PROTOCOL_DECLARATIONS')
            translated['pilot'] = translated.pop('workflow')
        evaluation = translated.get('evaluation')
        if isinstance(evaluation, dict):
            for current, retained in [('workflow_id', 'pilot_id'), ('workflow_sha256', 'pilot_sha256')]:
                if current in evaluation:
                    _require(retained not in evaluation or _digest(evaluation[retained]) == _digest(evaluation[current]),
                             'CONFLICTING_EVALUATION_PROTOCOL_DECLARATIONS')
                    evaluation[retained] = evaluation.pop(current)
        result = operation(translated)
        result['protocol_mapping'] = {
            'kind': 'WORKFLOW_COMPATIBILITY_MAPPING',
            'declared_input_sha256': _digest(document),
            'calculation_input_sha256': _digest(translated)}
        result['input_sha256'] = _digest(document)
        protocol = document.get('workflow', document.get('pilot'))
        result['workflow'] = deepcopy(protocol)
        result['workflow_sha256'] = _digest(protocol) if protocol is not None else None
        return result
    return compatible


def _stamp(value):
    _require(isinstance(value, str), 'EXPLICIT_TIMESTAMP_REQUIRED')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('EXPLICIT_TIMESTAMP_REQUIRED') from exc
    _require(result.tzinfo is not None and result.utcoffset() is not None, 'TIMEZONE_REQUIRED_NO_DATE_ONLY_MIDNIGHT')
    return result.astimezone(timezone.utc)


def _number(value, minimum=None):
    _require(not isinstance(value, bool) and isinstance(value, (str, int, float, Decimal)), 'EXPLICIT_NUMBER_REQUIRED')
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise ValueError('FINITE_NUMBER_REQUIRED') from exc
    _require(result.is_finite() and (minimum is None or result >= Decimal(str(minimum))), 'FINITE_NUMBER_RANGE')
    return result


def _id(value):
    _require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', value), 'SAFE_ID_REQUIRED')
    return value


def _hash(value):
    _require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'SHA256_REQUIRED')
    return value


def _base(document, kind):
    _require(isinstance(document, dict) and type(document.get('schema_version')) is int and document['schema_version'] == 1, 'SCHEMA_VERSION_1_REQUIRED')
    _stamp(document.get('as_of'))
    _require(isinstance(document.get('records'), list) and len(document['records']) <= MAX_RECORDS, 'RECORD_LIST_AND_10000_RECORD_CAP_REQUIRED')
    import market_sources
    evidence = market_sources.normalize(deepcopy({k: v for k, v in document.items() if k in {'schema_version', 'as_of', 'records'}}))
    return {'kind': kind, 'schema_version': 1, 'as_of': document['as_of'],
            'input_sha256': _digest(document), 'execution_authorized': False,
            'evidence': evidence, 'limitations': list(LIMITS)}


def _configuration(document):
    pilot = deepcopy(document.get('pilot', {}))
    _require(isinstance(pilot, dict), 'PILOT_OBJECT_REQUIRED')
    universe = deepcopy(pilot.get('universe', {'mode': 'us_listed_full'}))
    _require(isinstance(universe, dict), 'UNIVERSE_OBJECT_REQUIRED')
    _require(universe.get('mode') in {'us_listed_full', 'explicit_symbols'}, 'DISCOVERY_UNIVERSE_MODE_REQUIRED')
    if universe['mode'] == 'explicit_symbols':
        symbols = universe.get('symbols')
        _require(isinstance(symbols, list) and symbols and all(isinstance(x, str) and x for x in symbols)
                 and len(symbols) == len(set(symbols)), 'EXPLICIT_UNIQUE_SYMBOLS_REQUIRED')
    missing = [k for k in ('id', 'research_question', 'horizon', 'reviewer', 'study') if not pilot.get(k)]
    if 'id' in pilot:
        _id(pilot['id'])
    for section, fields in {'horizon': ('label', 'entry_policy', 'exit_policy'),
                            'reviewer': ('id', 'role'),
                            'study': ('registered_at', 'start_at', 'end_at', 'usefulness_criterion', 'workflow_baseline_id')}.items():
        if pilot.get(section):
            _require(isinstance(pilot[section], dict), 'PILOT_SECTION_OBJECT_REQUIRED')
            missing.extend(section + '.' + name for name in fields if not pilot[section].get(name))
    study = pilot.get('study')
    if study and all(study.get(x) for x in ('registered_at', 'start_at', 'end_at')):
        _require(_stamp(study['registered_at']) <= _stamp(study['start_at']) < _stamp(study['end_at']), 'ORDERED_PILOT_STUDY_REQUIRED')
    return pilot, universe, missing


def _readiness(document, missing):
    supplied = deepcopy(document.get('readiness_evidence', {}))
    _require(isinstance(supplied, dict) and not set(supplied) - set(HF), 'HF01_HF10_EVIDENCE_KEYS_REQUIRED')
    rows = [{'id': key, 'requirement': title, 'software_support_implemented': True,
             'real_world_acceptance': 'NOT_ESTABLISHED',
             'supplied_evidence': supplied.get(key),
             'remaining': ('Complete explicit workflow choices: ' + ', '.join(missing)) if key == 'HF01' and missing else {
                 'HF01': 'Register and retain the actual workflow protocol before observations.',
                 'HF02': 'Verify source terms, entitlements, redistribution and intended host use.',
                 'HF03': 'Review actual retained briefs for decision usefulness.',
                 'HF04': 'Supply dated live portfolio context and validate its completeness.',
                 'HF05': 'Run the elapsed prospective study; retain failures, abstentions and baselines.',
                 'HF06': 'Validate costs, spreads, borrow and capacity against the intended market and size.',
                 'HF07': 'Exercise recovery, overlap control and recurring delivery in the actual deployment.',
                 'HF08': 'Obtain actual target-host acceptance and available tool permissions.',
                 'HF09': 'Obtain and retain independent methodology challenge and its dispositions.',
                 'HF10': 'Validate target deployment, operations, rights and integration ownership.'}[key]}
            for key, title in HF.items()]
    by_id = {row['id']: row for row in rows}
    by_id['HF02']['rights_review'] = {
        'intended_uses': deepcopy(document.get('intended_data_uses', [])),
        'declared_sources': [{'id': r.get('source', {}).get('id'), 'rights': r.get('source', {}).get('rights', 'unknown'),
                              'access': r.get('source', {}).get('access')} for r in document.get('records', [])],
        'commercial_ai_cloud_storage_redistribution_rights_verified': False}
    host = deepcopy(document.get('host', {}))
    _require(isinstance(host, dict), 'HOST_DECLARATIONS_OBJECT_REQUIRED')
    required = host.get('required_capabilities', [])
    declared = host.get('declared_capabilities', [])
    _require(isinstance(required, list) and isinstance(declared, list)
             and all(isinstance(x, str) for x in required + declared), 'HOST_CAPABILITY_LISTS_REQUIRED')
    by_id['HF08']['host_review'] = {'declaration': host, 'missing_declared_capabilities': sorted(set(required) - set(declared)),
                                    'actual_host_test_results_verified': False, 'permissions_granted': False}
    deployment = deepcopy(document.get('deployment', {}))
    _require(isinstance(deployment, dict), 'DEPLOYMENT_OBJECT_REQUIRED')
    fields = ('owner', 'runbook', 'monitoring', 'rollback_plan', 'data_handling', 'credential_handling')
    by_id['HF10']['deployment_review'] = {'declaration': deployment,
                                         'missing_operational_declarations': [x for x in fields if not deployment.get(x)],
                                         'deployment_or_integration_performed': False}
    return rows


@_workflow_protocol
def plan(document):
    """Produce an adoptable protocol without starting a recurring task."""
    result = _base(document, 'INSTITUTIONAL_EVENT_PLAN')
    pilot, universe, missing = _configuration(document)
    result.update(status='CONFIGURATION_NEEDED' if missing else 'DECLARED_PROTOCOL_READY_FOR_REVIEW',
                  pilot=pilot, pilot_sha256=_digest(pilot), requested_discovery_universe=universe,
                  actual_coverage='SUPPLIED_RECORDS_ONLY', exhaustive_us_universe_verified=False,
                  missing_configuration=missing, readiness=_readiness(document, missing),
                  protocol={
                      'research_scope': 'Event-driven U.S.-listed equity paper research, including flow and squeeze hypotheses.',
                      'clock_policy': 'Use only records available at each decision cutoff; retain date-only clocks as unresolved.',
                      'first_response_policy': 'Capture exact first response before outcome/reviewer feedback; revisions use new IDs and parent references.',
                      'usefulness_study': 'Prespecify criterion, reviewer, workflow baseline, start/end and complete case roster before first decision.',
                      'returns_study': 'Separately compare declared paper returns with a same-period, same-basis, same-currency cost-aware baseline.',
                      'failure_policy': 'Retain acquisition failures, missing evidence, abstentions, abandoned hypotheses and negative findings.',
                      'challenge_policy': 'Retain challenger identity/basis, objections, evidence and unresolved dispositions; independence remains a declaration.',
                      'operations': 'Explicit journal/capture/recover CLI only; no scheduler or automatic recurring task is created.'})
    result['software_source_caps'] = {'max_records_per_document': MAX_RECORDS, 'max_bytes_per_cli_input': MAX_BYTES,
                                      'network_acquisition': 'Separate market_sources CLI only; no network in these operations.'}
    return result


def _portfolio(document, ticker, cutoff):
    portfolio = deepcopy(document.get('portfolio'))
    trade = deepcopy(document.get('proposed_trade'))
    result = {'status': 'CONTEXT_NOT_SUPPLIED', 'portfolio': portfolio, 'proposed_trade': trade,
              'actual_available_cash_verified': False, 'correlation_or_risk_reduction_established': False}
    if portfolio is None or trade is None:
        return result
    _require(isinstance(portfolio, dict) and isinstance(trade, dict), 'PORTFOLIO_AND_TRADE_OBJECTS_REQUIRED')
    if portfolio.get('as_of') is None or _stamp(portfolio['as_of']) > cutoff:
        result['status'] = 'PORTFOLIO_CLOCK_UNUSABLE'
        return result
    _require(portfolio.get('currency') == trade.get('currency') == 'USD', 'USD_ONLY_NO_IMPLICIT_FX')
    _require(trade.get('ticker') == ticker and trade.get('side') in {'buy', 'sell', 'short', 'cover'}, 'EXPLICIT_TICKER_AND_SIDE_REQUIRED')
    nav = _number(portfolio.get('total_value'), '0.000000000001')
    notional = _number(trade.get('notional'), 0)
    positions = portfolio.get('positions')
    _require(isinstance(positions, list) and len({p['ticker'] for p in positions}) == len(positions), 'UNIQUE_PORTFOLIO_POSITIONS_REQUIRED')
    _require(all(p.get('currency', portfolio['currency']) == 'USD' for p in positions), 'POSITION_CURRENCY_MISMATCH_NO_FX_MODEL')
    amounts = {p['ticker']: _number(p['market_value']) for p in positions}
    if ticker not in amounts and portfolio.get('completeness') != 'complete':
        result['status'] = 'BEFORE_POSITION_UNKNOWN_PARTIAL_PORTFOLIO'
        return result
    before = amounts.get(ticker, Decimal(0))
    delta = notional if trade['side'] in {'buy', 'cover'} else -notional
    after = before + delta
    gross_before = sum(map(abs, amounts.values()), Decimal(0))
    gross_after = gross_before - abs(before) + abs(after)
    result.update(status='DECLARED_EXPOSURE_SCENARIO', total_value_denominator=str(nav),
                  ticker=ticker, before_signed_market_value=str(before), after_signed_market_value=str(after),
                  before_nav_fraction=str(before / nav), after_nav_fraction=str(after / nav),
                  supplied_gross_exposure_before=str(gross_before / nav), supplied_gross_exposure_after=str(gross_after / nav),
                  coverage=portfolio.get('completeness', 'unknown'), costs_in_exposure_scenario=False,
                  crosses_zero_inventory=before * after < 0,
                  short_cover_interpretation='Declared signed-notional scenario only; labels do not establish inventory availability, borrow, a locate or an actual short/cover fill.',
                  limitation='Fixed marks and full supplied NAV denominator; partial holdings remain partial. No correlation, executable sizing, margin, settlement or cash-access inference.')
    return result


def _costs(document, ticker, cutoff):
    result = {'status': 'ASSUMPTIONS_NOT_SUPPLIED', 'costs': None, 'liquidity': deepcopy(document.get('liquidity')),
              'executable_capacity_established': False, 'borrow_access_established': False}
    if document.get('cost_contract') is not None:
        import planning_alignment
        result['costs'] = planning_alignment.trade_costs(deepcopy(document['cost_contract']))
        result['status'] = 'DECLARED_COSTS_COMPUTED'
        proposed = document.get('proposed_trade')
        result['cost_contract_matches_proposed_notional'] = None if proposed is None else (
            document['cost_contract'].get('currency') == proposed.get('currency')
            and _number(result['costs']['gross_notional']) == _number(proposed['notional'], 0))
    liquidity = document.get('liquidity')
    if liquidity is not None:
        _require(isinstance(liquidity, dict) and liquidity.get('ticker') == ticker, 'LIQUIDITY_TICKER_REQUIRED')
        if liquidity.get('available_at') is None or _stamp(liquidity['available_at']) > cutoff:
            result['liquidity_status'] = 'CLOCK_UNUSABLE'
        else:
            _require(liquidity.get('currency') == 'USD', 'USD_LIQUIDITY_REQUIRED')
            adv = _number(liquidity['average_daily_dollar_volume'], '0.000000000001')
            order = _number(liquidity['order_notional'], 0)
            result.update(liquidity_status='DECLARED_SCALE_CONTEXT', order_to_declared_adv=str(order / adv),
                          spread_bps=None if liquidity.get('spread_bps') is None else str(_number(liquidity['spread_bps'], 0)),
                          liquidity_limitation='ADV ratio is descriptive scale, not a feasible participation schedule, executable capacity or market-impact estimate.')
            proposed = document.get('proposed_trade')
            result['liquidity_matches_proposed_notional'] = None if proposed is None else order == _number(proposed['notional'], 0)
    result['review'] = ['Check timestamp, units, spread, fees, slippage, partial fills and halt/event liquidity.',
                        'For short exposure, separately qualify borrow availability, fee, recalls and unlimited-loss risk; public short data does not supply a locate.']
    return result


@_workflow_protocol
def brief(document):
    """Create a decision brief at the supplied cutoff, without selecting an order."""
    result = _base(document, 'INSTITUTIONAL_EVENT_BRIEF')
    pilot, universe, missing = _configuration(document)
    event = deepcopy(document.get('event', {}))
    ticker = event.get('ticker')
    _require(isinstance(ticker, str) and ticker, 'EVENT_TICKER_REQUIRED')
    cutoff = _stamp(document['as_of'])
    if event.get('decision_at') is not None:
        _require(_stamp(event['decision_at']) == cutoff, 'DECISION_CUTOFF_MUST_EQUAL_AS_OF')
    in_scope = universe['mode'] != 'explicit_symbols' or ticker in universe['symbols']
    eligible = [r for r in result['evidence']['records'] if r.get('eligible') and r.get('ticker') == ticker and in_scope]
    supplied_hypotheses = deepcopy(document.get('hypotheses', []))
    _require(isinstance(supplied_hypotheses, list), 'HYPOTHESES_LIST_REQUIRED')
    result.update(status='BRIEF_FOR_REVIEW' if eligible else 'INSUFFICIENT_ELIGIBLE_EVENT_EVIDENCE',
                  event=event, pilot=pilot, requested_discovery_universe=universe,
                  missing_configuration=missing, event_in_declared_scope=in_scope,
                  evidence_record_ids=[r['id'] for r in eligible], hypotheses=supplied_hypotheses,
                  catalyst_records=[deepcopy(r) for r in eligible if r.get('kind') == 'catalyst'],
                  decision={'disposition': document.get('disposition', 'RESEARCH_ONLY'),
                            'rationale': deepcopy(document.get('decision_rationale')),
                            'alternatives': deepcopy(document.get('alternatives', [])),
                            'invalidation_conditions': deepcopy(document.get('invalidation_conditions', [])),
                            'review_at': event.get('review_at'), 'horizon': deepcopy(event.get('horizon', pilot.get('horizon'))),
                            'selected_action_is_user_supplied': 'disposition' in document},
                  portfolio_impact=_portfolio(document, ticker, cutoff),
                  cost_liquidity_review=_costs(document, ticker, cutoff),
                  independent_challenge=_challenge(document.get('challenge'), cutoff),
                  readiness=_readiness(document, missing), profitability_established=False)
    _require('include_flow_analysis' not in document or type(document['include_flow_analysis']) is bool, 'FLOW_ANALYSIS_BOOLEAN_REQUIRED')
    if document.get('include_flow_analysis') is True:
        import market_flow
        flow_input = deepcopy(document)
        dependencies = {r['payload']['benchmark_record_id'] for r in eligible
                        if r.get('kind') == 'bar' and isinstance(r['payload'].get('benchmark_record_id'), str)}
        dependencies = {r['id'] for r in result['evidence']['records']
                        if r.get('eligible') and r['id'] in dependencies and r.get('kind') == 'bar'
                        and r['payload'].get('role') == 'benchmark'}
        record_index = {r['id']: r for r in result['evidence']['records'] if isinstance(r.get('id'), str)}
        def bar_key(row):
            p = row['payload']
            return (row.get('ticker'), p.get('feed_id'), p.get('start_at'), p.get('end_at'),
                    p.get('session_id'), p.get('comparison_group'))
        benchmark_keys = {bar_key(record_index[rid]) for rid in dependencies}
        # Keep competing active feed identities too: omitting one could turn a
        # conflicting or deduplicated benchmark into an apparently usable one.
        dependencies.update(r['id'] for r in result['evidence']['records']
                            if r.get('eligible') and r.get('kind') == 'bar'
                            and r['payload'].get('bar_type') == 'cumulative' and bar_key(r) in benchmark_keys)
        pending = list(dependencies)
        while pending:
            parent = record_index[pending.pop()].get('supersedes')
            if isinstance(parent, str) and parent in record_index and parent not in dependencies:
                dependencies.add(parent); pending.append(parent)
        flow_input['records'] = [deepcopy(r) for r in document.get('records', [])
                                 if (r.get('ticker') == ticker and in_scope) or r.get('id') in dependencies]
        result['flow_dependency_record_ids'] = sorted(dependencies)
        result['flow'] = market_flow.analyze(flow_input)
        result['positioning'] = market_flow.positioning(flow_input)
        result['squeeze'] = market_flow.squeeze(flow_input)
    return result


def _challenge(challenge, cutoff):
    if challenge is None:
        return {'status': 'NOT_SUPPLIED', 'independence_verified': False, 'findings': []}
    _require(isinstance(challenge, dict), 'CHALLENGE_OBJECT_REQUIRED')
    value = deepcopy(challenge)
    at = challenge.get('reviewed_at')
    status = 'SUPPLIED_CHALLENGE_NOT_AUTHENTICATED' if at is not None and _stamp(at) <= cutoff else 'CLOCK_UNUSABLE'
    return {'status': status, 'independence_verified': False, 'declaration': value,
            'findings': deepcopy(challenge.get('findings', [])) if status != 'CLOCK_UNUSABLE' else [],
            'limitation': 'Reviewer identity, external invocation and independence are not authenticated by this helper.'}


def _evaluation_protocol(document, evaluation, has_returns):
    """Reconcile declarations in this input; never authenticate registration."""
    fields = {'registered_at': 'registered_at', 'start_at': 'study_start', 'end_at': 'study_end',
              'usefulness_criterion': 'usefulness_criterion', 'workflow_baseline_id': 'workflow_baseline_id'}
    supplied = 'pilot' in document
    result = {'status': 'DECLARATION_ONLY_NO_PILOT', 'pilot_present': supplied,
              'declared_pilot': deepcopy(document.get('pilot')), 'pilot_sha256': None,
              'declared_evaluation_protocol': {k: deepcopy(v) for k, v in evaluation.items() if k != 'cases'},
              'conflicts': [], 'missing_configuration': [], 'registration_authenticated': False,
              'limitation': 'Reconciliation checks supplied declarations only; retain the actual adopted protocol and journal separately.'}
    if not supplied:
        return result, None, [], []
    pilot, universe, missing = _configuration(document)
    result.update(pilot_sha256=_digest(pilot), missing_configuration=list(missing))
    common, return_reasons = [], []
    if missing:
        common.append('SUPPLIED_PILOT_CONFIGURATION_INCOMPLETE')

    def conflict(field, pilot_value, evaluation_value, target):
        result['conflicts'].append({'field': field, 'pilot_value': deepcopy(pilot_value),
                                    'evaluation_value': deepcopy(evaluation_value), 'scope': 'protocol'})
        target.append('PILOT_EVALUATION_PROTOCOL_CONFLICT:' + field)

    study = pilot.get('study') or {}
    for field, counterpart in fields.items():
        if field not in study:
            continue  # Already reported as missing by the pilot configuration review.
        left, right = study[field], evaluation.get(counterpart)
        equal = _stamp(left) == _stamp(right) if field in {'registered_at', 'start_at', 'end_at'} and left and right else left == right
        if not equal:
            conflict('study.' + field, left, right, common)
    for field, actual in (('pilot_id', pilot.get('id')), ('pilot_sha256', result['pilot_sha256'])):
        if field in evaluation and evaluation[field] != actual:
            conflict(field, actual, evaluation[field], common)
    if 'expected_case_ids' in study and study['expected_case_ids'] != evaluation.get('expected_case_ids'):
        # Roster order is immaterial, but every declared membership must agree.
        left, right = study['expected_case_ids'], evaluation.get('expected_case_ids')
        _require(isinstance(left, list) and all(isinstance(x, str) for x in left)
                 and len(left) == len(set(left)), 'UNIQUE_PILOT_EXPECTED_CASE_IDS_REQUIRED')
        if not isinstance(right, list) or set(left) != set(right):
            conflict('study.expected_case_ids', left, right, common)
    if has_returns:
        baseline = study.get('return_baseline_id')
        if not baseline:
            result['missing_configuration'].append('study.return_baseline_id')
            return_reasons.append('PILOT_RETURN_BASELINE_NOT_PRESPECIFIED')
        elif baseline != evaluation.get('return_baseline_id'):
            conflict('study.return_baseline_id', baseline, evaluation.get('return_baseline_id'), return_reasons)
    result['status'] = ('PROTOCOL_CONFLICT' if result['conflicts'] else 'PROTOCOL_CONFIGURATION_INCOMPLETE'
                        if result['missing_configuration'] else 'MATCHED_DECLARED_PROTOCOL')
    return result, universe, common, return_reasons


def _input_ids(value, label):
    _require(isinstance(value, list) and len(value) <= MAX_RECORDS
             and all(isinstance(x, str) and x for x in value) and len(value) == len(set(value)),
             'UNIQUE_' + label + '_RECORD_IDS_REQUIRED')
    return value


def _case_scope(document, case, ids, universe):
    """Infer only the target declaration; benchmark/dependency tickers are not targets."""
    ticker, basis = case.get('ticker'), 'CASE_TICKER'
    if ticker is None:
        event = document.get('event')
        ticker = event.get('ticker') if isinstance(event, dict) else None
        basis = 'DOCUMENT_EVENT_TICKER'
    if ticker is None:
        candidates = {r.get('ticker') for r in document['records'] if isinstance(r, dict) and r.get('id') in ids
                      and isinstance(r.get('ticker'), str) and r['ticker'] and isinstance(r.get('payload'), dict)
                      and r['payload'].get('role') != 'benchmark'}
        if len(candidates) == 1:
            ticker, basis = next(iter(candidates)), 'UNIQUE_NONBENCHMARK_INPUT_TICKER'
        else:
            basis = 'TARGET_TICKER_UNRESOLVED'
    _require(ticker is None or isinstance(ticker, str) and ticker, 'CASE_TICKER_REQUIRED_IF_SUPPLIED')
    if universe is None:
        status = 'NO_SUPPLIED_PILOT_UNIVERSE'
    elif universe['mode'] == 'us_listed_full':
        status = 'REQUESTED_US_LISTED_SCOPE_NOT_CERTIFIED'
    else:
        status = 'TARGET_TICKER_UNRESOLVED' if ticker is None else 'DECLARED_SCOPE_MATCH' if ticker in universe['symbols'] else 'TARGET_OUTSIDE_DECLARED_SCOPE'
    return {'ticker': ticker, 'basis': basis, 'status': status}


@_workflow_protocol
def evaluate(document):
    """Evaluate prospective usefulness separately from descriptive paper returns."""
    result = _base(document, 'INSTITUTIONAL_EVENT_EVALUATION')
    evaluation = deepcopy(document.get('evaluation'))
    _require(isinstance(evaluation, dict), 'EVALUATION_OBJECT_REQUIRED')
    at = _stamp(document['as_of'])
    registered = _stamp(evaluation['registered_at'])
    start, end = _stamp(evaluation['study_start']), _stamp(evaluation['study_end'])
    _require(registered <= start < end, 'PROSPECTIVE_ORDERED_STUDY_REQUIRED')
    _require(isinstance(evaluation.get('usefulness_criterion'), str) and evaluation['usefulness_criterion'], 'PRESPECIFIED_USEFULNESS_CRITERION_REQUIRED')
    _require(isinstance(evaluation.get('workflow_baseline_id'), str) and evaluation['workflow_baseline_id'], 'PRESPECIFIED_WORKFLOW_BASELINE_REQUIRED')
    cases = evaluation.get('cases')
    _require(isinstance(cases, list) and len({c['id'] for c in cases}) == len(cases), 'UNIQUE_EVALUATION_CASES_REQUIRED')
    protocol, universe, protocol_reasons, protocol_return_reasons = _evaluation_protocol(
        document, evaluation, any(c.get('paper_return') is not None for c in cases))
    rows, useful, saved, excess = [], [], [], []
    import market_sources
    for case in cases:
        reasons = list(protocol_reasons)
        useful_reasons, return_reasons = [], list(protocol_return_reasons)
        decision = _stamp(case['decision_at'])
        first = case.get('first_response', {})
        first_at = _stamp(first['captured_at']) if first.get('captured_at') else None
        if not (start <= decision <= end and registered <= decision <= at):
            reasons.append('DECISION_OUTSIDE_AVAILABLE_PROSPECTIVE_STUDY')
        text = first.get('text')
        verified_first = isinstance(text, str) and isinstance(first.get('sha256'), str) and hashlib.sha256(text.encode('utf-8')).hexdigest() == first['sha256']
        if not verified_first or first_at is None or not registered <= first_at <= decision:
            reasons.append('FIRST_RESPONSE_BYTES_HASH_OR_PREDECISION_CLOCK_UNESTABLISHED')
        ids = _input_ids(case.get('input_record_ids', []), 'INPUT')
        evidence = market_sources.normalize({'schema_version': 1, 'as_of': case['decision_at'], 'records': deepcopy(document.get('records', []))})
        available_ids = {r['id'] for r in evidence['records'] if r.get('eligible')}
        if not ids or not set(ids) <= available_ids:
            reasons.append('DECISION_INPUTS_MISSING_OR_UNAVAILABLE_AT_CUTOFF')
        explicit_response_ids = 'input_record_ids' in first
        response_ids = _input_ids(first.get('input_record_ids', ids), 'FIRST_RESPONSE_INPUT')
        response_available = set()
        if first_at is not None:
            response_evidence = market_sources.normalize({'schema_version': 1, 'as_of': first['captured_at'],
                                                          'records': deepcopy(document['records'])})
            response_available = {r['id'] for r in response_evidence['records'] if r.get('eligible')}
        response_missing = sorted(set(response_ids) - response_available)
        if not response_ids or response_missing:
            reasons.append('FIRST_RESPONSE_INPUTS_MISSING_OR_UNAVAILABLE_AT_CAPTURE')
        scope = _case_scope(document, case, set(ids) & available_ids, universe)
        if scope['status'] in {'TARGET_TICKER_UNRESOLVED', 'TARGET_OUTSIDE_DECLARED_SCOPE'} and universe is not None:
            reasons.append(scope['status'])
            protocol['conflicts'].append({'field': 'universe', 'scope': 'case', 'case_id': case['id'],
                                          'pilot_value': deepcopy(universe), 'evaluation_value': deepcopy(scope)})
        record_hashes = {r['id']: _digest(r) for r in document['records']
                         if r.get('id') in response_ids and r.get('id') in response_available}
        response_review = {'status': 'MATCHED_DECLARED_RESPONSE_INPUTS' if response_ids and not response_missing else 'RESPONSE_INPUTS_UNAVAILABLE',
                           'binding_mode': 'EXPLICIT_RESPONSE_INPUTS' if explicit_response_ids else 'LEGACY_COMMON_INPUTS_CHECKED_AT_CAPTURE',
                           'captured_at': first.get('captured_at'), 'response_input_record_ids': deepcopy(response_ids),
                           'decision_input_record_ids': deepcopy(ids), 'unavailable_response_input_record_ids': response_missing,
                           'later_decision_input_record_ids': sorted(set(ids) - set(response_ids)),
                           'response_record_sha256': record_hashes, 'record_hash_basis': 'CANONICAL_JSON_RECORD_VALUES',
                           'input_manifest_sha256': _digest({'captured_at': first.get('captured_at'), 'record_ids': response_ids,
                                                           'record_sha256': record_hashes}),
                           'actual_response_consumption_verified': False}
        row = {'id': case['id'], 'declared_case': deepcopy(case), 'prospective_exclusion_reasons': reasons,
               'first_response_bytes_hash_verified': verified_first, 'usefulness_included': False,
                'returns_included': False, 'response_input_review': response_review, 'scope_review': scope,
                'usefulness_exclusion_reasons': useful_reasons, 'return_exclusion_reasons': return_reasons}
        outcome = case.get('usefulness')
        if outcome is not None:
            if protocol['pilot_present']:
                reviewer = (document['pilot'].get('reviewer') or {}).get('id')
                if outcome.get('reviewer_id') != reviewer:
                    useful_reasons.append('PILOT_REVIEWER_MISMATCH')
                    protocol['conflicts'].append({'field': 'reviewer.id', 'scope': 'case_usefulness', 'case_id': case['id'],
                                                  'pilot_value': reviewer, 'evaluation_value': outcome.get('reviewer_id')})
            valid = (outcome.get('available_at') is not None and decision <= _stamp(outcome['available_at']) <= at
                     and outcome.get('criterion') == evaluation['usefulness_criterion']
                     and type(outcome.get('useful')) is bool and bool(outcome.get('reviewer_id'))
                     and outcome.get('baseline_id') == evaluation['workflow_baseline_id'])
            if valid and not reasons and not useful_reasons:
                assisted = _number(outcome['assisted_minutes'], 0)
                baseline = _number(outcome['baseline_minutes'], 0)
                useful.append(outcome['useful']); saved.append(baseline - assisted)
                row.update(usefulness_included=True, declared_minutes_saved=str(baseline - assisted))
            else:
                row['usefulness_status'] = 'MISSING_CLOCK_CRITERION_BASELINE_OR_PROSPECTIVE_EVIDENCE'
        returns = case.get('paper_return')
        if returns is not None:
            benchmark = returns.get('benchmark', {})
            try:
                lo, hi = _stamp(returns['period_start']), _stamp(returns['period_end'])
                valid = (decision <= lo < hi <= end and hi <= _stamp(returns['available_at']) <= at
                         and _stamp(benchmark.get('period_start')) == lo
                         and _stamp(benchmark.get('period_end')) == hi
                         and returns.get('currency') == benchmark.get('currency') == 'USD'
                         and returns.get('return_basis') == benchmark.get('return_basis') == 'simple_total_return_decimal'
                         and returns.get('net_costs_included') is True and benchmark.get('net_costs_included') is True
                         and bool(evaluation.get('return_baseline_id'))
                         and benchmark.get('id') == evaluation['return_baseline_id'] and hi <= _stamp(benchmark['available_at']) <= at)
                if valid and not reasons and not return_reasons:
                    delta = _number(returns['return_decimal'], -1) - _number(benchmark['return_decimal'], -1)
                    excess.append(delta)
                    row.update(returns_included=True, descriptive_excess_return_decimal=str(delta))
                else:
                    row['returns_status'] = 'NONMATCHING_OR_UNAVAILABLE_NET_RETURN_BASELINE'
            except (KeyError, ValueError, TypeError):
                row['returns_status'] = 'INCOMPLETE_OR_INVALID_RETURN_CONTRACT'
        rows.append(row)
    if protocol['conflicts']:
        protocol['status'] = 'PROTOCOL_CONFLICT'
    expected = evaluation.get('expected_case_ids')
    if expected is not None:
        _require(isinstance(expected, list) and len(expected) == len(set(expected)), 'UNIQUE_EXPECTED_CASE_IDS_REQUIRED')
    present = {c['id'] for c in cases}
    result.update(status='DECLARED_STUDY_WINDOW_ELAPSED' if end <= at else 'PROSPECTIVE_PILOT_IN_PROGRESS',
                  evaluation_contract=evaluation, protocol_reconciliation=protocol, cases=rows,
                  roster={'status': 'UNKNOWN' if expected is None else 'MATCHED' if set(expected) == present else 'INCOMPLETE_OR_UNEXPECTED',
                          'missing': [] if expected is None else sorted(set(expected) - present),
                          'unexpected': [] if expected is None else sorted(present - set(expected))},
                  usefulness={'included_cases': len(useful), 'declared_useful_count': sum(useful),
                              'declared_useful_fraction': None if not useful else str(Decimal(sum(useful)) / len(useful)),
                              'mean_declared_minutes_saved': None if not saved else str(sum(saved) / len(saved)),
                              'basis': 'Supplied reviewer judgment and workflow baseline; no causal time-saving attribution.'},
                  returns={'included_cases': len(excess), 'mean_descriptive_excess_return_decimal': None if not excess else str(sum(excess) / len(excess)),
                           'overlapping_periods_not_compounded': True, 'annualization_or_significance_computed': False},
                  challenge=_challenge(document.get('challenge'), at),
                  actual_elapsed_operation_verified=False, profitability_established=False,
                  external_or_independent_validation_established=False,
                  readiness=_readiness(document, []))
    return result


def _directory(root, name):
    path = root / name
    if not path.exists():
        path.mkdir()
    _require(path.is_dir() and not path.is_symlink() and path.resolve() == root / name, 'OWNED_DIRECTORY_REQUIRED')
    return path


def _root(value):
    path = Path(value)
    _require(path.is_dir() and not path.is_symlink(), 'EXPLICIT_EXISTING_PRIVATE_ROOT_REQUIRED')
    return path.resolve()


def _read(path):
    _require(path.is_file() and not path.is_symlink(), 'REGULAR_FILE_REQUIRED')
    _require(path.stat().st_size <= MAX_BYTES, 'INPUT_SIZE_CAP')
    value = path.read_bytes()
    _require(len(value) <= MAX_BYTES, 'INPUT_SIZE_CAP')
    return value


def _publish(path, data):
    """Atomic no-clobber publication via same-directory hard link; no unsafe fallback."""
    if path.exists() or path.is_symlink():
        _require(_read(path) == data, 'IMMUTABLE_ARTIFACT_CONFLICT')
        return
    temp = path.parent / ('.tmp-' + uuid.uuid4().hex)
    try:
        with temp.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            _require(_read(path) == data, 'IMMUTABLE_ARTIFACT_CONFLICT')
    finally:
        if temp.exists():
            temp.unlink()


@contextmanager
def _lock(root, release_guard=False):
    path = root / ('.institutional-release.lock' if release_guard else '.institutional.lock')
    if not release_guard:
        _require(not (root / '.institutional-release.lock').exists(), 'LOCK_HELD_RELEASE_IN_PROGRESS')
    token = _bytes({'pid': os.getpid(), 'token': uuid.uuid4().hex, 'created_at': datetime.now(timezone.utc).isoformat()})
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError('LOCK_HELD_NO_AUTOMATIC_STALE_BREAK') from exc
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(token); stream.flush(); os.fsync(stream.fileno())
        yield
    finally:
        if path.is_file() and not path.is_symlink() and path.read_bytes() == token:
            path.unlink()


def _complete(root, transaction):
    entry_id = _id(transaction['entry']['id'])
    digest = _hash(transaction['entry']['object_sha256'])
    object_path = _directory(root, 'objects') / (digest + '.bin')
    _require(hashlib.sha256(_read(object_path)).hexdigest() == digest, 'CAPTURE_HASH_MISMATCH')
    data = _bytes(transaction['entry']) + b'\n'
    entry_path = _directory(root, 'entries') / (entry_id + '.json')
    _publish(entry_path, data)
    commit = {'id': entry_id, 'entry_sha256': hashlib.sha256(data).hexdigest(), 'object_sha256': digest}
    _publish(_directory(root, 'commits') / (entry_id + '.json'), _bytes(commit) + b'\n')
    return {'status': 'COMMITTED', **commit, 'execution_authorized': False}


def _record(root_value, entry_id, kind, raw, metadata):
    root = _root(root_value); _id(entry_id)
    _require(kind in {'protocol', 'brief', 'evaluation', 'challenge', 'first_response', 'failure', 'capture'}, 'JOURNAL_KIND_REQUIRED')
    _require(isinstance(raw, bytes) and len(raw) <= MAX_BYTES, 'INPUT_SIZE_CAP')
    digest = hashlib.sha256(raw).hexdigest()
    stable = {'id': entry_id, 'kind': kind, 'object_sha256': digest, 'bytes': len(raw), 'metadata': deepcopy(metadata)}
    key = _digest(stable)
    with _lock(root):
        path = _directory(root, 'transactions') / (entry_id + '.json')
        if path.exists():
            transaction = json.loads(_read(path))
            stored = {k: v for k, v in transaction['entry'].items() if k != 'recorded_at'}
            _require(transaction['idempotency_key'] == key and stored == stable, 'ENTRY_ID_CONFLICT_RETAIN_ORIGINAL')
        else:
            _publish(_directory(root, 'objects') / (digest + '.bin'), raw)
            entry = dict(stable, recorded_at=datetime.now(timezone.utc).isoformat())
            transaction = {'schema_version': 1, 'idempotency_key': key, 'entry': entry}
            _publish(path, _bytes(transaction) + b'\n')
        return _complete(root, transaction)


def _recover(root_value, entry_id):
    root = _root(root_value); _id(entry_id)
    with _lock(root):
        transaction = json.loads(_read(_directory(root, 'transactions') / (entry_id + '.json')))
        _require(transaction['entry']['id'] == entry_id, 'TRANSACTION_ID_MISMATCH')
        stable = {k: v for k, v in transaction['entry'].items() if k != 'recorded_at'}
        _require(_digest(stable) == transaction['idempotency_key'], 'TRANSACTION_HASH_MISMATCH')
        return _complete(root, transaction)


def _release_lock(root_value, expected_sha256, confirmed_stopped=False):
    root = _root(root_value); _hash(expected_sha256)
    _require(confirmed_stopped is True, 'OPERATOR_MUST_CONFIRM_OWNER_STOPPED')
    with _lock(root, release_guard=True):
        path = root / '.institutional.lock'
        original = _read(path)
        _require(hashlib.sha256(original).hexdigest() == expected_sha256 and _read(path) == original, 'LOCK_HASH_CHANGED')
        _publish(_directory(root, 'lock-releases') / (expected_sha256 + '.json'), original)
        _require(_read(path) == original, 'LOCK_HASH_CHANGED_DURING_RELEASE')
        path.unlink()
    return {'status': 'EXPLICIT_LOCK_RELEASED', 'execution_authorized': False,
            'limitation': 'Operator confirmed owner stopped; helper did not infer staleness or prove process state.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('plan', 'brief', 'evaluate'):
        item = sub.add_parser(name); item.add_argument('--input', required=True)
    for name in ('journal', 'capture'):
        item = sub.add_parser(name)
        item.add_argument('--root', required=True); item.add_argument('--entry-id', required=True)
        item.add_argument('--input', required=True); item.add_argument('--parent-id')
        if name == 'journal':
            item.add_argument('--kind', choices=['protocol', 'brief', 'evaluation', 'challenge', 'first_response', 'failure'], required=True)
        else:
            item.add_argument('--available-at', required=True); item.add_argument('--source-id', required=True)
            item.add_argument('--rights', default='unknown'); item.add_argument('--expected-sha256')
    item = sub.add_parser('recover'); item.add_argument('--root', required=True); item.add_argument('--entry-id', required=True)
    item = sub.add_parser('release-lock'); item.add_argument('--root', required=True)
    item.add_argument('--expected-lock-sha256', required=True); item.add_argument('--operator-confirmed-stopped', action='store_true')
    args = parser.parse_args(argv)
    if args.command in {'plan', 'brief', 'evaluate'}:
        document = json.loads(_read(Path(args.input)))
        result = {'plan': plan, 'brief': brief, 'evaluate': evaluate}[args.command](document)
    elif args.command in {'journal', 'capture'}:
        raw = _read(Path(args.input)); metadata = {'parent_id': args.parent_id}
        if args.parent_id is not None:
            _id(args.parent_id)
        if args.command == 'capture':
            _stamp(args.available_at); _id(args.source_id)
            if args.expected_sha256:
                _require(hashlib.sha256(raw).hexdigest() == _hash(args.expected_sha256), 'EXPECTED_CAPTURE_HASH_MISMATCH')
            metadata.update(available_at=args.available_at, source_id=args.source_id, rights=args.rights,
                            availability_basis='operator_declared_local_capture', source_authenticity_verified=False)
        result = _record(args.root, args.entry_id, args.kind if args.command == 'journal' else 'capture', raw, metadata)
    elif args.command == 'recover':
        result = _recover(args.root, args.entry_id)
    else:
        result = _release_lock(args.root, args.expected_lock_sha256, args.operator_confirmed_stopped)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'ERROR', 'error': str(exc), 'execution_authorized': False}), file=sys.stderr)
        raise SystemExit(2)
