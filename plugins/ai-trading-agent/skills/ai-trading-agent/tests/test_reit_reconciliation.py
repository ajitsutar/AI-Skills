"""Private arithmetic kernel regressions; public source boundaries are tested separately.

All prior exact arithmetic and invalid-allocation assertions remain. The public
workbench/workflow replay checks below still exercise the changed entrypoint.
"""
import copy
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import financial_alignment as financial
import quant_workbench as workbench
import research_workflow as workflow
from test_research_workflow import encode,plan_for,selected,build,write_artifacts


def example():
    return json.loads((ROOT/'examples/reit-cross-measure-input.json').read_text(encoding='utf-8'))


def document():return example()['jobs'][0]['inputs']['document']


def allocation(doc):
    return {'basis':copy.deepcopy(doc['gross_capex']['basis']),
            'recurring_is_subset_of_gross_capex':True,'evidence':'Synthetic explicit allocation schedule',
            'allocations':[{'id':'purchases','amount':8},{'id':'development','amount':12},{'id':'other','amount':3}]}


class ReitReconciliationTests(unittest.TestCase):
    def test_bridge_and_difference_identity_do_not_explain_capex_overlap(self):
        result=financial._reit_declared_arithmetic(document());ledger=result['metric_ledger']
        for key,value in {'ffo':65,'affo':36,'gross_capex':31,'cfo_after_gross_capex':23,
                          'ffo_minus_cfo':11,'affo_minus_cfo_after_gross_capex':13,
                          'cash_after_gross_capex_and_distributions':-7}.items():
            self.assertEqual(Decimal(ledger[key]['value']),Decimal(value),key)
        row=ledger['affo_minus_cfo_after_gross_capex']
        self.assertEqual(sum(Decimal(r['coefficient'])*Decimal(r['amount']) for r in row['components']),Decimal(13))
        self.assertEqual(result['capex_overlap']['status'],'UNKNOWN')
        self.assertIsNone(result['capex_overlap']['allocations'])
        self.assertIsNone(result['capex_overlap']['growth_or_maintenance_classification'])
        self.assertEqual(Decimal(ledger['distribution_payout_to_affo']['value']),Decimal(30)/36)
        self.assertIn('not distribution safety',ledger['distribution_payout_to_affo']['interpretation'])

    def test_equal_recurring_and_total_capex_does_not_create_mapping(self):
        doc=document();doc['affo_bridge']['recurring_capex']=31
        result=financial._reit_declared_arithmetic(doc)
        self.assertEqual(result['capex_overlap']['status'],'UNKNOWN')
        self.assertIsNone(result['capex_overlap']['allocations'])

    def test_valid_declared_mapping_has_no_growth_or_maintenance_classification(self):
        doc=document();doc['recurring_capex_mapping']=allocation(doc)
        result=financial._reit_declared_arithmetic(doc);overlap=result['capex_overlap']
        self.assertEqual(overlap['status'],'DECLARED_MAPPING_RECONCILED')
        self.assertEqual(sum(Decimal(r['recurring_amount']) for r in overlap['allocations']),Decimal(23))
        self.assertEqual(sum(Decimal(r['not_allocated_to_recurring']) for r in overlap['allocations']),Decimal(8))
        self.assertIsNone(overlap['growth_or_maintenance_classification'])

    def test_invalid_mapping_preserves_valid_raw_metrics(self):
        for change,reason in (
            (lambda m:m['allocations'].append(copy.deepcopy(m['allocations'][0])),'DUPLICATE'),
            (lambda m:m['allocations'][0].update(amount=-1),'RANGE'),
            (lambda m:m['allocations'][0].update(amount=99),'CAP_EXCEEDED'),
            (lambda m:m['allocations'][0].update(amount=7),'SUM_MUST_EQUAL'),
            (lambda m:m['allocations'][0].update(id='unlisted'),'EXACT_COMPONENT_IDS'),
            (lambda m:m['allocations'][0].update(amount=None),'AMOUNTS_REQUIRED'),
            (lambda m:m.update(recurring_is_subset_of_gross_capex=False),'SUBSET_DECLARATION'),
            (lambda m:m.update(evidence=''),'EVIDENCE_REQUIRED')):
            doc=document();mapping=allocation(doc);change(mapping);doc['recurring_capex_mapping']=mapping
            with self.subTest(reason=reason):
                result=financial._reit_declared_arithmetic(doc)
                self.assertEqual(result['capex_overlap']['status'],'UNRESOLVED_MAPPING')
                self.assertIn(reason,result['capex_overlap']['reason'])
                self.assertEqual(Decimal(result['metric_ledger']['affo']['value']),Decimal(36))

    def test_excluded_categories_cannot_explain_larger_recurring_amount(self):
        doc=document();mapping=allocation(doc)
        mapping['allocations']=[{'id':'purchases','amount':10},{'id':'development','amount':0},{'id':'other','amount':0}]
        doc['recurring_capex_mapping']=mapping
        result=financial._reit_declared_arithmetic(doc)
        self.assertEqual(result['capex_overlap']['status'],'UNRESOLVED_MAPPING')
        self.assertIn('SUM_MUST_EQUAL',result['capex_overlap']['reason'])

    def test_mapping_requires_known_matching_unit_period_and_holder_basis(self):
        for field,value in [('amount_unit','EUR millions'),('period_end','2029-12-31'),
                            ('holder_basis','consolidated including preferred'),('period_start',None)]:
            doc=document();mapping=allocation(doc);mapping['basis'][field]=value
            doc['recurring_capex_mapping']=mapping
            result=financial._reit_declared_arithmetic(doc)
            self.assertEqual(result['capex_overlap']['status'],'UNRESOLVED_MAPPING')
            self.assertEqual(Decimal(result['metric_ledger']['ffo']['value']),Decimal(65))

    def test_unknown_cross_measure_basis_is_conditional_not_primary(self):
        doc=document();del doc['affo_bridge']['basis'];doc['recurring_capex_mapping']=allocation(doc)
        result=financial._reit_declared_arithmetic(doc);row=result['metric_ledger']['affo']
        self.assertIsNone(row['value'])
        self.assertEqual(Decimal(row['conditional_same_basis_value']),Decimal(36))
        self.assertEqual(result['capex_overlap']['status'],'UNRESOLVED_MAPPING')
        self.assertEqual(Decimal(result['metric_ledger']['cfo']['value']),Decimal(54))
        self.assertEqual(Decimal(result['metric_ledger']['cfo_after_gross_capex']['value']),Decimal(23))

    def test_known_unit_conflict_is_not_even_a_same_basis_sensitivity(self):
        doc=document();doc['affo_bridge']['basis']['amount_unit']='EUR millions'
        row=financial._reit_declared_arithmetic(doc)['metric_ledger']['affo']
        self.assertIsNone(row['value']);self.assertIsNone(row['conditional_same_basis_value'])
        self.assertEqual(row['basis_compatibility']['conflicting_dimensions'],['amount_unit'])

    def test_missing_inputs_are_not_zero_and_unaffected_metrics_survive(self):
        doc=document();doc['affo_bridge'].pop('adjustments')
        result=financial._reit_declared_arithmetic(doc)
        self.assertIsNone(result['metric_ledger']['affo']['value'])
        self.assertEqual(Decimal(result['metric_ledger']['ffo']['value']),Decimal(65))
        doc['affo_bridge']['adjustments']=[]
        self.assertEqual(Decimal(financial._reit_declared_arithmetic(doc)['metric_ledger']['affo']['value']),Decimal(42))
        doc=document();doc.pop('cfo')
        result=financial._reit_declared_arithmetic(doc)
        self.assertEqual(Decimal(result['metric_ledger']['affo']['value']),Decimal(36))
        self.assertIsNone(result['metric_ledger']['cfo_after_gross_capex']['value'])
        doc=document();doc['affo_bridge']['recurring_capex']=None
        self.assertIsNone(financial._reit_declared_arithmetic(doc)['metric_ledger']['affo']['value'])
        doc['affo_bridge']['recurring_capex']=0
        self.assertEqual(Decimal(financial._reit_declared_arithmetic(doc)['metric_ledger']['affo']['value']),Decimal(59))

    def test_fraction_denominator_and_time_anchor_are_not_inferred(self):
        doc=document();doc['property_fractions']=[{'id':'renewals','value':'.18'}]
        row=financial._reit_declared_arithmetic(doc)['property_fractions'][0]
        self.assertIsNone(row['denominator']);self.assertIsNone(row['time_anchor'])
        self.assertEqual(row['unresolved_fields'],['denominator','time_anchor'])
        doc['property_fractions'][0].update(denominator='annualized base rent',time_anchor='2029 calendar year')
        row=financial._reit_declared_arithmetic(doc)['property_fractions'][0]
        self.assertEqual(row['denominator'],'annualized base rent');self.assertEqual(row['unresolved_fields'],[])

    def test_empty_and_unknown_capex_components_remain_distinct(self):
        doc=document();doc['gross_capex']['components']=None
        self.assertIsNone(financial._reit_declared_arithmetic(doc)['metric_ledger']['gross_capex']['value'])
        doc['gross_capex']['components']=[]
        self.assertEqual(Decimal(financial._reit_declared_arithmetic(doc)['metric_ledger']['gross_capex']['value']),Decimal(0))

    def test_explicit_zero_mapping_and_nonpositive_payout_denominator(self):
        doc=document();doc['affo_bridge']['recurring_capex']=0
        mapping=allocation(doc)
        for row in mapping['allocations']:row['amount']=0
        doc['recurring_capex_mapping']=mapping
        result=financial._reit_declared_arithmetic(doc)
        self.assertEqual(result['capex_overlap']['status'],'DECLARED_MAPPING_RECONCILED')
        self.assertEqual(sum(Decimal(r['recurring_amount']) for r in result['capex_overlap']['allocations']),0)
        doc['ffo_bridge']['components']=[{'id':'net_loss','amount':-5}]
        row=financial._reit_declared_arithmetic(doc)['metric_ledger']['distribution_payout_to_ffo']
        self.assertEqual(row['status'],'UNDEFINED_RATIO');self.assertIsNone(row['value'])

    def test_duplicate_or_negative_gross_components_are_rejected(self):
        doc=document();doc['gross_capex']['components']*=2
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):financial._reit_declared_arithmetic(doc)
        doc=document();doc['gross_capex']['components'][0]['amount']=-1
        with self.assertRaisesRegex(ValueError,'RANGE'):financial._reit_declared_arithmetic(doc)

    def test_public_example_and_operation_replay(self):
        request=example();before=copy.deepcopy(request)
        result=workbench.run(request)
        self.assertEqual(result['results'][0]['status'],'COMPUTED')
        bundle=workbench.freeze(request)
        self.assertEqual(workbench.verify(bundle)['status'],'REPLAY_MATCH')
        self.assertEqual(request,before)
        self.assertIn('financial.reit_reconciliation',workbench.operation_catalog()['operations'])

    def test_source_bound_workflow_preserves_inputs_and_replays(self):
        doc=document();sources={'issuer':('issuer.json',encode(doc),'supplied fictional issuer data')}
        plan=plan_for(sources,[{'id':'reit','operation':'financial.reit_reconciliation',
                               'arguments':{'document':selected('issuer')}}])
        artifacts=build(plan,sources)
        self.assertEqual(json.loads(artifacts['jobs/0000/arguments.json']),{'document':doc})
        result=json.loads(artifacts['result.json'])['jobs'][0]
        self.assertEqual(result['status'],'COMPUTED')
        self.assertEqual(result['result']['capex_overlap']['status'],'UNKNOWN')
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';write_artifacts(folder,artifacts)
            self.assertEqual(workflow.verify(folder)['status'],'WORKFLOW_REPLAY_AND_REPORT_MATCH')


if __name__=='__main__':unittest.main()
