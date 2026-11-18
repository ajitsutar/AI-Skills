"""Synthetic scope invariants; no participant answers or fixture-specific facts."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research_contracts as rc


class ResearchCapabilityScopeTests(unittest.TestCase):
    def document(self):
        return {'mode': 'flexible_review', 'as_of': '2032-03-01',
                'entry_at': '2032-03-02', 'comparison_at': '2036-03-02',
                'event_coverage': {'through': '2032-07-01', 'basis': 'synthetic disclosed window'}}

    def route(self, document):
        result = rc.route_horizon(document)['result']
        return result, result['research_capability_scope']

    def test_partial_calendar_retains_horizon_and_feasible_research(self):
        doc = self.document(); before = copy.deepcopy(doc)
        result, scope = self.route(doc)
        self.assertEqual(doc, before)
        self.assertEqual(result['status'], 'ROUTED')
        self.assertEqual(result['comparison_at'], doc['comparison_at'])
        self.assertEqual(scope['comparison_at'], doc['comparison_at'])
        self.assertIsNone(scope['hard_exit_at'])
        self.assertFalse(result['forced_exit'])
        self.assertEqual({r['scope']: r['status'] for r in scope['feasible_work']},
                         {'available_event_description': 'AVAILABLE_WITH_DISCLOSURES',
                          'qualitative_risk_review': 'AVAILABLE_WITH_DISCLOSURES'})

    def test_no_calendar_preserves_unknowns_without_disabling_description(self):
        doc = self.document(); doc.pop('event_coverage')
        result, scope = self.route(doc)
        self.assertEqual(result['event_coverage']['status'], 'UNKNOWN')
        self.assertEqual(scope['refresh']['unknown_after'], doc['entry_at'])
        self.assertEqual(scope['refresh']['unknown_through'], doc['comparison_at'])
        self.assertTrue(all(r['status'] == 'AVAILABLE_WITH_DISCLOSURES' for r in scope['feasible_work']))

    def test_full_calendar_never_certifies_event_absence_or_forecast(self):
        doc = self.document(); doc['event_coverage']['through'] = '2036-03-03'
        result, scope = self.route(doc)
        self.assertEqual(result['event_coverage']['status'], 'DECLARED_THROUGH_COMPARISON')
        self.assertFalse(scope['refresh']['coverage_incomplete_or_uncertain'])
        self.assertEqual({r['scope']: r['status'] for r in scope['uncertified_claims']},
                         {'event_free_hold': 'NOT_CERTIFIED_BY_ROUTING',
                          'quantified_gap_risk': 'REQUIRES_SEPARATE_EVIDENCE',
                          'terminal_forecast_or_ranking': 'REQUIRES_SEPARATE_EVIDENCE'})
        self.assertEqual(scope['research_complete'], 'NOT_ASSESSED')

    def test_explicit_exclusions_are_preserved_and_not_waived(self):
        for exclusion in ('entry_only', 'full_hold'):
            for through in ('2032-07-01', '2036-03-03'):
                with self.subTest(exclusion=exclusion, through=through):
                    doc = self.document(); doc['event_exclusion_requirement'] = exclusion
                    doc['event_coverage']['through'] = through
                    _, scope = self.route(doc)
                    requirement = scope['event_exclusion_requirement']
                    self.assertEqual(requirement['scope'], exclusion)
                    self.assertEqual(requirement['status'], 'DECLARED_UNCERTIFIED')
                    self.assertFalse(requirement['waived'])

    def test_unknown_exclusion_is_not_inferred_as_none(self):
        _, scope = self.route(self.document())
        self.assertEqual(scope['event_exclusion_requirement']['scope'], 'not_declared')
        self.assertEqual(scope['event_exclusion_requirement']['status'], 'NOT_DECLARED_TO_THIS_ROUTER')
        self.assertFalse(scope['event_exclusion_requirement']['other_event_policies_evaluated'])
        doc = self.document(); doc['event_exclusion_requirement'] = 'none'
        _, scope = self.route(doc)
        self.assertEqual(scope['event_exclusion_requirement']['scope'], 'none')

    def test_invalid_exclusion_is_rejected(self):
        for invalid in (True, None, 'automatically_avoid_earnings', ['full_hold']):
            doc = self.document(); doc['event_exclusion_requirement'] = invalid
            with self.assertRaisesRegex(ValueError, 'EXPLICIT_EVENT_EXCLUSION_REQUIREMENT'):
                self.route(doc)

    def test_conflicting_hard_exit_is_visible_and_not_repaired(self):
        doc = self.document(); doc['forced_exit'] = True; doc['hard_exit_at'] = '2033-03-02'
        result, scope = self.route(doc)
        self.assertEqual(result['status'], 'CONFLICT')
        self.assertEqual(scope['horizon_dependent_work'], 'RESOLVE_HORIZON_CONFLICT')
        self.assertEqual(scope['horizon_conflicts'], result['issues'])
        self.assertEqual(scope['comparison_at'], '2036-03-02')

    def test_reversed_chronology_still_fails(self):
        doc = self.document(); doc['comparison_at'] = '2031-03-01'
        with self.assertRaisesRegex(ValueError, 'HORIZON_CHRONOLOGY'):
            self.route(doc)

    def test_mixed_precision_is_uncertain_not_clear(self):
        doc = self.document(); doc['comparison_at'] = '2036-03-02T17:00:00Z'
        doc['event_coverage']['through'] = '2036-03-02'
        result, scope = self.route(doc)
        self.assertEqual(result['event_coverage']['status'], 'COVERAGE_PRECISION_UNKNOWN')
        self.assertTrue(scope['refresh']['coverage_incomplete_or_uncertain'])

    def test_projection_creates_no_schedule_events_or_authority(self):
        _, scope = self.route(self.document())
        self.assertFalse(scope['refresh']['review_schedule_created'])
        self.assertFalse(scope['refresh']['events_created'])
        self.assertFalse(scope['execution_authorized'])
        self.assertNotIn('next_review_at', scope['refresh'])


if __name__ == '__main__':
    unittest.main()
