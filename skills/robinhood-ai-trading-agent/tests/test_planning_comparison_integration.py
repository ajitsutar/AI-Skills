"""Shared-run reporting retains comparison uncertainty and date-path semantics."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import quant_workbench as qw
import report_facts as rf
import research_workflow as wf

def comparison():return {'currency':'USD','role':'user_assumption','criteria':[
    {'id':'cost','metric':'cash_cost','unit':'USD','basis':'same explicit scenario','direction':'minimize'},
    {'id':'risk','metric':'residual_exposure','unit':'USD','basis':'same target date','direction':'minimize'}],
    'alternatives':[{'id':'first','values':{'cost':'3','risk':'9'}},{'id':'second','values':{'cost':'5','risk':'7'}},{'id':'unknown','values':{'cost':None,'risk':'8'}}]}
def dates():return {'currency':'USD','role':'hypothetical_scenario','business_dates':['2031-01-06','2031-01-07','2031-01-08','2031-01-09'],
    'sale_date':'2031-01-06','settlement_lag':1,'transfer_lag':1,'spendable_deadline':'2031-01-09'}
def contract():return {'prompt':'Compare conditional alternatives','purpose':'test','base_currency':'USD','horizon_id':'P3D','as_of':'2031-01-06T13:00:00Z'}

class PlanningComparisonIntegration(unittest.TestCase):
    def test_replay_comparison_and_dates(self):
        bundle=qw.freeze({'schema_version':1,'contract':contract(),'jobs':[
            {'id':'alternatives','operation':'planning.alternative_comparison','inputs':{'document':comparison()}},
            {'id':'dates','operation':'planning.settlement_transfer_paths','inputs':{'document':dates()}}]})
        self.assertEqual(qw.verify(bundle)['status'],'REPLAY_MATCH')
        self.assertEqual(qw.implementation_hash(),rf.quant_hash())
        facts={f['source']['pointer']:f for f in rf.project(json.dumps(bundle).encode(),'quant',include_source_text=True)['facts']}
        self.assertEqual(facts['/result/results/0/result/pairwise/0/relation']['value'],'TRADEOFF')
        self.assertEqual(facts['/result/results/1/result/paths/0/status']['value'],'POSSIBLE_INTRADAY_ACCEPTANCE_UNKNOWN')
        self.assertEqual(facts['/result/results/1/result/paths/1/arrival_date']['value'],'2031-01-09')
        self.assertFalse(facts['/result/results/1/result/paths/1/guaranteed_spendable_by_deadline']['value'])
        self.assertIsNone(bundle['result']['results'][0]['result']['selected_alternative'])

    def test_source_bound_unknown_tradeoffs_are_not_unique_winner(self):
        raw=wf.encode(comparison())
        plan={'schema_version':1,'network_mode':'offline','contract':contract(),
          'sources':[{'id':'src','path':'comparison.json','format':'json','role':'supplied hypothetical criteria','sha256':wf.sha(raw)}],
          'jobs':[{'id':'compare','operation':'planning.alternative_comparison','arguments':{'document':{'$source':{'id':'src','pointer':''}}}}],
          'claims':[{'id':'relation','job_id':'compare','pointer':'/result/pairwise/0/relation','assertion':'TRADEOFF'}],
          'requirements':[{'id':'tradeoffs','question':'Compare without inventing preferences','job_ids':['compare'],'expected_operations':['planning.alternative_comparison']}]}
        out=wf.build(wf.encode(plan),{'comparison.json':raw}.__getitem__)
        result=json.loads(out['result.json'])['jobs'][0]['result']
        self.assertEqual(result['retained_input'],comparison())
        self.assertEqual(result['indeterminate_ids'],['first','second','unknown'])
        self.assertEqual(result['non_dominated_ids'],[])
        self.assertIsNone(result['selected_alternative'])

    def test_unsupported_plural_weights_do_not_silently_change_policy(self):
        import planning_comparison
        doc=comparison();doc['criteria'][0]['weights']=[1]
        with self.assertRaisesRegex(ValueError,'PREFERENCE_POLICY_NOT_IMPLEMENTED'):
            planning_comparison.alternative_comparison(doc)

if __name__=='__main__':unittest.main()
