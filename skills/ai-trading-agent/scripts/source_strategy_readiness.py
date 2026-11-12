"""Compose supplied daily identity/vintage sources into the readiness assessor.

No fetching, inferred ticker continuity, fill-forward, or independent grid rules.
The daily bridge requires feature event UTC dates to match observation sessions.
"""
import copy
from collections import Counter

import research_readiness
import security_master
from quant_data_contracts import cli, day, digest, finite, instant, require, sources, text
from point_in_time_data import timestamp


DOCUMENT_KEYS = {'schema_version', 'study_request', 'security_contract',
                 'feature_contract', 'observation_archive'}
CLOCKS = {'signal': 'decision_at', 'valuation': 'valuation_at', 'execution': 'execution_at'}


def _feature_key(row):
    return row['instrument_id'], timestamp(row['event_at'])[:10], row['field'], row['revision_id']


def _source_map(document):
    merged = {}
    groups = [document['security_contract']['sources'], document['feature_contract']['sources'],
              [document['observation_archive']['source']]]
    for group in groups:
        for sid, source in sources(group).items():
            require(sid not in merged or digest(merged[sid]) == digest(source), 'SOURCE_ID_COLLISION')
            merged[sid] = source
    return merged


def _archive_rows(archive):
    require(set(archive) == {'source'}, 'OBSERVATION_ARCHIVE_SOURCE_REQUIRED')
    source = archive['source']
    require(isinstance(source['body'], list) and len(source['body']) <= 2000000,
            'BOUNDED_DAILY_OBSERVATION_ROWS')
    rows = {}
    for i, row in enumerate(source['body']):
        require(isinstance(row, dict), 'OBSERVATION_OBJECT_REQUIRED')
        key = (text(row['security_id'], 'OBSERVATION_SECURITY'), day(row['session']),
               text(row['field'], 'OBSERVATION_FIELD'), text(row['revision_id'], 'OBSERVATION_REVISION'))
        require(key not in rows, 'DUPLICATE_OBSERVATION_REVISION')
        require(row['status'] in research_readiness.STATUSES, 'OBSERVATION_STATUS')
        require('executable' not in row or type(row['executable']) is bool, 'EXECUTABLE_BOOLEAN_REQUIRED')
        if row['status'] != 'unavailable':
            require(finite(row['value']), 'FINITE_OBSERVATION_VALUE')
        rows[key] = (row, '/' + str(i))
    return rows


def _join_features(adapted, raw_rows):
    """Check every revision, including future revisions, before selecting a grid."""
    seen = set()
    for feature in adapted['dataset']['records']:
        key = _feature_key(feature)
        require(key not in seen, 'AMBIGUOUS_INTRADAY_OBSERVATION_JOIN')
        seen.add(key)
        require(key in raw_rows, 'FEATURE_OBSERVATION_JOIN_MISSING')
        row, _ = raw_rows[key]
        require(row['status'] != 'unavailable', 'FEATURE_BOUND_TO_UNAVAILABLE_OBSERVATION')
        require(row['value'] == feature['value'], 'FEATURE_OBSERVATION_VALUE_MISMATCH')
        for name in ('unit', 'currency'):
            require(row[name] == feature[name], 'FEATURE_OBSERVATION_METADATA_MISMATCH:' + name)
        require(row.get('available_at') is not None and
                instant(row['available_at']) == instant(feature['available_at']),
                'FEATURE_OBSERVATION_AVAILABILITY_MISMATCH')
    require(all(key in seen or row['status'] == 'unavailable' for key, (row, _) in raw_rows.items()),
            'OBSERVATION_FEATURE_JOIN_MISSING')


def _securities(master, index_value):
    result = []
    for entity in master['rows']:
        sid = entity['security_id']
        episodes = [r for r in master['selected_episode_revisions'] if r['security_id'] == sid]
        interval = lambda r: {k: r[k] for k in ('start_inclusive', 'end_exclusive')}
        evidence = sorted({entity['source_id']} | {r['source_id'] for r in episodes})
        result.append({'security_id': sid, 'identity_status': 'source_bound', 'evidence_ids': evidence,
                       'listing_intervals': [interval(r) for r in episodes if r['kind'] == 'listing'],
                       'membership_intervals': [interval(r) for r in episodes
                                                if r['kind'] == 'membership' and r['value'] == index_value]})
    return result


def _aggregate(grid, warnings):
    counts = dict(Counter(r['observation_status'] for r in grid))
    unusable = sum(not r['usable_for_declared_purpose'] for r in grid)
    complete = bool(grid) and unusable == 0 and not warnings
    scenario = counts.get('modeled', 0) + counts.get('reference', 0)
    status = ('NO_REQUIREMENTS_IN_DECLARED_SCOPE' if not grid else
              'RESEARCH_GAPS_REMAIN' if not complete else
              'DECLARED_SCENARIO_GRID_COMPLETE' if scenario else 'DECLARED_STRICT_GRID_COMPLETE')
    return {'status': status, 'required_grid_rows': len(grid), 'unusable_requirements': unusable,
            'grid_status_counts': counts, 'declared_policy_grid_complete': complete,
            'strict_observed_grid_complete': complete and not scenario}


def assess(document):
    require(isinstance(document, dict) and set(document) == DOCUMENT_KEYS, 'EXACT_SOURCE_STUDY_DOCUMENT')
    require(type(document['schema_version']) is int and document['schema_version'] == 1, 'SCHEMA_VERSION')
    study = document['study_request']
    require(type(study.get('schema_version')) is int and study['schema_version'] == 1, 'STUDY_SCHEMA_VERSION')
    text(study['strategy_id'], 'STRATEGY_ID')
    text(study['index_value'], 'INDEX_VALUE')
    modes = study['study_modes']
    require(isinstance(modes, list) and modes and len(modes) == len(set(modes)) and
            set(modes) <= {'historical_membership', 'current_roster'}, 'UNIQUE_STUDY_MODES')
    decisions = study['decisions']
    require(isinstance(decisions, list) and 0 < len(decisions) <= 1000 and
            len({d['id'] for d in decisions}) == len(decisions), 'BOUNDED_UNIQUE_DECISIONS')
    requirements = study['requirements']
    require(isinstance(requirements, list) and 0 < len(requirements) <= 100 and
            len({r['id'] for r in requirements}) == len(requirements), 'BOUNDED_UNIQUE_REQUIREMENTS')
    for req in requirements:
        require(req['purpose'] in CLOCKS, 'REQUIREMENT_PURPOSE')
        require(req['scope'] in {'eligible', 'held', 'eligible_or_held'}, 'REQUIREMENT_SECURITY_SCOPE')
    all_sources = _source_map(document)
    raw_rows = _archive_rows(document['observation_archive'])
    observation_source = document['observation_archive']['source']
    roster = study['current_roster_security_ids']
    require(isinstance(roster, list) and len(roster) == len(set(roster)), 'UNIQUE_CURRENT_ROSTER')
    studies, master_receipts, feature_receipts = [], [], []
    total_rows = 0
    for decision in decisions:
        # Identity/membership knowledge is frozen at the decision, even when a
        # later valuation or execution cutoff selects a different price vintage.
        security_doc = copy.deepcopy(document['security_contract'])
        security_doc.update(as_of=decision['decision_at'], on=decision['signal_session'])
        master = security_master.snapshot(security_doc)
        securities = _securities(master, study['index_value'])
        known = {s['security_id'] for s in securities}
        require(set(roster) <= known, 'UNKNOWN_CURRENT_ROSTER_SECURITY')
        require(set(decision['held_security_ids']) <= known, 'UNKNOWN_HELD_SECURITY')
        require(all(key[0] in known for key in raw_rows), 'OBSERVATION_SECURITY_NOT_IN_MASTER')
        master_receipts.append({'decision_id': decision['id'], 'result': master})
        selected_by_purpose = {}
        for purpose in dict.fromkeys(r['purpose'] for r in requirements):
            cutoff = decision[CLOCKS[purpose]]
            feature_doc = copy.deepcopy(document['feature_contract'])
            feature_doc['as_of'] = cutoff
            linked_master = copy.deepcopy(document['security_contract'])
            linked_master.update(as_of=cutoff, on=timestamp(cutoff)[:10])
            feature_doc['security_contract'] = linked_master
            adapted = security_master.adapt_records(feature_doc)
            _join_features(adapted, raw_rows)
            selected, lookup = [], {}
            for feature in adapted['snapshot']['records']:
                key = _feature_key(feature)
                row, pointer = raw_rows[key]
                cell = key[:3]
                require(cell not in lookup, 'AMBIGUOUS_INTRADAY_SELECTED_OBSERVATION')
                # Keep raw timestamps and metadata so assessor pointers match the
                # actual source representation, not a rewritten normalized body.
                selected.append({**copy.deepcopy(row), 'source_id': observation_source['id'],
                                 'source_record_pointer': pointer})
                lookup[cell] = {'selected_value': feature['value'], 'selected_revision_id': feature['revision_id'],
                                'feature_event_at': feature['event_at'], 'source_record_pointer': pointer}
            selected_by_purpose[purpose] = selected, lookup
            feature_receipts.append({'decision_id': decision['id'], 'purpose': purpose,
                                     'cutoff': cutoff, 'result': adapted})
        for mode in modes:
            grid, warnings, calls = [], [], []
            for req in requirements:
                selected, lookup = selected_by_purpose[req['purpose']]
                derived_decision = copy.deepcopy(decision)
                scoped = securities
                if mode == 'current_roster' and req['scope'] != 'held':
                    wanted = set(roster)
                    if req['scope'] == 'eligible_or_held':
                        wanted.update(decision['held_security_ids'])
                    scoped = [s for s in securities if s['security_id'] in wanted]
                    # Nonheld requirements do not consume held IDs. The original
                    # list remains in input hashes and all held-purpose calls.
                    derived_decision['held_security_ids'] = [s for s in decision['held_security_ids'] if s in wanted]
                require(scoped, 'EMPTY_REQUESTED_SECURITY_SET')
                allowed = {s['security_id'] for s in scoped}
                prepared = {'schema_version': 1, 'strategy_id': study['strategy_id'], 'universe_mode': mode,
                            'sessions': copy.deepcopy(study['sessions']), 'sources': list(all_sources.values()),
                            'scope_evidence_ids': sorted(all_sources), 'securities': copy.deepcopy(scoped),
                            'requirements': [copy.deepcopy(req)], 'decisions': [derived_decision],
                            'observations': [r for r in selected if r['security_id'] in allowed],
                            'valuation_policy': copy.deepcopy(study['valuation_policy'])}
                result = research_readiness.assess(prepared)
                for row in result['grid']:
                    data = lookup.get((row['security_id'], row['session'], req['field']),
                                      {'selected_value': None, 'selected_revision_id': None,
                                       'feature_event_at': None, 'source_record_pointer': None})
                    grid.append({**row, **data})
                warnings.extend(result['warnings'])
                calls.append({'requirement_id': req['id'], 'prepared_input_sha256': digest(prepared),
                              'result': result})
                total_rows += len(result['grid'])
                require(total_rows <= 2000000, 'SOURCE_STUDY_GRID_TOO_LARGE_SPLIT_THE_RUN')
            studies.append({'decision_id': decision['id'], 'universe_mode': mode,
                            **_aggregate(grid, warnings), 'grid': grid, 'warnings': warnings,
                            'assessor_calls': calls})
    queries = []
    for query in study.get('symbol_queries', []):
        doc = copy.deepcopy(document['security_contract'])
        doc.update(as_of=query['as_of'], on=query['on'])
        result = security_master.snapshot(doc)
        queries.append({**copy.deepcopy(query), 'security_ids': [r['security_id'] for r in result['rows']
                       if query['symbol'] in r['symbol_values']], 'snapshot_input_sha256': result['input_sha256']})
    combined_grid = [row for s in studies for row in s['grid']]
    combined_warnings = [warning for s in studies for warning in s['warnings']]
    return {'schema_version': 1, 'method': 'source_strategy_readiness_v1', 'strategy_id': study['strategy_id'],
            **_aggregate(combined_grid, combined_warnings),
            'input_sha256': digest(document), 'source_document_hashes': {k: digest(document[k]) for k in DOCUMENT_KEYS - {'schema_version'}},
            'studies': studies, 'symbol_queries': queries, 'security_snapshots': master_receipts,
            'feature_snapshots': feature_receipts, 'required_grid_rows': total_rows,
            'source_authenticity_verified': False, 'historical_universe_completeness_certified': False,
            'limits': ['Declared source coverage only; missing episodes are not certified historical absence.',
                       'Current-roster studies are survivor-conditioned; held valuation uses its separate scope.',
                       'Daily join requires the UTC event date to equal the supplied session; ambiguous intraday joins are rejected.',
                       'Readiness is delegated to the existing assessor; hashes do not establish source truth, fills or trade authority.']}


if __name__ == '__main__':
    cli(assess)
