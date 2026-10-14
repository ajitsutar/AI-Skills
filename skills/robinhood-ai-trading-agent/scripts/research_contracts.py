"""Offline request bindings, evidence inventory, horizon routing and method audit.

CLI: research_contracts.py OPERATION INPUT.json --source-root DIR --private-output DIR
Operations: bind-request, inventory-evidence, route-horizon, audit-ranking, schema.
Replay a private receipt: research_contracts.py verify EXPORT_DIRECTORY
The caller explicitly selects roles, pointers and methods. No prompt intent,
source authenticity, acquisition completeness or execution permission is inferred.
All outputs are advisory; invalid research records never veto native execution.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import tempfile

import handoff_report as binding_json
from price_audit import timestamp

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'research-contracts-1'


def require(test, reason):
    if not test:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(binding_json.encode(value).encode('utf-8')).hexdigest()


def envelope(kind, document, result):
    return {'schema_version': 1, 'adapter_version': VERSION, 'kind': kind,
            'input_sha256': digest(document), 'result': result, 'advisory_only': True,
            'execution_gates': [], 'source_authenticity_verified': False,
            'limits': ['Caller-selected fields and roles do not prove correct interpretation of the user request.',
                       'Hashes establish retained-byte consistency, not truth, source authenticity or complete acquisition.',
                       'Research statuses never authorize, delay or refuse native execution.']}


def relative_name(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'RELATIVE_LOCAL_PATH_REQUIRED')
    parts = name.split('/')
    require(all(p and p not in ('.', '..') for p in parts), 'SOURCE_PATH_ESCAPE')
    require(not Path(name).is_absolute(), 'SOURCE_PATH_ESCAPE')
    return name


def source_path(root, name):
    name = relative_name(name)
    root = binding_json.local_path(root)
    path = (root / name).resolve()
    require(path.is_relative_to(root), 'SOURCE_PATH_ESCAPE')
    return path


def inventory_sources(document, root):
    allowlist = document.get('allowlist')
    require(isinstance(allowlist, list) and all(isinstance(x, str) for x in allowlist), 'EXPLICIT_ALLOWLIST_REQUIRED')
    allowed = {relative_name(x) for x in allowlist}
    sources = document.get('sources', [])
    require(isinstance(sources, list) and all(isinstance(s, dict) for s in sources), 'SOURCE_LIST_REQUIRED')
    require(all(isinstance(s.get('id'), str) and s['id'] for s in sources) and
            len({s['id'] for s in sources}) == len(sources), 'UNIQUE_SOURCE_IDS_REQUIRED')
    rows, values = [], {}
    for source in sources:
        row = {'id': source['id'], 'path': source.get('path'), 'role': source.get('role'),
               'expected_sha256': source.get('sha256'), 'actual_sha256': None}
        try:
            require(isinstance(source.get('role'), str) and bool(source['role']), 'SOURCE_ROLE_REQUIRED')
            name = relative_name(source.get('path'))
            if name not in allowed:
                row['status'] = 'NOT_ALLOWLISTED_NOT_READ'
            else:
                path = source_path(root, name)
                if not path.is_file():
                    row['status'] = 'MISSING_BYTES'
                else:
                    raw = path.read_bytes()
                    row['actual_sha256'] = hashlib.sha256(raw).hexdigest()
                    row['bytes'] = len(raw)
                    expected = source.get('sha256')
                    if not isinstance(expected, str) or not re.fullmatch('[a-fA-F0-9]{64}', expected):
                        row['status'] = 'EXPECTED_HASH_MISSING_OR_INVALID'
                    elif row['actual_sha256'] != expected.lower():
                        row['status'] = 'HASH_MISMATCH'
                    else:
                        form = source.get('format', 'json')
                        require(form in ('json', 'text', 'bytes'), 'SOURCE_FORMAT_UNSUPPORTED')
                        values[source['id']] = (binding_json.strict_json(raw) if form == 'json' else
                                                raw.decode('utf-8-sig') if form == 'text' else None)
                        row['status'] = 'BYTES_MATCH'
        except (ValueError, TypeError, OSError) as exc:
            row['status'] = 'INVALID_OR_UNREADABLE'
            row['reason'] = str(exc)
        rows.append(row)
    return rows, values


def pointer(value, path):
    # Unlike the handoff adapter, research observations may legitimately be null.
    if path == '':
        return value
    require(isinstance(path, str) and path.startswith('/'), 'JSON_POINTER_REQUIRED')
    for token in path[1:].split('/'):
        require(not re.search(r'~(?![01])', token), 'INVALID_POINTER_ESCAPE')
        key = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            require(bool(re.fullmatch('0|[1-9][0-9]*', key)), 'INVALID_ARRAY_INDEX')
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ValueError('POINTER_NOT_FOUND')
    return value


def inside(path, record):
    return record == '' or path == record or path.startswith(record + '/')


def leaves(value, path=''):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaves(child, path + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list) and value:
        for i, child in enumerate(value):
            yield from leaves(child, path + '/' + str(i))
    else:
        yield path


def bind_request(document, source_root):
    rows, values = inventory_sources(document, source_root)
    by_id = {row['id']: row for row in rows}
    declared = document.get('bindings', [])
    require(isinstance(declared, list) and all(isinstance(b, dict) for b in declared), 'BINDINGS_REQUIRED')
    require(all(isinstance(b.get('id'), str) for b in declared) and len({b['id'] for b in declared}) == len(declared), 'UNIQUE_BINDING_IDS')
    bound, consumed, targets = [], {}, {}
    prompt = document.get('prompt_binding')
    require(isinstance(prompt, dict), 'PROMPT_BINDING_REQUIRED')
    prompt_result = copy.deepcopy(prompt)
    try:
        prompt_value = pointer(values[prompt['source_id']], prompt.get('pointer', ''))
        require(isinstance(prompt_value, str) and prompt_value.strip(), 'PROMPT_TEXT_REQUIRED')
        prompt_result.update(status='BOUND', prompt_sha256=digest(prompt_value), text=prompt_value,
                             source_sha256=by_id[prompt['source_id']]['actual_sha256'])
        consumed.setdefault(prompt['source_id'], []).append(prompt.get('pointer', ''))
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        prompt_result.update(status='UNRESOLVED', reason=str(exc))
    for item in declared:
        row = copy.deepcopy(item)
        try:
            sid, path = item['source_id'], item['pointer']
            require(item.get('usage') in ('selected', 'unused'), 'BINDING_USAGE_REQUIRED')
            require(isinstance(item.get('target'), str) and item['target'], 'BINDING_TARGET_REQUIRED')
            value = pointer(values[sid], path)
            row.update(status='BOUND', value=value, value_sha256=digest(value),
                       source_sha256=by_id[sid]['actual_sha256'], source_role=by_id[sid]['role'])
            issues = []
            if item.get('required_role') and item['required_role'] != by_id[sid]['role']:
                issues.append('SOURCE_ROLE_MISMATCH')
            record = item.get('record_pointer', '')
            require(isinstance(record, str), 'RECORD_POINTER_REQUIRED')
            pointer(values[sid], record)
            if not inside(path, record):
                issues.append('VALUE_OUTSIDE_DECLARED_RECORD')
            metadata = {}
            meta = item.get('metadata_pointers', {})
            require(isinstance(meta, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in meta.items()), 'METADATA_POINTER_OBJECT_REQUIRED')
            for key, meta_path in meta.items():
                if not inside(meta_path, record):
                    issues.append('METADATA_OUTSIDE_DECLARED_RECORD:' + key)
                metadata[key] = {'pointer': meta_path, 'value': pointer(values[sid], meta_path)}
            row['metadata'] = metadata
            identity = item.get('record_identity')
            if identity:
                actual = pointer(values[sid], identity['pointer'])
                if not inside(identity['pointer'], record) or binding_json.differences(actual, identity['expected']):
                    issues.append('RECORD_IDENTITY_MISMATCH')
                row['record_identity_observed'] = actual
            row['issues'] = issues
            if issues:
                row['status'] = 'CONFLICT'
            if item['usage'] == 'selected':
                targets.setdefault(item['target'], []).append(row)
                consumed.setdefault(sid, []).extend([path] + list(item.get('metadata_pointers', {}).values()))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            row.update(status='UNRESOLVED', reason=str(exc))
        bound.append(row)
    conflicts = []
    for target, selected in targets.items():
        if len({r['value_sha256'] for r in selected}) > 1:
            conflicts.append({'target': target, 'binding_ids': [r['id'] for r in selected],
                              'status': 'CONFLICTING_SELECTED_VALUES'})
    unused = [{'source_id': sid, 'pointer': p} for sid, value in values.items()
              for p in leaves(value) if not any(inside(p, selected) for selected in consumed.get(sid, []))]
    clean = prompt_result['status'] == 'BOUND' and all(r['status'] == 'BOUND' for r in bound) and not conflicts
    return envelope('REQUEST_BINDING', document, {'status': 'BOUND' if clean else 'UNRESOLVED_OR_CONFLICTING',
                    'prompt': prompt_result, 'sources': rows, 'bindings': bound, 'conflicts': conflicts,
                    'unused_supplied_pointers': unused,
                    'selection_validated_against_natural_language': False})


def guarded_checks(checks, root, allowlist):
    """Actually invoke installed source/freshness/report helpers after path checks."""
    import research_handoff
    import research_report_checks
    require(isinstance(checks, list) and all(isinstance(c, dict) for c in checks), 'CHECK_OBJECT_LIST_REQUIRED')
    result = []
    def stable(value):
        # Existing source helpers include OS paths in missing-byte diagnostics.
        # Normalize only diagnostic fields so replay does not depend on a temp
        # directory name; source observations themselves remain unchanged.
        if isinstance(value, dict):
            return {k: diagnostic(v) if k in ('reason', 'reasons') else stable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return value
    def diagnostic(value):
        if isinstance(value, list): return [diagnostic(v) for v in value]
        if isinstance(value, str):
            resolved = str(Path(root).resolve())
            return value.replace(resolved.replace('\\', '\\\\'), '<source-root>').replace(resolved, '<source-root>').replace(resolved.replace('\\', '/'), '<source-root>')
        return value
    def guard(value):
        if isinstance(value, dict):
            if 'content_sha256' in value and 'file' in value:
                require(relative_name(value['file']) in allowlist, 'CHECK_SOURCE_NOT_ALLOWLISTED')
                source_path(root, value['file'])
            for child in value.values(): guard(child)
        elif isinstance(value, list):
            for child in value: guard(child)
    for check in checks:
        name = check.get('kind')
        try:
            args = check['inputs']; guard(args)
            require(isinstance(args, dict), 'CHECK_INPUT_OBJECT_REQUIRED')
            if name == 'primary_source':
                research_handoff.source(args['record'], root)
                output = {'status': 'SAVED_BYTES_CONSISTENT'}
            elif name == 'primary_freshness':
                output = research_handoff.freshness(args['audit'], args['vendor_period'], timestamp(args['cutoff']), root)
            elif name == 'research_handoff':
                output = research_handoff.evaluate(source_root=root, **args)
            elif name in ('pe_claim', 'revision', 'scenario_checks'):
                output = getattr(research_report_checks, name)(**args)
            else:
                raise ValueError('CHECK_NOT_ALLOWLISTED')
            result.append({'kind': name, 'status': 'HELPER_EXECUTED', 'result': stable(output)})
        except (KeyError, IndexError, ValueError, TypeError, OSError, RuntimeError) as exc:
            result.append({'kind': name, 'status': 'UNRESOLVED', 'reason': diagnostic(str(exc))})
    return result


def inventory_evidence(document, source_root):
    rows, values = inventory_sources(document, source_root)
    cutoff = timestamp(document['as_of'])
    sources = {s['id']: s for s in document['sources']}
    counts = {'included': 0, 'excluded': 0, 'unknown': 0}
    receipts, missing_receipts = [], []
    for row in rows:
        source = sources[row['id']]
        classification = source.get('classification')
        if classification is None:
            row['classification'] = {'status': 'NOT_APPLICABLE_NOT_DECLARED'}
        else:
            require(isinstance(classification, dict) and classification.get('status') in counts, 'CLASSIFICATION_STATUS_REQUIRED')
            row['classification'] = copy.deepcopy(classification)
            counts[classification['status']] += 1
        row['chronology'] = {'as_of': document['as_of'], 'published_at': source.get('published_at'),
                             'retrieved_at': source.get('retrieved_at'), 'available_at': source.get('available_at')}
        issues = []
        for name in ('published_at', 'retrieved_at', 'available_at'):
            if source.get(name):
                try:
                    if timestamp(source[name]) > cutoff:
                        issues.append({'published_at': 'PUBLISHED_AFTER_CUTOFF', 'retrieved_at': 'LATER_RETRIEVAL_NOT_NEW_PUBLICATION',
                                       'available_at': 'AVAILABLE_AFTER_CUTOFF'}[name])
                except (ValueError, TypeError):
                    issues.append('INVALID_TIMESTAMP:' + name)
        row['chronology']['issues'] = issues
        if source['role'] == 'acquisition_receipt':
            record = values.get(source['id'])
            if row['status'] == 'BYTES_MATCH' and isinstance(record, dict) and record.get('status') in ('success', 'failure'):
                receipts.append({'source_id': source['id'], 'status': record['status']})
            else:
                missing_receipts.append(source['id'])
    expected_receipts = document.get('expected_acquisition_receipt_ids', [])
    require(isinstance(expected_receipts, list), 'EXPECTED_RECEIPT_IDS_REQUIRED')
    observed_ids = {r['source_id'] for r in receipts}
    missing_receipts = sorted(set(missing_receipts) | (set(expected_receipts) - observed_ids))
    observed_failures = sum(r['status'] == 'failure' for r in receipts)
    declared_complete = document.get('acquisition_coverage') == 'declared_complete' and bool(expected_receipts) and not missing_receipts
    checks = guarded_checks(document.get('checks', []), source_root, set(document['allowlist']))
    return envelope('EVIDENCE_INVENTORY', document, {'sources': rows, 'classification_counts': counts,
                    'acquisition': {'observed_receipts': receipts, 'missing_or_invalid_receipts': missing_receipts,
                                    'observed_failure_count': observed_failures if receipts else None,
                                    'declared_complete_failure_count': observed_failures if declared_complete else None,
                                    'completeness': 'CALLER_DECLARED_WITH_LISTED_RECEIPTS' if declared_complete else 'UNKNOWN_OR_PARTIAL',
                                    'verified_zero_failures': False}, 'checks': checks,
                    'limits': 'Unknown classification is not an evidenced exclusion; absent receipts are not a verified zero-failure audit.'})


def clock_day(value):
    return date.fromisoformat(value) if len(value) == 10 else timestamp(value).date()


def clock_order(left, right):
    """Return -1/0/1 or unknown for overlapping mixed-precision clocks.

    Date-only values have no invented midnight or timezone. Distinct local
    calendar dates can be ordered; same-date mixed precision cannot.
    """
    require(isinstance(left, str) and isinstance(right, str), 'CLOCK_STRING_REQUIRED')
    if len(left) != 10 and len(right) != 10:
        a, b = timestamp(left), timestamp(right)
    elif len(left) == 10 and len(right) == 10:
        a, b = date.fromisoformat(left), date.fromisoformat(right)
    else:
        a, b = clock_day(left), clock_day(right)
        if a == b:
            return None
    return (a > b) - (a < b)


def route_horizon(document, source_root=None):
    mode = document.get('mode')
    require(mode in ('fixed_exit', 'flexible_review', 'comparison'), 'EXPLICIT_HORIZON_MODE_REQUIRED')
    issues, assumptions = [], copy.deepcopy(document.get('planning_assumptions', []))
    require(isinstance(assumptions, list) and all(isinstance(x, dict) and x.get('label') and x.get('value') is not None and
            x.get('basis') in ('user_supplied', 'analyst_proposal') for x in assumptions), 'LABEL_PLANNING_ASSUMPTIONS')
    chronology = {'status': 'DELEGATED_FIXED_CALENDAR'}
    if mode == 'fixed_exit':
        import horizon_review
        resolved = horizon_review.resolve_horizon(document['fixed_spec'])
        comparison, entry = resolved['exit_at'], resolved['entry_at']
        hard_exit = comparison
    else:
        comparison, entry = document['comparison_at'], document['entry_at']
        entry_order = clock_order(entry, comparison)
        asof_order = clock_order(document['as_of'], comparison)
        require(entry_order not in (0, 1) and asof_order != 1, 'HORIZON_CHRONOLOGY')
        chronology = {'as_of': document['as_of'], 'entry_before_comparison': entry_order == -1 if entry_order is not None else None,
                      'as_of_not_after_comparison': asof_order <= 0 if asof_order is not None else None,
                      'status': 'ORDER_CONFIRMED' if entry_order is not None and asof_order is not None else 'MIXED_PRECISION_ORDER_UNKNOWN'}
        resolved, hard_exit = None, None
        if document.get('forced_exit') not in (None, False) or document.get('hard_exit_at') is not None:
            issues.append('FLEXIBLE_REQUEST_CONTAINS_FORCED_EXIT_CONFLICT')
        if document.get('exit_buffer_minutes') is not None:
            issues.append('EXIT_BUFFER_NOT_APPLIED_TO_COMPARISON_DATE')
    coverage = copy.deepcopy(document.get('event_coverage', {}))
    through = coverage.get('through')
    if through is None:
        coverage.update(status='UNKNOWN', unknown_after=entry, unknown_through=comparison)
    else:
        end_order = clock_order(through, comparison)
        complete = end_order is not None and end_order >= 0
        coverage.update(status='DECLARED_THROUGH_COMPARISON' if complete else 'COVERAGE_PRECISION_UNKNOWN' if end_order is None else 'PARTIAL_DECLARED_COVERAGE',
                        unknown_after=None if complete else through, unknown_through=None if complete else comparison)
    return envelope('HORIZON_ROUTE', document, {'mode': mode, 'forced_exit': mode == 'fixed_exit',
                    'comparison_at': comparison, 'hard_exit_at': hard_exit, 'entry_at': entry,
                    'resolved_fixed_exit': resolved, 'event_coverage': coverage, 'chronology': chronology,
                    'planning_assumptions': assumptions, 'issues': issues,
                    'status': 'CONFLICT' if issues else 'ROUTED',
                    'calendar_dates_authenticate_future_events': False})


def audit_ranking(document, source_root):
    rows, values = inventory_sources(document, source_root)
    by_id = {r['id']: r for r in rows}
    requested, observed = document['requested'], document['observed']
    require(isinstance(requested, dict) and isinstance(observed, dict), 'METHOD_SELECTION_OBJECTS_REQUIRED')
    fields = ('profile_id', 'profile_version', 'method', 'implementation_sha256')
    findings, records = [], {}
    for label, selection in (('requested', requested), ('observed', observed)):
        sid = selection['profile_source_id']
        profile = values.get(sid)
        records[label] = {'declaration': copy.deepcopy(selection), 'source': by_id.get(sid)}
        if not isinstance(profile, dict) or by_id[sid]['status'] != 'BYTES_MATCH':
            findings.append(label + ':PROFILE_BYTES_UNAVAILABLE')
            continue
        records[label]['profile_canonical_sha256'] = digest(profile)
        records[label]['profile'] = profile
        for field in ('profile_id', 'profile_version'):
            if selection.get(field) != profile.get(field):
                findings.append(label + ':PROFILE_FIELD_MISMATCH:' + field)
        for field in fields:
            if not isinstance(selection.get(field), str) or not selection[field]:
                findings.append(label + ':METHOD_FIELD_MISSING:' + field)
        if not isinstance(selection.get('implementation_sha256'), str) or not re.fullmatch('[a-fA-F0-9]{64}', selection['implementation_sha256']):
            findings.append(label + ':IMPLEMENTATION_HASH_INVALID')
        if selection.get('implementation_source_id') is not None:
            implementation = by_id.get(selection['implementation_source_id'], {})
            if implementation.get('status') != 'BYTES_MATCH' or implementation.get('actual_sha256') != selection.get('implementation_sha256', '').lower():
                findings.append(label + ':IMPLEMENTATION_BYTES_MISMATCH_OR_UNAVAILABLE')
    for field in fields:
        if requested.get(field) != observed.get(field):
            findings.append('REQUESTED_OBSERVED_MISMATCH:' + field)
    if records['requested'].get('profile_canonical_sha256') != records['observed'].get('profile_canonical_sha256'):
        findings.append('REQUESTED_OBSERVED_PROFILE_HASH_MISMATCH')
    return envelope('RANKING_METHOD_AUDIT', document, {'status': 'METHOD_IDENTITY_MATCH' if not findings else 'METHOD_MISMATCH_OR_UNRESOLVED',
                    'requested': records['requested'], 'observed': records['observed'], 'findings': findings,
                    'ranking_execution_verified': False,
                    'limits': 'Matching declarations and profile bytes do not prove the scorer ran, intrinsic undervaluation or forecast quality.'})


OPERATIONS = {'bind-request': bind_request, 'inventory-evidence': inventory_evidence,
              'route-horizon': route_horizon, 'audit-ranking': audit_ranking}


def schema():
    return {'schema_version': 1, 'operations': [*OPERATIONS, 'verify'],
            'source_contract': {'allowlist': ['inputs.json'], 'sources': [{'id': 'input', 'path': 'inputs.json',
                'sha256': 'EXACT_FILE_SHA256', 'format': 'json', 'role': 'actual_user_request'}]},
            'bind_request_fields': {'prompt_binding': {'source_id': 'prompt', 'pointer': ''},
                'bindings': [{'id': 'equity', 'source_id': 'input', 'pointer': '/account/equity',
                    'target': 'account_equity', 'usage': 'selected', 'required_role': 'observed_account',
                    'record_pointer': '/account', 'record_identity': {'pointer': '/account/id', 'expected': 'account-A'},
                    'metadata_pointers': {'observed_at': '/account/observed_at'}}]},
            'inventory_extra_fields': ['as_of', 'expected_acquisition_receipt_ids', 'acquisition_coverage', 'checks'],
            'check_kinds': ['primary_source', 'primary_freshness', 'research_handoff', 'pe_claim', 'revision', 'scenario_checks'],
            'horizon_fields': ['mode', 'as_of', 'entry_at', 'comparison_at', 'fixed_spec (fixed_exit only)',
                               'event_coverage: {through,basis}', 'planning_assumptions: [{label,value,basis}]'],
            'ranking_fields': {'requested': ['profile_source_id', 'profile_id', 'profile_version', 'method', 'implementation_sha256'],
                               'observed': 'same fields as requested',
                               'optional': 'implementation_source_id binds the declared implementation hash to retained source bytes; no execution inferred'},
            'private_artifacts': ['request.json', 'report.json', 'receipt.json', 'source-bytes/<explicit allowlist path>'],
            'verify': 'verify EXPORT_DIRECTORY checks retained hashes, source presence and installed-helper replay; no authentication or execution permission claim',
            'limits': 'Schema describes explicit caller inputs. It does not infer correct selections from a prompt.'}


def parse_document(raw):
    from report_facts import strict_json
    document = strict_json(raw)
    require(isinstance(document, dict), 'REQUEST_OBJECT_REQUIRED')
    return document


def retained_sources(document, root):
    """Read only explicit local allowlist entries, without interpreting bytes."""
    names = document.get('allowlist', [])
    require(isinstance(names, list), 'EXPLICIT_ALLOWLIST_REQUIRED')
    clean = [relative_name(n) for n in names]
    require(len({n.casefold() for n in clean}) == len(clean), 'UNIQUE_ALLOWLIST_PATHS_REQUIRED')
    require(not clean or root is not None, 'SOURCE_ROOT_REQUIRED')
    files, absent = {}, []
    for name in clean:
        path = source_path(root, name)
        if path.is_file():
            files[name] = path.read_bytes()
        else:
            absent.append(name)
    return files, absent


def write_files(directory, files):
    for name, raw in files.items():
        path = source_path(directory, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)


def export_run(operation, raw, source_root, output):
    """Evaluate a frozen byte snapshot, then retain it in an exclusive directory."""
    require(operation in OPERATIONS, 'UNKNOWN_OPERATION')
    document = parse_document(raw)
    saved, absent = retained_sources(document, source_root)
    output = binding_json.local_path(output)
    require(not output.is_relative_to(ROOT), 'PRIVATE_OUTPUT_OUTSIDE_SKILL_REQUIRED')
    # Running helpers against this snapshot avoids a hash/read race and makes
    # source checks reproducible even after the original source root disappears.
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary)
        write_files(snapshot, saved)
        report = OPERATIONS[operation](document, snapshot)
    files = {'request.json': raw, 'report.json': (binding_json.encode(report) + '\n').encode('utf-8')}
    files.update({'source-bytes/' + name: content for name, content in saved.items()})
    manifest = {'schema_version': 1, 'operation': operation, 'absent_source_paths': absent,
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
                'source_authenticity_verified': False, 'execution_gates': []}
    files['receipt.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode('utf-8')
    output.mkdir(mode=0o700)
    (output / 'source-bytes').mkdir(mode=0o700)
    write_files(output, files)
    return report


def verify(directory):
    """Verify local byte consistency and replay installed helpers, never imports."""
    root = binding_json.local_path(directory)
    receipt = parse_document(source_path(root, 'receipt.json').read_bytes())
    require(receipt.get('schema_version') == 1 and receipt.get('operation') in OPERATIONS, 'RECEIPT_SCHEMA_INVALID')
    files = receipt.get('files')
    require(isinstance(files, dict) and 'request.json' in files and 'report.json' in files, 'RECEIPT_FILES_REQUIRED')
    for name, expected in files.items():
        require(name in ('request.json', 'report.json') or name.startswith('source-bytes/'), 'RECEIPT_PATH_UNSUPPORTED')
        path = source_path(root, name)
        require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected), 'RECEIPT_HASH_INVALID')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'RETAINED_BYTES_MISMATCH')
    document = parse_document((root / 'request.json').read_bytes())
    saved, absent = retained_sources(document, root / 'source-bytes')
    require(sorted(absent) == sorted(receipt.get('absent_source_paths', [])), 'SOURCE_PRESENCE_MISMATCH')
    require(set(files) == {'request.json', 'report.json'} | {'source-bytes/' + n for n in saved}, 'SOURCE_INVENTORY_MISMATCH')
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual_files == set(files) | {'receipt.json'}, 'UNLISTED_RETAINED_FILE')
    expected_report = binding_json.strict_json((root / 'report.json').read_bytes())
    report = OPERATIONS[receipt['operation']](document, root / 'source-bytes')
    replay_json = binding_json.strict_json(binding_json.encode(report).encode('utf-8'))
    require(not binding_json.differences(replay_json, expected_report), 'REPLAY_REPORT_MISMATCH')
    return {'status': 'RETAINED_BYTES_AND_REPLAY_CONSISTENT', 'operation': receipt['operation'],
            'file_count': len(files), 'source_authenticity_verified': False, 'execution_gates': []}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=[*OPERATIONS, 'schema', 'verify']); p.add_argument('input', nargs='?')
    p.add_argument('--source-root'); p.add_argument('--private-output')
    args = p.parse_args()
    if args.operation == 'schema':
        print(json.dumps(schema(), indent=2)); return
    try:
        if args.operation == 'verify':
            require(args.input is not None, 'EXPORT_DIRECTORY_REQUIRED')
            verify(args.input)
            return
        require(args.input is not None and args.private_output is not None, 'INPUT_AND_PRIVATE_OUTPUT_REQUIRED')
        require(args.source_root is not None or args.operation == 'route-horizon', 'SOURCE_ROOT_REQUIRED')
        raw = binding_json.local_path(args.input).read_bytes()
        export_run(args.operation, raw, args.source_root, args.private_output)
    except (ValueError, KeyError, IndexError, TypeError, OSError, RuntimeError):
        p.exit(2, 'Research receipt unavailable: inspect local schema, bindings and output path. Native execution permissions unchanged.\n')


if __name__ == '__main__':
    main()
