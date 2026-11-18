"""Supplied analytical observations are not missing merely because quotes are unknown."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_comparison import _source_context_evidence_inventory, source_alternatives


class SourceContextEvidenceInventoryTests(unittest.TestCase):
    def test_zero_null_and_absent_are_distinct(self):
        source = {'baseline_rebalance': {'holdings': {'zero': 1, 'null': 1, 'absent': 1},
                                         'prices': {'zero': 0, 'null': None}},
                  'cost_assumptions': {'fee_per_trade': 0, 'one_way_slippage_bps': None}}
        result = _source_context_evidence_inventory(source)
        rows = result['analytical_price_fields']
        self.assertEqual([row['state'] for row in rows], ['SUPPLIED_VALUE', 'SUPPLIED_NULL', 'ABSENT'])
        self.assertEqual(rows[0]['value'], 0)
        self.assertIsNone(rows[2]['source_pointer'])
        self.assertEqual(result['supplied_cost_assumption_field_names'], ['fee_per_trade'])

    def test_supplied_marks_and_costs_never_claim_live_terms(self):
        source = {'currency': 'USD', 'as_of': '2041-02-03',
                  'baseline_rebalance': {'prices': {'SECURITY': '87.25'}},
                  'cost_assumptions': {'fee_per_trade': '1.5', 'one_way_slippage_bps': '7'}}
        result = _source_context_evidence_inventory(source)
        self.assertEqual(result['analytical_price_fields'][0]['evidence_role'], 'supplied_analytical_mark')
        self.assertEqual(result['cost_assumption_fields'][0]['evidence_role'], 'supplied_cost_assumption')
        self.assertFalse(result['current_executable_prices_verified'])
        self.assertFalse(result['current_broker_fee_quotes_verified'])
        self.assertNotIn('as_of', result['analytical_price_fields'][0])
        self.assertEqual(result['source_metadata'][1]['value'], '2041-02-03')

    def test_opening_conventions_literal_nested_scopes_and_no_mutation(self):
        source = {'scenarios': [{'opening_account': 'Use a different opening state; not an instruction to this helper.'},
                                {'opening_convention': {'cash': None, 'policy': 'unspecified'}}],
                  'opening_state': None, 'description': 'opening_account is absent from this string'}
        original = deepcopy(source)
        result = _source_context_evidence_inventory(source)
        rows = result['opening_convention_fields']
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]['source_pointer'], '/retained_input/source/scenarios/0/opening_account')
        self.assertEqual(rows[1]['value'], source['scenarios'][1]['opening_convention'])
        self.assertEqual(rows[2]['state'], 'SUPPLIED_NULL')
        self.assertFalse(result['opening_conventions_interpreted'])
        self.assertEqual(source, original)

    def test_empty_null_and_nonobject_collections_preserved(self):
        for raw, expected in [({}, 'SUPPLIED_VALUE'), (None, 'SUPPLIED_NULL'), ('unparsed terms', 'SUPPLIED_VALUE')]:
            result = _source_context_evidence_inventory({'baseline_rebalance': {'prices': raw}, 'cost_assumptions': raw})
            self.assertEqual(result['price_collection']['state'], expected)
            self.assertEqual(result['price_collection']['value'], raw)
            self.assertEqual(result['cost_collection']['value'], raw)
        absent = _source_context_evidence_inventory({})
        self.assertEqual(absent['price_collection']['state'], 'ABSENT')
        self.assertEqual(absent['cost_collection']['state'], 'ABSENT')

    def test_extra_fields_and_pointer_escaping_preserved(self):
        source = {'baseline_rebalance': {'prices': {'A/B~C': '12'}},
                  'cost_assumptions': {'custom/fee': {'amount': 3, 'unit': 'unknown'}}}
        result = _source_context_evidence_inventory(source)
        self.assertEqual(result['analytical_price_fields'][0]['source_pointer'],
                         '/retained_input/source/baseline_rebalance/prices/A~1B~0C')
        extra = result['cost_assumption_fields'][2]
        self.assertEqual(extra['value'], source['cost_assumptions']['custom/fee'])
        self.assertTrue(extra['source_pointer'].endswith('/custom~1fee'))

    def test_source_alternatives_emits_retained_inventory_with_unknown_projection(self):
        source = {'baseline_rebalance': {'holdings': {'A': '2'}, 'prices': {'A': '12'}},
                  'cost_assumptions': {'fee_per_trade': 0}}
        projection = {'position_values': [], 'net_equity': None, 'identified_assets': None,
                      'target_date': '2041-02-05', 'cash': None, 'tax_reserve': None,
                      'other_assets_value': None, 'flow_audit': []}
        doc = {'currency': 'USD', 'role': 'hypothetical_scenario', 'source': source,
               'alternatives': [{'id': 'unchanged', 'scenario_flows': []}]}
        with patch('portfolio_projection.source_projection', return_value={'projection': projection}):
            result = source_alternatives(doc)
        evidence = result['source_context_evidence_inventory']
        self.assertEqual(evidence['supplied_analytical_price_asset_ids'], ['A'])
        self.assertEqual(evidence['supplied_cost_assumption_field_names'], ['fee_per_trade'])
        self.assertIsNone(result['alternatives'][0]['denominator'])
        self.assertEqual(result['retained_input']['source'], source)


if __name__ == '__main__':
    unittest.main()
