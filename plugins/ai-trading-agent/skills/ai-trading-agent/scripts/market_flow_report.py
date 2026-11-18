"""Replay original market documents into source-bound metric reports.

This adapter preserves native output roles, unknowns and diagnostics. It does
not authenticate source declarations, grade arbitrary prose or execute trades.
"""
from copy import deepcopy
import hashlib
import json
import re

import market_flow
from source_claims import Corpus
from source_lineage import at
from supplied_research import encode

METHOD = 'market-flow-report-1'
OPERATIONS = {'flow': market_flow.analyze, 'positioning': market_flow.positioning,
              'squeeze': market_flow.squeeze}
MAX_DOCUMENTS = 32


def require(condition, code):
    if not condition:
        raise ValueError(code)


def fields(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys), 'EXACT_MARKET_REPORT_FIELDS_REQUIRED')


def render(rows):
    lines = ['# Source-bound market metrics', '',
             'These are native local diagnostics of the selected original documents. '
             'Source declarations, completeness and investment conclusions are not certified.', '',
             'A null metric stays unknown. Conditional days to cover requires a comparable '
             'share basis but can have incomplete calendar coverage. An unreconciled '
             'share-count quotient is diagnostic arithmetic and is not days to cover.', '']
    for row in rows:
        lines.extend(['## Document ' + row['id'], '',
                      'Original binding: ' + encode(row['source_binding']).decode().strip(), ''])
        for operation, outcome in row['operations'].items():
            lines.extend(['### ' + operation, '', 'Operation status: ' + outcome['status'], ''])
            if outcome['status'] == 'FAILED':
                lines.extend(['Retained error:', '```json', encode(outcome['error']).decode().strip(), '```', ''])
                continue
            # All computed fields/statuses are rendered using their native names.
            # The potentially large normalized source history remains in the
            # complete structured result, not a second manually renamed summary.
            projection = {key: value for key, value in outcome['result'].items() if key != 'evidence'}
            lines.extend(['```json', encode(projection).decode().strip(), '```',
                          'The complete result retains the normalized evidence history.', ''])
    lines.extend(['No source authenticity, causal squeeze conclusion, execution authority '
                  'or whole-report semantic pass is established.', ''])
    return '\n'.join(lines)


def analyze(request, manifest_path, expected_manifest_sha256, source_root=None):
    """Run fixed native operations on whole objects from a pinned JSON corpus.

    request = {documents: [{id, source_ref: {source_id, pointer}}],
               operations: [flow|positioning|squeeze]}
    No numeric overrides, result pointers or caller-authored result are accepted.
    """
    fields(request, ('documents', 'operations'))
    documents, operations = request['documents'], request['operations']
    require(isinstance(documents, list) and 0 < len(documents) <= MAX_DOCUMENTS,
            'BOUNDED_MARKET_DOCUMENTS_REQUIRED')
    require(isinstance(operations, list) and 0 < len(operations) <= len(OPERATIONS)
            and all(isinstance(op, str) and op in OPERATIONS for op in operations)
            and len(set(operations)) == len(operations), 'UNIQUE_SUPPORTED_MARKET_OPERATIONS_REQUIRED')
    corpus = Corpus(manifest_path, expected_manifest_sha256, source_root)
    selected, seen = [], set()
    # Resolve and validate all source bindings before running any calculations.
    for item in documents:
        fields(item, ('id', 'source_ref'))
        identifier = item['id']
        require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}', identifier)
                and identifier not in seen, 'UNIQUE_MARKET_DOCUMENT_IDS_REQUIRED')
        seen.add(identifier)
        ref = item['source_ref']; fields(ref, ('source_id', 'pointer'))
        require(isinstance(ref['source_id'], str) and ref['source_id'] in corpus.sources,
                'REFERENCE_OUTSIDE_PINNED_CORPUS')
        source = corpus.sources[ref['source_id']]
        require(source['format'] == 'json', 'ORIGINAL_JSON_MARKET_DOCUMENT_REQUIRED')
        # Corpus already checked duplicate keys, nonfinite literals and exact
        # bytes. Match the native CLI's standard JSON numeric types here: its
        # result evidence must not turn original decimal numbers into strings
        # through the bridge's Decimal serialization convention.
        document = at(json.loads(source['raw']), ref['pointer'])
        require(isinstance(document, dict) and {'schema_version', 'as_of', 'records'} <= set(document),
                'WHOLE_MARKET_DOCUMENT_REQUIRED')
        selected.append((identifier, deepcopy(ref), source['sha256'], document))
    rows, failures = [], 0
    for identifier, ref, sha, document in selected:
        results = {}
        for operation in operations:
            try:
                native = OPERATIONS[operation](deepcopy(document))
                results[operation] = {'status': 'EXECUTED', 'result': native}
            except (ValueError, TypeError, KeyError, OverflowError) as error:
                # Retain genuine failed calculations; do not replace them with
                # zero/unknown successful metrics or abandon independent work.
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
            'limits': ['Only selected documents and named native operations were analyzed.',
                       'Unknown fields and native issues are findings, not supplied replacements.',
                       'Retained failed operations are not completed calculations.',
                       'Source authenticity, arbitrary prose and request completeness are not verified.',
                       'Raw source parsing and institutional briefs are separate operations.'],
            'execution_authorized': False, 'source_authenticity_verified': False,
            'whole_report_semantic_pass': False}
