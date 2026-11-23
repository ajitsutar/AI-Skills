"""Actual single-record entry, scoped delivery and legacy behavior."""
import json
import unittest
from pathlib import Path
import subprocess
import sys

import test_strategy_economics as fixtures
from strategy_clock_scope import selected_clocks


class SelectedStrategyClocksTests(unittest.TestCase):
    def setUp(self):
        case = fixtures.StrategyEconomicsTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case = case
        self.base = case.base
        study = json.loads(self.base.source.read_bytes())
        study['horizon'] = 'several years with a flexible exit'
        study['strategies'][0].update(decision='weekly completed close', holding_period='until reversal')
        self.base.source.write_text(json.dumps(study), encoding='utf8')

    def test_scoped_delivery_rejects_caller_clock_conflict_and_binds_final_pair(self):
        directory = self.base.directory
        self.case.options['strategy_registration']['uncertainty']['estimator'] = {
            'name':'circular_moving_block_percentile', 'block_observations':3, 'replicates':5000, 'seed':7}
        result = self.base.entry(self.case.options, '--scoped-design', directory/'export')
        self.assertEqual(result.returncode, 0, result.stderr)
        row = json.loads((directory/'export/answer-rows.json').read_bytes())[0]
        scope = row['clock_scope']
        self.assertEqual(scope['selected_record'], '/strategies/0')
        self.assertEqual(scope['decision_and_holding'], {
            'decision': {'record_pointer': '/decision', 'value': 'weekly completed close'},
            'holding_period': {'record_pointer': '/holding_period', 'value': 'until reversal'}})
        self.assertEqual(scope['registered_evaluation']['start']['record_pointer'], '/first')
        self.assertNotIn('several years', (directory/'export/answer.md').read_text(encoding='utf8'))
        root = Path(__file__).resolve().parents[1]
        metadata = directory/'metadata.json'
        metadata.write_text(json.dumps({'limitations':['Sibling horizon conflicts with the evaluation']}), encoding='utf8')
        argv = [sys.executable, '-B', str(root/'scripts/research_contracts.py'), 'deliver-strategy',
                str(directory/'export'), '--metadata', str(metadata), '--private-output', str(directory/'delivered')]
        failed = subprocess.run(argv, capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse((directory/'delivered').exists())
        from research_contracts import strategy_response
        with self.assertRaisesRegex(ValueError, 'SCOPED_STRATEGY_LIMITATIONS'):
            strategy_response((directory/'export/answer.md').read_bytes(), [row], metadata.read_bytes())
        metadata.write_text(json.dumps({'execution_limitations':[{'code':'UNKNOWN_HOST'}]}), encoding='utf8')
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        final = json.loads((directory/'delivered/files/response.json').read_bytes())
        self.assertEqual(final['rows'], [row])
        self.assertEqual(final['execution_limitations'], [{'code':'UNKNOWN_HOST'}])
        self.assertTrue(any('/strategies/0' in text for text in final['limitations']))

    def test_record_relative_override_cannot_resolve_a_sibling(self):
        from research_contracts import pointer
        selected = {'nested':{'decision-clock':'bar end'}, 'holding_period': None}
        origin = {'source_path':'book.json','source_sha256':'0'*64,'pointer':'/item'}
        out = selected_clocks(selected, origin, {}, {'decision':'/nested/decision-clock'}, pointer)
        self.assertEqual(out['decision_and_holding']['decision']['value'], 'bar end')
        self.assertNotIn('holding_period', out['decision_and_holding'])
        with self.assertRaises((ValueError, KeyError)):
            selected_clocks(selected, origin, {}, {'horizon':'/sibling/horizon'}, pointer)
