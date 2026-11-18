"""Independent finite-poset and metamorphic checks; no copied implementation oracle."""
import copy
import itertools
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_comparison import alternative_comparison, settlement_transfer_paths


def base(**fields):
    return dict(currency='USD', role='hypothetical_scenario', **fields)


def grid():
    return base(criteria=[dict(id='x', metric='cost', unit='USD', basis='scenario', direction='minimize'),
                          dict(id='y', metric='benefit', unit='points', basis='scenario', direction='maximize')],
                alternatives=[dict(id=f'{x},{y}', values=dict(x=x, y=y))
                              for x, y in itertools.product(range(3), repeat=2)])


class IndependentComparisonTests(unittest.TestCase):
    def test_finite_product_order_has_unique_extreme_and_correct_edge_count(self):
        # A 3x3 product order has one maximal point and 27 strictly ordered pairs:
        # 6*6 coordinate-wise comparable choices minus 9 reflexive choices.
        result = alternative_comparison(grid())
        self.assertEqual(result['non_dominated_ids'], ['0,2'])
        self.assertEqual(len(result['dominated_ids']), 8)
        self.assertEqual(sum(p['dominant_id'] is not None for p in result['pairwise']), 27)
        self.assertEqual(sum(p['relation'] == 'TRADEOFF' for p in result['pairwise']), 9)
        self.assertIsNone(result['selected_alternative'])

    def test_cloning_extreme_and_unknown_extension_do_not_choose_a_winner(self):
        data = grid()
        data['alternatives'].append(dict(id='clone', values=dict(x=0, y=2)))
        out = alternative_comparison(data)
        self.assertEqual(set(out['non_dominated_ids']), {'0,2', 'clone'})
        data['alternatives'].append(dict(id='unknown', values=dict(x=-100, y=None)))
        out = alternative_comparison(data)
        self.assertEqual(out['non_dominated_ids'], [])
        self.assertEqual(set(out['indeterminate_ids']), {'0,2', 'clone', 'unknown'})
        self.assertEqual(len(out['dominated_ids']), 8)
        self.assertIsNone(out['selected_alternative'])

    def test_source_permutation_preserves_directed_dominance_graph(self):
        def graph(out):
            return {(p['dominant_id'], p['right_id'] if p['dominant_id'] == p['left_id'] else p['left_id'])
                    for p in out['pairwise'] if p['dominant_id'] is not None}
        data = grid(); first = alternative_comparison(data)
        data['alternatives'] = data['alternatives'][3:] + data['alternatives'][:3]
        data['criteria'].reverse()
        second = alternative_comparison(data)
        self.assertEqual(graph(first), graph(second))
        self.assertEqual([x['id'] for x in second['alternatives']], [x['id'] for x in data['alternatives']])

    def test_incomparable_metric_on_extreme_never_reduces_to_known_objective(self):
        for dimension in ['metric', 'unit', 'basis']:
            data = grid()
            top = next(a for a in data['alternatives'] if a['id'] == '0,2')
            top['values']['y'] = dict(value=2, metric='benefit', unit='points', basis='scenario')
            top['values']['y'][dimension] = 'different'
            out = alternative_comparison(data)
            for pair in out['pairwise']:
                if '0,2' in [pair['left_id'], pair['right_id']]:
                    self.assertEqual(pair['relation'], 'INDETERMINATE')
                    self.assertIsNone(pair['dominant_id'])

    def test_documented_plural_criterion_weights_rejected(self):
        data = grid(); data['criteria'][0]['weights'] = {'high': 1}
        with self.assertRaises(ValueError):
            alternative_comparison(data)


class IndependentDateTests(unittest.TestCase):
    def scenario(self):
        return base(business_dates=['2040-01-02', '2040-01-03', '2040-02-29', '2040-09-01', '2041-01-01'],
                    sale_date='2040-01-03', settlement_lag=0, transfer_lag=0,
                    spendable_deadline='2040-02-29')

    def test_zero_identity_and_settlement_transfer_composition(self):
        # Settlement and transfer lag composition must agree at arrival, but
        # reallocating lag between them must preserve the distinct initiation.
        zero = settlement_transfer_paths(self.scenario())['paths'][0]
        self.assertEqual(zero['settlement_date'], '2040-01-03')
        self.assertEqual(zero['transfer_initiation_date'], '2040-01-03')
        self.assertEqual(zero['arrival_date'], '2040-01-03')
        paths = []
        for settlement, transfer in [(0, 2), (1, 1), (2, 0)]:
            data = self.scenario(); data.update(settlement_lag=settlement, transfer_lag=transfer)
            paths.append(settlement_transfer_paths(data)['paths'][0])
        self.assertEqual({p['arrival_date'] for p in paths}, {'2040-09-01'})
        self.assertEqual(len({p['transfer_initiation_date'] for p in paths}), 3)

    def test_truncation_removes_only_uncovered_events_and_extension_is_stable(self):
        full = self.scenario(); full.update(settlement_lag=1, transfer_lag=1)
        complete = settlement_transfer_paths(full)
        for n in range(2, 6):
            shorter = copy.deepcopy(full); shorter['business_dates'] = full['business_dates'][:n]
            out = settlement_transfer_paths(shorter)
            self.assertFalse(out['calendar_extended'])
            for actual, expected in zip(out['paths'], complete['paths']):
                for field in ['settlement_date', 'transfer_initiation_date', 'arrival_date']:
                    self.assertEqual(actual[field], expected[field] if expected[field] in shorter['business_dates'] else None)
                if actual['arrival_date'] is None:
                    self.assertIsNone(actual['date_relation_to_deadline'])

    def test_assumptions_change_feasibility_not_arithmetic_or_deadline_guarantees(self):
        data = self.scenario(); data.update(transfer_lag=1)
        outcomes = []
        for accepted in [None, True, False]:
            sample = copy.deepcopy(data)
            if accepted is not None:
                sample['same_day_transfer_assumption'] = dict(accepted=accepted, basis='scenario')
            outcomes.append(settlement_transfer_paths(sample))
        self.assertEqual({o['paths'][0]['arrival_date'] for o in outcomes}, {'2040-02-29'})
        self.assertEqual(len({o['paths'][0]['status'] for o in outcomes}), 3)
        for out in outcomes:
            self.assertEqual(out['paths'][0]['date_relation_to_deadline'], 'ON_DEADLINE_DATE_INTRADAY_UNRESOLVED')
            self.assertFalse(any(p['guaranteed_spendable_by_deadline'] for p in out['paths']))


if __name__ == '__main__':
    unittest.main()
