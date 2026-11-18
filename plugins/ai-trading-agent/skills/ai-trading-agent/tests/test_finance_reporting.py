"""Fixed portfolio/holdings semantics through retained canonical report replay."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import answer_facts
import holdings_ledger
import quant_portfolio
import quant_report
import quant_workbench
import report_facts
import research_workflow
from test_portfolio_borrow_accounting import allocation, job
from test_holdings_ledger import base, event, T2, T3


def ledger_document():
    document = base()
    document['as_of'] = T2
    document['opening']['tax_liability'] = '7'
    document['events'] = [event('sell', security_id='P', quantity='1', price='100', cost='1',
                                lots=['a'], execution_price_basis='observed', settles_at=T3)]
    return document


def request():
    model = allocation('robust_return')
    model['assets'][0].update(one_way_cost=.002, impact_coefficient=.0001)
    model['scenarios'][0]['name'] = 'flat/~scenario'
    document = job(model)
    document['jobs'].append({'id': 'holdings', 'operation': 'backtest.holdings_ledger',
                             'inputs': {'document': ledger_document()}})
    document['requirements'] = [{'id': 'research', 'question': 'Reconcile the supplied scenario amounts',
                                 'job_ids': ['allocation', 'holdings'],
                                 'expected_operations': ['portfolio.construct', 'backtest.holdings_ledger']}]
    return document


def by_pointer(fields):
    return {field['pointer']: field for field in fields}


class NativeFinanceFieldsTests(unittest.TestCase):
    def test_portfolio_units_costs_and_timing_reconcile_to_native_values(self):
        value = quant_portfolio.construct(request()['jobs'][0]['inputs']['document'])
        fields = by_pointer(report_facts.native_finance_fields('portfolio.construct', value))
        for path, field in fields.items():
            self.assertEqual(field['value'], report_facts.pointer(value, path))
            self.assertEqual(field['unit'], 'fraction_of_initial_nav')
            self.assertEqual(field['denominator'], 'initial portfolio NAV')
            self.assertIsNone(field['measurement_period'])
        self.assertAlmostEqual(value['estimated_cost_fraction'], value['entry_transaction_cost_fraction'] + value['holding_period_borrow_cost_fraction'])
        self.assertAlmostEqual(value['modeled_net_return'], value['modeled_return'] - value['estimated_cost_fraction'])
        self.assertAlmostEqual(value['scenario_pnl_fraction']['flat/~scenario'], -value['estimated_cost_fraction'])
        self.assertIn('not assumed paid at entry', fields['/holding_period_borrow_cost_fraction']['basis'])
        self.assertIn('excludes period borrow', fields['/cash_after_modeled_cost']['basis'])
        self.assertIn('not profit', fields['/free_cash_after_collateral_and_borrow_reserve']['basis'])
        self.assertIn('/scenario_pnl_fraction/flat~1~0scenario', fields)

    def test_existing_short_zero_borrow_all_long_and_minimum_risk_controls(self):
        for objective in ('minimum_risk', 'robust_return'):
            for control in ('existing-short', 'zero-borrow', 'all-long'):
                document = allocation(objective)
                if control == 'existing-short': document['assets'][0]['previous_weight'] = -.5
                if control == 'zero-borrow': document['assets'][0]['borrow_cost_per_period'] = 0
                if control == 'all-long':
                    document['assets'][0].update(min_weight=0, max_weight=.5)
                    document['constraints']['net_target'] = .5
                result = quant_portfolio.construct(document)
                fields = by_pointer(report_facts.native_finance_fields('portfolio.construct', result))
                with self.subTest(objective=objective, control=control):
                    self.assertEqual(fields['/holding_period_borrow_cost_fraction']['value'], result['holding_period_borrow_cost_fraction'])
                    self.assertEqual(fields['/modeled_net_return']['missingness'], 'null' if objective == 'minimum_risk' else None)
                    if control == 'existing-short': self.assertAlmostEqual(fields['/holding_period_borrow_cost_fraction']['value'], .01)
                    else: self.assertEqual(fields['/holding_period_borrow_cost_fraction']['value'], 0)

    def test_holdings_amounts_receivables_basis_and_unknown_tax_remain_distinct(self):
        value = holdings_ledger.replay(ledger_document())
        fields = by_pointer(report_facts.native_finance_fields('backtest.holdings_ledger', value))
        for path, field in fields.items():
            self.assertEqual(field['value'], report_facts.pointer(value, path))
            self.assertIsNone(field['measurement_period'])
            self.assertIsNone(field['observation_frequency'])
        self.assertEqual(fields['/final/settled_cash']['value'], '100')
        self.assertEqual(fields['/final/cash_receivables']['value'], '99')
        self.assertEqual(fields['/final/cash_available_after_tax_reserve']['value'], '93')
        self.assertEqual(fields['/lots/0/basis']['value'], '450')
        self.assertEqual(fields['/realizations/0/realized_gain']['value'], '49')
        self.assertEqual(fields['/final/settled_cash']['unit'], 'USD')
        self.assertEqual(fields['/lots/0/quantity']['unit'], 'security_units')
        for path in ('/tax_evidence/actual_tax_liability_amount', '/tax_evidence/total_scenario_liability_remaining', '/final/net_nav_after_declared_tax'):
            self.assertIsNone(fields[path]['value'])
            self.assertEqual(fields[path]['missingness'], 'null')

    def test_unknown_marks_basis_currency_and_absent_fields_are_not_zero(self):
        document = ledger_document()
        document['opening']['marks'] = []
        document['opening']['lots'][0]['basis'] = None
        # The sale supplies its own mark; a later split invalidates that mark.
        document['events'].append(event('split', security_id='P', factor='2'))
        value = holdings_ledger.replay(document)
        original = copy.deepcopy(value)
        fields = by_pointer(report_facts.native_finance_fields('backtest.holdings_ledger', value))
        self.assertEqual(value, original)
        for path in ('/final/gross_nav', '/final/positions/P/value', '/lots/0/basis', '/realizations/0/realized_gain'):
            self.assertIsNone(fields[path]['value'])
        del value['final']['cash_available_after_tax_reserve']
        del value['tax_evidence']['actual_tax_liability_amount']
        value['currency'] = 'unspecified'
        fields = by_pointer(report_facts.native_finance_fields('backtest.holdings_ledger', value))
        self.assertEqual(fields['/final/cash_available_after_tax_reserve']['missingness'], 'absent')
        self.assertEqual(fields['/tax_evidence/actual_tax_liability_amount']['missingness'], 'absent')
        self.assertIsNone(fields['/final/settled_cash']['unit'])
        self.assertEqual(fields['/final/settled_cash']['missingness'], 'unknown_currency')

    def test_malformed_numeric_and_mismatched_operation_never_gain_semantics(self):
        value = quant_portfolio.construct(allocation())
        for malformed in (True, 'not a number', 'NaN', float('inf')):
            changed = copy.deepcopy(value); changed['estimated_cost_fraction'] = malformed
            fact = by_pointer(report_facts.native_finance_fields('portfolio.construct', changed))['/estimated_cost_fraction']
            self.assertIsNone(fact['value']); self.assertEqual(fact['missingness'], 'invalid_type_or_value')
        self.assertIsNone(report_facts.native_finance_fields('backtest.holdings_ledger', value))
        self.assertIsNone(report_facts.native_finance_fields('unknown.operation', value))
        value['cost_accounting']['units'] = 'USD'
        self.assertIsNone(report_facts.native_finance_fields('portfolio.construct', value))
        self.assertIsNone(report_facts.native_finance_fields('portfolio.construct', quant_portfolio.construct(allocation(cap=.005))))


class RetainedFinanceReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='finance-report-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def quant(self):
        path = self.root/'request.json'; path.write_bytes(quant_report.encoded(request()))
        output = self.root/'quant'
        quant_report.run(path, output)
        return output

    def workflow(self):
        path = self.root/'original.json'; path.write_bytes(research_workflow.encode(request()))
        research_workflow.prepare(path, self.root/'prepared', 'Synthetic source-bound software regression')
        research_workflow.run(self.root/'prepared/plan.json', self.root/'run')
        return self.root/'run'

    def test_workbench_quant_report_canonical_bytes_and_exact_field_sources(self):
        directory = self.quant()
        self.assertEqual(quant_report.verify(directory)['status'], 'REPLAY_AND_REPORT_MATCH')
        bundle = json.loads((directory/'bundle.json').read_bytes())
        facts = json.loads((directory/'facts.json').read_bytes())
        typed = [f for f in facts['facts'] if 'value_kind' in f]
        self.assertGreater(len(typed), 30)
        for fact in typed:
            self.assertEqual(fact['semantic_mapping'], 'BUILTIN_CODE_SCHEMA')
            if fact['missingness'] is None:
                self.assertEqual(fact['value'], report_facts.pointer(bundle, fact['source']['pointer']))
            self.assertIsNone(fact['measurement_period'])
            self.assertIsNone(fact['observation_frequency'])
            self.assertIn('helper_inputs', fact['metadata_sources'])
        self.assertIn('Modeled total entry and period borrow cost', (directory/'report.md').read_text(encoding='utf8'))
        self.assertEqual(report_facts.verify_projection((directory/'bundle.json').read_bytes(), 'quant', (directory/'facts.json').read_bytes())['status'], 'VERIFIED_PROJECTION')

    def test_rehashed_whole_report_change_still_fails_canonical_replay(self):
        directory = self.quant(); path = directory/'report.md'
        path.write_bytes(path.read_bytes() + b'\nClaim: all period borrow settled at entry.\n')
        receipt = json.loads((directory/'receipt.json').read_bytes())
        receipt['artifacts']['report.md'] = quant_report.sha(path.read_bytes())
        (directory/'receipt.json').write_bytes(quant_report.encoded(receipt))
        with self.assertRaisesRegex(ValueError, 'CANONICAL_REPORT_MISMATCH'): quant_report.verify(directory)

    def test_projection_labels_units_values_and_source_pointers_are_exact(self):
        directory = self.quant(); raw = (directory/'bundle.json').read_bytes()
        facts = json.loads((directory/'facts.json').read_bytes())
        index = next(i for i, f in enumerate(facts['facts']) if f['source']['pointer'].endswith('/holding_period_borrow_cost_fraction'))
        for key, value in (('unit', 'USD'), ('metric', 'Realized cash profit'), ('value', 0)):
            changed = copy.deepcopy(facts); changed['facts'][index][key] = value
            self.assertFalse(report_facts.verify_projection(raw, 'quant', quant_report.encoded(changed))['matches'])
        changed = copy.deepcopy(facts); changed['facts'][index]['source']['pointer'] = '/result/results/0/result/entry_transaction_cost_fraction'
        self.assertFalse(report_facts.verify_projection(raw, 'quant', quant_report.encoded(changed))['matches'])

    def test_unknown_fingerprint_or_changed_input_operation_withholds_new_mapping(self):
        bundle = quant_workbench.freeze(request())
        for mode in ('fingerprint', 'operation', 'input_hash', 'result_hash'):
            changed = copy.deepcopy(bundle)
            if mode == 'fingerprint': changed['result']['implementation_sha256'] = 'unknown'
            if mode == 'operation':
                changed['input']['jobs'][0]['operation'] = 'backtest.holdings_ledger'
                changed['result']['input_sha256'] = report_facts.digest(changed['input'])
            if mode == 'input_hash': changed['result']['input_sha256'] = 'changed'
            changed['result_sha256'] = 'changed' if mode == 'result_hash' else report_facts.digest(changed['result'])
            facts = report_facts.project(quant_report.encoded(changed), 'quant')
            fact = next(f for f in facts['facts'] if f['source']['pointer'].endswith('/holding_period_borrow_cost_fraction'))
            self.assertEqual(fact['semantic_mapping'], 'UNMAPPED')
            self.assertIsNone(fact['unit'])

    def test_verified_answer_facts_match_native_and_reject_semantic_tampering(self):
        directory = self.workflow(); facts = answer_facts.project_verified(directory)
        result = research_workflow.read_result((directory/'result.json').read_bytes())
        self.assertTrue(all(row['projection_status'] == 'FIXED_FIELDS_PROJECTED' for row in facts['jobs']))
        for fact in facts['facts']:
            self.assertEqual(fact['value'], report_facts.pointer(result, fact['source']['pointer']))
            self.assertTrue(fact['input_bindings'])
            self.assertIsNone(fact['measurement_period'])
        self.assertFalse(facts['whole_answer_pass'])
        index = next(i for i, f in enumerate(facts['facts']) if f['source']['pointer'].endswith('/holding_period_borrow_cost_fraction'))
        self.assertEqual(facts['facts'][index]['unit'], 'fraction_of_initial_nav')
        for key, value in (('semantic_label', 'Paid entry cash'), ('unit', 'USD'), ('value', 0), ('scenario', 'observed_profit')):
            changed = copy.deepcopy(facts); changed['facts'][index][key] = value
            with self.assertRaisesRegex(ValueError, 'FIXED_ANSWER_FACTS_MISMATCH'):
                answer_facts.verify_projection(directory, research_workflow.encode(changed))
        self.assertEqual(answer_facts.verify_projection(directory, research_workflow.encode(facts))['status'], 'FIXED_ANSWER_FACTS_MATCH')

    def test_tampered_retained_source_is_rejected_before_answer_facts(self):
        directory = self.workflow()
        source = next((directory/'sources').glob('*.json'))
        source.write_bytes(source.read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'MISMATCH'):
            answer_facts.project_verified(directory)


if __name__ == '__main__':
    unittest.main()
