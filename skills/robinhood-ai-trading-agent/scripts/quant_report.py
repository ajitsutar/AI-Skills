"""Run retained offline quant requests and export a canonical, replayable report.

Accepts the existing workbench document. A job may instead supply inputs_source
{path, sha256, pointer}; its entire input object is selected from that local JSON
file without overrides. Operations are always explicit and allowlisted. This
module does not infer algorithms, measurements, trading permissions or outcomes.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import inspect
import json
from pathlib import Path
import re

import quant_workbench as workbench
import report_facts
from quant_common import digest, require

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'quant-report-1'


def replay_tolerances():
    parameters = inspect.signature(workbench.differences).parameters
    return {name: parameters[name].default for name in ('absolute', 'relative')}


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def resolve_request(raw, source_reader):
    """Retain source bytes; JSON pointers are selectors, never expressions."""
    document = report_facts.strict_json(raw)
    require(isinstance(document, dict), 'REQUEST_OBJECT_REQUIRED')
    require(document.get('schema_version') == 1, 'WORKBENCH_SCHEMA')
    require(isinstance(document.get('contract'), dict), 'CONTRACT_REQUIRED')
    jobs = document.get('jobs')
    require(isinstance(jobs, list) and jobs, 'JOBS_REQUIRED')
    require(all(isinstance(j, dict) and isinstance(j.get('id'), str) and j['id'].strip()
                for j in jobs), 'JOB_ID_REQUIRED')
    require(len({j['id'] for j in jobs}) == len(jobs), 'UNIQUE_JOB_IDS')
    materialized = copy.deepcopy(document)
    sources, artifacts = [], {'request.json': raw}
    for index, job in enumerate(materialized['jobs']):
        operation = job.get('operation')
        require(isinstance(operation, str) and operation in workbench.OPERATIONS,
                'OPERATION_NOT_ALLOWED')
        require(('inputs' in job) != ('inputs_source' in job), 'ONE_INPUT_SOURCE_REQUIRED')
        if 'inputs_source' in job:
            ref = job.pop('inputs_source')
            require(isinstance(ref, dict) and set(ref) == {'path', 'sha256', 'pointer'},
                    'INPUT_SOURCE_FIELDS')
            require(isinstance(ref['path'], str) and ref['path'], 'SOURCE_PATH_REQUIRED')
            require(isinstance(ref['sha256'], str) and re.fullmatch('[0-9a-f]{64}', ref['sha256']),
                    'SOURCE_SHA256_REQUIRED')
            require(isinstance(ref['pointer'], str), 'JSON_POINTER_REQUIRED')
            source_raw = source_reader(ref['path'], index)
            require(sha(source_raw) == ref['sha256'], 'SOURCE_HASH_MISMATCH')
            job['inputs'] = copy.deepcopy(report_facts.pointer(report_facts.strict_json(source_raw), ref['pointer']))
            name = f'source-{index:04d}.json'
            artifacts[name] = source_raw
            sources.append({'job_index': index, 'artifact': name, **ref})
        require(isinstance(job.get('inputs'), dict), 'JOB_INPUT_OBJECT_REQUIRED')
    return materialized, sources, artifacts


def prepare_request(document):
    """Bind supported defaults while preserving invalid jobs for helper rejection."""
    prepared = copy.deepcopy(document)
    bindings = []
    for index, job in enumerate(prepared['jobs']):
        supplied = copy.deepcopy(job['inputs'])
        entry = {'job_index': index, 'id': job['id'], 'operation': job['operation'],
                 'supplied_inputs_sha256': digest(supplied)}
        try:
            resolved = workbench.resolved_inputs(job['operation'], supplied)
            job['inputs'] = resolved
            entry.update(status='BOUND', resolved_inputs_sha256=digest(resolved),
                         defaults_used={k: v for k, v in resolved.items() if k not in supplied})
        except (ValueError, KeyError, TypeError) as exc:
            entry.update(status='INVALID_HELPER_INPUT', reason=type(exc).__name__ + ':' + str(exc))
        bindings.append(entry)
    return prepared, bindings


def summary(bundle):
    jobs = []
    for index, job in enumerate(bundle['result']['results']):
        function = workbench.OPERATIONS[job['operation']]
        jobs.append({'job_index': index, 'id': job['id'], 'operation': job['operation'],
                     'implementation': function.__module__ + '.' + function.__name__,
                     'computation_status': job['status'],
                     'helper_outcome': job.get('result', {}).get('status'),
                     'result_pointer': '/result/results/' + str(index)})
    computed = sum(j['computation_status'] == 'COMPUTED' for j in jobs)
    return {'status': 'COMPUTED' if computed == len(jobs) else 'PARTIAL_ANALYSIS' if computed else 'NO_COMPUTED_JOBS',
            'computed_jobs': computed, 'total_jobs': len(jobs), 'jobs': jobs,
            'meaning': 'Status counts helper computations, not valid observations, feasible portfolios, investment conclusions or external actions.'}


def markdown(analysis, facts, bindings):
    def cell(value):
        return html.escape(json.dumps(value, ensure_ascii=False, sort_keys=True)).replace('|', '&#124;').replace('`', '&#96;').replace('[', '&#91;').replace(']', '&#93;')
    rows = ['Offline quant run and report', '',
            'Analysis status: ' + analysis['status'], '', analysis['meaning'], '',
            '| Job | Operation | Fixed implementation | Computation | Helper outcome |',
            '|---|---|---|---|---|']
    for job in analysis['jobs']:
        rows.append('| ' + ' | '.join(cell(job[k]) for k in
                    ('id', 'operation', 'implementation', 'computation_status', 'helper_outcome')) + ' |')
    rows.extend(['', 'Parameter binding: supplied fields are preserved; only the installed helper defaults fill omitted optional fields. Required measurements and parameters are never invented.', ''])
    for item in bindings:
        rows.append('- ' + cell(item))
    rows.extend(['', 'The bundle was computed locally from prepared.json. Facts below project its exact values and retain unknown units/bases. No source observation was authenticated. Input-period metrics do not inherit the contract horizon as a measurement period.', '',
                 'Verification compares the report exactly and replays numerical helper results with tolerances: ' + cell(replay_tolerances()) + '.', '',
                 report_facts.markdown(facts)])
    return '\n'.join(rows)


def build(raw, source_reader, include_source_text=False):
    materialized, sources, artifacts = resolve_request(raw, source_reader)
    prepared, bindings = prepare_request(materialized)
    bundle = workbench.freeze(prepared)
    # Binding is checked against the actual executed interface, including defaults.
    for binding, result in zip(bindings, bundle['result']['results']):
        if result['status'] == 'COMPUTED':
            require(binding.get('resolved_inputs_sha256') == result['resolved_inputs_sha256'],
                    'EXECUTED_INPUT_BINDING_MISMATCH')
    bundle_raw = encoded(bundle)
    facts = report_facts.project(bundle_raw, 'quant', include_source_text=include_source_text)
    analysis = summary(bundle)
    artifacts.update({'prepared.json': encoded(prepared), 'bindings.json': encoded(bindings),
                      'bundle.json': bundle_raw, 'facts.json': encoded(facts),
                      'analysis.json': encoded(analysis),
                      'report.md': markdown(analysis, facts, bindings).encode('utf-8')})
    receipt = {'schema_version': 1, 'workflow_version': VERSION,
               'workflow_code_sha256': report_facts.code_hash('quant_report.py'),
               'implementation_sha256': workbench.implementation_hash(),
               'report_adapter_sha256': report_facts.code_hash('report_facts.py'),
               'request_sha256': sha(raw), 'materialized_input_sha256': digest(materialized),
               'prepared_input_sha256': digest(prepared), 'contract_sha256': digest(prepared['contract']),
               'source_bindings': sources, 'include_source_text': include_source_text,
               'analysis_status': analysis['status'],
               'numeric_replay_tolerances': replay_tolerances(), 'report_comparison': 'EXACT_BYTES',
               'artifacts': {name: sha(content) for name, content in sorted(artifacts.items())},
               'limits': ['Hashes and replay check consistency, not source authenticity or external model obedience.',
                          'Explicit input operations and parameters are retained; no natural-language algorithm inference.',
                          'No broker, network, scheduling or trading execution semantics.']}
    artifacts['receipt.json'] = encoded(receipt)
    return artifacts


def run(source, output, include_source_text=False):
    source, output = report_facts.local_path(source), report_facts.local_path(output)
    require(not output.is_relative_to(ROOT), 'OUTPUT_OUTSIDE_SKILL_REQUIRED')
    require(not output.exists(), 'NEW_OUTPUT_DIRECTORY_REQUIRED')

    def read_source(path, index):
        # Test the literal path before joining: joining can hide a URL/UNC prefix.
        report_facts.local_path(path)
        return report_facts.local_path(source.parent / path).read_bytes()

    artifacts = build(source.read_bytes(), read_source, include_source_text)
    output.mkdir()  # Exclusive, after all analysis: never overwrite a prior run.
    for name, content in artifacts.items():
        with (output / name).open('xb') as handle:
            handle.write(content)
    return report_facts.strict_json(artifacts['receipt.json'])


def verify(directory):
    directory = report_facts.local_path(directory)
    receipt = report_facts.strict_json((directory / 'receipt.json').read_bytes())
    require(receipt.get('workflow_version') == VERSION, 'WORKFLOW_VERSION_MISMATCH')
    require(receipt.get('workflow_code_sha256') == report_facts.code_hash('quant_report.py'), 'WORKFLOW_CODE_MISMATCH')
    require(receipt.get('implementation_sha256') == workbench.implementation_hash(), 'IMPLEMENTATION_MISMATCH')
    require(receipt.get('report_adapter_sha256') == report_facts.code_hash('report_facts.py'), 'REPORT_ADAPTER_MISMATCH')
    require(receipt.get('numeric_replay_tolerances') == replay_tolerances()
            and receipt.get('report_comparison') == 'EXACT_BYTES', 'COMPARISON_CONTRACT_MISMATCH')
    expected = receipt.get('artifacts')
    require(isinstance(expected, dict), 'ARTIFACT_MANIFEST_REQUIRED')
    for name, expected_hash in expected.items():
        require(name in {'request.json', 'prepared.json', 'bindings.json', 'bundle.json', 'facts.json', 'analysis.json', 'report.md'}
                or re.fullmatch(r'source-\d{4,}\.json', name), 'ARTIFACT_NAME_INVALID')
        require(sha((directory / name).read_bytes()) == expected_hash, 'ARTIFACT_HASH_MISMATCH')
    raw = (directory / 'request.json').read_bytes()
    materialized, sources, source_artifacts = resolve_request(raw, lambda path, index: (directory / f'source-{index:04d}.json').read_bytes())
    prepared, bindings = prepare_request(materialized)
    require(set(expected) == set(source_artifacts) | {'prepared.json', 'bindings.json', 'bundle.json', 'facts.json', 'analysis.json', 'report.md'}, 'ARTIFACT_SET_MISMATCH')
    require(receipt.get('request_sha256') == sha(raw) and receipt.get('source_bindings') == sources, 'REQUEST_BINDING_MISMATCH')
    require(receipt.get('materialized_input_sha256') == digest(materialized) and receipt.get('prepared_input_sha256') == digest(prepared)
            and receipt.get('contract_sha256') == digest(prepared['contract']), 'INPUT_BINDING_MISMATCH')
    require((directory / 'prepared.json').read_bytes() == encoded(prepared)
            and (directory / 'bindings.json').read_bytes() == encoded(bindings), 'PREPARATION_MISMATCH')
    bundle_raw = (directory / 'bundle.json').read_bytes()
    bundle = report_facts.strict_json(bundle_raw)
    require(bundle['input'] == prepared, 'BUNDLE_INPUT_MISMATCH')
    replay = workbench.verify(bundle)
    require(type(receipt.get('include_source_text')) is bool, 'SOURCE_TEXT_OPTION_REQUIRED')
    facts = report_facts.project(bundle_raw, 'quant', include_source_text=receipt['include_source_text'])
    analysis = summary(bundle)
    require(receipt.get('analysis_status') == analysis['status'], 'ANALYSIS_STATUS_MISMATCH')
    for name, content in {'facts.json': encoded(facts), 'analysis.json': encoded(analysis),
                          'report.md': markdown(analysis, facts, bindings).encode('utf-8')}.items():
        require((directory / name).read_bytes() == content, 'CANONICAL_REPORT_MISMATCH')
    return {'status': 'REPLAY_AND_REPORT_MATCH', 'analysis_status': analysis['status'],
            'jobs_verified': replay['jobs_verified'], 'request_sha256': sha(raw),
            'numeric_replay_tolerances': replay_tolerances(), 'report_comparison': 'EXACT_BYTES',
            'limitation': 'Consistency and helper replay only; no observation authentication or model-behavior guarantee.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('run', 'verify'))
    parser.add_argument('input')
    parser.add_argument('--private-output-dir')
    parser.add_argument('--include-source-text', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'run':
            require(args.private_output_dir is not None, 'PRIVATE_OUTPUT_DIRECTORY_REQUIRED')
            run(args.input, args.private_output_dir, args.include_source_text)
        else:
            require(args.private_output_dir is None and not args.include_source_text, 'VERIFY_OPTIONS_INVALID')
            result = verify(args.input)
            print(result['status'])  # No private values or paths on stdout.
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, OSError):
        parser.exit(2, 'Invalid analysis or export: inspect the retained local input/schema, source hashes, dependencies and new output path. No source values were printed.\n')


if __name__ == '__main__':
    main()
