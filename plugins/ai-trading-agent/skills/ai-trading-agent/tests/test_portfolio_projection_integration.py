"""Projection arithmetic must survive registry replay and typed reports."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import quant_workbench as qw
import report_facts as rf
import research_workflow as wf

def source(**kw):return {'currency':'USD','source_ref':'supplied:example','source_role':'hypothetical_scenario',**kw}
def data():
    return {'currency':'USD','role':'hypothetical_scenario','opening':source(as_of='2032-07-01',cash='100',tax_reserve='0',positions=[{'id':'a','quantity':'10'}]),
      'target_date':'2032-07-10','included_states':['scenario'],'mark_policy':'target_date_only',
      'marks':[source(id='m',asset_id='a',as_of='2032-07-10',price='20')],
      'other_assets':[],'liabilities':[],
      'flows':[source(id='out',kind='external_obligation',date='2032-07-05',amount='40',state='scenario',included_in_opening=False),
               source(id='reserve',kind='reserve_change',date='2032-07-06',amount='12',state='scenario',included_in_opening=False)]}
def contract():return {'prompt':'Compare conditional cash and assets','purpose':'test','base_currency':'USD','horizon_id':'P9D','as_of':'2032-07-01T13:00:00Z'}

class ProjectionIntegration(unittest.TestCase):
    def test_registry_replay_reports_assets_not_free_cash(self):
        tax={'currency':'USD','role':'hypothetical_scenario','scenarios':[source(id='tax',as_of='2032-07-06',gross_proceeds='60',selling_costs='2',cost_basis='40',tax_rate='.25',selling_costs_reduce_gain='yes')]}
        bundle=qw.freeze({'schema_version':1,'contract':contract(),'jobs':[
            {'id':'projection','operation':'planning.dated_projection','inputs':{'document':data()}},
            {'id':'tax','operation':'planning.tax_sensitivity','inputs':{'document':tax}}]})
        self.assertEqual(qw.verify(bundle)['status'],'REPLAY_MATCH')
        self.assertEqual(qw.implementation_hash(),rf.quant_hash())
        facts={f['source']['pointer']:f for f in rf.project(json.dumps(bundle).encode(),'quant')['facts']}
        base='/result/results/0/result/'
        self.assertEqual(facts[base+'net_equity']['value'],'260')
        self.assertEqual(facts[base+'cash_after_tax_earmark']['value'],'48')
        self.assertEqual(facts[base+'net_equity']['unit'],'input_currency_amount')
        self.assertEqual(facts['/result/results/1/result/scenarios/0/positive_tax_estimate']['value'],'4.50')

    def test_source_bound_unknown_denominator_remains_unknown(self):
        doc=data();del doc['liabilities'];raw=wf.encode(doc)
        plan={'schema_version':1,'network_mode':'offline','contract':contract(),
         'sources':[{'id':'src','path':'ledger.json','format':'json','role':'explicit hypothetical ledger','sha256':wf.sha(raw)}],
         'jobs':[{'id':'ledger','operation':'planning.dated_projection','arguments':{'document':{'$source':{'id':'src','pointer':''}}}}],
         'claims':[{'id':'cash','job_id':'ledger','pointer':'/result/cash','assertion':'60'}],
         'requirements':[{'id':'projection','question':'Project supplied balances','job_ids':['ledger'],'expected_operations':['planning.dated_projection']}]}
        out=wf.build(wf.encode(plan),{'ledger.json':raw}.__getitem__)
        result=json.loads(out['result.json'])['jobs'][0]['result']
        self.assertEqual(result['retained_input'],doc)
        self.assertIsNone(result['net_equity'])
        self.assertEqual(result['identified_assets'],'260')
        self.assertEqual(result['status'],'UNRESOLVED')

if __name__=='__main__':unittest.main()
