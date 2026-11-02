"""Adversarial semantic projections from original synthetic trade scenarios."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import answer_facts
import research_workflow as workflow


def trade_request(side='buy'):
    document = {'currency': 'USD', 'role': 'hypothetical_scenario', 'side': side,
                'price': '37.20', 'quantity': '3.125', 'entry_orders': 1,
                'costs': [{'id': 'sale_net_proceeds = misleading caption', 'unit': 'per_share',
                           'phase': 'each_side', 'amount': '0.04'},
                          {'id': 'fee', 'unit': 'per_order', 'phase': 'each_side', 'amount': '0.25'}]}
    if side == 'buy':
        document.update(budget='115', quantity_step='0.001', exit_price='35.00', exit_orders=1)
    else:
        document.update(transaction_phase='exit', required_net_proceeds='120', quantity_step='0.001')
    return {'schema_version': 1, 'contract': {'prompt': 'Synthetic trade arithmetic', 'purpose': 'offline synthetic test',
            'base_currency': 'USD', 'horizon_id': 'P1Y', 'as_of': '2030-01-01T00:00:00Z'},
            'jobs': [{'id': 'trade', 'operation': 'planning.trade_costs', 'inputs': {'document': document}}],
            'requirements': [{'id': 'costs', 'question': 'Compute supplied trade costs',
                              'job_ids': ['trade'], 'expected_operations': ['planning.trade_costs']}]}


class AnswerFactsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='answer-facts-')
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)

    def project(self, document=None):
        source = self.directory / 'request.json'
        source.write_bytes(workflow.encode(document or trade_request()))
        workflow.prepare(source, self.directory / 'prepared', 'Synthetic test inputs')
        workflow.run(self.directory / 'prepared/plan.json', self.directory / 'run')
        return answer_facts.project_verified(self.directory / 'run')

    def test_fixed_semantics_keep_aggregate_cost_rate_and_scenarios_separate(self):
        facts = self.project()
        by_field = {f['source']['pointer'].rsplit('/', 1)[-1]: f for f in facts['facts']
                    if '/cost_records/' not in f['source']['pointer']}
        total = next(f for f in facts['facts'] if f['semantic_label'] == 'aggregate transaction cost')
        rate = next(f for f in facts['facts'] if f['semantic_label'] == 'cost per share')
        self.assertEqual(total['value'], '0.37500')
        self.assertEqual(total['unit'], 'USD')
        self.assertEqual(rate['value'], '0.04')
        self.assertEqual(rate['unit'], 'USD_per_share')
        self.assertFalse(rate['is_aggregate_cost'])
        self.assertNotIn('sale_net_proceeds = misleading caption', rate['sentence'])
        self.assertEqual(by_field['entry_cash_debit']['scenario'], 'selected_order')
        self.assertEqual(by_field['budget_remainder']['scenario'], 'maximum_affordable_order')
        self.assertNotEqual(by_field['entry_cash_debit']['value'], by_field['affordable_cash_debit']['value'])
        self.assertEqual(by_field['sale_net_proceeds']['status'], 'UNAVAILABLE_NULL')
        self.assertFalse(facts['whole_answer_pass'])
        self.assertTrue(all(f['input_bindings'] and f['source']['sha256'] for f in facts['facts']))

    def test_net_sale_proceeds_cannot_be_replaced_by_costs_or_custom_caption(self):
        facts = self.project(trade_request('sell'))
        total = next(f for f in facts['facts'] if f['semantic_label'] == 'aggregate transaction cost')
        proceeds = next(f for f in facts['facts'] if f['semantic_label'] == 'sale net proceeds after costs'
                        and f['scenario'] == 'selected_order')
        self.assertEqual(proceeds['value'], '115.87500')
        for field, replacement in [('semantic_label', 'aggregate transaction cost'),
                                   ('value', total['value']), ('unit', 'USD_per_share'),
                                   ('scenario', 'maximum_affordable_order')]:
            changed = copy.deepcopy(facts)
            index = facts['facts'].index(proceeds)
            changed['facts'][index][field] = replacement
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'FIXED_ANSWER_FACTS_MISMATCH'):
                answer_facts.verify_projection(self.directory / 'run', workflow.encode(changed))
        self.assertEqual(answer_facts.verify_projection(self.directory / 'run', workflow.encode(facts))['status'],
                         'FIXED_ANSWER_FACTS_MATCH')

    def test_tampered_result_values_rejected_before_fact_generation(self):
        self.project()
        path = self.directory / 'run/result.json'
        result = workflow.read_result(path.read_bytes())
        result['jobs'][0]['result']['exit_net_proceeds'] = result['jobs'][0]['result']['exit_cost']
        path.write_bytes(workflow.encode(result))
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH_MISMATCH'):
            answer_facts.project_verified(self.directory / 'run')

    def test_failed_job_never_projects_caller_supplied_amounts(self):
        request = trade_request()
        request['jobs'][0]['inputs']['document']['quantity'] = '-1'
        facts = self.project(request)
        self.assertEqual(facts['facts'], [])
        self.assertEqual(facts['jobs'][0]['projection_status'], 'UNAVAILABLE_JOB_NOT_COMPUTED')

    def test_unknown_operation_mapping_and_declared_units_remain_unavailable(self):
        request = trade_request()
        request['jobs'] = [{'id': 'statistic', 'operation': 'validation.holm',
                            'inputs': {'p_values': {'a': .01}}}]
        request['requirements'][0]['job_ids'] = ['statistic']
        request['requirements'][0]['expected_operations'] = ['validation.holm']
        facts = self.project(request)
        self.assertEqual(facts['facts'], [])
        self.assertEqual(facts['jobs'][0]['projection_status'], 'UNAVAILABLE_OPERATION_MAPPING')

    def test_bps_parameter_keeps_basis_points_instead_of_currency(self):
        request = trade_request()
        request['jobs'][0]['inputs']['document']['costs'] = [
            {'id': 'bps', 'unit': 'bps_notional', 'phase': 'each_side', 'amount': '5'}]
        facts = self.project(request)
        rate = next(f for f in facts['facts'] if f['semantic_label'] == 'cost rate on notional')
        self.assertEqual(rate['unit'], 'basis_points_of_notional')
        self.assertEqual(rate['value'], '5')
        total = next(f for f in facts['facts'] if f['semantic_label'] == 'aggregate transaction cost')
        self.assertEqual(total['unit'], 'USD')
        self.assertNotEqual(total['value'], rate['value'])


if __name__ == '__main__':
    unittest.main()
