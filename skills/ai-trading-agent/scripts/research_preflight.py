"""Report installed research capabilities without requiring a broker account."""
import importlib
import importlib.metadata
import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_FILES = {
    'free_market_evidence': ['scripts/market_sources.py', 'references/market-source-catalog.json', 'references/market-sources.md'],
    'market_flow_and_positioning': ['scripts/market_flow.py', 'references/market-flow.md'],
    'institutional_event_pilot': ['scripts/institutional_research.py', 'references/institutional-research.md', 'profiles/event-research-pilot.json'],
    'execution_policy': ['scripts/execution_policy.py', 'scripts/execution_mode.py',
                         'templates/execution-policy.example.json',
                         'references/execution-modes.md'],
    'public_portfolio_following': ['scripts/portfolio_follower.py', 'scripts/portfolio_disclosures.py',
                                  'profiles/portfolio-followers-v1.json',
                                  'subskills/portfolio-following/SKILL.md',
                                  'references/portfolio-follower-calculations.md',
                                  'references/portfolio-disclosure-inputs.md'],
    'quant_research_assurance': ['scripts/' + name + '.py' for name in
        ('research_readiness', 'quant_data_contracts', 'security_master', 'price_refresh',
         'holdings_ledger', 'analyst_adapter', 'risk_diagnostics', 'experiment_registry',
         'release_acceptance', 'dependency_inventory')] +
        ['references/quant-research-assurance.md',
         'environments/windows-cp312-data-quant/requirements.lock.txt',
         'environments/windows-cp312-data-quant/sbom.cdx.json'],
    'historical_data_storage': ['scripts/research_data_store.py',
                                'references/backtest-data-storage.md'],
    'compact_evidence': ['scripts/evidence_storage.py',
                         'references/compact-evidence.md'],
    'monthly_experiments': ['scripts/monthly_experiment.py',
                            'references/monthly-portfolio-validation.md'],
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


def direct_release_member(path, verified_directories):
    directories = []
    for member in (path, *path.parents):
        if member in verified_directories:
            verified_directories.update(directories)
            return True
        info = member.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            return False
        if member != path:
            directories.append(member)
    return False


def package_integrity(root=None):
    root = Path(ROOT if root is None else root).resolve()
    try:
        manifest_path = root / 'PACKAGE-MANIFEST.json'
        verified_directories = {root}
        for required in (manifest_path, root / 'VERSION', root / 'SKILL.md'):
            if not direct_release_member(required, verified_directories):
                return {'status': 'INVALID', 'errors': ['MISSING_OR_UNSAFE:' + required.name]}
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if not isinstance(manifest['files'], dict):
            raise ValueError('Expected package member hashes')
        errors = []
        version = (root / 'VERSION').read_text(encoding='utf-8').strip()
        if manifest['version'] != version:
            errors.append('VERSION_MISMATCH')
        labels = active_package_versions((root / 'SKILL.md').read_text(encoding='utf-8-sig'))
        if not labels:
            errors.append('SKILL_PACKAGE_VERSION_MISSING')
        if len(labels) > 1:
            errors.append('SKILL_PACKAGE_VERSION_MULTIPLE')
        if None in labels:
            errors.append('SKILL_PACKAGE_VERSION_INVALID')
        if any(label is not None and label != version for label in labels):
            errors.append('SKILL_PACKAGE_VERSION_MISMATCH')
        for required in ('SKILL.md', 'VERSION'):
            if required not in manifest['files']:
                errors.append('MISSING_MANIFEST_ENTRY:' + required)
        for name, expected in manifest['files'].items():
            relative = PurePosixPath(name)
            path = root / relative
            if (not relative.parts or relative.as_posix() != name or relative.is_absolute()
                    or '..' in relative.parts or '\\' in name or ':' in name or name == manifest_path.name
                    or root not in path.parents or not path.is_file()
                    or not direct_release_member(path, verified_directories)):
                errors.append('MISSING_OR_UNSAFE:' + name)
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                errors.append('HASH_MISMATCH:' + name)
        result = {'status': 'VERIFIED' if not errors else 'INVALID', 'errors': errors,
                  'manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest()}
        if 'HASH_MISMATCH:SKILL.md' in errors:
            result['recovery'] = ('Restore the exact published skill from a trusted release. '
                                  'Keep any host wrapper outside the verified inner package.')
        return result
    except (OSError, ValueError, KeyError, TypeError):
        return {'status': 'INVALID', 'errors': ['PACKAGE_MANIFEST_UNAVAILABLE_OR_INVALID']}


def check():
    dependencies = {}
    for name in ('exchange_calendars', 'numpy', 'pandas', 'tzdata', 'scipy', 'arch', 'yfinance', 'requests', 'lxml', 'statsmodels', 'QuantLib', 'vaderSentiment', 'pyarrow'):
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
            'free_market_evidence': 'AVAILABLE_PUBLIC_OR_SUPPLIED_INPUTS_ACCESS_NOT_CERTIFIED' if integrity['status'] == 'VERIFIED' and not missing_by_capability['free_market_evidence'] else 'UNAVAILABLE',
            'market_flow_and_positioning': 'AVAILABLE_SUPPLIED_DATED_INPUTS_NO_CAUSAL_SQUEEZE_CONFIRMATION' if integrity['status'] == 'VERIFIED' and not missing_by_capability['market_flow_and_positioning'] else 'UNAVAILABLE',
            'institutional_event_pilot': 'AVAILABLE_PAPER_SOFTWARE_REAL_ACCEPTANCE_NOT_ESTABLISHED' if integrity['status'] == 'VERIFIED' and not missing_by_capability['institutional_event_pilot'] and available(['numpy', 'scipy']) else 'UNAVAILABLE',
            'quant_research_assurance': 'AVAILABLE_SUPPLIED_INPUTS_NOT_EXTERNAL_VALIDATION' if integrity['status'] == 'VERIFIED' and not missing_by_capability['quant_research_assurance'] and available(['numpy', 'scipy']) else 'UNAVAILABLE',
            'package_integrity': integrity,
            'historical_data_storage': 'AVAILABLE_REQUIRES_EXPLICIT_ROOT' if integrity['status'] == 'VERIFIED' and not missing_by_capability['historical_data_storage'] else 'UNAVAILABLE',
            'parquet_storage': 'IMPORTABLE_NOT_QUALIFIED' if available(['pyarrow']) else 'UNAVAILABLE_GZIP_STORAGE_UNAFFECTED',
            'compact_evidence': 'AVAILABLE_OPT_IN' if integrity['status'] == 'VERIFIED' and not missing_by_capability['compact_evidence'] else 'UNAVAILABLE',
            'monthly_experiments': 'AVAILABLE_REQUIRES_DATED_INPUTS' if integrity['status'] == 'VERIFIED' and not missing_by_capability['monthly_experiments'] and available(['numpy', 'scipy']) else 'UNAVAILABLE',
            'alignment_hardening': 'AVAILABLE_REQUIRES_SUPPLIED_REQUEST' if integrity['status'] == 'VERIFIED' and not missing_by_capability['alignment_hardening'] and available(['numpy', 'scipy', 'lxml', 'tzdata']) else 'UNAVAILABLE',
            'research_handoff': 'AVAILABLE' if integrity['status'] == 'VERIFIED' and not missing_by_capability['research_handoff'] else 'UNAVAILABLE',
            'missing_files': missing, 'missing_by_capability': missing_by_capability, 'dependencies': dependencies,
            'public_research': 'AVAILABLE' if not missing_by_capability['public_research'] and available(['yfinance', 'requests', 'lxml', 'pandas', 'exchange_calendars']) else 'UNAVAILABLE',
            'shared_default': 'AVAILABLE' if not missing_by_capability['shared_default'] and available(['exchange_calendars', 'numpy', 'pandas', 'tzdata']) else 'UNAVAILABLE',
            'volatility': 'AVAILABLE' if not missing_by_capability['volatility'] and available(['arch', 'numpy', 'pandas', 'scipy', 'statsmodels']) else 'SKIPPED_MISSING_COMPONENTS',
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


def task_preflight(capabilities, *, require_garch=False, anchor=None, calendar=None, vendor=False):
    findings = {}
    if require_garch:
        ready = (capabilities['volatility'] == 'AVAILABLE'
                 and capabilities['package_integrity']['status'] == 'VERIFIED')
        findings['garch'] = {'status': 'READY' if ready else 'BLOCKED',
                             'required_dependencies': ['arch', 'numpy', 'pandas', 'scipy', 'statsmodels']}
    if anchor is not None:
        from paper_pricing import common_anchor
        findings['anchor'] = common_anchor(anchor)
    if calendar is not None:
        from paper_screen import calendar_completeness
        findings['calendar'] = calendar_completeness(calendar)
    if vendor:
        from vendor_observations import contract_check
        findings['vendor_schema'] = contract_check()
    blocked = [name for name, result in findings.items() if result['status'] not in ('READY', 'PASS')]
    return {'status': 'BLOCKED' if blocked else 'READY', 'blocked': blocked, 'checks': findings}


if __name__ == '__main__':
    import sys
    if any(arg == '--request' or arg.startswith('--request=') for arg in sys.argv[1:]):
        from research_record import main
        main()
    elif len(sys.argv) == 1:
        print(json.dumps(check(), indent=2))
    else:
        import argparse
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--require-garch', action='store_true')
        parser.add_argument('--anchor-check', type=Path)
        parser.add_argument('--calendar-check', type=Path)
        parser.add_argument('--vendor-schema', action='store_true')
        flags = parser.parse_args()
        def read_input(path):
            return json.loads(path.read_text(encoding='utf-8-sig')) if path else None
        result = task_preflight(check(), require_garch=flags.require_garch,
                                anchor=read_input(flags.anchor_check),
                                calendar=read_input(flags.calendar_check), vendor=flags.vendor_schema)
        print(json.dumps(result, indent=2, allow_nan=False))
        sys.exit(0 if result['status'] == 'READY' else 2)
