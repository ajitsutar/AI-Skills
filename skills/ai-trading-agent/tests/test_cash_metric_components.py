"""Cash identity is its formula/components, never accidental numeric equality."""
import copy
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from financial_alignment import owner_cash_bridge


def bridge():
    return {'currency': 'EUR', 'role': 'supplied_observation', 'amount_unit': 'EUR thousands',
            'period_start': '2028-01-01', 'period_end': '2028-12-31',
            'reported_cfo': 50, 'total_capex': 12, 'maintenance_capex': 7, 'growth_capex': 5,
            'sbc_added_back_in_cfo': 6, 'acquisition_cash_paid': 6,
            'working_capital_cfo_effect': -4, 'reported_net_income': 25}


class CashMetricTests(unittest.TestCase):
    def test_equal_values_have_distinct_components_and_combined_proxy(self):
        result = owner_cash_bridge(bridge()); ledger = result['cash_metrics']
        sbc = ledger['sbc_deducted_economic_proxy']; acquired = ledger['after_total_capex_and_acquisitions']
        self.assertEqual(Decimal(sbc['value']), Decimal(acquired['value']))
        self.assertNotEqual(sbc['components'], acquired['components'])
        both = ledger['sbc_and_acquisitions_deducted_economic_proxy']
        self.assertEqual(Decimal(both['value']), Decimal(26))
        self.assertEqual(both['classification'], 'economic_proxy')
        self.assertIn('not cash paid', both['interpretation'])
        self.assertEqual({r['input_field'] for r in both['components']},
                         {'reported_cfo', 'total_capex', 'sbc_added_back_in_cfo', 'acquisition_cash_paid'})

    def test_all_metrics_reconcile_and_preserve_inputs(self):
        doc = bridge(); doc['acquisition_cash_paid'] = 9; before = copy.deepcopy(doc)
        result = owner_cash_bridge(doc)
        for key, row in result['cash_metrics'].items():
            expected = sum(Decimal(c['coefficient']) * Decimal(c['value']) for c in row['components'])
            self.assertEqual(Decimal(row['value']), expected)
            self.assertEqual(Decimal(result[key]), expected)
            self.assertEqual(row['amount_unit'], 'EUR thousands')
            self.assertEqual(row['measurement_period']['end'], '2028-12-31')
        self.assertEqual(doc, before)
        self.assertEqual(result, owner_cash_bridge(doc))

    def test_unknown_is_not_zero_and_zero_is_computable(self):
        key = 'sbc_and_acquisitions_deducted_economic_proxy'
        for component in ('sbc_added_back_in_cfo', 'acquisition_cash_paid'):
            for missing in ('absent', 'null'):
                doc = bridge()
                if missing == 'absent': del doc[component]
                else: doc[component] = None
                result = owner_cash_bridge(doc)
                self.assertIsNone(result[key])
                self.assertEqual(result['cash_metrics'][key]['missing_components'], [component])
            doc = bridge(); doc[component] = 0
            result = owner_cash_bridge(doc)
            self.assertEqual(Decimal(result[key]), Decimal(32))
            self.assertEqual(result['cash_metrics'][key]['missing_components'], [])


if __name__ == '__main__':
    unittest.main()
