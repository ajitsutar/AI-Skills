import copy
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import financial_alignment
import terminal_objectives
from test_terminal_capital_boundary import document


class TerminalObjectiveProjectionTests(unittest.TestCase):
    def projection(self, source):
        result = financial_alignment.terminal_scenarios(source)
        return result['diagnostic_objectives']

    def test_weak_row_positive_probe_is_named_zero_return_not_dcf(self):
        source = document()
        source['scenarios'][0].update(annual_revenue_growth='0', terminal_ebit_margin='.07',
                                      net_debt_at_exit=44, annual_dilution='.04')
        frozen = copy.deepcopy(source)
        result = self.projection(source)
        self.assertFalse(result['rows'][0]['met'])
        probe = result['derived_probes'][0]
        self.assertTrue(probe['met'])
        self.assertGreater(Decimal(probe['net_total_return_fraction']), 0)
        self.assertEqual(probe['held_assumptions']['scenario']['terminal_ebit_margin'], '.07')
        self.assertEqual(probe['objective_id'], 'AFTER_COST_CAPITAL_PRESERVATION')
        self.assertFalse(result['user_objective_inferred'])
        self.assertFalse(result['general_joint_conditions_established'])
        self.assertEqual(result['dcf_discount_closure']['status'], 'UNAVAILABLE_DCF_MODEL_NOT_EVALUATED')
        self.assertEqual(source, frozen)

    def test_unattainable_probe_not_promoted_to_success(self):
        source = document()
        source['equity_value_floor_zero'] = True
        source['scenarios'][0].update(terminal_ebit_margin=0, cumulative_dividends_per_share=0)
        result = self.projection(source)
        self.assertFalse(result['derived_probes'][0]['met'])

    def test_missing_investable_price_remains_unavailable(self):
        source = document()
        source['equity_value_floor_zero'] = False
        source['scenarios'][0].update(terminal_ebit_margin=0, net_debt_at_exit=50)
        result = self.projection(source)
        self.assertIsNone(result['rows'][0]['met'])
        self.assertIsNone(result['rows'][0]['net_total_return_fraction'])
        self.assertEqual(result['derived_probes'], [])

    def test_sensitivity_and_original_row_are_separate(self):
        source = document()
        source['sensitivities'] = [{'id': 'lower', 'base_scenario_id': 'moderate',
                                   'overrides': {'exit_ev_to_ebit': 1}}]
        result = self.projection(source)
        self.assertEqual([(r['id'],r['kind']) for r in result['rows']],
                         [('moderate','supplied_scenario'),('lower','declared_sensitivity')])
        self.assertEqual(len(result['derived_probes']), 2)


if __name__ == '__main__':
    unittest.main()
