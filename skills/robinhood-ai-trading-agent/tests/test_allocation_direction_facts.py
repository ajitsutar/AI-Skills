"""Semantic direction checks: weight changes do not imply target improvement."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_comparison import _allocation_direction_comparisons, source_alternatives


def row(name, weight, target='.30', denominator='100'):
    actual = Decimal(weight) if weight is not None else None
    goal = Decimal(target) if target is not None else None
    return {'id': name, 'target_date': '2038-06-01', 'denominator': denominator,
            'denominator_basis': 'same-target-date post-flow net equity',
            'allocations': [{'asset_id': 'asset', 'post_flow_weight': actual,
                             'target_weight': goal,
                             'target_drift': actual-goal if actual is not None and goal is not None else None,
                             'identified_assets_target_drift_sensitivity': Decimal('.01')}]}


class AllocationDirectionFactsTests(unittest.TestCase):
    def test_higher_weight_can_be_farther_or_closer(self):
        for weights, expected in [(('.28', '.25'), 'CLOSER'), (('.35', '.32'), 'FARTHER')]:
            pair = _allocation_direction_comparisons([row('left', weights[0]), row('right', weights[1])])['pairwise'][0]
            self.assertEqual(pair['left_weight_relative_to_right'], 'HIGHER')
            self.assertEqual(pair['left_target_distance_relative_to_right'], expected)

    def test_crossing_equal_distance_not_improvement(self):
        result = _allocation_direction_comparisons([row('left', '.35'), row('right', '.25')])
        self.assertEqual(result['pairwise'][0]['left_target_distance_relative_to_right'], 'EQUAL_DISTANCE')
        self.assertEqual([f['position_relative_to_target'] for f in result['allocation_facts']],
                         ['ABOVE_TARGET', 'BELOW_TARGET'])

    def test_primary_unknown_not_replaced_by_sensitivity(self):
        for denominator, weight in [(None, None), ('0', None), (None, '.25')]:
            result = _allocation_direction_comparisons([row('unknown', weight, denominator=denominator), row('known', '.28')])
            pair = result['pairwise'][0]
            self.assertEqual(pair['status'], 'UNRESOLVED')
            self.assertIsNone(pair['absolute_drift_delta_left_minus_right'])
            self.assertIsNone(pair['left_target_distance_relative_to_right'])

    def test_targets_or_dates_must_match_but_denominator_amounts_may_differ(self):
        left, right = row('a', '.28', denominator='90'), row('b', '.25', denominator='100')
        self.assertEqual(_allocation_direction_comparisons([left, right])['pairwise'][0]['status'], 'COMPUTED')
        right['allocations'][0]['target_weight'] = Decimal('.20')
        self.assertEqual(_allocation_direction_comparisons([left, right])['pairwise'][0]['status'], 'INCOMPARABLE')
        right = row('b', '.25')
        right['target_date'] = '2038-06-02'
        self.assertEqual(_allocation_direction_comparisons([left, right])['pairwise'][0]['status'], 'INCOMPARABLE')

    def test_all_pairs_no_implicit_baseline_rank_and_exact_decimal(self):
        rows = [row('a', '.300000000000000000000000001'), row('b', '.30'), row('c', '.25')]
        original = deepcopy(rows)
        result = _allocation_direction_comparisons(rows)
        self.assertEqual(len(result['pairwise']), 3)
        self.assertEqual(result['pairwise'][0]['left_target_distance_relative_to_right'], 'FARTHER')
        self.assertFalse(result['closest_alternative_rank_computed'])
        self.assertIsNone(result['default_baseline_alternative'])
        self.assertEqual(rows, original)
        reverse = _allocation_direction_comparisons(list(reversed(rows)))
        self.assertEqual(reverse['pairwise'][-1]['left_target_distance_relative_to_right'], 'CLOSER')

    def test_source_operation_serializes_facts_and_points_to_own_operands(self):
        def projection(bound):
            value = bound['scenario_flows'][0]['value']
            return {'projection': {'position_values': [{'asset_id': 'asset', 'market_value': value}],
                                   'net_equity': '100', 'identified_assets': '100', 'target_date': '2038-06-01',
                                   'cash': '70', 'tax_reserve': '0', 'other_assets_value': '0'}}
        doc = {'currency': 'USD', 'role': 'hypothetical_scenario',
               'source': {'baseline_rebalance': {'targets': {'asset': '.30'}}},
               'alternatives': [{'id': 'a', 'scenario_flows': [{'value': '28'}]},
                                {'id': 'b', 'scenario_flows': [{'value': '25'}]}]}
        with patch('portfolio_projection.source_projection', side_effect=projection):
            result = source_alternatives(doc)
        pair = result['allocation_direction_comparisons']['pairwise'][0]
        self.assertEqual(pair['absolute_drift_delta_left_minus_right'], '-0.03')
        for index, operand in enumerate(pair['operands']):
            self.assertEqual(operand['allocation_pointer'], f'/alternatives/{index}/allocations/0')
            self.assertEqual(operand['signed_drift'], result['alternatives'][index]['allocations'][0]['target_drift'])
        self.assertIsNone(result['selected_alternative'])


if __name__ == '__main__':
    unittest.main()
