"""Check replay, source retention and typed report projection for new operations."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import quant_workbench as qw
import report_facts as rf
import research_workflow as wf

def documents():
    header={'currency':'USD','role':'hypothetical_scenario'}
    sizing={**header,'mode':'alternatives','budget':'83.70',
        'quantity_scenarios':[{'id':'integer','quantity_basis':'whole_shares','quantity_step':'1'}],
        'rows':[{'id':'choice','price':'7','costs':[{'id':'fee','amount':'1','unit':'per_order','phase':'entry'}],'entry_orders':1}]}
    context={**header,'denominator':{'amount':'200','basis':'declared sleeve'},
        'rows':[{'id':'position','notional':'50','notional_basis':'gross_notional','instrument_type':'equity',
        'issuer_id':'one-issuer','sector':'one-sector','industry':'one-industry',
        'dollar_volume':{'amount':'25','currency':'USD','unit':'currency_per_session','period':'explicit historical sample'}}]}
    friction={**header,'costs':[],'price_basis':'last',
        'quoted_spread':{'amount':18,'unit':'bps','reference_price_basis':'unknown'}}
    return {'planning.budget_sizing':sizing,'planning.allocation_context':context,'planning.friction_context':friction}

def contract():
    return {'prompt':'Synthetic advisory comparison','purpose':'local test','base_currency':'USD',
            'horizon_id':'P17D','as_of':'2027-05-04T13:00:00Z'}

class PortfolioDecisionIntegrationTests(unittest.TestCase):
    def test_full_workbench_replay_and_mapped_facts(self):
        jobs=[{'id':op,'operation':op,'inputs':{'document':doc}} for op,doc in documents().items()]
        bundle=qw.freeze({'schema_version':1,'contract':contract(),'jobs':jobs})
        self.assertEqual(qw.verify(bundle)['status'],'REPLAY_MATCH')
        self.assertTrue(all(j['status']=='COMPUTED' for j in bundle['result']['results']))
        self.assertEqual(qw.implementation_hash(),rf.quant_hash())
        report=rf.project(json.dumps(bundle).encode(),'quant')
        values={f['source']['pointer']:f for f in report['facts']}
        debit=values['/result/results/0/result/scenarios/0/rows/0/modeled_cash_debit']
        self.assertEqual(debit['value'],'78');self.assertEqual(debit['unit'],'input_currency_amount')
        fraction=values['/result/results/1/result/exposures/sector/groups/one-sector/fraction_of_denominator']
        self.assertEqual(fraction['value'],'0.25');self.assertEqual(fraction['unit'],'fraction')
        self.assertIn('original declared denominator',fraction['denominator'])
        volume=values['/result/results/1/result/rows/0/dollar_volume_context/notional_to_supplied_dollar_volume']
        self.assertEqual(volume['value'],'2');self.assertIsNone(volume['unit'])
        self.assertIn('ratio_unit',volume['basis'])
        self.assertTrue(all(f['measurement_period'] is None for f in report['facts']))

    def test_unknowns_remain_visible_in_report(self):
        data=documents()['planning.budget_sizing'];data['rows'][0]['costs']=None
        result=qw.freeze({'schema_version':1,'contract':contract(),'jobs':[
            {'id':'missing','operation':'planning.budget_sizing','inputs':{'document':data}}]})
        self.assertEqual(result['result']['results'][0]['result']['status'],'INPUTS_UNRESOLVED')
        facts=rf.project(json.dumps(result).encode(),'quant')['facts']
        self.assertTrue(any(f['value']=='INPUTS_UNRESOLVED' for f in facts))
        debit=next(f for f in facts if f['source']['pointer'].endswith('/rows/0/modeled_cash_debit'))
        self.assertIsNone(debit['value'])

    def test_source_bound_workflow_preserves_actual_input_and_claim(self):
        data=documents()['planning.allocation_context'];raw=wf.encode(data)
        plan={'schema_version':1,'network_mode':'offline','contract':contract(),
              'sources':[{'id':'observation','path':'context.json','sha256':wf.sha(raw),'format':'json','role':'explicit hypothetical context'}],
              'jobs':[{'id':'context','operation':'planning.allocation_context','arguments':{'document':{'$source':{'id':'observation','pointer':''}}}}],
              'claims':[{'id':'ratio','job_id':'context','pointer':'/result/rows/0/dollar_volume_context/notional_to_supplied_dollar_volume','assertion':'2'}],
              'requirements':[{'id':'context','question':'Compute declared volume ratio','job_ids':['context'],'expected_operations':['planning.allocation_context']}]}
        artifacts=wf.build(wf.encode(plan),{'context.json':raw}.__getitem__)
        result=json.loads(artifacts['result.json'])
        self.assertEqual(result['jobs'][0]['result']['retained_input'],data)
        self.assertEqual(result['jobs'][0]['result']['rows'][0]['dollar_volume_context']['ratio_unit'],'sessions')
        self.assertEqual(result['status'],'COMPUTED')
        self.assertFalse(result['network_requests_performed'])

if __name__=='__main__':unittest.main()
