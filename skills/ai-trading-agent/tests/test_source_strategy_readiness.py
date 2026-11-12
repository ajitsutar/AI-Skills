"""Portable daily-source composition boundaries, using new fictional records."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import security_master
import source_strategy_readiness as adapter
from quant_data_contracts import digest


def source(sid, body):
    return {'id': sid, 'uri': 'urn:fictional:' + sid, 'source_role': 'native_json',
            'retrieved_at': '2028-02-08T12:00:00Z', 'body': body, 'body_sha256': digest(body)}


def bind(fields, prefix, sid, **extra):
    return {'source_id': sid, 'bindings': {k: prefix + '/' + k for k in fields}, **extra}


def fixture():
    identities, episodes, entity_bindings, episode_bindings = [], [], [], []
    for sid in ['OLD', 'NEW', 'CHILD']:
        entity = {'issuer_id': 'fictional:' + sid, 'share_class_id': 'common:' + sid,
                  'instrument_type': 'equity', 'currency': 'USD'}
        identities.append(entity)
        entity_bindings.append(bind(security_master.ENTITY_FIELDS, '/entities/' + str(len(identities)-1),
                                    'identity', security_id=sid))
        specs = [('listing', 'XTEST', '2028-02-05' if sid == 'NEW' else '2027-01-01', None),
                 ('symbol', sid, '2028-02-05' if sid == 'NEW' else '2027-01-01', None)]
        if sid != 'CHILD':
            specs.append(('membership', 'sample-index', '2027-01-01' if sid == 'OLD' else '2028-02-05',
                          '2028-02-05' if sid == 'OLD' else None))
        for kind, value, start, end in specs:
            row = {**{k: entity[k] for k in ['issuer_id', 'share_class_id']}, 'kind': kind,
                   'value': value, 'start_inclusive': start, 'end_exclusive': end,
                   'announced_at': '2028-02-01T10:00:00Z', 'available_at': '2028-02-01T10:01:00Z',
                   'revision_id': 'initial'}
            episodes.append(row)
            episode_bindings.append(bind(security_master.EPISODE_FIELDS, '/episodes/' + str(len(episodes)-1),
                                         'identity', security_id=sid, episode_id=sid + '-' + kind))
    observations, features = [], []
    dates = ['2028-02-03', '2028-02-04', '2028-02-05', '2028-02-06', '2028-02-07']
    for n, date in enumerate(dates):
        for si, sid in enumerate(['OLD', 'NEW', 'CHILD']):
            if sid == 'NEW' and date < '2028-02-05':
                continue
            for field in ['close', 'open']:
                if field == 'open' and (date < '2028-02-06' or (sid == 'NEW' and date == '2028-02-06')):
                    continue
                at = date + ('T20:00:00Z' if field == 'close' else 'T09:00:00Z')
                value = 50 + 10 * si + n
                observations.append({'security_id': sid, 'session': date, 'field': field, 'value': value,
                                     'status': 'modeled' if sid == 'CHILD' else 'observed',
                                     'executable': sid != 'CHILD', 'available_at': at, 'unit': 'USD/share',
                                     'currency': 'USD', 'revision_id': 'initial'})
                features.append({'instrument_id': sid, 'asset_class': 'equity', 'currency': 'USD',
                                 'field': field, 'event_at': at, 'available_at': at, 'value': value,
                                 'unit': 'USD/share', 'revision_id': 'initial'})
    reqs = [{'id': 'history', 'field': 'close', 'purpose': 'signal', 'scope': 'eligible', 'lookback_sessions': 3},
            {'id': 'marks', 'field': 'close', 'purpose': 'valuation', 'scope': 'held', 'lookback_sessions': 1},
            {'id': 'next-open', 'field': 'open', 'purpose': 'execution', 'scope': 'eligible', 'lookback_sessions': 1}]
    for req in reqs:
        req.update(unit='USD/share', currency='USD', numeric_domain='positive')
    decisions = [{'id': name, 'decision_at': anchor + 'T20:01:00Z', 'valuation_at': anchor + 'T20:01:00Z',
                  'execution_at': execution + 'T09:00:00Z', 'signal_session': anchor,
                  'execution_session': execution, 'held_security_ids': ['OLD', 'CHILD']}
                 for name, anchor, execution in [('early', dates[2], dates[3]), ('later', dates[3], dates[4])]]
    return {'schema_version': 1,
            'study_request': {'schema_version': 1, 'strategy_id': 'fictional-daily-study', 'sessions': dates,
                              'requirements': reqs, 'decisions': decisions,
                              'study_modes': ['historical_membership', 'current_roster'],
                              'current_roster_security_ids': ['OLD', 'NEW', 'CHILD'],
                              'index_value': 'sample-index',
                              'valuation_policy': {'allow_reference': False, 'allow_modeled': True}},
            'security_contract': {'schema_version': 1, 'sources': [source('identity', {'entities': identities, 'episodes': episodes})],
                                  'entities': entity_bindings, 'episodes': episode_bindings},
            'feature_contract': {'schema_version': 1, 'operation': 'features', 'dataset_id': 'fictional-daily',
                                 'sources': [source('features', features)],
                                 'records': [bind(security_master.FEATURE_FIELDS, '/' + str(i), 'features')
                                             for i in range(len(features))]},
            'observation_archive': {'source': source('prices', observations)}}


def reseal(doc):
    for group in [doc['security_contract']['sources'], doc['feature_contract']['sources'],
                  [doc['observation_archive']['source']]]:
        for s in group:
            s['body_sha256'] = digest(s['body'])


def study(result, decision='early', mode='historical_membership'):
    return next(s for s in result['studies'] if s['decision_id'] == decision and s['universe_mode'] == mode)


class SourceReadinessTests(unittest.TestCase):
    def test_top_level_status_conservatively_combines_studies(self):
        d = fixture()
        # Historical early history has gaps even though later held marks alone
        # can form a complete scenario. A report must retain the worst outcome.
        out = adapter.assess(d)
        self.assertEqual(out['status'], 'RESEARCH_GAPS_REMAIN')
        self.assertEqual(out['required_grid_rows'], sum(s['required_grid_rows'] for s in out['studies']))
        d['study_request']['requirements'] = [d['study_request']['requirements'][1]]
        out = adapter.assess(d)
        self.assertTrue(all(s['status'] == 'DECLARED_SCENARIO_GRID_COMPLETE' for s in out['studies']))
        self.assertEqual(out['status'], 'DECLARED_SCENARIO_GRID_COMPLETE')
        self.assertTrue(out['declared_policy_grid_complete'])
        self.assertFalse(out['strict_observed_grid_complete'])
        d['study_request']['decisions'][0]['held_security_ids'] = ['OLD']
        out = adapter.assess(d)
        self.assertEqual({s['status'] for s in out['studies']},
                         {'DECLARED_STRICT_GRID_COMPLETE', 'DECLARED_SCENARIO_GRID_COMPLETE'})
        self.assertEqual(out['status'], 'DECLARED_SCENARIO_GRID_COMPLETE')
        d['study_request']['decisions'][1]['held_security_ids'] = ['OLD']
        out = adapter.assess(d)
        self.assertEqual(out['status'], 'DECLARED_STRICT_GRID_COMPLETE')
        self.assertTrue(out['strict_observed_grid_complete'])

    def test_anchor_scope_and_prelisting_history_not_session_membership(self):
        d = fixture(); before = digest(d); out = adapter.assess(d); s = study(out)
        self.assertEqual(digest(d), before)
        self.assertEqual(s['required_grid_rows'], 6)
        signal = [r for r in s['grid'] if r['purpose'] == 'signal']
        self.assertEqual({r['security_id'] for r in signal}, {'NEW'})
        self.assertEqual(len(signal), 3)
        self.assertEqual(sum(r['observation_status'] == 'outside_lifetime' for r in signal), 2)
        self.assertEqual(s['unusable_requirements'], 3)
        self.assertEqual(s['status'], 'RESEARCH_GAPS_REMAIN')
        self.assertFalse(out['historical_universe_completeness_certified'])

    def test_held_scope_after_exit_and_model_only_valuation(self):
        out = adapter.assess(fixture()); s = study(out)
        self.assertEqual({r['security_id'] for r in s['grid'] if r['purpose'] == 'valuation'}, {'OLD', 'CHILD'})
        current = study(out, mode='current_roster')
        self.assertEqual(current['required_grid_rows'], 14)
        child = [r for r in current['grid'] if r['security_id'] == 'CHILD']
        self.assertTrue(all(r['usable_for_declared_purpose'] == (r['purpose'] == 'valuation') for r in child))
        self.assertEqual(current['unusable_requirements'], 7)

    def test_purpose_cutoffs_select_different_vintages(self):
        d = fixture(); d['study_request']['decisions'][0]['valuation_at'] = '2028-02-05T22:00:00Z'
        d['study_request']['decisions'][0]['held_security_ids'].append('NEW')
        raw = d['observation_archive']['source']['body']; features = d['feature_contract']['sources'][0]['body']
        old = next(r for r in raw if r['security_id'] == 'NEW' and r['session'] == '2028-02-05' and r['field'] == 'close')
        new = {**old, 'revision_id': 'corrected', 'available_at': '2028-02-05T21:00:00Z', 'value': 77}
        raw.append(new)
        feature = next(r for r in features if r['instrument_id'] == 'NEW' and r['event_at'] == '2028-02-05T20:00:00Z')
        features.append({**feature, 'revision_id': 'corrected', 'available_at': new['available_at'], 'value': 77})
        d['feature_contract']['records'].append(bind(security_master.FEATURE_FIELDS, '/' + str(len(features)-1), 'features'))
        reseal(d); out = adapter.assess(d)
        rows = [r for r in study(out)['grid'] if r['security_id'] == 'NEW' and r['session'] == '2028-02-05']
        self.assertEqual({r['purpose']: r['selected_value'] for r in rows}, {'signal': old['value'], 'valuation': 77})
        self.assertEqual({r['purpose']: r['selected_revision_id'] for r in rows}, {'signal': 'initial', 'valuation': 'corrected'})

    def test_later_membership_revision_does_not_rewrite_earlier_decision(self):
        d = fixture(); contract = d['security_contract']; body = contract['sources'][0]['body']['episodes']
        old = next(r for r in body if r['issuer_id'] == 'fictional:NEW' and r['kind'] == 'membership')
        body.append({**old, 'end_exclusive': '2028-02-06', 'announced_at': '2028-02-06T19:00:00Z',
                     'available_at': '2028-02-06T19:00:00Z', 'revision_id': 'updated'})
        contract['episodes'].append(bind(security_master.EPISODE_FIELDS, '/episodes/' + str(len(body)-1),
                                          'identity', security_id='NEW', episode_id='NEW-membership'))
        reseal(d); out = adapter.assess(d)
        self.assertEqual(len([r for r in study(out)['grid'] if r['purpose'] == 'signal']), 3)
        later = study(out, 'later')
        self.assertEqual(later['required_grid_rows'], 2)
        self.assertEqual(later['status'], 'DECLARED_SCENARIO_GRID_COMPLETE')
        self.assertFalse(later['strict_observed_grid_complete'])

    def test_current_roster_subset_does_not_drop_nonroster_held(self):
        d = fixture(); d['study_request']['current_roster_security_ids'] = ['NEW']
        s = study(adapter.assess(d), mode='current_roster')
        self.assertEqual({r['security_id'] for r in s['grid'] if r['purpose'] == 'signal'}, {'NEW'})
        self.assertEqual({r['security_id'] for r in s['grid'] if r['purpose'] == 'valuation'}, {'OLD', 'CHILD'})

    def test_no_missing_open_substitution(self):
        s = study(adapter.assess(fixture()))
        fill = next(r for r in s['grid'] if r['purpose'] == 'execution')
        self.assertEqual(fill['observation_status'], 'unavailable')
        self.assertIn('OBSERVATION_UNAVAILABLE', fill['reasons'])
        self.assertFalse(fill['usable_for_declared_purpose'])

    def test_source_integrity_and_join_mismatch_rejected(self):
        for field, value, error in [('value', 900, 'VALUE_MISMATCH'), ('currency', 'EUR', 'METADATA_MISMATCH'),
                                    ('available_at', '2028-02-03T20:00:01Z', 'AVAILABILITY_MISMATCH')]:
            with self.subTest(field=field):
                d = fixture(); d['observation_archive']['source']['body'][0][field] = value; reseal(d)
                with self.assertRaisesRegex(ValueError, error): adapter.assess(d)
        d = fixture(); d['observation_archive']['source']['body'][0]['value'] = 900
        with self.assertRaisesRegex(ValueError, 'SOURCE_BODY_HASH_MISMATCH'): adapter.assess(d)

    def test_duplicates_and_omissions_rejected(self):
        d = fixture(); raw = d['observation_archive']['source']['body']; raw.append(copy.deepcopy(raw[0])); reseal(d)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_OBSERVATION_REVISION'): adapter.assess(d)
        d = fixture(); d['observation_archive']['source']['body'].pop(); reseal(d)
        with self.assertRaisesRegex(ValueError, 'FEATURE_OBSERVATION_JOIN_MISSING'): adapter.assess(d)
        d = fixture(); d['feature_contract']['records'].pop()
        with self.assertRaisesRegex(ValueError, 'OBSERVATION_FEATURE_JOIN_MISSING'): adapter.assess(d)

    def test_source_ids_must_not_collide(self):
        d = fixture(); d['observation_archive']['source']['id'] = 'identity'
        with self.assertRaisesRegex(ValueError, 'SOURCE_ID_COLLISION'): adapter.assess(d)

    def test_future_purpose_clock_does_not_change_membership_scope(self):
        d = fixture(); contract = d['security_contract']; body = contract['sources'][0]['body']['episodes']
        old = next(r for r in body if r['issuer_id'] == 'fictional:NEW' and r['kind'] == 'membership')
        body.append({**old, 'end_exclusive': '2028-02-06', 'announced_at': '2028-02-06T08:00:00Z',
                     'available_at': '2028-02-06T08:00:00Z', 'revision_id': 'later-known'})
        contract['episodes'].append(bind(security_master.EPISODE_FIELDS, '/episodes/' + str(len(body)-1),
                                          'identity', security_id='NEW', episode_id='NEW-membership'))
        reseal(d); s = study(adapter.assess(d))
        self.assertEqual([r['security_id'] for r in s['grid'] if r['purpose'] == 'execution'], ['NEW'])


if __name__ == '__main__':
    unittest.main()
