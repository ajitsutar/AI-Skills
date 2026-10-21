"""Coverage is a sample inventory, not an exclusive funding conclusion."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_comparison import _alternative_coverage_audit, source_alternatives


def trade(asset, quantity, side='sell', ident='trade'):
    return {'id': ident, 'kind': 'trade', 'asset_id': asset, 'date': '2039-04-03',
            'state': 'hypothetical', 'trade': {'side': side, 'quantity': quantity}}


def fixture(flow_sets, holdings=None, included=True):
    doc = {'currency': 'USD', 'role': 'hypothetical_scenario',
           'source': {'baseline_rebalance': {'holdings': holdings or {'A': '20', 'B': '20', 'C': '20'}}},
           'alternatives': [{'id': str(i), 'scenario_flows': flows} for i, flows in enumerate(flow_sets)]}
    rows = [{'projection_receipt': {'projection': {'flow_audit': [
        {'id': flow['id'], 'included': included, 'exclusion_reasons': [] if included else ['STATE_NOT_INCLUDED']}
        for flow in flows]}}} for flows in flow_sets]
    return doc, rows


class AlternativeCoverageAuditTests(unittest.TestCase):
    def test_asymmetric_quantities_and_omitted_held_assets(self):
        doc, rows = fixture([[trade('A', '2')], [trade('A', '4')], [trade('B', '2')]])
        original = deepcopy(doc)
        result = _alternative_coverage_audit(doc, rows)
        self.assertEqual(result['omitted_held_asset_ids'], ['C'])
        four = result['sale_quantity_sample_groups'][1]
        self.assertEqual(four['sampled_source_held_asset_ids'], ['A'])
        self.assertEqual(four['source_held_asset_ids_without_this_known_sample'], ['B', 'C'])
        self.assertTrue(result['asymmetric_known_quantity_samples'])
        self.assertFalse(result['exclusive_feasible_funder_claim_supported'])
        self.assertEqual(doc, original)

    def test_buy_and_multi_trade_scenarios_do_not_become_independent_funders(self):
        flows = [trade('A', '2', ident='sell1'), trade('A', '3', ident='sell2'),
                 trade('A', '7', side='buy', ident='buy'), trade('B', '4', ident='other')]
        doc, rows = fixture([flows])
        result = _alternative_coverage_audit(doc, rows)
        totals = result['per_alternative_asset_sale_totals']
        self.assertEqual(totals[0]['total_sale_quantity'], Decimal('5'))
        self.assertEqual(result['known_positive_sale_quantities_by_asset'][0]['quantities'],
                         [Decimal('2'), Decimal('3')])
        self.assertEqual(len(result['trade_observations']), 4)
        self.assertFalse(result['exclusive_feasible_funder_claim_supported'])

    def test_unknown_quantity_is_retained_not_zero_or_known_sample(self):
        doc, rows = fixture([[trade('A', None), trade('A', '2', ident='known')]])
        result = _alternative_coverage_audit(doc, rows)
        self.assertIsNone(result['per_alternative_asset_sale_totals'][0]['total_sale_quantity'])
        self.assertEqual(result['per_alternative_asset_sale_totals'][0]['known_quantity_sum'], Decimal('2'))
        self.assertEqual(len(result['unknown_quantity_sale_samples']), 1)
        self.assertEqual(result['unknown_quantity_sale_samples'][0]['asset_id'], 'A')

    def test_excluded_flows_zero_holdings_and_unknown_holdings(self):
        doc, rows = fixture([[trade('A', '2')]], {'A': '20', 'B': None, 'Z': '0'}, included=False)
        result = _alternative_coverage_audit(doc, rows)
        self.assertEqual(result['omitted_held_asset_ids'], ['A'])
        self.assertEqual(result['unknown_opening_quantity_asset_ids'], ['B'])
        self.assertEqual(result['zero_opening_quantity_asset_ids'], ['Z'])
        self.assertEqual(result['known_positive_sale_quantities_by_asset'], [])
        self.assertFalse(result['trade_observations'][0]['included_in_projection'])

    def test_symmetric_samples_still_not_exhaustive_or_feasible(self):
        doc, rows = fixture([[trade(asset, '2')] for asset in ['A', 'B', 'C']])
        result = _alternative_coverage_audit(doc, rows)
        self.assertFalse(result['asymmetric_known_quantity_samples'])
        self.assertEqual(result['omitted_held_asset_ids'], [])
        self.assertFalse(result['full_asset_quantity_search_established'])
        self.assertFalse(result['sale_quantity_sample_groups'][0]['economic_equivalence_established'])

    def test_source_result_wiring_and_pointer_scopes(self):
        doc, rows = fixture([[trade('A', '2')]])
        projection = {**rows[0]['projection_receipt']['projection'], 'position_values': [],
                      'net_equity': None, 'identified_assets': '100', 'target_date': '2039-04-04',
                      'cash': '100', 'tax_reserve': None, 'other_assets_value': None}
        with patch('portfolio_projection.source_projection', return_value={'projection': projection}):
            result = source_alternatives(doc)
        observation = result['alternative_coverage_audit']['trade_observations'][0]
        self.assertEqual(observation['input_pointer'], '/retained_input/alternatives/0/scenario_flows/0')
        self.assertEqual(observation['projection_audit_pointer'], '/alternatives/0/projection_receipt/projection/flow_audit/0')
        self.assertFalse(observation['lot_selection_established_by_audit'])
        self.assertIsNone(result['selected_alternative'])


if __name__ == '__main__':
    unittest.main()
