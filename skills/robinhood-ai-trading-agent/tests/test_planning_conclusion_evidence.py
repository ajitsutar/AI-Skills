"""Exhaustive conditional timing sets and lossless sizing threshold evidence."""
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_alignment import trade_costs
from planning_comparison import settlement_transfer_sweep


def timing(**extra):
    return dict(currency='USD', role='hypothetical_scenario',
                business_dates=['2038-02-02', '2038-02-04', '2038-02-08', '2038-02-11'],
                spendable_deadline='2038-02-11', settlement_lag=1, transfer_lag=1, **extra)


def sizing(price='3', needed='10', step='1'):
    return dict(currency='USD', role='hypothetical_scenario', side='sell', price=price,
                quantity='4', entry_orders=1, transaction_phase='exit', costs=[],
                required_net_proceeds=needed, quantity_step=step)


class ConclusionEvidenceTests(unittest.TestCase):
    def test_deadline_path_survives_next_path_missing_coverage(self):
        result = settlement_transfer_sweep(timing())
        summary = result['timing_summary']
        self.assertEqual(summary['sale_dates_with_any_conditional_arrival_on_or_before_deadline'],
                         ['2038-02-02', '2038-02-04'])
        groups = summary['paths_by_deadline_relation']
        self.assertEqual(len(groups['on_deadline']), 2)
        last = groups['on_deadline'][-1]
        self.assertEqual(last['sale_date'], '2038-02-04')
        self.assertEqual(last['path_id'], 'same_day_initiation')
        self.assertTrue(any(p['sale_date'] == last['sale_date'] for p in groups['unresolved_calendar']))
        self.assertFalse(summary['no_modeled_arrival_means_impossible'])
        self.assertEqual(summary['guaranteed_sale_dates'], [])
        # Every original path appears exactly once, with a resolvable pointer.
        pointers = []
        for records in groups.values():
            for record in records:
                pointer = record['result_pointer']; pointers.append(pointer)
                value = result
                for token in pointer.strip('/').split('/'):
                    value = value[int(token)] if isinstance(value, list) else value[token]
                self.assertEqual(value['id'], record['path_id'])
        self.assertEqual(len(set(pointers)), 8)

    def test_explicit_rejection_excludes_same_day_even_on_deadline(self):
        result = settlement_transfer_sweep(timing(same_day_transfer_assumption={
            'accepted': False, 'basis': 'Caller assumes settlement-day initiation unavailable.'}))
        summary = result['timing_summary']
        self.assertEqual(summary['sale_dates_with_any_conditional_arrival_on_or_before_deadline'], ['2038-02-02'])
        self.assertEqual(len(summary['paths_by_deadline_relation']['excluded_by_assumption']), 4)
        self.assertEqual(len(summary['paths_by_deadline_relation']['on_deadline']), 1)

    def test_after_deadline_is_distinct_from_missing_and_no_dates_is_valid(self):
        data = timing(); data['spendable_deadline'] = '2038-02-04'
        summary = settlement_transfer_sweep(data)['timing_summary']
        self.assertEqual(len(summary['paths_by_deadline_relation']['after_deadline']), 3)
        self.assertEqual(summary['sale_dates_with_any_conditional_arrival_on_or_before_deadline'], [])
        data['spendable_deadline'] = '2038-02-01'
        summary = settlement_transfer_sweep(data)['timing_summary']
        self.assertTrue(all(not rows for rows in summary['paths_by_deadline_relation'].values()))

    def test_recurring_threshold_is_not_an_exact_decimal(self):
        with localcontext() as context:
            context.prec = 12
            result = trade_costs(sizing())
        meta = result['proceeds_sizing_precision']
        self.assertEqual(Fraction(int(meta['threshold_quantity_numerator']),
                                  int(meta['threshold_quantity_denominator'])), Fraction(10, 3))
        self.assertFalse(meta['decimal_quantity_is_exact'])
        self.assertEqual(result['minimum_quantity_at_increment'], '4')
        self.assertEqual(result['sized_net_proceeds'], '12')
        self.assertLess(Decimal('3.333') * 3, 10)

    def test_terminating_zero_and_fractional_increment(self):
        for needed, expected in [('1', '0.25'), ('0', '0')]:
            result = trade_costs(sizing(price='4', needed=needed, step='.01'))
            self.assertTrue(result['proceeds_sizing_precision']['decimal_quantity_is_exact'])
            self.assertEqual(Decimal(result['minimum_quantity_at_increment']), Decimal(expected))
        result = trade_costs(sizing(step='.01'))
        self.assertEqual(result['minimum_quantity_at_increment'], '3.34')
        self.assertGreaterEqual(Decimal(result['sized_net_proceeds']), 10)


if __name__ == '__main__':
    unittest.main()
