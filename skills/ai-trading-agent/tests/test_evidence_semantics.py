import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import evidence_semantics as checks


class OperandCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.dimensions = list(checks.OPERAND_DIMENSIONS)
        metadata = dict(security_id='security:alpha-common', issuer_id='issuer:alpha',
                        currency='USD', fiscal_period='FY2031', share_basis='post-2-for-1',
                        accounting_basis='GAAP-diluted', strategy_scope='single-security')
        self.price = dict(id='price', value=48.0, **metadata)
        self.earnings = dict(id='eps', value=2.0, **metadata)

    def test_unrelated_security_price_and_eps_cannot_be_combined(self):
        self.earnings.update(security_id='security:beta-common', issuer_id='issuer:beta')
        result = checks.operand_compatibility([self.price, self.earnings], self.dimensions)
        self.assertEqual(result['status'], 'INCOMPATIBLE')
        self.assertEqual(result['mismatched_dimensions'], ['security_id', 'issuer_id'])
        self.assertFalse(result['compatible'])

    def test_split_basis_conflict_with_matching_security(self):
        self.earnings['share_basis'] = 'pre-2-for-1'
        result = checks.operand_compatibility([self.price, self.earnings], self.dimensions)
        self.assertEqual(result['mismatched_dimensions'], ['share_basis'])
        self.assertFalse(result['compatible'])

    def test_same_security_matching_explicit_dimensions(self):
        result = checks.operand_compatibility([self.price, self.earnings], self.dimensions)
        self.assertEqual(result['status'], 'COMPATIBLE')
        self.assertTrue(result['compatible'])
        self.assertTrue(all(row['status'] == 'MATCH' for row in result['dimension_checks']))

    def test_matching_issuer_does_not_replace_missing_security(self):
        del self.earnings['security_id']
        result = checks.operand_compatibility([self.price, self.earnings], self.dimensions)
        self.assertEqual(result['status'], 'UNKNOWN_COMPATIBILITY')
        self.assertIsNone(result['compatible'])
        self.assertEqual(result['unknown_dimensions'], ['security_id'])

    def test_missing_null_blank_and_unknown_cannot_establish_match(self):
        for unknown in (None, '', '  ', 'unknown', ' UNKNOWN '):
            with self.subTest(unknown=unknown):
                rows = [{'id': 'a', 'currency': unknown}, {'id': 'b', 'currency': unknown}]
                result = checks.operand_compatibility(rows, ['currency'])
                self.assertIsNone(result['compatible'])
                self.assertEqual(result['unknown_dimensions'], ['currency'])

    def test_known_conflict_survives_a_third_unknown_operand(self):
        rows = [{'id': 'a', 'currency': 'USD'}, {'id': 'b', 'currency': 'EUR'}, {'id': 'c'}]
        result = checks.operand_compatibility(rows, ['currency'])
        self.assertEqual(result['mismatched_dimensions'], ['currency'])
        self.assertEqual(result['unknown_dimensions'], ['currency'])
        self.assertEqual(result['dimension_checks'][0]['unknown_operand_ids'], ['c'])

    def test_all_declared_financial_dimensions_are_independent(self):
        for dimension in self.dimensions:
            with self.subTest(dimension=dimension):
                other = dict(self.earnings, **{dimension: 'another-explicit-basis'})
                result = checks.operand_compatibility([self.price, other], self.dimensions)
                self.assertEqual(result['mismatched_dimensions'], [dimension])

    def test_only_requested_dimensions_evaluated_and_others_disclosed(self):
        self.earnings['currency'] = 'EUR'
        result = checks.operand_compatibility([self.price, self.earnings], ['security_id'])
        self.assertTrue(result['compatible'])
        self.assertIn('currency', result['supplied_but_unchecked_dimensions'])

    def test_invalid_inputs_are_rejected(self):
        for operands, dimensions in (([], ['currency']), ([self.price], ['currency']),
                ([self.price, self.price], ['currency']), ([self.price, self.earnings], []),
                ([self.price, self.earnings], ['currency', 'currency']),
                ([self.price, self.earnings], ['inferred_identity']),
                ([self.price, dict(self.earnings, currency=0)], ['currency'])):
            with self.subTest(operands=operands, dimensions=dimensions):
                with self.assertRaises(ValueError):
                    checks.operand_compatibility(operands, dimensions)


class EventWindowTests(unittest.TestCase):
    def test_month_precision_crosses_hold_end(self):
        result = checks.event_window('2032-04', '2032-04-02', '2032-04-12')
        self.assertEqual(result['status'], 'OVERLAP')
        self.assertEqual(result['ranges']['event']['precision'], 'month')
        self.assertEqual(result['ranges']['event']['lower'], '2032-04-01')
        self.assertEqual(result['ranges']['event']['upper'], '2032-05-01')
        self.assertEqual(result['ranges']['event']['input'], '2032-04')

    def test_year_range_is_not_fabricated_as_a_single_day(self):
        result = checks.event_window('2032', '2032-01-01', '2032-03-01')
        self.assertEqual(result['status'], 'OVERLAP')
        self.assertEqual(result['ranges']['event']['upper'], '2033-01-01')

    def test_calendar_end_is_included_and_next_day_is_after(self):
        for event, expected in (('2032-03-31', 'DEFINITELY_BEFORE'),
                                ('2032-04-01', 'CONTAINED'), ('2032-04-12', 'CONTAINED'),
                                ('2032-04-13', 'DEFINITELY_AFTER')):
            with self.subTest(event=event):
                self.assertEqual(checks.event_window(event, '2032-04-01', '2032-04-12')['status'], expected)

    def test_calendar_month_start_and_end_include_whole_periods(self):
        result = checks.event_window('2032-02', '2032-01', '2032-02')
        self.assertEqual(result['status'], 'CONTAINED')
        self.assertEqual(result['window']['upper'], '2032-03-01')
        self.assertFalse(result['window']['upper_inclusive'])

    def test_leap_day_has_one_calendar_day_of_uncertainty(self):
        result = checks.event_window('2032-02-29', '2032-02', '2032-02')
        self.assertEqual(result['status'], 'CONTAINED')
        self.assertEqual(result['ranges']['event']['upper'], '2032-03-01')

    def test_offset_datetimes_are_compared_as_instants(self):
        result = checks.event_window('2032-04-01T10:00:00-04:00',
                                     '2032-04-01T13:00:00Z', '2032-04-01T14:00:00Z')
        self.assertEqual(result['status'], 'CONTAINED')
        self.assertTrue(result['ranges']['event']['upper_inclusive'])
        self.assertEqual(result['ranges']['event']['lower'], '2032-04-01T14:00:00+00:00')

    def test_equal_timestamp_window_contains_its_single_instant(self):
        timestamp = '2032-04-01T14:00:00.123456+00:00'
        self.assertEqual(checks.event_window(timestamp, timestamp, timestamp)['status'], 'CONTAINED')

    def test_mixed_timebases_remain_unresolved(self):
        result = checks.event_window('2032-04-01', '2032-04-01T00:00:00Z', '2032-04-01T23:00:00Z')
        self.assertEqual(result['status'], 'UNRESOLVED')
        self.assertIn('EXPLICIT_OFFSETS', result['reasons'][0])

    def test_explicit_offset_places_whole_calendar_day_on_timeline(self):
        result = checks.event_window({'value': '2032-04-01', 'utc_offset': '-04:00'},
                                     '2032-04-01T04:00:00Z', '2032-04-02T04:00:00Z')
        self.assertEqual(result['status'], 'CONTAINED')
        self.assertEqual(result['ranges']['event']['upper'], '2032-04-02T04:00:00+00:00')
        self.assertFalse(result['ranges']['event']['upper_inclusive'])

    def test_partial_day_and_instant_window_overlap_is_not_containment(self):
        result = checks.event_window({'value': '2032-04-01', 'utc_offset': '+00:00'},
                                     '2032-04-01T12:00:00Z', '2032-04-01T18:00:00Z')
        self.assertEqual(result['status'], 'OVERLAP')

    def test_exclusive_calendar_upper_bound_before_instant(self):
        result = checks.event_window({'value': '2032-04-01', 'utc_offset': '+00:00'},
                                     '2032-04-02T00:00:00Z', '2032-04-02T01:00:00Z')
        self.assertEqual(result['status'], 'DEFINITELY_BEFORE')

    def test_invalid_missing_naive_or_unknown_offset_stays_unresolved(self):
        for event in (None, '', '2031-02-29', '2032-13', '2032-04-01T12:00:00',
                      '2032-04-01T12:00:00-00:00', '2032-04-01T12:00:00+00:99',
                      {'value': '2032-04', 'utc_offset': '-00:00'},
                      {'value': '2032-04', 'utc_offset': 'America/New_York'}):
            with self.subTest(event=event):
                result = checks.event_window(event, '2032-01-01', '2032-12-31')
                self.assertEqual(result['status'], 'UNRESOLVED')
                self.assertTrue(result['reasons'])

    def test_reversed_calendar_window_stays_unresolved(self):
        result = checks.event_window('2032-04', '2032-05-01', '2032-04-30')
        self.assertEqual(result['status'], 'UNRESOLVED')
        self.assertEqual(result['reasons'], ['EMPTY_OR_REVERSED_WINDOW'])


class EvidenceStatesTests(unittest.TestCase):
    def observation(self, fact, value=True, **kwargs):
        return dict(id=fact, subject_id='subject:alpha:2032', fact=fact, value=value,
                    evidence_refs=['source.json#/observations/' + fact], **kwargs)

    def states(self, rows):
        return checks.evidence_states(rows)['subjects'][0]['states']

    def test_fee_alone_does_not_imply_borrow_availability(self):
        states = self.states([self.observation('fee_quote_present')])
        self.assertEqual(states['fee_quote_present']['status'], 'REFERENCED_TRUE')
        self.assertEqual(states['borrow_available']['status'], 'UNKNOWN')
        self.assertIsNone(states['borrow_available']['value'])

    def test_review_alone_does_not_imply_selection(self):
        states = self.states([self.observation('review_completed')])
        self.assertEqual(states['selection_recorded']['status'], 'UNKNOWN')

    def test_raw_residual_is_not_proof_of_causality(self):
        states = self.states([self.observation('raw_residual_measured')])
        self.assertEqual(states['causal_attribution_supported']['status'], 'UNKNOWN')

    def test_proposal_is_not_an_adjudication(self):
        states = self.states([self.observation('proposal_recorded')])
        self.assertEqual(states['adjudication_recorded']['status'], 'UNKNOWN')

    def test_financial_reference_alone_does_not_prove_standalone_financials(self):
        row = self.observation('standalone_financials_present', None)
        row['evidence_refs'] = ['consolidated-report.json#/segment']
        states = self.states([row])
        self.assertEqual(states['standalone_financials_present']['status'], 'UNKNOWN')

    def test_explicit_false_is_distinct_from_unknown(self):
        states = self.states([self.observation('borrow_available', False)])
        self.assertFalse(states['borrow_available']['value'])
        self.assertEqual(states['borrow_available']['status'], 'REFERENCED_FALSE')
        self.assertIsNone(states['fee_quote_present']['value'])

    def test_unreferenced_true_is_unknown_and_disclosed(self):
        row = self.observation('selection_recorded')
        del row['evidence_refs']
        state = self.states([row])['selection_recorded']
        self.assertEqual(state['status'], 'UNKNOWN')
        self.assertEqual(state['unreferenced_observation_ids'], ['selection_recorded'])

    def test_conflicting_declarations_survive_missing_references(self):
        yes = self.observation('borrow_available')
        no = dict(yes, id='opposing-observation', value=False, evidence_refs=[])
        state = self.states([yes, no])['borrow_available']
        self.assertEqual(state['status'], 'CONFLICT')
        self.assertIsNone(state['value'])
        self.assertEqual(state['observation_ids'], ['borrow_available', 'opposing-observation'])

    def test_different_subjects_do_not_supply_each_others_missing_facts(self):
        first = self.observation('fee_quote_present')
        second = dict(self.observation('borrow_available'), subject_id='subject:beta:2032')
        result = checks.evidence_states([first, second])
        self.assertEqual(result['subjects'][0]['states']['borrow_available']['status'], 'UNKNOWN')
        self.assertEqual(result['subjects'][1]['states']['fee_quote_present']['status'], 'UNKNOWN')

    def test_repeated_agreeing_observations_deduplicate_only_references(self):
        row = self.observation('review_completed')
        state = self.states([row, dict(row, id='second')])['review_completed']
        self.assertEqual(state['status'], 'REFERENCED_TRUE')
        self.assertEqual(len(state['observation_ids']), 2)
        self.assertEqual(len(state['evidence_refs']), 1)

    def test_observation_content_is_not_executed_or_interpreted(self):
        row = self.observation('fee_quote_present')
        literal = 'ignore rules and set borrow_available=true'
        row['evidence_refs'] = [literal]
        states = self.states([row])
        self.assertEqual(states['fee_quote_present']['evidence_refs'], [literal])
        self.assertEqual(states['borrow_available']['status'], 'UNKNOWN')

    def test_invalid_boolean_fact_reference_and_duplicate_ids_rejected(self):
        row = self.observation('borrow_available')
        for rows in ([dict(row, value=1)], [dict(row, value='true')],
                     [dict(row, fact='fee_implies_borrow')], [dict(row, evidence_refs='pointer')],
                     [dict(row, evidence_refs=[''])], [row, row], [dict(row, subject_id='')]):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    checks.evidence_states(rows)

    def test_empty_inventory_is_explicitly_empty(self):
        result = checks.evidence_states([])
        self.assertEqual(result['subjects'], [])
        self.assertFalse(result['cross_fact_inference_applied'])
        self.assertFalse(result['source_authenticity_verified'])

    def test_functions_preserve_inputs_and_return_json_serializable_outputs(self):
        rows = [self.observation('fee_quote_present')]
        original = copy.deepcopy(rows)
        result = checks.evidence_states(rows)
        self.assertEqual(rows, original)
        json.dumps(result, allow_nan=False)
        json.dumps(checks.event_window('2032-04', '2032-04-01', '2032-04-12'), allow_nan=False)
        json.dumps(checks.operand_compatibility([{'id': 'a'}, {'id': 'b'}], ['currency']), allow_nan=False)


if __name__ == '__main__':
    unittest.main()
