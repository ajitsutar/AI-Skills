"""Regression coverage for omitted intent and exhaustive finite-universe review."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_research_handoff as support
from research_handoff import lock, evaluate, verify_contract
from public_research import digest


class OptionalMandateTests(unittest.TestCase):
    setUp = support.HandoffTests.setUp
    evidence = support.HandoffTests.evidence
    reviews = support.HandoffTests.reviews

    def relock(self, mandate):
        self.c = lock(mandate)
        self.l['contract_sha256'] = digest(self.c)
        self.l['rows'] = [self.evidence('DEMO' + str(i)) for i in range(10)]

    def run_review(self, review=None):
        with patch('research_handoff.review_screen', return_value=review or self.reviews()):
            return evaluate(self.c, self.s, self.l, {'decision_mode': 'fixed_horizon'}, self.source_root)

    def test_absent_count_and_budget_do_not_invent_a_quota_or_capital(self):
        m = copy.deepcopy(self.m)
        del m['count']; del m['capital']
        self.relock(m)
        self.assertIsNone(self.c['mandate']['count'])
        self.assertIsNone(self.c['mandate']['capital'])
        verify_contract(self.c)
        result = self.run_review()
        self.assertEqual(result['selected_symbols'], ['DEMO' + str(i) for i in reversed(range(10))])
        self.assertEqual(len(result['research_candidates']), 10)
        self.assertIsNone(result['requested_count_met'])
        self.assertEqual(result['completion_basis'], 'EXHAUSTIVE_UNIVERSE_REVIEW')

    def test_budget_has_no_effect_on_identical_ranking_or_selection(self):
        self.relock(self.m)
        with_capital = self.run_review()
        m = copy.deepcopy(self.m); m.pop('capital')
        self.relock(m)
        without_capital = self.run_review()
        for field in ('research_candidates', 'decisions', 'selected_symbols', 'public_result_sha256'):
            self.assertEqual(with_capital[field], without_capital[field])
        m['research_intent'] = 'allocation'
        with self.assertRaisesRegex(ValueError, 'CAPITAL_REQUIRED_FOR_ALLOCATION'):
            lock(m)

    def test_invalid_supplied_count_and_capital_remain_invalid(self):
        for field, value in [('count', 0), ('count', False), ('count', 2.5),
                             ('capital', 0), ('capital', True), ('capital', 'NaN')]:
            m = copy.deepcopy(self.m); m[field] = value
            with self.assertRaises(ValueError):
                lock(m)

    def test_fewer_than_requested_complete_only_after_entire_universe_resolved(self):
        self.relock(self.m)
        review = self.reviews()
        for r in review['candidates']:
            if r['symbol'] not in {'DEMO9', 'DEMO8'}:
                r['status'] = 'Reject'
        result = self.run_review(review)
        self.assertEqual(result['selected_symbols'], ['DEMO9', 'DEMO8'])
        self.assertEqual(result['selection_status'], 'COMPUTED_REVIEWED_COMPARISON')
        self.assertFalse(result['requested_count_met'])
        self.assertEqual(result['count_shortfall'], 1)
        self.assertEqual(result['completion_basis'], 'EXHAUSTIVE_UNIVERSE_REVIEW')
        # A lower-ranked unresolved contender can still supply the third choice.
        review['candidates'][0]['status'] = 'Watch'
        review['candidates'][0]['unresolved_checks'] = 1
        result = self.run_review(review)
        self.assertEqual(result['selected_symbols'], [])
        self.assertIn('DEMO0', result['blocking_review_symbols'])

    def test_zero_selections_can_be_an_exhausted_review_not_a_count_pass(self):
        self.relock(self.m)
        review = self.reviews()
        for r in review['candidates']:
            r['status'] = 'Reject'
        result = self.run_review(review)
        self.assertEqual(result['selection_status'], 'COMPUTED_REVIEWED_COMPARISON')
        self.assertEqual(result['selected_symbols'], [])
        self.assertFalse(result['requested_count_met'])
        self.assertEqual(result['count_shortfall'], 3)

    def test_no_quota_must_resolve_low_ranked_frontier(self):
        m = copy.deepcopy(self.m); m['count'] = None
        self.relock(m)
        review = self.reviews(); review['candidates'][0]['unresolved_checks'] = 1
        result = self.run_review(review)
        self.assertEqual(result['selected_symbols'], [])
        self.assertIn('DEMO0', result['blocking_review_symbols'])
        self.assertFalse(result['review_queue_exhausted'])

    def test_provisional_count_does_not_claim_final_target_met(self):
        self.relock(self.m)
        self.l['rows'] = [r for r in self.l['rows'] if r['symbol'] != 'DEMO9']
        result = self.run_review()
        self.assertEqual(len(result['provisional_reviewed_choices']), 3)
        self.assertEqual(result['selected_symbols'], [])
        self.assertFalse(result['requested_count_met'])
        self.assertIsNone(result['count_shortfall'])

    def test_unscored_issuer_cannot_be_hidden_by_exhaustion(self):
        m = copy.deepcopy(self.m); m['count'] = 20
        self.relock(m)
        # Nonempty response with a missing financial cell is not a network failure.
        self.s['rows'][0]['income']['data'][0][0] = None
        result = self.run_review()
        self.assertFalse(result['coverage']['full_universe_scored'])
        self.assertEqual(result['selected_symbols'], [])
        self.assertEqual(result['selection_status'], 'INCOMPLETE_REVIEW')

    def test_event_block_with_incomplete_evidence_cannot_exhaust_queue(self):
        m = copy.deepcopy(self.m); m['count'] = None
        self.relock(m)
        review = self.reviews(); row = review['candidates'][0]
        row['event_status'] = 'blocked'; row['primary_evidence_complete'] = False
        result = self.run_review(review)
        self.assertIn('DEMO0', result['blocking_review_symbols'])
        self.assertEqual(result['selected_symbols'], [])

    def test_documented_defaults_preserve_unspecified_descriptive_intent(self):
        m = copy.deepcopy(self.m)
        for field in ('risk_posture', 'early_exit_policy', 'earnings_policy'):
            del m[field]
        c = lock(m); frozen = c['mandate']
        self.assertEqual(frozen['risk_posture'], 'unspecified')
        self.assertEqual(frozen['early_exit_policy'], 'unspecified')
        self.assertEqual(frozen['earnings_policy'], 'allow_with_disclosure')
        self.assertEqual(frozen['field_provenance']['risk_posture'], 'unresolved')
        self.assertEqual(frozen['field_provenance']['earnings_policy'], 'documented_default')
        self.assertEqual(frozen['custom_filters'], [])
        self.assertEqual(frozen['standing_preferences'], 'ignore')
        verify_contract(c)
        m['earnings_policy'] = 'exclude_during_hold'
        self.assertEqual(lock(m)['mandate']['earnings_policy'], 'exclude_during_hold')
        m['standing_preferences'] = None
        with self.assertRaisesRegex(ValueError, 'PREFERENCE_SCOPE_REQUIRED'):
            lock(m)

    def test_flexible_comparison_has_no_forced_sale_and_keeps_horizon_checks(self):
        m = copy.deepcopy(self.m)
        m['horizon_mode'] = 'flexible_review'
        m['comparison_at'] = m.pop('exit_at')
        self.relock(m)
        frozen = self.c['mandate']
        self.assertFalse(frozen['forced_exit'])
        self.assertIsNone(frozen['hard_exit_at'])
        result = self.run_review()
        self.assertFalse(result['forced_exit'])
        self.assertEqual(result['comparison_at'], self.m['exit_at'])
        review = self.reviews(); review['horizon']['exit_at'] = '2028-06-15T19:45:00Z'
        with self.assertRaisesRegex(ValueError, 'REVIEW_CLOCK_MISMATCH'):
            self.run_review(review)
        m['forced_exit'] = True
        with self.assertRaisesRegex(ValueError, 'FORCED_EXIT_MODE_CONFLICT'):
            lock(m)

    def test_explicit_exit_and_legacy_fields_are_preserved_not_reinterpreted_as_orders(self):
        m = copy.deepcopy(self.m); m['horizon_mode'] = 'fixed_exit'; m['forced_exit'] = True
        c = lock(m)
        for field in self.m:
            self.assertEqual(c['mandate'][field], self.m[field])
        self.assertEqual(c['mandate']['hard_exit_at'], self.m['exit_at'])
        self.assertFalse(c['execution_authorized'])
        # A frozen old schema/hash is not silently relocked or upgraded.
        archived = copy.deepcopy(c); archived['schema_version'] = 1
        with self.assertRaisesRegex(ValueError, 'CONTRACT_OR_IMPLEMENTATION_MISMATCH'):
            verify_contract(archived)

    def test_default_route_template_agrees_with_public_handoff(self):
        root = Path(__file__).resolve().parents[1]
        settings = json.loads((root/'templates/research-settings.example.json').read_text())['long_term']
        self.assertEqual(settings['profile_path'], 'profiles/public-vqm-discovery-v1.json')
        self.assertEqual(settings['strict_alternative']['profile_path'], 'profiles/vqm-fundamental-v1.json')
        self.assertEqual(settings['mandate_defaults']['earnings_policy'], 'allow_with_disclosure')
        self.assertIsNone(settings['mandate_defaults']['count'])
        self.assertIsNone(settings['mandate_defaults']['capital'])


if __name__ == '__main__':
    unittest.main()
