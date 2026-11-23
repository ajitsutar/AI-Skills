"""Offline request bindings, evidence inventory, horizon routing and method audit.

CLI: research_contracts.py OPERATION INPUT.json --source-root DIR --private-output DIR
Operations: bind-request, inventory-evidence, route-horizon, audit-ranking, plan-strategy, strategy-answer, schema.
Replay a private receipt: research_contracts.py verify EXPORT_DIRECTORY
The caller explicitly selects roles, pointers and methods. No prompt intent,
source authenticity, acquisition completeness or execution permission is inferred.
All outputs are advisory; invalid research records never veto native execution.
"""
from __future__ import annotations

import argparse
import copy
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile

import handoff_report as binding_json
from price_audit import timestamp

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'research-contracts-1'


def require(test, reason):
    if not test:
        raise ValueError(reason)


def digest(value):
    return hashlib.sha256(binding_json.encode(value).encode('utf-8')).hexdigest()


def envelope(kind, document, result):
    return {'schema_version': 1, 'adapter_version': VERSION, 'kind': kind,
            'input_sha256': digest(document), 'result': result, 'advisory_only': True,
            'execution_gates': [], 'source_authenticity_verified': False,
            'limits': ['Caller-selected fields and roles do not prove correct interpretation of the user request.',
                       'Hashes establish retained-byte consistency, not truth, source authenticity or complete acquisition.',
                       'Research statuses never authorize, delay or refuse native execution.']}


def relative_name(name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name,
            'RELATIVE_LOCAL_PATH_REQUIRED')
    parts = name.split('/')
    require(all(p and p not in ('.', '..') for p in parts), 'SOURCE_PATH_ESCAPE')
    require(not Path(name).is_absolute(), 'SOURCE_PATH_ESCAPE')
    return name


def source_path(root, name):
    name = relative_name(name)
    root = binding_json.local_path(root)
    path = (root / name).resolve()
    require(path.is_relative_to(root), 'SOURCE_PATH_ESCAPE')
    return path


def inventory_sources(document, root):
    allowlist = document.get('allowlist')
    require(isinstance(allowlist, list) and all(isinstance(x, str) for x in allowlist), 'EXPLICIT_ALLOWLIST_REQUIRED')
    allowed = {relative_name(x) for x in allowlist}
    sources = document.get('sources', [])
    require(isinstance(sources, list) and all(isinstance(s, dict) for s in sources), 'SOURCE_LIST_REQUIRED')
    require(all(isinstance(s.get('id'), str) and s['id'] for s in sources) and
            len({s['id'] for s in sources}) == len(sources), 'UNIQUE_SOURCE_IDS_REQUIRED')
    rows, values = [], {}
    for source in sources:
        row = {'id': source['id'], 'path': source.get('path'), 'role': source.get('role'),
               'expected_sha256': source.get('sha256'), 'actual_sha256': None}
        try:
            require(isinstance(source.get('role'), str) and bool(source['role']), 'SOURCE_ROLE_REQUIRED')
            name = relative_name(source.get('path'))
            if name not in allowed:
                row['status'] = 'NOT_ALLOWLISTED_NOT_READ'
            else:
                path = source_path(root, name)
                if not path.is_file():
                    row['status'] = 'MISSING_BYTES'
                else:
                    raw = path.read_bytes()
                    row['actual_sha256'] = hashlib.sha256(raw).hexdigest()
                    row['bytes'] = len(raw)
                    expected = source.get('sha256')
                    if not isinstance(expected, str) or not re.fullmatch('[a-fA-F0-9]{64}', expected):
                        row['status'] = 'EXPECTED_HASH_MISSING_OR_INVALID'
                    elif row['actual_sha256'] != expected.lower():
                        row['status'] = 'HASH_MISMATCH'
                    else:
                        form = source.get('format', 'json')
                        require(form in ('json', 'text', 'bytes'), 'SOURCE_FORMAT_UNSUPPORTED')
                        values[source['id']] = (binding_json.strict_json(raw) if form == 'json' else
                                                raw.decode('utf-8-sig') if form == 'text' else None)
                        row['status'] = 'BYTES_MATCH'
        except (ValueError, TypeError, OSError) as exc:
            row['status'] = 'INVALID_OR_UNREADABLE'
            row['reason'] = str(exc)
        rows.append(row)
    return rows, values


def pointer(value, path):
    # Unlike the handoff adapter, research observations may legitimately be null.
    if path == '':
        return value
    require(isinstance(path, str) and path.startswith('/'), 'JSON_POINTER_REQUIRED')
    for token in path[1:].split('/'):
        require(not re.search(r'~(?![01])', token), 'INVALID_POINTER_ESCAPE')
        key = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            require(bool(re.fullmatch('0|[1-9][0-9]*', key)), 'INVALID_ARRAY_INDEX')
            value = value[int(key)]
        elif isinstance(value, dict):
            value = value[key]
        else:
            raise ValueError('POINTER_NOT_FOUND')
    return value


def inside(path, record):
    return record == '' or path == record or path.startswith(record + '/')


def leaves(value, path=''):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaves(child, path + '/' + key.replace('~', '~0').replace('/', '~1'))
    elif isinstance(value, list) and value:
        for i, child in enumerate(value):
            yield from leaves(child, path + '/' + str(i))
    else:
        yield path


def bind_request(document, source_root):
    rows, values = inventory_sources(document, source_root)
    by_id = {row['id']: row for row in rows}
    declared = document.get('bindings', [])
    require(isinstance(declared, list) and all(isinstance(b, dict) for b in declared), 'BINDINGS_REQUIRED')
    require(all(isinstance(b.get('id'), str) for b in declared) and len({b['id'] for b in declared}) == len(declared), 'UNIQUE_BINDING_IDS')
    bound, consumed, targets = [], {}, {}
    prompt = document.get('prompt_binding')
    require(isinstance(prompt, dict), 'PROMPT_BINDING_REQUIRED')
    prompt_result = copy.deepcopy(prompt)
    try:
        prompt_value = pointer(values[prompt['source_id']], prompt.get('pointer', ''))
        require(isinstance(prompt_value, str) and prompt_value.strip(), 'PROMPT_TEXT_REQUIRED')
        prompt_result.update(status='BOUND', prompt_sha256=digest(prompt_value), text=prompt_value,
                             source_sha256=by_id[prompt['source_id']]['actual_sha256'])
        consumed.setdefault(prompt['source_id'], []).append(prompt.get('pointer', ''))
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        prompt_result.update(status='UNRESOLVED', reason=str(exc))
    for item in declared:
        row = copy.deepcopy(item)
        try:
            sid, path = item['source_id'], item['pointer']
            require(item.get('usage') in ('selected', 'unused'), 'BINDING_USAGE_REQUIRED')
            require(isinstance(item.get('target'), str) and item['target'], 'BINDING_TARGET_REQUIRED')
            value = pointer(values[sid], path)
            row.update(status='BOUND', value=value, value_sha256=digest(value),
                       source_sha256=by_id[sid]['actual_sha256'], source_role=by_id[sid]['role'])
            issues = []
            if item.get('required_role') and item['required_role'] != by_id[sid]['role']:
                issues.append('SOURCE_ROLE_MISMATCH')
            record = item.get('record_pointer', '')
            require(isinstance(record, str), 'RECORD_POINTER_REQUIRED')
            pointer(values[sid], record)
            if not inside(path, record):
                issues.append('VALUE_OUTSIDE_DECLARED_RECORD')
            metadata = {}
            meta = item.get('metadata_pointers', {})
            require(isinstance(meta, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in meta.items()), 'METADATA_POINTER_OBJECT_REQUIRED')
            for key, meta_path in meta.items():
                if not inside(meta_path, record):
                    issues.append('METADATA_OUTSIDE_DECLARED_RECORD:' + key)
                metadata[key] = {'pointer': meta_path, 'value': pointer(values[sid], meta_path)}
            row['metadata'] = metadata
            identity = item.get('record_identity')
            if identity:
                actual = pointer(values[sid], identity['pointer'])
                if not inside(identity['pointer'], record) or binding_json.differences(actual, identity['expected']):
                    issues.append('RECORD_IDENTITY_MISMATCH')
                row['record_identity_observed'] = actual
            row['issues'] = issues
            if issues:
                row['status'] = 'CONFLICT'
            if item['usage'] == 'selected':
                targets.setdefault(item['target'], []).append(row)
                consumed.setdefault(sid, []).extend([path] + list(item.get('metadata_pointers', {}).values()))
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            row.update(status='UNRESOLVED', reason=str(exc))
        bound.append(row)
    conflicts = []
    for target, selected in targets.items():
        if len({r['value_sha256'] for r in selected}) > 1:
            conflicts.append({'target': target, 'binding_ids': [r['id'] for r in selected],
                              'status': 'CONFLICTING_SELECTED_VALUES'})
    unused = [{'source_id': sid, 'pointer': p} for sid, value in values.items()
              for p in leaves(value) if not any(inside(p, selected) for selected in consumed.get(sid, []))]
    clean = prompt_result['status'] == 'BOUND' and all(r['status'] == 'BOUND' for r in bound) and not conflicts
    return envelope('REQUEST_BINDING', document, {'status': 'BOUND' if clean else 'UNRESOLVED_OR_CONFLICTING',
                    'prompt': prompt_result, 'sources': rows, 'bindings': bound, 'conflicts': conflicts,
                    'unused_supplied_pointers': unused,
                    'selection_validated_against_natural_language': False})


def guarded_checks(checks, root, allowlist):
    """Actually invoke installed source/freshness/report helpers after path checks."""
    import research_handoff
    import research_report_checks
    require(isinstance(checks, list) and all(isinstance(c, dict) for c in checks), 'CHECK_OBJECT_LIST_REQUIRED')
    result = []
    def stable(value):
        # Existing source helpers include OS paths in missing-byte diagnostics.
        # Normalize only diagnostic fields so replay does not depend on a temp
        # directory name; source observations themselves remain unchanged.
        if isinstance(value, dict):
            return {k: diagnostic(v) if k in ('reason', 'reasons') else stable(v) for k, v in value.items()}
        if isinstance(value, list):
            return [stable(v) for v in value]
        return value
    def diagnostic(value):
        if isinstance(value, list): return [diagnostic(v) for v in value]
        if isinstance(value, str):
            resolved = str(Path(root).resolve())
            return value.replace(resolved.replace('\\', '\\\\'), '<source-root>').replace(resolved, '<source-root>').replace(resolved.replace('\\', '/'), '<source-root>')
        return value
    def guard(value):
        if isinstance(value, dict):
            if 'content_sha256' in value and 'file' in value:
                require(relative_name(value['file']) in allowlist, 'CHECK_SOURCE_NOT_ALLOWLISTED')
                source_path(root, value['file'])
            for child in value.values(): guard(child)
        elif isinstance(value, list):
            for child in value: guard(child)
    for check in checks:
        name = check.get('kind')
        try:
            args = check['inputs']; guard(args)
            require(isinstance(args, dict), 'CHECK_INPUT_OBJECT_REQUIRED')
            if name == 'primary_source':
                research_handoff.source(args['record'], root)
                output = {'status': 'SAVED_BYTES_CONSISTENT'}
            elif name == 'primary_freshness':
                output = research_handoff.freshness(args['audit'], args['vendor_period'], timestamp(args['cutoff']), root)
            elif name == 'research_handoff':
                output = research_handoff.evaluate(source_root=root, **args)
            elif name in ('pe_claim', 'revision', 'scenario_checks'):
                output = getattr(research_report_checks, name)(**args)
            else:
                raise ValueError('CHECK_NOT_ALLOWLISTED')
            result.append({'kind': name, 'status': 'HELPER_EXECUTED', 'result': stable(output)})
        except (KeyError, IndexError, ValueError, TypeError, OSError, RuntimeError) as exc:
            result.append({'kind': name, 'status': 'UNRESOLVED', 'reason': diagnostic(str(exc))})
    return result


def inventory_evidence(document, source_root):
    rows, values = inventory_sources(document, source_root)
    cutoff = timestamp(document['as_of'])
    sources = {s['id']: s for s in document['sources']}
    counts = {'included': 0, 'excluded': 0, 'unknown': 0}
    receipts, missing_receipts = [], []
    for row in rows:
        source = sources[row['id']]
        classification = source.get('classification')
        if classification is None:
            row['classification'] = {'status': 'NOT_APPLICABLE_NOT_DECLARED'}
        else:
            require(isinstance(classification, dict) and classification.get('status') in counts, 'CLASSIFICATION_STATUS_REQUIRED')
            row['classification'] = copy.deepcopy(classification)
            counts[classification['status']] += 1
        row['chronology'] = {'as_of': document['as_of'], 'published_at': source.get('published_at'),
                             'retrieved_at': source.get('retrieved_at'), 'available_at': source.get('available_at')}
        issues = []
        for name in ('published_at', 'retrieved_at', 'available_at'):
            if source.get(name):
                try:
                    if timestamp(source[name]) > cutoff:
                        issues.append({'published_at': 'PUBLISHED_AFTER_CUTOFF', 'retrieved_at': 'LATER_RETRIEVAL_NOT_NEW_PUBLICATION',
                                       'available_at': 'AVAILABLE_AFTER_CUTOFF'}[name])
                except (ValueError, TypeError):
                    issues.append('INVALID_TIMESTAMP:' + name)
        row['chronology']['issues'] = issues
        if source['role'] == 'acquisition_receipt':
            record = values.get(source['id'])
            if row['status'] == 'BYTES_MATCH' and isinstance(record, dict) and record.get('status') in ('success', 'failure'):
                receipts.append({'source_id': source['id'], 'status': record['status']})
            else:
                missing_receipts.append(source['id'])
    expected_receipts = document.get('expected_acquisition_receipt_ids', [])
    require(isinstance(expected_receipts, list), 'EXPECTED_RECEIPT_IDS_REQUIRED')
    observed_ids = {r['source_id'] for r in receipts}
    missing_receipts = sorted(set(missing_receipts) | (set(expected_receipts) - observed_ids))
    observed_failures = sum(r['status'] == 'failure' for r in receipts)
    declared_complete = document.get('acquisition_coverage') == 'declared_complete' and bool(expected_receipts) and not missing_receipts
    checks = guarded_checks(document.get('checks', []), source_root, set(document['allowlist']))
    return envelope('EVIDENCE_INVENTORY', document, {'sources': rows, 'classification_counts': counts,
                    'acquisition': {'observed_receipts': receipts, 'missing_or_invalid_receipts': missing_receipts,
                                    'observed_failure_count': observed_failures if receipts else None,
                                    'declared_complete_failure_count': observed_failures if declared_complete else None,
                                    'completeness': 'CALLER_DECLARED_WITH_LISTED_RECEIPTS' if declared_complete else 'UNKNOWN_OR_PARTIAL',
                                    'verified_zero_failures': False}, 'checks': checks,
                    'limits': 'Unknown classification is not an evidenced exclusion; absent receipts are not a verified zero-failure audit.'})


def clock_day(value):
    return date.fromisoformat(value) if len(value) == 10 else timestamp(value).date()


def clock_order(left, right):
    """Return -1/0/1 or unknown for overlapping mixed-precision clocks.

    Date-only values have no invented midnight or timezone. Distinct local
    calendar dates can be ordered; same-date mixed precision cannot.
    """
    require(isinstance(left, str) and isinstance(right, str), 'CLOCK_STRING_REQUIRED')
    if len(left) != 10 and len(right) != 10:
        a, b = timestamp(left), timestamp(right)
    elif len(left) == 10 and len(right) == 10:
        a, b = date.fromisoformat(left), date.fromisoformat(right)
    else:
        a, b = clock_day(left), clock_day(right)
        if a == b:
            return None
    return (a > b) - (a < b)


def horizon_capability_scope(document, coverage, issues, entry, comparison, hard_exit):
    """Separate feasible descriptive work from claims this router cannot certify.

    Calendar coverage is a declared time boundary, not an event-exclusion test,
    forecast, or quantitative risk model. This projection creates no events,
    review schedule, valuation inputs, or execution authority.
    """
    exclusion = document.get('event_exclusion_requirement', 'not_declared')
    require(exclusion in ('not_declared', 'none', 'entry_only', 'full_hold'),
            'EXPLICIT_EVENT_EXCLUSION_REQUIREMENT')
    incomplete = coverage['status'] != 'DECLARED_THROUGH_COMPARISON'
    return {
        'kind': 'RESEARCH_CAPABILITY_SCOPE',
        'entry_at': entry, 'comparison_at': comparison, 'hard_exit_at': hard_exit,
        'horizon_dependent_work': 'RESOLVE_HORIZON_CONFLICT' if issues else 'REQUESTED_HORIZON_RETAINED',
        'horizon_conflicts': copy.deepcopy(issues),
        'feasible_work': [
            {'scope': 'available_event_description', 'status': 'AVAILABLE_WITH_DISCLOSURES',
             'requires': ['Available dated records, or explicit disclosure that dates are unavailable.'],
             'boundary': 'Describe only supplied events and their uncertainty; unavailable future dates do not shorten the requested research horizon.'},
            {'scope': 'qualitative_risk_review', 'status': 'AVAILABLE_WITH_DISCLOSURES',
             'requires': ['Separate general risk mechanisms from issuer-specific supported facts.'],
             'boundary': 'Discuss gap, liquidity and recurring-event exposure without inventing dates, probabilities or loss bounds.'}],
        'event_exclusion_requirement': {
            'scope': exclusion,
            'status': ('DECLARED_UNCERTIFIED' if exclusion in ('entry_only', 'full_hold') else
                       'DECLARED_NONE' if exclusion == 'none' else 'NOT_DECLARED_TO_THIS_ROUTER'),
            'waived': False, 'other_event_policies_evaluated': False,
            'boundary': 'Descriptive research does not satisfy an explicit event-exclusion requirement. Evaluate that requirement separately with applicable event evidence and policy.'},
        'uncertified_claims': [
            {'scope': 'event_free_hold', 'status': 'NOT_CERTIFIED_BY_ROUTING',
             'reason': 'Even full declared calendar coverage does not establish absence of prohibited events.'},
            {'scope': 'quantified_gap_risk', 'status': 'REQUIRES_SEPARATE_EVIDENCE',
             'reason': 'Calendar dates do not supply a gap distribution, event probability or maximum loss bound.'},
            {'scope': 'terminal_forecast_or_ranking', 'status': 'REQUIRES_SEPARATE_EVIDENCE',
             'reason': 'Calendar coverage does not establish terminal assumptions, valuation applicability, ranking or sizing support. Explicit hypothetical sensitivities remain separate.'}],
        'refresh': {'coverage_incomplete_or_uncertain': incomplete,
                    'unknown_after': coverage.get('unknown_after'),
                    'unknown_through': coverage.get('unknown_through'),
                    'review_schedule_created': False, 'events_created': False,
                    'boundary': 'Refresh available event disclosures during future research; any cadence is a separate explicit proposal, not an announced event or active automation.'},
        'research_complete': 'NOT_ASSESSED',
        'execution_authorized': False}


def route_horizon(document, source_root=None):
    mode = document.get('mode')
    require(mode in ('fixed_exit', 'flexible_review', 'comparison'), 'EXPLICIT_HORIZON_MODE_REQUIRED')
    issues, assumptions = [], copy.deepcopy(document.get('planning_assumptions', []))
    require(isinstance(assumptions, list) and all(isinstance(x, dict) and x.get('label') and x.get('value') is not None and
            x.get('basis') in ('user_supplied', 'analyst_proposal') for x in assumptions), 'LABEL_PLANNING_ASSUMPTIONS')
    chronology = {'status': 'DELEGATED_FIXED_CALENDAR'}
    if mode == 'fixed_exit':
        import horizon_review
        resolved = horizon_review.resolve_horizon(document['fixed_spec'])
        comparison, entry = resolved['exit_at'], resolved['entry_at']
        hard_exit = comparison
    else:
        comparison, entry = document['comparison_at'], document['entry_at']
        entry_order = clock_order(entry, comparison)
        asof_order = clock_order(document['as_of'], comparison)
        require(entry_order not in (0, 1) and asof_order != 1, 'HORIZON_CHRONOLOGY')
        chronology = {'as_of': document['as_of'], 'entry_before_comparison': entry_order == -1 if entry_order is not None else None,
                      'as_of_not_after_comparison': asof_order <= 0 if asof_order is not None else None,
                      'status': 'ORDER_CONFIRMED' if entry_order is not None and asof_order is not None else 'MIXED_PRECISION_ORDER_UNKNOWN'}
        resolved, hard_exit = None, None
        if document.get('forced_exit') not in (None, False) or document.get('hard_exit_at') is not None:
            issues.append('FLEXIBLE_REQUEST_CONTAINS_FORCED_EXIT_CONFLICT')
        if document.get('exit_buffer_minutes') is not None:
            issues.append('EXIT_BUFFER_NOT_APPLIED_TO_COMPARISON_DATE')
    coverage = copy.deepcopy(document.get('event_coverage', {}))
    through = coverage.get('through')
    if through is None:
        coverage.update(status='UNKNOWN', unknown_after=entry, unknown_through=comparison)
    else:
        end_order = clock_order(through, comparison)
        complete = end_order is not None and end_order >= 0
        coverage.update(status='DECLARED_THROUGH_COMPARISON' if complete else 'COVERAGE_PRECISION_UNKNOWN' if end_order is None else 'PARTIAL_DECLARED_COVERAGE',
                        unknown_after=None if complete else through, unknown_through=None if complete else comparison)
    return envelope('HORIZON_ROUTE', document, {'mode': mode, 'forced_exit': mode == 'fixed_exit',
                    'comparison_at': comparison, 'hard_exit_at': hard_exit, 'entry_at': entry,
                    'resolved_fixed_exit': resolved, 'event_coverage': coverage, 'chronology': chronology,
                    'planning_assumptions': assumptions, 'issues': issues,
                    'status': 'CONFLICT' if issues else 'ROUTED',
                    'calendar_dates_authenticate_future_events': False,
                    'research_capability_scope': horizon_capability_scope(
                        document, coverage, issues, entry, comparison, hard_exit)})


def audit_ranking(document, source_root):
    rows, values = inventory_sources(document, source_root)
    by_id = {r['id']: r for r in rows}
    requested, observed = document['requested'], document['observed']
    require(isinstance(requested, dict) and isinstance(observed, dict), 'METHOD_SELECTION_OBJECTS_REQUIRED')
    fields = ('profile_id', 'profile_version', 'method', 'implementation_sha256')
    findings, records = [], {}
    for label, selection in (('requested', requested), ('observed', observed)):
        sid = selection['profile_source_id']
        profile = values.get(sid)
        records[label] = {'declaration': copy.deepcopy(selection), 'source': by_id.get(sid)}
        if not isinstance(profile, dict) or by_id[sid]['status'] != 'BYTES_MATCH':
            findings.append(label + ':PROFILE_BYTES_UNAVAILABLE')
            continue
        records[label]['profile_canonical_sha256'] = digest(profile)
        records[label]['profile'] = profile
        for field in ('profile_id', 'profile_version'):
            if selection.get(field) != profile.get(field):
                findings.append(label + ':PROFILE_FIELD_MISMATCH:' + field)
        for field in fields:
            if not isinstance(selection.get(field), str) or not selection[field]:
                findings.append(label + ':METHOD_FIELD_MISSING:' + field)
        if not isinstance(selection.get('implementation_sha256'), str) or not re.fullmatch('[a-fA-F0-9]{64}', selection['implementation_sha256']):
            findings.append(label + ':IMPLEMENTATION_HASH_INVALID')
        if selection.get('implementation_source_id') is not None:
            implementation = by_id.get(selection['implementation_source_id'], {})
            if implementation.get('status') != 'BYTES_MATCH' or implementation.get('actual_sha256') != selection.get('implementation_sha256', '').lower():
                findings.append(label + ':IMPLEMENTATION_BYTES_MISMATCH_OR_UNAVAILABLE')
    for field in fields:
        if requested.get(field) != observed.get(field):
            findings.append('REQUESTED_OBSERVED_MISMATCH:' + field)
    if records['requested'].get('profile_canonical_sha256') != records['observed'].get('profile_canonical_sha256'):
        findings.append('REQUESTED_OBSERVED_PROFILE_HASH_MISMATCH')
    return envelope('RANKING_METHOD_AUDIT', document, {'status': 'METHOD_IDENTITY_MATCH' if not findings else 'METHOD_MISMATCH_OR_UNRESOLVED',
                    'requested': records['requested'], 'observed': records['observed'], 'findings': findings,
                    'ranking_execution_verified': False,
                    'limits': 'Matching declarations and profile bytes do not prove the scorer ran, intrinsic undervaluation or forecast quality.'})


def plan_strategy(document, source_root):
    """Keep one supplied strategy separate from prospective choices and missing observations."""
    which = document['strategy_source']
    sources, values = inventory_sources(document, source_root)
    source_id, path = which['source_id'], which['pointer']
    require(source_id in values, 'STRATEGY_SOURCE_BYTES_REQUIRED')
    selected = pointer(values[source_id], path)
    require(isinstance(selected, dict) and selected, 'STRATEGY_RECORD_REQUIRED')
    mode = document['design_kind']
    require(mode in ('research_contract', 'forward_paper'), 'STRATEGY_DESIGN_KIND')
    required = ['benchmark', 'variant_treatment', 'evaluation_window', 'execution_convention']
    if mode == 'forward_paper':
        required += ['variant_decision_record', 'quote_order_fill_reconciliation']
    else:
        required += ['development_validation_split']

    terms = document.get('design_terms', {})
    require(isinstance(terms, dict), 'DESIGN_TERMS_OBJECT_REQUIRED')
    resolved, missing = {}, []
    for name in required:
        term = terms.get(name)
        if term is None:
            missing.append(name)
            continue
        require(isinstance(term, dict), 'DESIGN_TERM_OBJECT_REQUIRED')
        if 'record_pointer' in term:
            require(set(term) == {'record_pointer'}, 'SOURCE_TERM_HAS_ADDED_VALUES')
            # All field pointers are relative to the selected record, never its enclosing file.
            value = pointer(selected, term['record_pointer'])
            basis = 'supplied'
        else:
            require(set(term) == {'proposal'}, 'EXPLICIT_PROPOSAL_REQUIRED')
            value, basis = term['proposal'], 'proposed'
        require(isinstance(value, (str, list, dict)) and bool(value) and
                (not isinstance(value, str) or bool(value.strip())), 'EMPTY_DESIGN_TERM')
        resolved[name] = {'basis': basis, 'value': value}
        if basis == 'supplied':
            resolved[name]['record_pointer'] = term['record_pointer']
    require(not (set(terms) - set(required)), 'UNRECOGNIZED_DESIGN_TERM')

    decisions = document.get('proposed_decision_rules', [])
    require(isinstance(decisions, list), 'DECISION_RULE_LIST_REQUIRED')
    assessed = set()
    for rule in decisions:
        require(isinstance(rule, dict) and rule.get('purpose') in ('performance', 'risk', 'operations'),
                'DECISION_RULE_PURPOSE')
        require(all(isinstance(rule.get(k), str) and rule[k].strip()
                    for k in ('measure', 'units', 'measurement_window', 'on_failure', 'if_unmeasurable')),
                'MEASURABLE_DECISION_RULE_REQUIRED')
        threshold = rule.get('threshold')
        require(type(threshold) in (int, float) and math.isfinite(threshold) and
                rule.get('comparison') in ('<', '<=', '>', '>=', '=='), 'DECISION_RULE_COMPARISON')
        assessed.add(rule['purpose'])
    purposes = ['performance', 'risk'] if mode == 'research_contract' else ['performance', 'risk', 'operations']
    missing.extend('decision_rule.' + purpose for purpose in purposes if purpose not in assessed)
    return envelope('PROSPECTIVE_STRATEGY_DESIGN', document, {
        'design_kind': mode, 'source_id': source_id, 'source_pointer': path,
        'source_sha256': next(row['actual_sha256'] for row in sources if row['id'] == source_id),
        'supplied_strategy': selected, 'design_terms': resolved, 'proposed_decision_rules': decisions,
        'missing_design_fields': missing, 'design_status': 'INCOMPLETE' if missing else 'DRAFT_FOR_REVIEW',
        'limits': 'No outcomes evaluated. Completeness checks the declared structure only. '
                  'A designated window or a drafted rule does not verify prior registration or an untouched sample.'})


def strategy_answer(document, source_root):
    from strategy_design_answer import controls
    original = document
    request_binding = None
    if 'original_request' in document:
        from research_record import bound_design
        selection, request_binding = bound_design(document, source_root)
        document = dict(document, strategy_source=selection)
    # One declaration governs selection in both representations. Legacy
    # plan-strategy accepts its original variant_treatment field unchanged.
    terms = dict(document.get('design_terms', {}))
    require('variant_treatment' not in terms, 'USE_STRUCTURED_VARIANT_POLICY')
    terms['variant_treatment'] = {'proposal': document['answer_controls']['variants']['mode']}
    draft = plan_strategy(dict(document, design_terms=terms), source_root)['result']
    answer_controls = document['answer_controls']
    if 'strategy_registration' in document:
        from strategy_registration import apply_registration
        answer_controls = apply_registration(document, draft, pointer)
    require(not draft['missing_design_fields'], 'COMPLETE_DECLARED_DESIGN_REQUIRED')
    draft['answer_controls'] = controls(answer_controls, draft['proposed_decision_rules'])
    primary = draft['answer_controls']['variants']['primary']
    if 'record_pointer' in primary:
        value = pointer(draft['supplied_strategy'], primary['record_pointer'])
        require(value is not None, 'MISSING_PRIMARY_SPECIFICATION')
        draft['primary_specification'] = {'basis': 'supplied', 'record_pointer': primary['record_pointer'], 'value': value}
    else:
        draft['primary_specification'] = {'basis': 'proposed', 'value': primary['proposal']}
    draft['source_path'] = next(s['path'] for s in document['sources'] if s['id'] == draft['source_id'])
    if draft['design_kind'] == 'forward_paper':
        from forward_reconciliation import protocol
        draft['forward_reconciliation'] = protocol()
    if request_binding is not None:
        draft['original_request_binding'] = request_binding
    if 'clock_fields' in document:
        from strategy_clock_scope import selected_clocks
        require(request_binding is not None and 'strategy_registration' in draft, 'ORIGINAL_REGISTERED_STRATEGY_REQUIRED')
        draft['clock_scope'] = selected_clocks(draft['supplied_strategy'], request_binding,
                                              draft['strategy_registration']['evaluation'],
                                              document['clock_fields'], pointer)
    return envelope('SOURCE_BOUND_STRATEGY_ANSWER', original, draft)


OPERATIONS = {'bind-request': bind_request, 'inventory-evidence': inventory_evidence,
              'route-horizon': route_horizon, 'audit-ranking': audit_ranking, 'plan-strategy': plan_strategy,
              'strategy-answer': strategy_answer}


def schema():
    from strategy_registration import registration_schema
    return {'schema_version': 1, 'operations': [*OPERATIONS, 'verify', 'deliver-strategy'],
            'source_contract': {'allowlist': ['inputs.json'], 'sources': [{'id': 'input', 'path': 'inputs.json',
                'sha256': 'EXACT_FILE_SHA256', 'format': 'json', 'role': 'actual_user_request'}]},
            'bind_request_fields': {'prompt_binding': {'source_id': 'prompt', 'pointer': ''},
                'bindings': [{'id': 'equity', 'source_id': 'input', 'pointer': '/account/equity',
                    'target': 'account_equity', 'usage': 'selected', 'required_role': 'observed_account',
                    'record_pointer': '/account', 'record_identity': {'pointer': '/account/id', 'expected': 'account-A'},
                    'metadata_pointers': {'observed_at': '/account/observed_at'}}]},
            'plan_strategy': {'design_kind': ['research_contract', 'forward_paper'],
                              'strategy_source': {'source_id': 'input', 'pointer': '/chosen_record'},
                              'design_terms': 'Use record_pointer relative to the selected record, or proposal. See references/strategy-evaluation.md.',
                              'proposed_decision_rules': ['purpose', 'measure', 'units', 'measurement_window',
                                                          'comparison', 'threshold', 'on_failure', 'if_unmeasurable']},
            'strategy_answer': {'base': 'plan_strategy',
                'registered_request_schema': registration_schema(),
                'preferred_registration': 'For a selected single-instrument long/cash record use --scoped-design with registered_request_schema.executable_design. Link the selected record, cash accrual, comparator, fill economics, activity floor and forward quality thresholds. Use --registered-design to replay prior comparator/calendar/estimator choices.',
                'legacy_scope': 'Open prose does not validate comparator inputs or a committed estimator.',
                'answer_controls': {
                'session_basis': 'Data calendar and bar eligibility', 'warmup': 'Required history and first eligible decision',
                'initial_state': 'Initial position, regime and tie handling',
                'variants': {'mode': 'fixed_primary', 'primary': {'record_pointer': '/variants/0'}},
                'sample': {'minimum_observations': 30, 'observation_unit': 'paired observations',
                           'minimum_events': 5, 'event_unit': 'completed decisions', 'rationale': 'Replace illustrative floors with justified minima'},
                'uncertainty': {'performance_rule': 0, 'confidence': 0.95, 'method': 'Predeclared interval estimator',
                                'dependence_treatment': 'Define dependence model and tuning choices'}},
                'structured_delivery': 'deliver-strategy OUTPUT --metadata HOST.json --private-output NEW writes NEW/files/first-response.md and NEW/files/response.json',
                'readback': 'verify OUTPUT --answer FINAL.md --rows FINAL.json checks provided text and rows; add --metadata HOST.json for the generated envelope'},
            'inventory_extra_fields': ['as_of', 'expected_acquisition_receipt_ids', 'acquisition_coverage', 'checks'],
            'check_kinds': ['primary_source', 'primary_freshness', 'research_handoff', 'pe_claim', 'revision', 'scenario_checks'],
            'horizon_fields': ['mode', 'as_of', 'entry_at', 'comparison_at', 'fixed_spec (fixed_exit only)',
                               'event_coverage: {through,basis}',
                               'event_exclusion_requirement (optional): not_declared | none | entry_only | full_hold',
                               'planning_assumptions: [{label,value,basis}]'],
            'ranking_fields': {'requested': ['profile_source_id', 'profile_id', 'profile_version', 'method', 'implementation_sha256'],
                               'observed': 'same fields as requested',
                               'optional': 'implementation_source_id binds the declared implementation hash to retained source bytes; no execution inferred'},
            'private_artifacts': ['request.json', 'report.json', 'receipt.json', 'source-bytes/<explicit allowlist path>'],
            'verify': 'verify EXPORT_DIRECTORY checks retained hashes, source presence and installed-helper replay; no authentication or execution permission claim',
            'limits': 'Schema describes explicit caller inputs. It does not infer correct selections from a prompt.'}


def parse_document(raw):
    from report_facts import strict_json
    document = strict_json(raw)
    require(isinstance(document, dict), 'REQUEST_OBJECT_REQUIRED')
    return document


def retained_sources(document, root):
    """Read only explicit local allowlist entries, without interpreting bytes."""
    names = document.get('allowlist', [])
    require(isinstance(names, list), 'EXPLICIT_ALLOWLIST_REQUIRED')
    clean = [relative_name(n) for n in names]
    require(len({n.casefold() for n in clean}) == len(clean), 'UNIQUE_ALLOWLIST_PATHS_REQUIRED')
    require(not clean or root is not None, 'SOURCE_ROOT_REQUIRED')
    files, absent = {}, []
    for name in clean:
        path = source_path(root, name)
        if path.is_file():
            files[name] = path.read_bytes()
        else:
            absent.append(name)
    return files, absent


def write_files(directory, files):
    for name, raw in files.items():
        path = source_path(directory, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(raw)


def export_run(operation, raw, source_root, output, original_contract=None):
    """Evaluate a frozen byte snapshot, then retain it in an exclusive directory."""
    require(operation in OPERATIONS, 'UNKNOWN_OPERATION')
    document = parse_document(raw)
    if operation == 'strategy-answer':
        from strategy_intake import mentions_fields, packaged_request
        package = packaged_request(source_root)
        require(not package or not any(mentions_fields(raw) for raw in package),
                'USE_ORIGINAL_REQUEST_ENTRY_FOR_PACKAGED_STRATEGY_DESIGNS')
        if original_contract is not None:
            from response_contract import declared_fields
            declared_fields(original_contract)
            require('original_request' in document, 'DELIVERY_CONTRACT_REQUIRES_BOUND_ORIGINAL_REQUEST')
    saved, absent = retained_sources(document, source_root)
    output = binding_json.local_path(output)
    require(not output.is_relative_to(ROOT), 'PRIVATE_OUTPUT_OUTSIDE_SKILL_REQUIRED')
    # Running helpers against this snapshot avoids a hash/read race and makes
    # source checks reproducible even after the original source root disappears.
    with tempfile.TemporaryDirectory() as temporary:
        snapshot = Path(temporary)
        write_files(snapshot, saved)
        report = OPERATIONS[operation](document, snapshot)
    files = {'request.json': raw, 'report.json': (binding_json.encode(report) + '\n').encode('utf-8')}
    if operation == 'strategy-answer':
        from strategy_design_answer import render
        files['answer.md'] = render(report['result']).encode('utf-8')
        files['answer-rows.json'] = (binding_json.encode([report['result']]) + '\n').encode('utf-8')
    files.update({'source-bytes/' + name: content for name, content in saved.items()})
    receipt_version = 2 if operation == 'strategy-answer' and 'forward_reconciliation' in report['result'] else 1
    if original_contract is not None:
        require(operation == 'strategy-answer', 'RESPONSE_DECLARATION_FOR_STRATEGY_ONLY')
        files['response-contract.txt'] = original_contract
        receipt_version = 3
    manifest = {'schema_version': receipt_version, 'operation': operation, 'absent_source_paths': absent,
                'files': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
                'source_authenticity_verified': False, 'execution_gates': []}
    files['receipt.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode('utf-8')
    output.mkdir(mode=0o700)
    (output / 'source-bytes').mkdir(mode=0o700)
    if operation == 'strategy-answer':
        from strategy_registration import STRICT, LEGACY
        manifest['registration_scope'] = STRICT if 'strategy_registration' in document else LEGACY
        files['receipt.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode('utf-8')
    write_files(output, files)
    return report


def strategy_response(markdown, typed_rows, metadata_raw):
    """Retain host declarations as JSON values. The replay owns the answer hash and rows."""
    metadata = binding_json.strict_json(metadata_raw)
    require(isinstance(metadata, dict) and not {'rows', 'first_response_sha256'}.intersection(metadata),
            'HOST_METADATA_OBJECT_WITHOUT_GENERATED_FIELDS_REQUIRED')
    if len(typed_rows) == 1 and isinstance(typed_rows[0], dict) and 'clock_scope' in typed_rows[0]:
        from strategy_clock_scope import limitations
        expected = limitations(typed_rows[0])
        require('limitations' not in metadata or metadata['limitations'] in ([], expected),
                'SCOPED_STRATEGY_LIMITATIONS_ARE_GENERATED_USE_EXECUTION_LIMITATIONS_FOR_HOST_DISCLOSURES')
        metadata = dict(metadata, limitations=expected)
    envelope = dict(metadata, first_response_sha256=hashlib.sha256(markdown).hexdigest(), rows=typed_rows)
    return (binding_json.encode(envelope) + '\n').encode('utf-8')


def delivery_path(value):
    """Require local canonical paths with no symlink or Windows reparse component."""
    from supplied_research import safe
    path = Path(value).absolute()
    require('://' not in str(value) and not str(path).startswith(('\\\\', '//')), 'LOCAL_PATH_REQUIRED')
    require('..' not in Path(value).parts and safe(path) == path, 'CANONICAL_DELIVERY_PATH_REQUIRED')
    return path


def verify(directory, answer=None, rows=None, metadata=None, response_contract=None):
    """Verify local byte consistency and replay installed helpers, never imports."""
    if response_contract is not None:
        require(metadata is not None, 'RESPONSE_CONTRACT_REQUIRES_METADATA_READBACK')
    if metadata is not None:
        require(answer is not None and rows is not None, 'METADATA_READBACK_REQUIRES_STRATEGY_PAIR')
        root = delivery_path(directory)
        for supplied in (answer, rows, metadata):
            delivery_path(supplied)
        for member in root.rglob('*'):
            delivery_path(member)
    root = binding_json.local_path(directory)
    receipt = parse_document(source_path(root, 'receipt.json').read_bytes())
    version = receipt.get('schema_version')
    require(type(version) is int and version in (1, 2, 3) and receipt.get('operation') in OPERATIONS,
            'RECEIPT_SCHEMA_INVALID')
    files = receipt.get('files')
    expects_answer = receipt['operation'] == 'strategy-answer'
    outputs = {'request.json', 'report.json'}
    if version == 3:
        require(expects_answer, 'BOUND_ORIGINAL_STRATEGY_RECEIPT_REQUIRED')
        outputs.add('response-contract.txt')
    if expects_answer:
        outputs.update(('answer.md', 'answer-rows.json'))
    require((answer is None and rows is None) or expects_answer, 'STRATEGY_ANSWER_RECEIPT_REQUIRED')
    require(isinstance(files, dict) and 'request.json' in files and 'report.json' in files, 'RECEIPT_FILES_REQUIRED')
    for name, expected in files.items():
        require(name in outputs or name.startswith('source-bytes/'), 'RECEIPT_PATH_UNSUPPORTED')
        path = source_path(root, name)
        require(isinstance(expected, str) and re.fullmatch('[a-f0-9]{64}', expected), 'RECEIPT_HASH_INVALID')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'RETAINED_BYTES_MISMATCH')
    document = parse_document((root / 'request.json').read_bytes())
    saved, absent = retained_sources(document, root / 'source-bytes')
    require(sorted(absent) == sorted(receipt.get('absent_source_paths', [])), 'SOURCE_PRESENCE_MISMATCH')
    require(set(files) == outputs | {'source-bytes/' + n for n in saved}, 'SOURCE_INVENTORY_MISMATCH')
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    require(actual_files == set(files) | {'receipt.json'}, 'UNLISTED_RETAINED_FILE')
    expected_report = binding_json.strict_json((root / 'report.json').read_bytes())
    report = OPERATIONS[receipt['operation']](document, root / 'source-bytes')
    forward = expects_answer and report['result']['design_kind'] == 'forward_paper'
    require(version != 2 or forward, 'FORWARD_RECEIPT_REQUIRED')
    if version == 3:
        from response_contract import declared_fields
        retained_contract = source_path(root, 'response-contract.txt').read_bytes()
        required_fields = declared_fields(retained_contract)
        require('original_request_binding' in report['result'], 'ORIGINAL_REQUEST_REPLAY_REQUIRED')
        if response_contract is not None:
            require(delivery_path(response_contract).read_bytes() == retained_contract, 'ORIGINAL_RESPONSE_DECLARATION_CHANGED')
    if forward and version == 1:
        # Earlier receipts predate register-level reconciliation. Replay their original projection.
        del report['result']['forward_reconciliation']
    replay_json = binding_json.strict_json(binding_json.encode(report).encode('utf-8'))
    require(not binding_json.differences(replay_json, expected_report), 'REPLAY_REPORT_MISMATCH')
    checks = {'retained_export': True}
    if expects_answer:
        from strategy_design_answer import render
        projection = render(report['result']).encode('utf-8')
        require((root / 'answer.md').read_bytes() == projection, 'STRATEGY_ANSWER_REPLAY_MISMATCH')
        typed = binding_json.encode([report['result']])
        require((root / 'answer-rows.json').read_bytes() == (typed + '\n').encode('utf-8'), 'STRATEGY_ROWS_REPLAY_MISMATCH')
        if answer is not None:
            answer_path = binding_json.local_path(answer)
            require(answer_path.read_bytes() == projection, 'FINAL_STRATEGY_ANSWER_DIFFERS')
            checks['markdown'] = 'export_member' if answer_path.is_relative_to(root) else 'provided_file'
        if rows is not None:
            rows_path = binding_json.local_path(rows)
            final_raw = rows_path.read_bytes()
            final = binding_json.strict_json(final_raw)
            payload = final['rows'] if isinstance(final, dict) else final
            require(binding_json.encode(payload) == typed, 'FINAL_STRATEGY_ROWS_DIFFER')
            checks['rows'] = 'export_member' if rows_path.is_relative_to(root) else 'provided_file'
        if metadata is not None:
            from supplied_research import read
            declared = read(delivery_path(metadata))
            require(final_raw == strategy_response(projection, [report['result']], declared),
                    'FINAL_STRATEGY_ENVELOPE_DIFFERS')
            checks['declared_metadata_sha256'] = hashlib.sha256(declared).hexdigest()
            if version == 3 or response_contract is not None:
                from response_contract import audit
                checks['response_contract'] = audit(retained_contract if version == 3 else read(delivery_path(response_contract)), final)
                if version == 3:
                    require(current_strategy_design(report['result']), 'SCOPED_INCOMPLETE_REGISTER_EXECUTABLE_ECONOMICS_AND_SELECTED_CLOCKS')
    result = {'status': 'RETAINED_BYTES_AND_REPLAY_CONSISTENT', 'operation': receipt['operation'],
              'file_count': len(files), 'checks': checks, 'submission_observed': False,
              'source_authenticity_verified': False, 'execution_gates': []}
    if expects_answer:
        from strategy_registration import STRICT, LEGACY
        scope = STRICT if 'strategy_registration' in document else LEGACY
        require(receipt.get('registration_scope', LEGACY) == scope, 'STRATEGY_REGISTRATION_SCOPE_MISMATCH')
        result['registration_scope'] = scope
        if version == 3:
            result['delivery_scope'] = ('current_registered_strategy' if current_strategy_design(report['result'])
                                        else 'scoped_incomplete')
            result['required_response_fields'] = required_fields
    if expects_answer and answer is None and rows is None:
        result['next_for_structured_delivery'] = 'deliver-strategy EXPORT --metadata HOST.json --private-output NEW'
    return result


def current_strategy_design(row):
    registration = row.get('strategy_registration', {})
    economics = registration.get('economics', {})
    return bool(row.get('original_request_binding') and 'clock_scope' in row and economics and
                (row['design_kind'] != 'forward_paper' or economics.get('execution_quality')))


def deliver_strategy(directory, metadata, output, response_contract=None):
    """Verify both staged files, reserve the destination exclusively and publish the pair together."""
    from supplied_research import read, write
    root, metadata, output = map(delivery_path, (directory, metadata, output))
    require(not output.exists() and not output.is_relative_to(ROOT) and not output.is_relative_to(root)
            and not root.is_relative_to(output) and not metadata.is_relative_to(output),
            'NEW_DISJOINT_PRIVATE_DELIVERY_REQUIRED')
    require(parse_document(read(root / 'receipt.json')).get('operation') == 'strategy-answer',
            'STRATEGY_ANSWER_RECEIPT_REQUIRED')
    markdown = read(root / 'answer.md')
    rows = binding_json.strict_json(read(root / 'answer-rows.json'))
    envelope = strategy_response(markdown, rows, read(metadata))
    if response_contract is not None:
        from response_contract import audit
        original_contract = read(delivery_path(response_contract))
        expected_contract = audit(original_contract, binding_json.strict_json(envelope))
    pair = {'first-response.md': markdown, 'response.json': envelope}
    # Same-filesystem rename publishes both closed files inside the new, owned directory.
    with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
        staged = Path(temporary).resolve() / 'files'
        for name, raw in pair.items():
            write(staged, name, raw)
        audit = verify(root, staged / 'first-response.md', staged / 'response.json', metadata, response_contract)
        if response_contract is not None:
            require(audit['checks']['response_contract'] == expected_contract, 'RESPONSE_CONTRACT_CHANGED')
        output.mkdir(mode=0o700)
        final = output / 'files'
        staged.rename(final)
    for name, raw in pair.items():
        require(read(final / name) == raw, 'PUBLISHED_STRATEGY_PAIR_DIFFERS')
    if 'delivery_scope' not in audit:
        audit['delivery_scope'] = ('provided_contract_checked_during_delivery' if response_contract is not None
                                   else 'scoped_incomplete_original_delivery_contract_unbound')
    audit['local_files_sha256'] = {'files/' + name: hashlib.sha256(raw).hexdigest() for name, raw in pair.items()}
    return audit


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=[*OPERATIONS, 'schema', 'verify', 'deliver-strategy']); p.add_argument('input', nargs='?')
    p.add_argument('--source-root'); p.add_argument('--private-output')
    p.add_argument('--answer', help='Verify the exact response file against a strategy-answer receipt')
    p.add_argument('--rows', help='Verify a JSON row list or the rows in a response envelope')
    p.add_argument('--metadata', help='Host JSON declarations for the strategy response envelope')
    p.add_argument('--response-contract', help='Original response field declaration or required-key JSON file')
    args = p.parse_args()
    if args.response_contract is not None and args.operation not in ('deliver-strategy', 'verify'):
        p.error('--response-contract is supported by deliver-strategy and verify')
    if args.operation == 'schema':
        print(json.dumps(schema(), indent=2)); return
    try:
        if args.operation == 'verify':
            require(args.input is not None, 'EXPORT_DIRECTORY_REQUIRED')
            audit = verify(args.input, args.answer, args.rows, args.metadata, args.response_contract)
            if audit['operation'] == 'strategy-answer':
                print(json.dumps(audit, sort_keys=True))
            return
        if args.operation == 'deliver-strategy':
            require(args.input and args.metadata and args.private_output and not any((args.source_root, args.answer, args.rows)),
                    'DELIVERY_REQUIRES_EXPORT_METADATA_AND_NEW_PRIVATE_OUTPUT')
            print(json.dumps(deliver_strategy(args.input, args.metadata, args.private_output, args.response_contract), sort_keys=True))
            return
        require(args.metadata is None, 'METADATA_REQUIRES_STRATEGY_DELIVERY_OR_VERIFY')
        require(args.answer is None and args.rows is None, 'ANSWER_VERIFICATION_ONLY')
        require(args.input is not None and args.private_output is not None, 'INPUT_AND_PRIVATE_OUTPUT_REQUIRED')
        require(args.source_root is not None or args.operation == 'route-horizon', 'SOURCE_ROOT_REQUIRED')
        raw = binding_json.local_path(args.input).read_bytes()
        export_run(args.operation, raw, args.source_root, args.private_output)
        if args.operation == 'strategy-answer':
            receipt = parse_document((Path(args.private_output) / 'receipt.json').read_bytes())
            print(json.dumps({'operation': args.operation, 'registration_scope': receipt['registration_scope'],
                              'delivery_scope': 'scoped_incomplete_original_delivery_contract_unbound'}))
    except (ValueError, KeyError, IndexError, TypeError, OSError, RuntimeError) as exc:
        if str(exc) == 'USE_ORIGINAL_REQUEST_ENTRY_FOR_PACKAGED_STRATEGY_DESIGNS':
            p.exit(2, 'Use research_preflight.py --request with the original prompt, source root and design choices.\n')
        if str(exc).startswith(('SCOPED_INCOMPLETE_', 'MISSING_REQUIRED_RESPONSE_FIELDS')):
            p.exit(2, 'Delivery incomplete. Check the original response fields and the registered executable economics.\n')
        p.exit(2, 'Research receipt unavailable: inspect local schema, bindings and output path. Native execution permissions unchanged.\n')


if __name__ == '__main__':
    main()
