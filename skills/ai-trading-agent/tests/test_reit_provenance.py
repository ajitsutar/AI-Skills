"""Generic source roles cannot be erased by matching REIT metadata labels."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import financial_alignment as financial
import reit_provenance as provenance
import research_workflow as workflow
from test_research_workflow import assumed,selected,encode,plan_for,build,write_artifacts


def document():
    basis={'amount_unit':'EUR million','period_start':'2028-01-01','period_end':'2028-12-31','holder_basis':'common equity'}
    group=lambda **kwargs:dict(basis=copy.deepcopy(basis),**kwargs)
    return {'currency':'EUR','role':'supplied_observation',
        'ffo_bridge':group(definition='Synthetic signed bridge',components=[{'id':'earnings','amount':42},{'id':'depreciation','amount':18}]),
        'affo_bridge':group(definition='Synthetic issuer adjustment',adjustments=[{'id':'other','amount':-7}],recurring_capex=22),
        'cfo':group(amount=45),'gross_capex':group(components=[{'id':'first','amount':20},{'id':'second','amount':10}]),
        'distributions':group(amount=25),
        'recurring_capex_mapping':group(recurring_is_subset_of_gross_capex=True,evidence='Synthetic explicit allocation table',allocations=[{'id':'first','amount':17},{'id':'second','amount':5}]),
        'property_fractions':[{'id':'leased','value':'.82','denominator':'floor area','time_anchor':'2028-12-31'}]}


def args_for(doc):return {'document':{key:selected('issuer','/'+key) for key in doc}}


def bound(args=None,doc=None):
    doc=document() if doc is None else doc
    args={'document':selected('issuer')} if args is None else args
    values={'issuer':doc};sources={'issuer':{'role':'supplied_observations','sha256':workflow.sha(encode(doc))}}
    bindings=[];arguments=workflow.bind(args,values,sources,bindings=bindings)
    original=copy.deepcopy(arguments)
    p=provenance.derive(arguments,bindings)
    result=provenance.reconcile(arguments['document'],p,financial._reit_declared_arithmetic)
    assert arguments==original
    return result,arguments,p


class ReitProvenanceTests(unittest.TestCase):
    def test_sourced_ancestor_preserves_all_old_results(self):
        doc=document();before=copy.deepcopy(doc);result,args,p=bound(doc=doc)
        original=financial._reit_declared_arithmetic(doc)
        for key,row in original['metric_ledger'].items():
            self.assertEqual({k:v for k,v in result['metric_ledger'][key].items() if k in row},row)
        self.assertEqual(result['capex_overlap']['status'],'DECLARED_MAPPING_RECONCILED')
        self.assertEqual(result['property_fractions'][0]['unresolved_fields'],[])
        self.assertEqual(doc,before);self.assertEqual(result['metadata_evidence']['declared_document'],doc)
        self.assertEqual(p['/document/cfo/basis/holder_basis']['source_pointer'],'')

    def test_every_basis_dimension_assumption_is_conditional(self):
        for group in provenance.GROUPS[:-1]:
            for field in provenance.BASIS_FIELDS:
                with self.subTest(group=group,field=field):
                    doc=document();args=args_for(doc)
                    g={key:selected('issuer','/'+group+'/'+key) for key in doc[group]}
                    g['basis']={key:selected('issuer','/'+group+'/basis/'+key) for key in provenance.BASIS_FIELDS}
                    g['basis'][field]=assumed(doc[group]['basis'][field]);args['document'][group]=g
                    result,_,_=bound(args,doc)
                    key='distribution_payout_to_affo' if group in ('ffo_bridge','affo_bridge','distributions') else 'cfo_after_gross_capex'
                    metric=result['metric_ledger'][key]
                    self.assertIsNone(metric['value']);self.assertIsNotNone(metric['conditional_same_basis_value'])
                    self.assertIn(field,metric['basis_compatibility']['unknown_dimensions'])
                    for raw in ('ffo','cfo','gross_capex'):self.assertIsNotNone(result['metric_ledger'][raw]['value'])

    def test_whole_basis_group_document_and_arguments_assumptions(self):
        doc=document()
        variants=[assumed({'document':doc}),{'document':assumed(doc)}]
        for value in (assumed(doc['cfo']),dict(amount=selected('issuer','/cfo/amount'),basis=assumed(doc['cfo']['basis']))):
            args=args_for(doc);args['document']['cfo']=value;variants.append(args)
        for args in variants:
            result,_,p=bound(args,doc)
            self.assertIsNone(result['metric_ledger']['cfo_after_gross_capex']['value'])
            self.assertEqual(result['metric_ledger']['cfo_after_gross_capex']['conditional_same_basis_value'],'15')
            self.assertEqual(p['/document/cfo/basis/holder_basis']['kind'],'ASSUMPTION')

    def test_unbound_and_missing_metadata_never_become_primary(self):
        doc=document();p=provenance.derive({'document':doc},[])
        result=financial.reit_reconciliation(doc,metadata_provenance=p)
        self.assertIsNone(result['metric_ledger']['affo']['value'])
        self.assertEqual(result['metric_ledger']['affo']['conditional_same_basis_value'],'31')
        self.assertEqual(result['property_fractions'][0]['unresolved_fields'],['denominator','time_anchor'])
        doc['affo_bridge']['basis']['amount_unit']=None
        result,_,_=bound(doc=doc)
        self.assertIsNone(result['metric_ledger']['affo']['value'])

    def test_supported_conflicts_suppress_primary_and_conditional(self):
        for field,value in [('amount_unit','GBP million'),('holder_basis','all holders'),('period_end','2028-11-30')]:
            doc=document();doc['affo_bridge']['basis'][field]=value
            result,_,_=bound(doc=doc);row=result['metric_ledger']['affo']
            self.assertEqual(row['basis_compatibility']['status'],'INCOMPATIBLE')
            self.assertIsNone(row['value']);self.assertIsNone(row['conditional_same_basis_value'])

    def test_assumed_conflict_is_retained_not_silently_repaired(self):
        doc=document();doc['cfo']['basis']['holder_basis']='all holders'
        args=args_for(doc);args['document']['cfo']=assumed(doc['cfo'])
        result,_,_=bound(args,doc);row=result['metric_ledger']['cfo_after_gross_capex']
        self.assertEqual(row['basis_compatibility']['status'],'UNKNOWN')
        self.assertEqual(row['declared_basis_compatibility']['status'],'INCOMPATIBLE')
        self.assertIsNone(row['value']);self.assertIsNone(row['conditional_same_basis_value'])
        self.assertIn('withheld',next(k for k in row if k.startswith('conditional_value_')))

    def test_property_leaf_array_and_object_assumptions_retain_originals(self):
        doc=document();variants=[]
        for value in (assumed(doc['property_fractions']),[assumed(doc['property_fractions'][0])]):
            args=args_for(doc);args['document']['property_fractions']=value;variants.append(args)
        args=args_for(doc);row={k:selected('issuer','/property_fractions/0/'+k) for k in doc['property_fractions'][0]}
        row['time_anchor']=assumed('2028-12-31');args['document']['property_fractions']=[row];variants.append(args)
        for args in variants:
            result,_,_=bound(args,doc);r=result['property_fractions'][0]
            self.assertIsNone(r['time_anchor']);self.assertIn('time_anchor',r['unresolved_fields'])
            self.assertEqual(r['declared_metadata']['time_anchor'],'2028-12-31')
            self.assertEqual(r['source_record'],doc['property_fractions'][0]);self.assertEqual(r['fraction'],'0.82')
        self.assertEqual(result['property_fractions'][0]['denominator'],'floor area')

    def test_mapping_basis_assumption_does_not_establish_allocation(self):
        doc=document();args=args_for(doc);mapping={k:selected('issuer','/recurring_capex_mapping/'+k) for k in doc['recurring_capex_mapping']}
        mapping['basis']=assumed(doc['recurring_capex_mapping']['basis']);args['document']['recurring_capex_mapping']=mapping
        result,_,_=bound(args,doc);overlap=result['capex_overlap']
        self.assertEqual(overlap['status'],'UNRESOLVED_MAPPING');self.assertIsNone(overlap['allocations'])
        self.assertEqual(overlap['declared_mapping'],doc['recurring_capex_mapping'])
        self.assertEqual(result['metric_ledger']['affo']['value'],'31')
        self.assertEqual(result['metric_ledger']['cfo_after_gross_capex']['value'],'15')

    def test_missing_numbers_conflicts_and_invalid_mapping_preserve_old_guards(self):
        doc=document();doc['cfo']['amount']=None;doc['recurring_capex_mapping']={'unexpected':True}
        result,_,_=bound({'document':assumed(doc)},doc)
        self.assertIsNone(result['metric_ledger']['cfo_after_gross_capex']['conditional_same_basis_value'])
        self.assertEqual(result['metric_ledger']['cfo_after_gross_capex']['status'],'MISSING_INPUT')
        self.assertEqual(result['capex_overlap']['status'],'UNRESOLVED_MAPPING')
        doc['recurring_capex_mapping']=None
        self.assertEqual(bound(doc=doc)[0]['capex_overlap']['status'],'UNKNOWN')

    def test_nearest_binding_and_malformed_provenance(self):
        doc=document();_,_,p=bound(doc=doc)
        valid=copy.deepcopy(p)
        for bad in ([],{},dict(p,unexpected={'kind':'SOURCE'})):
            with self.assertRaisesRegex(ValueError,'PROVENANCE'):financial.reit_reconciliation(doc,metadata_provenance=bad)
        pointer='/document/cfo/basis/holder_basis'
        for record in ({'kind':'SOURCE'},{'kind':'FORGED'},{'kind':'UNBOUND','source_id':'fake'}):
            bad=copy.deepcopy(valid);bad[pointer]=record
            with self.assertRaises(ValueError):financial.reit_reconciliation(doc,metadata_provenance=bad)
        source=p[pointer]
        parent={'target_pointer':'/document','kind':'ASSUMPTION','reason':'Synthetic scenario','value':doc}
        near=copy.deepcopy(source);near['target_pointer']='/document/cfo'
        derived=provenance.derive({'document':doc},[parent,near])
        self.assertEqual(derived[pointer]['kind'],'SOURCE')
        self.assertEqual(derived['/document/affo_bridge/basis/holder_basis']['kind'],'ASSUMPTION')
        with self.assertRaisesRegex(ValueError,'DUPLICATE'):provenance.derive({'document':doc},[parent,parent])

    def test_direct_helper_withholds_unbound_cross_measure_values(self):
        doc=document();before=copy.deepcopy(doc)
        result=financial.reit_reconciliation(doc)
        self.assertNotIn('metadata_evidence',result)
        self.assertIsNone(result['metric_ledger']['affo']['value'])
        self.assertEqual(result['metric_ledger']['affo']['conditional_same_basis_value'],'31')
        self.assertFalse(result['metric_ledger']['affo']['source_bound_comparability'])
        self.assertEqual(doc,before)

    def test_workflow_derives_roles_and_replays_without_changing_arguments(self):
        doc=document();args=args_for(doc);args['document']['cfo']=assumed(doc['cfo'])
        sources={'issuer':('issuer.json',encode(doc),'supplied_observations')}
        plan=plan_for(sources,[{'id':'bridge','operation':'financial.reit_reconciliation','arguments':args}])
        before=copy.deepcopy(plan);artifacts=build(plan,sources)
        job=json.loads(artifacts['result.json'])['jobs'][0]
        self.assertEqual(job['status'],'COMPUTED',job)
        result=job['result'];self.assertIsNone(result['metric_ledger']['cfo_after_gross_capex']['value'])
        self.assertEqual(result['metric_ledger']['cfo_after_gross_capex']['conditional_same_basis_value'],'15')
        self.assertEqual(json.loads(artifacts['jobs/0000/arguments.json']),{'document':doc})
        self.assertEqual(plan,before)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';write_artifacts(folder,artifacts)
            self.assertEqual(workflow.verify(folder)['status'],'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            summary=workflow.summarize(folder)
            self.assertIn('ASSUMPTION',json.dumps(summary))

    def test_workflow_rejects_injected_provenance_from_all_argument_bindings(self):
        doc=document();_,_,p=bound(doc=doc)
        sources={'issuer':('issuer.json',encode({'document':doc,'metadata_provenance':p}),'supplied_observations')}
        for args in (selected('issuer'),assumed({'document':doc,'metadata_provenance':p})):
            plan=plan_for(sources,[{'id':'bridge','operation':'financial.reit_reconciliation','arguments':args}])
            job=json.loads(build(plan,sources)['result.json'])['jobs'][0]
            self.assertEqual(job['status'],'UNRESOLVED_INPUT_OR_FAILED')
            self.assertIn('WORKFLOW_DERIVED',job['reason'])


if __name__=='__main__':unittest.main()
