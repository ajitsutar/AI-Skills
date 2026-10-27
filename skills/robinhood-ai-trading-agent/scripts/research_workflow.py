"""Offline source-to-result research plans and verifiable reports.

The caller selects operations and binds their arguments to local source pointers
or explicit assumptions. No natural-language intent, observation authenticity,
network access, arbitrary code or trading action is inferred or performed.
"""
from __future__ import annotations

import argparse
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile

import handoff_report as exact_json
import report_facts
import research_contracts
from research_contracts import require

# The execute checkpoint must remain available when numerical dependencies are
# absent. These lightweight modules above use only the standard library.
DEPENDENCY_FAILURE = None
try:
    import quant_report
    import quant_workbench
except ImportError as exc:
    quant_report = quant_workbench = None
    DEPENDENCY_FAILURE = {'type': type(exc).__name__, 'module': getattr(exc, 'name', None),
                          'reason': str(exc)}

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'research-workflow-3'
CONTRACT_OPERATIONS = {
    'research.bind_request': research_contracts.bind_request,
    'research.inventory_evidence': research_contracts.inventory_evidence,
    'research.route_horizon': research_contracts.route_horizon,
    'research.audit_ranking': research_contracts.audit_ranking,
}


def encode(value):
    # Preserve source Decimal scale: contract value hashes include that spelling.
    # Give generated floats the same scientific notation on export and reload.
    def numbers(item):
        if isinstance(item, dict):
            return {key: numbers(child) for key, child in item.items()}
        if isinstance(item, list):
            return [numbers(child) for child in item]
        if type(item) is float:
            return Decimal(str(item))
        return item
    return (exact_json.encode(numbers(value)) + '\n').encode('utf-8')


def assertion_matches(actual, expected):
    """Compare JSON values, preserving types but ignoring decimal display scale."""
    fractional = (float, Decimal)
    if isinstance(actual, fractional) and isinstance(expected, fractional):
        return Decimal(str(actual)) == Decimal(str(expected))
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            assertion_matches(actual[key], expected[key]) for key in actual)
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            assertion_matches(a, b) for a, b in zip(actual, expected))
    return actual == expected


def read_result(raw):
    """Reload exact contract evidence without changing quant numeric semantics."""
    result = report_facts.strict_json(raw)
    exact = exact_json.strict_json(raw)
    contract_ids = set()
    for job, retained in zip(result.get('jobs', []), exact.get('jobs', [])):
        if job.get('operation') in CONTRACT_OPERATIONS:
            contract_ids.add(job['id'])
            for key in ('result', 'nested_states'):
                if key in retained:
                    job[key] = retained[key]
    for claim, retained in zip(result.get('claims', []), exact.get('claims', [])):
        if claim.get('job_id') in contract_ids and 'actual_value' in retained:
            claim['actual_value'] = retained['actual_value']
    return result


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def implementation_hash():
    # Contract adapters invoke other local helpers. Bind all installed code and
    # profiles so a transitive implementation change cannot escape this receipt.
    paths = sorted((ROOT / 'scripts').glob('*.py')) + sorted((ROOT / 'profiles').glob('*.json'))
    return quant_workbench.digest({p.relative_to(ROOT).as_posix(): p.read_text(encoding='utf-8')
                                   for p in paths})


def catalog():
    return {
        'schema_version': 1,
        'operation_catalog': quant_workbench.operation_catalog(),
        'additional_operations': {
            'research.bind_request': ['document'],
            'research.inventory_evidence': ['document'],
            'research.route_horizon': ['document'],
            'research.audit_ranking': ['document'],
            'report.quant': ['source_id', 'custom_source_id (optional)', 'include_source_text (optional)'],
            'report.public_vqm': ['source_id', 'custom_source_id (optional)', 'include_source_text (optional)'],
        },
        'source': {'id': 'unique-id', 'path': 'relative/local.json', 'sha256': 'exact file SHA-256',
                   'format': 'json | text | bytes', 'role': 'declared source role'},
        'argument_binding': {'$source': {'id': 'unique-id', 'pointer': '/record/value'}},
        'assumption_binding': {'$assumption': 0.01, 'reason': 'Explicit analyst scenario, not observed data'},
        'requirement': {'id': 'question-1', 'question': 'Specific requested work',
                        'job_ids': ['job-1'], 'expected_operations': ['planning.cash_plan']},
        'claim': {'id': 'claim-1', 'job_id': 'job-1', 'pointer': '/result/status',
                  'assertion': 'Optional literal claim checked exactly, including JSON value types'},
        'prepare': {
            'input': 'Existing workbench request with full inputs or inputs_source {path, sha256, pointer}',
            'request_role': 'Required explicit role for the retained original request',
            'source_roles': 'Required explicit role for every distinct inputs_source path',
            'preserved': ['contract', 'job IDs and operations', 'entire selected inputs',
                          'requirements', 'claims', 'omitted installed-helper defaults'],
            'output': 'New private directory containing plan.json and exact source bytes'},
        'summary': 'Verify a retained run, then project claims, coverage, source bindings and literal evidence states',
        'execute': {
            'input': 'The same explicit workbench request and source roles as prepare',
            'output': 'New private root with prepare, run, verification and summary directories, fixed answer facts, completion receipt and artifact inventory',
            'failure_policy': 'Preserve original request, partial artifacts and per-job failure states. Never overwrite or automatically retry.',
            'scope': 'Offline installed helpers only. No dependency installation, backend, host download or remote action.'},
        'limits': ['Source identities and operation selection remain declared, not inferred from prose.',
                   'Requirements are an explicit checklist, not proof that the entire prompt was understood.',
                   'No execution prerequisites or external actions.'],
    }


def prepare_artifacts(raw, source_reader, request_role, source_roles=None):
    """Translate an explicit workbench request, never a prompt or partial inputs.

    Source roles are supplied independently; no filename or data-based guessing.
    Full input objects remain selected from retained bytes, including bad helper
    inputs. Only the installed quant runner resolves omitted helper defaults.
    """
    require(isinstance(request_role, str) and request_role.strip(), 'REQUEST_ROLE_REQUIRED')
    source_roles = {} if source_roles is None else source_roles
    require(isinstance(source_roles, dict) and all(isinstance(k, str) and
            isinstance(v, str) and v.strip() for k, v in source_roles.items()), 'SOURCE_ROLES_REQUIRED')
    document = report_facts.strict_json(raw)
    require(isinstance(document, dict) and set(document) <= {
        'schema_version', 'network_mode', 'contract', 'jobs', 'requirements', 'claims'},
        'PREPARE_REQUEST_FIELDS')
    require(document.get('network_mode', 'offline') == 'offline', 'OFFLINE_PLAN_REQUIRED')
    require(isinstance(document.get('contract'), dict) and
            isinstance(document['contract'].get('prompt'), str), 'CONTRACT_REQUIRED')
    jobs = document.get('jobs')
    unique_rows(jobs, 'JOB')
    expected_paths = set()
    for job in jobs:
        require(set(job) in ({'id', 'operation', 'inputs'}, {'id', 'operation', 'inputs_source'}),
                'PREPARE_JOB_FIELDS')
        if 'inputs_source' in job:
            ref = job['inputs_source']
            require(isinstance(ref, dict) and set(ref) == {'path', 'sha256', 'pointer'} and
                    isinstance(ref['path'], str), 'INPUT_SOURCE_FIELDS')
            expected_paths.add(ref['path'])
    require(set(source_roles) == expected_paths, 'EXACT_SOURCE_ROLES_REQUIRED')
    for field, kind in (('requirements', 'REQUIREMENT'), ('claims', 'CLAIM')):
        unique_rows(document.get(field, []), kind)
    # The installed resolver validates hashes, operations, pointers and the
    # selected whole-object type without running a calculation or adding defaults.
    _, references, retained = quant_report.resolve_request(raw, source_reader)
    artifacts = {'original-request.json': raw}
    sources = [{'id': 'request', 'path': 'original-request.json', 'sha256': sha(raw),
                'format': 'json', 'role': request_role}]
    selections = {}
    for ref in references:
        index = ref['job_index']
        sid = f'input-{index:04d}'
        name = 'inputs/' + ref['artifact']
        artifacts[name] = retained[ref['artifact']]
        sources.append({'id': sid, 'path': name, 'sha256': ref['sha256'],
                        'format': 'json', 'role': source_roles[ref['path']]})
        selections[index] = {'id': sid, 'pointer': ref['pointer']}
    plan = {'schema_version': 1, 'network_mode': 'offline',
            'preparation': {'kind': 'WORKBENCH_REQUEST', 'request_source_id': 'request'},
            'contract': copy.deepcopy(document['contract']), 'sources': sources,
            'jobs': [{'id': job['id'], 'operation': job['operation'],
                      'arguments': {'$source': selections.get(index, {
                          'id': 'request', 'pointer': f'/jobs/{index}/inputs'})}}
                     for index, job in enumerate(jobs)],
            'requirements': copy.deepcopy(document.get('requirements', [])),
            'claims': copy.deepcopy(document.get('claims', []))}
    artifacts['plan.json'] = encode(plan)
    return artifacts


def check_preparation(document, sources, artifacts):
    """Re-derive every prepared plan field from the retained original request."""
    require(document['preparation'] == {'kind': 'WORKBENCH_REQUEST', 'request_source_id': 'request'},
            'PREPARATION_FIELDS')
    original = artifacts['sources/' + sources['request']['path']]
    request = report_facts.strict_json(original)
    roles = {job['inputs_source']['path']: sources[f'input-{index:04d}']['role']
             for index, job in enumerate(request['jobs']) if 'inputs_source' in job}
    prepared = prepare_artifacts(original, lambda _path, index:
        artifacts['sources/' + sources[f'input-{index:04d}']['path']], sources['request']['role'], roles)
    require(encode(document) == prepared['plan.json'], 'PREPARED_REQUEST_BINDING_MISMATCH')


def prepare(request, output, request_role, source_roles=None, attempted_source_writer=None):
    request, output = report_facts.local_path(request), report_facts.local_path(output)
    require(not output.is_relative_to(ROOT) and not output.exists(), 'NEW_PRIVATE_OUTPUT_REQUIRED')

    def reader(path, index):
        # Preserve quant_report's local-path restrictions, including URL/UNC
        # rejection before joining. Original source names remain in the request.
        report_facts.local_path(path)
        raw = report_facts.local_path(request.parent / path).read_bytes()
        if attempted_source_writer is not None:
            attempted_source_writer(path, index, raw)
        return raw

    artifacts = prepare_artifacts(request.read_bytes(), reader, request_role, source_roles)
    output.mkdir()
    for name, raw in artifacts.items():
        path = output / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle:
            handle.write(raw)
    return report_facts.strict_json(artifacts['plan.json'])


def bind(value, values, sources, trail='', bindings=None):
    """Every scalar is source-bound or explicitly an assumption; no expressions."""
    if bindings is None:
        bindings = []
    if isinstance(value, dict):
        if '$source' in value:
            require(set(value) == {'$source'}, 'SOURCE_BINDING_FIELDS')
            ref = value['$source']
            require(isinstance(ref, dict) and set(ref) == {'id', 'pointer'}, 'SOURCE_REFERENCE_FIELDS')
            sid = ref['id']
            selected = research_contracts.pointer(values[sid], ref['pointer'])
            bindings.append({'target_pointer': trail, 'kind': 'SOURCE', 'source_id': sid,
                             'source_pointer': ref['pointer'], 'source_role': sources[sid]['role'],
                             'source_sha256': sources[sid]['sha256'],
                             'selected_value_sha256': quant_workbench.digest(selected)})
            return copy.deepcopy(selected)
        if '$assumption' in value:
            require(set(value) == {'$assumption', 'reason'} and isinstance(value['reason'], str)
                    and value['reason'].strip(), 'ASSUMPTION_REASON_REQUIRED')
            bindings.append({'target_pointer': trail, 'kind': 'ASSUMPTION',
                             'reason': value['reason'], 'value': copy.deepcopy(value['$assumption'])})
            return copy.deepcopy(value['$assumption'])
        require(not any(k.startswith('$') for k in value), 'UNKNOWN_BINDING_OPERATOR')
        return {k: bind(v, values, sources, trail + '/' + report_facts.escape(k), bindings)
                for k, v in value.items()}
    if isinstance(value, list):
        return [bind(v, values, sources, trail + '/' + str(i), bindings) for i, v in enumerate(value)]
    raise ValueError('UNBOUND_LITERAL:' + trail)


def unique_rows(rows, kind):
    require(isinstance(rows, list) and all(isinstance(r, dict) and isinstance(r.get('id'), str)
            and r['id'].strip() for r in rows), kind + '_OBJECTS_REQUIRED')
    require(len({r['id'] for r in rows}) == len(rows), kind + '_UNIQUE_IDS')


def source_inventory(document, reader):
    rows = document.get('sources', [])
    unique_rows(rows, 'SOURCE')
    sources, values, artifacts = {}, {}, {}
    paths = set()
    for row in rows:
        require(set(row) == {'id', 'path', 'sha256', 'format', 'role'}, 'SOURCE_FIELDS')
        path = research_contracts.relative_name(row['path'])
        require(path.casefold() not in paths, 'UNIQUE_SOURCE_PATHS')
        paths.add(path.casefold())
        require(row['format'] in ('json', 'text', 'bytes'), 'SOURCE_FORMAT')
        require(isinstance(row['role'], str) and bool(row['role'].strip()), 'SOURCE_ROLE_REQUIRED')
        raw = reader(path)
        require(sha(raw) == row['sha256'], 'SOURCE_HASH_MISMATCH')
        sources[row['id']] = copy.deepcopy(row)
        values[row['id']] = (report_facts.strict_json(raw) if row['format'] == 'json' else
                            raw.decode('utf-8-sig') if row['format'] == 'text' else None)
        artifacts['sources/' + path] = raw
    return sources, values, artifacts


def nested_states(value, trail=''):
    """Retain evidence states beneath a successful computation wrapper."""
    if isinstance(value, dict):
        for key, child in sorted(value.items()):
            path = trail + '/' + report_facts.escape(key)
            if key in ('status', 'reason', 'warning', 'warnings', 'limitation', 'limits',
                       'unknowns', 'rejections', 'rejected', 'remaining_requirement'):
                yield {'pointer': path, 'value': child}
            yield from nested_states(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from nested_states(child, trail + '/' + str(index))


def coverage(requirements, jobs):
    unique_rows(requirements, 'REQUIREMENT')
    rows = []
    for item in requirements:
        require(isinstance(item.get('question'), str) and item['question'].strip(), 'QUESTION_REQUIRED')
        ids = item.get('job_ids', [])
        require(isinstance(ids, list) and len(ids) == len(set(ids)), 'REQUIREMENT_JOB_IDS')
        selected = [jobs.get(job_id) for job_id in ids]
        expected = item.get('expected_operations', [])
        require(isinstance(expected, list) and all(isinstance(x, str) for x in expected), 'EXPECTED_OPERATIONS')
        operations = [j['operation'] for j in selected if j is not None]
        missing = [op for op in expected if op not in operations]
        status = ('UNADDRESSED' if not ids else 'UNKNOWN_JOB' if None in selected else
                  'OPERATION_MISMATCH' if missing else
                  'EXECUTED' if all(j['status'] == 'COMPUTED' for j in selected) else 'PARTIAL_OR_FAILED')
        rows.append({**copy.deepcopy(item), 'status': status, 'operations_executed': operations,
                     'missing_expected_operations': missing,
                     'meaning': 'Executed means the declared work ran; nested results may remain unresolved.'})
    return rows


def claims(rows, jobs):
    unique_rows(rows, 'CLAIM')
    result = []
    for item in rows:
        row = copy.deepcopy(item)
        try:
            job = jobs[item['job_id']]
            value = research_contracts.pointer(job, item['pointer'])
            row['actual_value'] = value
            row['job_result_sha256'] = sha(encode(job))
            row['status'] = ('MATCH' if assertion_matches(value, item['assertion'])
                             else 'CONTRADICTED') if 'assertion' in item else 'PROJECTED'
        except (KeyError, IndexError, TypeError, ValueError):
            row['status'] = 'UNRESOLVED_POINTER'
        result.append(row)
    return result


def render(result, job_reports):
    lines = ['Source-bound research report', '',
             'Workflow: ' + result['status'] + '. Research diagnostics only; no execution gates.', '',
             'Declared objective: ' + json.dumps(result['contract']['prompt'], ensure_ascii=False), '',
             'Coverage is a declared checklist. It does not prove complete interpretation of the prompt.', '',
             '## Requested work', '', '```json', encode(result['coverage']).decode(), '```', '',
             '## Claims projected or checked against actual results', '', '```json',
             encode(result['claims']).decode(), '```', '',
             'No free-form commentary outside this generated report has been verified.', '',
             '## Source bindings and assumptions', '', '```json',
             encode(result['bindings']).decode(), '```', '',
             '## Unconsumed supplied fields', '', '```json', encode(result['unused_source_pointers']).decode(), '```', '',
             '## Helper results', '']
    for job in result['jobs']:
        lines.extend(['### ' + json.dumps(job['id']) + ': ' + job['operation'], '', '```json',
                      encode(job).decode(), '```', ''])
        if job['id'] in job_reports:
            lines.extend([job_reports[job['id']], ''])
    return '\n'.join(lines).encode('utf-8')


class _RetainedArtifacts(dict):
    """Optionally retain each completed artifact before a later stage can fail."""
    def __init__(self, initial, writer=None):
        super().__init__()
        self.writer = writer
        for name, data in initial.items():
            self[name] = data

    def __setitem__(self, name, data):
        if self.writer is not None:
            self.writer(name, data)
        super().__setitem__(name, data)


def build(raw, reader, artifact_writer=None):
    doc = report_facts.strict_json(raw)
    require(doc.get('schema_version') == 1 and doc.get('network_mode') == 'offline', 'OFFLINE_PLAN_REQUIRED')
    contract = doc['contract']
    require(isinstance(contract, dict) and isinstance(contract.get('prompt'), str), 'CONTRACT_REQUIRED')
    jobs = doc.get('jobs', [])
    unique_rows(jobs, 'JOB')
    sources, values, artifacts = source_inventory(doc, reader)
    artifacts = _RetainedArtifacts(artifacts, artifact_writer)
    if 'preparation' in doc:
        check_preparation(doc, sources, artifacts)
    artifacts['plan.json'] = raw
    results, bindings, reports, consumed = [], [], {}, {}
    if 'preparation' in doc:
        # All original request fields were consumed by the exact re-derivation.
        consumed['request'] = ['']
    with tempfile.TemporaryDirectory(prefix='research-sources-') as temp:
        source_root = Path(temp)
        for name, data in artifacts.items():
            if name.startswith('sources/'):
                path = source_root / name[8:]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
        for index, job in enumerate(jobs):
            op = job.get('operation')
            row = {'id': job['id'], 'operation': op}
            job_bindings = []
            try:
                args = bind(job.get('arguments', {}), values, sources, bindings=job_bindings)
                require(isinstance(args, dict), 'ARGUMENT_OBJECT_REQUIRED')
                row['arguments_sha256'] = quant_workbench.digest(args)
                artifacts[f'jobs/{index:04d}/arguments.json'] = encode(args)
                if op in quant_workbench.OPERATIONS:
                    request = {'schema_version': 1, 'contract': contract,
                               'jobs': [{'id': job['id'], 'operation': op, 'inputs': args}]}
                    output = quant_report.build(encode(request), lambda *_: None)
                    for name, data in output.items():
                        artifacts[f'jobs/{index:04d}/quant/{name}'] = data
                    bundle = report_facts.strict_json(output['bundle.json'])
                    computed = bundle['result']['results'][0]
                    row.update(status=computed['status'], result=computed.get('result'),
                               reason=computed.get('reason'),
                               prepared_input_sha256=report_facts.strict_json(output['receipt.json'])['prepared_input_sha256'])
                    reports[job['id']] = output['report.md'].decode('utf-8')
                elif op in CONTRACT_OPERATIONS:
                    require(set(args) == {'document'}, 'DOCUMENT_ARGUMENT_REQUIRED')
                    document = args['document']
                    if op in ('research.bind_request', 'research.inventory_evidence', 'research.audit_ranking'):
                        # Local checks can read only the retained declared source paths.
                        require(set(document.get('allowlist', [])) <= {s['path'] for s in sources.values()}, 'UNRETAINED_SOURCE')
                        value = CONTRACT_OPERATIONS[op](document, source_root)
                    else:
                        value = CONTRACT_OPERATIONS[op](document)
                    row.update(status='COMPUTED', result=value)
                elif op in ('report.quant', 'report.public_vqm'):
                    require(set(args) <= {'source_id', 'custom_source_id', 'include_source_text'}
                            and 'source_id' in args, 'REPORT_ARGUMENTS')
                    source = sources[args['source_id']]
                    original = artifacts['sources/' + source['path']]
                    custom = (artifacts['sources/' + sources[args['custom_source_id']]['path']]
                              if args.get('custom_source_id') else None)
                    kind = 'quant' if op == 'report.quant' else 'public-vqm'
                    source_text = args.get('include_source_text', False)
                    require(type(source_text) is bool, 'SOURCE_TEXT_OPTION')
                    facts = report_facts.project(original, kind, custom_raw=custom, include_source_text=source_text)
                    projection = encode(facts)
                    verification = report_facts.verify_projection(original, kind, projection,
                                                                  custom_raw=custom, include_source_text=source_text)
                    row.update(status='COMPUTED', result={'facts': facts, 'projection_verification': verification})
                    reports[job['id']] = report_facts.markdown(facts)
                    consumed.setdefault(source['id'], []).append('')
                    if args.get('custom_source_id'):
                        consumed.setdefault(args['custom_source_id'], []).append('')
                else:
                    row.update(status='UNSUPPORTED_OPERATION', reason='No installed operation with this name; custom analysis is distinct.')
            except (KeyError, IndexError, ValueError, TypeError, OSError, OverflowError) as exc:
                row.update(status='UNRESOLVED_INPUT_OR_FAILED', reason=type(exc).__name__ + ':' + str(exc))
            row['nested_states'] = list(nested_states(row.get('result')))
            bindings.append({'job_id': job['id'], 'arguments': job_bindings})
            for binding in job_bindings:
                if binding['kind'] == 'SOURCE':
                    consumed.setdefault(binding['source_id'], []).append(binding['source_pointer'])
            results.append(row)
    by_id = {r['id']: r for r in results}
    checked_claims = claims(doc.get('claims', []), by_id)
    checked_coverage = coverage(doc.get('requirements', []), by_id)
    unresolved = not results or not checked_coverage or any(r['status'] != 'COMPUTED' for r in results) or any(
        r['status'] != 'EXECUTED' for r in checked_coverage) or any(
        r['status'] in ('CONTRADICTED', 'UNRESOLVED_POINTER') for r in checked_claims)
    unused = [{'source_id': sid, 'pointer': p} for sid, value in values.items()
              for p in research_contracts.leaves(value)
              if not any(research_contracts.inside(p, used) for used in consumed.get(sid, []))]
    result = {'schema_version': 1, 'status': 'DIAGNOSTICS_PRESENT' if unresolved else 'COMPUTED',
              'contract': contract, 'network_mode': 'offline', 'network_requests_performed': 0,
              'sources': list(sources.values()), 'bindings': bindings, 'jobs': results,
              'coverage': checked_coverage, 'claims': checked_claims, 'unused_source_pointers': unused,
              'execution_gates': [], 'source_authenticity_verified': False,
              'free_form_commentary_verified': False,
              'limits': ['COMPUTED does not validate nested evidence states or natural-language interpretation.',
                         'Only declared claims and requirements are checked; omissions from the plan remain possible.',
                         'Custom algorithms and external acquisitions require separately retained evidence.']}
    artifacts['result.json'] = encode(result)
    artifacts['report.md'] = render(result, reports)
    artifacts['receipt.json'] = encode({'schema_version': 1, 'workflow_version': VERSION,
                                      'implementation_sha256': implementation_hash(),
                                      'plan_sha256': sha(raw),
                                      'artifacts': {k: sha(v) for k, v in sorted(artifacts.items())}})
    return artifacts


def _write_new(root, name, raw):
    path = research_contracts.source_path(root, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as handle:
        handle.write(raw)


def run(plan, output, preserve_partial=False):
    plan, output = report_facts.local_path(plan), report_facts.local_path(output)
    require(not output.is_relative_to(ROOT) and not output.exists(), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    writer = None
    if preserve_partial:
        output.mkdir()
        writer = lambda name, raw: _write_new(output, name, raw)
    artifacts = build(plan.read_bytes(), lambda name: research_contracts.source_path(plan.parent, name).read_bytes(),
                      artifact_writer=writer)
    if not preserve_partial:
        output.mkdir()
        for name, raw in artifacts.items():
            _write_new(output, name, raw)
    return read_result(artifacts['result.json'])


def verify(directory):
    directory = report_facts.local_path(directory)
    receipt = report_facts.strict_json((directory / 'receipt.json').read_bytes())
    require(receipt.get('workflow_version') == VERSION and
            receipt.get('implementation_sha256') == implementation_hash(), 'WORKFLOW_IMPLEMENTATION_MISMATCH')
    expected = receipt['artifacts']
    require(isinstance(expected, dict), 'ARTIFACT_MANIFEST_REQUIRED')
    for name, digest in expected.items():
        require(sha(research_contracts.source_path(directory, name).read_bytes()) == digest, 'ARTIFACT_HASH_MISMATCH')
    raw = (directory / 'plan.json').read_bytes()
    require(sha(raw) == receipt['plan_sha256'], 'PLAN_HASH_MISMATCH')
    rebuilt = build(raw, lambda name: research_contracts.source_path(directory / 'sources', name).read_bytes())
    require(set(expected) == set(rebuilt) - {'receipt.json'}, 'ARTIFACT_SET_MISMATCH')
    # Runtime metadata is observational. Replay compares numerical outputs with
    # workbench tolerances; verify retained quant artifacts with their own runner.
    original_result = read_result((directory / 'result.json').read_bytes())
    new_result = read_result(rebuilt['result.json'])
    def exact_metadata(result):
        view = copy.deepcopy(result)
        view['claims'] = None  # Separately regenerated from retained job values.
        for job in view['jobs']:
            if job['operation'] in quant_workbench.OPERATIONS:
                job['result'] = None
                job['nested_states'] = None
        return view
    require(encode(exact_metadata(original_result)) == encode(exact_metadata(new_result)),
            'WORKFLOW_METADATA_REPLAY_MISMATCH')
    plan = report_facts.strict_json(raw)
    require(encode(original_result['claims']) == encode(claims(plan.get('claims', []),
            {j['id']: j for j in original_result['jobs']})), 'RETAINED_CLAIM_BINDING_MISMATCH')
    for name, content in rebuilt.items():
        if name not in ('result.json', 'report.md', 'receipt.json') and '/quant/' not in name:
            require((directory / name).read_bytes() == content, 'RETAINED_INPUT_BINDING_MISMATCH')
    for index, job in enumerate(original_result['jobs']):
        require(encode(job['nested_states']) == encode(list(nested_states(job.get('result')))),
                'NESTED_STATE_BINDING_MISMATCH')
        if job['operation'] in quant_workbench.OPERATIONS:
            require(not quant_workbench.differences(job.get('result'), new_result['jobs'][index].get('result')),
                    'WORKFLOW_REPLAY_MISMATCH')
        if job['operation'] in ('report.quant', 'report.public_vqm'):
            require(encode(job) == encode(new_result['jobs'][index]), 'EXACT_PROJECTION_BINDING_MISMATCH')
        quant = directory / f'jobs/{index:04d}/quant'
        if quant.is_dir():
            quant_report.verify(quant)
            require((quant / 'request.json').read_bytes() == rebuilt[f'jobs/{index:04d}/quant/request.json'],
                    'QUANT_REQUEST_BINDING_MISMATCH')
            bundle = report_facts.strict_json((quant / 'bundle.json').read_bytes())
            actual = bundle['result']['results'][0]
            fields = ('status', 'result', 'reason')
            require(encode({key: actual.get(key) for key in fields}) ==
                    encode({key: job.get(key) for key in fields}), 'QUANT_RESULT_BINDING_MISMATCH')
    # Verify prose from retained values, not a tolerance-rounded re-computation.
    reports = {}
    for index, job in enumerate(original_result['jobs']):
        quant = directory / f'jobs/{index:04d}/quant/report.md'
        if quant.is_file():
            reports[job['id']] = quant.read_text(encoding='utf-8')
        elif job['operation'] in ('report.quant', 'report.public_vqm') and job['status'] == 'COMPUTED':
            reports[job['id']] = report_facts.markdown(job['result']['facts'])
    require((directory / 'report.md').read_bytes() == render(original_result, reports), 'CANONICAL_REPORT_MISMATCH')
    return {'status': 'WORKFLOW_REPLAY_AND_REPORT_MATCH', 'jobs_verified': len(original_result['jobs']),
            'research_status': original_result['status'], 'execution_gates': [],
            'limits': 'Consistency only; source truth, operation selection and free-form commentary are not validated.'}


def summarize(directory):
    """Project retained values only after the complete run and report verify."""
    directory = report_facts.local_path(directory)
    verification = verify(directory)
    return _summarize_verified(directory, verification)


def _summarize_verified(directory, verification):
    """Internal projection shared with execute after its actual verification."""
    raw = (directory / 'result.json').read_bytes()
    result = read_result(raw)
    jobs = []
    for index, job in enumerate(result['jobs']):
        value = job.get('result')
        jobs.append({'id': job['id'], 'operation': job['operation'], 'status': job['status'],
                     'reason': job.get('reason'), 'result_pointer': f'/jobs/{index}/result',
                     'nested_states': copy.deepcopy(job['nested_states']),
                     'null_result_pointers': [p for p in research_contracts.leaves(value)
                                              if research_contracts.pointer(value, p) is None]})
    return {'schema_version': 1, 'verification': verification, 'result_sha256': sha(raw),
            'status': result['status'], 'contract': copy.deepcopy(result['contract']),
            'coverage': copy.deepcopy(result['coverage']), 'claims': copy.deepcopy(result['claims']),
            'sources': copy.deepcopy(result['sources']), 'bindings': copy.deepcopy(result['bindings']),
            'unused_source_pointers': copy.deepcopy(result['unused_source_pointers']), 'jobs': jobs,
            'execution_gates': [], 'free_form_commentary_verified': False,
            'limits': ['Values are copied from the verified retained result without rounding or paraphrase.',
                       'Nested-state and null pointers are relative to each job result, not inferred meanings.',
                       'Only declared claims are projected; the complete results and canonical report remain authoritative.',
                       'Consistency does not validate source truth, omitted tasks, operation choice or model adherence.']}


def execute(request, output, request_role, source_roles=None):
    """Run the existing protected stages once and retain their actual outcomes.

    The root must be new and outside the skill. A rejected request leaves a
    checkpoint instead of silently disappearing. Runtime failure never turns
    retained historical artifacts or a partially computed job into completion.
    """
    import answer_facts
    import evidence_provenance
    request, output = report_facts.local_path(request), report_facts.local_path(output)
    require(not output.is_relative_to(ROOT) and not output.exists(), 'NEW_PRIVATE_OUTPUT_REQUIRED')
    output.mkdir()
    stages = {name: {'status': 'NOT_STARTED'} for name in
              ('prepare', 'run', 'verification', 'summary', 'answer_facts')}
    raw, original, result, verification = None, None, None, None
    failure = None
    stage = 'prepare'
    try:
        stages[stage]['status'] = 'STARTED'
        raw = request.read_bytes()
        _write_new(output, 'original-request.json', raw)
        original = report_facts.strict_json(raw)
        require(DEPENDENCY_FAILURE is None, 'DEPENDENCY_UNAVAILABLE')
        def retain_attempt(path, index, source_raw):
            # Only bytes already requested by the existing validated local
            # resolver are copied. No recursive directory or extra reads.
            _write_new(output, f'attempted-sources/{index:04d}/source.json', source_raw)
            _write_new(output, f'attempted-sources/{index:04d}/identity.json', encode({
                'job_index': index, 'declared_source_path': path, 'sha256': sha(source_raw),
                'status': 'READ_BYTES_NOT_YET_VALIDATED'}))
        # Existing prepare validates source identities, exact roles and full
        # object selections. Its reader never performs network acquisition.
        prepare(request, output / 'prepare', request_role, source_roles,
                attempted_source_writer=retain_attempt)
        require((output / 'prepare/original-request.json').read_bytes() == raw,
                'ORIGINAL_REQUEST_CHANGED_DURING_PREPARATION')
        stages[stage]['status'] = 'COMPLETED'
        stage = 'run'
        stages[stage]['status'] = 'STARTED'
        result = run(output / 'prepare/plan.json', output / 'run', preserve_partial=True)
        stages[stage] = {'status': 'COMPLETED', 'research_status': result['status']}
        stage = 'verification'
        stages[stage]['status'] = 'STARTED'
        verification = verify(output / 'run')
        _write_new(output, 'verification/result.json', encode(verification))
        stages[stage]['status'] = 'COMPLETED'
        stage = 'summary'
        stages[stage]['status'] = 'STARTED'
        _write_new(output, 'summary/result.json', encode(_summarize_verified(output / 'run', verification)))
        stages[stage]['status'] = 'COMPLETED'
        stage = 'answer_facts'
        stages[stage]['status'] = 'STARTED'
        result_raw = (output / 'run/result.json').read_bytes()
        facts = answer_facts._project(read_result(result_raw), sha(result_raw), artifact='run/result.json')
        facts['verification'] = verification
        _write_new(output, 'answer-facts.json', encode(facts))
        _write_new(output, 'answer-facts.txt', answer_facts.text_projection(facts).encode('utf-8'))
        stages[stage]['status'] = 'COMPLETED'
    except Exception as exc:
        # Preserve unexpected runtime/dependency failures too. KeyboardInterrupt
        # and process termination are not caught or misrepresented as outcomes.
        failure = {'stage': stage, 'type': type(exc).__name__, 'reason': str(exc)}
        if DEPENDENCY_FAILURE is not None:
            failure.update(category='DEPENDENCY_UNAVAILABLE', dependency=DEPENDENCY_FAILURE)
        stages[stage] = {'status': 'FAILED', 'error': failure}
        _write_new(output, 'failure.json', encode(failure))
    requested_jobs = original.get('jobs', []) if isinstance(original, dict) else []
    if not isinstance(requested_jobs, list):
        requested_jobs = []
    jobs = []
    retained_jobs = result.get('jobs', []) if isinstance(result, dict) else []
    for index, requested in enumerate(requested_jobs):
        if not isinstance(requested, dict):
            requested = {}
        actual = retained_jobs[index] if index < len(retained_jobs) else None
        partial = output / f'run/jobs/{index:04d}/quant/bundle.json'
        partial_available = actual is None and partial.is_file()
        status = actual['status'] if actual else 'NOT_EXECUTED_OR_UNRESOLVED'
        if partial_available:
            status = 'PARTIAL_ARTIFACTS_UNVERIFIED'
        observed = status == 'COMPUTED'
        evidence = evidence_provenance.classify_evidence({
            'origin': 'current', 'kind': 'invocation', 'execution_observed': observed,
            'artifacts_available': actual is not None or partial_available,
            'verification_passed': verification is not None})
        jobs.append({'job_index': index, 'id': requested.get('id'), 'operation': requested.get('operation'),
                     'computation_status': status,
                     'reason': actual.get('reason') if actual else 'No complete retained job outcome is available.',
                     'result_pointer': f'/jobs/{index}/result' if actual else None,
                     'nested_states': copy.deepcopy(actual.get('nested_states', [])) if actual else [],
                     'partial_artifact': partial.relative_to(output).as_posix() if partial_available else None,
                     'evidence': evidence,
                     'financial_conclusion_validated': False})
    diagnostics = (result is None or result.get('status') != 'COMPUTED' or
                   any(j['computation_status'] != 'COMPUTED' for j in jobs))
    completion = {'schema_version': 1, 'workflow_version': VERSION,
                  'status': 'INCOMPLETE' if failure else
                            'COMPLETED_WITH_DIAGNOSTICS' if diagnostics else 'COMPLETED_LOCAL_WORKFLOW',
                  'request_sha256': sha(raw) if raw is not None else None,
                  'request_hash_scope': 'exact_original_request_bytes',
                  'stages': stages, 'jobs': jobs,
                  'coverage': copy.deepcopy(result.get('coverage', [])) if result else [],
                  'failure': failure, 'network_requests_performed': 0,
                  'dependency_installs_performed': 0, 'host_download_observed': False,
                  'whole_answer_pass': False, 'execution_authorized': False,
                  'limits': ['Completion describes only these local stages and declared jobs, not full prompt understanding.',
                             'Nested invalid, ambiguous or null outcomes remain unresolved even when computation and replay succeed.',
                             'No source truth, arbitrary model prose, investment correctness or external file delivery was verified.']}
    _write_new(output, 'completion.json', encode(completion))
    inventory = [{'path': path.relative_to(output).as_posix(), 'bytes': path.stat().st_size,
                  'sha256': sha(path.read_bytes())} for path in sorted(output.rglob('*')) if path.is_file()]
    _write_new(output, 'export-inventory.json', encode({
        'schema_version': 1, 'artifact_root': '.', 'artifacts': inventory,
        'inventory_excludes_itself': True, 'location': 'local_filesystem',
        'host_download_observed': False, 'remote_upload_observed': False}))
    return completion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('schema', 'prepare', 'run', 'verify', 'summary', 'execute'))
    parser.add_argument('input', nargs='?')
    parser.add_argument('--private-output-dir')
    parser.add_argument('--request-role')
    parser.add_argument('--source-role', nargs=2, action='append', metavar=('PATH', 'ROLE'))
    args = parser.parse_args()
    try:
        if args.command != 'execute':
            require(DEPENDENCY_FAILURE is None, 'DEPENDENCY_UNAVAILABLE')
        if args.command not in ('prepare', 'execute'):
            require(args.request_role is None and args.source_role is None, 'PREPARE_OPTIONS_ONLY')
        if args.command == 'schema':
            print(encode(catalog()).decode(), end='')
        elif args.command in ('prepare', 'execute'):
            require(args.input and args.private_output_dir, 'REQUEST_AND_OUTPUT_REQUIRED')
            roles = args.source_role or []
            require(len(dict(roles)) == len(roles), 'DUPLICATE_SOURCE_ROLES')
            if args.command == 'prepare':
                prepare(args.input, args.private_output_dir, args.request_role, dict(roles))
                print('PREPARED')
            else:
                result = execute(args.input, args.private_output_dir, args.request_role, dict(roles))
                print(result['status'])
                if result['status'] != 'COMPLETED_LOCAL_WORKFLOW':
                    parser.exit(2)
        elif args.command == 'run':
            require(args.input and args.private_output_dir, 'PLAN_AND_OUTPUT_REQUIRED')
            print(run(args.input, args.private_output_dir)['status'])
        else:
            require(args.input and not args.private_output_dir, 'DIRECTORY_REQUIRED')
            if args.command == 'summary':
                print(encode(summarize(args.input)).decode(), end='')
            else:
                print(verify(args.input)['status'])
    except (ValueError, KeyError, TypeError, IndexError, OSError, OverflowError):
        parser.exit(2, 'Invalid research plan/export. Inspect local schema, source hashes and output path; no source values printed.\n')


if __name__ == '__main__':
    main()
