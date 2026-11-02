"""Fictional boundary fixtures for scoped readiness, PIT identity and price refresh."""
import copy
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research_readiness as rr
import security_master as sm
import price_refresh as pr
from quant_data_contracts import digest, pointer


def source(body, sid='fixture', role='native_json', at='2026-01-06T22:00:00Z'):
    return {'id': sid, 'uri': 'urn:fictional:' + sid, 'source_role': role,
            'retrieved_at': at, 'body': body, 'body_sha256': digest(body)}


def binding(fields, prefix, sid='fixture', **extra):
    return {'source_id': sid, 'bindings': {k: prefix + '/' + k for k in fields}, **extra}


def master_fixture():
    body = {'entity': {'issuer_id': 'fictional:issuer1', 'share_class_id': 'fictional:common1',
                       'instrument_type': 'equity', 'currency': 'USD'}, 'episodes': []}
    for kind, value, start in [('listing', 'XNYS', '2025-01-01'), ('symbol', 'DEMO', '2025-01-01'), ('membership', 'fictional-index', '2026-01-05')]:
        body['episodes'].append({'issuer_id': body['entity']['issuer_id'], 'share_class_id': body['entity']['share_class_id'], 'kind': kind, 'value': value, 'start_inclusive': start,
                                 'end_exclusive': None, 'announced_at': '2026-01-02T12:00:00Z',
                                 'available_at': '2026-01-02T12:01:00Z', 'revision_id': 'original'})
    return {'schema_version': 1, 'as_of': '2026-01-05T21:01:00Z', 'on': '2026-01-05',
            'sources': [source(body)], 'entities': [binding(sm.ENTITY_FIELDS, '/entity', security_id='s1')],
            'episodes': [binding(sm.EPISODE_FIELDS, '/episodes/' + str(i), security_id='s1', episode_id='ep' + str(i)) for i in range(3)]}


def readiness_fixture():
    dates = ['2026-01-02', '2026-01-05', '2026-01-06']
    raw = []
    for session, field, at, value in [(dates[0], 'close', '21:00:00', 100), (dates[1], 'close', '21:00:00', 102), (dates[2], 'open', '14:30:00', 103)]:
        raw.append({'security_id': 's1', 'session': session, 'field': field, 'value': value,
                    'status': 'observed', 'unit': 'USD/share', 'currency': 'USD',
                    'available_at': session + 'T' + at + 'Z', 'executable': True})
    obs = [{**x, 'source_id': 'fixture', 'source_record_pointer': '/' + str(i)} for i, x in enumerate(raw)]
    reqs = [{'id': 'signal', 'field': 'close', 'purpose': 'signal', 'scope': 'eligible', 'lookback_sessions': 2},
            {'id': 'nav', 'field': 'close', 'purpose': 'valuation', 'scope': 'held', 'lookback_sessions': 1},
            {'id': 'fill', 'field': 'open', 'purpose': 'execution', 'scope': 'eligible', 'lookback_sessions': 1}]
    for r in reqs:r.update(unit='USD/share', currency='USD', numeric_domain='positive')
    return {'schema_version': 1, 'strategy_id': 'fictional-month-end', 'universe_mode': 'historical_membership',
            'sessions': dates, 'sources': [source(raw)], 'scope_evidence_ids': ['fixture'],
            'securities': [{'security_id': 's1', 'identity_status': 'source_bound', 'evidence_ids': ['fixture'],
                            'listing_intervals': [{'start_inclusive': '2025-01-01', 'end_exclusive': None}],
                            'membership_intervals': [{'start_inclusive': '2026-01-05', 'end_exclusive': None}]}],
            'requirements': reqs, 'observations': obs,
            'valuation_policy': {'allow_reference': False, 'allow_modeled': False},
            'decisions': [{'id': 'd1', 'decision_at': '2026-01-05T21:01:00Z', 'valuation_at': '2026-01-05T21:01:00Z',
                           'execution_at': '2026-01-06T14:30:00Z', 'signal_session': '2026-01-05',
                           'execution_session': '2026-01-06', 'held_security_ids': ['s1']}]}


def change_observation(d, i, **changes):
    d['observations'][i].update(changes);d['sources'][0]['body'][i].update(changes)
    d['sources'][0]['body_sha256'] = digest(d['sources'][0]['body'])


def feature_fixture():
    raw = [{'instrument_id': 's1', 'asset_class': 'equity', 'currency': 'USD', 'field': 'eps',
            'event_at': '2025-12-31T00:00:00Z', 'available_at': '2026-01-05T20:00:00Z',
            'value': 2.1, 'unit': 'USD/share', 'revision_id': 'original'},
           {'instrument_id': 's1', 'asset_class': 'equity', 'currency': 'USD', 'field': 'eps',
            'event_at': '2025-12-31T00:00:00Z', 'available_at': '2026-02-05T20:00:00Z',
            'value': 1.9, 'unit': 'USD/share', 'revision_id': 'restated'}]
    return {'schema_version': 1, 'operation': 'features', 'dataset_id': 'fictional-eps',
            'as_of': '2026-01-06T00:00:00Z', 'sources': [source(raw)],
            'records': [binding(sm.FEATURE_FIELDS, '/' + str(i)) for i in range(2)]}


def refresh_fixture():
    c = {'provider': 'fictional-provider', 'security_id': 's1', 'share_class_id': 'common1',
         'currency': 'USD', 'adjustment': 'raw', 'schema_version': 1, 'parser_version': '1',
         'fields': ['close', 'volume'], 'units': {'close': 'USD/share', 'volume': 'shares'}}
    rows = [{'session': d, 'values': {'close': p, 'volume': 100}, 'status': 'observed'}
            for d, p in [('2026-01-02', 100), ('2026-01-05', 102), ('2026-01-06', 103)]]
    old = {'contract': c, 'rows': copy.deepcopy(rows[:2]), 'rows_sha256': digest(rows[:2]), 'revision': 'r1'}
    new = {'contract': copy.deepcopy(c), 'rows': copy.deepcopy(rows[1:]), 'rows_sha256': digest(rows[1:]), 'revision': 'r2'}
    proof = {'provider': c['provider'], 'security_id': 's1', 'contract_sha256': digest(c),
             'prefix_start': '2026-01-02', 'prefix_end': '2026-01-05', 'prefix_rows_sha256': old['rows_sha256'],
             'hash_algorithm': 'canonical-json-sha256-v1', 'revision': 'r2', 'checked_at': '2026-01-06T21:30:00Z'}
    return {'schema_version': 1, 'mode': 'incremental', 'partial_fetch_opt_in': True, 'current_scope': 'tail',
            'decision_at': '2026-01-06T21:00:00Z', 'acquired_at': '2026-01-06T22:00:00Z',
            'expected_sessions': [r['session'] for r in rows], 'previous': old, 'current': new,
            'sources': [source(proof)], 'prefix_proof': binding(pr.PROOF_FIELDS, ''),
            'derived_artifacts': [{'id': 'old-signal', 'source_start': '2026-01-02', 'source_end': '2026-01-05'},
                                  {'id': 'new-signal', 'source_start': '2026-01-05', 'source_end': '2026-01-06'}]}


class ReadinessTests(unittest.TestCase):
    def test_reserved_normalized_intervals_cannot_override(self):
        for key in ['listing', 'membership']:
            d = readiness_fixture(); d['securities'][0][key] = []
            with self.assertRaisesRegex(ValueError, 'RESERVED_SECURITY_KEYS'): rr.assess(d)
    def test_real_grid_and_immutable_input(self):
        d = readiness_fixture(); before = digest(d); r = rr.assess(d)
        self.assertEqual(len(r['grid']), 4); self.assertTrue(r['strict_observed_grid_complete'])
        self.assertFalse(r['historical_universe_completeness_certified']); self.assertEqual(before, digest(d))

    def test_future_signal_observation(self):
        d = readiness_fixture(); change_observation(d, 1, available_at='2026-01-05T21:02:00Z')
        r = rr.assess(d); self.assertFalse(r['declared_policy_grid_complete'])
        self.assertTrue(any('NOT_AVAILABLE_FOR_PURPOSE' in x['reasons'] for x in r['grid']))

    def test_subsecond_cutoff(self):
        d = readiness_fixture(); change_observation(d, 1, available_at='2026-01-05T21:01:00.000001Z')
        self.assertFalse(rr.assess(d)['declared_policy_grid_complete'])

    def test_model_never_signal_or_fill(self):
        d = readiness_fixture(); d['valuation_policy']['allow_modeled'] = True
        change_observation(d, 1, status='modeled'); change_observation(d, 2, status='modeled')
        r = rr.assess(d)
        self.assertFalse(r['declared_policy_grid_complete'])
        self.assertTrue(next(x for x in r['grid'] if x['purpose'] == 'valuation')['usable_for_declared_purpose'])
        self.assertFalse(next(x for x in r['grid'] if x['purpose'] == 'execution')['usable_for_declared_purpose'])

    def test_explicit_model_valuation_only_is_not_strict(self):
        d = readiness_fixture(); d['requirements'] = [d['requirements'][1]]
        d['valuation_policy']['allow_modeled'] = True; change_observation(d, 1, status='modeled')
        r = rr.assess(d); self.assertEqual(r['status'], 'DECLARED_SCENARIO_GRID_COMPLETE')
        self.assertFalse(r['strict_observed_grid_complete'])

    def test_reference_requires_opt_in(self):
        d = readiness_fixture(); d['requirements'] = [d['requirements'][1]];change_observation(d, 1, status='reference')
        self.assertFalse(rr.assess(d)['declared_policy_grid_complete'])
        d['valuation_policy']['allow_reference'] = True
        self.assertEqual(rr.assess(d)['status'], 'DECLARED_SCENARIO_GRID_COMPLETE')

    def test_missing_open_not_replaced_by_close(self):
        d = readiness_fixture();d['observations'].pop()
        r=rr.assess(d);self.assertEqual(r['grid_status_counts']['unavailable'],1)

    def test_unknown_bounds_are_not_empty_complete(self):
        d=readiness_fixture();d['securities'][0]['membership_intervals']=None
        self.assertFalse(rr.assess(d)['declared_policy_grid_complete'])

    def test_held_position_remains_after_membership_exit(self):
        d=readiness_fixture();d['securities'][0]['membership_intervals']=[{'start_inclusive':'2025-01-01','end_exclusive':'2026-01-05'}]
        r=rr.assess(d);self.assertEqual(len(r['grid']),1);self.assertEqual(r['grid'][0]['purpose'],'valuation')

    def test_empty_scope_not_pass(self):
        d=readiness_fixture();d['decisions'][0]['held_security_ids']=[];d['securities'][0]['membership_intervals']=[]
        r=rr.assess(d);self.assertEqual(r['status'],'NO_REQUIREMENTS_IN_DECLARED_SCOPE');self.assertFalse(r['strict_observed_grid_complete'])

    def test_preipo_lookback_keeps_denominator(self):
        d=readiness_fixture();d['securities'][0]['listing_intervals'][0]['start_inclusive']='2026-01-05'
        r=rr.assess(d);self.assertEqual(len(r['grid']),4);self.assertEqual(r['grid_status_counts']['outside_lifetime'],1)

    def test_short_calendar_flags_requirement(self):
        d=readiness_fixture();d['requirements'][0]['lookback_sessions']=3
        self.assertTrue(rr.assess(d)['warnings'])

    def test_identity_unknown(self):
        d=readiness_fixture();d['securities'][0]['identity_status']='unknown'
        self.assertFalse(rr.assess(d)['declared_policy_grid_complete'])

    def test_source_metadata_and_hash_rejected(self):
        d=readiness_fixture();d['observations'][0]['session']='2026-01-01'
        with self.assertRaisesRegex(ValueError,'SOURCE_METADATA'):rr.assess(d)
        d=readiness_fixture();d['sources'][0]['body'][0]['value']=99
        with self.assertRaisesRegex(ValueError,'HASH'):rr.assess(d)

    def test_units_and_zero_not_green(self):
        d=readiness_fixture();change_observation(d,1,currency='EUR',value=0)
        r=rr.assess(d);self.assertTrue(any('UNIT_OR_CURRENCY_MISMATCH' in x['reasons'] and 'NONPOSITIVE_VALUE' in x['reasons'] for x in r['grid']))

    def test_duplicate_observations_need_vintage_selection(self):
        d=readiness_fixture();d['observations'].append(copy.deepcopy(d['observations'][0]))
        with self.assertRaisesRegex(ValueError,'CONFLICTING'):rr.assess(d)

    def test_execution_after_decision(self):
        d=readiness_fixture();d['decisions'][0]['execution_at']=d['decisions'][0]['decision_at']
        with self.assertRaisesRegex(ValueError,'PRECEDE'):rr.assess(d)


class SecurityTests(unittest.TestCase):
    def test_episode_subject_cannot_be_reassigned(self):
        d = master_fixture(); body = d['sources'][0]['body']
        body['other'] = dict(body['entity'], issuer_id='fictional:other', share_class_id='fictional:other-common')
        d['sources'][0]['body_sha256'] = digest(body)
        d['entities'].append(binding(sm.ENTITY_FIELDS, '/other', security_id='s2'))
        d['episodes'][0]['security_id'] = 's2'
        with self.assertRaisesRegex(ValueError, 'EPISODE_SUBJECT_IDENTITY_MISMATCH'): sm.snapshot(d)
    def test_membership_not_before_effective_date(self):
        d=master_fixture();d['on']='2026-01-02';r=sm.snapshot(d)
        self.assertEqual(r['rows'][0]['membership_values'],[])
        d['on']='2026-01-05';self.assertEqual(sm.snapshot(d)['rows'][0]['membership_values'],['fictional-index'])

    def test_later_revision_not_retroactive(self):
        d=master_fixture();d['on']='2026-01-06';d['as_of']='2026-01-06T00:00:00Z';body=d['sources'][0]['body'];rev={**body['episodes'][2],'end_exclusive':'2026-01-06','revision_id':'correction','available_at':'2026-01-06T12:00:00Z'}
        body['episodes'].append(rev);d['sources'][0]['body_sha256']=digest(body)
        d['episodes'].append(binding(sm.EPISODE_FIELDS,'/episodes/3',security_id='s1',episode_id='ep2'))
        self.assertTrue(sm.snapshot(d)['rows'][0]['membership_values'])
        d['as_of']='2026-01-06T13:00:00Z';self.assertEqual(sm.snapshot(d)['rows'][0]['membership_values'],[])

    def test_subsecond_revision_not_leaked(self):
        d=master_fixture();body=d['sources'][0]['body'];body['episodes'][2]['available_at']='2026-01-05T21:01:00.000001Z';d['sources'][0]['body_sha256']=digest(body)
        self.assertEqual(sm.snapshot(d)['rows'][0]['membership_values'],[])

    def test_ambiguous_revision_is_rejected(self):
        d=master_fixture();body=d['sources'][0]['body'];body['episodes'].append({**body['episodes'][2],'revision_id':'another'});d['sources'][0]['body_sha256']=digest(body)
        d['episodes'].append(binding(sm.EPISODE_FIELDS,'/episodes/3',security_id='s1',episode_id='ep2'))
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):sm.snapshot(d)

    def test_ticker_reuse_cannot_change_episode_security(self):
        d=master_fixture();d['episodes'].append({**d['episodes'][0],'security_id':'missing'})
        with self.assertRaisesRegex(ValueError,'UNKNOWN_SECURITY'):sm.snapshot(d)

    def test_feature_restatement_and_original_pointer_retained(self):
        d=feature_fixture();r=sm.adapt_records(d)
        self.assertEqual(r['snapshot']['records'][0]['value'],2.1);self.assertEqual(len(r['provenance']),2)
        d['as_of']='2026-03-01T00:00:00Z';self.assertEqual(sm.adapt_records(d)['snapshot']['records'][0]['value'],1.9)

    def test_no_period_end_as_publication(self):
        d=feature_fixture();del d['records'][0]['bindings']['available_at']
        with self.assertRaisesRegex(ValueError,'EXACT_SOURCE'):sm.adapt_records(d)

    def test_wrong_source_unit_revision_is_rejected(self):
        d=feature_fixture();d['sources'][0]['body'][1]['currency']='EUR';d['sources'][0]['body_sha256']=digest(d['sources'][0]['body'])
        with self.assertRaisesRegex(ValueError,'changes'):sm.adapt_records(d)

    def test_pointer_missing_and_source_hash(self):
        d=master_fixture();d['entities'][0]['bindings']['share_class_id']='/absent'
        with self.assertRaisesRegex(ValueError,'POINTER'):sm.snapshot(d)
        d=master_fixture();d['sources'][0]['body_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'HASH'):sm.snapshot(d)

    def test_feature_identity_mapping_optional_but_explicit(self):
        d=feature_fixture();self.assertEqual(sm.adapt_records(d)['identity_link_status'],'NOT_CHECKED')
        d['security_contract']=master_fixture();d['security_contract']['as_of']=d['as_of']
        self.assertEqual(sm.adapt_records(d)['identity_link_status'],'SOURCE_BOUND_IDENTIFIERS_MATCHED')
        d['sources'][0]['body'][0]['instrument_id']='unknown';d['sources'][0]['body_sha256']=digest(d['sources'][0]['body'])
        with self.assertRaisesRegex(ValueError,'NOT_IN_MASTER'):sm.adapt_records(d)

    def test_invalid_pointer_escape(self):
        with self.assertRaisesRegex(ValueError,'INVALID_JSON_POINTER_ESCAPE'):pointer({'a~2b':1},'/a~2b')


class RefreshTests(unittest.TestCase):
    def test_verified_supplied_prefix_reconciles_and_preserves_inputs(self):
        d=refresh_fixture();h=digest(d);r=pr.reconcile(d)
        self.assertEqual(r['status'],'RECONCILED_INCREMENTAL');self.assertEqual(len(r['rows']),3)
        self.assertEqual(r['invalidated_artifact_ids'],['new-signal']);self.assertEqual(digest(d),h)

    def test_opt_in_required(self):
        d=refresh_fixture();d['partial_fetch_opt_in']=False
        self.assertEqual(pr.reconcile(d)['status'],'FULL_FETCH_REQUIRED')

    def test_full_mode_never_silently_uses_tail(self):
        d=refresh_fixture();d['mode']='full'
        self.assertEqual(pr.reconcile(d)['reason'],'PARTIAL_FETCH_NOT_EXPLICITLY_SELECTED')

    def test_no_proof_local_hash_is_insufficient(self):
        d=refresh_fixture();del d['prefix_proof']
        self.assertEqual(pr.reconcile(d)['reason'],'CURRENT_PROVIDER_PREFIX_PROOF_MISSING')

    def test_stale_native_proof(self):
        d=refresh_fixture();d['sources'][0]['body']['checked_at']='2026-01-05T22:00:00Z';d['sources'][0]['body_sha256']=digest(d['sources'][0]['body'])
        self.assertEqual(pr.reconcile(d)['status'],'FULL_FETCH_REQUIRED')

    def test_reviewed_extraction_cannot_impersonate_native_revision_index(self):
        d=refresh_fixture();d['sources'][0]['source_role']='reviewed_extraction'
        self.assertEqual(pr.reconcile(d)['reason'],'PREFIX_PROOF_NOT_NATIVE_PROVIDER_REPRESENTATION')

    def test_overlap_correction_requires_full(self):
        d=refresh_fixture();d['current']['rows'][0]['values']['close']=51;d['current']['rows_sha256']=digest(d['current']['rows'])
        self.assertEqual(pr.reconcile(d)['reason'],'OVERLAP_REVISED_FETCH_FULL_HISTORY')

    def test_adjustment_contract_change_requires_full(self):
        d=refresh_fixture();d['current']['contract']['adjustment']='split_adjusted'
        self.assertEqual(pr.reconcile(d)['reason'],'PRICE_REPRESENTATION_CONTRACT_CHANGED')

    def test_provider_prefix_correction_requires_full(self):
        d=refresh_fixture();d['sources'][0]['body']['prefix_rows_sha256']='f'*64;d['sources'][0]['body_sha256']=digest(d['sources'][0]['body'])
        self.assertEqual(pr.reconcile(d)['status'],'FULL_FETCH_REQUIRED')

    def test_full_correction_invalidates_old_and_new_dependencies(self):
        d=refresh_fixture();rows=copy.deepcopy(d['previous']['rows'])+[copy.deepcopy(d['current']['rows'][-1])]
        rows[0]['values']['close']=50;d['current']['rows']=rows;d['current']['rows_sha256']=digest(rows);d['current_scope']='full'
        r=pr.reconcile(d);self.assertEqual(r['status'],'RECONCILED_FULL');self.assertEqual(r['earliest_changed_or_added_session'],'2026-01-02')
        self.assertEqual(r['invalidated_artifact_ids'],['old-signal','new-signal'])

    def test_missing_tail_session(self):
        d=refresh_fixture();d['expected_sessions'].append('2026-01-07')
        self.assertEqual(pr.reconcile(d)['reason'],'MERGED_SESSION_GRID_INCOMPLETE')

    def test_incomplete_old_prefix(self):
        d=refresh_fixture();d['expected_sessions'].insert(0,'2026-01-01')
        self.assertEqual(pr.reconcile(d)['reason'],'PREVIOUS_PREFIX_NOT_COMPLETE_FOR_REQUEST')

    def test_corrupt_rows_hash_rejected(self):
        d=refresh_fixture();d['previous']['rows'][0]['values']['close']=50
        with self.assertRaisesRegex(ValueError,'HASH'):pr.reconcile(d)

    def test_invalid_numeric_and_missing_field(self):
        d=refresh_fixture();d['current']['rows'][0]['values']['close']=True;d['current']['rows_sha256']=digest(d['current']['rows'])
        with self.assertRaisesRegex(ValueError,'FINITE'):pr.reconcile(d)
        d=refresh_fixture();del d['current']['rows'][0]['values']['volume'];d['current']['rows_sha256']=digest(d['current']['rows'])
        with self.assertRaisesRegex(ValueError,'FIELD_CONTRACT'):pr.reconcile(d)

    def test_null_volume_not_fabricated(self):
        d=refresh_fixture();d['current']['rows'][-1]['values']['volume']=None;d['current']['rows_sha256']=digest(d['current']['rows'])
        self.assertIsNone(pr.reconcile(d)['rows'][-1]['values']['volume'])

    def test_inexact_full_capture_not_success(self):
        d=refresh_fixture();d['current_scope']='full'
        self.assertEqual(pr.reconcile(d)['reason'],'FULL_CAPTURE_HAS_SESSION_GAPS')

    def test_successor_cannot_replace_predecessor_even_full(self):
        d=refresh_fixture();d['current_scope']='full';d['current']['contract']['security_id']='acquirer'
        with self.assertRaisesRegex(ValueError,'SUCCESSOR_SPLICE'):pr.reconcile(d)

    def test_future_price_session_rejected(self):
        d=refresh_fixture();d['current']['rows'][-1]['session']='2026-01-07';d['current']['rows_sha256']=digest(d['current']['rows'])
        with self.assertRaisesRegex(ValueError,'FUTURE_PRICE'):pr.reconcile(d)

if __name__=='__main__':unittest.main()
