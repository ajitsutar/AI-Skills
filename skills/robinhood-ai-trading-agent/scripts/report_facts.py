"""Local deterministic projection of helper results; no calculations or narrative validation."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'report-facts-1'
STATUSES = {'COMPUTED', 'REJECTED_INPUT', 'CALCULATION_FAILED', 'RESEARCH_QUEUE_ONLY', 'SIMULATED',
            'SHORTFALL', 'PROJECTED_COVERED', 'AMBIGUOUS_OR_NONCONVENTIONAL_CASHFLOWS',
            'ROOT_OUTSIDE_NUMERICAL_BRACKET', 'NO_VERIFIED_FEASIBLE_SOLUTION',
            'RESEARCH_PROPOSAL', 'ADVISORY_RISK_ALERT', 'CHECKED_METRICS_WITHIN_LIMITS'}
OMIT_FIELDS = {'execution_authorized', 'validated_for_live', 'skill_submitted_order',
               'external_permissions_changed', 'point_in_time_evidence_verified'}
QUANT_FILES = ('quant_workbench.py', 'quant_common.py', 'quant_validation.py',
               'quant_portfolio.py', 'multi_asset_risk.py', 'investment_ops.py',
               'primary_financial_data.py', 'price_audit.py', 'financial_normalize.py',
               'filing_extract.py', 'deterministic_rank.py', 'portfolio_backtest.py',
               'manager_monitor.py')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def code_hash(name):
    return hashlib.sha256((ROOT / 'scripts' / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def quant_hash():
    sources = {name: (ROOT / 'scripts' / name).read_text(encoding='utf-8') for name in QUANT_FILES}
    sources['financial-normalization-v1.json'] = (ROOT / 'profiles/financial-normalization-v1.json').read_text(encoding='utf-8')
    return digest(sources)


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
        'lags': ('HAC lag count', 'count', None, 'input observation lags')},
    'ops.xirr': {'annual_xirr': ('Annualized XIRR', 'annual_return_fraction', 'dated investor cash flows', 'ACT/365 conventional cash-flow root')},
    'ops.attribution': {k: (name, 'return_fraction', 'consistent beginning group weights', 'single-period Brinson-Fachler') for k, name in [
        ('active_return', 'Portfolio minus benchmark return'), ('allocation', 'Allocation effect'),
        ('selection', 'Selection effect'), ('interaction', 'Interaction effect'), ('reconciliation_error', 'Attribution reconciliation residual')]},
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
        known = result.get('implementation_sha256') == quant_hash()
        inputs = doc.get('input') if wrapped else None
        if isinstance(inputs, dict) and (not isinstance(inputs.get('jobs'), list) or
                any(not isinstance(x, dict) for x in inputs['jobs']) or
                not isinstance(inputs.get('contract'), dict)):
            raise ValueError('INVALID_EMBEDDED_INPUT_SCHEMA')
        bound = isinstance(inputs, dict) and digest(inputs) == result.get('input_sha256')
        result_bound = wrapped and doc.get('result_sha256') == digest(result)
        self.notices.append({'code_mapping_matches': known, 'embedded_input_hash_matches': bound,
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
    parser.add_argument('--include-source-text', action='store_true', help='Explicitly export selected source strings, including status/reason/security labels. Review privately before sharing.')
    args = parser.parse_args()
    try:
        source, output = local_path(args.input), local_path(args.private_output)
        if output.is_relative_to(ROOT):
            raise ValueError('OUTPUT_OUTSIDE_SKILL_REQUIRED')
        report = project(source.read_bytes(), args.kind,
                         local_path(args.custom_bindings).read_bytes() if args.custom_bindings else None,
                         args.include_source_text)
        rendered = markdown(report) if args.format == 'markdown' else json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n'
        with output.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(rendered)
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        # Avoid dumping source values or private paths on a terminal error.
        parser.exit(2, 'Report export failed: invalid input/schema/path, unavailable file, or existing output. Source values were not printed.\n')


if __name__ == '__main__':
    main()
