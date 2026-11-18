"""The raw-observation route retains arithmetic and unresolved evidence in reports."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_flow_normalization import example
import quant_workbench as qw
import report_facts as rf
import research_workflow as wf

def contract():return dict(prompt='Normalize supplied operating cash',purpose='test',base_currency='USD',horizon_id='P1Y',as_of='2026-04-30T23:00:00Z')

class FlowIntegration(unittest.TestCase):
    def test_replay_and_fact_statuses(self):
        bundle=qw.freeze({'schema_version':1,'contract':contract(),'jobs':[{'id':'flows','operation':'data.normalize_flows','inputs':{'document':example()}}]})
        self.assertEqual(qw.verify(bundle)['status'],'REPLAY_MATCH')
        self.assertEqual(qw.implementation_hash(),rf.quant_hash())
        facts={f['source']['pointer']:f for f in rf.project(json.dumps(bundle).encode(),'quant')['facts']}
        prefix='/result/results/0/result/normalization/issuers/0/'
        self.assertEqual(facts[prefix+'fields/cfo_ttm/value']['value'],'60')
        self.assertEqual(facts[prefix+'fields/cfo_ttm/status']['value'],'DRAFT_UNVERIFIED')
        self.assertEqual(facts[prefix+'status']['value'],'INCOMPLETE')
        self.assertFalse(facts[prefix+'latest_public_period_checked']['value'])

    def test_source_bound_route_preserves_original_mapping(self):
        data=example();raw=wf.encode(data)
        plan={'schema_version':1,'network_mode':'offline','contract':contract(),
          'sources':[{'id':'src','path':'flows.json','format':'json','role':'invented raw observations with explicit mappings','sha256':wf.sha(raw)}],
          'jobs':[{'id':'normalize','operation':'data.normalize_flows','arguments':{'document':{'$source':{'id':'src','pointer':''}}}}],
          'claims':[{'id':'ttm','job_id':'normalize','pointer':'/result/normalization/issuers/0/fields/cfo_ttm/value','assertion':'60'}],
          'requirements':[{'id':'normalization','question':'Reconstruct cash with evidence limits','job_ids':['normalize'],'expected_operations':['data.normalize_flows']}]}
        out=wf.build(wf.encode(plan),{'flows.json':raw}.__getitem__)
        result=json.loads(out['result.json'])['jobs'][0]['result']
        self.assertEqual(result['mapping_input'],data)
        self.assertEqual(result['normalization_input']['schema_version'],1)
        self.assertEqual(result['status'],'INCOMPLETE')

if __name__=='__main__':unittest.main()
