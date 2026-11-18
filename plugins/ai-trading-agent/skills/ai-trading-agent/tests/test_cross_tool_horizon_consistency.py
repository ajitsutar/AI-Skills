import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from horizon_consistency import audit
from research_contracts import route_horizon
from horizon_review import resolve_horizon
from research_handoff import lock


class HorizonConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.route = {'mode': 'flexible_review', 'as_of': '2026-07-01',
                      'entry_at': '2026-07-02', 'comparison_at': '2026-07-05'}
        self.fixed = {'schema_version': 1, 'as_of': '2026-07-01T14:00:00Z',
                      'entry_at': '2026-07-02T15:00:00Z', 'anchor_date': '2026-07-02',
                      'deadline_mode': 'fixed_end', 'duration': {'unit': 'calendar_days', 'value': 3},
                      'early_exit_policy': 'risk_exits_allowed', 'non_session_exit': 'previous_session',
                      'exit_buffer_minutes': 10, 'exchange': 'XNYS', 'strategy_route': 'swing',
                      'calendar_confirmed_through': '2026-12-31',
                      'calendar_evidence': ['Synthetic calendar declaration, not live confirmation']}

    def request(self, kind='route_request', context=None, route=None):
        return {'request_id': 'synthetic-review',
                'route': {'request_id': 'synthetic-review', 'document': copy.deepcopy(route or self.route)},
                'contexts': [{'id': 'downstream', 'request_id': 'synthetic-review', 'kind': kind,
                              'clock_role': 'hard_exit',
                              'document': copy.deepcopy(context or self.route)}]}

    def codes(self, result):
        return {x['code'] for x in result['result']['findings']}

    def test_independently_valid_flexible_and_fixed_inputs_are_a_detectable_conflict(self):
        # Existing helpers each accept their own declaration; neither sees the other.
        self.assertEqual(route_horizon(self.route)['result']['status'], 'ROUTED')
        fixed = resolve_horizon(self.fixed)
        self.assertNotEqual(fixed['raw_deadline_date'], fixed['exit_session'])
        result = audit(self.request('clock_request', self.fixed))
        self.assertEqual(result['result']['status'], 'CONFLICT')
        self.assertIn('FORCED_EXIT_MODE_CONFLICT', self.codes(result))
        self.assertIn('COMPARISON_HAS_EXIT_BUFFER', self.codes(result))
        self.assertIn('COMPARISON_AT_PRECISION_MISMATCH', self.codes(result))
        self.assertEqual(result['result']['route']['comparison_at'], '2026-07-05')
        self.assertIsNone(result['result']['route']['hard_exit_at'])

    def test_same_flexible_context_preserves_nonsession_date_without_calendar_conversion(self):
        result = audit(self.request())
        self.assertEqual(result['result']['status'], 'CONSISTENT')
        self.assertFalse(result['result']['intent_authenticated'])
        self.assertFalse(result['result']['screen_checks_replaced'])
        self.assertFalse(result['result']['narrative_correctness_verified'])

    def test_comparison_alias_does_not_infer_forced_sale_but_cannot_hide_clock_shift(self):
        doc = self.request('clock_request', self.fixed)
        doc['contexts'][0]['clock_role'] = 'comparison_only'
        result = audit(doc)
        self.assertEqual(result['result']['status'], 'CONFLICT')
        self.assertNotIn('FORCED_EXIT_MODE_CONFLICT', self.codes(result))
        self.assertIn('COMPARISON_AT_PRECISION_MISMATCH', self.codes(result))
        actual = resolve_horizon(self.fixed)
        doc['route']['document'].update(as_of=actual['as_of'], entry_at=actual['entry_at'], comparison_at=actual['exit_at'])
        self.assertEqual(audit(doc)['result']['status'], 'CONSISTENT')
        del doc['contexts'][0]['clock_role']
        self.assertEqual(audit(doc)['result']['status'], 'UNRESOLVED')

    def test_screen_input_is_recomputed_and_fixed_exit_requirements_are_not_relaxed(self):
        route = {'mode': 'fixed_exit', 'fixed_spec': self.fixed}
        screen = {'decision_mode': 'fixed_horizon', 'horizon': self.fixed}
        doc = self.request('screen_request', screen, route)
        result = audit(doc)
        self.assertEqual(result['result']['status'], 'CONSISTENT')
        self.assertEqual(result['result']['route']['hard_exit_at'], resolve_horizon(self.fixed)['exit_at'])
        doc['contexts'][0]['document']['horizon']['exit_buffer_minutes'] = 0
        self.assertEqual(audit(doc)['result']['status'], 'UNRESOLVED')
        with self.assertRaises(ValueError):
            route_horizon({'mode': 'fixed_exit', 'fixed_spec': doc['contexts'][0]['document']['horizon']})

    def test_a_long_term_screen_alone_cannot_certify_clock_consistency(self):
        result = audit(self.request('screen_request', {'decision_mode': 'long_term'}))
        self.assertEqual(result['result']['status'], 'UNRESOLVED')
        self.assertIn('SCREEN_HAS_NO_EXACT_CLOCK', self.codes(result))

    def test_wrong_request_identity_and_duplicate_contexts_cannot_pass(self):
        doc = self.request()
        doc['contexts'][0]['request_id'] = 'other-request'
        self.assertEqual(audit(doc)['result']['status'], 'CONFLICT')
        doc['contexts'].append(copy.deepcopy(doc['contexts'][0]))
        with self.assertRaisesRegex(ValueError, 'UNIQUE_CONTEXT_IDS_REQUIRED'):
            audit(doc)

    def test_shifted_date_and_injected_hard_exit_are_detected(self):
        doc = self.request()
        doc['contexts'][0]['document']['comparison_at'] = '2026-07-06'
        self.assertIn('COMPARISON_AT_DIFFERENT', self.codes(audit(doc)))
        doc = self.request()
        doc['contexts'][0]['document']['hard_exit_at'] = '2026-07-05'
        self.assertIn('FLEXIBLE_REQUEST_CONTAINS_FORCED_EXIT_CONFLICT', self.codes(audit(doc)))

    def test_equivalent_timezone_instants_match_but_date_precision_is_not_invented(self):
        route = dict(self.route, entry_at='2026-07-02T15:00:00Z', comparison_at='2026-07-06T20:00:00Z')
        other = dict(route, comparison_at='2026-07-06T13:00:00-07:00')
        self.assertEqual(audit(self.request(context=other, route=route))['result']['status'], 'CONSISTENT')
        other['comparison_at'] = '2026-07-06'
        self.assertIn('COMPARISON_AT_PRECISION_MISMATCH', self.codes(audit(self.request(context=other, route=route))))

    def test_handoff_contract_must_match_route_and_retain_contract_integrity(self):
        mandate = {'prompt': 'Synthetic comparison', 'universe': 'synthetic', 'hold': 'three days',
                   'standing_preferences': 'ignore', 'selection_mode': 'computed_order',
                   'allowed_statuses': ['Eligible'], 'custom_filters': [],
                   'information_cutoff': '2026-07-01T14:00:00Z', 'entry_at': '2026-07-02T15:00:00Z',
                   'comparison_at': '2026-07-06T20:00:00Z', 'price_date': '2026-07-01',
                   'horizon_mode': 'flexible_review'}
        contract = lock(mandate)
        route = dict(self.route, as_of=mandate['information_cutoff'], entry_at=mandate['entry_at'], comparison_at=mandate['comparison_at'])
        doc = self.request('handoff_contract', contract, route)
        self.assertEqual(audit(doc)['result']['status'], 'CONSISTENT')
        doc['contexts'][0]['document']['mandate']['comparison_at'] = '2026-07-07T20:00:00Z'
        self.assertEqual(audit(doc)['result']['status'], 'UNRESOLVED')

    def test_input_is_not_mutated_and_empty_audit_is_not_a_pass(self):
        doc = self.request(); original = copy.deepcopy(doc)
        audit(doc)
        self.assertEqual(doc, original)
        doc['contexts'] = []
        with self.assertRaisesRegex(ValueError, 'HORIZON_CONTEXTS_REQUIRED'):
            audit(doc)


if __name__ == '__main__':
    unittest.main()
