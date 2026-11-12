"""Private-default export preserves typed research qualifications, not source prose."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import quant_workbench as q
import report_facts as rf
import quant_report
from test_quant_assurance_integration import envelope
from test_quant_data_contracts import readiness_fixture, change_observation
from test_analyst_adapter import request
from test_source_strategy_readiness import fixture as source_readiness_fixture


def cases():
    result=[]
    result.append(('data.source_strategy_readiness',source_readiness_fixture()))
    for name,op in [('readiness','data.strategy_readiness'),('security-master','data.security_snapshot'),('features','data.source_features'),('price-refresh','data.price_refresh')]:
        result.append((op,json.loads((ROOT/'examples/quant-data'/f'{name}.json').read_text())))
    attempt=json.loads((ROOT/'examples/experiment-attempt.json').read_text())
    result += [('backtest.holdings_ledger',json.loads((ROOT/'examples/holdings-event-ledger.json').read_text())),
               ('experiment.validate_attempt',attempt),('experiment.overlap_review',{'attempts':[attempt]}),
               ('release.rights_inventory',json.loads((ROOT/'templates/source-rights-inventory.json').read_text())),
               ('release.grade_response',{'response_text':'{"n":2}','expected':{'n':2},'absolute_tolerance':0,'relative_tolerance':0}),
               ('analyst.extract_table',request('Analyst | Firm | Target | Date\nPRIVATE_PERSON_SENTINEL | PRIVATE_FIRM_SENTINEL | $100 | 2026-10-30')),
               ('analyst.earnings_basis',{'as_of':'2026-11-01T00:00:00Z','quote':{'price':100,'currency':'USD','share_basis':'post','available_at':'2026-10-30T00:00:00Z'},'estimates':[]})]
    for row in json.loads((ROOT/'examples/fictional-risk-diagnostics.json').read_text())['requests']:
        result.append((row['operation'],row['inputs']['document']))
    return result


class AssuranceReportTests(unittest.TestCase):
    def project(self,op,doc):
        req=envelope(op,doc)
        if op=='data.source_strategy_readiness':req['contract']['as_of']='2028-02-10T00:00:00Z'
        if op=='portfolio.sensitivity':req['contract']['horizon_id']=doc['base']['horizon_id']
        bundle=q.freeze(req)
        self.assertEqual(bundle['result']['results'][0]['status'],'COMPUTED',bundle['result'])
        report=rf.project(json.dumps(bundle,allow_nan=False).encode(),'quant')
        self.assertTrue(report['checks'][0]['code_mapping_matches'])
        return bundle,report

    def test_every_new_route_projects_with_current_code_and_retained_status(self):
        rows=cases();self.assertEqual({op for op,_ in rows},set(q.ASSURANCE_OPERATIONS))
        self.assertEqual(rf.quant_hash(),q.implementation_hash())
        for op,doc in rows:
            bundle,report=self.project(op,doc)
            self.assertIn(op,rf.extended_semantics())
            value=bundle['result']['results'][0]['result'].get('status')
            if value is not None:
                facts=[x for x in report['facts'] if x['source']['pointer']=='/result/results/0/result/status']
                self.assertEqual(len(facts),1);self.assertEqual(facts[0]['value'],value)
                self.assertIsNone(facts[0]['missingness'])
            self.assertNotIn('PRIVATE_PERSON_SENTINEL',json.dumps(report))
            self.assertNotIn('PRIVATE_FIRM_SENTINEL',json.dumps(report))

    def test_scenario_readiness_does_not_export_as_observed_complete(self):
        d=readiness_fixture();d['requirements']=[d['requirements'][1]]
        d['valuation_policy']['allow_modeled']=True;change_observation(d,1,status='modeled')
        bundle,report=self.project('data.strategy_readiness',d)
        facts={f['source']['pointer']:f for f in report['facts']}
        prefix='/result/results/0/result/'
        self.assertEqual(facts[prefix+'status']['value'],'DECLARED_SCENARIO_GRID_COMPLETE')
        self.assertFalse(facts[prefix+'strict_observed_grid_complete']['value'])
        self.assertTrue(facts[prefix+'declared_policy_grid_complete']['value'])
        self.assertEqual(facts[prefix+'universe_mode']['value'],'historical_membership')
        count=facts[prefix+'grid_status_counts/modeled']
        self.assertEqual((count['value'],count['unit']),(1,'count'))
        self.assertIn('not a stock',count['basis'])
        summary=quant_report.summary(bundle)
        self.assertEqual(summary['jobs'][0]['helper_outcome'],'DECLARED_SCENARIO_GRID_COMPLETE')
        self.assertIn('not valid observations',summary['meaning'])

    def test_reference_holdings_valuation_qualification_is_not_withheld(self):
        from test_holdings_ledger import base
        d=base();d['valuation_policy']='allow_references';d['opening']['marks'][0]['kind']='reference'
        _,report=self.project('backtest.holdings_ledger',d)
        fact=next(f for f in report['facts'] if f['source']['pointer'].endswith('/final/valuation_status'))
        self.assertEqual(fact['value'],'REFERENCE_OR_MODEL_SCENARIO')
        self.assertIn('not executable',fact['basis'])

    def test_all_declared_native_outcomes_registered_without_arbitrary_text(self):
        for status in ['RESEARCH_GAPS_REMAIN','FULL_FETCH_REQUIRED','CONFLICTS_PRESENT','UNRESOLVED_BASIS','FIXTURE_MISMATCH','UNGRADABLE_RESPONSE']:
            self.assertIn(status,rf.STATUSES)
        self.assertNotIn('PRIVATE_PERSON_SENTINEL',rf.STATUSES)


if __name__=='__main__':unittest.main()
