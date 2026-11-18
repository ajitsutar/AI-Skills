"""Bind declared answer reviews to retained deliveries; never grade arbitrary prose.

Read-only local assessment. Existing delivery verifiers own numerical replay and
Markdown/JSON consistency for generated deliveries. Authored pairs receive only
exact-byte/input bindings; no replay or semantic consistency is inferred.
Reviewer judgments and capture clocks remain declared.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re

import institutional_acceptance as evidence

METHOD = 'delivered-answer-review-1'
STATUSES = ('SATISFIED', 'MATERIAL_ERROR', 'UNSUPPORTED', 'OMITTED', 'UNREVIEWED')
ISSUES = {'currency', 'period', 'amount', 'attribution', 'source_status',
          'contradiction', 'omitted_alternative', 'other'}
MAX_SOURCES = 128
MAX_UNITS = 1000
MAX_TOTAL = 64 * 1024 * 1024
require = evidence.require
exact = evidence.exact
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def text(value):
    require(type(value) is str and 0 < len(value) <= 4096 and value.strip(), 'BOUNDED_TEXT_REQUIRED')
    return value


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', value), 'IDENTIFIER_REQUIRED')
    return value


class Reader:
    """Reuse existing path/private-name/reparse rules; bound cumulative reads."""
    def __init__(self, root):
        self.root = Path(root)
        self.files = {}
        self.total = 0

    def read(self, ref):
        exact(ref, ('path', 'sha256'), 'artifact')
        evidence.sha(ref['sha256'])
        path = evidence._path(self.root, ref['path'])
        require(path.stat().st_size <= evidence.MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
        raw = path.read_bytes()
        require(len(raw) <= evidence.MAX_BYTES and sha(raw) == ref['sha256'], 'ARTIFACT_HASH_MISMATCH')
        if ref['path'] not in self.files:
            self.total += len(raw)
        require(self.total <= MAX_TOTAL, 'REVIEW_TOTAL_SIZE_LIMIT')
        require(ref['path'] not in self.files or self.files[ref['path']] == ref['sha256'], 'CONFLICTING_ARTIFACT_PIN')
        self.files[ref['path']] = ref['sha256']
        return raw

    def unchanged(self):
        for path, pin in list(self.files.items()):
            self.read({'path': path, 'sha256': pin})


def span(value, raw):
    exact(value, ('start_byte', 'end_byte', 'sha256'), 'span')
    start, end = value['start_byte'], value['end_byte']
    require(type(start) is int and type(end) is int and 0 <= start < end <= len(raw), 'BYTE_SPAN_RANGE')
    evidence.sha(value['sha256'])
    require(sha(raw[start:end]) == value['sha256'], 'BYTE_SPAN_HASH_MISMATCH')
    # Offsets are UTF-8 bytes, never characters; disallow partial code points.
    try:
        raw[:start].decode('utf8'); raw[start:end].decode('utf8'); raw[end:].decode('utf8')
    except UnicodeError as error:
        raise ValueError('UTF8_SPAN_BOUNDARY') from error


def spans(values, raw, required=False):
    require(type(values) is list and int(required) <= len(values) <= 32, 'BOUNDED_SPANS_REQUIRED')
    for item in values:
        span(item, raw)


def protocol(raw, reader):
    value = evidence._json(raw)
    exact(value, ('schema_version', 'id', 'adopted_at', 'original_request', 'sources', 'units',
                  'max_material_error_units'), 'answer_review_protocol')
    require(type(value['schema_version']) is int and value['schema_version'] == 1, 'SCHEMA_VERSION')
    identifier(value['id']); evidence.clock(value['adopted_at'])
    original = reader.read(value['original_request'])
    require(type(value['sources']) is list and len(value['sources']) <= MAX_SOURCES, 'BOUNDED_SOURCES')
    sources = {}
    for row in value['sources']:
        exact(row, ('id', 'artifact'), 'source')
        sid = identifier(row['id'])
        require(sid not in sources, 'DUPLICATE_SOURCE_ID')
        sources[sid] = reader.read(row['artifact'])
    units = value['units']
    require(type(units) is list and 0 < len(units) <= MAX_UNITS, 'FROZEN_NONEMPTY_UNITS')
    seen = set()
    for unit in units:
        exact(unit, ('id', 'requirement', 'request_spans', 'required_source_ids'), 'review_unit')
        uid = identifier(unit['id']); require(uid not in seen, 'DUPLICATE_UNIT_ID'); seen.add(uid)
        text(unit['requirement']); spans(unit['request_spans'], original, required=True)
        ids = unit['required_source_ids']
        require(type(ids) is list and all(type(i) is str for i in ids)
                and len(ids) == len(set(ids)) and set(ids) <= set(sources), 'REQUIRED_SOURCE_IDS')
    limit = value['max_material_error_units']
    require(type(limit) is int and 0 <= limit <= len(units), 'ABSOLUTE_ERROR_TOLERANCE')
    return value, sources


def authored_pair(value, reader):
    """Review actual authored artifacts without inventing a producer contract."""
    exact(value, ('kind', 'first_response', 'response', 'original_inputs', 'captured_at'), 'authored_pair')
    evidence.clock(value['captured_at'])
    inputs = value['original_inputs']
    require(type(inputs) is list and 0 < len(inputs) <= MAX_SOURCES + 1, 'BOUNDED_ORIGINAL_INPUTS')
    input_hashes = {}
    for ref in inputs:
        raw = reader.read(ref)
        require(ref['path'] not in input_hashes, 'DUPLICATE_ORIGINAL_INPUT')
        input_hashes[ref['path']] = sha(raw)
    first = reader.read(value['first_response'])
    response = reader.read(value['response'])
    require(value['first_response']['path'] != value['response']['path'], 'DISTINCT_ANSWER_ARTIFACTS_REQUIRED')
    require(not {value['first_response']['path'], value['response']['path']} & set(input_hashes),
            'ANSWER_CANNOT_REPLACE_ORIGINAL_INPUT')
    try:
        require(bool(first.decode('utf8').strip()), 'NONEMPTY_AUTHORED_MARKDOWN')
        result = evidence._json(response)
    except UnicodeError as error:
        raise ValueError('AUTHORED_PAIR_UTF8_REQUIRED') from error
    require(type(result) is dict and bool(result), 'AUTHORED_RESPONSE_OBJECT_REQUIRED')
    return {'first_response': first, 'response': response}, input_hashes


def delivery(value, reader):
    if type(value) is dict and value.get('kind') == 'authored_pair':
        return authored_pair(value, reader)
    exact(value, ('kind', 'directory', 'receipt_sha256', 'first_response_sha256',
                  'response_sha256', 'captured_at'), 'delivery')
    require(value['kind'] in ('canonical_response', 'request_coverage'), 'SUPPORTED_DELIVERY_KIND')
    evidence.clock(value['captured_at'])
    directory = evidence._path(reader.root, value['directory'], directory=True)
    prefix = value['directory'] + '/'
    reader.read({'path': prefix + 'receipt.json', 'sha256': value['receipt_sha256']})
    if value['kind'] == 'canonical_response':
        import final_report
        final_report.verify_response(directory)
        first = 'report/first-response.md'
    else:
        import request_coverage
        request_coverage.verify(directory)
        first = 'first-response.md'
    first_raw = reader.read({'path': prefix + first, 'sha256': value['first_response_sha256']})
    response_raw = reader.read({'path': prefix + 'response.json', 'sha256': value['response_sha256']})
    # Financial result JSON can contain Decimal-compatible tokens; only hashes
    # are inspected here, not recoded numeric values or inferred financial facts.
    from source_lineage import parse
    result = parse(response_raw)
    require(type(result.get('input_hashes')) is dict, 'DELIVERY_ORIGINAL_INPUT_HASHES_REQUIRED')
    return {'first_response': first_raw, 'response': response_raw}, result['input_hashes']


def assess(document, evidence_root, expected_protocol_sha256):
    """Validate bindings and derive counts; declared semantic outcomes stay declared."""
    exact(document, ('schema_version', 'protocol', 'reviewed_at', 'reviewer', 'delivery', 'reviews'), 'answer_review')
    evidence._clean(document)
    require(type(document['schema_version']) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    evidence.sha(expected_protocol_sha256)
    require(document['protocol']['sha256'] == expected_protocol_sha256, 'EXTERNAL_PROTOCOL_PIN_MISMATCH')
    reader = Reader(evidence_root)
    plan, sources = protocol(reader.read(document['protocol']), reader)
    exact(document['reviewer'], ('id', 'kind'), 'reviewer')
    identifier(document['reviewer']['id'])
    require(document['reviewer']['kind'] in ('human_reported', 'automated', 'unknown'), 'REVIEWER_KIND')
    require(evidence.clock(plan['adopted_at']) <= evidence.clock(document['delivery']['captured_at'])
            <= evidence.clock(document['reviewed_at']), 'REVIEW_CLOCK_ORDER')
    answer, input_hashes = delivery(document['delivery'], reader)
    pinned_inputs = [plan['original_request']] + [s['artifact'] for s in plan['sources']]
    require(all(ref['sha256'] in input_hashes.values() for ref in pinned_inputs), 'REVIEW_SOURCE_NOT_IN_DELIVERED_CORPUS')
    if document['delivery']['kind'] == 'authored_pair':
        expected_inputs = {ref['path']: ref['sha256'] for ref in pinned_inputs}
        require(input_hashes == expected_inputs, 'AUTHORED_PAIR_EXACT_PROTOCOL_INPUTS_REQUIRED')
    require(type(document['reviews']) is list and len(document['reviews']) <= MAX_UNITS, 'BOUNDED_REVIEWS')
    units = {u['id']: u for u in plan['units']}
    reviewed = {}
    supplied_unreviewed = set()
    for row in document['reviews']:
        exact(row, ('unit_id', 'status', 'material_error', 'issues', 'rationale', 'answer_spans', 'source_reviews'), 'unit_review')
        uid = row['unit_id']
        require(type(uid) is str and uid in units and uid not in reviewed, 'UNKNOWN_OR_DUPLICATE_REVIEW_UNIT')
        require(row['status'] in STATUSES, 'REVIEW_STATUS')
        material = row['material_error']
        require(material is None or type(material) is bool, 'DECLARED_MATERIALITY_REQUIRED')
        require(row['status'] != 'MATERIAL_ERROR' or material is True, 'MATERIAL_ERROR_STATUS_CONFLICT')
        require(row['status'] != 'SATISFIED' or material is False, 'SATISFIED_MATERIALITY_CONFLICT')
        require(row['status'] != 'UNREVIEWED' or material is None, 'UNREVIEWED_MATERIALITY_UNKNOWN')
        issues = row['issues']
        require(type(issues) is list and all(type(x) is str for x in issues)
                and len(issues) == len(set(issues)) and set(issues) <= ISSUES, 'ISSUE_CATEGORIES')
        require(not issues if row['status'] == 'SATISFIED' else bool(issues) or row['status'] == 'UNREVIEWED', 'STATUS_ISSUE_CONFLICT')
        text(row['rationale'])
        refs = row['answer_spans']
        require(type(refs) is list and len(refs) <= 32, 'BOUNDED_ANSWER_SPANS')
        require(bool(refs) or row['status'] in ('OMITTED', 'UNREVIEWED'), 'ANSWER_LOCATOR_REQUIRED')
        for ref in refs:
            exact(ref, ('artifact', 'span'), 'answer_locator')
            require(ref['artifact'] in answer, 'ANSWER_ARTIFACT')
            span(ref['span'], answer[ref['artifact']])
        source_rows = row['source_reviews']
        require(type(source_rows) is list and len(source_rows) <= MAX_SOURCES, 'BOUNDED_SOURCE_REVIEWS')
        seen = set()
        for source in source_rows:
            exact(source, ('source_id', 'status', 'spans'), 'source_review')
            sid = source['source_id']
            require(type(sid) is str and sid in units[uid]['required_source_ids'] and sid not in seen, 'REVIEW_SOURCE_UNIT_MISMATCH')
            seen.add(sid)
            require(source['status'] in ('REVIEWED', 'SUPPLIED_UNREVIEWED'), 'SOURCE_REVIEW_STATUS')
            spans(source['spans'], sources[sid], required=source['status'] == 'REVIEWED')
            if source['status'] == 'SUPPLIED_UNREVIEWED':
                require(not source['spans'] and row['status'] != 'SATISFIED', 'UNREVIEWED_SOURCE_CANNOT_SUPPORT_SATISFIED')
                supplied_unreviewed.add(sid)
        require(seen == set(units[uid]['required_source_ids']), 'MISSING_SOURCE_REVIEW_DISPOSITION')
        reviewed[uid] = copy.deepcopy(row)
    missing = sorted(set(units) - set(reviewed))
    counts = {status: sum(row['status'] == status for row in reviewed.values()) for status in STATUSES}
    counts['UNREVIEWED'] += len(missing)
    unknown_materiality = sorted(uid for uid, row in reviewed.items() if row['material_error'] is None)
    material_errors = sum(row['material_error'] is True for row in reviewed.values())
    complete = not missing and counts['UNREVIEWED'] == 0 and not supplied_unreviewed and not unknown_materiality
    tolerance_met = material_errors <= plan['max_material_error_units'] if complete else None
    escalation = not complete or not tolerance_met or bool(counts['UNSUPPORTED'] or counts['OMITTED'])
    reader.unchanged()
    return {'schema_version': 1, 'method': METHOD,
        'status': 'INCOMPLETE_DECLARED_REVIEW' if not complete else 'REQUIRES_ESCALATION' if escalation else 'WITHIN_DECLARED_TOLERANCE',
        'protocol': copy.deepcopy(document['protocol']), 'reviewed_at': document['reviewed_at'],
        'reviewer': copy.deepcopy(document['reviewer']), 'delivery': copy.deepcopy(document['delivery']),
        'original_request': copy.deepcopy(plan['original_request']), 'sources': copy.deepcopy(plan['sources']),
        'units': copy.deepcopy(plan['units']), 'reviews': [reviewed[u['id']] for u in plan['units'] if u['id'] in reviewed],
        'expected_units': len(units), 'status_counts': counts, 'material_error_units': material_errors,
        'unknown_materiality_unit_ids': unknown_materiality, 'missing_unit_ids': missing,
        'supplied_unreviewed_source_ids': sorted(supplied_unreviewed),
        'max_material_error_units': plan['max_material_error_units'], 'declared_review_complete': complete,
        'declared_material_error_tolerance_met': tolerance_met, 'escalation_required_by_review_policy': escalation,
        'delivery_binding_kind': document['delivery']['kind'],
        'generated_delivery_verifier_executed': document['delivery']['kind'] != 'authored_pair',
        'authored_pair_semantic_consistency_verified': False,
        'semantic_judgments_are_reviewer_declarations': True, 'whole_answer_correctness_verified': False,
        'request_semantic_completeness_verified': False, 'source_authenticity_verified': False,
        'source_absence_established': False, 'human_activity_authenticated': False,
        'capture_clocks_authenticated': False, 'execution_authorized': False,
        'input_sha256': evidence.digest(document), 'checked_artifacts': dict(reader.files),
        'limits': ['Generated deliveries retain their existing verifier; authored pairs bind exact files and declared input inventory only, with no numerical replay or semantic consistency check.',
            'Units, relevance, materiality and semantic judgments are adopted/reviewer declarations; omitted requirements can remain outside that roster.',
            'Missing units and supplied-but-unreviewed sources are incomplete review, never a zero-error pass or source absence.',
            'Unsupported/omitted answers require advisory escalation even when the material-error count is within its declared limit.',
            'Local hashes and declared chronology do not authenticate reviewers, honest clocks, prespecification, or productivity. No study or action is dispatched.']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--protocol-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        # Explicit input is subject to the same ancestor/private-name/size checks.
        root = args.evidence_root.absolute()
        name = args.input.absolute().relative_to(root).as_posix()
        path = evidence._path(root, name)
        require(path.stat().st_size <= evidence.MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
        raw = path.read_bytes(); require(len(raw) <= evidence.MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
        result = assess(evidence._json(raw), root, args.protocol_sha256)
        require(path.read_bytes() == raw, 'REVIEW_INPUT_CHANGED')
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 0 if result['status'] == 'WITHIN_DECLARED_TOLERANCE' else 2
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, OverflowError, RecursionError) as error:
        print(json.dumps({'status': 'INVALID_REVIEW_EVIDENCE', 'error': str(error), 'whole_answer_correctness_verified': False}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
