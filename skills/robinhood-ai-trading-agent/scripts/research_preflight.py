"""Report installed research capabilities without requiring a broker account."""
import importlib
import importlib.metadata
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_FILES = {
    'alignment_hardening': ['scripts/research_workflow.py', 'scripts/answer_facts.py',
                            'scripts/concentration_bounds.py', 'scripts/evidence_provenance.py',
                            'references/model-alignment-hardening.md'],
    'research_alignment': ['scripts/' + name + '.py' for name in
        ('research_workflow', 'evidence_semantics', 'price_comparison', 'recommendation_report', 'ranking_alignment', 'research_contracts', 'planning_alignment', 'allocation_policy', 'financial_alignment', 'strategy_research',
         'forward_evidence', 'analysis_checks', 'quant_report', 'report_facts', 'portfolio_analytics',
         'accounting_tools', 'research_analytics', 'strategy_lab', 'risk_engine')] +
        ['profiles/report-facts-v2.json', 'references/research-alignment.md', 'references/source-bound-workflow.md',
         'references/evidence-semantics.md', 'references/ranking-alignment.md'],
    'offline_run_and_report': ['scripts/quant_report.py', 'scripts/analyst_report.py',
                              'scripts/handoff_report.py', 'scripts/report_facts.py',
                              'references/run-and-report.md'],
    'news_and_analyst_research': ['scripts/news_sources.py', 'scripts/news_analysis.py', 'scripts/analyst_evidence.py',
                                'profiles/news-sources-v1.json', 'references/news-and-guidance.md', 'references/analyst-research.md'],
    'research_handoff': ['scripts/research_handoff.py', 'scripts/research_source_overlay.py', 'references/research-handoff.md', 'PACKAGE-MANIFEST.json'],
    'quant_workbench': ['scripts/' + name + '.py' for name in
        ('quant_workbench', 'quant_common', 'quant_validation', 'quant_portfolio',
         'multi_asset_risk', 'investment_ops', 'primary_financial_data',
         'portfolio_backtest', 'manager_monitor', 'price_audit', 'deterministic_rank',
         'financial_normalize', 'filing_extract', 'analysis_checks', 'planning_alignment', 'allocation_policy',
         'financial_alignment', 'strategy_research', 'forward_evidence', 'portfolio_analytics',
         'accounting_tools', 'research_analytics', 'strategy_lab', 'risk_engine', 'report_facts', 'evidence_semantics',
         'employer_reference', 'equity_cash_comparison', 'source_exposure',
         'portable_quant', 'point_in_time_data', 'costed_bar_replay')] +
         ['profiles/financial-normalization-v1.json', 'profiles/report-facts-v2.json'],
    'public_research': ['profiles/public-vqm-discovery-v1.json', 'scripts/public_research.py',
                        'scripts/public_research_fetch.py', 'scripts/listed_universe.py', 'scripts/research_report_checks.py'],
    'shared_default': ['profiles/vqm-fundamental-v1.json', 'profiles/financial-normalization-v1.json'] + ['scripts/' + name + '.py' for name in
        ('vqm_research', 'screen_review', 'research_bundle', 'horizon_review', 'trading_calendar',
         'deterministic_rank', 'price_audit', 'cash_benchmark', 'risk_engine', 'financial_normalize', 'filing_extract')],
    'volatility': ['scripts/garch_volatility.py', 'scripts/price_audit.py'],
    'allocation': ['scripts/benchmark_portfolio.py', 'scripts/deterministic_rank.py', 'scripts/price_audit.py',
                   'scripts/allocation_policy.py', 'references/allocation-policy.md'],
}


def active_package_versions(text):
    """Read active display labels, excluding fenced examples and quoted history."""
    labels = []
    fence = None
    for line in text.splitlines():
        stripped = line.strip()
        marker = re.match(r'^(`{3,}|~{3,})', stripped)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        label = re.match(r'^Package version\s*:\s*(.*)$', stripped, re.I)
        if label:
            value = label.group(1).strip().lstrip('*` ')
            version = re.match(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?(?=$|[\s*`])', value)
            labels.append(version.group(0) if version else None)
    return labels


def package_integrity():
    try:
        manifest = json.loads((ROOT / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
        errors = []
        version = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
        if manifest['version'] != version:
            errors.append('VERSION_MISMATCH')
        labels = active_package_versions((ROOT / 'SKILL.md').read_text(encoding='utf-8-sig'))
        if not labels:
            errors.append('SKILL_PACKAGE_VERSION_MISSING')
        if len(labels) > 1:
            errors.append('SKILL_PACKAGE_VERSION_MULTIPLE')
        if None in labels:
            errors.append('SKILL_PACKAGE_VERSION_INVALID')
        if any(label is not None and label != version for label in labels):
            errors.append('SKILL_PACKAGE_VERSION_MISMATCH')
        for name, expected in manifest['files'].items():
            path = (ROOT / name).resolve()
            if ROOT.resolve() not in path.parents or not path.is_file():
                errors.append('MISSING_OR_UNSAFE:' + name)
            elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                errors.append('HASH_MISMATCH:' + name)
        return {'status': 'VERIFIED' if not errors else 'INVALID', 'errors': errors,
                'manifest_sha256': hashlib.sha256((ROOT / 'PACKAGE-MANIFEST.json').read_bytes()).hexdigest()}
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'INVALID', 'errors': ['PACKAGE_MANIFEST_UNAVAILABLE_OR_INVALID']}


def check():
    dependencies = {}
    for name in ('exchange_calendars', 'numpy', 'pandas', 'tzdata', 'scipy', 'arch', 'yfinance', 'requests', 'lxml', 'statsmodels', 'QuantLib', 'vaderSentiment'):
        try:
            importlib.import_module(name)
            dependencies[name] = {'status': 'IMPORTABLE', 'version': importlib.metadata.version(name)}
        except Exception as exc:
            dependencies[name] = {'status': 'UNAVAILABLE', 'reason': type(exc).__name__}
    missing_by_capability = {key: [p for p in paths if not (ROOT / p).is_file()]
                             for key, paths in CAPABILITY_FILES.items()}
    missing = sorted({p for paths in missing_by_capability.values() for p in paths})
    available = lambda names: all(dependencies[n]['status'] == 'IMPORTABLE' for n in names)
    integrity = package_integrity()
    return {'skill_version': (ROOT / 'VERSION').read_text(encoding='utf-8').strip(),
            'package_integrity': integrity,
            'alignment_hardening': 'AVAILABLE_REQUIRES_SUPPLIED_REQUEST' if integrity['status'] == 'VERIFIED' and not missing_by_capability['alignment_hardening'] and available(['numpy', 'scipy', 'lxml', 'tzdata']) else 'UNAVAILABLE',
            'research_handoff': 'AVAILABLE' if integrity['status'] == 'VERIFIED' and not missing_by_capability['research_handoff'] else 'UNAVAILABLE',
            'missing_files': missing, 'missing_by_capability': missing_by_capability, 'dependencies': dependencies,
            'public_research': 'AVAILABLE' if not missing_by_capability['public_research'] and available(['yfinance', 'requests', 'lxml', 'pandas', 'exchange_calendars']) else 'UNAVAILABLE',
            'shared_default': 'AVAILABLE' if not missing_by_capability['shared_default'] and available(['exchange_calendars', 'numpy', 'pandas', 'tzdata']) else 'UNAVAILABLE',
            'volatility': 'AVAILABLE' if not missing_by_capability['volatility'] and available(['arch', 'numpy', 'pandas', 'scipy']) else 'SKIPPED_MISSING_COMPONENTS',
            'allocation': 'AVAILABLE_REQUIRES_CALIBRATION' if not missing_by_capability['allocation'] and available(['numpy', 'scipy']) else 'UNAVAILABLE',
            'portable_optional_calculations': {
                'arima_and_cointegration': 'IMPORTABLE_NOT_QUALIFIED' if available(['statsmodels']) else 'UNAVAILABLE',
                'quantlib_european': 'IMPORTABLE_NOT_QUALIFIED' if available(['QuantLib']) else 'UNAVAILABLE',
                'vader': 'IMPORTABLE_NOT_QUALIFIED' if available(['vaderSentiment']) else 'UNAVAILABLE'},
            'execution_authorized': False,
            'news_and_analyst_research': 'AVAILABLE_RESEARCH_ONLY_ACCESS_NOT_VERIFIED' if integrity['status'] == 'VERIFIED' and not missing_by_capability['news_and_analyst_research'] and available(['requests', 'tzdata']) else 'UNAVAILABLE',
            'quant_workbench': 'AVAILABLE_RESEARCH_ONLY' if not missing_by_capability['quant_workbench'] and available(['numpy', 'scipy', 'lxml', 'tzdata']) else 'UNAVAILABLE',
            'research_alignment': 'AVAILABLE_ADVISORY_ONLY' if integrity['status'] == 'VERIFIED' and not missing_by_capability['research_alignment'] and available(['numpy', 'scipy', 'lxml', 'tzdata']) else 'UNAVAILABLE',
            'limitations': 'Import checks are not execution evidence, market-data entitlement, performance validation or broker readiness'}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
