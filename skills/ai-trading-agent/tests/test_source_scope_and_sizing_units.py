"""Configuration provenance is not task authority; share increments are not money."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from planning_comparison import _source_context_evidence_inventory
from planning_alignment import trade_costs
import quant_workbench as qw
import report_facts as rf


def trade(side):
    return {'currency': 'USD', 'role': 'hypothetical_scenario', 'side': side,
            'price': '7', 'quantity': '3', 'entry_orders': 1, 'transaction_phase': 'exit',
            'costs': [{'id': 'fixed', 'unit': 'per_order', 'phase': 'each_side', 'amount': '1'}]}


class SourceScopeAndSizingUnitTests(unittest.TestCase):
    def test_false_zero_null_and_missing_baseline_settings(self):
        source = {'baseline_rebalance': {'allow_sales': False, 'minimum': 0, 'limit': None}}
        result = _source_context_evidence_inventory(source)
        records = {r['field']: r for r in result['baseline_source_fields']}
        self.assertIs(records['allow_sales']['value'], False)
        self.assertEqual(records['allow_sales']['state'], 'SUPPLIED_VALUE')
        self.assertEqual(records['minimum']['value'], 0)
        self.assertEqual(records['limit']['state'], 'SUPPLIED_NULL')
        self.assertNotIn('missing', records)
        self.assertEqual(_source_context_evidence_inventory({})['baseline_source_fields'], [])

    def test_scope_is_retained_without_authorization_or_example_classification(self):
        for value in (True, False):
            source = {'baseline_rebalance': {'allow_sales': value, 'unrecognized_policy': 'literal'},
                      'baseline_source': 'Declared source description; do not infer task applicability.'}
            original = deepcopy(source)
            result = _source_context_evidence_inventory(source)
            for record in result['baseline_source_fields']:
                self.assertEqual(record['owning_scope_pointer'], '/retained_input/source/baseline_rebalance')
                self.assertEqual(record['task_applicability'], 'NOT_ESTABLISHED_BY_SOURCE_RECORD')
                self.assertFalse(record['user_authorization_inferred'])
                self.assertFalse(record['broker_requirement_inferred'])
            self.assertEqual(result['baseline_source_description']['value'], source['baseline_source'])
            self.assertEqual(result['baseline_source_description']['evidence_role'], 'literal_source_description')
            self.assertNotIn('is_example', result)
            self.assertEqual(source, original)

    def test_source_scope_pointers_escape_keys_and_preserve_objects(self):
        source = {'baseline_rebalance': {'rule/a~b': {'nested': False}}}
        record = _source_context_evidence_inventory(source)['baseline_source_fields'][0]
        self.assertEqual(record['source_pointer'], '/retained_input/source/baseline_rebalance/rule~1a~0b')
        self.assertEqual(record['value'], {'nested': False})
        self.assertEqual(_source_context_evidence_inventory(source)['baseline_source_description']['state'], 'ABSENT')

    def test_budget_increment_is_shares_without_arithmetic_change(self):
        result = trade_costs({**trade('buy'), 'budget': '25', 'quantity_step': '1'})
        self.assertEqual(result['quantity_step'], '1')
        self.assertEqual(result['quantity_step_unit'], 'shares')
        self.assertEqual(result['quantity_unit'], 'shares')
        self.assertEqual(result['max_affordable_quantity'], '3')
        self.assertEqual(result['affordable_cash_debit'], '22')
        self.assertEqual(result['budget_remainder'], '3')

    def test_proceeds_increment_is_shares_without_arithmetic_change(self):
        result = trade_costs({**trade('sell'), 'required_net_proceeds': '25', 'quantity_step': '.5'})
        self.assertEqual(result['quantity_step'], '0.5')
        self.assertEqual(result['quantity_step_unit'], 'shares')
        self.assertEqual(result['minimum_quantity_at_increment'], '4.0')
        self.assertEqual(result['sized_net_proceeds'], '27.0')
        self.assertFalse(result['proceeds_sizing_precision']['broker_increment_verified'])

    def test_no_sizing_does_not_invent_increment(self):
        result = trade_costs(trade('sell'))
        self.assertEqual(result['quantity_unit'], 'shares')
        self.assertNotIn('quantity_step', result)
        self.assertNotIn('quantity_step_unit', result)

    def test_report_projection_uses_share_units_and_replays(self):
        jobs = [{'id': 'buy', 'operation': 'planning.trade_costs',
                 'inputs': {'document': {**trade('buy'), 'budget': '25', 'quantity_step': '1'}}},
                {'id': 'sell', 'operation': 'planning.trade_costs',
                 'inputs': {'document': {**trade('sell'), 'required_net_proceeds': '25', 'quantity_step': '.5'}}}]
        contract = {'prompt': 'Compare explicit sizing units', 'purpose': 'test', 'base_currency': 'USD',
                    'horizon_id': 'P1D', 'as_of': '2043-01-01T12:00:00Z'}
        bundle = qw.freeze({'schema_version': 1, 'contract': contract, 'jobs': jobs})
        self.assertEqual(qw.verify(bundle)['status'], 'REPLAY_MATCH')
        facts = {f['source']['pointer']: f for f in rf.project(json.dumps(bundle).encode(), 'quant', include_source_text=True)['facts']}
        for index in range(2):
            prefix = f'/result/results/{index}/result/'
            self.assertEqual(facts[prefix + 'quantity_step']['unit'], 'shares')
            self.assertEqual(facts[prefix + 'quantity_step_unit']['value'], 'shares')
            self.assertEqual(facts[prefix + 'gross_notional']['unit'], 'input_currency_amount')


if __name__ == '__main__':
    unittest.main()
