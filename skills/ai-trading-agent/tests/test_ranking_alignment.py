"""Generic adapter contracts and parity with existing scorers; no investment claims."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests'))
import ranking_alignment as ranking
import public_research
import vqm_research
from test_public_research import fixture as public_snapshot
from test_shared_strategy import snapshot as strict_snapshot
from test_financial_normalization import normalized_snapshot


def source(value, indent=None):
    text = json.dumps(value, indent=indent)
    return {'text': text, 'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()}


def replay_document(module, snapshot, **extra):
    profile = module.profile()
    return {'schema_version': 1, 'profile': source(profile), 'snapshot': snapshot,
            'requested': {'profile_id': profile['profile_id'], 'profile_sha256': ranking.digest(profile)}, **extra}


def side(value, **dimensions):
    data = {'ranking': value, **dimensions}
    bindings = {name: {'source_id': 'retained', 'pointer': '/' + name} for name in dimensions}
    bindings.update({name: {'source_id': 'retained', 'pointer': '/ranking/' + name}
                     for name in ('candidates', 'scores', 'classifier_available')})
    return {'sources': {'retained': source(data)}, 'bindings': bindings}


def comparison(left, right):
    return {'schema_version': 1, 'identity_field': 'symbol', 'left': left, 'right': right}


class RankingRouteTests(unittest.TestCase):
    def test_public_replay_is_exact_existing_scorer_and_does_not_mutate(self):
        document = replay_document(public_research, public_snapshot(), selection_count=4)
        original = copy.deepcopy(document)
        actual = ranking.replay_ranking(document)
        self.assertEqual(actual['requested_result'], public_research.calculate(document['snapshot'], 4))
        self.assertEqual(actual['status'], 'REQUESTED_REPLAY_COMPUTED')
        self.assertIsNone(actual['diagnostic_result'])
        self.assertEqual(document, original)
        self.assertEqual(actual['classifier']['per_name_buy_eligibility'], 'NOT_ASSESSED')

    def test_both_strict_schemas_replay_exact_existing_scorer(self):
        for snapshot in (strict_snapshot(), normalized_snapshot()):
            with self.subTest(schema=snapshot['schema_version']):
                document = replay_document(vqm_research, snapshot, selection_count=3)
                actual = ranking.replay_ranking(document)
                expected = vqm_research.calculate(snapshot)
                self.assertEqual(actual['requested_result'], expected)
                self.assertEqual(actual['selection']['candidates'], expected['discovery_order'][:3])
                self.assertEqual(actual['available_diagnostic_route']['profile_id'], vqm_research.profile()['profile_id'])

    def test_strict_data_is_not_misrouted_to_public(self):
        document = replay_document(vqm_research, strict_snapshot())
        public = public_research.profile()
        document['requested'] = {'profile_id': public['profile_id'], 'profile_sha256': ranking.digest(public)}
        with patch.object(public_research, 'calculate', side_effect=AssertionError('Wrong scorer')):
            withheld = ranking.replay_ranking(document)
            self.assertEqual(withheld['status'], 'NOT_REPLAYED')
            self.assertIsNone(withheld['requested_route'])
            self.assertEqual(withheld['requested_method_relation'], 'DIFFERENT')
            document['allow_diagnostic_replay'] = True
            replay = ranking.replay_ranking(document)
        self.assertIsNone(replay['requested_result'])
        self.assertEqual(replay['diagnostic_result'], vqm_research.calculate(document['snapshot']))
        self.assertEqual(replay['selection']['scope'], 'diagnostic_result')
        self.assertEqual(replay['requested'], document['requested'])

    def test_public_data_cannot_claim_requested_strict_result(self):
        document = replay_document(public_research, public_snapshot(), selection_count=2, allow_diagnostic_replay=True)
        strict = vqm_research.profile()
        document['requested'] = {'profile_id': strict['profile_id'], 'profile_sha256': ranking.digest(strict)}
        result = ranking.replay_ranking(document)
        self.assertIsNone(result['requested_result'])
        self.assertEqual(result['diagnostic_result'], public_research.calculate(document['snapshot'], 2))

    def test_missing_requested_method_does_not_silently_promote_diagnostic(self):
        document = replay_document(vqm_research, strict_snapshot())
        del document['requested']['profile_sha256']
        result = ranking.replay_ranking(document)
        self.assertEqual(result['requested_method_relation'], 'UNKNOWN')
        self.assertEqual(result['status'], 'NOT_REPLAYED')
        document['allow_diagnostic_replay'] = True
        self.assertEqual(ranking.replay_ranking(document)['status'], 'DIAGNOSTIC_REPLAY_COMPUTED')

    def test_profile_bytes_hash_schema_and_contents_all_matter(self):
        original = replay_document(vqm_research, strict_snapshot())
        document = copy.deepcopy(original)
        document['profile']['text'] += ' '
        with self.assertRaisesRegex(ValueError, 'BYTES_HASH'):
            ranking.route_ranking(document)
        document = copy.deepcopy(original)
        profile = vqm_research.profile(); profile['peer_minimum'] += 1
        document['profile'] = source(profile)
        document['snapshot']['profile_sha256'] = ranking.digest(profile)
        self.assertIn('SUPPLIED_PROFILE_NOT_INSTALLED', ranking.route_ranking(document)['findings'])
        document = copy.deepcopy(original)
        document['snapshot']['profile_sha256'] = ranking.digest(public_research.profile())
        self.assertIsNone(ranking.route_ranking(document)['available_diagnostic_route'])
        for schema in (True, 99):
            document = copy.deepcopy(original); document['snapshot']['schema_version'] = schema
            self.assertIn('SNAPSHOT_SCHEMA_UNSUPPORTED_FOR_PROFILE', ranking.route_ranking(document)['findings'])

    def test_whitespace_changes_bytes_not_profile_identity(self):
        document = replay_document(vqm_research, strict_snapshot())
        document['profile'] = source(vqm_research.profile(), indent=4)
        self.assertEqual(ranking.route_ranking(document)['requested_method_relation'], 'SAME')

    def test_scorer_error_preserved_no_alternative_weights(self):
        document = replay_document(public_research, public_snapshot(), selection_count=3)
        document['snapshot']['session_dates'].pop()
        result = ranking.replay_ranking(document)
        self.assertEqual(result['status'], 'SCORER_INPUT_ERROR')
        self.assertIn('SESSION_GRID', result['scorer_error']['message'])
        self.assertIsNone(result['requested_result'])
        self.assertIsNone(result['diagnostic_result'])
        self.assertFalse(result['ranking_execution_verified'])

    def test_non_json_profile_and_extra_method_fields_rejected(self):
        document = replay_document(vqm_research, strict_snapshot())
        text = '{"profile_id":"first","profile_id":"second"}'
        document['profile'] = {'text': text, 'sha256': hashlib.sha256(text.encode()).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON'):
            ranking.route_ranking(document)
        document = replay_document(vqm_research, strict_snapshot())
        document['requested']['method'] = 'arbitrary cheapness'
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_REQUESTED_METHOD'):
            ranking.route_ranking(document)


class RankingComparisonTests(unittest.TestCase):
    def setUp(self):
        self.rows = {'candidates': ['North', 'South'],
                     'scores': [{'symbol': 'North', 'score': '0.2'}, {'symbol': 'South', 'score': '0.1'}],
                     'classifier_available': False}
        self.method = {'profile_id': 'synthetic-method', 'profile_version': '1', 'weights': {'x': 1}}

    def test_same_different_unknown_method_profiles_are_distinct(self):
        a = side(self.rows, method_profile=self.method)
        equal = ranking.compare_rankings(comparison(a, a))
        self.assertEqual(equal['dimensions']['method_profile']['status'], 'SAME')
        changed = copy.deepcopy(self.method); changed['weights'] = {'x': 2}
        different = ranking.compare_rankings(comparison(a, side(self.rows, method_profile=changed)))
        self.assertEqual(different['dimensions']['method_profile']['status'], 'DIFFERENT')
        self.assertEqual(different['scores']['method_comparability'], 'DIFFERENT')
        unknown = ranking.compare_rankings(comparison(a, side(self.rows)))
        self.assertEqual(unknown['dimensions']['method_profile']['status'], 'UNKNOWN')

    def test_both_missing_metadata_is_unknown_not_equal(self):
        a = side(self.rows)
        result = ranking.compare_rankings(comparison(a, a))
        for name in ('horizon', 'preferences', 'review_decisions', 'method_profile', 'snapshot'):
            self.assertEqual(result['dimensions'][name]['status'], 'UNKNOWN', name)
        self.assertEqual(result['candidates']['status'], 'SAME')
        self.assertEqual(result['dimensions']['classifier_available']['status'], 'SAME')
        self.assertFalse(result['dimensions']['classifier_available']['left'])
        self.assertEqual(result['per_name_buy_eligibility']['status'], 'NOT_ASSESSED')

    def test_explicit_metadata_change_is_independent_of_equal_candidates(self):
        a = side(self.rows, horizon={'duration': 'P2Y'}, preferences={'mode': 'none'}, review_decisions={'North': 'pending'})
        b = side(self.rows, horizon={'duration': 'P3Y'}, preferences={'mode': 'none'}, review_decisions={'North': 'reviewed'})
        result = ranking.compare_rankings(comparison(a, b))
        self.assertEqual(result['dimensions']['horizon']['status'], 'DIFFERENT')
        self.assertEqual(result['dimensions']['preferences']['status'], 'SAME')
        self.assertEqual(result['dimensions']['review_decisions']['status'], 'DIFFERENT')
        self.assertEqual(result['candidates']['status'], 'SAME')

    def test_rank_score_and_snapshot_differences_retain_separate_evidence(self):
        changed = copy.deepcopy(self.rows)
        changed['candidates'].reverse(); changed['scores'][0]['score'] = '0.35'
        a = side(self.rows, snapshot={'cash': 7, 'unavailable': None}, method_profile=self.method)
        b = side(changed, snapshot={'cash': 8}, method_profile=self.method)
        result = ranking.compare_rankings(comparison(a, b))
        self.assertEqual(result['candidates']['jaccard'], 1)
        self.assertEqual(len(result['candidates']['rank_differences']), 2)
        self.assertEqual(result['scores']['differences'][0]['right_minus_left'], '0.15')
        self.assertEqual(result['dimensions']['snapshot']['difference_count'], 2)
        self.assertEqual(result['dimensions']['snapshot']['differences'][1]['right_present'], False)
        self.assertEqual(result['provenance']['left']['bindings']['scores']['pointer'], '/ranking/scores')

    def test_missing_scores_and_empty_candidates_do_not_invent_percent_agreement(self):
        a = side({'candidates': [], 'scores': [], 'classifier_available': None})
        result = ranking.compare_rankings(comparison(a, a))
        self.assertIsNone(result['candidates']['jaccard'])
        self.assertIsNone(result['candidates']['fraction_of_left'])
        self.assertEqual(result['scores']['status'], 'UNKNOWN')
        self.assertEqual(result['dimensions']['classifier_available']['status'], 'UNKNOWN')
        a = side({'candidates': ['North'], 'scores': [{'symbol': 'North', 'score': None}]})
        self.assertEqual(ranking.compare_rankings(comparison(a, a))['scores']['unresolved_ids'], ['North'])

    def test_missing_pointer_is_retained_and_source_tampering_rejected(self):
        a = side(self.rows)
        a['bindings']['horizon'] = {'source_id': 'retained', 'pointer': '/absent'}
        result = ranking.compare_rankings(comparison(a, a))
        self.assertEqual(result['provenance']['left']['bindings']['horizon']['status'], 'PATH_ABSENT')
        a['sources']['retained']['text'] += ' '
        with self.assertRaisesRegex(ValueError, 'BYTES_HASH'):
            ranking.compare_rankings(comparison(a, a))

    def test_duplicate_identity_and_string_false_are_rejected(self):
        for change, error in (({'candidates': ['North', 'North']}, 'DUPLICATE_CANDIDATE'),
                              ({'classifier_available': 'false'}, 'CLASSIFIER_AVAILABILITY')):
            a = side({**self.rows, **change})
            with self.assertRaisesRegex(ValueError, error):
                ranking.compare_rankings(comparison(a, a))

    def test_snapshot_difference_limit_is_disclosed(self):
        document = comparison(side(self.rows, snapshot={'x': 1, 'y': 2}),
                              side(self.rows, snapshot={'x': 3, 'y': 4}))
        document['max_snapshot_differences'] = 1
        result = ranking.compare_rankings(document)['dimensions']['snapshot']
        self.assertEqual(result['difference_count'], 2)
        self.assertEqual(len(result['differences']), 1)
        self.assertTrue(result['differences_truncated'])


if __name__ == '__main__':
    unittest.main()
