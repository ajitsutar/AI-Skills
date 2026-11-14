"""Offline, immutable criterion/evidence preflight; never dispatches participants.

Typed declarations constrain packet construction, not the semantic content of an
arbitrary document. Hashes prove retained identity, not authenticity or honest clocks.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys

from source_claims import Corpus
from source_lineage import parse
import institutional_research as research

KIND = 'OFFLINE_REVIEW_PACKET_PREFLIGHT'
MAX_BYTES = 50 * 1024 * 1024
MAX_SOURCES = 128
ARMS = ['source_only', 'brief_assisted']
REQUIRED = {'adopted_protocol', 'registered_roster', 'selection_coverage',
            'identity_coverage', 'source_cutoff', 'original_response_capture',
            'decision_clocks', 'scoring_criteria', 'source_inputs', 'brief', 'neutral_instructions'}
EVALUATOR = REQUIRED - {'source_inputs', 'brief', 'neutral_instructions'}
OPTIONAL = {'provenance_metadata', 'machine_review_timing', 'source_only_answer',
            'brief_assisted_answer', 'future_outcomes'}
FORBIDDEN = {'private_contact', 'private_contact_configuration', 'runtime_config', 'runtime_configuration', 'credentials'}
LIMITS = [
    'Coverage means declared evidence support, not a scored criterion verdict or source authenticity.',
    'Clocks and model/context identities are retained declarations; hashes prove neither honest clocks nor independence.',
    'Explicit evidence roles and known-byte leak checks are not semantic content classification or host DLP.',
    'No network, model API, participant dispatch, schedule, broker action or study observation runs.',
    'Historical responses and scores remain unchanged; new evidence requires a retained review revision.']


def require(condition, code):
    if not condition:
        raise ValueError(code)


def raw_hash(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return research._bytes(value) + b'\n'


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', value), 'SAFE_PACKET_ID_REQUIRED')
    return value


def no_links(path):
    """Reject symlinks and Windows reparse points, including ancestor directories."""
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        require(not item.is_symlink(), 'LINK_OR_REPARSE_POINT_REFUSED')
        if item.exists():
            require(not getattr(item.stat(), 'st_file_attributes', 0) & 0x400, 'LINK_OR_REPARSE_POINT_REFUSED')
    return path


def read(path):
    path = no_links(path)
    require(path.is_file() and path.stat().st_size <= MAX_BYTES, 'BOUNDED_REGULAR_FILE_REQUIRED')
    raw = path.read_bytes()
    require(len(raw) <= MAX_BYTES, 'INPUT_SIZE_CAP')
    return raw


def root_path(value):
    root = no_links(value)
    require(root.is_dir(), 'EXPLICIT_EXISTING_ROOT_REQUIRED')
    return root.resolve()


def relative(root, value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value
            and not Path(value).is_absolute() and '..' not in Path(value).parts, 'BOUNDED_RELATIVE_PATH_REQUIRED')
    path = no_links(root / value)
    require(path.resolve().is_relative_to(root), 'SOURCE_ROOT_ESCAPE')
    return path


def load_corpus(manifest_path, pin, source_root):
    root = root_path(source_root)
    manifest_path = no_links(manifest_path)
    raw = read(manifest_path)
    require(raw_hash(raw) == research._hash(pin), 'INGRESS_MANIFEST_HASH_MISMATCH')
    manifest = parse(raw)
    require(isinstance(manifest, dict) and isinstance(manifest.get('sources'), list)
            and 0 < len(manifest['sources']) <= MAX_SOURCES, 'BOUNDED_SOURCE_INVENTORY_REQUIRED')
    total = 0
    for item in manifest['sources']:
        require(isinstance(item, dict), 'SOURCE_OBJECT_REQUIRED')
        path = relative(root, item.get('path'))
        require(path.is_file() and path.stat().st_size <= MAX_BYTES, 'BOUNDED_REGULAR_FILE_REQUIRED')
        total += path.stat().st_size
    require(total <= MAX_BYTES, 'TOTAL_SOURCE_SIZE_CAP')
    # Compose the existing externally pinned source/lineage contract after bounds.
    corpus = Corpus(manifest_path, pin, root)
    return corpus, raw


def analyze(request, manifest_path, expected_manifest_sha256, source_root):
    """Read-only status contract. Supported means evidence coverage, never a score."""
    require(isinstance(request, dict) and set(request) <= {
        'schema_version', 'packet_id', 'revision', 'parent_packet_sha256', 'case_id',
        'review_at', 'adopted_protocol_sha256', 'evidence'}, 'EXACT_REVIEW_REQUEST_FIELDS_REQUIRED')
    require(type(request.get('schema_version')) is int and request['schema_version'] == 1, 'SCHEMA_VERSION_1_REQUIRED')
    identifier(request.get('packet_id')); identifier(request.get('case_id'))
    revision = request.get('revision')
    require(type(revision) is int and 1 <= revision <= 100, 'REVIEW_REVISION_1_TO_100_REQUIRED')
    if revision > 1:
        research._hash(request.get('parent_packet_sha256'))
    else:
        require(request.get('parent_packet_sha256') is None, 'FIRST_REVISION_HAS_NO_PARENT')
    review_at = research._stamp(request.get('review_at'))
    research._hash(request.get('adopted_protocol_sha256'))
    evidence = request.get('evidence')
    require(isinstance(evidence, list) and len(evidence) <= MAX_SOURCES, 'BOUNDED_TYPED_EVIDENCE_REQUIRED')
    by_role, seen, source_roles = {}, set(), {}
    # Refuse declared private roles before opening any corpus source bytes.
    for item in evidence:
        require(isinstance(item, dict) and set(item) == {'id', 'role', 'source_id', 'allowed_arms', 'available_at'}, 'EXACT_TYPED_EVIDENCE_FIELDS_REQUIRED')
        identifier(item['id'])
        require(item['id'] not in seen, 'DUPLICATE_EVIDENCE_ID'); seen.add(item['id'])
        role = item['role']
        require(isinstance(role, str) and role not in FORBIDDEN, 'PRIVATE_RUNTIME_EVIDENCE_REFUSED')
        require(role in REQUIRED | OPTIONAL, 'UNKNOWN_EVIDENCE_ROLE')
        allowed = ARMS if role in {'source_inputs', 'neutral_instructions'} else ['brief_assisted'] if role in {'brief', 'provenance_metadata'} else []
        require(item['allowed_arms'] == allowed, 'ARM_INPUT_POLICY_VIOLATION')
        require(isinstance(item['source_id'], str) and item['source_id'] not in source_roles, 'ONE_ROLE_PER_SOURCE_REQUIRED')
        source_roles[item['source_id']] = role
        if role != 'source_inputs':
            require(role not in by_role, 'DUPLICATE_EVIDENCE_ROLE')
        by_role.setdefault(role, []).append(item)
        research._stamp(item['available_at'])
    corpus, _ = load_corpus(manifest_path, expected_manifest_sha256, source_root)
    require(all(item['source_id'] in corpus.sources for item in evidence), 'REFERENCE_OUTSIDE_PINNED_CORPUS')
    issues = []
    role_issues = {role: [] for role in REQUIRED | OPTIONAL}

    def issue(code, roles):
        if code not in issues:
            issues.append(code)
        for role in roles:
            role_issues[role].append(code)

    def document(role):
        if role not in by_role:
            return None
        source = corpus.sources[by_role[role][0]['source_id']]
        require(source['format'] == 'json' and isinstance(source['document'], dict), 'TYPED_JSON_EVIDENCE_REQUIRED:' + role)
        return source['document']

    for role in sorted(REQUIRED - set(by_role)):
        issue('MISSING_ROLE:' + role, [role])
    for item in evidence:
        if research._stamp(item['available_at']) > review_at:
            issue('EVIDENCE_AFTER_REVIEW_CUTOFF:' + item['id'], [item['role']])
    protocol = document('adopted_protocol')
    if protocol is not None:
        sid = by_role['adopted_protocol'][0]['source_id']
        if corpus.sources[sid]['sha256'] != request['adopted_protocol_sha256']:
            issue('ADOPTED_PROTOCOL_HASH_MISMATCH', ['adopted_protocol'])
        require(isinstance(protocol.get('id'), str), 'PROTOCOL_ID_REQUIRED')
        adopted = research._stamp(protocol.get('adopted_at'))
    else:
        adopted = None
    for role in ('registered_roster', 'scoring_criteria'):
        value = document(role)
        if value is not None and value.get('protocol_sha256') != request['adopted_protocol_sha256']:
            issue('PROTOCOL_REVISION_MISMATCH:' + role, [role, 'adopted_protocol'])
    roster = document('registered_roster')
    if roster is not None:
        ids = roster.get('case_ids')
        require(isinstance(ids, list) and all(isinstance(x, str) and x for x in ids)
                and len(ids) == len(set(ids)), 'UNIQUE_REGISTERED_CASE_IDS_REQUIRED')
        if request['case_id'] not in ids:
            issue('CASE_OUTSIDE_REGISTERED_ROSTER', ['registered_roster'])
        if protocol is not None and protocol.get('case_ids') != ids:
            issue('ROSTER_DIFFERS_FROM_ADOPTED_PROTOCOL', ['registered_roster', 'adopted_protocol'])
    cutoff_document = document('source_cutoff')
    cutoff = research._stamp(cutoff_document.get('source_cutoff_at')) if cutoff_document is not None else None
    clock_document = document('decision_clocks')
    decision = research._stamp(clock_document.get('decision_at')) if clock_document is not None else None
    if decision is not None and decision > review_at:
        issue('DECISION_AFTER_REVIEW_CUTOFF', ['decision_clocks'])
    if adopted is not None and cutoff is not None and adopted > cutoff:
        issue('PROTOCOL_ADOPTED_AFTER_SOURCE_CUTOFF', ['adopted_protocol'])
    for role in ('selection_coverage', 'identity_coverage'):
        value = document(role)
        if value is not None:
            if value.get('case_id') != request['case_id']:
                issue('CASE_IDENTITY_MISMATCH:' + role, [role])
            refs = value.get('source_ids')
            require(isinstance(refs, list) and refs and all(isinstance(x, str) and x in corpus.sources for x in refs), 'PINNED_COVERAGE_SOURCE_IDS_REQUIRED')
            if not isinstance(value.get('scope'), str) or not value['scope'].strip():
                issue('COVERAGE_SCOPE_UNESTABLISHED:' + role, [role])
            if role == 'selection_coverage':
                if not isinstance(value.get('selection_method'), str) or not value['selection_method'].strip():
                    issue('SELECTION_METHOD_UNESTABLISHED', [role])
                if value.get('status') not in {'COMPLETE_DECLARED_SCOPE', 'PARTIAL_DECLARED_SCOPE'}:
                    issue('SELECTION_COVERAGE_UNESTABLISHED', [role])
                if value.get('status') == 'PARTIAL_DECLARED_SCOPE' and not value.get('gaps'):
                    issue('PARTIAL_SELECTION_GAPS_UNDECLARED', [role])
                common = {x['source_id'] for x in by_role.get('source_inputs', [])}
                if not common <= set(refs):
                    issue('PARTICIPANT_INPUT_OUTSIDE_RETAINED_SELECTION', [role, 'source_inputs'])
            if role == 'identity_coverage' and value.get('status') != 'MATCHED_DECLARED_IDENTITY':
                issue('IDENTITY_UNRESOLVED', [role])
    capture = document('original_response_capture')
    captured = None
    journal_evaluator_bytes = []
    journal_object_raw = None
    if capture is not None:
        require(set(capture) == {'entry_source_id', 'transaction_source_id', 'commit_source_id', 'object_source_id'}, 'EXACT_JOURNAL_BINDINGS_REQUIRED')
        require(all(isinstance(sid, str) and sid in corpus.sources for sid in capture.values()), 'JOURNAL_OUTSIDE_PINNED_CORPUS')
        sources = {key: corpus.sources[sid] for key, sid in capture.items()}
        # Match the native journal's standard JSON numeric decoding for its
        # canonical idempotency key; Corpus has already rejected invalid JSON.
        keys = ('entry_source_id', 'transaction_source_id', 'commit_source_id')
        require(all(sources[key]['format'] == 'json' for key in keys), 'JSON_JOURNAL_RECORDS_REQUIRED')
        entry, transaction, commit = [json.loads(sources[key]['raw']) for key in keys]
        require(isinstance(entry, dict) and set(entry) == {'id', 'kind', 'object_sha256', 'bytes', 'metadata', 'recorded_at'}
                and isinstance(entry['metadata'], dict) and type(entry['bytes']) is int
                and isinstance(transaction, dict) and set(transaction) == {'schema_version', 'idempotency_key', 'entry'}
                and type(transaction['schema_version']) is int and transaction['schema_version'] == 1
                and isinstance(commit, dict) and set(commit) == {'id', 'entry_sha256', 'object_sha256'}, 'NATIVE_JOURNAL_SCHEMA_REQUIRED')
        research._id(entry['id'])
        stable = {k: v for k, v in entry.items() if k != 'recorded_at'}
        obj = sources['object_source_id']
        journal_object_raw = obj['raw']
        journal_evaluator_bytes = [('original_response_capture.' + key, capture[key], sources[key]['raw'])
                                   for key in keys]
        valid = (entry.get('kind') == 'first_response' and transaction.get('entry') == entry
                 and transaction.get('idempotency_key') == research._digest(stable)
                 and entry.get('object_sha256') == obj['sha256'] and entry.get('bytes') == len(obj['raw'])
                 and commit.get('id') == entry.get('id') and commit.get('entry_sha256') == sources['entry_source_id']['sha256']
                 and commit.get('object_sha256') == obj['sha256'])
        if not valid:
            issue('ORIGINAL_RESPONSE_JOURNAL_BINDING_MISMATCH', ['original_response_capture'])
        captured = research._stamp(entry.get('recorded_at'))
        if decision is not None and captured > decision or cutoff is not None and captured < cutoff or captured > review_at:
            issue('ORIGINAL_RESPONSE_CLOCK_ORDER_UNESTABLISHED', ['original_response_capture', 'decision_clocks'])
        if 'brief' in by_role and corpus.sources[by_role['brief'][0]['source_id']]['sha256'] != obj['sha256']:
            issue('BRIEF_DIFFERS_FROM_RETAINED_ORIGINAL_RESPONSE', ['brief', 'original_response_capture'])
    for item in evidence:
        limit = cutoff if item['role'] in {'source_inputs', 'neutral_instructions', 'adopted_protocol', 'registered_roster', 'selection_coverage', 'identity_coverage', 'scoring_criteria'} else captured if item['role'] in {'brief', 'provenance_metadata'} else None
        if limit is not None and research._stamp(item['available_at']) > limit:
            issue('POST_CUTOFF_EVIDENCE:' + item['id'], [item['role']])
    # Detect exact known forbidden bytes, including aliases with different IDs.
    forbidden = [corpus.sources[item['source_id']]['raw'] for role in ('source_only_answer', 'brief_assisted_answer', 'future_outcomes') for item in by_role.get(role, [])]
    brief_raw = corpus.sources[by_role['brief'][0]['source_id']]['raw'] if 'brief' in by_role else None
    rubric_raw = corpus.sources[by_role['scoring_criteria'][0]['source_id']]['raw'] if 'scoring_criteria' in by_role else None
    evaluator_bytes = [(item['role'], item['id'], corpus.sources[item['source_id']]['raw'])
                       for item in evidence if not item['allowed_arms']] + journal_evaluator_bytes
    blocked_participant_ids = set()
    for item in evidence:
        if item['allowed_arms']:
            raw = corpus.sources[item['source_id']]['raw']
            if not raw.strip():
                issue('EMPTY_PARTICIPANT_EVIDENCE:' + item['id'], [item['role']])
            if any(secret and secret in raw for secret in forbidden):
                issue('KNOWN_ANSWER_OR_FUTURE_OUTCOME_LEAK:' + item['id'], [item['role']])
                blocked_participant_ids.add(item['id'])
            if 'source_only' in item['allowed_arms'] and brief_raw and brief_raw in raw:
                issue('BRIEF_LEAKED_TO_SOURCE_ONLY:' + item['id'], [item['role']])
                blocked_participant_ids.add(item['id'])
            if 'source_only' in item['allowed_arms'] and journal_object_raw and journal_object_raw in raw:
                issue('ORIGINAL_RESPONSE_LEAKED_TO_SOURCE_ONLY:' + item['id'], [item['role']])
                blocked_participant_ids.add(item['id'])
            if rubric_raw and rubric_raw in raw:
                issue('EVALUATOR_CRITERIA_LEAKED_TO_PARTICIPANT:' + item['id'], [item['role']])
                blocked_participant_ids.add(item['id'])
            for role, evaluator_id, protected_raw in evaluator_bytes:
                if protected_raw and protected_raw in raw:
                    issue('EVALUATOR_ONLY_EVIDENCE_LEAKED_TO_PARTICIPANT:' + item['id'] + ':' + role + ':' + evaluator_id,
                          [item['role']])
                    blocked_participant_ids.add(item['id'])
    criteria_document = document('scoring_criteria')
    criteria = criteria_document.get('criteria') if criteria_document is not None else []
    require(isinstance(criteria, list) and len(criteria) <= 128, 'BOUNDED_CRITERIA_REQUIRED')
    if protocol is not None and criteria_document is not None and protocol.get('criteria') != criteria:
        issue('CRITERIA_DIFFER_FROM_ADOPTED_PROTOCOL', ['scoring_criteria', 'adopted_protocol'])
    coverage, ids = [], set()
    for criterion in criteria:
        require(isinstance(criterion, dict) and set(criterion) == {'id', 'criterion', 'assessment_kind', 'required_roles'}
                and isinstance(criterion['criterion'], str) and criterion['criterion'].strip(), 'EXACT_SCORING_CRITERION_FIELDS_REQUIRED')
        cid = identifier(criterion['id']); require(cid not in ids, 'DUPLICATE_CRITERION_ID'); ids.add(cid)
        roles = criterion['required_roles']
        require(isinstance(roles, list) and roles and all(isinstance(x, str) and x in REQUIRED | OPTIONAL for x in roles)
                and len(roles) == len(set(roles)), 'EXPLICIT_CRITERION_EVIDENCE_ROLES_REQUIRED')
        required = REQUIRED | set(roles)
        if criterion['assessment_kind'] == 'machine_duration':
            required.add('machine_review_timing')
        missing = sorted(required - set(by_role))
        codes = sorted({code for role in required for code in role_issues[role]})
        if criterion['assessment_kind'] not in {'evidence_review', 'machine_duration'}:
            codes.append('CRITERION_NOT_VERIFIABLE_BY_PREFLIGHT')
        if criterion['assessment_kind'] == 'machine_duration':
            timing = document('machine_review_timing')
            if timing is None:
                missing = sorted(set(missing) | {'machine_review_timing'})
            elif timing.get('measurement') != 'actual_machine_duration':
                codes.append('ACTUAL_MACHINE_MEASUREMENT_UNESTABLISHED')
            else:
                for arm in ARMS:
                    clocks = timing.get(arm, {})
                    if not isinstance(clocks, dict) or not clocks.get('started_at') or not clocks.get('finished_at'):
                        codes.append('MISSING_MACHINE_CLOCKS:' + arm)
                    elif research._stamp(clocks['finished_at']) < research._stamp(clocks['started_at']):
                        codes.append('REVERSED_MACHINE_CLOCKS:' + arm)
                    elif research._stamp(clocks['finished_at']) > review_at or research._stamp(clocks['finished_at']) > research._stamp(by_role['machine_review_timing'][0]['available_at']):
                        codes.append('MACHINE_MEASUREMENT_NOT_AVAILABLE_AT_REVIEW:' + arm)
        coverage.append({'criterion_id': cid, 'status': 'UNASSESSED' if missing or codes else 'SUPPORTED_BY_DECLARED_EVIDENCE',
                         'missing_roles': missing, 'issues': sorted(set(codes)),
                         'evidence': [{'role': role, 'evidence_ids': [x['id'] for x in by_role.get(role, [])]} for role in sorted(required)],
                         'score': None})
    if not criteria:
        issue('NO_SCORING_CRITERIA', ['scoring_criteria'])
    ready = bool(coverage) and not issues and all(row['status'] == 'SUPPORTED_BY_DECLARED_EVIDENCE' for row in coverage)
    participants = {arm: [{'evidence_id': item['id'], 'role': item['role'], 'source_id': item['source_id'],
                          'sha256': corpus.sources[item['source_id']]['sha256']}
                         for item in evidence if arm in item['allowed_arms']
                         and item['id'] not in blocked_participant_ids] for arm in ARMS}
    result = {'kind': KIND, 'schema_version': 1, 'status': 'READY_FOR_OFFLINE_REVIEW' if ready else 'UNASSESSED',
            'dispatch_ready': ready, 'packet_id': request['packet_id'], 'revision': revision,
            'parent_packet_sha256': request.get('parent_packet_sha256'), 'case_id': request['case_id'],
            'review_at': request['review_at'], 'adopted_protocol_sha256': request['adopted_protocol_sha256'],
            'registered_case_ids': deepcopy(protocol.get('case_ids')) if protocol is not None else None,
            'criterion_coverage': coverage, 'issues': sorted(issues), 'participants': participants,
            'common_input_sha256': research._digest(participants['source_only']),
            'manifest_sha256': expected_manifest_sha256,
            'source_inventory': [{'source_id': sid, 'sha256': value['sha256']} for sid, value in corpus.sources.items()],
            'bound_evidence': [{'id': item['id'], 'role': item['role'], 'source_id': item['source_id'],
                                'sha256': corpus.sources[item['source_id']]['sha256']} for item in evidence],
            'source_authenticity_verified': False, 'model_independence_verified': False,
            'honest_clock_verified': False, 'scored_criterion_verdicts_produced': False,
            'execution_authorized': False, 'limitations': list(LIMITS)}
    if blocked_participant_ids:
        result['blocked_participant_evidence_ids'] = sorted(blocked_participant_ids)
    return result


def prepare(request_path, manifest_path, expected_manifest_sha256, source_root, private_output_root):
    source_root = root_path(source_root)
    request_raw = read(request_path); request = json.loads(request_raw, object_pairs_hook=research_pairs,
                                                         parse_constant=invalid_constant)
    result = analyze(request, manifest_path, expected_manifest_sha256, source_root)
    root = root_path(private_output_root)
    package = Path(__file__).resolve().parents[1]
    require(not root.is_relative_to(package), 'PRIVATE_OUTPUT_MUST_BE_OUTSIDE_PACKAGE')
    require(not source_root.is_relative_to(root), 'OUTPUT_MUST_NOT_CONTAIN_SOURCE_ROOT')
    if request['revision'] > 1:
        parent = root / (request['packet_id'] + '-r' + str(request['revision'] - 1))
        parent_result = verify(parent, request['parent_packet_sha256'])
        previous = json.loads(read(parent / 'request.json'))
        if previous['adopted_protocol_sha256'] != request['adopted_protocol_sha256']:
            corpus, _ = load_corpus(manifest_path, expected_manifest_sha256, source_root)
            protocol_id = next(x['source_id'] for x in request['evidence'] if x['role'] == 'adopted_protocol')
            protocol = corpus.sources[protocol_id]['document']
            require(protocol.get('predecessor_protocol_sha256') == previous['adopted_protocol_sha256'],
                    'CHANGED_PROTOCOL_MUST_RETAIN_PREDECESSOR')
            prior_corpus, _ = load_corpus(parent / 'ingress.json', parent_result['manifest_sha256'], parent / 'sealed')
            prior_id = next(x['source_id'] for x in parent_result['bound_evidence'] if x['role'] == 'adopted_protocol')
            prior_protocol = prior_corpus.sources[prior_id]['document']
            require(research._stamp(protocol.get('adopted_at')) > research._stamp(prior_protocol.get('adopted_at')),
                    'CHANGED_PROTOCOL_REQUIRES_NEW_ADOPTION_CLOCK')
    folder = root / (request['packet_id'] + '-r' + str(request['revision']))
    no_links(folder); folder.mkdir(exist_ok=True)
    corpus, manifest_raw = load_corpus(manifest_path, expected_manifest_sha256, source_root)
    files = {'request.json': request_raw, 'ingress.json': manifest_raw}
    # Seal complete originals, including evaluator-only context, outside participant directories.
    for source in corpus.sources.values():
        files['sealed/' + source['path']] = source['raw']
    for arm, items in result['participants'].items():
        for item in items:
            files['participants/' + arm + '/' + item['evidence_id'] + '.bin'] = corpus.sources[item['source_id']]['raw']
    inventory = {name: raw_hash(raw) for name, raw in sorted(files.items())}
    packet = {'schema_version': 1, 'preflight': result, 'files': inventory}
    packet_raw = encode(packet); pin = raw_hash(packet_raw)
    # An incomplete previous attempt may be resumed, but no existing byte changes.
    for name, raw in files.items():
        path = relative(folder, name); path.parent.mkdir(parents=True, exist_ok=True)
        research._publish(path, raw)
    research._publish(folder / 'packet.json', packet_raw)
    result = verify(folder, pin)
    return {**result, 'packet_directory': str(folder)}


def research_pairs(pairs):
    value = {}
    for key, child in pairs:
        require(key not in value, 'DUPLICATE_JSON_KEY')
        value[key] = child
    return value


def invalid_constant(value):
    raise ValueError('NONFINITE_JSON_NUMBER')


def verify(packet_directory, expected_packet_sha256):
    folder = root_path(packet_directory)
    packet_raw = read(folder / 'packet.json')
    require(raw_hash(packet_raw) == research._hash(expected_packet_sha256), 'PACKET_HASH_MISMATCH')
    packet = json.loads(packet_raw, object_pairs_hook=research_pairs)
    require(isinstance(packet, dict) and set(packet) == {'schema_version', 'preflight', 'files'}
            and type(packet['schema_version']) is int and packet['schema_version'] == 1
            and isinstance(packet['files'], dict), 'PACKET_SCHEMA_REQUIRED')
    actual = set()
    for path in folder.rglob('*'):
        no_links(path)
        if path.is_file():
            actual.add(path.relative_to(folder).as_posix())
    require(actual == set(packet['files']) | {'packet.json'}, 'PACKET_FILE_INVENTORY_MISMATCH')
    for name, digest in packet['files'].items():
        require(raw_hash(read(relative(folder, name))) == digest, 'SEALED_PACKET_BYTES_CHANGED:' + name)
    request = json.loads(read(folder / 'request.json'), object_pairs_hook=research_pairs)
    # The original manifest is retained exactly; originals live under sealed/.
    result = analyze(request, folder / 'ingress.json', packet['preflight']['manifest_sha256'], folder / 'sealed')
    require(result == packet['preflight'], 'PREFLIGHT_REPLAY_MISMATCH')
    require(folder.name == result['packet_id'] + '-r' + str(result['revision']), 'REVIEW_DIRECTORY_IDENTITY_MISMATCH')
    if result['revision'] > 1:
        parent = folder.parent / (result['packet_id'] + '-r' + str(result['revision'] - 1))
        previous = verify(parent, request['parent_packet_sha256'])
        require(previous['packet_id'] == result['packet_id'] and previous['revision'] == result['revision'] - 1,
                'REVIEW_PREDECESSOR_IDENTITY_MISMATCH')
        if previous['adopted_protocol_sha256'] != result['adopted_protocol_sha256']:
            current_corpus, _ = load_corpus(folder / 'ingress.json', result['manifest_sha256'], folder / 'sealed')
            prior_corpus, _ = load_corpus(parent / 'ingress.json', previous['manifest_sha256'], parent / 'sealed')
            current_id = next(x['source_id'] for x in result['bound_evidence'] if x['role'] == 'adopted_protocol')
            prior_id = next(x['source_id'] for x in previous['bound_evidence'] if x['role'] == 'adopted_protocol')
            current_protocol = current_corpus.sources[current_id]['document']
            prior_protocol = prior_corpus.sources[prior_id]['document']
            require(current_protocol.get('predecessor_protocol_sha256') == previous['adopted_protocol_sha256'],
                    'CHANGED_PROTOCOL_MUST_RETAIN_PREDECESSOR')
            require(research._stamp(current_protocol.get('adopted_at')) > research._stamp(prior_protocol.get('adopted_at')),
                    'CHANGED_PROTOCOL_REQUIRES_NEW_ADOPTION_CLOCK')
    expected_participants = {f'participants/{arm}/{item["evidence_id"]}.bin': item['sha256']
                             for arm, items in result['participants'].items() for item in items}
    require({k: v for k, v in packet['files'].items() if k.startswith('participants/')} == expected_participants,
            'PARTICIPANT_INPUT_INVENTORY_MISMATCH')
    return {**result, 'packet_sha256': expected_packet_sha256, 'integrity_status': 'VERIFIED'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    item = sub.add_parser('prepare')
    item.add_argument('--request', required=True); item.add_argument('--manifest', required=True)
    item.add_argument('--manifest-sha256', required=True); item.add_argument('--source-root', required=True)
    item.add_argument('--private-output-root', required=True)
    item = sub.add_parser('verify'); item.add_argument('--packet-directory', required=True)
    item.add_argument('--packet-sha256', required=True)
    args = parser.parse_args(argv)
    if args.command == 'prepare':
        result = prepare(args.request, args.manifest, args.manifest_sha256, args.source_root, args.private_output_root)
    else:
        result = verify(args.packet_directory, args.packet_sha256)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return 0 if result['dispatch_ready'] else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'kind': KIND, 'status': 'ERROR', 'dispatch_ready': False, 'error': str(exc), 'execution_authorized': False}), file=sys.stderr)
        raise SystemExit(2)
