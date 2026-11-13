"""Source-bound projection of pure institutional plans and study evaluations.

Preserves separate usefulness/return inclusion and all native limitations.
No capture, journal, recovery, acquisition, scheduler or account action runs.
"""
from copy import deepcopy
import hashlib
import json
import re

import institutional_research
from source_claims import Corpus
from source_lineage import at
from supplied_research import encode

METHOD = 'institutional-report-1'
OPERATIONS = {'plan': institutional_research.plan, 'evaluate': institutional_research.evaluate}
MAX_DOCUMENTS = 32


def require(condition, code):
    if not condition:
        raise ValueError(code)


def fields(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys), 'EXACT_INSTITUTIONAL_REPORT_FIELDS_REQUIRED')


def render(rows):
    lines = ['# Source-bound institutional research', '',
             'Native plans and evaluations of the selected original documents follow. '
             'Declarations do not establish actual prospective operation, source authenticity '
             'or independent institutional acceptance.', '',
             'Usefulness and returns have separate inclusion flags, exclusion reasons and '
             'aggregate denominators. Eligibility for one metric does not imply eligibility '
             'for the other. No shared inclusion label replaces those fields.', '']
    for row in rows:
        lines.extend(['## Document ' + row['id'], '',
                      'Original binding: ' + encode(row['source_binding']).decode().strip(), ''])
        for operation, outcome in row['operations'].items():
            lines.extend(['### ' + operation, '', 'Operation status: ' + outcome['status'], ''])
            if outcome['status'] == 'FAILED':
                lines.extend(['Retained error:', '```json', encode(outcome['error']).decode().strip(), '```', ''])
                continue
            projection = {key: value for key, value in outcome['result'].items() if key != 'evidence'}
            lines.extend(['```json', encode(projection).decode().strip(), '```',
                          'The complete result retains the normalized evidence history.', ''])
    lines.extend(['These findings do not establish profitability, causal usefulness, '
                  'live enforcement or execution authority. No real workflow was started.', ''])
    return '\n'.join(lines)


def analyze(request, manifest_path, expected_manifest_sha256, source_root=None):
    """Run plan/evaluate on whole original JSON objects; no result overrides."""
    fields(request, ('documents', 'operations'))
    documents, operations = request['documents'], request['operations']
    require(isinstance(documents, list) and 0 < len(documents) <= MAX_DOCUMENTS,
            'BOUNDED_INSTITUTIONAL_DOCUMENTS_REQUIRED')
    require(isinstance(operations, list) and 0 < len(operations) <= len(OPERATIONS)
            and all(isinstance(op, str) and op in OPERATIONS for op in operations)
            and len(set(operations)) == len(operations), 'UNIQUE_PURE_INSTITUTIONAL_OPERATIONS_REQUIRED')
    corpus = Corpus(manifest_path, expected_manifest_sha256, source_root)
    selected, seen = [], set()
    for item in documents:
        fields(item, ('id', 'source_ref'))
        identifier = item['id']
        require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}', identifier)
                and identifier not in seen, 'UNIQUE_INSTITUTIONAL_DOCUMENT_IDS_REQUIRED')
        seen.add(identifier)
        ref = item['source_ref']; fields(ref, ('source_id', 'pointer'))
        require(isinstance(ref['source_id'], str) and ref['source_id'] in corpus.sources,
                'REFERENCE_OUTSIDE_PINNED_CORPUS')
        source = corpus.sources[ref['source_id']]
        require(source['format'] == 'json', 'ORIGINAL_JSON_INSTITUTIONAL_DOCUMENT_REQUIRED')
        # Corpus already validated exact bytes and duplicate/nonfinite literals.
        # Standard decoding matches the native CLI and its input/workflow hashes.
        document = at(json.loads(source['raw']), ref['pointer'])
        require(isinstance(document, dict) and {'schema_version', 'as_of', 'records'} <= set(document),
                'WHOLE_INSTITUTIONAL_DOCUMENT_REQUIRED')
        selected.append((identifier, deepcopy(ref), source['sha256'], document))
    rows, failures = [], 0
    for identifier, ref, sha, document in selected:
        results = {}
        for operation in operations:
            try:
                native = OPERATIONS[operation](deepcopy(document))
                results[operation] = {'status': 'EXECUTED', 'result': native}
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                failures += 1
                results[operation] = {'status': 'FAILED', 'error': {
                    'type': type(error).__name__, 'message': str(error)}}
        rows.append({'id': identifier, 'source_binding': {**ref, 'source_sha256': sha},
                     'operations': results})
    text = render(rows)
    return {'method': METHOD,
            'status': 'PARTIAL_RETAINED_FAILURES' if failures else 'EXECUTED_SELECTED_OPERATIONS',
            'failed_operations': failures, 'rows': rows,
            'source_inventory': [{'source_id': sid, 'sha256': source['sha256']}
                                 for sid, source in corpus.sources.items()],
            'manifest_sha256': expected_manifest_sha256,
            'report': {'text': text, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                       'whole_report_semantic_pass': False},
            'limits': ['Only selected original documents and pure plan/evaluate operations were analyzed.',
                       'Native per-case flags, exclusions, roster gaps and aggregate denominators remain distinct.',
                       'Failed operations are retained, not completed calculations.',
                       'No original journal authenticity, actual elapsed operation, causal attribution or profitability is established.',
                       'Source authenticity, arbitrary prose and request completeness are not verified.'],
            'execution_authorized': False, 'source_authenticity_verified': False,
            'whole_report_semantic_pass': False}
