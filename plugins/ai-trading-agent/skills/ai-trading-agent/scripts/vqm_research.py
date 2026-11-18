"""Frozen, point-in-time VQM research baseline. No network or order submission.

Formulas are repository-authored conventions, not a replication of a published
portfolio. Source metadata and accounting mappings remain supplied evidence.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import date, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

from deterministic_rank import digest, number
from price_audit import timestamp
from trading_calendar import sessions

ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = ROOT / 'profiles/vqm-fundamental-v1.json'


def profile():
    return json.loads(PROFILE_PATH.read_text(encoding='utf-8'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def session_grid(decision_at):
    """Use the last scheduled completed XNYS session, including early closes."""
    decision = timestamp(decision_at)
    grid = sessions((decision.date() - timedelta(days=550)).isoformat(),
                    decision.date().isoformat(), 'XNYS')
    completed = [s for s in grid if timestamp(s['close']) <= decision]
    require(len(completed) >= 253, 'Need 253 completed calendar sessions')
    return completed[-253:]


def adapter(row):
    sector, industry = row['sector_code'], row['industry_code']
    require(bool(re.fullmatch(r'\d{2}', sector)) and bool(re.fullmatch(r'\d{6}', industry))
            and industry.startswith(sector), 'Invalid GICS sector/industry codes')
    if industry == '401010':
        return 'bank'
    if industry == '403010':
        return 'insurer'
    if sector == '40':
        return 'other_financial'
    if industry.startswith('6010'):
        return 'equity_reit'
    return 'corporate'


def fact_value(row, name, sources, cutoff, kind, expected_period=None):
    observation = row.get('facts', {}).get(name)
    require(isinstance(observation, dict), 'MISSING_FACT:' + name)
    source = sources.get(observation.get('source_id'), {})
    require(source.get('kind') == kind, 'SOURCE_KIND:' + name)
    require(timestamp(source['published_at']) <= cutoff, 'FUTURE_SOURCE:' + name)
    require(observation.get('unit') == 'USD', 'FACT_UNIT:' + name)
    if expected_period is not None:
        require(observation.get('period_end') == expected_period, 'PERIOD_MISMATCH:' + name)
        source_period = observation.get('balance_date', expected_period) if name.endswith('_prior') else expected_period
        require(timestamp(source['published_at']).date() >= date.fromisoformat(source_period),
                'SOURCE_PREDATES_FINANCIAL_PERIOD:' + name)
    if kind == 'market':
        require(timestamp(observation['observed_at']) == cutoff, 'MARKET_OBSERVATION_CUTOFF:' + name)
    return number(observation['value'])


def raw_metrics(row, sources, cutoff):
    """Calculate signed yields; do not discard loss makers or estimate addbacks."""
    period = date.fromisoformat(row['financial_period_end'])
    require(0 <= (cutoff.date() - period).days <= profile()['max_financial_period_age_days'],
            'FINANCIAL_PERIOD_STALE_OR_FUTURE')
    start = date.fromisoformat(row['ttm_start'])
    require(350 <= (period - start).days + 1 <= 380, 'TTM_PERIOD_LENGTH')
    require(row.get('currency') == 'USD', 'CURRENCY_UNSUPPORTED')
    require(row.get('accounting_basis') == 'reported_gaap_ttm', 'ACCOUNTING_BASIS')
    require(row.get('latest_public_period_checked') is True, 'LATEST_PERIOD_UNREVIEWED')
    require(row.get('source_conflicts') == [], 'SOURCE_CONFLICT_UNRESOLVED')
    a = adapter(row)
    def f(name):
        value = fact_value(row, name, sources, cutoff, 'financial', period.isoformat())
        if name.endswith('_ttm'):
            require(row['facts'][name].get('period_start') == start.isoformat(), 'TTM_START:' + name)
        if name.endswith('_prior'):
            prior = date.fromisoformat(row['facts'][name].get('balance_date', ''))
            require(prior == start - timedelta(days=1), 'AVERAGE_BALANCE_DATE:' + name)
        return value
    def pos(value, name):
        require(value > 0, 'NONPOSITIVE_DENOMINATOR:' + name)
        return value
    def nn(value, name):
        require(value >= 0, 'NEGATIVE_BALANCE:' + name)
        return value
    market_cap = pos(fact_value(row, 'market_cap', sources, cutoff, 'market'), 'market_cap')
    pos(fact_value(row, 'close_price', sources, cutoff, 'market'), 'close_price')
    require(row['facts']['market_cap'].get('period_end') == cutoff.date().isoformat(), 'MARKET_CAP_DATE')
    require(row.get('market_cap_scope') == 'all_common_share_classes', 'MARKET_CAP_SCOPE')
    if a in {'corporate', 'equity_reit'}:
        assets = pos(f('assets'), 'assets')
        avg_assets = (assets + pos(f('assets_prior'), 'assets_prior')) / 2
        debt, cash = nn(f('debt'), 'debt'), nn(f('cash'), 'cash')
        cfo, capex, income = f('cfo_ttm'), nn(f('capex_ttm'), 'capex_ttm'), f('net_income_ttm')
        if a == 'corporate':
            ev = pos(market_cap + debt + nn(f('preferred_equity'), 'preferred_equity')
                     + nn(f('noncontrolling_interest'), 'noncontrolling_interest') - cash,
                     'enterprise_value')
            value_a, quality_a = f('ebit_ttm') / ev, income / avg_assets
        else:
            require(row.get('ffo_basis') == 'nareit_unadjusted_common', 'FFO_BASIS')
            value_a, quality_a = f('ffo_common_ttm') / market_cap, f('ffo_common_ttm') / avg_assets
        v = [value_a, (cfo - capex) / market_cap]
        q = [quality_a, (cfo - income) / avg_assets, -(debt - cash) / assets]
    elif a == 'bank':
        equity = pos(f('tangible_common_equity'), 'tangible_common_equity')
        average = (equity + pos(f('tangible_common_equity_prior'), 'tangible_common_equity_prior')) / 2
        income = f('common_income_ttm')
        v = [income / market_cap, equity / market_cap]
        q = [income / average, nn(f('cet1'), 'cet1') / pos(f('risk_weighted_assets'), 'risk_weighted_assets'),
             -nn(f('nonperforming_loans'), 'nonperforming_loans') / pos(f('gross_loans'), 'gross_loans')]
    else:
        equity = pos(f('common_equity'), 'common_equity')
        average = (equity + pos(f('common_equity_prior'), 'common_equity_prior')) / 2
        income = f('common_income_ttm')
        v = [income / market_cap, equity / market_cap]
        q = [income / average, equity / pos(f('assets'), 'assets'), -nn(f('debt'), 'debt') / equity]
    return a, v, q


def midrank(value, population):
    n = Decimal(len(population))
    return 2 * (sum(x < value for x in population) + Decimal('0.5') * sum(x == value for x in population)) / n - 1


def calculate(snapshot):
    with localcontext() as context:
        context.prec = 40
        if snapshot.get('schema_version') == 2:
            from financial_normalize import materialize
            derived, normalization = materialize(snapshot)
            derived['schema_version'] = 1
            result = _calculate(derived)
            result['snapshot_sha256'] = digest(snapshot)
            result['normalization'] = normalization
            result['input_assurance'] = 'SHARED_NORMALIZATION_REPLAY'
            return result
        result = _calculate(snapshot)
        result['input_assurance'] = 'LEGACY_DECLARED_FACTS_NOT_NORMALIZED'
        return result


def _calculate(snapshot):
    p = profile()
    require(snapshot.get('schema_version') == 1, 'Unsupported VQM snapshot schema')
    require(snapshot.get('profile_sha256') == digest(p), 'PROFILE_HASH_MISMATCH')
    for key in ('snapshot_id', 'universe_id', 'benchmark_id', 'taxonomy_version', 'market_provider', 'universe_provider'):
        require(nonempty(snapshot.get(key)), 'Snapshot requires ' + key)
    grid = session_grid(snapshot['decision_at'])
    cutoff = timestamp(snapshot['information_cutoff'])
    require(cutoff == timestamp(grid[-1]['close']), 'CUTOFF_NOT_LAST_COMPLETED_SESSION')
    require(snapshot.get('calendar_reviewed_through', '') >= grid[-1]['date'], 'CALENDAR_NOT_REVIEWED')
    require(nonempty(snapshot.get('calendar_evidence')), 'CALENDAR_EVIDENCE_MISSING')
    require(timestamp(snapshot['contract_defined_at']) <= timestamp(snapshot['retrieval_started_at']),
            'CONTRACT_DEFINED_AFTER_RETRIEVAL')
    universe = snapshot['universe_symbols']
    require(isinstance(universe, list) and universe and all(nonempty(x) for x in universe)
            and len(universe) == len(set(universe)), 'UNIVERSE_IDENTIFIERS')
    rows = snapshot['rows']
    require(isinstance(rows, list) and len(rows) == len(universe)
            and {r['symbol'] for r in rows} == set(universe), 'ROWS_MUST_COVER_UNIVERSE_ONCE')
    sources = {}
    for s in snapshot['sources']:
        sid = s['source_id']
        require(nonempty(sid) and sid not in sources, 'DUPLICATE_SOURCE')
        require(s['kind'] in {'financial', 'market', 'identity'}, 'SOURCE_KIND')
        require(nonempty(s.get('uri')) and bool(re.fullmatch('[0-9a-f]{64}', s.get('content_sha256', ''))), 'SOURCE_PROVENANCE')
        published, retrieved = timestamp(s['published_at']), timestamp(s['retrieved_at'])
        require(published <= retrieved and timestamp(snapshot['retrieval_started_at']) <= retrieved, 'SOURCE_TIMESTAMPS')
        if s['kind'] == 'financial':
            require(s.get('origin') in p['source_priority']['financial'], 'PRIMARY_FINANCIAL_SOURCE_REQUIRED')
        elif s['kind'] == 'market':
            require(s.get('provider') == snapshot['market_provider'], 'MARKET_PROVIDER_CHANGED')
        else:
            require(s.get('provider') == snapshot['universe_provider'], 'UNIVERSE_PROVIDER_CHANGED')
        sources[sid] = s
    excluded, missing, representatives, groups = [], [], [], {}
    for row in sorted(rows, key=lambda r: r['symbol']):
        require(nonempty(row.get('issuer_id')), 'ISSUER_MAPPING_REQUIRED:' + row['symbol'])
        groups.setdefault(row['issuer_id'], []).append(row)
    for issuer, classes in sorted(groups.items()):
        try:
            for row in classes:
                source = sources.get(row.get('identity_source_id'), {})
                require(source.get('kind') == 'identity' and timestamp(source['published_at']) <= cutoff, 'IDENTITY_EVIDENCE')
                require(row.get('membership_as_of') == cutoff.date().isoformat(), 'MEMBERSHIP_DATE')
                require(row.get('identity_conflicts') == [], 'IDENTITY_CONFLICT')
                require(row.get('data_status') == 'complete', 'EXPLICIT_DATA_GAP')
                adv = fact_value(row, 'adv20', sources, cutoff, 'market')
                require(adv > 0 and row['facts']['adv20'].get('period_end') == cutoff.date().isoformat(), 'ADV20_DATE_OR_VALUE')
            chosen = sorted(classes, key=lambda r: (-number(r['facts']['adv20']['value']), r['symbol']))[0]
            representatives.append(chosen)
            excluded.extend({'symbol': r['symbol'], 'reason': 'DUPLICATE_ISSUER', 'representative': chosen['symbol']}
                            for r in classes if r is not chosen)
        except (ValueError, KeyError, TypeError) as exc:
            missing.extend({'symbol': r['symbol'], 'reason': 'ISSUER_SELECTION:' + str(exc)} for r in classes)
    raw = []
    dates = [s['date'] for s in grid]
    for row in representatives:
        try:
            a, v, q = raw_metrics(row, sources, cutoff)
            history = row['total_return_history']
            source = sources.get(history.get('source_id'), {})
            require(source.get('kind') == 'market' and timestamp(source['published_at']) <= cutoff, 'PRICE_SOURCE')
            require(history.get('corporate_actions_reviewed') is True and history.get('unresolved_actions') == []
                    and nonempty(history.get('audit_evidence')), 'PRICE_ACTION_AUDIT')
            require(history.get('dates') == dates, 'PRICE_SESSION_GRID')
            values = [number(x) for x in history['values']]
            require(len(values) == 253 and all(x > 0 for x in values), 'PRICE_VALUES')
            raw.append({'symbol': row['symbol'], 'issuer_id': row['issuer_id'], 'adapter': a,
                        'sector': row['sector_code'], 'industry': row['industry_code'],
                        'value_raw': v, 'quality_raw': q, 'momentum_raw': values[-22] / values[0] - 1})
        except (ValueError, KeyError, TypeError) as exc:
            missing.append({'symbol': row['symbol'], 'reason': str(exc)})
    scored = []
    for row in raw:
        peers, level = [], None
        for key, label in (('industry', 'industry'), ('sector', 'sector'), (None, 'adapter')):
            peers = [r for r in raw if r['adapter'] == row['adapter'] and (key is None or r[key] == row[key])]
            if len(peers) >= p['peer_minimum']:
                level = label
                break
        if level is None:
            missing.append({'symbol': row['symbol'], 'reason': 'INSUFFICIENT_ADAPTER_PEERS'})
            continue
        v = sum(midrank(x, [r['value_raw'][i] for r in peers]) for i, x in enumerate(row['value_raw'])) / 2
        q = sum(midrank(x, [r['quality_raw'][i] for r in peers]) for i, x in enumerate(row['quality_raw'])) / 3
        m = midrank(row['momentum_raw'], [r['momentum_raw'] for r in raw])
        scored.append({**row, 'value': v, 'quality': q, 'momentum': m, 'score': (v + q + m) / 3,
                       'peer_level': level, 'peer_symbols': sorted(r['symbol'] for r in peers)})
    scored.sort(key=lambda r: (-r['score'], r['symbol']))
    def serial(value):
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, dict):
            return {k: serial(v) for k, v in value.items()}
        if isinstance(value, list):
            return [serial(v) for v in value]
        return value
    return serial({'status': 'COMPUTED' if not missing else 'INCOMPLETE',
                   'profile_sha256': digest(p), 'snapshot_sha256': digest(snapshot),
                   'information_cutoff': cutoff.isoformat(), 'scores': scored,
                   'discovery_order': [r['symbol'] for r in scored], 'missing': sorted(missing, key=lambda r: r['symbol']),
                   'excluded': sorted(excluded, key=lambda r: r['symbol']), 'expected_return': None,
                   'strong_buy_available': False, 'execution_authorized': False,
                   'limitations': 'Research baseline; source/accounting declarations are not authenticated and no performance calibration is supplied'})


def prepare_document(document):
    """Derive the only permitted numeric ranking from an embedded shared snapshot."""
    doc = copy.deepcopy(document)
    contract = doc.get('shared_strategy')
    if contract is None:
        require(doc.get('ranking_spec', {}).get('profile_id') != 'vqm-fundamental', 'VQM_REQUIRES_SHARED_SNAPSHOT')
        return doc, None
    require(contract.get('profile_id') == 'vqm-fundamental' and contract.get('profile_version') == '1.0.0', 'UNSUPPORTED_SHARED_PROFILE')
    require(doc.get('decision_mode') in {'long_term', 'fixed_horizon'}, 'VQM_REQUIRES_FUNDAMENTAL_MODE')
    if doc.get('horizon'):
        require(doc['horizon'].get('strategy_route') == 'long_term', 'VQM_NOT_A_SWING_OR_INTRADAY_SIGNAL')
    count = contract.get('selection_count')
    require(count is None or (type(count) is int and count > 0), 'INVALID_SELECTION_COUNT')
    snapshot = doc['vqm_snapshot']
    # Legacy arithmetic remains available for retained fixtures and diagnostics.
    # New real research must use the executable data pipeline, not model-entered
    # numbers carrying the same factor-profile name.
    require(snapshot.get('schema_version') == 2 or snapshot.get('fictional') is True,
            'SHARED_FINANCIAL_NORMALIZATION_REQUIRED')
    if snapshot.get('fictional') is True:
        require(doc.get('fictional') is True, 'FICTIONAL_SNAPSHOT_REQUIRES_FICTIONAL_REPORT')
    require(set(doc['universe']['symbols']) == set(snapshot['universe_symbols']), 'UNIVERSE_MISMATCH')
    cutoff = timestamp(snapshot['information_cutoff'])
    require(timestamp(doc.get('research_as_of') or doc.get('horizon', {}).get('as_of')) == cutoff, 'RESEARCH_CUTOFF_MISMATCH')
    result = calculate(snapshot)
    definitions = {'vqm_score': {'unit': 'dimensionless', 'period': 'TTM and 252/21 sessions',
        'basis': 'vqm-fundamental 1.0.0', 'normalization': 'fixed adapter midranks; equal family means',
        'source_priority': ['embedded vqm_snapshot with primary financial facts']}}
    spec = {'schema_version': 1, 'profile_id': contract['profile_id'], 'profile_version': contract['profile_version'],
        'snapshot_id': snapshot['snapshot_id'], 'as_of': snapshot['information_cutoff'], 'max_age_seconds': 1,
        'selection_count': count, 'max_per_group': None, 'missing_data_policy': 'exclude',
        'tie_break': 'symbol_ascending', 'allowed_statuses': ['Eligible'], 'minimum_score': '0',
        'criteria': [{'metric': 'vqm_score', 'direction': 'higher', 'low': '-1', 'high': '1', 'weight': '1'}],
        'filters': [], 'field_definitions': definitions}
    by_symbol = {r['symbol']: r for r in result['scores']}
    if snapshot.get('schema_version') == 2:
        from financial_normalize import materialize
        financial_rows, _ = materialize(snapshot)
    else:
        financial_rows = snapshot
    facts_by_symbol = {r['symbol']: r for r in financial_rows['rows']}
    for candidate in doc.get('candidates', []):
        primary = candidate.get('primary_review') or {}
        row = facts_by_symbol.get(candidate['symbol'])
        require(row is not None, 'CANDIDATE_OUTSIDE_SHARED_SNAPSHOT')
        for field in ('latest_public_period_end', 'reviewed_period_end'):
            require(not primary.get(field) or primary[field] == row.get('financial_period_end'),
                    'PRIMARY_FACTOR_PERIOD_MISMATCH:' + candidate['symbol'])
        scenario = candidate.get('horizon_review', {}).get('terminal_scenarios')
        if scenario:
            require(scenario.get('scenario_basis') == 'issuer_specific_valuation', 'COMMON_STRESS_IS_NOT_ISSUER_VALUATION')
            dist = scenario.get('distributions_review', {})
            require(dist.get('status') == 'reviewed' and isinstance(dist.get('evidence'), list)
                    and dist['evidence'] and all(nonempty(x) for x in dist['evidence'])
                    and nonempty(dist.get('assumption')), 'DISTRIBUTIONS_REVIEW_REQUIRED')
            require(number(scenario['entry_price']) == number(row['facts']['close_price']['value']), 'SCENARIO_PRICE_NOT_SHARED_CLOSE')
            cash = scenario.get('cash_benchmark', {})
            age = cash.get('max_age_seconds')
            require(type(age) is int and 0 < age <= profile()['cash_benchmark_max_age_seconds'], 'CASH_BENCHMARK_FRESHNESS_OVERRIDE')
    inputs = [{'symbol': symbol, 'observed_at': snapshot['information_cutoff'],
               'group': by_symbol.get(symbol, {}).get('sector'),
               'metrics': {'vqm_score': by_symbol.get(symbol, {}).get('score')},
               'evidence': ['vqm_snapshot sha256:' + result['snapshot_sha256']]}
              for symbol in sorted(snapshot['universe_symbols'])]
    for key, derived in (('ranking_spec', spec), ('ranking_inputs', inputs)):
        require(key not in doc or doc[key] == derived, 'SHARED_STRATEGY_OVERRIDE:' + key)
        doc[key] = derived
    require(doc.get('report', {}).get('recommendation_label', 'research_comparison') == 'research_comparison',
            'STRONG_BUY_UNAVAILABLE_UNCALIBRATED_PROFILE')
    result['mandate_sha256'] = digest({'horizon': doc.get('horizon'), 'contract': contract,
                                      'benchmark': snapshot['benchmark_id'], 'universe': snapshot['universe_id']})
    result['evidence_decisions_sha256'] = digest(doc.get('candidates', []))
    result['implementation_sha256'] = digest({p.name: p.read_text(encoding='utf-8')
                                             for p in sorted((ROOT / 'scripts').glob('*.py'))})
    result['reproducibility_key'] = digest({k: result[k] for k in ('profile_sha256', 'snapshot_sha256', 'mandate_sha256', 'evidence_decisions_sha256', 'implementation_sha256')})
    result['recommendation_confidence'] = 'UNCALIBRATED_RESEARCH_ONLY'
    return doc, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    result = calculate(json.loads(args.snapshot.read_text(encoding='utf-8-sig')))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result['status'] != 'COMPUTED':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
