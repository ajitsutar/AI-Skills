"""Source-bound retained-text parsing with explicit original clock bindings.

Constructs the installed parser envelope without changing original files or
inventing observation metadata. No acquisition, network or account action runs.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import PurePosixPath

import market_sources
import source_metadata_fitness
from source_claims import Corpus
from source_lineage import at, parse
from supplied_research import encode, relative

METHOD = 'market-sources-report-1'
MAX_JOBS = 64


def require(condition, code):
    if not condition:
        raise ValueError(code)


def binding(corpus, ref):
    require(isinstance(ref, dict) and set(ref) == {'source_id', 'pointer'}, 'ORIGINAL_REFERENCE_REQUIRED')
    require(isinstance(ref['source_id'], str) and ref['source_id'] in corpus.sources, 'REFERENCE_OUTSIDE_PINNED_CORPUS')
    source = corpus.sources[ref['source_id']]
    require(source['format'] == 'json', 'ORIGINAL_JSON_REFERENCE_REQUIRED')
    value = at(json.loads(source['raw']), ref['pointer'])
    return deepcopy(value), {'source_ref': deepcopy(ref), 'source_sha256': source['sha256']}, source


def clock(value):
    require(isinstance(value, str) and 'T' in value, 'EXACT_ORIGINAL_AS_OF_REQUIRED')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('EXACT_ORIGINAL_AS_OF_REQUIRED') from error
    require(result.tzinfo is not None, 'TIMEZONE_AWARE_ORIGINAL_AS_OF_REQUIRED')
    return result


def prepared(job, origin, corpus, fallback_clock, fallback_binding, row):
    require(isinstance(job, dict), 'ORIGINAL_PARSE_JOB_OBJECT_REQUIRED')
    native = deepcopy(job)
    if 'schema_version' in native:
        require(type(native['schema_version']) is int and native['schema_version'] == 1,
                'UNSUPPORTED_ORIGINAL_SCHEMA_VERSION')
        schema_origin = 'ORIGINAL_JOB'
    else:
        native['schema_version'] = 1
        schema_origin = 'INSTALLED_PARSER_INTERFACE_CONTRACT'
    if 'as_of' in native:
        original_clock = clock(native['as_of'])
        if fallback_binding is not None:
            require(original_clock == clock(fallback_clock), 'CONFLICTING_ORIGINAL_AS_OF_REFERENCES')
        clock_binding = {'origin': 'ORIGINAL_JOB', 'value': native['as_of']}
    else:
        require(fallback_binding is not None, 'ORIGINAL_AS_OF_REFERENCE_REQUIRED')
        clock(fallback_clock)
        native['as_of'] = fallback_clock
        clock_binding = {'origin': 'BOUND_CORPUS_CLOCK', 'value': fallback_clock, **fallback_binding}
    row['envelope_construction'] = {'schema_version': native['schema_version'],
        'schema_version_origin': schema_origin, 'as_of_binding': clock_binding,
        'source_observation_metadata_inferred': False}
    name = relative(job.get('text_file'))
    raw_path = (PurePosixPath(origin['path']).parent / name).as_posix()
    matches = [(sid, source) for sid, source in corpus.sources.items() if source['path'] == raw_path]
    require(len(matches) == 1, 'UNIQUE_ORIGINAL_RAW_SOURCE_REQUIRED')
    sid, raw_source = matches[0]
    raw = raw_source['raw']
    require(len(raw) <= market_sources.MAX_BYTES, 'RAW_SOURCE_TOO_LARGE')
    decoded = raw.decode('utf-8-sig')
    row['raw_source_binding'] = {'source_id': sid, 'path': raw_path, 'sha256': raw_source['sha256'],
        'decoded_content_sha256': hashlib.sha256(raw).hexdigest(),
        'decoding': 'UTF8_SIG_NATIVE_PLAIN_FILE_CONVENTION'}
    if 'text' in native:
        require(native['text'] == decoded, 'ORIGINAL_INLINE_TEXT_CONFLICTS_WITH_RAW_SOURCE')
    native['text'] = decoded
    require(isinstance(native.get('source'), dict), 'ORIGINAL_SOURCE_OBJECT_REQUIRED')
    for key in ('raw_sha256', 'decoded_content_sha256'):
        value = hashlib.sha256(raw).hexdigest()
        require(key not in native['source'] or native['source'][key] == value, 'CONFLICTING_ORIGINAL_RAW_HASH')
        native['source'][key] = value
    if native.get('adapter') in ('sec_submissions', 'social_leads'):
        parse(raw)  # Reject duplicate/nonfinite JSON before native standard decode.
        data = json.loads(raw)
        if 'data' in native:
            canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
            require(canonical(native['data']) == canonical(data), 'ORIGINAL_DATA_CONFLICTS_WITH_RAW_SOURCE')
        native['data'] = data
    row['native_input_sha256'] = hashlib.sha256(json.dumps(native, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()
    return native


def render(rows, metadata_fitness):
    parts = ['# Source-bound retained-text parser results', '',
             'Every job in the selected original list is retained. The request cutoff is an '
             'original clock binding, not a source publication or availability claim. '
             'Schema version construction describes the installed interface only.', '']
    for row in rows:
        parts.extend(['## Original job ' + str(row['job_index']), '',
                      '```json', encode(row).decode().rstrip(), '```', ''])
    parts.extend(['## Bound context metadata fitness', '',
                  'This is a bounded metadata-only assessment, not dataset certification or complete request coverage.',
                  '', '```json', encode(metadata_fitness).decode().rstrip(), '```', ''])
    parts.append('EXECUTED means the native parser returned; inspect every record eligibility, '
                 'parse_error and issue. Failed operations and rejected rows are not successful '
                 'extractions. Source authenticity, whole-task completeness and investment '
                 'correctness remain unverified. No external action was performed.\n')
    return '\n'.join(parts)


def analyze(request, manifest_path, expected_manifest_sha256, source_root=None):
    """Bind an entire original job list and optional explicit original cutoff.

    request = {jobs_ref: {source_id, pointer}, as_of_ref?: {source_id, pointer}}
    Each original job supplies text_file relative to its original JSON file.
    No literal override, selected job subset or arbitrary raw path is accepted.
    """
    require(isinstance(request, dict) and 'jobs_ref' in request
            and set(request) <= {'jobs_ref', 'as_of_ref'}, 'EXACT_PARSER_REPORT_REQUEST_REQUIRED')
    corpus = Corpus(manifest_path, expected_manifest_sha256, source_root)
    jobs, jobs_binding, origin = binding(corpus, request['jobs_ref'])
    require(isinstance(jobs, list) and 0 < len(jobs) <= MAX_JOBS, 'COMPLETE_ORIGINAL_PARSE_JOB_LIST_REQUIRED')
    fallback, fallback_binding = None, None
    if 'as_of_ref' in request:
        fallback, fallback_binding, _ = binding(corpus, request['as_of_ref'])
        clock(fallback)
    rows, failures = [], 0
    for index, job in enumerate(jobs):
        row = {'job_index': index, 'original_job': deepcopy(job),
               'job_source_binding': {**jobs_binding, 'list_index': index}}
        try:
            native = prepared(job, origin, corpus, fallback, fallback_binding, row)
            result = market_sources.parse(native)
            row.update(status='EXECUTED', result=result,
                       returned_rows_with_parse_errors=sum(bool(record.get('parse_error')) for record in result['records']))
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            failures += 1
            row.update(status='FAILED', error={'type': type(error).__name__, 'message': str(error)})
        rows.append(row)
    metadata_fitness = source_metadata_fitness.audit_bound_context(corpus, request.get('as_of_ref'))
    text = render(rows, metadata_fitness)
    return {'method': METHOD,
            'status': 'PARTIAL_RETAINED_FAILURES' if failures else 'EXECUTED_ALL_BOUND_PARSE_JOBS',
            'jobs_binding': jobs_binding, 'original_job_count': len(jobs), 'failed_operations': failures,
            'rows': rows, 'metadata_fitness': metadata_fitness, 'manifest_sha256': expected_manifest_sha256,
            'source_inventory': [{'source_id': sid, 'sha256': source['sha256']}
                                 for sid, source in corpus.sources.items()],
            'report': {'text': text, 'sha256': hashlib.sha256(text.encode('utf8')).hexdigest(),
                       'whole_report_semantic_pass': False},
            'limits': ['Every job in this bound list is represented; relevance and whole-request completeness are not certified.',
                       'Only retained plain UTF-8 text/JSON is supported; no acquisition or archive extraction occurs.',
                       'Protocol schema version is not market metadata. Source clocks remain their original declarations.',
                       'Native row errors, exclusions, raw fields and source scope retain their original meaning.',
                       'This parser report does not validate unrelated manual cross-checks or capture/export completeness.'],
            'execution_authorized': False, 'source_authenticity_verified': False,
            'whole_report_semantic_pass': False}
