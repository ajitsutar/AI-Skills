import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import quant_workbench as w
import report_facts


def fixture():
    examples=ROOT/'examples'
    jobs=[]
    for filename in sorted(examples.glob('derivatives-*.json')):
        jobs.append({'id':filename.stem,'operation':'derivatives.calculate','inputs':{'document':json.loads(filename.read_text(encoding='utf-8'))}})
    for name,op in [('paper-multiasset.json','paper.replay'),('platform-readiness.json','platform.assess')]:
        jobs.append({'id':op,'operation':op,'inputs':{'document':json.loads((examples/name).read_text(encoding='utf-8'))}})
    for filename in sorted(examples.glob('time-series-*-input.json')):
        jobs.append({'id':filename.stem,'operation':'timeseries.run','inputs':{'document':json.loads(filename.read_text(encoding='utf-8'))}})
    return {'schema_version':1,'contract':{'prompt':'Replay fictional multiasset examples and report explicit limits; no trades.','purpose':'offline regression','base_currency':'USD','horizon_id':'declared_in_each_example','as_of':'2026-10-24T06:00:00Z'},'jobs':jobs}


class MultiAssetIntegrationTests(unittest.TestCase):
    def test_routes_are_computed_and_replay(self):
        d=fixture();self.assertEqual({j['operation'] for j in d['jobs']},set(w.MULTIASSET_OPERATIONS))
        self.assertEqual(len(d['jobs']),10)
        b=w.freeze(w.prepare(d))
        self.assertEqual([(r['operation'],r.get('error')) for r in b['result']['results'] if r['status']!='COMPUTED'],[])
        self.assertEqual(w.verify(b)['status'],'REPLAY_MATCH')
        self.assertEqual(set(w.MODULES),set(report_facts.QUANT_FILES))
        self.assertEqual(w.implementation_hash(),report_facts.quant_hash())

    def test_paper_currency_cutoff_and_input_immutability(self):
        d=fixture();old=copy.deepcopy(d);w.prepare(d);self.assertEqual(d,old)
        d['contract']['as_of']='2020-01-01T00:00:00Z'
        results=w.run(d)['results']
        for op in ('paper.replay','platform.assess','timeseries.run','derivatives.calculate'):
            self.assertEqual(next(r for r in results if r['operation']==op)['status'],'REJECTED_INPUT')
        d=fixture();d['contract']['base_currency']='EUR'
        for row in w.run(d)['results']:
            if row['operation'] in ('paper.replay','derivatives.calculate'):
                self.assertEqual(row['status'],'REJECTED_INPUT')

    def test_successful_execution_does_not_claim_production(self):
        results=w.run(fixture())['results']
        paper=next(r for r in results if r['operation']=='paper.replay')['result']
        self.assertEqual(paper['live_orders_submitted'],0)
        self.assertFalse(paper['production_qualified'])
        platform=next(r for r in results if r['operation']=='platform.assess')['result']
        self.assertFalse(platform['execution_authorized'])
        self.assertTrue(all(r['readiness_claim']=='NOT_ESTABLISHED_BY_THIS_ASSESSOR' for r in platform['results']))


if __name__=='__main__':unittest.main()
