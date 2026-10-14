"""Report installed research capabilities without requiring a broker account."""
import importlib
import importlib.metadata
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_FILES = {
    'research_alignment': ['scripts/' + name + '.py' for name in
        ('research_workflow', 'evidence_semantics', 'ranking_alignment', 'research_contracts', 'planning_alignment', 'allocation_policy', 'financial_alignment', 'strategy_research',
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
         'accounting_tools', 'research_analytics', 'strategy_lab', 'risk_engine', 'report_facts', 'evidence_semantics')] +
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


def package_integrity():
    try:
        manifest = json.loads((ROOT / 'PACKAGE-MANIFEST.json').read_text(encoding='utf-8'))
        errors = []
        if manifest['version'] != (ROOT / 'VERSION').read_text(encoding='utf-8').strip():
            errors.append('VERSION_MISMATCH')
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
    for name in ('exchange_calendars', 'numpy', 'pandas', 'tzdata', 'scipy', 'arch', 'yfinance', 'requests', 'lxml'):
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
            'research_handoff': 'AVAILABLE' if integrity['status'] == 'VERIFIED' and not missing_by_capability['research_handoff'] else 'UNAVAILABLE',
            'missing_files': missing, 'missing_by_capability': missing_by_capability, 'dependencies': dependencies,
            'public_research': 'AVAILABLE' if not missing_by_capability['public_research'] and available(['yfinance', 'requests', 'lxml', 'pandas', 'exchange_calendars']) else 'UNAVAILABLE',
            'shared_default': 'AVAILABLE' if not missing_by_capability['shared_default'] and available(['exchange_calendars', 'numpy', 'pandas', 'tzdata']) else 'UNAVAILABLE',
            'volatility': 'AVAILABLE' if not missing_by_capability['volatility'] and available(['arch', 'numpy', 'pandas', 'scipy']) else 'SKIPPED_MISSING_COMPONENTS',
            'allocation': 'AVAILABLE_REQUIRES_CALIBRATION' if not missing_by_capability['allocation'] and available(['numpy', 'scipy']) else 'UNAVAILABLE',
            'execution_authorized': False,
            'news_and_analyst_research': 'AVAILABLE_RESEARCH_ONLY_ACCESS_NOT_VERIFIED' if integrity['status'] == 'VERIFIED' and not missing_by_capability['news_and_analyst_research'] and available(['requests', 'tzdata']) else 'UNAVAILABLE',
            'quant_workbench': 'AVAILABLE_RESEARCH_ONLY' if not missing_by_capability['quant_workbench'] and available(['numpy', 'scipy', 'lxml', 'tzdata']) else 'UNAVAILABLE',
            'research_alignment': 'AVAILABLE_ADVISORY_ONLY' if integrity['status'] == 'VERIFIED' and not missing_by_capability['research_alignment'] and available(['numpy', 'scipy', 'lxml', 'tzdata']) else 'UNAVAILABLE',
            'limitations': 'Import checks are not execution evidence, market-data entitlement, performance validation or broker readiness'}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
