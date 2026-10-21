"""Local deterministic projection and projection verification; no helper replay."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
from functools import lru_cache
from collections import defaultdict, deque

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'report-facts-1'
STATUSES = {'COMPUTED', 'REJECTED_INPUT', 'CALCULATION_FAILED', 'RESEARCH_QUEUE_ONLY', 'SIMULATED',
            'SHORTFALL', 'PROJECTED_COVERED', 'AMBIGUOUS_OR_NONCONVENTIONAL_CASHFLOWS',
            'ROOT_OUTSIDE_NUMERICAL_BRACKET', 'NO_VERIFIED_FEASIBLE_SOLUTION',
            'RESEARCH_PROPOSAL', 'ADVISORY_RISK_ALERT', 'CHECKED_METRICS_WITHIN_LIMITS',
            'INCOMPARABLE', 'UNKNOWN_COMPARABILITY', 'CHECKED', 'PARTIAL', 'PARTIAL_ANALYSIS', 'ASSESSED',
            'NOT_ADMISSIBLE', 'ADMISSIBLE_DECLARATION', 'NOT_ESTABLISHED', 'SOURCE_BYTES_BOUND',
            'RECONCILED', 'UNRESOLVED_DIFFERENCE', 'UNEXPLAINED_EQUITY_DIFFERENCE',
            'UNFUNDED_SHORTFALL', 'FILLED', 'ALREADY_LONG', 'ALREADY_CASH',
            'MISSED_ENTRY_SCENARIO', 'UNFILLED_NO_VOLUME', 'UNFILLED_BEYOND_DATA',
            'INPUTS_UNRESOLVED', 'EXPLICIT_COST_MODEL', 'PARTIAL_CONTEXT', 'COMPUTED_CONTEXT',
            'NOT_SUPPLIED', 'UNRESOLVED', 'ALREADY_INCLUDED_NO_EXTRA_CHARGE',
            'EXPLICIT_ONE_WAY_MODEL', 'NO_KNOWN_FUND_NOTIONAL', 'COMPLETE_SUPPLIED_WEIGHTS',
            'INTERPRETED', 'COMPARED', 'NO_SHOCKS_SUPPLIED', 'NOT_APPLICABLE', 'UNKNOWN_MODEL',
            'COMPUTED_SCENARIO', 'COMPUTED_SCENARIOS', 'COMPUTED_CONDITIONAL_PROJECTION',
            'DATE_PATHS_MODELED', 'EXCLUDED_BY_EXPLICIT_ASSUMPTION', 'UNRESOLVED_CALENDAR_COVERAGE',
            'POSSIBLE_INTRADAY_ACCEPTANCE_UNKNOWN', 'CONDITIONAL_DATE_PATH',
            'BEFORE_DEADLINE_DATE', 'ON_DEADLINE_DATE_INTRADAY_UNRESOLVED', 'AFTER_DEADLINE_DATE',
            'INDETERMINATE', 'LEFT_DOMINATES', 'RIGHT_DOMINATES', 'EQUIVALENT_ON_DECLARED_CRITERIA', 'TRADEOFF',
            'MAPPING_REQUIRED', 'DRAFT_UNVERIFIED', 'PRIMARY_EVIDENCE_REQUIRED', 'READY', 'INCOMPLETE', 'NOT_ASSESSED',
            'NO_INCLUDED_FUTURE_VEST_DATE', 'DATED_ALTERNATIVES_COMPARED',
            'SOURCE_BOUND_SCENARIO_AT_REQUESTED_EXIT', 'SOURCE_BOUND_CONDITIONAL_COMPARISON',
            'PRIMARY_APPLICABILITY_UNRESOLVED', 'CONDITIONAL_WEIGHTED_ARITHMETIC',
            'COMPLETE_WITHIN_SUPPLIED_ROWS', 'KNOWN_LOWER_BOUND_ONLY'}
# The original workbench numerical modules and existing schemas were inspected
# byte-for-text-identical before the additive operation extension. This identifies
# a known historical schema, not a successful replay with the current code.
COMPATIBLE_QUANT_SCHEMAS = frozenset({
    '6294350238ac62bbb0c452a1d5a3e1179c69662139cfdeb62b59c4fe77aacc7c'})
OMIT_FIELDS = {'execution_authorized', 'validated_for_live', 'skill_submitted_order',
               'external_permissions_changed', 'point_in_time_evidence_verified'}
QUANT_FILES = ('quant_workbench.py', 'quant_common.py', 'quant_validation.py',
               'quant_portfolio.py', 'multi_asset_risk.py', 'investment_ops.py',
               'primary_financial_data.py', 'price_audit.py', 'financial_normalize.py',
               'filing_extract.py', 'deterministic_rank.py', 'portfolio_backtest.py',
               'manager_monitor.py', 'analysis_checks.py', 'planning_alignment.py', 'financial_alignment.py',
               'portfolio_analytics.py', 'accounting_tools.py', 'strategy_research.py',
               'strategy_lab.py', 'risk_engine.py', 'forward_evidence.py', 'report_facts.py',
               'research_analytics.py', 'evidence_semantics.py', 'ranking_alignment.py',
               'vqm_research.py', 'public_research.py', 'research_bundle.py', 'screen_review.py',
               'horizon_review.py', 'cash_benchmark.py', 'trading_calendar.py', 'allocation_policy.py',
               'portfolio_decision.py', 'planning_roles.py', 'portfolio_projection.py', 'planning_comparison.py',
               'flow_normalization.py', 'price_comparison.py', 'recommendation_report.py', 'employer_reference.py',
               'equity_cash_comparison.py', 'source_exposure.py')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def code_hash(name):
    return hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def quant_hash():
    sources = {name: (ROOT / 'scripts' / name).read_text(encoding='utf-8') for name in QUANT_FILES}
    sources['financial-normalization-v1.json'] = (ROOT / 'profiles/financial-normalization-v1.json').read_text(encoding='utf-8')
    sources['report-facts-v2.json'] = (ROOT / 'profiles/report-facts-v2.json').read_text(encoding='utf-8')
    for name in ('vqm-fundamental-v1.json', 'public-vqm-discovery-v1.json'):
        sources[name] = (ROOT / 'profiles' / name).read_text(encoding='utf-8')
    return digest(sources)


@lru_cache(maxsize=1)
def extended_semantics():
    """Installed, versioned schema only; source files cannot supply this mapping."""
    profile = json.loads((ROOT / 'profiles/report-facts-v2.json').read_text(encoding='utf-8'))
    if profile.get('schema_version') != 1 or not isinstance(profile.get('operations'), dict):
        raise ValueError('EXTENDED_FACTS_SCHEMA')
    return profile['operations']


def extended_spec(operation, relative_path):
    parts = relative_path.split('/')
    for pattern, item in extended_semantics().get(operation, {}).items():
        keys = pattern.split('/')
        if len(keys) == len(parts) and all(a == '*' or a == b for a, b in zip(keys, parts)):
            return tuple(item.get(k) for k in ('metric', 'unit', 'denominator', 'basis'))
    return None


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def bad_number(value):
        raise ValueError('NONFINITE_JSON_NUMBER')
    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('NONFINITE_JSON_NUMBER')
        return number
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=bad_number, parse_float=finite_float)


def pointer(document, path):
    """RFC6901 only. A pointer selects data; it never executes an expression."""
    if path == '':
        return document
    if not isinstance(path, str) or not path.startswith('/'):
        raise ValueError('JSON_POINTER_REQUIRED')
    value = document
    for token in path[1:].split('/'):
        if re.search(r'~(?![01])', token):
            raise ValueError('INVALID_POINTER_ESCAPE')
        key = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', key):
                raise KeyError(path)
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise KeyError(path)
    return value


def escape(key):
    return str(key).replace('~', '~0').replace('/', '~1')


def numeric(value):
    return type(value) in (int, float) and (type(value) is int or math.isfinite(value))


def leaves(value, path):
    if isinstance(value, dict):
        for key in sorted(value):
            yield from leaves(value[key], path + '/' + escape(key))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from leaves(item, path + '/' + str(i))
    elif numeric(value) or value is None or type(value) in (bool, str):
        yield path, value


# Labels describe code formulas, not verified source observations. No scaling is performed.
TAIL = {
    'total_return': ('Compounded input-series return', 'return_fraction', 'initial synthetic wealth', 'product(1 + supplied return) - 1'),
    'max_drawdown': ('Input-series maximum drawdown', 'loss_fraction', 'running peak synthetic wealth', 'compounded supplied returns; account/trade capital base unknown'),
    'loss_var': ('Input-period loss VaR', 'return_fraction', None, 'empirical negative supplied return; negative loss denotes gain'),
    'loss_expected_shortfall': ('Input-period loss expected shortfall', 'return_fraction', None, 'fractional empirical worst tail; negative loss denotes gain'),
    'observations': ('Input return count', 'count', None, 'supplied return series'),
    'confidence': ('Tail confidence', 'fraction', None, 'declared empirical tail confidence'),
    'effective_tail_observations': ('Effective empirical tail observations', 'count', None, '(1-confidence) * observations')}
SIMPLE = {
    'validation.hac': {
        'mean': ('Mean input-period return', 'return_fraction', None, 'arithmetic mean of supplied returns'),
        'standard_error_hac': ('HAC standard error of mean', 'return_fraction', None, 'Bartlett/Newey-West; supplied lag count'),
        'two_sided_p': ('Two-sided HAC p-value', 'probability', None, 'normal asymptotic test'),
        'z': ('HAC mean test statistic', 'dimensionless_statistic', 'HAC standard error of mean', 'mean supplied return / HAC standard error'),
        'ci95/0': ('HAC mean 95% interval lower endpoint', 'return_fraction', None, 'mean - normal 97.5% quantile * HAC standard error; not a future-return bound'),
        'ci95/1': ('HAC mean 95% interval upper endpoint', 'return_fraction', None, 'mean + normal 97.5% quantile * HAC standard error; not a future-return bound'),
        'lags': ('HAC lag count', 'count', None, 'input observation lags')},
    'validation.bootstrap': {
        'mean': ('Mean input-period return', 'return_fraction', None, 'arithmetic mean of supplied returns'),
        'mean_percentile_ci95/0': ('Block-bootstrap mean 95% interval lower endpoint', 'return_fraction', None, '2.5% quantile of seeded circular moving-block sample means; approximate stationarity, not future profit probability'),
        'mean_percentile_ci95/1': ('Block-bootstrap mean 95% interval upper endpoint', 'return_fraction', None, '97.5% quantile of seeded circular moving-block sample means; approximate stationarity, not future profit probability'),
        'block_length': ('Bootstrap block length', 'count', None, 'input observations per circular moving block'),
        'replications': ('Bootstrap replications', 'count', None, 'number of resampled series'),
        'seed': ('Bootstrap random seed', 'integer_seed', None, 'NumPy default_rng seed; recorded runtime and algorithm')},
    'ops.xirr': {'annual_xirr': ('Annualized XIRR', 'annual_return_fraction', 'dated investor cash flows', 'ACT/365 conventional cash-flow root')},
    'ops.attribution': {**{k: (name, 'return_fraction', 'consistent beginning group weights', 'single-period arithmetic Brinson-Fachler; component names do not establish causal effects or benchmark appropriateness') for k, name in [
        ('active_return', 'Portfolio minus benchmark return'), ('allocation', 'Allocation effect'),
        ('selection', 'Selection component'), ('interaction', 'Interaction component'), ('reconciliation_error', 'Attribution reconciliation residual')]},
        'benchmark_appropriateness': ('Benchmark appropriateness', 'status', None, 'not assessed by arithmetic decomposition'),
        'causal_attribution_assessed': ('Causal attribution assessed', 'boolean', None, 'no causal identification from aggregate returns'),
        'aggregation_basis_assessed': ('Aggregation basis assessed', 'boolean', None, 'group inputs do not verify common currency, period or non-overlap'),
        'observed_combined_performance': ('Observed combined performance', 'return_fraction', None, 'unknown without separately bound aggregation evidence'),
        'calculation_role': ('Attribution calculation role', 'status', None, 'conditional weighted arithmetic; not observed combined performance')},
    'ops.shortfall': {k: (name, unit, denominator, 'decision/arrival/terminal price accounting; positive cost on either side') for k, name, unit, denominator in [
        ('total_shortfall', 'Total implementation shortfall', 'input_currency_amount', None),
        ('fees', 'Explicit fees', 'input_currency_amount', None),
        ('delay_cost', 'Delay cost', 'input_currency_amount', None),
        ('execution_cost_vs_arrival', 'Execution cost versus arrival', 'input_currency_amount', None),
        ('opportunity_cost', 'Unfilled opportunity cost', 'input_currency_amount', None),
        ('shortfall_bps_of_intended_notional', 'Shortfall per intended notional', 'basis_points', 'intended quantity * decision price')]}}
CORPORATE = {
    'value_raw/0': ('Operating-income yield on EV proxy', 'enterprise-value proxy', 'four-quarter OperatingIncome / price-bridged vendor EV'),
    'value_raw/1': ('Free-cash-flow yield on market-cap proxy', 'market-cap proxy', '(four-quarter CFO - gross capex) / price-bridged vendor market cap'),
    'quality_raw/0': ('Return on average assets', 'average current and prior-year assets', 'four-quarter NetIncome / average assets; not ROE'),
    'quality_raw/1': ('Cash earnings surplus on average assets', 'average current and prior-year assets', '(four-quarter CFO - NetIncome) / average assets; higher signed factor is better'),
    'quality_raw/2': ('Negative net debt to assets', 'current total assets', '-(TotalDebt - CashAndCashEquivalents) / TotalAssets')}
FINANCIAL = {
    'value_raw/0': ('Common-income yield on market-cap proxy', 'market-cap proxy', 'four-quarter NetIncomeCommonStockholders / price-bridged vendor market cap'),
    'value_raw/1': ('Common equity to market-cap proxy', 'market-cap proxy', 'CommonStockEquity / price-bridged vendor market cap'),
    'quality_raw/0': ('Return on average common equity', 'average current and prior-year common equity', 'four-quarter NetIncomeCommonStockholders / average common equity'),
    'quality_raw/1': ('Common equity to assets', 'current total assets', 'CommonStockEquity / TotalAssets'),
    'quality_raw/2': ('Negative debt to common equity', 'current common equity', '-TotalDebt / CommonStockEquity')}


class Projector:
    def __init__(self, raw, kind, include_source_text=False):
        self.document = strict_json(raw)
        self.hash = hashlib.sha256(raw).hexdigest()
        self.kind = kind
        self.text = include_source_text
        self.facts = []
        self.notices = []
        self.custom_hash = None

    def fact(self, path, metric, unit=None, denominator=None, basis=None, horizon=None,
             assumptions=None, mapping='UNMAPPED', metadata_sources=None, context=None):
        absent = False
        try:
            value = pointer(self.document, path)
        except (KeyError, IndexError):
            value, absent = None, True
        missing = 'absent' if absent else 'null' if value is None else None
        if isinstance(value, (list, dict)):
            raise ValueError('FACT_MUST_BE_SCALAR')
        if isinstance(value, str) and not self.text and not (unit == 'status' and value in STATUSES) and not re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?', value):
            value, missing = None, 'source_text_withheld'
        item = {'metric': metric, 'value': value, 'unit': unit, 'denominator': denominator,
                'basis': basis, 'horizon': horizon, 'assumptions': assumptions or [],
                'horizon_role': 'declared research contract; not metric measurement period or observation frequency',
                'measurement_period': None, 'observation_frequency': None,
                'missingness': missing,
                'unknown_metadata': [k for k, v in [('unit', unit), ('denominator', denominator), ('basis', basis), ('horizon', horizon)] if v is None] + ['measurement_period', 'observation_frequency'],
                'source': {'artifact_sha256': self.hash, 'pointer': path},
                'semantic_mapping': mapping, 'metadata_sources': metadata_sources or {}, 'context': context or {}}
        self.facts.append(item)
        return item

    def quant(self):
        doc = self.document
        wrapped = isinstance(doc.get('result'), dict) and 'results' in doc['result']
        result, base = (doc['result'], '/result') if wrapped else (doc, '')
        if not isinstance(result.get('results'), list):
            raise ValueError('QUANT_RESULTS_REQUIRED')
        current_code = result.get('implementation_sha256') == quant_hash()
        legacy_schema = result.get('implementation_sha256') in COMPATIBLE_QUANT_SCHEMAS
        known = current_code or legacy_schema
        inputs = doc.get('input') if wrapped else None
        if isinstance(inputs, dict) and (not isinstance(inputs.get('jobs'), list) or
                any(not isinstance(x, dict) for x in inputs['jobs']) or
                not isinstance(inputs.get('contract'), dict)):
            raise ValueError('INVALID_EMBEDDED_INPUT_SCHEMA')
        bound = isinstance(inputs, dict) and digest(inputs) == result.get('input_sha256')
        result_bound = wrapped and doc.get('result_sha256') == digest(result)
        self.notices.append({'code_mapping_matches': current_code, 'known_historical_schema': legacy_schema and not current_code,
                             'semantics_mapping_known': known, 'embedded_input_hash_matches': bound,
                             'embedded_result_hash_matches': result_bound, 'calculation_replayed': False})
        for i, job in enumerate(result.get('results', [])):
            if not isinstance(job, dict) or not isinstance(job.get('operation'), str):
                raise ValueError('QUANT_JOB_REQUIRED')
            op = job.get('operation'); root = f'{base}/results/{i}'
            linked = None
            if bound:
                matches = [(j, x) for j, x in enumerate(inputs.get('jobs', [])) if x.get('id') == job.get('id') and x.get('operation') == op]
                if len(matches) == 1:
                    linked = matches[0]
            horizon = inputs.get('contract', {}).get('horizon_id') if linked else None
            if horizon is not None and not isinstance(horizon, str):
                raise ValueError('HORIZON_MUST_BE_TEXT')
            meta = {'horizon': '/input/contract/horizon_id'} if horizon is not None else {}
            if linked:
                meta['helper_inputs'] = f'/input/jobs/{linked[0]}/inputs'
            common = {'horizon': horizon, 'metadata_sources': meta, 'context': {'job_index': i, 'operation': op if known else None},
                      'assumptions': ['Source claims a helper result; projection does not replay or authenticate it.']}
            self.fact(root + '/status', 'Helper job status', unit='status', mapping='SOURCE_STATUS', **common)
            if job.get('status') != 'COMPUTED':
                self.fact(root + '/reason', 'Reported non-computation reason', unit='text', mapping='SOURCE_STATUS', **common)
                continue
            for path, value in leaves(job.get('result', {}), root + '/result'):
                rel = path[len(root + '/result/'):]
                if any(part in OMIT_FIELDS for part in rel.split('/')):
                    continue
                spec = None
                if rel.rsplit('/', 1)[-1] in ('status', 'warning', 'limitation'):
                    field = rel.rsplit('/', 1)[-1]
                    self.fact(path, 'Helper result ' + field, unit='status' if field == 'status' else 'text', mapping='SOURCE_FIELD', **common)
                    continue
                if known:
                    spec = SIMPLE.get(op, {}).get(rel)
                    if spec is None and current_code:
                        spec = extended_spec(op, rel)
                        issuer_root = {'planning.allocation_context': 'issuer_identity_summary/',
                                       'planning.source_allocation_context': 'allocation_result/issuer_identity_summary/'}.get(op)
                        if issuer_root and rel in (issuer_root + 'distinct_known_issuer_count',
                                                   issuer_root + 'total_distinct_issuer_count'):
                            spec = ('Distinct known issuer count' if rel.endswith('distinct_known_issuer_count') else
                                    'Total distinct issuer count within supplied rows', 'count', None,
                                    'Positive terminal issuer identities; cash and repeated share classes excluded; total unknown when identity coverage is unresolved')
                    if op == 'validation.tail':
                        spec = TAIL.get(rel)
                    elif op == 'backtest.portfolio':
                        if rel.startswith('metrics/'):
                            spec = TAIL.get(rel.split('/', 1)[1])
                            if spec and rel in ('metrics/total_return', 'metrics/max_drawdown'):
                                spec = ('Modeled portfolio ' + ('total return' if rel.endswith('total_return') else 'maximum drawdown'), 'return_fraction' if rel.endswith('total_return') else 'loss_fraction', 'initial modeled portfolio equity' if rel.endswith('total_return') else 'running peak modeled portfolio equity', 'period simulator equity after declared costs; not trade-capital return')
                        elif rel in ('costs_paid', 'gross_traded_notional'):
                            spec = ('Modeled total costs' if rel == 'costs_paid' else 'Gross traded notional', 'input_currency_amount', None, 'sum of period simulator amounts')
                        elif rel in ('benchmark_total_return', 'total_return_difference'):
                            spec = ('Compounded benchmark return' if rel == 'benchmark_total_return' else 'Portfolio minus benchmark total return', 'return_fraction', 'initial modeled portfolio equity / benchmark wealth', 'same modeled periods')
                if spec:
                    self.fact(path, *spec, mapping='BUILTIN_CODE_SCHEMA', **common)
                else:
                    self.fact(path, 'Unmapped field: ' + rel, **common)

    def public_vqm(self):
        doc = self.document
        wrapped = isinstance(doc.get('result'), dict)
        result, base = (doc['result'], '/result') if wrapped else (doc, '')
        if result.get('status') == 'RESEARCH_QUEUE_ONLY' and not isinstance(result.get('scores'), list):
            raise ValueError('VQM_SCORES_REQUIRED')
        if not isinstance(result.get('mandate', {}), dict):
            raise ValueError('INVALID_VQM_SCHEMA')
        profile = json.loads((ROOT / 'profiles/public-vqm-discovery-v1.json').read_text(encoding='utf-8'))
        known = (wrapped and doc.get('scorer_sha256') == code_hash('public_research.py')
                 and result.get('profile_sha256') == digest(profile))
        result_bound = wrapped and doc.get('result_sha256') == digest(result)
        input_bound = wrapped and isinstance(doc.get('input'), dict) and doc.get('input_sha256') == digest(doc['input'])
        self.notices.append({'code_mapping_matches': known, 'embedded_result_hash_matches': result_bound,
                             'embedded_input_hash_matches': input_bound, 'calculation_replayed': False})
        horizon = result.get('mandate', {}).get('hold')
        if horizon is not None and not isinstance(horizon, str):
            raise ValueError('HORIZON_MUST_BE_TEXT')
        common = {'horizon': horizon, 'metadata_sources': {'horizon': base + '/mandate/hold'} if horizon is not None else {},
                  'assumptions': ['Vendor approximation; source observations and execution are not authenticated.', 'Tied values stay tied; array order is not evidence of strict factor superiority.']}
        self.fact(base + '/status', 'Public research result status', unit='status', mapping='SOURCE_STATUS', **common)
        if result.get('status') != 'RESEARCH_QUEUE_ONLY':
            self.fact(base + '/reason', 'Reported non-scoring reason', unit='text', mapping='SOURCE_STATUS', **common)
            self.notices.append({'public_score_projection': 'WITHHELD_UNSUPPORTED_OR_MISSING_STATUS'})
            return
        if any(not isinstance(row, dict) for row in result['scores']):
            raise ValueError('INVALID_VQM_SCHEMA')
        for key in ('universe_securities', 'unique_issuers', 'scored_issuers', 'full_universe_scored'):
            self.fact(base + '/' + key, key.replace('_', ' ').capitalize(), unit='boolean' if key == 'full_universe_scored' else 'count', mapping='SOURCE_FIELD', **common)
        for i, row in enumerate(result.get('scores', [])):
            root = f'{base}/scores/{i}'
            ctx = {'score_row_index': i}
            self.fact(root + '/symbol', 'Scored security label', unit='identifier', mapping='SOURCE_FIELD', context=ctx, **common)
            mappings = CORPORATE if row.get('adapter') == 'corporate' else FINANCIAL if row.get('adapter') in ('insurer', 'other_financial') else {}
            for field, (name, denominator, basis) in mappings.items() if known else []:
                self.fact(root + '/' + field, name, 'ratio', denominator, basis, mapping='BUILTIN_CODE_SCHEMA', context=ctx, **common)
            for field in ('value', 'quality', 'momentum', 'score', 'momentum_raw'):
                label = {'value': 'Value peer-midrank composite', 'quality': 'Quality peer-midrank composite', 'momentum': 'Universe momentum midrank', 'score': 'Equal-weight VQM score', 'momentum_raw': '252-session return skipping latest21 sessions'}.get(field)
                self.fact(root + '/' + field, label if known else 'Unmapped field: ' + field,
                          'return_fraction' if field == 'momentum_raw' and known else 'dimensionless_score' if known else None,
                          'earliest adjusted close in frozen session grid' if field == 'momentum_raw' and known else None,
                          'Adj Close[-22] / Adj Close[0] - 1' if field == 'momentum_raw' and known else 'signed midranks; no expected-return calibration' if known else None,
                          mapping='BUILTIN_CODE_SCHEMA' if known else 'UNMAPPED', context=ctx, **common)
            if not known or not mappings:
                for field in ('value_raw', 'quality_raw'):
                    for path, value in leaves(row.get(field), root + '/' + field):
                        self.fact(path, 'Unmapped VQM component', context=ctx, **common)
        # Missing/excluded records are retained as pointers, without copying arbitrary source prose by default.
        for i, _ in enumerate(result.get('exclusions', [])):
            self.fact(f'{base}/exclusions/{i}/reason', 'Excluded security reason', unit='text', mapping='SOURCE_FIELD', **common)

    def custom(self, raw):
        declarations = strict_json(raw)
        if not isinstance(declarations, dict) or set(declarations) != {'facts'}:
            raise ValueError('CUSTOM_FACTS_OBJECT_REQUIRED')
        self.custom_hash = hashlib.sha256(raw).hexdigest()
        for item in declarations['facts']:
            if not isinstance(item, dict) or set(item) - {'pointer', 'metric', 'unit', 'denominator', 'basis', 'horizon', 'assumptions'}:
                raise ValueError('CUSTOM_FIELD_NOT_ALLOWED')
            if not all(isinstance(item.get(k), str) for k in ('pointer', 'metric')):
                raise ValueError('CUSTOM_POINTER_AND_METRIC_REQUIRED')
            if any(part.replace('~1', '/').replace('~0', '~') in OMIT_FIELDS for part in item['pointer'].split('/')):
                raise ValueError('EXECUTION_METADATA_NOT_A_REPORT_FACT')
            kwargs = {k: item.get(k) for k in ('unit', 'denominator', 'basis', 'horizon')}
            if any(v is not None and not isinstance(v, str) for v in kwargs.values()):
                raise ValueError('CUSTOM_METADATA_MUST_BE_TEXT')
            assumptions = item.get('assumptions', [])
            if not isinstance(assumptions, list) or not all(isinstance(x, str) for x in assumptions):
                raise ValueError('CUSTOM_ASSUMPTIONS_MUST_BE_TEXT_LIST')
            self.fact(item['pointer'], item['metric'], **kwargs,
                      assumptions=assumptions + ['All custom labels and metadata are declared, not verified.'],
                      mapping='CUSTOM_DECLARED_UNVERIFIED',
                      metadata_sources={'declarations_sha256': hashlib.sha256(raw).hexdigest()})

    def report(self):
        return {'schema_version': 1, 'adapter_version': VERSION, 'kind': self.kind,
                'adapter_code_sha256': code_hash('report_facts.py'),
                'source_artifact_sha256': self.hash, 'source_text_exported': self.text,
                'custom_bindings_sha256': self.custom_hash,
                'semantics_code_sha256': {'quant_workbench': quant_hash(), 'public_research.py': code_hash('public_research.py')},
                'checks': self.notices, 'facts': self.facts,
                'limits': ['Projection only: no helper replay, source authentication, narrative validation or new calculation.',
                           'Content hash matches are consistency checks, not proof of execution or observation.',
                           'Unknown metadata stays null; declared horizon is not verified observation frequency.',
                           'Local export may contain private selected data; no publication or redaction guarantee.',
                           'No broker, network, scheduling or execution permission semantics.']}


def project(raw, kind, custom_raw=None, include_source_text=False):
    p = Projector(raw, kind, include_source_text)
    if not isinstance(p.document, dict):
        raise ValueError('JSON_OBJECT_REQUIRED')
    if kind == 'quant':
        p.quant()
    elif kind == 'public-vqm':
        p.public_vqm()
    else:
        raise ValueError('UNSUPPORTED_ARTIFACT_KIND')
    if custom_raw is not None:
        p.custom(custom_raw)
    return p.report()


def _changed_paths(expected, actual, path=''):
    """Structured, type-sensitive differences without copying selected values."""
    if type(expected) is not type(actual):
        return [path]
    if isinstance(expected, dict):
        differences = []
        for key in sorted(expected.keys() | actual.keys()):
            child = path + '/' + escape(key)
            if key not in expected or key not in actual:
                differences.append(child)
            else:
                differences.extend(_changed_paths(expected[key], actual[key], child))
        return differences
    if isinstance(expected, list):
        differences = []
        for index in range(max(len(expected), len(actual))):
            child = path + '/' + str(index)
            if index >= len(expected) or index >= len(actual):
                differences.append(child)
            else:
                differences.extend(_changed_paths(expected[index], actual[index], child))
        return differences
    return [] if expected == actual else [path]


def _fact_differences(expected, actual):
    """Match exact facts first, then stable identities to explain altered fields.

    Matching is diagnostic only: verification separately compares the complete
    ordered projection. A changed identity can be reported as missing + added.
    """
    remaining_expected = dict(expected)
    remaining_actual = dict(actual)

    def match(key):
        candidates = defaultdict(deque)
        for index, fact in remaining_actual.items():
            candidates[key(fact)].append(index)
        pairs = []
        for index, fact in list(remaining_expected.items()):
            choices = candidates.get(key(fact))
            if choices:
                other = choices.popleft()
                pairs.append((index, other, remaining_expected.pop(index), remaining_actual.pop(other)))
        return pairs

    exact = match(digest)
    def identity(fact, field):
        source = fact.get('source')
        value = source.get('pointer') if field == 'pointer' and isinstance(source, dict) else fact.get(field)
        return digest([value, fact.get('context'), fact.get('semantic_mapping')])
    altered = match(lambda f: identity(f, 'pointer'))
    altered.extend(match(lambda f: identity(f, 'metric')))

    def reference(index, fact):
        source = fact.get('source')
        return {'index': index, 'pointer': source.get('pointer') if isinstance(source, dict) else None,
                'fact_sha256': digest(fact)}
    return {'expected_count': len(expected), 'actual_count': len(actual),
            'exact_match_count': len(exact),
            'missing': [reference(i, f) for i, f in remaining_expected.items()],
            'added': [reference(i, f) for i, f in remaining_actual.items()],
            'altered': [{'expected': reference(i, e), 'actual': reference(j, a),
                         'changed_fields': _changed_paths(e, a)} for i, j, e, a in altered]}


def verify_projection(raw, kind, projection_raw, custom_raw=None, include_source_text=False):
    """Reproject source bytes and compare the complete canonical JSON structure.

    Source/custom errors have the same exceptions as project(). An unreadable or
    malformed candidate returns INVALID_PROJECTION. No helper is replayed and a
    successful comparison does not establish source authenticity or correctness.
    """
    expected = project(raw, kind, custom_raw, include_source_text)
    binding_fields = ('schema_version', 'adapter_version', 'kind', 'adapter_code_sha256',
                      'source_artifact_sha256', 'source_text_exported',
                      'custom_bindings_sha256', 'semantics_code_sha256')
    result = {'schema_version': 1, 'status': 'INVALID_PROJECTION', 'matches': False,
              'expected_bindings': {k: expected[k] for k in binding_fields},
              'binding_matches': None,
              'projection_artifact_sha256': hashlib.sha256(projection_raw).hexdigest(),
              'expected_projection_content_sha256': digest(expected),
              'actual_projection_content_sha256': None,
              'metadata_mismatch_paths': None, 'facts_sequence_matches': None,
              'builtin_facts': None, 'custom_facts': None,
              'source_mapping_checks': expected['checks'], 'calculation_replayed': False,
              'limits': ['Exact projection consistency only; no helper replay, source authentication or narrative validation.',
                         'Historical schema recognition is not current-code replay; unknown mappings stay unknown.',
                         'Fact pointers and hashes can be private even though selected values are not copied into these diagnostics.']}
    try:
        actual = strict_json(projection_raw)
    except (ValueError, TypeError):
        result['reason'] = 'INVALID_PROJECTION_JSON'
        return result
    if (not isinstance(actual, dict) or not isinstance(actual.get('facts'), list)
            or any(not isinstance(fact, dict) for fact in actual['facts'])):
        result['reason'] = 'PROJECTION_OBJECT_AND_FACTS_REQUIRED'
        return result
    result['actual_projection_content_sha256'] = digest(actual)
    result['binding_matches'] = {k: k in actual and not _changed_paths(expected[k], actual[k])
                                 for k in binding_fields}
    result['metadata_mismatch_paths'] = _changed_paths(
        {k: v for k, v in expected.items() if k != 'facts'},
        {k: v for k, v in actual.items() if k != 'facts'})
    result['facts_sequence_matches'] = digest(expected['facts']) == digest(actual['facts'])
    for name, custom in (('builtin_facts', False), ('custom_facts', True)):
        def selected(facts):
            return [(i, f) for i, f in enumerate(facts)
                    if (f.get('semantic_mapping') == 'CUSTOM_DECLARED_UNVERIFIED') == custom]
        result[name] = _fact_differences(selected(expected['facts']), selected(actual['facts']))
    result['matches'] = result['expected_projection_content_sha256'] == result['actual_projection_content_sha256']
    result['status'] = 'VERIFIED_PROJECTION' if result['matches'] else 'PROJECTION_MISMATCH'
    return result


def verification_markdown(diagnostics):
    # JSON is rendered literally; candidate metadata must not become active markup.
    literal = html.escape(json.dumps(diagnostics, indent=2, ensure_ascii=False, allow_nan=False))
    return 'Report projection verification: ' + diagnostics['status'] + '\n\n<pre>' + literal + '</pre>\n'


def markdown(report):
    def cell(value):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return (html.escape(text).replace('\\', '&#92;').replace('[', '&#91;').replace(']', '&#93;')
                .replace('|', '&#124;').replace('`', '&#96;').replace('\n', '<br>'))
    rows = ['Report facts (local projection; no computation or source authentication).', '',
            'Artifact SHA-256: ' + report['source_artifact_sha256'], '',
            'Adapter code SHA-256: ' + report['adapter_code_sha256'], '',
            'Mapping code fingerprints: ' + cell(report['semantics_code_sha256']), '',
            '| Metric | Value | Unit | Denominator | Basis | Horizon | Missingness / unknown metadata | Mapping | Exact source pointer |',
            '|---|---|---|---|---|---|---|---|---|']
    for f in report['facts']:
        rows.append('| ' + ' | '.join(cell(x) for x in [f['metric'], f['value'], f['unit'], f['denominator'], f['basis'], f['horizon'],
                    {'value': f['missingness'], 'metadata': f['unknown_metadata']}, f['semantic_mapping'], f['source']['pointer']]) + ' |')
    rows.extend(['', 'Metadata and assumptions (same artifact hash):'])
    for i, f in enumerate(report['facts']):
        rows.append(f'- Fact {i}: ' + cell({'context': f['context'], 'metadata_sources': f['metadata_sources'], 'assumptions': f['assumptions'],
                    'horizon_role': f['horizon_role'], 'measurement_period': f['measurement_period'], 'observation_frequency': f['observation_frequency']}))
    rows.extend(['', 'Checks: ' + cell(report['checks']), '', *report['limits']])
    return '\n'.join(rows) + '\n'


def local_path(value):
    if str(value).startswith(('\\\\', '//')) or '://' in str(value):
        raise ValueError('LOCAL_PATH_REQUIRED')
    resolved = Path(value).resolve()
    if str(resolved).startswith(('\\\\', '//')):
        raise ValueError('LOCAL_PATH_REQUIRED')
    return resolved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=('quant', 'public-vqm'))
    parser.add_argument('input')
    parser.add_argument('--private-output', required=True, help='Explicit local export path; never printed to stdout.')
    parser.add_argument('--format', choices=('json', 'markdown'), default='json')
    parser.add_argument('--custom-bindings', help='Optional local JSON pointers with declared/unverified labels.')
    parser.add_argument('--verify-projection', help='Compare a local JSON projection against this source and options; export diagnostics instead of facts.')
    parser.add_argument('--include-source-text', action='store_true', help='Explicitly export selected source strings, including status/reason/security labels. Review privately before sharing.')
    args = parser.parse_args()
    try:
        source, output = local_path(args.input), local_path(args.private_output)
        if output.is_relative_to(ROOT):
            raise ValueError('OUTPUT_OUTSIDE_SKILL_REQUIRED')
        raw = source.read_bytes()
        custom_raw = local_path(args.custom_bindings).read_bytes() if args.custom_bindings else None
        if args.verify_projection:
            report = verify_projection(raw, args.kind, local_path(args.verify_projection).read_bytes(),
                                       custom_raw, args.include_source_text)
            render_markdown = verification_markdown
        else:
            report = project(raw, args.kind, custom_raw, args.include_source_text)
            render_markdown = markdown
        rendered = render_markdown(report) if args.format == 'markdown' else json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        with output.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(rendered)
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        # Avoid dumping source values or private paths on a terminal error.
        parser.exit(2, 'Report export failed: invalid input/schema/path, unavailable file, or existing output. Source values were not printed.\n')
    if args.verify_projection and not report['matches']:
        parser.exit(1)


if __name__ == '__main__':
    main()
