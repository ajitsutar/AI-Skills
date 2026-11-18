"""Source-bound and typed-report checks beyond direct helper tests."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import quant_workbench as qw
import report_facts as rf
import research_workflow as wf

def source():
    return {'currency':'USD','role':'hypothetical_scenario','sleeves':[
        {'id':'linear','exposure_model':'long_linear_price'},
        {'id':'cash','exposure_model':'not_applicable'},
        {'id':'unmodeled'}], 'shocks':[{'id':'explicit','return_fraction':'-.17'}]}
def contract():return {'prompt':'Compare stated sleeves','purpose':'test','base_currency':'USD','horizon_id':'P13D','as_of':'2027-06-11T13:00:00Z'}

class PlanningRolesIntegration(unittest.TestCase):
    def test_replay_facts_and_unknown_model(self):
        roles={'currency':'USD','role':'user_assumption','records':[{'id':'ceiling','semantic_role':'maximum','source_role':'user_assumption','value':'20','metric':'loss','unit':'USD','scope':'sleeve','basis':'after_cost'}],'checks':[{'id':'below','constraint_id':'ceiling','candidate':{'value':'12','metric':'loss','unit':'USD','scope':'sleeve','basis':'after_cost'}}]}
        bundle=qw.freeze({'schema_version':1,'contract':contract(),'jobs':[
            {'id':'roles','operation':'planning.input_roles','inputs':{'document':roles}},
            {'id':'comparison','operation':'planning.reference_comparison','inputs':{'document':source()}}]})
        self.assertEqual(qw.verify(bundle)['status'],'REPLAY_MATCH')
        self.assertEqual(qw.implementation_hash(),rf.quant_hash())
        facts=rf.project(json.dumps(bundle).encode(),'quant')['facts']
        values={x['source']['pointer']:x for x in facts}
        f=values['/result/results/1/result/sleeves/0/reference_scenarios/0/price_pnl_per_currency_unit']
        self.assertEqual(f['value'],'-0.17');self.assertEqual(f['unit'],'fraction')
        self.assertEqual(values['/result/results/1/result/sleeves/2/scenario_status']['value'],'UNKNOWN_MODEL')
        self.assertTrue(values['/result/results/0/result/checks/0/satisfies_declared_relation']['value'])
        self.assertIsNone(bundle['result']['results'][1]['result']['sleeves'][2]['reference_notional'])

    def test_source_bound_comparison_does_not_invent_allocation(self):
        raw=wf.encode(source())
        plan={'schema_version':1,'network_mode':'offline','contract':contract(),
          'sources':[{'id':'source','path':'source.json','sha256':wf.sha(raw),'format':'json','role':'explicit hypothetical source'}],
          'jobs':[{'id':'compare','operation':'planning.reference_comparison','arguments':{'document':{'$source':{'id':'source','pointer':''}}}}],
          'claims':[{'id':'price','job_id':'compare','pointer':'/result/sleeves/0/reference_scenarios/0/price_pnl_per_currency_unit','assertion':'-0.17'}],
          'requirements':[{'id':'reference','question':'Compare supplied price exposure','job_ids':['compare'],'expected_operations':['planning.reference_comparison']}]}
        output=wf.build(wf.encode(plan),{'source.json':raw}.__getitem__)
        result=json.loads(output['result.json'])
        helper=result['jobs'][0]['result']
        self.assertEqual(helper['retained_input'],source())
        self.assertTrue(all(row['recommended_allocation'] is None for row in helper['sleeves']))
        self.assertEqual(helper['sleeves'][1]['reference_scenarios'],[])
        self.assertEqual(result['status'],'COMPUTED')

if __name__=='__main__':unittest.main()
