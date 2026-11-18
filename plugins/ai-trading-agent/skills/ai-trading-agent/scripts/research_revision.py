"""Retain a bounded, assistant-operated draft/review/correction history.

No model is called and no prose is graded here. Native host reviewers provide
the actual judgments; answer_review.assess verifies their retained bindings.
Use one writer and retain each returned head pin outside this run directory.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path, PurePosixPath

import answer_review as review

evidence = review.evidence
require = evidence.require
METHOD = 'native-research-revision-1'
MODES = ('independent_native', 'self_native')
SKILL_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_METHOD = 'pinned-review-inputs-1'
WHOLE_REQUEST_ID = 'whole-request'


def _workflow(state):
    if state['final'] is not None:
        return {'workflow_state': 'DELIVERY_SELECTED', 'next_action': 'Deliver the exact selected pair and its review notice; retain any unresolved findings.'}
    if not state['drafts']:
        return {'workflow_state': 'DRAFT_REQUIRED', 'next_action': 'Author and freeze the complete draft pair. An actual second-pass native review is still required.'}
    if len(state['reviews']) < len(state['drafts']):
        return {'workflow_state': 'REVIEW_REQUIRED', 'next_action': 'Perform an actual native second-pass review of the whole latest draft against the original request and all adopted units/sources; then record that review.'}
    return {'workflow_state': 'REVIEW_RECORDED', 'next_action': 'Correct fixable findings within the retained budget and review the new complete pair, or select the latest reviewed pair with its explicit limitations.'}


def _readable(raw):
    _raw(raw)
    text = raw.decode('utf8')
    require(bool(text.strip()) and all(ord(c) >= 32 or c in '\t\r\n' for c in text),
            'READABLE_UTF8_INPUT_REQUIRED')
    return raw


def _input_path(path):
    path = Path(path).absolute()
    # Explicit allowlisting is not permission to read host authentication stores.
    denied = {'.ssh', '.aws', '.azure', '.env', 'credentials', 'credentials.json',
              'login data', 'cookies', 'local state', 'web data', 'id_rsa', 'id_ed25519'}
    require(not any(part.casefold() in denied for part in path.parts), 'AUTHENTICATION_INPUT_EXCLUDED')
    return evidence._path(path.parent, path.name)


def _pinned_input(path, expected):
    evidence.sha(expected)
    path = _input_path(path)
    require(path.stat().st_size <= evidence.MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
    raw = _raw(path.read_bytes())
    require(review.sha(raw) == expected, 'ORIGINAL_INPUT_HASH_MISMATCH')
    return path, raw


def _source_manifest(raw):
    manifest = evidence._json(raw)
    evidence.exact(manifest, ('schema_version', 'sources'), 'bootstrap_source_manifest')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1, 'SCHEMA_VERSION')
    rows = manifest['sources']
    require(type(rows) is list and 0 < len(rows) <= review.MAX_SOURCES, 'NONEMPTY_BOUNDED_SOURCE_ALLOWLIST')
    ids, paths = set(), set()
    for row in rows:
        evidence.exact(row, ('id', 'path', 'sha256', 'format'), 'bootstrap_source')
        sid = review.identifier(row['id']); evidence.sha(row['sha256'])
        name = row['path']; require(type(name) is str and name, 'SOURCE_PATH_REQUIRED')
        p = PurePosixPath(name)
        require(not p.is_absolute() and '\\' not in name and ':' not in name
                and all(part not in ('', '.', '..') for part in name.split('/')), 'UNSAFE_SOURCE_PATH')
        require(sid.casefold() not in ids and name.casefold() not in paths, 'DUPLICATE_SOURCE_ID_OR_PATH')
        require(row['format'] in ('text', 'json'), 'READABLE_SOURCE_FORMAT_REQUIRED')
        ids.add(sid.casefold()); paths.add(name.casefold())
    return manifest


def _whole_request(request, source_ids):
    return {'id': WHOLE_REQUEST_ID,
            'requirement': 'Review coverage of the entire original request. Identify material requirements or source qualifications omitted from the draft or adopted unit roster; assess them explicitly rather than treating this scaffold as proof of semantic completeness.',
            'request_spans': [{'start_byte': 0, 'end_byte': len(request), 'sha256': review.sha(request)}],
            'required_source_ids': list(source_ids)}


def _bootstrap_check(value, plan, reader):
    evidence.exact(value, ('method', 'manifest', 'request_sha256', 'whole_request_unit_id'), 'bootstrap_provenance')
    require(value['method'] == BOOTSTRAP_METHOD and value['whole_request_unit_id'] == WHOLE_REQUEST_ID,
            'BOOTSTRAP_METHOD')
    require(value['manifest']['path'] == 'bootstrap-manifest.json', 'BOOTSTRAP_MANIFEST_PATH')
    manifest = _source_manifest(reader.read(value['manifest']))
    request = _readable(reader.read(plan['original_request']))
    require(value['request_sha256'] == review.sha(request), 'BOOTSTRAP_REQUEST_PIN')
    ids = [row['id'] for row in manifest['sources']]
    require([row['id'] for row in plan['sources']] == ids, 'COMPLETE_MANIFEST_SOURCE_INVENTORY_REQUIRED')
    for source, original in zip(plan['sources'], manifest['sources']):
        require(source['artifact'] == {'path': 'sources/' + original['id'] + '.bin', 'sha256': original['sha256']},
                'BOOTSTRAP_SOURCE_ASSOCIATION')
        _readable(reader.read(source['artifact']))
    require(plan['units'][0] == _whole_request(request, ids), 'WHOLE_REQUEST_REVIEW_UNIT_REQUIRED')


def bootstrap_run(root, request_path, request_sha256, source_manifest_path,
                  manifest_sha256, source_root, adopted_at, *, material_units=None,
                  max_corrections=2):
    """Create actual review state from externally pinned readable original files.

    The whole allowlist is ingested, with no source-selection argument. The host
    authors any additional material units before protocol freeze. Neither this
    scaffold nor its next-action label is a review or a completeness certificate.
    """
    request_path, request = _pinned_input(request_path, request_sha256); _readable(request)
    manifest_path, manifest_raw = _pinned_input(source_manifest_path, manifest_sha256)
    manifest = _source_manifest(manifest_raw)
    sources, retained = {}, [(request_path, request), (manifest_path, manifest_raw)]
    source_root = Path(source_root).absolute()
    for row in manifest['sources']:
        # Validate lexical scope and all ancestors before opening the listed file.
        path = evidence._path(source_root, row['path'])
        path, raw = _pinned_input(path, row['sha256']); sources[row['id']] = _readable(raw)
        retained.append((path, raw))
        require(sum(len(b) for b in sources.values()) + len(request) < review.MAX_TOTAL // 2,
                'SOURCE_CORPUS_SIZE_LIMIT')
    require(material_units is None or type(material_units) is list, 'MATERIAL_UNITS_LIST_REQUIRED')
    units = [_whole_request(request, sources)] + copy.deepcopy(material_units or [])
    # Validate the complete native-authored roster before creating any output.
    artifacts = {'request.md': request, **{'sources/' + sid + '.bin': raw for sid, raw in sources.items()}}
    class MemoryReader:
        def read(self, ref):
            raw = artifacts[ref['path']]
            require(review.sha(raw) == ref['sha256'], 'PREFLIGHT_ARTIFACT_PIN')
            return raw
    plan = {'schema_version': 1, 'id': 'research-review', 'adopted_at': adopted_at,
            'original_request': {'path': 'request.md', 'sha256': review.sha(request)},
            'sources': [{'id': sid, 'artifact': {'path': 'sources/' + sid + '.bin', 'sha256': review.sha(raw)}}
                        for sid, raw in sources.items()], 'units': units, 'max_material_error_units': 0}
    review.protocol(encode(plan), MemoryReader())
    require(type(max_corrections) is int and 0 <= max_corrections <= 5, 'MAX_CORRECTIONS_0_TO_5')
    for path, raw in retained:
        require(_input_path(path).read_bytes() == raw, 'ORIGINAL_INPUT_CHANGED_DURING_BOOTSTRAP')
    result = create_run(root, request, sources, units, adopted_at, max_corrections,
                        _bootstrap_manifest=manifest_raw)
    for path, raw in retained:
        require(_input_path(path).read_bytes() == raw, 'ORIGINAL_INPUT_CHANGED_DURING_BOOTSTRAP')
    return result


def encode(value):
    evidence._clean(value)
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False,
                       allow_nan=False) + '\n').encode('utf8')


def _raw(value):
    require(type(value) is bytes and 0 < len(value) <= evidence.MAX_BYTES, 'BOUNDED_NONEMPTY_BYTES_REQUIRED')
    return value


def _root(root):
    root = Path(root).absolute()
    evidence._path(root, 'run.json')
    require(not root.resolve().is_relative_to(SKILL_ROOT), 'OUTPUT_MUST_BE_OUTSIDE_INSTALLED_SKILL')
    return root


def _read(root, name):
    path = evidence._path(root, name)
    require(path.stat().st_size <= evidence.MAX_BYTES, 'ARTIFACT_SIZE_LIMIT')
    return _raw(path.read_bytes())


def _write(root, name, raw):
    _raw(raw)
    path = root / name
    path.parent.mkdir(exist_ok=True)
    require(not evidence._reparse(path.parent), 'REPARSE_ARTIFACT_REJECTED')
    with path.open('xb') as stream:
        stream.write(raw)
    return {'path': name, 'sha256': review.sha(raw)}


def _receipt(state, **extra):
    return {'method': METHOD, 'run_sha256': state['run_sha256'],
            'head_sha256': state['head_sha256'], 'protocol': copy.deepcopy(state['run']['protocol']),
            **_workflow(state), **extra}


def create_run(root, request_bytes, sources, units, adopted_at, max_corrections=2, *, _bootstrap_manifest=None):
    """Freeze exact request/sources and assistant-authored answer_review units.

    ``root`` must not exist, its parent must exist, and its resolved path must
    be outside this skill. Units use UTF-8 byte spans in request_bytes.
    An unsupported requirement remains in this roster.
    """
    _raw(request_bytes)
    require(bool(request_bytes.decode('utf8').strip()), 'NONEMPTY_REQUEST_REQUIRED')
    require(type(sources) is dict and len(sources) <= review.MAX_SOURCES, 'BOUNDED_SOURCES')
    require(type(max_corrections) is int and 0 <= max_corrections <= 5, 'MAX_CORRECTIONS_0_TO_5')
    evidence.clock(adopted_at)
    for sid, raw in sources.items():
        review.identifier(sid); _raw(raw)
    require(sum(len(raw) for raw in sources.values()) + len(request_bytes) < review.MAX_TOTAL // 2,
            'SOURCE_CORPUS_SIZE_LIMIT')
    root = Path(root).absolute()
    require(root.parent.is_dir() and not root.exists(), 'FRESH_RUN_DIRECTORY_REQUIRED')
    # Validate every existing ancestor before creating any file.
    require(not any(evidence._reparse(p) for p in (root.parent, *root.parent.parents)),
            'REPARSE_EVIDENCE_ROOT_REJECTED')
    require(not root.resolve().is_relative_to(SKILL_ROOT), 'OUTPUT_MUST_BE_OUTSIDE_INSTALLED_SKILL')
    require(not any(p.lower() == 'private-runtime' or p.lower() == 'sec-contact.json'
                    or (p.lower().startswith('private-') and 'config' in p.lower())
                    for p in root.parts), 'PRIVATE_CONTACT_CONFIGURATION_EXCLUDED')
    root.mkdir()
    request = _write(root, 'request.md', request_bytes)
    source_refs = [{'id': sid, 'artifact': _write(root, 'sources/' + sid + '.bin', raw)}
                   for sid, raw in sources.items()]
    plan = {'schema_version': 1, 'id': 'research-review', 'adopted_at': adopted_at,
            'original_request': request, 'sources': source_refs, 'units': copy.deepcopy(units),
            'max_material_error_units': 0}
    plan_raw = encode(plan)
    review.protocol(plan_raw, review.Reader(root))
    protocol_ref = _write(root, 'protocol.json', plan_raw)
    run = {'schema_version': 1, 'method': METHOD, 'protocol': protocol_ref,
           'max_corrections': max_corrections, 'delivery_scope': 'complete_user_delivery'}
    if _bootstrap_manifest is not None:
        run['bootstrap'] = {'method': BOOTSTRAP_METHOD,
                            'manifest': _write(root, 'bootstrap-manifest.json', _bootstrap_manifest),
                            'request_sha256': review.sha(request_bytes), 'whole_request_unit_id': WHOLE_REQUEST_ID}
    _write(root, 'run.json', encode(run))
    return _receipt(verify(root))


def _disposition(assessment):
    findings = [copy.deepcopy(row) for row in assessment['reviews'] if row['status'] != 'SATISFIED']
    missing = assessment['missing_unit_ids']
    if not assessment['declared_review_complete']:
        status = 'REVIEW_INCOMPLETE'
    elif assessment['escalation_required_by_review_policy']:
        status = 'DELIVERED_WITH_LIMITATIONS'
    else:
        status = 'REVIEWED_DELIVERY'
    return {'final_status': status, 'open_findings': findings, 'missing_unit_ids': copy.deepcopy(missing),
            'whole_answer_correctness_verified': False,
            'semantic_judgments_are_reviewer_declarations': True}


def _notice(state):
    assessed = state['reviews'][-1]['assessment']
    disposition = _disposition(assessed)
    lines = ['# Review and delivery notice', '', 'Status: ' + disposition['final_status'], '',
             'Reviewer mode: ' + state['reviews'][-1]['reviewer_mode'] + ' (declared, not authenticated).', '',
             'Read this notice alongside the exact retained complete draft. Review judgments are native assistant declarations; '
             'the file checker does not certify correctness or source authenticity.', '']
    if disposition['open_findings'] or disposition['missing_unit_ids']:
        lines += ['The following material findings remain unresolved. Claims at the listed answer spans are unreliable '
                  'or unsupported as described; do not treat them as verified conclusions.', '']
        requirements = {unit['id']: unit['requirement'] for unit in assessed['units']}
        for row in disposition['open_findings']:
            lines += ['- ' + row['unit_id'] + ': ' + row['status'] + '. ' + requirements[row['unit_id']],
                      '  Finding: ' + row['rationale'],
                      '  Exact answer locators: ' + json.dumps(row['answer_spans'], ensure_ascii=False)]
        for uid in disposition['missing_unit_ids']:
            lines += ['- ' + uid + ': UNREVIEWED. ' + requirements[uid] + ' No unit review was retained.']
    else:
        lines += ['No open findings were declared in the frozen review roster. This does not prove that the '
                  'roster captured every semantic requirement or that the answer is wholly correct.']
    return ('\n'.join(lines) + '\n').encode('utf8')


def verify(root, expected_head_sha256=None):
    """Replay the actual verifier and all preserved events; optionally bind a caller pin."""
    root = _root(root)
    run_raw = _read(root, 'run.json'); run = evidence._json(run_raw)
    fields = ('schema_version', 'method', 'protocol', 'max_corrections', 'delivery_scope')
    evidence.exact(run, fields + (('bootstrap',) if 'bootstrap' in run else ()), 'revision_run')
    require(type(run['schema_version']) is int and run['schema_version'] == 1
            and run['method'] == METHOD and run['delivery_scope'] == 'complete_user_delivery', 'REVISION_RUN_METHOD')
    require(type(run['max_corrections']) is int and 0 <= run['max_corrections'] <= 5, 'MAX_CORRECTIONS_0_TO_5')
    reader = review.Reader(root)
    plan, _ = review.protocol(reader.read(run['protocol']), reader)
    if 'bootstrap' in run:
        _bootstrap_check(run['bootstrap'], plan, reader)
    require(plan['max_material_error_units'] == 0, 'ZERO_MATERIAL_ERROR_REVIEW_POLICY_REQUIRED')
    known = {'run.json', *reader.files}
    state = {'run': run, 'run_sha256': review.sha(run_raw), 'head_sha256': review.sha(run_raw),
             'drafts': [], 'reviews': [], 'final': None, 'event_count': 0}
    paths = list(root.rglob('*'))
    require(len(paths) <= 1024, 'RUN_ARTIFACT_COUNT_LIMIT')
    require(all(not evidence._reparse(p) for p in paths), 'REPARSE_ARTIFACT_REJECTED')
    event_names = sorted(p.relative_to(root).as_posix() for p in paths if p.is_file() and p.parent == root / 'events')
    require(len(event_names) <= 2 * (1 + run['max_corrections']) + 1, 'CORRECTION_ATTEMPT_LIMIT')
    inputs = [plan['original_request']] + [s['artifact'] for s in plan['sources']]
    for seq, name in enumerate(event_names, 1):
        require(name == 'events/%06d.json' % seq, 'EVENT_SEQUENCE_GAP')
        raw = _read(root, name); event = evidence._json(raw)
        evidence.exact(event, ('schema_version', 'sequence', 'previous_sha256', 'run_sha256', 'kind', 'payload'), 'revision_event')
        require(type(event['schema_version']) is int and event['schema_version'] == 1
                and type(event['sequence']) is int and event['sequence'] == seq, 'EVENT_SEQUENCE')
        require(event['previous_sha256'] == state['head_sha256'] and event['run_sha256'] == state['run_sha256'],
                'EVENT_CHAIN_MISMATCH')
        require(state['final'] is None, 'FINAL_SELECTION_IS_TERMINAL')
        payload = event['payload']; kind = event['kind']
        if kind == 'draft':
            evidence.exact(payload, ('draft_id', 'parent_draft_id', 'delivery'), 'revision_draft')
            count = len(state['drafts'])
            require(count <= run['max_corrections'], 'CORRECTION_ATTEMPT_LIMIT')
            require(payload['draft_id'] == 'draft-%03d' % count, 'DRAFT_SEQUENCE')
            require(payload['parent_draft_id'] == (state['drafts'][-1]['draft_id'] if count else None), 'DRAFT_PARENT_MISMATCH')
            require(not count or len(state['reviews']) == count, 'PARENT_REVIEW_REQUIRED')
            pair = payload['delivery']
            require(pair.get('kind') == 'authored_pair' and pair.get('original_inputs') == inputs, 'COMPLETE_AUTHORED_PAIR_REQUIRED')
            prefix = 'drafts/%03d/' % count
            require(pair['first_response']['path'] == prefix + 'first-response.md'
                    and pair['response']['path'] == prefix + 'response.json', 'COMPLETE_DRAFT_PATHS_REQUIRED')
            review.authored_pair(pair, reader)
            require(evidence.clock(plan['adopted_at']) <= evidence.clock(pair['captured_at']), 'DRAFT_CLOCK_ORDER')
            if count:
                require(evidence.clock(state['reviews'][-1]['document']['reviewed_at']) <= evidence.clock(pair['captured_at']),
                        'REVISION_PRECEDES_PARENT_REVIEW')
            state['drafts'].append(payload)
        elif kind == 'review':
            evidence.exact(payload, ('draft_id', 'reviewer_mode', 'document', 'assessment'), 'revision_review')
            require(state['drafts'] and len(state['reviews']) < len(state['drafts']), 'ONE_REVIEW_PER_DRAFT')
            require(payload['draft_id'] == state['drafts'][-1]['draft_id'], 'REVIEW_LATEST_DRAFT_REQUIRED')
            require(payload['reviewer_mode'] in MODES, 'NATIVE_REVIEWER_MODE_REQUIRED')
            document = payload['document']
            require(document['delivery'] == state['drafts'][-1]['delivery'], 'EXACT_COMPLETE_DRAFT_REVIEW_REQUIRED')
            require(document['protocol'] == run['protocol'], 'UNCHANGED_REVIEW_PROTOCOL_REQUIRED')
            require(document['reviewer']['kind'] == 'automated', 'NATIVE_ASSISTANT_REVIEW_REQUIRED')
            assessed = review.assess(document, root, run['protocol']['sha256'])
            require(assessed == payload['assessment'], 'REVIEW_ASSESSMENT_REPLAY_MISMATCH')
            state['reviews'].append(payload)
        elif kind == 'selection':
            evidence.exact(payload, ('draft_id', 'delivery', 'review_event_sha256', 'disposition', 'delivery_notice'), 'revision_selection')
            require(state['drafts'] and len(state['reviews']) == len(state['drafts']), 'LATEST_DRAFT_REVIEW_REQUIRED')
            require(payload['draft_id'] == state['drafts'][-1]['draft_id']
                    and payload['delivery'] == state['drafts'][-1]['delivery'], 'EXACT_LATEST_DELIVERY_REQUIRED')
            require(payload['review_event_sha256'] == state['head_sha256'], 'LATEST_REVIEW_PIN_REQUIRED')
            require(payload['disposition'] == _disposition(state['reviews'][-1]['assessment']), 'OPEN_FINDINGS_MUST_BE_RETAINED')
            require(payload['delivery_notice']['path'] == 'delivery-notice.md', 'DELIVERY_NOTICE_PATH_REQUIRED')
            require(reader.read(payload['delivery_notice']) == _notice(state), 'EXACT_DELIVERY_NOTICE_REQUIRED')
            state['final'] = payload
        else:
            raise ValueError('UNKNOWN_REVISION_EVENT')
        known.add(name); state['event_count'] = seq; state['head_sha256'] = review.sha(raw)
    known.update(reader.files)
    actual = {p.relative_to(root).as_posix() for p in paths if p.is_file()}
    require(actual == known, 'UNTRACKED_OR_MISSING_RUN_ARTIFACTS')
    reader.unchanged()
    require(_read(root, 'run.json') == run_raw, 'RUN_CHANGED_DURING_VERIFICATION')
    if expected_head_sha256 is not None:
        evidence.sha(expected_head_sha256)
        require(state['head_sha256'] == expected_head_sha256, 'EXTERNAL_HEAD_PIN_MISMATCH')
    state.update(_workflow(state))
    return state


def _append(root, state, kind, payload):
    event = {'schema_version': 1, 'sequence': state['event_count'] + 1,
             'previous_sha256': state['head_sha256'], 'run_sha256': state['run_sha256'],
             'kind': kind, 'payload': payload}
    ref = _write(Path(root), 'events/%06d.json' % event['sequence'], encode(event))
    return _receipt(verify(root, ref['sha256']), **copy.deepcopy(payload))


def freeze_draft(root, markdown_bytes, response_bytes, captured_at, *, expected_head_sha256, parent_draft_id=None):
    """Retain both complete user-facing artifacts, never just an annex/excerpt."""
    state = verify(root, expected_head_sha256)
    require(state['final'] is None, 'FINAL_SELECTION_IS_TERMINAL')
    count = len(state['drafts'])
    require(count <= state['run']['max_corrections'], 'CORRECTION_ATTEMPT_LIMIT')
    require(parent_draft_id == (state['drafts'][-1]['draft_id'] if count else None), 'DRAFT_PARENT_MISMATCH')
    require(len(state['reviews']) == count, 'PARENT_REVIEW_REQUIRED')
    _raw(markdown_bytes); _raw(response_bytes)
    require(bool(markdown_bytes.decode('utf8').strip()), 'NONEMPTY_AUTHORED_MARKDOWN')
    require(type(evidence._json(response_bytes)) is dict and bool(evidence._json(response_bytes)), 'AUTHORED_RESPONSE_OBJECT_REQUIRED')
    plan, _ = review.protocol(review.Reader(root).read(state['run']['protocol']), review.Reader(root))
    require(evidence.clock(plan['adopted_at']) <= evidence.clock(captured_at), 'DRAFT_CLOCK_ORDER')
    if count:
        require(evidence.clock(state['reviews'][-1]['document']['reviewed_at']) <= evidence.clock(captured_at),
                'REVISION_PRECEDES_PARENT_REVIEW')
    prefix = 'drafts/%03d/' % count
    # Parent is fixed, generated and private to this run. No caller output paths.
    (Path(root) / 'drafts').mkdir(exist_ok=True)
    (Path(root) / prefix).mkdir(exist_ok=False)
    pair = {'kind': 'authored_pair', 'first_response': _write(Path(root), prefix + 'first-response.md', markdown_bytes),
            'response': _write(Path(root), prefix + 'response.json', response_bytes),
            'original_inputs': [plan['original_request']] + [s['artifact'] for s in plan['sources']],
            'captured_at': captured_at}
    return _append(root, state, 'draft', {'draft_id': 'draft-%03d' % count,
                   'parent_draft_id': parent_draft_id, 'delivery': pair})


def record_review(root, review_document, *, reviewer_mode, expected_head_sha256):
    """Store actual host-assistant review declarations and real binding assessment."""
    state = verify(root, expected_head_sha256)
    require(state['final'] is None, 'FINAL_SELECTION_IS_TERMINAL')
    require(state['drafts'] and len(state['reviews']) < len(state['drafts']), 'ONE_REVIEW_PER_DRAFT')
    require(reviewer_mode in MODES, 'NATIVE_REVIEWER_MODE_REQUIRED')
    document = copy.deepcopy(review_document)
    require(document['delivery'] == state['drafts'][-1]['delivery'], 'EXACT_COMPLETE_DRAFT_REVIEW_REQUIRED')
    require(document['protocol'] == state['run']['protocol'], 'UNCHANGED_REVIEW_PROTOCOL_REQUIRED')
    require(document['reviewer']['kind'] == 'automated', 'NATIVE_ASSISTANT_REVIEW_REQUIRED')
    assessed = review.assess(document, root, state['run']['protocol']['sha256'])
    return _append(root, state, 'review', {'draft_id': state['drafts'][-1]['draft_id'],
                   'reviewer_mode': reviewer_mode, 'document': document, 'assessment': assessed})


def select_final(root, draft_id, *, expected_head_sha256):
    """Select exact latest reviewed delivery, retaining unresolved/incomplete findings."""
    state = verify(root, expected_head_sha256)
    require(state['final'] is None, 'FINAL_SELECTION_IS_TERMINAL')
    require(state['drafts'] and len(state['reviews']) == len(state['drafts']), 'LATEST_DRAFT_REVIEW_REQUIRED')
    require(draft_id == state['drafts'][-1]['draft_id'], 'EXACT_LATEST_DELIVERY_REQUIRED')
    return _append(root, state, 'selection', {'draft_id': draft_id,
                   'delivery': state['drafts'][-1]['delivery'], 'review_event_sha256': state['head_sha256'],
                   'disposition': _disposition(state['reviews'][-1]['assessment']),
                   'delivery_notice': _write(Path(root), 'delivery-notice.md', _notice(state))})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('bootstrap', 'create', 'freeze', 'review', 'final', 'verify'))
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--job', type=Path, help='Explicit bounded JSON; byte inputs use UTF-8 text fields.')
    parser.add_argument('--expected-head-sha256')
    parser.add_argument('--request', type=Path)
    parser.add_argument('--request-sha256')
    parser.add_argument('--source-manifest', type=Path)
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--adopted-at')
    parser.add_argument('--max-corrections', type=int)
    parser.add_argument('--units', type=Path, help='Optional native-authored material-unit list, before protocol freeze.')
    parser.add_argument('--units-sha256')
    args = parser.parse_args(argv)
    try:
        bootstrap_args = (args.request, args.request_sha256, args.source_manifest, args.manifest_sha256,
                          args.source_root, args.adopted_at, args.max_corrections, args.units, args.units_sha256)
        if args.action == 'bootstrap':
            require(args.job is None and args.expected_head_sha256 is None, 'BOOTSTRAP_OPTION_CONFLICT')
            require(all(x is not None for x in bootstrap_args[:6]), 'PINNED_BOOTSTRAP_INPUTS_REQUIRED')
            require((args.units is None) == (args.units_sha256 is None), 'MATERIAL_UNITS_EXTERNAL_PIN_REQUIRED')
            units = None
            if args.units is not None:
                _, unit_raw = _pinned_input(args.units, args.units_sha256)
                units = evidence._json(unit_raw)
            result = bootstrap_run(args.run, args.request, args.request_sha256, args.source_manifest,
                                   args.manifest_sha256, args.source_root, args.adopted_at,
                                   material_units=units, max_corrections=2 if args.max_corrections is None else args.max_corrections)
            print(encode(result).decode('utf8'), end='')
            return 0
        require(all(x is None for x in bootstrap_args), 'BOOTSTRAP_OPTIONS_REQUIRE_BOOTSTRAP_ACTION')
        job = {}
        if args.job:
            job = evidence._json(_read(args.job.absolute().parent, args.job.name))
        if args.action == 'create':
            evidence.exact(job, ('request', 'sources', 'units', 'adopted_at', 'max_corrections'), 'create_job')
            result = create_run(args.run, job['request'].encode('utf8'),
                                {sid: raw.encode('utf8') for sid, raw in job['sources'].items()},
                                job['units'], job['adopted_at'], job['max_corrections'])
        elif args.action == 'verify':
            result = verify(args.run, args.expected_head_sha256)
        else:
            require(args.expected_head_sha256 is not None, 'EXTERNAL_HEAD_PIN_REQUIRED')
            if args.action == 'freeze':
                evidence.exact(job, ('markdown', 'response', 'captured_at', 'parent_draft_id'), 'freeze_job')
                result = freeze_draft(args.run, job['markdown'].encode('utf8'), job['response'].encode('utf8'),
                                      job['captured_at'], expected_head_sha256=args.expected_head_sha256,
                                      parent_draft_id=job['parent_draft_id'])
            elif args.action == 'review':
                evidence.exact(job, ('review_document', 'reviewer_mode'), 'review_job')
                result = record_review(args.run, job['review_document'], reviewer_mode=job['reviewer_mode'],
                                       expected_head_sha256=args.expected_head_sha256)
            else:
                evidence.exact(job, ('draft_id',), 'final_job')
                result = select_final(args.run, job['draft_id'], expected_head_sha256=args.expected_head_sha256)
        print(encode(result).decode('utf8'), end='')
        return 0
    except (ValueError, KeyError, TypeError, OSError, UnicodeError, OverflowError, AttributeError) as error:
        print(json.dumps({'status': 'INVALID_REVISION_EVIDENCE', 'error': str(error)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
