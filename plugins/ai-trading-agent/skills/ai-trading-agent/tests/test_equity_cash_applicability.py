"""Synthetic cash-date provenance, independent of private comparison exercises."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import equity_cash_comparison as comparison
import quant_workbench as qw
import report_facts as rf
import research_workflow as workflow
from test_research_workflow import assumed, selected, encode, plan_for, build, write_artifacts, resign, regenerate_outer_report


def document():
    entry='2041-02-01T00:00:00Z'; exit='2042-02-01T00:00:00Z'
    source=json.dumps({'scenario': {'price': 91, 'at': exit}})
    common={'currency':'EUR','role':'supplied_observation','provenance':{'source':'synthetic retained record'}}
    return {'schema_version':1,'as_of':entry,
        'equity_document':dict(common,entry_at=entry,exit_at=exit,day_count='ACT/365F',entry_price=80,
            entry_cost_bps=0,exit_cost_bps=0,scenarios=[{'id':'illustration','terminal_price':91,'cumulative_dividends_per_share':0}]),
        'cash_document':dict(common,start_at=entry,end_at=exit,annual_effective_rate='.025',day_count='ACT/365F',floor=0,events=[],fee=0),
        'cash_benchmark':{'instrument':'Synthetic floating cash reference','evidence':['retained synthetic quote'],
            'observed_at':'2041-01-31T18:00:00Z','max_age_seconds':86400,'entry_at':entry,'exit_at':exit,
            'rate_or_return':'.025','basis':'annual_effective','day_count':'ACT/365F','currency':'EUR',
            'methodology':'Constant annual-effective rate projection before fees and taxes.',
            'horizon_adjustment_evidence':['Floating cash has no fixed maturity; hold supplied rate constant only as a projection assumption.']},
        'source_utf8':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'source_ref':'synthetic terminal record',
        'source_role':'hypothetical_scenario','terminal_time_pointer':'/scenario/at','terminal_price_pointers':{'illustration':'/scenario/price'}}


def bound(doc=None,args=None):
    doc=document() if doc is None else doc
    args={'document':selected('input')} if args is None else args
    bindings=[]
    actual=workflow.bind(args,{'input':doc},{'input':{'role':'supplied_observations','sha256':workflow.sha(encode(doc))}},bindings=bindings)
    provenance=comparison.benchmark_provenance(actual,bindings)
    return comparison.equity_cash_comparison(actual['document'],provenance)


def args_for(doc):return {'document':{k:selected('input','/'+k) for k in doc}}


class CashApplicabilityTests(unittest.TestCase):
    def test_positive_dated_source_does_not_guarantee_future_rate(self):
        doc=document(); before=deepcopy(doc); result=bound(doc)
        self.assertEqual(result['status'],'SOURCE_BOUND_CONDITIONAL_COMPARISON')
        self.assertEqual(result['cash_calculation_unresolved'],[])
        self.assertEqual(result['cash_applicability']['status'],'SOURCE_BOUND_DATED_ASSUMPTION')
        self.assertFalse(result['cash_applicability']['future_rate_guaranteed'])
        self.assertAlmostEqual(float(result['primary_comparison']['rows'][0]['cash_terminal_same_capital']),82)
        self.assertEqual(doc,before)

    def assert_conditional(self, result):
        self.assertIsNone(result['primary_comparison'])
        self.assertEqual(result['cash_calculation_unresolved'],[])
        self.assertIsNotNone(result['cash_result'])
        self.assertAlmostEqual(float(result['conditional_price_sensitivity']['rows'][0]['cash_terminal_same_capital']),82)

    def test_missing_dates_cutoff_policy_and_all_metadata_retain_arithmetic(self):
        for path in ('observed_at','max_age_seconds','entry_at','exit_at'):
            doc=document();del doc['cash_benchmark'][path]
            with self.subTest(path=path):self.assert_conditional(bound(doc))
        for path in ('cash_benchmark','as_of'):
            doc=document();del doc[path];self.assert_conditional(bound(doc))
        doc=document();del doc['cash_benchmark']['max_age_seconds']
        self.assertIn('CASH_FRESHNESS_POLICY_UNASSESSED',bound(doc)['cash_unresolved'])

    def test_stale_future_outside_interval_and_invalid_dates(self):
        for key,value in [('observed_at','2041-01-20T00:00:00Z'),('observed_at','2041-02-02T00:00:00Z'),
                          ('entry_at','2041-02-02T00:00:00Z'),('exit_at','2043-02-01T00:00:00Z'),
                          ('observed_at',None),('observed_at',123),('observed_at','bad')]:
            doc=document();doc['cash_benchmark'][key]=value
            with self.subTest(key=key,value=value):self.assert_conditional(bound(doc))

    def test_maturity_adjustment_is_explicit_and_not_years_of_rate_certainty(self):
        doc=document();del doc['cash_benchmark']['horizon_adjustment_evidence'];self.assert_conditional(bound(doc))
        doc['cash_benchmark']['instrument_maturity_at']=doc['equity_document']['exit_at']
        self.assertIsNotNone(bound(doc)['primary_comparison'])
        doc['cash_benchmark']['instrument_maturity_at']='2040-02-01T00:00:00Z';self.assert_conditional(bound(doc))

    def test_rate_basis_currency_mismatch_remains_conditional(self):
        for key,value in [('rate_or_return','.026'),('basis','annual_simple'),('day_count','ACT/360'),('currency','USD')]:
            doc=document();doc['cash_benchmark'][key]=value
            with self.subTest(key=key):self.assert_conditional(bound(doc))

    def test_assumed_metadata_and_ancestor_never_become_primary(self):
        doc=document()
        for key in comparison.BENCHMARK_SOURCE_FIELDS:
            args=args_for(doc);args['document']['cash_benchmark']={k:selected('input','/cash_benchmark/'+k) for k in doc['cash_benchmark']}
            args['document']['cash_benchmark'][key]=assumed(doc['cash_benchmark'][key])
            with self.subTest(key=key):self.assert_conditional(bound(doc,args))
        for group in ('equity_document','cash_document'):
            args=args_for(doc);args['document'][group]={k:selected('input','/'+group+'/'+k) for k in doc[group]}
            args['document'][group]['currency']=assumed('EUR');self.assert_conditional(bound(doc,args))
        self.assert_conditional(bound(doc,{'document':assumed(doc)}))
        self.assert_conditional(comparison.equity_cash_comparison(doc))

    def test_null_labels_and_assumption_source_roles_are_not_primary(self):
        for field in ('instrument','methodology'):
            for value in (None, '', ' ', 0, False):
                doc=document();doc['cash_benchmark'][field]=value
                with self.subTest(field=field,value=value):self.assert_conditional(bound(doc))
        doc=document()
        for role in ('user_assumption','user_assumptions','hypothetical_scenario','unknown'):
            bindings=[];args=workflow.bind({'document':selected('input')},{'input':doc},
                {'input':{'role':role,'sha256':workflow.sha(encode(doc))}},bindings=bindings)
            result=comparison.equity_cash_comparison(doc,comparison.benchmark_provenance(args,bindings))
            with self.subTest(role=role):self.assert_conditional(result)

    def test_calendar_timestamp_cannot_date_an_unrelated_cash_quote(self):
        doc=document();doc['calendar_publication']=doc['cash_benchmark']['observed_at']
        args=args_for(doc);args['document']['cash_benchmark']={k:selected('input','/cash_benchmark/'+k) for k in doc['cash_benchmark']}
        args['document']['cash_benchmark']['observed_at']=selected('input','/calendar_publication')
        result=bound(doc,args);self.assert_conditional(result)
        self.assertIn('CASH_OBSERVATION_NOT_BOUND_TO_SAME_RATE_RECORD',result['cash_unresolved'])

    def test_workflow_integration_replay_and_no_original_argument_mutation(self):
        doc=document();sources={'input':('input.json',encode(doc),'supplied_observations')}
        plan=plan_for(sources,[{'id':'comparison','operation':'financial.equity_cash_comparison','arguments':{'document':selected('input')}}])
        plan['contract']['as_of']=doc['as_of']
        artifacts=build(plan,sources);job=json.loads(artifacts['result.json'])['jobs'][0]
        self.assertEqual(job['status'],'COMPUTED',job);self.assertIsNotNone(job['result']['primary_comparison'])
        self.assertEqual(json.loads(artifacts['jobs/0000/arguments.json']),{'document':doc})
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'run';write_artifacts(folder,artifacts)
            self.assertEqual(workflow.verify(folder)['status'],'WORKFLOW_REPLAY_AND_REPORT_MATCH')
            result=json.loads((folder/'result.json').read_bytes())
            result['jobs'][0]['result']['cash_applicability']['future_rate_guaranteed']=True
            (folder/'result.json').write_bytes(encode(result));regenerate_outer_report(folder);resign(folder)
            with self.assertRaises(ValueError):workflow.verify(folder)

    def test_workflow_cutoff_cannot_be_replaced_by_later_document_cutoff(self):
        doc=document();sources={'input':('input.json',encode(doc),'supplied_observations')}
        plan=plan_for(sources,[{'id':'comparison','operation':'financial.equity_cash_comparison','arguments':{'document':selected('input')}}])
        job=json.loads(build(plan,sources)['result.json'])['jobs'][0]
        self.assertEqual(job['status'],'COMPUTED',job);self.assert_conditional(job['result'])
        self.assertIn('CASH_RESEARCH_CUTOFF_DIFFERS_FROM_WORKFLOW_CONTRACT',job['result']['cash_unresolved'])

    def test_workflow_rejects_provenance_injection(self):
        doc=document();sources={'input':('input.json',encode(doc),'supplied_observations')}
        args={'document':selected('input'),'benchmark_provenance':assumed({'schema_version':1,'records':[]})}
        job=json.loads(build(plan_for(sources,[{'id':'comparison','operation':'financial.equity_cash_comparison','arguments':args}]),sources)['result.json'])['jobs'][0]
        self.assertEqual(job['status'],'UNRESOLVED_INPUT_OR_FAILED');self.assertIn('WORKFLOW_DERIVED',job['reason'])

    def test_cash_dependency_is_in_both_semantic_hashes(self):
        original=Path.read_text; before=qw.implementation_hash(); before_report=rf.quant_hash()
        def altered(path, *args, **kwargs):
            raw=original(path, *args, **kwargs)
            return raw+'\n# synthetic semantic mutation\n' if path.name=='cash_benchmark.py' else raw
        with patch.object(Path,'read_text',altered):
            self.assertNotEqual(qw.implementation_hash(),before)
            self.assertNotEqual(rf.quant_hash(),before_report)

if __name__=='__main__':unittest.main()
