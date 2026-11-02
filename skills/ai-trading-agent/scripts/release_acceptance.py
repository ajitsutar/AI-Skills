"""Bounded release fixtures, actual response-file comparison and rights inventory.

No installation, downloads, broker connection, permission grant or commercial
certification. An offline regression is not an investment-performance validation.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib
import json
import math
from pathlib import Path
import platform
import sys
from experiment_registry import digest, require, stamp, hash_value

OPERATIONS={'planning.allocate':('allocation_policy','allocate'),
            'planning.cash_projection':('planning_alignment','cash_projection'),
            'experiment.overlap_review':('experiment_registry','overlap_review')}

def pointer(value,path):
    require(isinstance(path,str) and (path=='' or path.startswith('/')),'JSON_POINTER_REQUIRED')
    for token in path.split('/')[1:]:
        token=token.replace('~1','/').replace('~0','~')
        value=value[int(token)] if isinstance(value,list) else value[token]
    return value

def equal(actual,expected,atol,rtol):
    if type(actual) in (int,float) and type(expected) in (int,float):
        return math.isfinite(actual) and math.isfinite(expected) and math.isclose(actual,expected,abs_tol=atol,rel_tol=rtol)
    if type(actual)!=type(expected):return False
    if isinstance(actual,list):return len(actual)==len(expected) and all(equal(a,b,atol,rtol) for a,b in zip(actual,expected))
    if isinstance(actual,dict):return set(actual)==set(expected) and all(equal(actual[k],expected[k],atol,rtol) for k in actual)
    return actual==expected

def run_fixtures(document,output_dir):
    require(set(document)=={'schema_version','fixtures'},'FIXTURE_FIELDS')
    require(document['schema_version']==1 and isinstance(document['fixtures'],list) and document['fixtures'],'FIXTURE_SCHEMA')
    rows=document['fixtures'];require(len({x['id'] for x in rows})==len(rows),'DUPLICATE_FIXTURE_ID')
    out=Path(output_dir).resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'input.json').write_text(json.dumps(document,indent=2,allow_nan=False),encoding='utf-8')
    results=[]
    for row in rows:
        require(set(row)=={'id','operation','inputs','expect','absolute_tolerance','relative_tolerance'},'FIXTURE_ROW_FIELDS')
        require(row['operation'] in OPERATIONS,'OPERATION_NOT_ALLOWLISTED')
        require(isinstance(row['expect'],dict) and row['expect'],'EXPECTED_PROJECTIONS_REQUIRED')
        for k in ['absolute_tolerance','relative_tolerance']:
            require(type(row[k]) in (float,int) and math.isfinite(row[k]) and row[k]>=0,'FINITE_NONNEGATIVE_TOLERANCE')
        module_name,function=OPERATIONS[row['operation']];entry={'id':row['id'],'operation':row['operation']}
        try:
            module=importlib.import_module(module_name);actual=getattr(module,function)(row['inputs'])
            entry['implementation_sha256']=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            entry['actual_result']=actual
            comparisons=[]
            for path,expected in row['expect'].items():
                try:
                    value=pointer(actual,path);passed=equal(value,expected,row['absolute_tolerance'],row['relative_tolerance'])
                    comparisons.append({'pointer':path,'actual':value,'expected':expected,'passed':passed})
                except (KeyError,IndexError,ValueError,TypeError):comparisons.append({'pointer':path,'passed':False,'error':'RESULT_POINTER_MISSING'})
            entry.update(checks=comparisons,status='pass' if all(x['passed'] for x in comparisons) else 'fail')
        except Exception as exc:
            entry.update(status='fail',error_type=type(exc).__name__,error=str(exc))
        results.append(entry)
    report={'schema_version':1,'status':'OFFLINE_FIXTURES_PASSED' if all(r['status']=='pass' for r in results) else 'OFFLINE_FIXTURES_FAILED','input_sha256':digest(document),'python':sys.version,'platform':platform.platform(),'results':results,'production_readiness_established':False,'predictive_skill_established':False,'limitation':'Actual local fixture calls only. No clean-install claim unless a separately observed fresh environment receipt establishes it.'}
    (out/'result.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report

def rights_inventory(document):
    """Review declared permitted uses and evidence dates without granting rights."""
    require(set(document)=={'schema_version','as_of','intended_use','sources'},'RIGHTS_FIELDS')
    require(document['schema_version']==1,'SCHEMA_VERSION');now=stamp(document['as_of'])
    require(document['intended_use'] in {'personal_research','commercial_internal','redistribution'},'INTENDED_USE_REQUIRED')
    rows=document['sources'];require(isinstance(rows,list),'SOURCE_ARRAY_REQUIRED')
    require(len({r['id'] for r in rows})==len(rows),'DUPLICATE_SOURCE_ID')
    results=[]
    for r in rows:
        fields={'id','provider','artifact_kind','source_url','terms_url','terms_sha256','terms_observed_at','valid_until','permitted_uses','review_status','reviewer','attribution','retention_days','evidence_ref'}
        require(set(r)==fields,'RIGHTS_ROW_FIELDS')
        require(all(isinstance(r[k],str) and r[k].strip() for k in ['id','provider']),'SOURCE_ID_AND_PROVIDER_REQUIRED')
        require(r['artifact_kind'] in {'code','dependency','market_data','article','analyst_report','model_weights'},'ARTIFACT_KIND')
        require(r['review_status'] in {'permitted','restricted','unknown'},'REVIEW_STATUS')
        require(isinstance(r['permitted_uses'],list) and set(r['permitted_uses'])<={'personal_research','commercial_internal','redistribution'},'PERMITTED_USE_VALUES')
        require(r['retention_days'] is None or (type(r['retention_days']) is int and r['retention_days']>=0),'RETENTION_DAYS')
        reasons=[]
        for key in ['source_url','terms_url','terms_sha256','terms_observed_at','valid_until','reviewer','evidence_ref']:
            if not r[key]:reasons.append('MISSING_'+key.upper())
        if r['terms_sha256'] is not None:hash_value(r['terms_sha256'])
        if r['terms_observed_at'] is not None and stamp(r['terms_observed_at'])>now:reasons.append('FUTURE_TERMS_OBSERVATION')
        if r['valid_until'] is not None and stamp(r['valid_until'])<=now:reasons.append('REVIEW_EXPIRED')
        if r['review_status']!='permitted':reasons.append('USE_NOT_REVIEWED_AS_PERMITTED')
        if document['intended_use'] not in r['permitted_uses']:reasons.append('INTENDED_USE_NOT_LISTED')
        results.append({'id':r['id'],'status':'DECLARED_EVIDENCE_CURRENT' if not reasons else 'UNRESOLVED_OR_RESTRICTED','reasons':reasons})
    return {'input_sha256':digest(document),'sources':results,'inventory_complete':bool(rows) and all(x['status']=='DECLARED_EVIDENCE_CURRENT' for x in results),'rights_granted':False,'legal_compliance_certified':False,'source_evidence_authenticated':False,'limitation':'Evaluates caller-supplied review records only. Does not fetch terms, authenticate receipts, interpret licenses, or permit redistribution.'}

HOST_CHECKS={'numeric_results','universe','dates_and_availability','units_and_denominators','source_access','assumptions','exclusions','recommendation_limits','artifact_export'}

def grade_response(document):
    """Pure strict-JSON fixture grading; does not authenticate a host invocation."""
    require(set(document)=={'response_text','expected','absolute_tolerance','relative_tolerance'},'GRADE_FIELDS')
    require(isinstance(document['response_text'],str) and isinstance(document['expected'],dict),'RESPONSE_TEXT_AND_EXPECTED_OBJECT_REQUIRED')
    for k in ['absolute_tolerance','relative_tolerance']:
        require(type(document[k]) in (int,float) and math.isfinite(document[k]) and document[k]>=0,'FINITE_NONNEGATIVE_TOLERANCE')
    def pairs(values):
        obj={}
        for k,v in values:
            require(k not in obj,'DUPLICATE_RESPONSE_KEY');obj[k]=v
        return obj
    sha=hashlib.sha256(document['response_text'].encode('utf-8')).hexdigest()
    try:
        actual=json.loads(document['response_text'],object_pairs_hook=pairs,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('NONFINITE_RESPONSE_VALUE')))
        passed=equal(actual,document['expected'],document['absolute_tolerance'],document['relative_tolerance'])
        return {'status':'FIXTURE_MATCH' if passed else 'FIXTURE_MISMATCH','response_text_sha256':sha,'actual':actual,'expected':document['expected'],'external_invocation_authenticated':False,'scope':'Only this supplied fictional fixture and response; no model equivalence or investment-performance claim.'}
    except (ValueError,TypeError) as exc:
        return {'status':'UNGRADABLE_RESPONSE','response_text_sha256':sha,'error':str(exc),'external_invocation_authenticated':False}

def compare_host_responses(document,root):
    """Hash actual retained host responses; independent semantic review is explicit."""
    require(set(document)=={'schema_version','expected_hosts','prompt_sha256','input_bundle_sha256','captures'},'HOST_FIELDS')
    require(document['schema_version']==1,'SCHEMA_VERSION')
    expected=document['expected_hosts'];require(isinstance(expected,list) and expected and len(set(expected))==len(expected),'UNIQUE_EXPECTED_HOSTS')
    hash_value(document['prompt_sha256']);hash_value(document['input_bundle_sha256'])
    captures=document['captures'];require(isinstance(captures,list),'CAPTURES_REQUIRED')
    require(len({c['host'] for c in captures})==len(captures),'DUPLICATE_HOST_CAPTURE')
    require({c['host'] for c in captures}<=set(expected),'UNEXPECTED_HOST')
    base=Path(root).resolve();results=[]
    for host in expected:
        c=next((x for x in captures if x['host']==host),None)
        if c is None:results.append({'host':host,'status':'NOT_RUN'});continue
        require(set(c)=={'host','model','model_version','observed_at','prompt_sha256','input_bundle_sha256','response_path','response_sha256','checks','independence_limits'},'HOST_CAPTURE_FIELDS')
        stamp(c['observed_at']);hash_value(c['response_sha256'])
        require(isinstance(c['independence_limits'],list),'INDEPENDENCE_LIMITS_REQUIRED')
        path=(base/c['response_path']).resolve();require(path.is_relative_to(base),'RESPONSE_PATH_OUTSIDE_EVIDENCE_ROOT')
        checks=c['checks'];require(isinstance(checks,list) and len({x['id'] for x in checks})==len(checks),'UNIQUE_HOST_CHECKS')
        require(all(set(x)=={'id','outcome','reviewer','evidence_ref'} and x['id'] in HOST_CHECKS and x['outcome'] in {'pass','fail','not_reviewed'} for x in checks),'HOST_CHECK_FIELDS')
        reasons=[];observed_sha=None
        if not path.is_file():reasons.append('RESPONSE_FILE_MISSING')
        elif path.stat().st_size>50*1024*1024:reasons.append('RESPONSE_SIZE_LIMIT')
        else:
            observed_sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if observed_sha!=c['response_sha256']:reasons.append('RESPONSE_BYTES_CHANGED')
        if c['prompt_sha256']!=document['prompt_sha256'] or c['input_bundle_sha256']!=document['input_bundle_sha256']:reasons.append('INPUT_CONTRACT_MISMATCH')
        if {x['id'] for x in checks}!=HOST_CHECKS:reasons.append('INCOMPLETE_SEMANTIC_REVIEW')
        if any(x['outcome']!='pass' or not x['reviewer'] or not x['evidence_ref'] for x in checks):reasons.append('REVIEW_NOT_PASSED')
        results.append({'host':host,'status':'RETAINED_RESPONSE_REVIEW_PASSED' if not reasons else 'INCOMPLETE_OR_FAILED','actual_response_sha256':observed_sha,'reasons':reasons,'independence_limits':c['independence_limits']})
    return {'input_sha256':digest(document),'hosts':results,'all_hosts_reviewed':all(x['status']=='RETAINED_RESPONSE_REVIEW_PASSED' for x in results),'model_equivalence_established':False,'external_invocations_authenticated':False,'limitation':'Actual response bytes checked locally; semantic grades and independence remain reviewer declarations. Unrun hosts stay NOT_RUN; matching prose is not independent predictive validation.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('fixtures');a.add_argument('input',type=Path);a.add_argument('output',type=Path)
    a=sub.add_parser('rights');a.add_argument('input',type=Path)
    a=sub.add_parser('hosts');a.add_argument('input',type=Path);a.add_argument('evidence_root',type=Path)
    a=sub.add_parser('grade');a.add_argument('input',type=Path)
    args=p.parse_args();doc=json.loads(args.input.read_text(encoding='utf-8-sig'))
    if args.command=='fixtures':result=run_fixtures(doc,args.output)
    elif args.command=='rights':result=rights_inventory(doc)
    elif args.command=='grade':result=grade_response(doc)
    else:result=compare_host_responses(doc,args.evidence_root)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
