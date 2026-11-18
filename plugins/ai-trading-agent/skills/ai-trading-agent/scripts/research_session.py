"""On-demand assistant bridge from exact ordinary requests to reviewed research.

The host interprets the request, obtains permitted evidence, selects calculations
and authors/reviews the answer. This module retains those decisions and invokes
the existing producers. It contains no natural-language parser or model backend.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ('earnings_guidance', 'event_research')
MAX_BYTES = 32 * 1024 * 1024


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identifier(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value),
            'SAFE_IDENTIFIER_REQUIRED')
    return value


def clock(value):
    require(type(value) is str, 'AWARE_TIMESTAMP_REQUIRED')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.utcoffset() is not None, 'AWARE_TIMESTAMP_REQUIRED')
    return value


def local(value):
    require(not str(value).startswith(('\\\\', '//')) and '://' not in str(value), 'LOCAL_PATH_REQUIRED')
    path = Path(value).absolute()
    require(not any(p.is_symlink() or (p.exists() and getattr(p.stat(), 'st_file_attributes', 0) &
                    getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))
                    for p in (path, *path.parents)), 'REPARSE_PATH_REJECTED')
    return path.resolve()


def read(path):
    path = local(path)
    require(path.is_file() and path.stat().st_size <= MAX_BYTES, 'BOUNDED_EXPLICIT_FILE_REQUIRED')
    raw = path.read_bytes()
    require(len(raw) <= MAX_BYTES, 'SOURCE_SIZE_LIMIT')
    return raw


def write(root, name, raw):
    target = member(root, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target = member(root, name)
    with target.open('xb') as stream:
        stream.write(raw)
    return {'path': name, 'sha256': sha(raw)}


def load(path):
    return json.loads(read(path).decode('utf8'))


def member(root, name):
    require(type(name) is str and bool(name) and '\\' not in name and ':' not in name and
            not name.startswith('/') and all(part not in ('', '.', '..') for part in name.split('/')),
            'SAFE_SESSION_MEMBER_REQUIRED')
    path = local(root / name)
    require(path.is_relative_to(root), 'SESSION_MEMBER_ESCAPE')
    return path


def session(root, expected_session_sha256):
    root = local(root)
    require(root.is_dir() and not root.is_relative_to(ROOT), 'PRIVATE_SESSION_REQUIRED')
    manifest_raw = read(root / 'session.json')
    require(sha(manifest_raw) == expected_session_sha256, 'EXTERNAL_SESSION_PIN_MISMATCH')
    manifest = json.loads(manifest_raw)
    for ref in [manifest['original_request'], *[s['artifact'] for s in manifest['sources']]]:
        require(sha(read(member(root, ref['path']))) == ref['sha256'], 'SESSION_INPUT_CHANGED')
    return root, manifest


def readable_source(raw, row):
    """Text-span review cannot represent original binary document inspection."""
    if raw.startswith((b'%PDF-', b'PK\x03\x04', b'\x89PNG', b'GIF8', b'\xff\xd8')) or b'\x00' in raw:
        return False
    if Path(row['original_filename']).suffix.lower() in ('.pdf', '.png', '.jpg', '.jpeg', '.zip', '.docx', '.xlsx', '.pptx'):
        return False
    try:
        raw.decode('utf8')
    except UnicodeError:
        return False
    return True


def review_sources(root, manifest):
    """Use explicit provenance-only proxies for binaries; never invent spans."""
    rows = {row['id']: row for row in manifest['sources']}
    originals = {sid: read(member(root, row['artifact']['path'])) for sid, row in rows.items()}
    sources, projections, unprojected = {}, {}, set()
    for sid, row in rows.items():
        raw = originals[sid]
        if readable_source(raw, row):
            sources[sid] = raw
            continue
        projection = row.get('metadata', {}).get('readable_projection_source_id')
        if projection is not None:
            require(type(projection) is str and projection in rows and projection != sid,
                    'EXPLICIT_READABLE_PROJECTION_SOURCE_REQUIRED')
            require(readable_source(originals[projection], rows[projection]) and
                    bool(originals[projection].decode('utf8').strip()), 'UTF8_READABLE_PROJECTION_REQUIRED')
            projections[sid] = projection
        else:
            unprojected.add(sid)
        sources[sid] = encode({
            'representation': 'PROVENANCE_ONLY_NOT_ORIGINAL_BINARY_CONTENT',
            'source_id': sid, 'original_filename': row['original_filename'],
            'retained_original': {'session_member': row['artifact']['path'],
                                  'sha256': sha(raw), 'byte_length': len(raw)},
            'readable_projection_source_id': projection,
            'projection_status': 'explicit_host_mapping_not_content_verified' if projection else 'UNAVAILABLE',
            'native_inspection_limits': [
                'A REVIEWED span in this manifest reviews provenance metadata only, never original binary content.',
                'The host must inspect the binary with native tools and retain a readable projection with page/table locators.',
                'Projection fidelity, completeness and visual inspection remain native reviewer declarations, not helper verification.',
                'Without a linked readable projection the affected evidence coverage remains unsupported or unreviewed.']})
    return sources, projections, unprojected


def start_session(root, original_request, *, workflow, sources, tasks, as_of,
                  acquisition_policy='Use permitted free primary sources first; disclose access limits.'):
    """Retain exact UTF-8 prompt and explicitly named files, never scan a folder.

    sources are assistant-authored {id,path,role,origin,metadata?,derived_from?}.
    tasks are {id,requirement,request_excerpt,required_source_ids}; each excerpt
    must occur exactly once in the original request. Missing evidence uses [].
    """
    root = local(root)
    require(not root.exists() and root.parent.is_dir() and not root.is_relative_to(ROOT),
            'NEW_PRIVATE_SESSION_REQUIRED')
    require(type(original_request) is bytes and 0 < len(original_request) <= MAX_BYTES,
            'EXACT_REQUEST_BYTES_REQUIRED')
    text = original_request.decode('utf8')
    require(text.strip() and workflow in WORKFLOWS, 'SUPPORTED_WORKFLOW_REQUIRED')
    clock(as_of)
    require(type(acquisition_policy) is str and acquisition_policy.strip(), 'ACQUISITION_POLICY_REQUIRED')
    require(type(sources) is list and len(sources) <= 100, 'BOUNDED_SOURCE_LIST_REQUIRED')
    # Initialize before source reads so a missing/invalid explicit source leaves
    # the exact original request and a failure receipt for the next host turn.
    root.mkdir()
    request_ref = write(root, 'request.txt', original_request)
    write(root, 'host-plan.json', encode({'workflow': workflow, 'sources': sources, 'tasks': tasks,
                                        'as_of': as_of, 'acquisition_policy': acquisition_policy}))
    try:
        ids, rows = set(), []
        for spec in sources:
            require(type(spec) is dict and set(spec) <= {'id', 'path', 'role', 'origin', 'metadata', 'derived_from'},
                    'SOURCE_FIELDS')
            sid = identifier(spec['id'])
            require(sid not in ids and not sid.startswith('session-'), 'UNIQUE_SOURCE_ID_REQUIRED')
            ids.add(sid)
            require(type(spec['role']) is str and spec['role'].strip(), 'SOURCE_ROLE_REQUIRED')
            require(spec['origin'] in ('supplied', 'host_collected', 'host_derived'), 'SOURCE_ORIGIN_REQUIRED')
            require(type(spec.get('metadata', {})) is dict, 'SOURCE_METADATA_OBJECT_REQUIRED')
            raw = read(spec['path'])
            row = {k: v for k, v in spec.items() if k != 'path'}
            row.update(original_filename=Path(spec['path']).name,
                       artifact=write(root, f'sources/{sid}.bin', raw))
            rows.append(row)
        for row in rows:
            derived = row.get('derived_from', [])
            require(type(derived) is list and len(derived) == len(set(derived)) and
                    set(derived) <= ids and row['id'] not in derived, 'DERIVED_SOURCE_IDS')
            require(row['origin'] != 'host_derived' or bool(derived), 'DERIVED_SOURCE_LINEAGE_REQUIRED')
        by_id = {row['id']: row for row in rows}
        completed = set()
        def lineage(sid, active):
            require(sid not in active, 'CYCLIC_SOURCE_LINEAGE')
            if sid in completed:
                return
            active.add(sid)
            for parent in by_id[sid].get('derived_from', []):
                lineage(parent, active)
            active.remove(sid)
            completed.add(sid)
        for sid in by_id:
            lineage(sid, set())
        require(type(tasks) is list and 0 < len(tasks) <= 100, 'MATERIAL_TASKS_REQUIRED')
        units, seen = [], set()
        for task in tasks:
            require(type(task) is dict and set(task) == {'id', 'requirement', 'request_excerpt', 'required_source_ids'},
                    'TASK_FIELDS')
            uid = identifier(task['id'])
            require(uid not in seen and uid != 'session-whole-answer', 'UNIQUE_TASK_ID_REQUIRED'); seen.add(uid)
            excerpt = task['request_excerpt']
            require(type(excerpt) is str and excerpt.strip() and text.count(excerpt) == 1,
                    'UNIQUE_LITERAL_REQUEST_EXCERPT_REQUIRED')
            require(type(task['requirement']) is str and task['requirement'].strip(), 'TASK_REQUIREMENT_REQUIRED')
            required_ids = task['required_source_ids']
            require(type(required_ids) is list and len(set(required_ids)) == len(required_ids) and
                    set(required_ids) <= ids, 'TASK_SOURCE_IDS')
            start = len(text[:text.index(excerpt)].encode('utf8'))
            units.append({'id': uid, 'requirement': task['requirement'], 'required_source_ids': required_ids,
                          'request_spans': [{'start_byte': start, 'end_byte': start + len(excerpt.encode('utf8')),
                                             'sha256': sha(excerpt.encode('utf8'))}]})
        manifest = {'schema_version': 1, 'workflow': workflow, 'as_of': as_of,
                    'original_request': request_ref, 'sources': rows, 'units': units,
                    'acquisition_policy': acquisition_policy,
                    'interpretation': 'Host-authored scope and source identities; not proof of complete prompt understanding.'}
        # Validate only explicitly linked projections, with originals already
        # retained. Missing projections remain a deliverable research limitation.
        review_sources(root, manifest)
        manifest_ref = write(root, 'session.json', encode(manifest))
        return {'session': manifest, 'session_sha256': manifest_ref['sha256']}
    except Exception as exc:
        write(root, 'start-failure.json', encode({'type': type(exc).__name__, 'reason': str(exc)}))
        raise


def prepare_packet(root, *, expected_session_sha256, dispositions, filings=None, calculation=None):
    """Extract selected filings and execute an assistant-prepared workbench.

    dispositions explicitly address every material task: {id,status,reason,
    evidence_ids}; status is supported/limited/unsupported and remains a host
    judgment. A calculation uses the existing full workbench request with every
    job bound via inputs_source to '<retained-source-id>.bin'.
    """
    root, manifest = session(root, expected_session_sha256)
    require(not (root / 'packet-plan.json').exists(), 'PACKET_ALREADY_ATTEMPTED')
    filings = [] if filings is None else filings
    write(root, 'packet-plan.json', encode({'dispositions': dispositions, 'filings': filings,
                                          'calculation': calculation}))
    try:
        sources = {s['id']: s for s in manifest['sources']}
        require(type(dispositions) is list and len(dispositions) == len(manifest['units']) and
                {r['id'] for r in dispositions} == {u['id'] for u in manifest['units']},
                'EXACT_MATERIAL_TASK_DISPOSITIONS_REQUIRED')
        for row in dispositions:
            require(set(row) == {'id', 'status', 'reason', 'evidence_ids'} and
                    row['status'] in ('supported', 'limited', 'unsupported') and
                    type(row['reason']) is str and row['reason'].strip(), 'TASK_DISPOSITION_FIELDS')
            require(type(row['evidence_ids']) is list and set(row['evidence_ids']) <= set(sources),
                    'DISPOSITION_SOURCE_IDS')
            require(row['status'] != 'supported' or bool(row['evidence_ids']), 'SUPPORTED_TASK_NEEDS_EVIDENCE')
        extraction, errors = [], []
        require(type(filings) is list, 'FILING_JOBS_LIST_REQUIRED')
        seen = set()
        for job in filings:
            sid = job['source_id']
            require(sid in sources and sid not in seen, 'EXPLICIT_UNIQUE_FILING_SOURCE_REQUIRED'); seen.add(sid)
            require(set(job) == {'source_id', 'options'} and type(job['options']) is dict and
                    set(job['options']) <= {'form_type', 'source_url', 'accession', 'accepted_at',
                                           'retrieved_at', 'content_type', 'passage_terms'}, 'FILING_OPTIONS')
            try:
                import filing_documents
                report = filing_documents.extract_document(read(root / sources[sid]['artifact']['path']),
                                                           source_id=sid, **job['options'])
                ref = write(root, f'filings/{sid}.json', encode(report))
                extraction.append({'source_id': sid, 'artifact': ref, 'status': 'EXTRACTED_NOT_SEMANTICALLY_CERTIFIED'})
            except Exception as exc:
                error = {'source_id': sid, 'type': type(exc).__name__, 'reason': str(exc)}
                write(root, f'filings/{sid}-failure.json', encode(error)); errors.append(error)
        completion, calculation_ref, calculation_outputs = None, None, []
        if calculation is not None:
            import research_workflow
            require(type(calculation) is dict and calculation.get('contract', {}).get('prompt') ==
                    read(root / 'request.txt').decode('utf8'), 'CALCULATION_MUST_BIND_EXACT_ORIGINAL_REQUEST')
            jobs = calculation.get('jobs')
            require(type(jobs) is list and bool(jobs), 'CALCULATION_JOBS_REQUIRED')
            inputs, roles = root / 'calculation-inputs', {}
            inputs.mkdir()
            for job in jobs:
                require(set(job) == {'id', 'operation', 'inputs_source'}, 'SOURCE_BOUND_CALCULATION_JOB_REQUIRED')
                ref = job['inputs_source']
                require(type(ref) is dict and set(ref) == {'path', 'sha256', 'pointer'}, 'CALCULATION_INPUT_REFERENCE')
                sid = ref['path'][:-4] if type(ref['path']) is str and ref['path'].endswith('.bin') else None
                require(sid in sources and ref['path'] == sid + '.bin', 'RETAINED_CALCULATION_SOURCE_ONLY')
                raw = read(root / sources[sid]['artifact']['path'])
                require(sha(raw) == ref['sha256'], 'CALCULATION_SOURCE_HASH_MISMATCH')
                if ref['path'] not in roles:
                    write(inputs, ref['path'], raw)
                roles[ref['path']] = sources[sid]['role']
            write(inputs, 'request.json', encode(calculation))
            completion = research_workflow.execute(inputs / 'request.json', root / 'calculation',
                                                  'assistant_prepared_original_request_bound_jobs', roles)
            calculation_ref = {'path': 'calculation/completion.json',
                               'sha256': sha(read(root / 'calculation/completion.json'))}
            for name in ('answer-facts.json', 'run/result.json', 'run/report.md'):
                target = root / 'calculation' / name
                if target.is_file():
                    calculation_outputs.append({'path': 'calculation/' + name, 'sha256': sha(read(target))})
        packet = {'schema_version': 1, 'workflow': manifest['workflow'], 'as_of': manifest['as_of'],
                  'original_request': manifest['original_request'], 'sources': manifest['sources'],
                  'material_tasks': dispositions, 'filing_extractions': extraction, 'filing_errors': errors,
                  'calculation_completion': completion, 'calculation_receipt': calculation_ref,
                  'calculation_outputs': calculation_outputs,
                  'status': 'EVIDENCE_WITH_LIMITATIONS' if errors or any(d['status'] != 'supported' for d in dispositions)
                            or (completion and completion['status'] != 'COMPLETED_LOCAL_WORKFLOW') else 'EVIDENCE_PREPARED',
                  'limits': ['The host authors the complete readable answer and reviews it against the original request.',
                             'Scope, source identity, extraction semantics and investment judgments remain host-reviewed.',
                             'Replay of calculations does not establish arbitrary prose correctness or full evidence coverage.']}
        packet_ref = write(root, 'packet.json', encode(packet))
        return {'packet': packet, 'packet_sha256': packet_ref['sha256']}
    except Exception as exc:
        write(root, 'packet-failure.json', encode({'type': type(exc).__name__, 'reason': str(exc)}))
        raise


def start_review(root, *, expected_session_sha256, expected_packet_sha256, adopted_at, max_corrections=2,
                 additional_review_sources=None):
    """Bind all original sources plus the actual packet/extractions/annex to review."""
    import research_revision
    root, manifest = session(root, expected_session_sha256)
    packet_raw = read(root / 'packet.json')
    require(sha(packet_raw) == expected_packet_sha256, 'EXTERNAL_PACKET_PIN_MISMATCH')
    packet = json.loads(packet_raw)
    sources, projections, unprojected = review_sources(root, manifest)
    sources['session-packet'] = packet_raw
    for row in packet['filing_extractions']:
        ref = row['artifact']; raw = read(member(root, ref['path']))
        require(sha(raw) == ref['sha256'], 'PACKET_EXTRACTION_CHANGED')
        sources['session-filing-' + row['source_id']] = raw
    if packet['calculation_receipt']:
        ref = packet['calculation_receipt']; raw = read(member(root, ref['path']))
        require(sha(raw) == ref['sha256'], 'CALCULATION_RECEIPT_CHANGED')
        sources['session-calculation-completion'] = raw
        if any(ref['path'] == 'calculation/answer-facts.json' for ref in packet['calculation_outputs']):
            import research_workflow
            research_workflow.verify(root / 'calculation/run')
        for index, ref in enumerate(packet['calculation_outputs']):
            raw = read(member(root, ref['path']))
            require(sha(raw) == ref['sha256'], 'CALCULATION_OUTPUT_CHANGED')
            sources[f'session-calculation-output-{index}'] = raw
    if additional_review_sources is not None:
        require(type(additional_review_sources) is dict and len(additional_review_sources) <= 16,
                'BOUNDED_ADDITIONAL_REVIEW_SOURCES_REQUIRED')
        total = 0
        for sid, raw in additional_review_sources.items():
            identifier(sid)
            require(sid.startswith('extra-') and sid not in sources, 'ADDITIONAL_REVIEW_SOURCE_ID_CONFLICT')
            require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,
                    'ADDITIONAL_REVIEW_SOURCE_BYTES_REQUIRED')
            total += len(raw)
            require(total <= MAX_BYTES, 'ADDITIONAL_REVIEW_SOURCE_SIZE_LIMIT')
            require(readable_source(raw, {'original_filename': sid + '.txt'}),
                    'ADDITIONAL_REVIEW_SOURCE_MUST_BE_READABLE')
            sources[sid] = raw
    units = []
    for unit in manifest['units']:
        item = dict(unit)
        required = list(unit['required_source_ids'])
        required += [projections[sid] for sid in required if sid in projections]
        item['required_source_ids'] = list(dict.fromkeys(required + ['session-packet']))
        if set(unit['required_source_ids']) & unprojected:
            item['requirement'] += ' Original binary evidence has no linked readable projection; preserve this unsupported/unreviewed evidence limitation.'
        units.append(item)
    original = read(root / 'request.txt')
    units.append({'id': 'session-whole-answer',
                  'requirement': 'Inspect the entire original request and complete readable/structured answer for all material topics, '
                                 'omissions, source limitations, factual contradictions and consistency between the answer artifacts. '
                                 'Assess beyond the task roster; this is a declared semantic judgment, not proof of correctness.',
                  'request_spans': [{'start_byte': 0, 'end_byte': len(original), 'sha256': sha(original)}],
                  'required_source_ids': list(sources)})
    if unprojected:
        units[-1]['requirement'] += ' Binary evidence without linked readable projections remains unresolved: ' + ', '.join(sorted(unprojected)) + '.'
    return research_revision.create_run(root / 'review', read(root / 'request.txt'), sources, units,
                                        adopted_at, max_corrections=max_corrections)


def freeze_draft(root, markdown_bytes, response_bytes, captured_at, *, expected_session_sha256, expected_head_sha256,
                 parent_draft_id=None):
    import research_revision
    root, _ = session(root, expected_session_sha256)
    return research_revision.freeze_draft(root / 'review', markdown_bytes, response_bytes, captured_at,
                                         expected_head_sha256=expected_head_sha256,
                                         parent_draft_id=parent_draft_id)


def check_binary_limitations(root, manifest, reviews):
    """Metadata inspection alone cannot satisfy missing original-content review."""
    _, _, unprojected = review_sources(root, manifest)
    affected = {unit['id'] for unit in manifest['units'] if set(unit['required_source_ids']) & unprojected}
    if unprojected:
        affected.add('session-whole-answer')
    for row in reviews:
        require(row.get('unit_id') not in affected or row.get('status') != 'SATISFIED',
                'UNPROJECTED_BINARY_EVIDENCE_REMAINS_UNRESOLVED')


def record_review(root, review_document, *, expected_session_sha256, reviewer_mode, expected_head_sha256):
    import research_revision
    root, manifest = session(root, expected_session_sha256)
    check_binary_limitations(root, manifest, review_document.get('reviews', []))
    return research_revision.record_review(root / 'review', review_document, reviewer_mode=reviewer_mode,
                                          expected_head_sha256=expected_head_sha256)


def select_final(root, draft_id, *, expected_session_sha256, expected_head_sha256):
    import research_revision
    root, manifest = session(root, expected_session_sha256)
    state = research_revision.verify(root / 'review', expected_head_sha256)
    if state['reviews']:
        check_binary_limitations(root, manifest, state['reviews'][-1]['assessment']['reviews'])
    return research_revision.select_final(root / 'review', draft_id, expected_head_sha256=expected_head_sha256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('start'); start.add_argument('--directory', required=True)
    start.add_argument('--request', required=True); start.add_argument('--host-plan', required=True)
    packet = sub.add_parser('prepare'); packet.add_argument('--directory', required=True)
    packet.add_argument('--host-plan', required=True)
    packet.add_argument('--expected-session-sha256', required=True)
    review = sub.add_parser('start-review'); review.add_argument('--directory', required=True)
    review.add_argument('--adopted-at', required=True); review.add_argument('--max-corrections', type=int, default=2)
    review.add_argument('--expected-session-sha256', required=True)
    review.add_argument('--expected-packet-sha256', required=True)
    args = parser.parse_args()
    if args.command == 'start':
        result = start_session(args.directory, read(args.request), **load(args.host_plan))
    elif args.command == 'prepare':
        result = prepare_packet(args.directory, expected_session_sha256=args.expected_session_sha256,
                                **load(args.host_plan))
    else:
        result = start_review(args.directory, expected_session_sha256=args.expected_session_sha256,
                              expected_packet_sha256=args.expected_packet_sha256,
                              adopted_at=args.adopted_at, max_corrections=args.max_corrections)
    print(encode(result).decode('utf8'), end='')


if __name__ == '__main__':
    main()
