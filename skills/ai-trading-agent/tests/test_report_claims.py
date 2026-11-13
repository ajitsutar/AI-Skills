from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve()
sys.path[:0]=[str(HERE.parents[1]/'scripts'),str(HERE.parents[3]/'candidate/ai-trading-agent/scripts')]
import report_claims as report


def scenario_output():
    target={'value':0,'unit':'fraction','valuation_basis':'holding_period_return','horizon_years':2}
    objective={'id':'return_goal','measure':'net_total_return_fraction','operator':'>=',
               'target':target,'status':'DEFINED',
               'definition':{'measure':'net_total_return_fraction','operator':'>=','target':target}}
    rows=[]
    for i,(margin,multiple,value) in enumerate([(0.1,4,-0.8),(0.1,8,0.1),(0.2,4,0.2),(0.2,8,0.9)]):
        rows.append({'id':'row-'+str(i),'parameters':{'terminal_ebit_margin':margin,'exit_ev_to_ebit':multiple},
                     'objectives':{'return_goal':{'measure':'net_total_return_fraction','target':0,'value':value,'met':value>=0}}})
    return {'scope':{'kind':'FINITE_CARTESIAN_DOMAIN','row_count':4},'objectives':[objective],'rows':rows}


def scenario_claim():
    return {'id':'condition-test','kind':'scenario_condition','evidence':{'artifact':'e','pointer':''},
            'objective_id':'return_goal','connective':'all','conditions':[
                {'parameter':'terminal_ebit_margin','operator':'>','value':0.1},
                {'parameter':'exit_ev_to_ebit','operator':'>','value':4}]}


def accounting_output():
    fields={
        'income':{'value':9,'attribution':'income_available_to_common','period_start':'2032-01-01',
                  'period_end':'2032-12-31','issuer':'SYNTHETIC','currency':'EUR','unit_scale':1},
        'shares':{'value':3,'basis':'dated_share_count','period_start':'2032-01-01',
                  'period_end':'2032-12-31','issuer':'SYNTHETIC','unit_scale':1}}
    bound={group:{key:{'value':value,'source_ref':{'source_id':'fictional','pointer':'/'+group+'/'+key}}
                  for key,value in values.items()} for group,values in fields.items()}
    return {'method':'source-claims-1.0.0','operation':'accounting','classification':'DIAGNOSTIC_RATIO_ONLY',
            'raw_operand_ratio':3,'eps':None,'pe':None,'allowed_claims':[],
            'bound_fields':bound,'reasons':['PERIOD_WEIGHTED_SHARE_BASIS_NOT_ESTABLISHED']}


def cohort_output():
    return {'method':'source-claims-1.0.0','operation':'analyst_corpus',
      'status':'REVIEWED_WITH_CONFIGURED_CORPUS_COVERAGE',
      'coverage':{'status':'CONFIGURED_SCAN_RECONCILED','unresolved_candidate_ids':[],
                  'unlinked_record_ids':[],'scan':{'unsupported_sources':[]},
                  'record_ids':['house-a-old','house-a-new','house-b']},
      'analysis':{'method':'analyst-evidence-1.0.0','as_of':'2035-02-01T00:00:00Z','target_horizon':'P1Y',
                  'individual_targets_used':[
                      {'record_id':'house-a-new','firm_id':'house-a','issued_at':'2035-01-20','target':41},
                      {'record_id':'house-b','firm_id':'house-b','issued_at':'2035-01-15','target':38}],
                  'excluded':[{'record_id':'house-a-old','reason':'SUPERSEDED_FIRM_TARGET'}],
                  'consensus':{'independent_firms':2}}}


def prepared(evidence,claim):
    raw=json.dumps(evidence).encode()
    return {'artifacts':{'e':{'path':'output.json','sha256':hashlib.sha256(raw).hexdigest()}},
            'segments':[{'claim':claim}]},{'e':raw}


def presence_output(has_candidates=True,unsupported=False,binding='UNBOUND'):
    ref={'source_id':'source-a','pointer':'/customer_revenue_fraction'}
    candidates=[{'candidate_id':'candidate-a','source_ref':ref,'source_sha256':'a'*64,
                 'matched_terms':['revenue'],'value':0.17,'meaning_verified':False}] if has_candidates else []
    predicate='SOURCE_CANDIDATE_PRESENT' if candidates else 'NO_CONFIGURED_LEXICAL_MATCH'
    if unsupported:predicate+='_INCOMPLETE_SCAN'
    return {'method':'source-claims-1.0.0','operation':'presence',
      'scan':{'terms':['revenue'],'match':'any','sources_scanned':['source-a','opaque'] if unsupported else ['source-a'],
              'unsupported_sources':['opaque'] if unsupported else [],'candidates':candidates,
              'scope':'CONFIGURED_LEXICAL_SEARCH_OF_PINNED_CORPUS','semantic_completeness_verified':False},
      'binding_state':binding,'binding_reason':'NO_ADAPTER_BINDING_SUPPLIED' if binding=='UNBOUND' else None,
      'predicate':predicate,'allowed_claims':(['source_candidate_present'] if candidates else [])+
           (['adapter_value_bound'] if binding=='EXACT_SOURCE_VALUE' else []),'source_absence_established':False,
      'facts':[{'predicate':predicate,'binding_state':binding,'semantic_scope_verified':False,
                'source_refs':[ref] if candidates else []}]}


class ReportClaimTests(unittest.TestCase):
    def test_stronger_and_claim_has_two_counterexamples(self):
        plan,raw=prepared(scenario_output(),scenario_claim())
        out=report.compile_report(plan,raw)
        facts=out['claims'][0]['facts']
        self.assertEqual(facts['necessary'],'REFUTED')
        self.assertEqual(len(facts['necessity_counterexamples']),2)
        self.assertEqual(facts['sufficient'],'HOLDS_ON_DECLARED_FINITE_DOMAIN')
        self.assertIn(' AND ',out['report'])

    def test_or_is_not_rewritten_as_and(self):
        claim=scenario_claim();claim.update(connective='any',assertion='necessary_and_sufficient')
        plan,raw=prepared(scenario_output(),claim)
        out=report.compile_report(plan,raw)
        self.assertIn(' OR ',out['report'])
        self.assertEqual(out['claims'][0]['facts']['necessary'],'HOLDS_ON_DECLARED_FINITE_DOMAIN')
        edited=out['report'].replace(' OR ',' AND ').encode()
        self.assertEqual(report.audit_saved_report(plan,raw,edited)['status'],'SAVED_REPORT_MISMATCH')

    def test_unsupported_necessity_assertion_fails_before_render(self):
        claim=scenario_claim();claim['assertion']='necessary'
        plan,raw=prepared(scenario_output(),claim)
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_NECESSITY'):
            report.compile_report(plan,raw)

    def test_no_free_objective_alias_or_claim_text(self):
        for field in ['objective_label','conclusion','rendered_text']:
            claim=scenario_claim();claim[field]='a different result'
            plan,raw=prepared(scenario_output(),claim)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError,'UNSUPPORTED_OR_MISSING_FIELDS'):
                report.compile_report(plan,raw)

    def test_dcf_unavailable_cannot_inherit_return_success(self):
        evidence=scenario_output()
        evidence['objectives'].append({'id':'dcf_goal','measure':'dcf_discount_closure',
                                      'status':'UNAVAILABLE_DCF_MODEL_NOT_EVALUATED',
                                      'definition':{'measure':'dcf_discount_closure'}})
        for row in evidence['rows']:
            row['objectives']['dcf_goal']={'measure':'dcf_discount_closure','value':None,'met':None}
        claim=scenario_claim();claim['objective_id']='dcf_goal'
        plan,raw=prepared(evidence,claim)
        out=report.compile_report(plan,raw)
        self.assertEqual(out['claims'][0]['facts']['necessary'],'UNDETERMINED')
        self.assertIn('DCF discount closure is unavailable',out['report'])
        plan['segments'][0]['claim']['assertion']='sufficient'
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_SUFFICIENCY'):
            report.compile_report(plan,raw)

    def test_retained_row_boolean_cannot_disagree_with_numeric_goal(self):
        evidence=scenario_output();evidence['rows'][0]['objectives']['return_goal']['met']=True
        plan,raw=prepared(evidence,scenario_claim())
        with self.assertRaisesRegex(ValueError,'ROW_RESULT_CONTRADICTION'):
            report.compile_report(plan,raw)

    def test_no_success_and_no_condition_are_not_vacuous_proofs(self):
        evidence=scenario_output()
        for row in evidence['rows']:
            row['objectives']['return_goal'].update(value=-1,met=False)
        claim=scenario_claim();claim['conditions'][0]['value']=0.9
        plan,raw=prepared(evidence,claim)
        facts=report.compile_report(plan,raw)['claims'][0]['facts']
        self.assertEqual(facts['necessary'],'NO_SUCCESS_WITNESS')
        self.assertEqual(facts['sufficient'],'NO_CONDITION_WITNESS')

    def test_dated_share_arithmetic_cannot_be_eps_or_pe(self):
        for label in ['basic_eps','diluted_eps','pe']:
            claim={'id':'accounting','kind':'accounting_label','label':label,'evidence':{'artifact':'e','pointer':''}}
            plan,raw=prepared(accounting_output(),claim)
            with self.subTest(label=label), self.assertRaisesRegex(ValueError,'UNSUPPORTED_ACCOUNTING_LABEL'):
                report.compile_report(plan,raw)

    def test_diagnostic_preserves_unit_and_classification_limit(self):
        claim={'id':'accounting','kind':'accounting_label','label':'diagnostic_ratio','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(accounting_output(),claim)
        text=report.compile_report(plan,raw)['report']
        self.assertIn('Unscaled diagnostic',text);self.assertIn('not established reported EPS or P/E',text)

    def test_explicit_eps_permission_does_not_grant_pe(self):
        evidence=accounting_output();evidence.update(classification='DILUTED_EPS_SOURCE_BOUND',eps=3,
                                                   allowed_claims=['diluted_eps'],reasons=[])
        evidence['bound_fields']['shares']['basis']['value']='weighted_average_diluted'
        evidence['bound_fields']['income']['attribution']['value']='diluted_income_available_to_common'
        claim={'id':'accounting','kind':'accounting_label','label':'diluted_eps','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(evidence,claim)
        self.assertIn('Retained fields classify as diluted_eps',report.compile_report(plan,raw)['report'])
        plan['segments'][0]['claim']['label']='pe'
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_ACCOUNTING_LABEL'):report.compile_report(plan,raw)

    def test_stale_or_omitted_selected_cohort_is_rejected(self):
        for selected in [['house-a-old','house-b'],['house-a-new'],['house-a-new','house-a-new']]:
            claim={'id':'cohort','kind':'analyst_cohort','evidence':{'artifact':'e','pointer':''},'assert_record_ids':selected}
            plan,raw=prepared(cohort_output(),claim)
            with self.subTest(selected=selected), self.assertRaisesRegex(ValueError,'STALE_OR_OMITTED'):
                report.compile_report(plan,raw)

    def test_renderer_includes_all_selected_rows_and_exclusions(self):
        claim={'id':'cohort','kind':'analyst_cohort','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(cohort_output(),claim)
        text=report.compile_report(plan,raw)['report']
        self.assertIn('target 41',text);self.assertIn('target 38',text)
        self.assertIn('SUPERSEDED_FIRM_TARGET',text)

    def test_unresolved_or_unsupported_corpus_blocks_latest_claim(self):
        for field in ['unresolved_candidate_ids','unlinked_record_ids']:
            evidence=cohort_output();evidence['coverage'][field]=['pending']
            claim={'id':'cohort','kind':'analyst_cohort','evidence':{'artifact':'e','pointer':''}}
            plan,raw=prepared(evidence,claim)
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_CORPUS'):report.compile_report(plan,raw)

    def test_exact_saved_report_still_does_not_certify_source_or_prose_truth(self):
        plan,raw=prepared(scenario_output(),scenario_claim())
        text=report.compile_report(plan,raw)['report'].encode()
        audit=report.audit_saved_report(plan,raw,text)
        self.assertEqual(audit['status'],'EXACT_BOUND_REPORT')
        self.assertFalse(audit['whole_report_semantic_pass'])
        self.assertFalse(audit['source_authenticity_verified'])

    def test_edited_duplicate_removed_and_appended_claims_fail_saved_byte_audit(self):
        plan,raw=prepared(scenario_output(),scenario_claim());text=report.compile_report(plan,raw)['report']
        for edited in [text.replace('REFUTED','PROVEN'),text+text,'',text+'A new unsupported conclusion.']:
            with self.subTest(length=len(edited)):
                out=report.audit_saved_report(plan,raw,edited.encode())
                self.assertEqual(out['status'],'SAVED_REPORT_MISMATCH');self.assertTrue(out['differences'])

    def test_registered_contradictory_free_text_always_remains_unaudited(self):
        plan,raw=prepared(scenario_output(),scenario_claim())
        plan['segments'].append({'unverified':'Both conditions are universally necessary for a different valuation goal.'})
        compiled=report.compile_report(plan,raw)
        out=report.audit_saved_report(plan,raw,compiled['report'].encode())
        self.assertEqual(out['status'],'PARTIAL_UNAUDITED_PROSE')
        span=out['unverified_spans'][0]
        self.assertEqual(compiled['report'][span['start']:span['end']],plan['segments'][1]['unverified'])
        self.assertFalse(out['whole_report_semantic_pass'])

    def test_hash_substitution_and_duplicate_claim_identity_rejected(self):
        plan,raw=prepared(scenario_output(),scenario_claim())
        changed={'e':raw['e']+b' '}
        with self.assertRaisesRegex(ValueError,'ARTIFACT_HASH_OR_SIZE'):report.compile_report(plan,changed)
        plan['segments'].append(deepcopy(plan['segments'][0]))
        with self.assertRaisesRegex(ValueError,'UNIQUE_SAFE_CLAIM_ID'):report.compile_report(plan,raw)

    def test_hand_edited_accounting_permission_cannot_override_retained_basis(self):
        evidence=accounting_output();evidence.update(classification='DILUTED_EPS_SOURCE_BOUND',eps=3,
                                                   allowed_claims=['diluted_eps'],reasons=[])
        claim={'id':'accounting','kind':'accounting_label','label':'diluted_eps','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(evidence,claim)
        with self.assertRaisesRegex(ValueError,'ACCOUNTING_CONTRACT_REPLAY_MISMATCH'):
            report.compile_report(plan,raw)

    def test_omitted_corpus_record_cannot_be_hidden_by_no_asserted_record_list(self):
        evidence=cohort_output();evidence['coverage']['record_ids'].append('unprocessed-new-row')
        claim={'id':'cohort','kind':'analyst_cohort','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(evidence,claim)
        with self.assertRaisesRegex(ValueError,'COHORT_COVERAGE_PARTITION_MISMATCH'):
            report.compile_report(plan,raw)

    def test_objective_target_units_and_definition_cannot_be_swapped(self):
        for mutation in ['unit','measure']:
            evidence=scenario_output()
            if mutation=='unit':evidence['objectives'][0]['target']['unit']='currency_per_share'
            else:evidence['objectives'][0]['definition']['measure']='dcf_discount_closure'
            plan,raw=prepared(evidence,scenario_claim())
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError,'OBJECTIVE_'):
                report.compile_report(plan,raw)

    def test_decimal_string_serialization_preserves_objective_target_binding(self):
        evidence=scenario_output()
        evidence['objectives'][0]['target']=dict(evidence['objectives'][0]['target'],value='0')
        for row in evidence['rows']:row['objectives']['return_goal']['target']='0'
        plan,raw=prepared(evidence,scenario_claim())
        self.assertEqual(report.compile_report(plan,raw)['claims'][0]['facts']['necessary'],'REFUTED')

    def test_serialized_numeric_accounting_roles_only_are_decoded(self):
        evidence=accounting_output()
        evidence['bound_fields']['income']['value']['value']='9.0'
        evidence['bound_fields']['shares']['value']['value']='3.0'
        for group in ('income','shares'):
            evidence['bound_fields'][group]['unit_scale']['value']='1e3'
            evidence['bound_fields'][group]['issuer']['value']='314'
        claim={'id':'ratio','kind':'accounting_label','label':'diagnostic_ratio','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(evidence,claim)
        self.assertEqual(report.compile_report(plan,raw)['claims'][0]['facts']['value'],3)
        self.assertEqual(evidence['bound_fields']['income']['issuer']['value'],'314')

    def test_malformed_or_nonfinite_serialized_operands_are_rejected(self):
        claim={'id':'ratio','kind':'accounting_label','label':'diagnostic_ratio','evidence':{'artifact':'e','pointer':''}}
        for bad in ['NaN','Infinity','-Infinity','1_000',' 9 ','nine','01']:
            evidence=accounting_output();evidence['bound_fields']['income']['value']['value']=bad
            plan,raw=prepared(evidence,claim)
            with self.subTest(value=bad),self.assertRaises(ValueError):report.compile_report(plan,raw)

    def test_real_source_cli_decimal_output_renders_and_audits(self):
        producer=Path(sys.modules['source_claims'].__file__)
        consumer=Path(report.__file__)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            source={group:{field:r['value'] for field,r in rows.items()}
                    for group,rows in accounting_output()['bound_fields'].items()}
            source['income']['value']=13.2;source['shares']['value']=3.3
            source['shares']['basis']='weighted_average_basic'
            for group in ('income','shares'):source[group]['unit_scale']=1000.0
            def save(name,obj):
                (root/name).write_text(json.dumps(obj),encoding='utf-8')
                return hashlib.sha256((root/name).read_bytes()).hexdigest()
            source_hash=save('source.json',source)
            pin=save('manifest.json',{'schema_version':1,'sources':[
                {'id':'fictional','path':'source.json','format':'json','sha256':source_hash}]})
            request={group:{field:{'source_id':'fictional','pointer':'/'+group+'/'+field}
                            for field in fields} for group,fields in source.items()}
            request['operation']='accounting';save('request.json',request)
            env=dict(os.environ,PYTHONPATH=os.pathsep.join([str(consumer.parent),str(producer.parent)]))
            def run(*args):
                result=subprocess.run([sys.executable,'-B',*map(str,args)],capture_output=True,env=env)
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            run(producer,'--manifest',root/'manifest.json','--manifest-sha256',pin,
                '--source-root',root,'--input',root/'request.json','--output',root/'accounting.json')
            actual=json.loads((root/'accounting.json').read_bytes())
            self.assertEqual(actual['classification'],'BASIC_EPS_SOURCE_BOUND')
            self.assertEqual(actual['bound_fields']['income']['value']['value'],'13.2')
            self.assertEqual(actual['bound_fields']['shares']['unit_scale']['value'],'1000.0')
            save('plan.json',{'artifacts':{'e':{'path':'accounting.json',
                  'sha256':hashlib.sha256((root/'accounting.json').read_bytes()).hexdigest()}},
                  'segments':[{'claim':{'id':'eps','kind':'accounting_label','label':'basic_eps',
                     'evidence':{'artifact':'e','pointer':''}}}]})
            run(consumer,'render',root/'plan.json',root,root/'render.json','--report',root/'report.md')
            run(consumer,'audit',root/'plan.json',root,root/'audit.json','--report',root/'report.md')
            audit=json.loads((root/'audit.json').read_bytes())
            self.assertEqual(audit['status'],'EXACT_BOUND_REPORT')
            self.assertFalse(audit['whole_report_semantic_pass'])

    def test_presence_candidate_is_not_erased_by_missing_adapter_binding(self):
        claim={'id':'presence','kind':'source_presence','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(presence_output(),claim)
        out=report.compile_report(plan,raw)
        self.assertIn('SOURCE_CANDIDATE_PRESENT',out['report'])
        self.assertIn('UNBOUND',out['report']);self.assertIn('/customer_revenue_fraction',out['report'])
        self.assertFalse(out['claims'][0]['facts']['source_absence_established'])

    def test_no_match_and_incomplete_scan_never_authorize_absence(self):
        for found in (False,True):
            for incomplete in (False,True):
                claim={'id':'presence','kind':'source_presence','evidence':{'artifact':'e','pointer':''}}
                plan,raw=prepared(presence_output(found,incomplete),claim)
                out=report.compile_report(plan,raw)
                self.assertIn('does not establish source absence',out['report'])
                self.assertEqual(bool(out['claims'][0]['facts']['unsupported_sources']),incomplete)
                plan['segments'][0]['claim']['assertion']='source_absent'
                with self.assertRaisesRegex(ValueError,'UNSUPPORTED_PRESENCE_ASSERTION'):
                    report.compile_report(plan,raw)

    def test_presence_adapter_value_permission_is_separate_from_lexical_search(self):
        claim={'id':'presence','kind':'source_presence','assertion':'adapter_value_bound',
               'evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(presence_output(False,False,'EXACT_SOURCE_VALUE'),claim)
        self.assertIn('NO_CONFIGURED_LEXICAL_MATCH',report.compile_report(plan,raw)['report'])
        plan,raw=prepared(presence_output(True,False,'UNBOUND'),claim)
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_PRESENCE_ASSERTION'):report.compile_report(plan,raw)

    def test_presence_hand_edited_absence_or_semantic_completeness_fails(self):
        for field in ('absence','semantic','predicate','facts'):
            evidence=presence_output()
            if field=='absence':evidence['source_absence_established']=True
            elif field=='semantic':evidence['scan']['semantic_completeness_verified']=True
            elif field=='predicate':evidence['predicate']='NO_CONFIGURED_LEXICAL_MATCH'
            else:evidence['facts'][0]['source_refs']=[]
            claim={'id':'presence','kind':'source_presence','evidence':{'artifact':'e','pointer':''}}
            plan,raw=prepared(evidence,claim)
            with self.subTest(field=field),self.assertRaises(ValueError):report.compile_report(plan,raw)

    def test_edited_presence_sentence_is_a_saved_report_mismatch(self):
        claim={'id':'presence','kind':'source_presence','evidence':{'artifact':'e','pointer':''}}
        plan,raw=prepared(presence_output(),claim)
        saved=report.compile_report(plan,raw)['report'].replace('does not establish source absence','establishes source absence')
        self.assertEqual(report.audit_saved_report(plan,raw,saved.encode())['status'],'SAVED_REPORT_MISMATCH')


if __name__=='__main__':unittest.main()
