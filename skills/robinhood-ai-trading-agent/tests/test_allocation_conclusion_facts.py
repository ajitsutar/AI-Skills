"""Scoped conclusion facts preserve accounting and missing identity coverage."""
from copy import deepcopy
from decimal import Decimal, localcontext
from pathlib import Path
import hashlib
import json
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import portfolio_decision as decision
import quant_workbench as workbench
import report_facts


def pointer(document, path):
    for part in path.split('/')[1:]:
        document = document[int(part)] if isinstance(document, list) else document[part]
    return document


def sizing():
    return {'currency':'USD','role':'hypothetical_scenario','mode':'alternatives','budget':'83',
        'quantity_scenarios':[{'id':'whole','quantity_basis':'whole_shares','quantity_step':'1'}],
        'rows':[{'id':'alpha','price':'12','price_basis':'last','entry_orders':1,
                 'costs':[{'id':'ticket','amount':'2','unit':'per_order','phase':'entry'}]}]}


def allocation():
    return {'currency':'USD','role':'supplied_observation',
        'denominator':{'amount':'100','basis':'declared sleeve'},
        'rows':[{'id':'a','notional':'25','notional_basis':'gross_notional',
                 'instrument_type':'equity','issuer_id':'issuer-a'},
                {'id':'b','notional':'10','notional_basis':'gross_notional','instrument_type':'equity'},
                {'id':'cash','notional':'5','notional_basis':'gross_notional','instrument_type':'cash'}]}


class ConclusionFactsTests(unittest.TestCase):
    def assert_pointers(self, result, conclusion):
        for fact in conclusion['facts'].values():
            self.assertEqual(fact['value'], pointer(result,fact['result_pointer']))

    def test_sizing_budget_is_not_invested_gross(self):
        result=decision.budget_sizing(sizing())
        summary=result['scenarios'][0]['rows'][0]['conclusion_facts']
        self.assert_pointers(result,summary)
        values={k:Decimal(v['value']) for k,v in summary['facts'].items()}
        self.assertEqual(values['requested_cash_budget'],83)
        self.assertEqual(values['gross_notional'],72)
        self.assertEqual(values['modeled_entry_cost'],2)
        self.assertEqual(values['budget_remainder'],9)
        self.assertEqual(summary['budget_reconciliation_residual'],'0')
        self.assertEqual(summary['reconciliation_status'],'RECONCILED')
        self.assertFalse(summary['investment_dominance_established'])

    def test_portfolio_unassigned_cash_is_in_combined_remainder(self):
        doc=sizing(); doc['mode']='portfolio'; doc['rows'][0]['budget']='40'
        doc['rows'].append({**deepcopy(doc['rows'][0]),'id':'beta','budget':'20'})
        result=decision.budget_sizing(doc)
        totals=result['scenarios'][0]['portfolio_totals']
        summary=totals['conclusion_facts']
        self.assert_pointers(result,summary)
        self.assertEqual(summary['scope'],'combined_portfolio')
        self.assertEqual(totals['unassigned_cash_budget'],'23')
        self.assertEqual(Decimal(totals['budget_remainder']),31)
        self.assertEqual(summary['budget_reconciliation_residual'],'0')
        for row in result['scenarios'][0]['rows']:
            self.assertEqual(row['conclusion_facts']['scope'],'portfolio_row_cash_envelope')
            self.assert_pointers(result,row['conclusion_facts'])

    def test_alternatives_are_not_added_and_unknown_costs_stay_unknown(self):
        doc=sizing(); doc['rows'].append({**deepcopy(doc['rows'][0]),'id':'beta','costs':None})
        result=decision.budget_sizing(doc)
        scenario=result['scenarios'][0]
        self.assertIsNone(scenario['portfolio_totals'])
        summary=scenario['rows'][1]['conclusion_facts']
        self.assert_pointers(result,summary)
        self.assertEqual(summary['reconciliation_status'],'INPUTS_UNRESOLVED')
        self.assertIsNone(summary['facts']['gross_notional']['value'])
        self.assertIsNone(summary['budget_reconciliation_residual'])

    def test_zero_quantity_cash_and_low_decimal_context(self):
        doc=sizing();doc['budget']='1'
        with localcontext() as ctx:
            ctx.prec=2
            result=decision.budget_sizing(doc)
        summary=result['scenarios'][0]['rows'][0]['conclusion_facts']
        self.assertEqual(Decimal(summary['facts']['gross_notional']['value']),0)
        self.assertEqual(Decimal(summary['facts']['modeled_entry_cost']['value']),0)
        self.assertEqual(Decimal(summary['facts']['budget_remainder']['value']),1)
        self.assertEqual(summary['reconciliation_status'],'RECONCILED')

    def test_allocation_does_not_invent_cash_or_comparative_ranking(self):
        result=decision.allocation_context(allocation())
        summary=result['conclusion_facts'];self.assert_pointers(result,summary)
        self.assertEqual(summary['facts']['distinct_known_issuer_count']['value'],1)
        self.assertIsNone(summary['facts']['total_distinct_issuer_count']['value'])
        self.assertEqual(summary['facts']['count_status']['value'],'KNOWN_LOWER_BOUND_ONLY')
        self.assertEqual(Decimal(summary['facts']['unknown_issuer_notional']['value']),10)
        self.assertEqual(Decimal(summary['facts']['non_applicable_cash_notional']['value']),5)
        self.assertEqual(Decimal(result['denominator_difference']),60)
        self.assertIsNone(summary['outside_cash']);self.assertIsNone(summary['entry_cost'])
        for field in ('comparative_diversification_established','relative_risk_established',
                      'correlation_established','investment_dominance_established'):
            self.assertFalse(summary[field])

    def test_unquantified_row_does_not_become_zero_total(self):
        doc=allocation();doc['rows'][1]['notional']=None
        result=decision.allocation_context(doc);summary=result['conclusion_facts']
        self.assert_pointers(result,summary)
        self.assertIsNone(summary['facts']['total_gross_notional']['value'])
        self.assertIsNone(summary['facts']['total_distinct_issuer_count']['value'])
        self.assertEqual(Decimal(summary['facts']['known_gross_notional']['value']),30)

    def test_projection_types_direct_and_source_wrapped_facts(self):
        def source(document):
            text=json.dumps(document)
            return {'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),
                    'role':'supplied_observation','provenance':'synthetic regression input'}
        costs=source({'currency':'USD','costs':{'fee_per_trade':'2','one_way_slippage_bps':'0'}})
        source_sizing=sizing(); source_sizing['schema_version']=1
        del source_sizing['rows'][0]['costs']
        source_sizing['rows'][0]['price_basis']='unknown'
        source_sizing.update(cost_source=costs,cost_bindings={'currency':'/currency','cost_assumptions':'/costs'},
                             sensitivities=[{'id':'last-sensitivity','price_basis':'last'}])
        identities=source({'currency':'USD','identities':{'SYNTH':{'issuer_id':'issuer-a','instrument_type':'equity'}}})
        identities.update(id='identities',adapter='portfolio_context_v1',bindings={'root':''})
        source_context={'schema_version':1,'currency':'USD','role':'supplied_observation',
            'denominator':{'amount':'100','basis':'supplied sleeve'},'sources':[identities],
            'rows':[{'id':'position','symbol':'SYNTH','notional':'25','notional_basis':'gross_notional'}]}
        documents=[('planning.budget_sizing',sizing()),('planning.allocation_context',allocation()),
                   ('planning.source_budget_sizing',source_sizing),('planning.source_allocation_context',source_context)]
        bundle=workbench.freeze({'schema_version':1,'contract':{'prompt':'Describe supplied accounting and identity scope',
            'purpose':'local regression','base_currency':'USD','horizon_id':'P1Y','as_of':'2027-05-04T13:00:00Z'},
            'jobs':[{'id':str(index),'operation':op,'inputs':{'document':doc}} for index,(op,doc) in enumerate(documents)]})
        self.assertTrue(all(job['status']=='COMPUTED' for job in bundle['result']['results']))
        report=report_facts.project(json.dumps(bundle).encode(),'quant')
        by_path={fact['source']['pointer']:fact for fact in report['facts']}
        prefixes=['/result/results/0/result/scenarios/0/rows/0/conclusion_facts',
                  '/result/results/2/result/primary_result/scenarios/0/rows/0/conclusion_facts',
                  '/result/results/2/result/sensitivities/0/result/scenarios/0/rows/0/conclusion_facts']
        for prefix in prefixes:
            self.assertEqual(by_path[prefix+'/facts/gross_notional/value']['unit'],'input_currency_amount')
            self.assertEqual(by_path[prefix+'/investment_dominance_established']['unit'],'boolean')
        self.assertIsNone(by_path[prefixes[1]+'/facts/gross_notional/value']['value'])
        for prefix in ['/result/results/1/result/conclusion_facts',
                       '/result/results/3/result/allocation_result/conclusion_facts']:
            self.assertEqual(by_path[prefix+'/facts/distinct_known_issuer_count/value']['unit'],'count')
            self.assertEqual(by_path[prefix+'/facts/count_status/value']['unit'],'status')
            self.assertEqual(by_path[prefix+'/comparative_diversification_established']['unit'],'boolean')
            self.assertIsNone(by_path[prefix+'/outside_cash']['value'])


if __name__=='__main__': unittest.main()
