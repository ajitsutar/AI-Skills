"""Opening-state scopes must control source events before ledger arithmetic."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from portfolio_projection import source_projection
from planning_comparison import source_alternatives


def document():
    return {'currency': 'USD', 'role': 'hypothetical_scenario', 'source_ref': 'fixture#',
            'source_role': 'supplied_observation', 'date_basis': 'source_calendar_label',
            'target_date': '2042-05-15', 'included_states': ['confirmed', 'planned', 'scenario'],
            'mark_policy': 'carry_forward_supplied', 'opening_tax_reserve': '0',
            'other_assets': [], 'liabilities': [],
            'source': {'currency': 'USD', 'as_of': '2042-05-01T12:00:00Z',
                       'baseline_rebalance': {'cash': '100', 'holdings': {'asset': '12'}, 'prices': {'asset': '4'}},
                       'scenario': {'clock': '2042-05-10T10:00:00Z', 'opening_convention': 'Reuse supplied baseline; only explicitly selected events.'},
                       'confirmed_cash_events': [{'available_at': '2042-05-12', 'amount': '-5', 'kind': 'external_obligation', 'confirmed': True}],
                       'withdrawal': {'spendable_by': '2042-05-15', 'amount': '10'},
                       'employer': {'symbol': 'asset', 'grant_records': [
                           {'vest_date': '2042-05-05', 'gross_shares': '3', 'shares_withheld_for_tax': '0',
                            'shares_sold_for_tax': '0', 'status': 'future_scheduled'}]}},
            'scenario_flows': [{'id': 'purchase', 'currency': 'USD', 'source_ref': 'scenario:purchase',
                                'source_role': 'hypothetical_scenario', 'kind': 'trade', 'state': 'scenario',
                                'date': '2042-05-11', 'asset_id': 'asset', 'included_in_opening': False,
                                'trade': {'side': 'buy', 'quantity': '2', 'price': '4', 'entry_orders': 1, 'costs': []}}]}


def independent():
    return {'mode': 'independent_scenario',
            'opening': {'balances_pointer': '/baseline_rebalance', 'as_of_pointer': '/scenario/clock',
                        'convention_pointer': '/scenario/opening_convention', 'reuse_basis': 'Explicit isolated balance-reuse assumption.'},
            'source_event_dispositions': [
                {'source_pointer': '/confirmed_cash_events/0', 'disposition': 'include', 'reason': 'Applies in this scenario.'},
                {'source_pointer': '/withdrawal', 'disposition': 'include', 'reason': 'Scenario spending objective.'},
                {'source_pointer': '/employer/grant_records/0', 'disposition': 'exclude_from_scenario', 'reason': 'Outside isolated scenario.'}]}


class ProjectionScopeTests(unittest.TestCase):
    def test_scenario_requires_explicit_scope_but_no_scenario_remains_compatible(self):
        doc = document()
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_PROJECTION_SCOPE'):
            source_projection(doc)
        doc['scenario_flows'] = []
        result = source_projection(doc)
        self.assertFalse(result['projection_scope_receipt']['explicit'])
        self.assertEqual(result['projection']['position_values'][0]['quantity'], '15')

    def test_baseline_continuation_and_independent_have_different_event_universes(self):
        doc = document(); doc['projection_scope'] = {'mode': 'baseline_continuation'}
        self.assertEqual(source_projection(doc)['projection']['position_values'][0]['quantity'], '17')
        doc['projection_scope'] = independent()
        original = deepcopy(doc)
        result = source_projection(doc)
        self.assertEqual(result['projection']['position_values'][0]['quantity'], '14')
        self.assertEqual(result['projection']['cash'], '77')
        self.assertEqual(result['source_flow_count'], 3)
        self.assertEqual(result['scoped_source_flow_count'], 2)
        self.assertEqual(result['bound_projection_input']['opening']['as_of'], '2042-05-10')
        self.assertEqual(result['bound_projection_input']['marks'][0]['as_of'], '2042-05-01')
        receipt = result['projection_scope_receipt']
        self.assertEqual(receipt['opening_binding']['raw_as_of'], doc['source']['scenario']['clock'])
        self.assertFalse(receipt['source_event_audit'][2]['passed_to_projection'])
        self.assertEqual(doc, original)

    def test_complete_unique_known_dispositions_required(self):
        for mutation, error in [('missing', 'COMPLETE'), ('duplicate', 'DUPLICATE'), ('invalid', 'UNKNOWN')]:
            doc = document(); doc['projection_scope'] = independent()
            rows = doc['projection_scope']['source_event_dispositions']
            if mutation == 'missing': rows.pop()
            elif mutation == 'duplicate': rows.append(deepcopy(rows[0]))
            else: rows[0]['source_pointer'] = '/not-an-event'
            with self.assertRaisesRegex(ValueError, error): source_projection(doc)

    def test_already_in_opening_retained_without_application_and_future_rejected(self):
        doc = document(); doc['projection_scope'] = independent()
        rows = doc['projection_scope']['source_event_dispositions']
        rows[2]['disposition'] = 'already_in_opening'
        result = source_projection(doc)
        self.assertEqual(result['projection']['position_values'][0]['quantity'], '14')
        self.assertEqual(result['projection_scope_receipt']['source_event_audit'][2]['disposition'], 'already_in_opening')
        rows[0]['disposition'] = 'already_in_opening'
        with self.assertRaisesRegex(ValueError, 'FUTURE_EVENT'): source_projection(doc)

    def test_included_preopening_and_same_day_events_rejected(self):
        for date in ('2042-05-05', '2042-05-10'):
            doc = document(); doc['projection_scope'] = independent()
            doc['source']['employer']['grant_records'][0]['vest_date'] = date
            doc['projection_scope']['source_event_dispositions'][2]['disposition'] = 'include'
            with self.assertRaisesRegex(ValueError, 'SCOPED_INCLUDED_EVENT_NOT_AFTER_OPENING'):
                source_projection(doc)

    def test_unknown_balances_and_later_events_are_not_filled_or_discarded(self):
        doc = document(); doc['projection_scope'] = independent()
        doc['source']['baseline_rebalance']['holdings']['asset'] = None
        doc['source']['baseline_rebalance']['cash'] = None
        doc['source']['withdrawal']['spendable_by'] = '2042-05-20'
        result = source_projection(doc)
        self.assertIsNone(result['projection']['cash'])
        self.assertIsNone(result['projection']['position_values'][0]['quantity'])
        self.assertEqual(len(result['projection_scope_receipt']['source_event_audit']), 3)
        self.assertIn('AFTER_TARGET_DATE', result['projection']['excluded_supplied_flows'][0]['exclusion_reasons'])

    def test_opening_binding_is_real_source_pointer_and_baseline_mode_disallows_override(self):
        for change in ('missing_pointer', 'other_balances', 'empty_basis'):
            doc = document(); doc['projection_scope'] = independent()
            opening = doc['projection_scope']['opening']
            if change == 'missing_pointer': opening['as_of_pointer'] = '/absent'
            elif change == 'other_balances': opening['balances_pointer'] = '/scenario'
            else: opening['reuse_basis'] = ''
            with self.assertRaises((ValueError, KeyError)): source_projection(doc)
        doc = document(); doc['projection_scope'] = {'mode': 'baseline_continuation', 'opening': {}}
        with self.assertRaisesRegex(ValueError, 'NO_EVENT_OR_OPENING_OVERRIDES'): source_projection(doc)

    def test_source_alternatives_inherit_one_scope_and_keep_empty_alternative(self):
        doc = document(); flow = doc.pop('scenario_flows')[0]
        doc['projection_scope'] = independent()
        doc['alternatives'] = [{'id': 'unchanged', 'scenario_flows': []}, {'id': 'purchase', 'scenario_flows': [flow]}]
        result = source_alternatives(doc)
        self.assertEqual([row['projection_receipt']['projection']['position_values'][0]['quantity'] for row in result['alternatives']], ['12', '14'])
        self.assertTrue(all(row['projection_receipt']['projection_scope_receipt']['mode'] == 'independent_scenario' for row in result['alternatives']))


if __name__ == '__main__':
    unittest.main()
