import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import quant_workbench as workbench
import quant_report
import report_facts
from quant_common import digest


def request(operation, inputs):
    return {'schema_version':1,'contract':{'prompt':'Fictional offline comparison',
        'purpose':'test accounting and provenance','base_currency':'USD','horizon_id':'P1Y',
        'as_of':'2026-10-13T16:00:00Z'},'jobs':[{'id':'one','operation':operation,'inputs':inputs}]}


class AlignmentIntegrationTests(unittest.TestCase):
    def test_schema_and_computation_have_same_implementation_identity(self):
        self.assertEqual(workbench.implementation_hash(), report_facts.quant_hash())

    def test_nested_unknown_comparison_survives_report(self):
        doc=request('analysis.compare_claim',{'document':{'left':{'value':4},'right':{'value':4},'relation':'eq'}})
        artifacts=quant_report.build(json.dumps(doc).encode(), lambda name,index: self.fail('No external source'))
        # build returns the exact retained bytes, not an independently typed summary.
        facts=json.loads(artifacts['facts.json'])
        statuses=[f['value'] for f in facts['facts'] if f['unit']=='status']
        self.assertIn('COMPUTED',statuses)
        self.assertIn('UNKNOWN_COMPARABILITY',statuses)
        bundle=json.loads(artifacts['bundle.json'])
        self.assertIsNone(bundle['result']['results'][0]['result']['typed_comparison'])

    def test_new_backtest_cannot_advance_analysis_beyond_contract(self):
        doc=request('backtest.dual_sma',{'bars':[], 'as_of':'2027-01-01T00:00:00Z'})
        result=workbench.run(doc)['results'][0]
        self.assertEqual(result['status'],'REJECTED_INPUT')
        self.assertIn('FUTURE_ANALYSIS_CUTOFF',result['reason'])

    def test_known_old_schema_is_not_mislabeled_current_replay(self):
        bundle=workbench.freeze(request('validation.tail',{'returns':[.05,-.03,.02]}))
        bundle['result']['implementation_sha256']=next(iter(report_facts.COMPATIBLE_QUANT_SCHEMAS))
        bundle['result_sha256']=digest(bundle['result'])
        facts=report_facts.project(json.dumps(bundle).encode(),'quant')
        checks=facts['checks'][0]
        self.assertFalse(checks['code_mapping_matches'])
        self.assertTrue(checks['known_historical_schema'])
        self.assertFalse(checks['calculation_replayed'])
        self.assertTrue(any(f['metric']=='Input-series maximum drawdown' for f in facts['facts']))
        with self.assertRaises(ValueError): workbench.verify(bundle)

    def test_installed_mapping_preserves_exact_scalar_and_unit(self):
        doc=request('analysis.hedge_scenarios',{'document':{'shares':50,'price':20,
            'currency':'USD','shock_returns':[-.2], 'hedges':[{'id':'h','kind':'short_linear',
            'short_notional':500,'shock_sensitivity':.6,'total_explicit_cost':3}]}})
        bundle=workbench.freeze(doc)
        facts=report_facts.project(json.dumps(bundle).encode(),'quant')
        selected=[f for f in facts['facts'] if f['source']['pointer'].endswith('/linear_residual_fraction')]
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['value'],.7)
        self.assertEqual(selected[0]['unit'],'fraction')
        self.assertIsNotNone(selected[0]['denominator'])
        self.assertIsNone(selected[0]['observation_frequency'])


if __name__=='__main__': unittest.main()
