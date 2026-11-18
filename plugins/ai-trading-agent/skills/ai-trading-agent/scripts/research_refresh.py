"""On-demand research refresh, using native collection and existing producers.

The assistant selects sources, performs source checks, prepares jobs and reviews
the whole answer. This helper retains those declarations; it never fetches,
polls, authenticates a source or starts a service. Keep returned pins externally.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import research_memory as memory
import research_revision as revision
import research_session as session

require = session.require
METHOD = 'on-demand-research-refresh-1'
STATUSES = ('verified_unchanged', 'revised', 'retracted', 'unavailable', 'unchecked')
MAX_FILES = 1024
MAX_TOTAL = 128 * 1024 * 1024


def instant(value):
    session.clock(value)
    return memory.instant(value)


def _tree(root):
    """Inventory only an explicitly selected research run, never a user folder."""
    root = session.local(root)
    require(root.is_dir() and not root.is_relative_to(session.ROOT), 'PRIVATE_ARCHIVE_REQUIRED')
    ordinary = (root / 'session.json').is_file()
    require(ordinary or (root / 'refresh.json').is_file(), 'EXPLICIT_RESEARCH_RUN_REQUIRED')
    allowed = ({'request.txt', 'host-plan.json', 'session.json', 'sources', 'packet-plan.json', 'packet.json',
                'filings', 'calculation-inputs', 'calculation', 'review'} if ordinary else
               {'parent-archive', 'parent-manifest.json', 'previous-answer.md', 'lineage.json', 'current',
                'refresh.json', 'refresh-packet-plan.json', 'refresh-packet.json', 'current-manifest.json', 'completion.json'})
    rows, total, count = [], 0, 0
    for path in root.rglob('*'):
        count += 1
        require(count <= MAX_FILES, 'ARCHIVE_FILE_COUNT_LIMIT')
        require(path.relative_to(root).parts[0] in allowed, 'UNRECOGNIZED_RESEARCH_ARCHIVE_MEMBER')
        session.local(path)  # Refuse every reparse point, including directories.
        if path.is_file():
            name = path.relative_to(root).as_posix()
            require(not any(part.lower() in ('private-runtime', '.git', 'credentials', 'browser-data')
                            or part.lower() == 'sec-contact.json' for part in path.relative_to(root).parts),
                    'PRIVATE_RUNTIME_NOT_RESEARCH_ARCHIVE')
            raw = session.read(path); total += len(raw)
            require(total <= MAX_TOTAL, 'ARCHIVE_TOTAL_SIZE_LIMIT')
            rows.append({'path': name, 'sha256': session.sha(raw), 'bytes': len(raw)})
    return sorted(rows, key=lambda row: row['path'])


def _completed(root, session_pin, head_pin):
    root, manifest = session.session(root, session_pin)
    state = revision.verify(root / 'review', head_pin)
    require(state['final'] is not None, 'PREVIOUS_COMPLETE_DELIVERY_REQUIRED')
    return root, manifest, state


def _review_delta(current, review, expected_packet_sha256):
    protocol = session.load(current / 'review' / review['run']['protocol']['path'])
    rows = [r for r in protocol['sources'] if r['id'] == 'extra-refresh-delta']
    require(len(rows) == 1 and rows[0]['artifact']['sha256'] == expected_packet_sha256,
            'PINNED_REFRESH_DELTA_REVIEW_REQUIRED')
    whole = [unit for unit in protocol['units'] if unit['id'] == 'session-whole-answer']
    require(len(whole) == 1 and 'extra-refresh-delta' in whole[0]['required_source_ids'],
            'WHOLE_ANSWER_REFRESH_DELTA_REQUIRED')


def _selected(spec, cutoff, checked_at):
    require(type(spec) is dict and set(spec) <= {'id', 'path', 'role', 'origin', 'metadata', 'derived_from'},
            'EXPLICIT_SOURCE_SPEC_REQUIRED')
    session.identifier(spec['id'])
    require(not spec['id'].startswith('refresh-'), 'REFRESH_SOURCE_ID_RESERVED')
    metadata = spec.get('metadata', {})
    available = instant(metadata.get('available_at'))
    retrieved = instant(metadata.get('retrieved_at'))
    require(available <= instant(cutoff), 'SOURCE_AVAILABLE_AFTER_REQUESTED_CUTOFF')
    require(available <= retrieved <= instant(checked_at), 'SOURCE_CHRONOLOGY_INVALID')
    raw = session.read(spec['path'])
    return copy.deepcopy(spec), raw


def begin_refresh(root, request_bytes, *, parent_root, expected_parent_session_sha256,
                  expected_parent_head_sha256, as_of, checked_at, decisions, additions,
                  tasks, expected_parent_refresh_sha256=None, expected_parent_completion_sha256=None):
    """Freeze a completed previous run and start a new ordinary research session.

    parent_root is a completed ordinary session, or an entire previous refresh
    with expected_parent_refresh_sha256. Each previous non-refresh source needs
    one {id,status,reason} decision. Unchanged/revised/retracted also need check
    {path,scope,checked_at,coverage_through}; revised needs replacement (source
    spec with the same id). New source specs are additions. Source metadata must
    retain available_at/retrieved_at; available_at cannot exceed the cutoff.
    A check's source identity, scope and absence-of-newer-document conclusion
    remain host declarations. Unchecked and unavailable bytes are archived only.
    """
    root, parent = session.local(root), session.local(parent_root)
    require(not root.exists() and root.parent.is_dir() and not root.is_relative_to(session.ROOT),
            'FRESH_PRIVATE_REFRESH_REQUIRED')
    require(not root.is_relative_to(parent) and not parent.is_relative_to(root), 'DISJOINT_RUNS_REQUIRED')
    require(instant(as_of) <= instant(checked_at), 'CHECK_PRECEDES_REQUESTED_CUTOFF')
    if expected_parent_refresh_sha256 is not None:
        previous = verify_refresh(parent, expected_parent_refresh_sha256,
                                  expected_completion_sha256=expected_parent_completion_sha256)
        require(previous.get('completion') is not None, 'PARENT_REFRESH_NOT_COMPLETED')
        current_parent = parent / 'current'
    else:
        require(not (parent / 'refresh.json').exists(), 'PARENT_REFRESH_PIN_REQUIRED')
        current_parent = parent
    current_parent, previous, state = _completed(current_parent, expected_parent_session_sha256,
                                                expected_parent_head_sha256)
    require(instant(as_of) >= instant(previous['as_of']), 'HISTORICAL_RECONSTRUCTION_IS_NOT_REFRESH')
    original = {row['id']: row for row in previous['sources'] if not row['id'].startswith('refresh-')}
    require(type(decisions) is list and len(decisions) == len(original) and
            {d['id'] for d in decisions} == set(original), 'EXACT_PREVIOUS_SOURCE_DECISIONS_REQUIRED')
    require(type(additions) is list and len(additions) + len(decisions) <= 90, 'BOUNDED_REFRESH_SOURCES')
    before = _tree(parent)
    selected, delta, check_sources = [], [], []
    for index, decision in enumerate(decisions):
        require(type(decision) is dict and set(decision) <= {'id', 'status', 'reason', 'check', 'replacement'},
                'SOURCE_DECISION_FIELDS')
        sid, status = decision['id'], decision['status']
        old = original[sid]
        require(status in STATUSES and type(decision['reason']) is str and decision['reason'].strip(),
                'SOURCE_STATUS_AND_REASON_REQUIRED')
        require(('replacement' in decision) == (status == 'revised'), 'REPLACEMENT_ONLY_FOR_REVISED')
        row = {'id': sid, 'status': status, 'reason': decision['reason'],
               'previous_sha256': old['artifact']['sha256'],
               'previous_metadata': copy.deepcopy(old.get('metadata', {})), 'current_sha256': None}
        check = decision.get('check')
        if status in ('verified_unchanged', 'revised', 'retracted'):
            require(type(check) is dict and set(check) == {'path', 'scope', 'checked_at', 'coverage_through'},
                    'RETAINED_SOURCE_CHECK_REQUIRED')
        if check is not None:
            require(type(check) is dict and set(check) == {'path', 'scope', 'checked_at', 'coverage_through'},
                    'SOURCE_CHECK_FIELDS')
            require(type(check['scope']) is str and check['scope'].strip(), 'SOURCE_CHECK_SCOPE_REQUIRED')
            require(instant(as_of) <= instant(check['coverage_through']) <= instant(check['checked_at'])
                    <= instant(checked_at), 'SOURCE_CHECK_COVERAGE_CHRONOLOGY')
            raw = session.read(check['path']); require(bool(raw.strip()), 'NONEMPTY_SOURCE_CHECK_REQUIRED')
            check_id = 'refresh-check-' + str(index)
            check_sources.append({'id': check_id, 'path': check['path'], 'role': 'Retained source-index check; host-attributed scope',
                                  'origin': 'host_collected', 'metadata': {k: v for k, v in check.items() if k != 'path'}})
            row['check'] = {k: v for k, v in check.items() if k != 'path'}
            row['check'].update(source_id=check_id, sha256=session.sha(raw))
        if status == 'verified_unchanged':
            require(old['origin'] != 'host_derived', 'DERIVED_INPUTS_REQUIRE_REBUILD')
            spec = {k: copy.deepcopy(v) for k, v in old.items() if k not in ('artifact', 'original_filename')}
            spec['path'] = str(current_parent / old['artifact']['path'])
            spec, raw = _selected(spec, as_of, checked_at)
            require(session.sha(raw) == old['artifact']['sha256'], 'UNCHANGED_SOURCE_BYTES_MISMATCH')
            selected.append(spec); row['current_sha256'] = session.sha(raw)
        elif status == 'revised':
            spec, raw = _selected(decision['replacement'], as_of, checked_at)
            require(spec['id'] == sid, 'REPLACEMENT_SOURCE_ID_MISMATCH')
            require(session.sha(raw) != old['artifact']['sha256'], 'REVISED_SOURCE_MUST_CHANGE_BYTES')
            selected.append(spec); row['current_sha256'] = session.sha(raw)
        delta.append(row)
    ids = set(original)
    for spec in additions:
        spec, raw = _selected(spec, as_of, checked_at)
        require(spec['id'] not in ids, 'NEW_SOURCE_ID_MUST_BE_UNIQUE'); ids.add(spec['id'])
        selected.append(spec)
        delta.append({'id': spec['id'], 'status': 'new', 'reason': 'Explicitly selected new evidence.',
                      'previous_sha256': None, 'current_sha256': session.sha(raw)})
    by_id = {s['id']: s for s in selected}
    for spec in selected:
        for ancestor in spec.get('derived_from', []):
            require(ancestor in by_id, 'UNAVAILABLE_OR_RETRACTED_DEPENDENCY')
            require(instant(by_id[ancestor]['metadata']['available_at']) <=
                    instant(spec['metadata']['available_at']), 'DERIVATION_PRECEDES_SOURCE_AVAILABILITY')
    root.mkdir()
    try:
        archive = root / 'parent-archive'; archive.mkdir()
        for row in before:
            raw = session.read(parent / row['path'])
            require(session.sha(raw) == row['sha256'], 'PREVIOUS_ARCHIVE_CHANGED_DURING_COPY')
            session.write(archive, row['path'], raw)
        require(before == _tree(parent), 'PREVIOUS_ARCHIVE_CHANGED_DURING_COPY')
        archive_manifest = memory.seal(archive, {'run_id': 'retained-parent', 'as_of': checked_at,
            'hold': 'retained-original-mandate', 'universe': 'retained-original-universe',
            'artifacts': [{'path': r['path'], 'kind': 'snapshot', 'as_of': checked_at,
                           'notes': 'Archive copy clock only; source clocks remain inside unchanged bytes.'} for r in before]})
        archive_ref = session.write(root, 'parent-manifest.json', session.encode(archive_manifest))
        previous_answer = state['final']['delivery']['first_response']
        answer_raw = session.read(current_parent / 'review' / previous_answer['path'])
        answer_ref = session.write(root, 'previous-answer.md', answer_raw)
        lineage = {'method': METHOD, 'as_of': as_of, 'checked_at': checked_at, 'source_delta': delta,
                   'parent_archive': archive_ref, 'parent_session_sha256': expected_parent_session_sha256,
                   'parent_head_sha256': expected_parent_head_sha256,
                   'parent_refresh_sha256': expected_parent_refresh_sha256,
                   'parent_completion_sha256': expected_parent_completion_sha256,
                   'previous_answer': answer_ref,
                   'limits': ['Checks and source identities are host declarations, not source authenticity proof.',
                              'Only selected sources available through as_of may support updated conclusions.',
                              'Unchecked/unavailable sources remain stale or unknown; retractions invalidate dependent claims.',
                              'Review the whole old/new thesis, assumptions, valuation and risks, not just changed numbers.']}
        lineage_ref = session.write(root, 'lineage.json', session.encode(lineage))
        selected += check_sources + [
            {'id': 'refresh-lineage', 'path': str(root / lineage_ref['path']), 'role': 'Source refresh delta and limits', 'origin': 'host_derived',
             'derived_from': [s['id'] for s in selected] or ['refresh-previous-answer']},
            {'id': 'refresh-previous-answer', 'path': str(root / answer_ref['path']), 'role': 'Previous complete answer; historical only', 'origin': 'supplied'}]
        tasks = copy.deepcopy(tasks)
        for task in tasks:
            task['required_source_ids'] = list(dict.fromkeys(task['required_source_ids'] + ['refresh-lineage', 'refresh-previous-answer']))
            task['requirement'] += ' Explain changes versus the previous answer and unresolved stale/retracted evidence; assess the whole conclusion.'
        created = session.start_session(root / 'current', request_bytes, workflow=previous['workflow'],
            sources=selected, tasks=tasks, as_of=as_of,
            acquisition_policy=previous['acquisition_policy'] + ' On-demand refresh; no monitoring or execution.')
        document = {'schema_version': 1, 'method': METHOD, 'lineage': lineage_ref,
                    'parent_archive': archive_ref, 'current_session_sha256': created['session_sha256'],
                    'parent_session_relative_root': current_parent.relative_to(parent).as_posix(),
                    'as_of': as_of, 'checked_at': checked_at}
        ref = session.write(root, 'refresh.json', session.encode(document))
        return {'refresh_sha256': ref['sha256'], 'session_sha256': created['session_sha256'],
                'source_delta': delta, 'current_session': 'current', 'execution_authorized': False}
    except Exception as exc:
        session.write(root, 'refresh-failure.json', session.encode({'type': type(exc).__name__, 'reason': str(exc)}))
        raise


def verify_refresh(root, expected_refresh_sha256, *, expected_packet_sha256=None,
                   expected_completion_sha256=None):
    """Reopen with an external pin; byte equality never establishes currentness."""
    root = session.local(root)
    raw = session.read(root / 'refresh.json')
    require(session.sha(raw) == expected_refresh_sha256, 'EXTERNAL_REFRESH_PIN_MISMATCH')
    document = json.loads(raw)
    require(document['method'] == METHOD, 'REFRESH_METHOD')
    for ref in (document['lineage'], document['parent_archive']):
        require(session.sha(session.read(session.member(root, ref['path']))) == ref['sha256'], 'REFRESH_ARTIFACT_CHANGED')
    archived = json.loads(session.read(root / 'parent-manifest.json'))
    memory.verify(root / 'parent-archive', archived)
    require({r['path'] for r in _tree(root / 'parent-archive')} == {r['path'] for r in archived['artifacts']},
            'PARENT_ARCHIVE_ROSTER_CHANGED')
    lineage = json.loads(session.read(root / 'lineage.json'))
    require(session.sha(session.read(session.member(root, lineage['previous_answer']['path']))) ==
            lineage['previous_answer']['sha256'], 'PREVIOUS_ANSWER_CHANGED')
    _completed(root / 'parent-archive' / document['parent_session_relative_root'],
               lineage['parent_session_sha256'], lineage['parent_head_sha256'])
    current, manifest = session.session(root / 'current', document['current_session_sha256'])
    result = {'refresh': document, 'session': manifest, 'source_delta': lineage['source_delta'],
              'archive_integrity': 'VERIFIED', 'source_checks': 'RETAINED_HOST_DECLARATIONS',
              'source_authenticity_verified': False, 'completion': None}
    if expected_packet_sha256 is not None:
        packet = session.read(root / 'refresh-packet.json')
        require(session.sha(packet) == expected_packet_sha256, 'EXTERNAL_REFRESH_PACKET_PIN_MISMATCH')
        result['packet'] = json.loads(packet)
        require(session.sha(session.read(current / 'packet.json')) == result['packet']['session_packet_sha256'],
                'SESSION_PACKET_CHANGED')
        ref = result['packet']['host_plan']
        require(session.sha(session.read(session.member(root, ref['path']))) == ref['sha256'],
                'REFRESH_HOST_PLAN_CHANGED')
    if (root / 'completion.json').exists():
        require(expected_completion_sha256 is not None, 'EXTERNAL_COMPLETION_PIN_REQUIRED')
        raw = session.read(root / 'completion.json')
        require(session.sha(raw) == expected_completion_sha256, 'EXTERNAL_COMPLETION_PIN_MISMATCH')
        completion = json.loads(raw)
        require(completion['refresh_sha256'] == expected_refresh_sha256, 'COMPLETION_REFRESH_PIN_MISMATCH')
        require(session.sha(session.read(root / 'refresh-packet.json')) == completion['refresh_packet_sha256'],
                'COMPLETED_REFRESH_PACKET_CHANGED')
        if expected_packet_sha256 is not None:
            require(completion['refresh_packet_sha256'] == expected_packet_sha256, 'COMPLETION_PACKET_PIN_MISMATCH')
        completed_packet = session.load(root / 'refresh-packet.json')
        ref = completed_packet['host_plan']
        require(session.sha(session.read(session.member(root, ref['path']))) == ref['sha256'], 'REFRESH_HOST_PLAN_CHANGED')
        _, _, reviewed = _completed(current, document['current_session_sha256'], completion['head_sha256'])
        _review_delta(current, reviewed, completion['refresh_packet_sha256'])
        require(completion['delivery'] == reviewed['final']['delivery'] and
                completion['disposition'] == reviewed['final']['disposition'], 'EXACT_COMPLETED_DELIVERY_REQUIRED')
        sealed = json.loads(session.read(root / 'current-manifest.json'))
        require(session.sha(session.read(root / 'current-manifest.json')) == completion['archive_manifest_sha256'],
                'COMPLETED_ARCHIVE_MANIFEST_CHANGED')
        memory.verify(current, sealed)
        require({r['path'] for r in _tree(current)} == {r['path'] for r in sealed['artifacts']}, 'COMPLETED_ARCHIVE_ROSTER_CHANGED')
        result['completion'] = completion
    return result


def prepare_refresh(root, *, expected_refresh_sha256, dispositions, dependencies,
                    filings=None, calculation=None):
    """Run existing producers; account for every previous calculation job.

    dependencies = [{id,status,reason,new_job_id?}], status recomputed/unsupported.
    Every prior job requires an explicit disposition even if its values look
    unchanged. New-cutoff results are never silently inherited. New jobs are
    retained too; arbitrary operations are not invented for missing producers.
    """
    root = session.local(root)
    state = verify_refresh(root, expected_refresh_sha256)
    doc = state['refresh']
    previous = root / 'parent-archive' / doc['parent_session_relative_root']
    previous_plan = json.loads(session.read(previous / 'packet-plan.json'))
    old_jobs = (previous_plan.get('calculation') or {}).get('jobs', [])
    require(type(dependencies) is list and len(dependencies) == len(old_jobs) and
            {r['id'] for r in dependencies} == {j['id'] for j in old_jobs}, 'EXACT_PREVIOUS_JOB_DISPOSITIONS_REQUIRED')
    planned_ids = {j['id'] for j in (calculation or {}).get('jobs', [])}
    for row in dependencies:
        require(set(row) <= {'id', 'status', 'reason', 'new_job_id'} and
                row['status'] in ('recomputed', 'unsupported') and type(row['reason']) is str and row['reason'].strip(),
                'JOB_DISPOSITION_FIELDS')
        require((row.get('new_job_id') in planned_ids) if row['status'] == 'recomputed' else 'new_job_id' not in row,
                'RECOMPUTED_JOB_MUST_BE_EXECUTED')
    plan_ref = session.write(root, 'refresh-packet-plan.json', session.encode({'dependencies': dependencies,
        'dispositions': dispositions, 'filings': filings, 'calculation': calculation}))
    try:
        prepared = session.prepare_packet(root / 'current', expected_session_sha256=doc['current_session_sha256'],
            dispositions=dispositions, filings=filings, calculation=calculation)
        new_jobs = {j['id']: j for j in (prepared['packet']['calculation_completion'] or {}).get('jobs', [])}
        def retained_results(folder):
            path = folder / 'calculation/run/result.json'
            if not path.is_file():
                return {}
            result = json.loads(session.read(path))
            return {job['id']: job.get('result') for job in result.get('jobs', [])}
        old_results, current_results = retained_results(previous), retained_results(root / 'current')
        previous_sources = {r['id']: r for r in session.load(previous / 'session.json')['sources']}
        changed_ids = {r['id'] for r in state['source_delta'] if r['status'] != 'verified_unchanged'}
        def ancestors(sid, seen=None):
            seen = set() if seen is None else seen
            if sid in seen:
                return seen
            seen.add(sid)
            for ancestor in previous_sources.get(sid, {}).get('derived_from', []):
                ancestors(ancestor, seen)
            return seen
        jobs_by_id = {j['id']: j for j in old_jobs}
        result_delta = []
        for row in dependencies:
            actual = new_jobs.get(row.get('new_job_id'))
            verified = bool(actual and actual.get('computation_status') == 'COMPUTED')
            previous_result = old_results.get(row['id'])
            current_result = current_results.get(row.get('new_job_id'))
            source_path = jobs_by_id[row['id']]['inputs_source']['path']
            dependent_ids = ancestors(source_path[:-4]) if source_path.endswith('.bin') else set()
            result_delta.append({**row, 'actual_status': actual,
                'dependency_source_ids': sorted(dependent_ids), 'affected_by_source_ids': sorted(dependent_ids & changed_ids),
                'recomputation_verified': verified, 'previous_result': previous_result, 'current_result': current_result,
                'comparison_status': ('UNSUPPORTED_OR_NOT_COMPUTED' if not verified else 'NO_PRIOR_COMPLETE_RESULT'
                    if previous_result is None else 'UNCHANGED_AFTER_RECOMPUTATION' if previous_result == current_result else 'CHANGED'),
                'previous_result_scope': 'historical; inspect parent-archive result and previous complete answer'})
        packet = {'method': METHOD, 'host_plan': plan_ref, 'source_delta': state['source_delta'], 'result_delta': result_delta,
            'session_packet_sha256': prepared['packet_sha256'], 'as_of': doc['as_of'],
            'status': 'REFRESH_WITH_LIMITATIONS' if any(r['status'] in ('unchecked', 'unavailable', 'retracted') for r in state['source_delta'])
                or any(not r['recomputation_verified'] for r in result_delta)
                or prepared['packet']['status'] != 'EVIDENCE_PREPARED' else 'REFRESH_EVIDENCE_PREPARED',
            'limits': ['Recomputed means actual producer output, not source truth or a verified investment conclusion.',
                       'Review the exact old and new complete answers; source checks remain host declarations.',
                       'Unsupported dependencies and unchecked stale sources must remain visible in the delivered answer.']}
        ref = session.write(root, 'refresh-packet.json', session.encode(packet))
        return {'refresh_packet_sha256': ref['sha256'], 'session_packet_sha256': prepared['packet_sha256'], 'packet': packet}
    except Exception as exc:
        session.write(root, 'refresh-prepare-failure.json', session.encode({'type': type(exc).__name__, 'reason': str(exc)}))
        raise


def start_review(root, *, expected_refresh_sha256, expected_refresh_packet_sha256,
                 adopted_at, max_corrections=2):
    """Use the ordinary review path, including the refresh delta in whole-answer review."""
    root = session.local(root)
    state = verify_refresh(root, expected_refresh_sha256, expected_packet_sha256=expected_refresh_packet_sha256)
    require(instant(adopted_at) >= instant(state['refresh']['checked_at']), 'REVIEW_PRECEDES_REFRESH_CHECKS')
    return session.start_review(root / 'current', expected_session_sha256=state['refresh']['current_session_sha256'],
        expected_packet_sha256=state['packet']['session_packet_sha256'], adopted_at=adopted_at,
        max_corrections=max_corrections,
        additional_review_sources={'extra-refresh-delta': session.read(root / 'refresh-packet.json')})


def complete_refresh(root, *, expected_refresh_sha256, expected_refresh_packet_sha256,
                     expected_head_sha256):
    """Seal exact reviewed delivery and current archive; never rewrite the previous run."""
    root = session.local(root)
    state = verify_refresh(root, expected_refresh_sha256, expected_packet_sha256=expected_refresh_packet_sha256)
    current, manifest, review = _completed(root / 'current', state['refresh']['current_session_sha256'], expected_head_sha256)
    _review_delta(current, review, expected_refresh_packet_sha256)
    files = _tree(current)
    archive = memory.seal(current, {'run_id': 'completed-refresh', 'as_of': state['refresh']['checked_at'],
        'hold': 'retained-current-request', 'universe': 'retained-current-request',
        'artifacts': [{'path': r['path'], 'kind': 'snapshot', 'as_of': state['refresh']['checked_at']} for r in files]})
    ref = session.write(root, 'current-manifest.json', session.encode(archive))
    completion = {'method': METHOD, 'refresh_sha256': expected_refresh_sha256,
        'refresh_packet_sha256': expected_refresh_packet_sha256, 'head_sha256': expected_head_sha256,
        'archive_manifest_sha256': ref['sha256'], 'delivery': review['final']['delivery'],
        'disposition': review['final']['disposition'], 'execution_authorized': False}
    saved = session.write(root, 'completion.json', session.encode(completion))
    return {'completion_sha256': saved['sha256'], 'completion': completion}
