"""On-demand workflow setup using existing preflight and ordinary research helpers.

No discovery of private configuration, network request, installation or service.
Native tools named by the host remain declarations until the host uses them.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
from pathlib import Path
import platform
import sys

import research_preflight
import research_session

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = {
    'earnings_guidance': {'research_session': ('start_session', 'prepare_packet'),
                          'filing_documents': ('extract_document',)},
    'event_research': {'research_session': ('start_session', 'prepare_packet'),
                       'filing_documents': ('extract_document',)},
    'refresh': {'research_refresh': ('begin_refresh', 'prepare_refresh', 'start_review', 'complete_refresh')},
    'options_activity': {'options_activity': ('parse', 'analyze', 'bind_float')},
}


def encode(value):
    return research_session.encode(value)


def source_probe(value):
    """Read only an explicitly selected bounded local file through the existing guard."""
    try:
        path = research_session.local(value)
        raw = research_session.read(path)
        if not raw:
            raise ValueError('EMPTY_SOURCE')
        return {'path': str(path), 'status': 'READABLE', 'byte_length': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'source_authenticity_verified': False}
    except (OSError, ValueError) as exc:
        return {'path': str(value), 'status': 'UNAVAILABLE', 'reason': type(exc).__name__,
                'detail': str(exc) if isinstance(exc, ValueError) else 'Explicit selected file could not be read.'}


def setup(workflow, output_root, *, sources=(), host='unspecified', declared_tools=()):
    """Create one private setup receipt; every new attempt requires a new directory.

    The assistant supplies workflow and explicit sources. Host labels/tool names
    are recorded as declarations, never promoted into observed availability.
    """
    if workflow not in WORKFLOWS:
        raise ValueError('SUPPORTED_WORKFLOW_REQUIRED')
    if not isinstance(host, str) or not host.strip() or len(host) > 100:
        raise ValueError('BOUNDED_HOST_LABEL_REQUIRED')
    sources, declared_tools = list(sources), list(declared_tools)
    if len(sources) > 100 or len(declared_tools) > 50 or any(
            not isinstance(t, str) or not t.strip() or len(t) > 200 for t in declared_tools):
        raise ValueError('BOUNDED_EXPLICIT_INPUTS_REQUIRED')
    output_root = research_session.local(output_root)
    if output_root.exists() or not output_root.parent.is_dir() or output_root.is_relative_to(ROOT):
        raise ValueError('NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED')
    output_root.mkdir()
    report = {'schema_version': 1, 'workflow': workflow, 'host_as_declared': host,
              'observed_at': datetime.now(timezone.utc).isoformat(),
              'runtime': {'python': platform.python_version(), 'platform': sys.platform,
                          'status': 'OBSERVED_THIS_INVOCATION'},
              'native_tools': [{'name': t, 'status': 'DECLARED_NOT_TESTED'} for t in declared_tools],
              'execution_authorized': False, 'backend_required': False,
              'limits': ['Local checks do not establish native tool access, data entitlement, source authenticity, '
                         'semantic correctness, execution authority or another host demonstration.']}
    try:
        # Reuse the package's existing inventory instead of maintaining a second dependency framework.
        try:
            report['preflight'] = research_preflight.check()
        except Exception as exc:
            report['preflight'] = {'package_integrity': {'status': 'INVALID'},
                                   'error': type(exc).__name__}
        modules = []
        for name, methods in WORKFLOWS[workflow].items():
            entry = {'module': name, 'required_callables': list(methods)}
            try:
                module = importlib.import_module(name)
                missing = [m for m in methods if not callable(getattr(module, m, None))]
                entry.update(status='UNAVAILABLE' if missing else 'IMPORTABLE_CALLABLES_PRESENT',
                             missing_callables=missing)
            except Exception as exc:
                entry.update(status='UNAVAILABLE', reason=type(exc).__name__)
            modules.append(entry)
        report['workflow_modules'] = modules
        report['sources'] = [source_probe(p) for p in sources]
        # An actual bounded write/read/remove proves only this explicitly selected output directory.
        probe = output_root / 'write-probe.tmp'
        probe.write_bytes(b'ai-trading-agent private setup probe\n')
        if probe.read_bytes() != b'ai-trading-agent private setup probe\n':
            raise OSError('OUTPUT_READBACK_FAILED')
        probe.unlink()
        report['private_output'] = {'status': 'WRITE_READ_REMOVE_OBSERVED', 'path': str(output_root)}
        valid_package = report['preflight'].get('package_integrity', {}).get('status') == 'VERIFIED'
        modules_ok = all(m['status'] == 'IMPORTABLE_CALLABLES_PRESENT' for m in modules)
        files_ok = bool(sources) and all(s['status'] == 'READABLE' for s in report['sources'])
        report['status'] = ('READY_FOR_LOCAL_EVIDENCE_PREPARATION' if valid_package and modules_ok and files_ok
                            else 'LIMITED_SETUP')
        recovery = []
        if not valid_package:
            recovery.append({'issue': 'PACKAGE_INTEGRITY_UNVERIFIED', 'action':
                'Use a verified complete package; retain this result. Do not regenerate a manifest to hide missing files.'})
        if not modules_ok:
            recovery.append({'issue': 'WORKFLOW_HELPER_UNAVAILABLE', 'action':
                'Continue source reading and native authored review where supported; disclose helper work not performed. '
                'Use an already permitted Python environment if available. Do not auto-install.'})
        if not files_ok:
            recovery.append({'issue': 'SOURCE_CONTENT_NOT_READY', 'action':
                'The assistant opens permitted free primary sources with available native tools, then retains explicit files. '
                'If unavailable, use genuinely supplied documents; otherwise deliver a limited answer naming missing documents.'})
        if files_ok:
            recovery.append({'issue': 'NATIVE_ACQUISITION_NOT_ESTABLISHED', 'action':
                'Proceed with these explicit readable sources within their dated scope. '
                'Do not call this live acquisition or a current refresh.'})
        report['bounded_recovery'] = {'maximum_new_setup_attempts': 1,
            'retry_only_after_observed_change': True, 'steps': recovery,
            'stop': 'After one changed-input retry, deliver supported work and concrete remaining limitations; preserve both receipts.'}
    except Exception as exc:
        report['status'] = 'SETUP_FAILED'
        report['failure'] = {'type': type(exc).__name__, 'detail': 'Local setup probe failed.'}
    (output_root / 'setup.json').write_bytes(encode(report))
    return report


def exercise(output_root, *, host='unspecified'):
    """Run a fictional ordinary-task setup/packet fixture, not a full research answer."""
    output_root = research_session.local(output_root)
    if output_root.exists() or not output_root.parent.is_dir() or output_root.is_relative_to(ROOT):
        raise ValueError('NEW_PRIVATE_OUTPUT_DIRECTORY_REQUIRED')
    output_root.mkdir()
    request = b'Review Fictional Helio earnings and guidance. Explain the main risks.\n'
    raw = (b'<html><body><h2>Item 2.02 Results of Operations and Financial Condition</h2>'
           b'<p>Fictional Helio revenue was USD 110 million versus USD 100 million. '
           b'FY2030 adjusted diluted EPS guidance is USD 2.00. '
           b'Supply constraints could delay shipments. Outlook is forward-looking.</p></body></html>')
    source = output_root / 'fictional-release.html'
    source.write_bytes(raw)
    result = {'fixture': 'offline-fictional-ordinary-setup-v1', 'host_as_declared': host,
              'full_answer_or_review_demonstrated': False, 'live_acquisition_demonstrated': False,
              'other_hosts_demonstrated': False}
    try:
        result['setup'] = setup('earnings_guidance', output_root / 'setup', sources=[source], host=host)
        tasks = [{'id': 'earnings', 'requirement': 'Explain the reported earnings and guidance.',
                  'request_excerpt': 'earnings and guidance', 'required_source_ids': ['release']},
                 {'id': 'risks', 'requirement': 'Explain the principal risks and evidence limits.',
                  'request_excerpt': 'main risks', 'required_source_ids': ['release']}]
        started = research_session.start_session(output_root / 'session', request,
            workflow='earnings_guidance', sources=[{'id': 'release', 'path': str(source),
                'role': 'fictional supplied issuer release', 'origin': 'supplied'}], tasks=tasks,
            as_of='2030-07-15T18:00:00Z')
        prepared = research_session.prepare_packet(output_root / 'session',
            expected_session_sha256=started['session_sha256'], dispositions=[{
                'id': t['id'], 'status': 'limited', 'reason':
                'Fictional partial source; setup fixture does not establish full research coverage.',
                'evidence_ids': ['release']} for t in tasks],
            filings=[{'source_id': 'release', 'options': {'form_type': '8-K',
                'content_type': 'text/html', 'passage_terms': ['guidance', 'constraints']}}])
        result.update(session_sha256=started['session_sha256'], packet_sha256=prepared['packet_sha256'],
                      packet_status=prepared['packet']['status'])
        extracted = prepared['packet']['filing_extractions']
        result['status'] = ('LOCAL_SETUP_AND_PACKET_OBSERVED' if len(extracted) == 1 and
                            not prepared['packet']['filing_errors'] else 'FIXTURE_LIMITED_OR_FAILED')
    except Exception as exc:
        result.update(status='FIXTURE_FAILED', failure={'type': type(exc).__name__, 'detail': str(exc)})
    (output_root / 'exercise.json').write_bytes(encode(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check')
    check.add_argument('--workflow', required=True, choices=WORKFLOWS)
    check.add_argument('--source', action='append', default=[], type=Path)
    check.add_argument('--declare-native-tool', action='append', default=[])
    for sub in (check, commands.add_parser('exercise')):
        sub.add_argument('--output', required=True, type=Path)
        sub.add_argument('--host', default='unspecified')
    args = parser.parse_args()
    result = (exercise(args.output, host=args.host) if args.command == 'exercise' else
              setup(args.workflow, args.output, sources=args.source, host=args.host,
                    declared_tools=args.declare_native_tool))
    print(json.dumps(result, indent=2))
    return 0 if result['status'] in ('READY_FOR_LOCAL_EVIDENCE_PREPARATION',
                                     'LOCAL_SETUP_AND_PACKET_OBSERVED') else 2


if __name__ == '__main__':
    raise SystemExit(main())
