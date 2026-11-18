"""Build the actual strategy/date/field research requirement grid.

This assesses supplied source-bound observations, not source authenticity or broker
permission. There is no inferred historical roster, filled price or execution gate.
"""
from collections import Counter
from quant_data_contracts import require, digest, text, day, instant, sources, pointer, finite, cli

STATUSES = {'observed', 'reference', 'modeled', 'unavailable'}
PURPOSES = {'signal', 'valuation', 'execution'}


def intervals(value):
    if value is None:
        return None
    require(isinstance(value, list), 'INTERVAL_LIST_OR_NULL')
    out = []
    for row in value:
        a, b = day(row['start_inclusive']), row['end_exclusive']
        require(b is None or day(b) > a, 'INTERVAL_ORDER')
        out.append((a, b))
    return out


def contains(ranges, session):
    return None if ranges is None else any(a <= session and (b is None or session < b) for a, b in ranges)


def assess(document):
    require(type(document.get('schema_version')) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    text(document['strategy_id'], 'STRATEGY_ID')
    require(document['universe_mode'] in {'current_roster', 'historical_membership'}, 'UNIVERSE_MODE')
    calendar = document['sessions']
    require(isinstance(calendar, list) and calendar and len(calendar) <= 100000, 'BOUNDED_SESSION_CALENDAR')
    require(calendar == sorted(set(map(day, calendar))), 'UNIQUE_ORDERED_CALENDAR')
    indices = {x: i for i, x in enumerate(calendar)}
    smap = sources(document['sources'])
    scope_evidence = document.get('scope_evidence_ids', [])
    require(isinstance(scope_evidence, list) and all(x in smap for x in scope_evidence), 'SCOPE_EVIDENCE_IDS')
    securities = {}
    for row in document['securities']:
        sid = text(row['security_id'], 'SECURITY_ID')
        require(sid not in securities, 'DUPLICATE_SECURITY')
        require(row['identity_status'] in {'source_bound', 'unknown'}, 'IDENTITY_STATUS')
        require(isinstance(row['evidence_ids'], list) and all(x in smap for x in row['evidence_ids']), 'SECURITY_EVIDENCE_IDS')
        require(row['identity_status'] != 'source_bound' or bool(row['evidence_ids']), 'IDENTITY_EVIDENCE_REQUIRED')
        require(not {'listing', 'membership'} & row.keys(), 'RESERVED_SECURITY_KEYS')
        securities[sid] = {**row, 'listing': intervals(row['listing_intervals']),
                           'membership': intervals(row['membership_intervals'])}
    require(bool(securities), 'REQUESTED_SECURITIES_REQUIRED')
    requirements = document['requirements']
    require(requirements and len({r['id'] for r in requirements}) == len(requirements), 'UNIQUE_REQUIREMENTS')
    for r in requirements:
        text(r['id'], 'REQUIREMENT_ID'); text(r['field'], 'FIELD')
        text(r['unit'], 'REQUIREMENT_UNIT'); text(r['currency'], 'REQUIREMENT_CURRENCY')
        require(r['numeric_domain'] in {'finite', 'positive', 'nonnegative'}, 'NUMERIC_DOMAIN')
        require(r['purpose'] in PURPOSES, 'REQUIREMENT_PURPOSE')
        require(r['scope'] in {'eligible', 'held', 'eligible_or_held'}, 'REQUIREMENT_SECURITY_SCOPE')
        require(type(r['lookback_sessions']) is int and 1 <= r['lookback_sessions'] <= 10000, 'LOOKBACK_COUNT')
        require(r['purpose'] != 'execution' or r['lookback_sessions'] == 1, 'EXECUTION_LOOKBACK_ONE')
    policy = document['valuation_policy']
    require(set(policy) == {'allow_reference', 'allow_modeled'} and all(type(x) is bool for x in policy.values()), 'EXPLICIT_VALUATION_POLICY')
    observations = {}
    for row in document['observations']:
        sid = row['security_id']; session = day(row['session']); field = text(row['field'], 'OBSERVATION_FIELD')
        require(sid in securities, 'UNREQUESTED_OBSERVATION_SECURITY')
        key = sid, session, field
        require(row['status'] in STATUSES, 'OBSERVATION_STATUS')
        require(key not in observations, 'CONFLICTING_OBSERVATIONS_SELECT_VINTAGE_FIRST')
        available = row.get('available_at')
        if available is not None:
            instant(available)
        if row['status'] != 'unavailable':
            require(finite(row['value']), 'FINITE_OBSERVATION_VALUE')
            require(row['source_id'] in smap, 'OBSERVATION_SOURCE_REQUIRED')
            extracted = pointer(smap[row['source_id']]['body'], row['source_record_pointer'])
            require(isinstance(extracted, dict), 'OBSERVATION_RECORD_POINTER')
            for name in ('security_id', 'session', 'field', 'value', 'status', 'available_at', 'unit', 'currency'):
                require(name in row and name in extracted and digest(extracted[name]) == digest(row[name]), 'OBSERVATION_SOURCE_METADATA_MISMATCH:' + name)
            if 'executable' in row:
                require(type(row['executable']) is bool and extracted.get('executable') is row['executable'], 'EXECUTION_ANNOTATION_SOURCE_MISMATCH')
        observations[key] = row
    decision_ids = set(); grid = []; warnings = []; skipped = []; total_expected = 0
    for d in document['decisions']:
        did = text(d['id'], 'DECISION_ID'); require(did not in decision_ids, 'DUPLICATE_DECISION')
        decision_ids.add(did)
        decision_at = instant(d['decision_at']); valuation_at = instant(d['valuation_at']); execution_at = instant(d['execution_at'])
        require(decision_at < execution_at, 'DECISION_MUST_PRECEDE_EXECUTION')
        signal_session, execution_session = day(d['signal_session']), day(d['execution_session'])
        require(signal_session in indices and execution_session in indices, 'DECISION_OUTSIDE_CALENDAR')
        require(signal_session <= decision_at.date().isoformat() and execution_session >= signal_session, 'DECISION_SESSION_ORDER')
        require(execution_session <= execution_at.date().isoformat(), 'EXECUTION_SESSION_AFTER_EXECUTION_TIME')
        held = d['held_security_ids']; require(isinstance(held, list) and set(held) <= set(securities), 'UNKNOWN_HELD_SECURITY')
        eligible, uncertain = set(), set()
        for sid, sec in securities.items():
            listing = contains(sec['listing'], signal_session)
            membership = contains(sec['membership'], signal_session) if document['universe_mode'] == 'historical_membership' else True
            if listing is not False and membership is not False:
                eligible.add(sid)
                if listing is None or membership is None or sec['identity_status'] == 'unknown':
                    uncertain.add(sid)
        for req in requirements:
            candidates = eligible if req['scope'] == 'eligible' else set(held) if req['scope'] == 'held' else eligible | set(held)
            anchor = execution_session if req['purpose'] == 'execution' else signal_session
            stop = indices[anchor] + 1; start = stop - req['lookback_sessions']
            if start < 0:
                warnings.append({'decision_id': did, 'requirement_id': req['id'], 'reason': 'INSUFFICIENT_CALENDAR_LOOKBACK', 'missing_sessions': -start})
            needed = calendar[max(0, start):stop]
            total_expected += len(candidates) * len(needed)
            require(total_expected <= 2000000, 'REQUIREMENT_GRID_TOO_LARGE_SPLIT_THE_RUN')
            for sid in sorted(candidates):
                sec = securities[sid]
                for session in needed:
                    row = observations.get((sid, session, req['field']))
                    status = row['status'] if row else 'unavailable'
                    reasons = []
                    listed = contains(sec['listing'], session)
                    if listed is False:
                        status = 'outside_lifetime'
                        reasons.append('INSUFFICIENT_LISTED_HISTORY' if req['purpose'] == 'signal' else 'UNLISTED_POSITION_OR_EXECUTION_REQUIRES_EVENT_LEDGER')
                    elif listed is None:
                        reasons.append('LISTING_BOUNDS_UNKNOWN')
                    if sid in uncertain:
                        reasons.append('ELIGIBILITY_OR_IDENTITY_UNRESOLVED')
                    if sec['identity_status'] == 'unknown':
                        reasons.append('IDENTITY_UNRESOLVED')
                    cutoff = decision_at if req['purpose'] == 'signal' else valuation_at if req['purpose'] == 'valuation' else execution_at
                    if status not in {'unavailable', 'outside_lifetime'}:
                        if row['unit'] != req['unit'] or row['currency'] != req['currency']:
                            reasons.append('UNIT_OR_CURRENCY_MISMATCH')
                        if req['numeric_domain'] == 'positive' and row['value'] <= 0:
                            reasons.append('NONPOSITIVE_VALUE')
                        if req['numeric_domain'] == 'nonnegative' and row['value'] < 0:
                            reasons.append('NEGATIVE_VALUE')
                        if row.get('available_at') is None:
                            reasons.append('AVAILABILITY_UNKNOWN')
                        elif instant(row['available_at']) > cutoff:
                            reasons.append('NOT_AVAILABLE_FOR_PURPOSE')
                    if status == 'unavailable':
                        reasons.append('OBSERVATION_UNAVAILABLE')
                    if req['purpose'] == 'signal' and status in {'reference', 'modeled'}:
                        reasons.append('NONOBSERVED_SIGNAL_INPUT')
                    if req['purpose'] == 'execution':
                        if status != 'observed':reasons.append('NONOBSERVED_EXECUTION_PRICE')
                        if row is None or row.get('executable') is not True:reasons.append('EXECUTABILITY_NOT_ESTABLISHED')
                    if req['purpose'] == 'valuation':
                        if status == 'reference' and not policy['allow_reference']:reasons.append('REFERENCE_VALUATION_NOT_SELECTED')
                        if status == 'modeled' and not policy['allow_modeled']:reasons.append('MODEL_VALUATION_NOT_SELECTED')
                    grid.append({'decision_id': did, 'requirement_id': req['id'], 'security_id': sid,
                                 'session': session, 'field': req['field'], 'purpose': req['purpose'],
                                 'observation_status': status, 'usable_for_declared_purpose': not reasons,
                                 'reasons': sorted(set(reasons)), 'source_id': row.get('source_id') if row else None,
                                 'available_at': row.get('available_at') if row else None})
        skipped.extend({'decision_id': did, 'security_id': sid, 'reason': 'OUTSIDE_DECLARED_LISTING_OR_MEMBERSHIP'}
                       for sid in sorted(set(securities) - eligible - set(held)))
    require(bool(decision_ids), 'DECISIONS_REQUIRED')
    counts = dict(Counter(r['observation_status'] for r in grid))
    failures = sum(not r['usable_for_declared_purpose'] for r in grid)
    complete = bool(grid) and failures == 0 and not warnings
    modeled = counts.get('modeled', 0); reference = counts.get('reference', 0)
    status = 'DECLARED_STRICT_GRID_COMPLETE' if complete and not modeled and not reference else 'DECLARED_SCENARIO_GRID_COMPLETE' if complete else 'RESEARCH_GAPS_REMAIN'
    if not grid:status = 'NO_REQUIREMENTS_IN_DECLARED_SCOPE'
    return {'schema_version': 1, 'method': 'strategy_requirement_grid_v1', 'strategy_id': document['strategy_id'],
            'status': status, 'universe_mode': document['universe_mode'], 'requested_security_count': len(securities),
            'grid': grid, 'grid_status_counts': counts, 'unusable_requirements': failures, 'warnings': warnings,
            'skipped_outside_declared_scope': skipped, 'scope_evidence_ids': scope_evidence,
            'strict_observed_grid_complete': complete and not modeled and not reference,
            'declared_policy_grid_complete': complete, 'input_sha256': digest(document),
            'source_authenticity_verified': False, 'historical_universe_completeness_certified': False,
            'limits': ['Completeness applies only to this supplied strategy grid, source-pointer checks and declared calendar/identity intervals.',
                       'Current-roster history is survivor-conditioned; an empty grid or unavailable membership is not a full-universe pass.',
                       'Reference/model values can qualify only for explicitly selected valuation scenarios, never signals or fills.',
                       'Executability, source publication and identity intervals still require substantive source review; this report does not authorize or block broker actions.']}


if __name__ == '__main__':
    cli(assess)
