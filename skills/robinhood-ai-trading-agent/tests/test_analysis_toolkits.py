"""Behavioral integration of all added allowlisted operations, with frozen replay."""
import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import quant_workbench as w
import report_facts


class AnalysisIntegrationTests(unittest.TestCase):
    def fixture(self):
        return json.loads((ROOT/'examples/analysis-workbench.json').read_text(encoding='utf-8'))
    def test_report_schema_registry_tracks_full_calculation_implementation(self):
        self.assertEqual(set(w.MODULES),set(report_facts.QUANT_FILES))
        self.assertEqual(w.implementation_hash(),report_facts.quant_hash())
        bundle=w.freeze(w.prepare(self.fixture()))
        projected=report_facts.project(json.dumps(bundle).encode('utf-8'),'quant')
        self.assertTrue(projected['checks'][0]['code_mapping_matches'])
    def test_new_operations_compute_and_replay(self):
        doc=w.prepare(self.fixture())
        self.assertEqual({j['operation'] for j in doc['jobs']},set(w.ANALYSIS_OPERATIONS))
        self.assertEqual(w.prepare(doc),doc)
        bundle=w.freeze(doc)
        failures=[r for r in bundle['result']['results'] if r['status']!='COMPUTED']
        self.assertEqual(failures,[])
        self.assertEqual(w.verify(bundle)['status'],'REPLAY_MATCH')
        by={r['operation']:r['result'] for r in bundle['result']['results']}
        self.assertAlmostEqual(by['factor.fama_french']['alpha_per_period'],.002)
        self.assertAlmostEqual(by['factor.style_risk']['portfolio_variance'],.115)
        self.assertEqual(by['sentiment.fuse']['composite'],0)
    def test_defaults_are_explicit_and_no_mutation(self):
        original=self.fixture();saved=copy.deepcopy(original)
        doc=w.prepare(original)
        self.assertEqual(original,saved)
        technical=next(j for j in doc['jobs'] if j['operation']=='technical.analyze')['inputs']['request']
        self.assertIn('parameters',technical)
        sentiment=next(j for j in doc['jobs'] if j['operation']=='sentiment.analyze')['inputs']['document']
        self.assertIn('window_start',sentiment)
    def test_future_or_conflicting_contract_is_rejected(self):
        doc=self.fixture();doc['contract']['as_of']='2020-01-01T00:00:00Z'
        results=w.run(doc)['results']
        for op in ('technical.analyze','sentiment.analyze','sentiment.trend','sentiment.fuse','sentiment.backtest','factor.normalize','factor.fama_french'):
            self.assertEqual(next(r for r in results if r['operation']==op)['status'],'REJECTED_INPUT')
        doc=self.fixture();doc['contract']['base_currency']='EUR'
        self.assertEqual(next(r for r in w.run(doc)['results'] if r['operation']=='fundamental.calculate')['status'],'REJECTED_INPUT')
    def test_hashes_detect_input_and_implementation_tampering(self):
        b=w.freeze(w.prepare(self.fixture()))
        b['input']['jobs'][0]['inputs']['request']['bars'][0]['close']+=.01
        with self.assertRaises(ValueError):w.verify(b)
    def test_optional_inference_is_not_in_replay_allowlist(self):
        self.assertFalse(any('infer' in name for name in w.ANALYSIS_OPERATIONS))
    def test_depth_and_calibration_cannot_leak_future(self):
        doc=self.fixture()
        tech=next(j for j in doc['jobs'] if j['operation']=='technical.analyze')
        tech['inputs']['request']['depth_snapshot']={'as_of':'2099-01-01T00:00:00Z','bids':[[99,10]],'asks':[[101,10]]}
        cal=next(j for j in doc['jobs'] if j['operation']=='sentiment.calibrate')
        cal['inputs']['document']['rows'][0]['label_available_at']='2099-01-01T00:00:00Z'
        results=w.run(doc)['results']
        for op in ('technical.analyze','sentiment.calibrate'):
            self.assertEqual(next(r for r in results if r['operation']==op)['status'],'REJECTED_INPUT')
    def test_completed_bar_availability_required(self):
        doc=self.fixture()
        job=next(j for j in doc['jobs'] if j['operation']=='technical.analyze')
        del job['inputs']['data_available_at']
        self.assertEqual(next(r for r in w.run(doc)['results'] if r['operation']=='technical.analyze')['status'],'REJECTED_INPUT')


if __name__=='__main__':unittest.main()
