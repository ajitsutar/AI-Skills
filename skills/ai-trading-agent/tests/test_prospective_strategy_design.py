import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_contracts as contracts


class StrategyDesignTests(unittest.TestCase):
    def setUp(self):
        self.sources = Path(__file__).resolve().parent / 'fixtures'
        path = self.sources / 'quarterly-spread-study.json'
        self.request = {
            'allowlist': [path.name],
            'sources': [{'id': 'original', 'role': 'supplied_plan', 'path': path.name,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}],
            'strategy_source': {'source_id': 'original', 'pointer': '/studies/0'},
            'design_kind': 'research_contract',
            'design_terms': {'benchmark': {'record_pointer': '/comparators/hedged'},
                             'variant_treatment': {'proposal': 'Primary base spread; lagged spread sensitivity only.'},
                             'evaluation_window': {'record_pointer': '/simulation_interval'},
                             'execution_convention': {'proposal': 'Use first tradable quote after publication.'},
                             'development_validation_split': {'proposal': 'Fit through 2028, validate 2029-30.'}},
            'proposed_decision_rules': [self.rule('performance', 'mean net active return', 'bp per quarter', '>', 4),
                                        self.rule('risk', 'maximum drawdown', 'fraction', '<=', 0.08)]}

    def rule(self, purpose, measure, units, op, cutoff):
        return {'purpose': purpose, 'measure': measure, 'units': units, 'comparison': op,
                'threshold': cutoff, 'measurement_window': 'full paper interval',
                'on_failure': 'hold for review', 'if_unmeasurable': 'inconclusive'}

    def design(self):
        return contracts.OPERATIONS['plan-strategy'](self.request, self.sources)['result']

    def test_research_contract_scopes_facts_and_retains_proposed_rules(self):
        report = self.design()
        self.assertEqual(report['design_status'], 'DRAFT_FOR_REVIEW')
        self.assertEqual(report['supplied_strategy']['holding_rule'], 'until the next scheduled release')
        self.assertEqual(report['design_terms']['benchmark']['basis'], 'supplied')
        self.assertEqual(report['design_terms']['benchmark']['value'], 'equal-weight freight basket')
        self.assertEqual(report['design_terms']['execution_convention']['basis'], 'proposed')
        self.assertEqual(report['proposed_decision_rules'][0]['threshold'], 4)
        self.assertNotIn('eight years', json.dumps(report))
        self.assertNotIn('fixed price example', json.dumps(report))

    def test_cannot_read_sibling_term_or_accept_wrong_source_pin(self):
        self.request['design_terms']['benchmark'] = {'record_pointer': '/accounts/holding_period'}
        with self.assertRaises(KeyError):
            self.design()
        self.request['sources'][0]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'STRATEGY_SOURCE_BYTES_REQUIRED'):
            self.design()

    def test_operational_protocol_requires_its_own_terms_and_rule(self):
        self.request['design_kind'] = 'forward_paper'
        del self.request['design_terms']['development_validation_split']
        report = self.design()
        self.assertEqual(report['design_status'], 'INCOMPLETE')
        self.assertEqual(set(report['missing_design_fields']), {
            'variant_decision_record', 'quote_order_fill_reconciliation', 'decision_rule.operations'})
        self.request['design_terms'].update(
            variant_decision_record={'proposal': 'Log both spread values and orders by variant, including abstentions.'},
            quote_order_fill_reconciliation={'proposal': 'Link arrival quote and partial fills by order ID.'})
        self.request['proposed_decision_rules'].append(self.rule('operations', 'unlinked fills', 'count', '==', 0))
        self.assertEqual(self.design()['design_status'], 'DRAFT_FOR_REVIEW')
        risk = self.request['proposed_decision_rules'].pop(1)
        missing_risk = self.design()
        self.assertEqual(missing_risk['design_status'], 'INCOMPLETE')
        self.assertEqual(missing_risk['missing_design_fields'], ['decision_rule.risk'])
        self.request['proposed_decision_rules'].insert(1, risk)
        self.request['proposed_decision_rules'][-1]['threshold'] = 'choose later'
        with self.assertRaisesRegex(ValueError, 'DECISION_RULE_COMPARISON'):
            self.design()


if __name__ == '__main__':
    unittest.main()
