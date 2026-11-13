"""Audit explicitly related research clocks without inferring natural-language intent.

The route is the caller's declared authority for one request, not authenticated
user intent. Each context contains the original helper input/locked contract;
the audit recomputes its clock rather than trusting a transcribed result.
"""
from __future__ import annotations

import copy
from datetime import date

from price_audit import timestamp
from research_contracts import digest, envelope, require, route_horizon


def _clock(value):
    require(isinstance(value, str), 'CLOCK_STRING_REQUIRED')
    if len(value) == 10:
        return 'date', date.fromisoformat(value)
    return 'instant', timestamp(value)


def _compare(expected, actual):
    if actual is None:
        return 'MISSING'
    a, b = _clock(expected), _clock(actual)
    if a[0] != b[0]:
        return 'PRECISION_MISMATCH'
    return 'MATCH' if a[1] == b[1] else 'DIFFERENT'


def _route(document):
    routed = route_horizon(document)['result']
    routed['as_of'] = (routed['resolved_fixed_exit']['as_of'] if routed['mode'] == 'fixed_exit'
                       else document['as_of'])
    return routed


def _resolve(kind, document, clock_role=None):
    if kind == 'route_request':
        routed = _route(document)
        return routed, routed['issues']
    if kind in ('clock_request', 'screen_request'):
        require(clock_role in ('hard_exit', 'comparison_only'), 'EXPLICIT_LEGACY_CLOCK_ROLE_REQUIRED')
        if kind == 'screen_request':
            if document.get('decision_mode') != 'fixed_horizon':
                return None, ['SCREEN_HAS_NO_EXACT_CLOCK']
            spec = document['horizon']
        else:
            spec = document
        import horizon_review
        resolved = horizon_review.resolve_horizon(spec)
        forced = clock_role == 'hard_exit'
        # The legacy resolver is also used for analytical comparisons. Its
        # exit_at alias alone cannot establish a forced-sale instruction.
        return {'mode': 'fixed_exit' if forced else 'comparison', 'as_of': resolved['as_of'],
                'entry_at': resolved['entry_at'],
                'comparison_at': resolved['exit_at'], 'forced_exit': forced,
                'hard_exit_at': resolved['exit_at'] if forced else None,
                'resolved_legacy_clock': resolved, 'declared_clock_role': clock_role,
                'calculation_exit_buffer_minutes': spec['exit_buffer_minutes'],
                'exit_buffer_minutes': spec['exit_buffer_minutes'] if forced else None}, []
    require(kind == 'handoff_contract', 'UNKNOWN_HORIZON_CONTEXT_KIND')
    from research_handoff import verify_contract
    verify_contract(document)
    mandate = document['mandate']
    return {'mode': mandate['horizon_mode'], 'as_of': mandate['information_cutoff'], 'entry_at': mandate['entry_at'],
            'comparison_at': mandate['comparison_at'], 'forced_exit': mandate['forced_exit'],
            'hard_exit_at': mandate['hard_exit_at']}, []


def audit(document):
    """Compare same-request contexts; this never relaxes a screen or authorizes an exit."""
    require(isinstance(document, dict), 'HORIZON_AUDIT_OBJECT_REQUIRED')
    request_id = document.get('request_id')
    require(isinstance(request_id, str) and request_id.strip(), 'REQUEST_ID_REQUIRED')
    authority = document.get('route')
    require(isinstance(authority, dict) and isinstance(authority.get('document'), dict),
            'ROUTE_REQUEST_REQUIRED')
    require(authority.get('request_id') == request_id, 'ROUTE_REQUEST_ID_MISMATCH')
    contexts = document.get('contexts')
    require(isinstance(contexts, list) and contexts, 'HORIZON_CONTEXTS_REQUIRED')
    ids = [r.get('id') for r in contexts if isinstance(r, dict)]
    require(len(ids) == len(contexts) and all(isinstance(x, str) and x for x in ids)
            and len(set(ids)) == len(ids), 'UNIQUE_CONTEXT_IDS_REQUIRED')
    route = _route(authority['document'])
    findings = [{'context_id': None, 'code': x} for x in route['issues']]
    rows = []
    for context in contexts:
        row = {'id': context['id'], 'kind': context.get('kind'),
               'request_id': context.get('request_id'), 'findings': []}
        payload = context.get('document')
        require(isinstance(payload, dict), 'CONTEXT_DOCUMENT_REQUIRED')
        row['input_sha256'] = digest(payload)
        if context.get('request_id') != request_id:
            row['findings'].append('CONTEXT_REQUEST_ID_MISMATCH')
        try:
            actual, issues = _resolve(context.get('kind'), payload, context.get('clock_role'))
        except (KeyError, TypeError, ValueError) as exc:
            actual, issues = None, ['INVALID_CONTEXT:' + str(exc)]
        row['resolved'] = copy.deepcopy(actual)
        row['findings'].extend(issues)
        if actual is not None:
            for field in ('as_of', 'entry_at', 'comparison_at'):
                relation = _compare(route[field], actual.get(field))
                if relation != 'MATCH':
                    row['findings'].append(field.upper() + '_' + relation)
            if actual.get('forced_exit') != route['forced_exit']:
                row['findings'].append('FORCED_EXIT_MODE_CONFLICT')
            if not route['forced_exit']:
                if actual.get('hard_exit_at') is not None:
                    row['findings'].append('COMPARISON_HAS_HARD_EXIT')
                if actual.get('exit_buffer_minutes') is not None:
                    row['findings'].append('COMPARISON_HAS_EXIT_BUFFER')
            elif actual.get('hard_exit_at') is None:
                row['findings'].append('HARD_EXIT_MISSING')
            elif _compare(route['hard_exit_at'], actual['hard_exit_at']) != 'MATCH':
                row['findings'].append('HARD_EXIT_CLOCK_CONFLICT')
        row['status'] = ('CONFLICT' if actual is not None or 'CONTEXT_REQUEST_ID_MISMATCH' in row['findings']
                         else 'UNRESOLVED') if row['findings'] else 'CONSISTENT'
        findings.extend({'context_id': row['id'], 'code': x} for x in row['findings'])
        rows.append(row)
    status = ('CONFLICT' if any(r['status'] == 'CONFLICT' for r in rows) or route['issues']
              else 'UNRESOLVED' if findings else 'CONSISTENT')
    result = {'request_id': request_id, 'route_input_sha256': digest(authority['document']),
              'route': route, 'contexts': rows, 'findings': findings, 'status': status,
              'scope': 'EXPLICIT_SAME_REQUEST_CLOCK_CONSISTENCY',
              'intent_authenticated': False, 'screen_checks_replaced': False,
              'narrative_correctness_verified': False}
    return envelope('HORIZON_CONSISTENCY_AUDIT', document, result)
