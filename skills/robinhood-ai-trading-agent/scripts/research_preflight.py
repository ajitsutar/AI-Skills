"""Report installed research capabilities without requiring a broker account."""
import importlib
import importlib.metadata
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_FILES = {
    'public_research': ['profiles/public-vqm-discovery-v1.json', 'scripts/public_research.py',
                        'scripts/public_research_fetch.py', 'scripts/research_report_checks.py'],
    'shared_default': ['profiles/vqm-fundamental-v1.json', 'profiles/financial-normalization-v1.json'] + ['scripts/' + name + '.py' for name in
        ('vqm_research', 'screen_review', 'research_bundle', 'horizon_review', 'trading_calendar',
         'deterministic_rank', 'price_audit', 'cash_benchmark', 'risk_engine', 'financial_normalize', 'filing_extract')],
    'volatility': ['scripts/garch_volatility.py', 'scripts/price_audit.py'],
    'allocation': ['scripts/benchmark_portfolio.py', 'scripts/deterministic_rank.py', 'scripts/price_audit.py'],
}


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
    return {'skill_version': (ROOT / 'VERSION').read_text(encoding='utf-8').strip(),
            'missing_files': missing, 'missing_by_capability': missing_by_capability, 'dependencies': dependencies,
            'public_research': 'AVAILABLE' if not missing_by_capability['public_research'] and available(['yfinance', 'requests', 'lxml', 'pandas', 'exchange_calendars']) else 'UNAVAILABLE',
            'shared_default': 'AVAILABLE' if not missing_by_capability['shared_default'] and available(['exchange_calendars', 'numpy', 'pandas', 'tzdata']) else 'UNAVAILABLE',
            'volatility': 'AVAILABLE' if not missing_by_capability['volatility'] and available(['arch', 'numpy', 'pandas', 'scipy']) else 'SKIPPED_MISSING_COMPONENTS',
            'allocation': 'AVAILABLE_REQUIRES_CALIBRATION' if not missing_by_capability['allocation'] and available(['numpy', 'scipy']) else 'UNAVAILABLE',
            'execution_authorized': False,
            'limitations': 'Import checks are not execution evidence, market-data entitlement, performance validation or broker readiness'}


if __name__ == '__main__':
    print(json.dumps(check(), indent=2))
