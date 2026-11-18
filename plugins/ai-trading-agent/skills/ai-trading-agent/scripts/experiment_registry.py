"""Durable, local research-attempt and forward-capture evidence, never a trading gate.

Hashes bind retained bytes; they cannot prove a complete search history, authentic
source, external model invocation, or an honest system clock. No network access.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

SCHEMA = 2
MAX_BYTES = 50 * 1024 * 1024

def require(ok, message):
    if not ok: raise ValueError(message)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()

def stamp(value):
    require(isinstance(value, str), 'TIMESTAMP_REQUIRED')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(dt.tzinfo is not None and dt.utcoffset() is not None, 'TIMEZONE_REQUIRED')
    return dt.astimezone(timezone.utc)

def utcnow(): return datetime.now(timezone.utc).isoformat()

def identifier(value):
    require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',value), 'SAFE_IDENTIFIER_REQUIRED')
    return value

def hash_value(value):
    require(isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value), 'SHA256_REQUIRED')

def validate_attempt(document):
    """Validate one declared attempt contract; no artifact existence is inferred."""
    fields={'schema_version','attempt_id','campaign_id','parent_attempt_id','revision_reason','model','prompt_sha256','package_sha256','runtime_sha256','data_vintages','universe_sha256','constraints','selection','conventions','train_start','train_end','evaluation_start','evaluation_end','label_end','embargo_seconds','purpose'}
    require(isinstance(document,dict) and set(document)==fields,'ATTEMPT_FIELDS')
    require(document['schema_version']==SCHEMA,'SCHEMA_VERSION')
    for k in ['attempt_id','campaign_id']:identifier(document[k])
    if document['parent_attempt_id'] is not None:
        identifier(document['parent_attempt_id']);require(bool(document['revision_reason']),'REVISION_REASON_REQUIRED')
    for k in ['prompt_sha256','package_sha256','runtime_sha256','universe_sha256']:hash_value(document[k])
    require(isinstance(document['model'],dict) and set(document['model'])=={'host','name','version','settings'},'MODEL_CONTEXT_REQUIRED')
    require(all(isinstance(document['model'][k],str) and document['model'][k] for k in ['host','name','version']),'MODEL_LABELS_REQUIRED')
    require(isinstance(document['model']['settings'],dict),'MODEL_SETTINGS_REQUIRED')
    require(isinstance(document['data_vintages'],list) and document['data_vintages'],'DATA_VINTAGES_REQUIRED')
    require(len({x['id'] for x in document['data_vintages']})==len(document['data_vintages']),'DUPLICATE_VINTAGE')
    for row in document['data_vintages']:
        require(set(row)=={'id','sha256','available_at'},'VINTAGE_FIELDS');identifier(row['id']);hash_value(row['sha256']);stamp(row['available_at'])
    for k in ['constraints','selection']:require(isinstance(document[k],dict),'DECLARED_'+k.upper()+'_REQUIRED')
    conventions=document['conventions']
    require(isinstance(conventions,dict) and set(conventions)=={'accounting','benchmark','cash','dividends','costs'},'CONVENTIONS_REQUIRED')
    require(all(isinstance(v,str) and v.strip() for v in conventions.values()),'EXPLICIT_CONVENTION_DESCRIPTIONS_REQUIRED')
    require(document['purpose'] in {'development','holdout','forward_paper'},'PURPOSE_REQUIRED')
    dates=[stamp(document[k]) for k in ['train_start','train_end','evaluation_start','evaluation_end','label_end']]
    require(dates[0]<=dates[1]<dates[2]<=dates[3]<=dates[4],'ORDERED_WINDOWS_REQUIRED')
    embargo=document['embargo_seconds'];require(type(embargo) is int and embargo>=0,'NONNEGATIVE_EMBARGO')
    require((dates[2]-dates[1]).total_seconds()>=embargo,'EMBARGO_NOT_SATISFIED')
    late=[row['id'] for row in document['data_vintages'] if stamp(row['available_at'])>dates[2]]
    return {'status':'DECLARED_CONTRACT_VALID','input_sha256':digest(document),'preselection_vintages_available_after_evaluation_start':late,'point_in_time_inputs_established':False,'external_execution_verified':False,'search_completeness_established':False}

def overlap_review(document):
    """Compare registered train/evaluation/label windows, including abandoned trials.

    It identifies overlap; this is not a multiple-testing correction and cannot
    find experiments that were never registered.
    """
    require(set(document)=={'attempts'},'OVERLAP_FIELDS')
    rows=document['attempts'];require(isinstance(rows,list),'ATTEMPTS_REQUIRED')
    require(len({x['attempt_id'] for x in rows})==len(rows),'DUPLICATE_ATTEMPT')
    for row in rows:validate_attempt(row)
    warnings=[]
    for i,left in enumerate(rows):
        for right in rows[i+1:]:
            lo=max(stamp(left['evaluation_start']),stamp(right['evaluation_start']))
            hi=min(stamp(left['label_end']),stamp(right['label_end']))
            if lo<=hi:
                warnings.append({'left':left['attempt_id'],'right':right['attempt_id'],'kind':'EVALUATION_OR_LABEL_WINDOW_OVERLAP','overlap_start':lo.isoformat(),'overlap_end':hi.isoformat()})
            for training,testing in [(left,right),(right,left)]:
                if max(stamp(training['train_start']),stamp(testing['evaluation_start']))<=min(stamp(training['train_end']),stamp(testing['label_end'])):
                    warnings.append({'left':training['attempt_id'],'right':testing['attempt_id'],'kind':'TRAINING_OVERLAPS_OTHER_EVALUATION_LABELS'})
    return {'registered_attempt_count':len(rows),'warnings':warnings,'search_completeness_established':False,'all_trials_correction_computed':False,'limitation':'Only supplied registered trials inspected. Shared test observations and adapted constraints require disclosure; no number of tests proves independence.'}

class Registry:
    def __init__(self, root):
        self.root=Path(root).resolve()
        require(self.root.is_dir(),'REGISTRY_ROOT_MUST_ALREADY_EXIST')
        self.events=self.root/'events.json'
        self.blobs=self.root/'blobs'

    @contextmanager
    def lock(self):
        lock=self.root/'.writer-lock'
        try:lock.mkdir()
        except FileExistsError:raise ValueError('REGISTRY_WRITER_LOCKED_RECONCILE_OWNER_BEFORE_RETRY')
        try:
            (lock/'owner.json').write_text(json.dumps({'pid':os.getpid(),'at':utcnow()}))
            yield
        finally:
            (lock/'owner.json').unlink(missing_ok=True);lock.rmdir()

    def read(self):
        if not self.events.exists():return []
        rows=json.loads(self.events.read_text(encoding='utf-8'))
        require(isinstance(rows,list),'REGISTRY_ARRAY_REQUIRED')
        previous=None
        for i,row in enumerate(rows):
            require(set(row)=={'sequence','previous_sha256','recorded_at','kind','payload','sha256'},'EVENT_FIELDS')
            require(row['sequence']==i and row['previous_sha256']==previous,'CHAIN_SEQUENCE_MISMATCH')
            require(digest({k:v for k,v in row.items() if k!='sha256'})==row['sha256'],'CHAIN_HASH_MISMATCH')
            stamp(row['recorded_at']);previous=row['sha256']
            for artifact in row['payload'].get('artifacts',[]):
                hash_value(artifact['sha256']);path=self.blobs/artifact['sha256']
                require(path.is_file() and not path.is_symlink(),'MISSING_OR_REDIRECTED_ARTIFACT')
                data=path.read_bytes();require(len(data)==artifact['bytes'] and hashlib.sha256(data).hexdigest()==artifact['sha256'],'ARTIFACT_HASH_MISMATCH')
        return rows

    def _artifact(self,path,role):
        path=Path(path).resolve();require(path.is_file(),'ARTIFACT_FILE_REQUIRED')
        require(path.stat().st_size<=MAX_BYTES,'ARTIFACT_SIZE_LIMIT')
        data=path.read_bytes();require(len(data)<=MAX_BYTES,'ARTIFACT_SIZE_LIMIT')
        sha=hashlib.sha256(data).hexdigest();self.blobs.mkdir(exist_ok=True)
        require(not self.blobs.is_symlink() and self.blobs.resolve().is_relative_to(self.root),'BLOB_DIRECTORY_REDIRECTED')
        dst=self.blobs/sha
        if dst.exists():require(not dst.is_symlink() and dst.read_bytes()==data,'EXISTING_BLOB_MISMATCH')
        else:
            with dst.open('xb') as f:f.write(data)
        return {'role':role,'sha256':sha,'bytes':len(data),'original_name':path.name}

    def _append(self,rows,kind,payload):
        row={'sequence':len(rows),'previous_sha256':rows[-1]['sha256'] if rows else None,'recorded_at':utcnow(),'kind':kind,'payload':payload}
        row['sha256']=digest(row);rows=rows+[row]
        temp=self.root/('events-'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('x',encoding='utf-8') as f:
                json.dump(rows,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.events)
        finally:temp.unlink(missing_ok=True)
        return row

    def register(self,document,prompt_path):
        validate_attempt(document)
        with self.lock():
            rows=self.read();contracts=[r['payload']['contract'] for r in rows if r['kind']=='registered']
            require(document['attempt_id'] not in {x['attempt_id'] for x in contracts},'ATTEMPT_ALREADY_REGISTERED')
            if document['parent_attempt_id'] is not None:require(document['parent_attempt_id'] in {x['attempt_id'] for x in contracts},'PARENT_NOT_REGISTERED')
            artifact=self._artifact(prompt_path,'prompt')
            require(artifact['sha256']==document['prompt_sha256'],'PROMPT_BYTES_MISMATCH')
            if document['purpose']=='forward_paper':require(stamp(utcnow())<stamp(document['evaluation_start']),'FORWARD_REGISTRATION_TOO_LATE')
            return self._append(rows,'registered',{'contract':document,'artifacts':[artifact]})

    def record_result(self,attempt_id,status,result_path,accounting_path=None,benchmark_path=None):
        identifier(attempt_id);require(status in {'complete','failed','abandoned'},'TERMINAL_STATUS_REQUIRED')
        with self.lock():
            rows=self.read();require(any(r['kind']=='registered' and r['payload']['contract']['attempt_id']==attempt_id for r in rows),'UNKNOWN_ATTEMPT')
            require(not any(r['kind']=='result' and r['payload']['attempt_id']==attempt_id for r in rows),'RESULT_ALREADY_RECORDED_NEW_ATTEMPT_REQUIRED')
            require(status!='complete' or (accounting_path is not None and benchmark_path is not None),'COMPLETED_ACCOUNTING_AND_BENCHMARK_ARTIFACTS_REQUIRED')
            paths=[(result_path,'result_or_error')]+([(accounting_path,'accounting')] if accounting_path is not None else [])+([(benchmark_path,'benchmark')] if benchmark_path is not None else [])
            require(all(Path(p).is_file() for p,role in paths),'ARTIFACT_FILE_REQUIRED')
            artifacts=[self._artifact(p,role) for p,role in paths]
            return self._append(rows,'result',{'attempt_id':attempt_id,'status':status,'artifacts':artifacts,'external_execution_verified':False,'accounting_correctness_established':False})

    def capture_forward(self,attempt_id,decision_at,target_at,prediction_path):
        identifier(attempt_id)
        with self.lock():
            rows=self.read();reg=next((r for r in rows if r['kind']=='registered' and r['payload']['contract']['attempt_id']==attempt_id),None)
            require(reg is not None and reg['payload']['contract']['purpose']=='forward_paper','REGISTERED_FORWARD_ATTEMPT_REQUIRED')
            require(not any(r['kind']=='result' and r['payload']['attempt_id']==attempt_id for r in rows),'FORWARD_ATTEMPT_ALREADY_TERMINAL')
            now=stamp(utcnow());decision=stamp(decision_at);target=stamp(target_at);contract=reg['payload']['contract']
            require(stamp(reg['recorded_at'])<=decision<=now<target,'FORWARD_CAPTURE_NOT_BEFORE_TARGET')
            require(stamp(contract['evaluation_start'])<=decision<target<=stamp(contract['evaluation_end']),'FORWARD_CAPTURE_OUTSIDE_WINDOW')
            require(not any(r['kind']=='forward_capture' and r['payload']['attempt_id']==attempt_id and stamp(r['payload']['decision_at'])==decision for r in rows),'DUPLICATE_DECISION_CAPTURE')
            artifact=self._artifact(prediction_path,'prediction')
            return self._append(rows,'forward_capture',{'attempt_id':attempt_id,'decision_at':decision_at,'target_at':target_at,'artifacts':[artifact],'clock_authenticity_verified':False})

    def audit(self):
        rows=self.read();contracts=[r['payload']['contract'] for r in rows if r['kind']=='registered']
        results={r['payload']['attempt_id']:r['payload']['status'] for r in rows if r['kind']=='result'}
        overlaps=overlap_review({'attempts':contracts});assessments=[]
        for contract in contracts:
            attempt=contract['attempt_id'];registration=next(r for r in rows if r['kind']=='registered' and r['payload']['contract']['attempt_id']==attempt)
            timely=stamp(registration['recorded_at'])<stamp(contract['evaluation_start'])
            late=validate_attempt(contract)['preselection_vintages_available_after_evaluation_start']
            related=[w for w in overlaps['warnings'] if attempt in (w['left'],w['right'])]
            if contract['purpose']=='development':status='DEVELOPMENT_NOT_UNTOUCHED_HOLDOUT'
            elif not timely:status='LATE_REGISTERED_NOT_UNTOUCHED_HOLDOUT'
            elif late:status='FUTURE_PRESELECTION_INPUTS_NOT_UNTOUCHED_HOLDOUT'
            elif related:status='REGISTERED_OVERLAP_NOT_UNTOUCHED_HOLDOUT'
            else:status='LOCALLY_PROSPECTIVE_CONTRACT_ONLY'
            assessments.append({'attempt_id':attempt,'status':status,'registered_before_evaluation':timely,'late_preselection_vintages':late,'related_registered_overlap_count':len(related),'globally_untouched_holdout_established':False})
        return {'status':'RETAINED_CHAIN_AND_BYTES_VERIFIED','events':len(rows),'registered_attempts':len(contracts),'outcomes':{x['attempt_id']:results.get(x['attempt_id'],'open') for x in contracts},'overlap':overlaps,'holdout_assessments':assessments,'last_event_sha256':rows[-1]['sha256'] if rows else None,'limitations':['Append-only API; filesystem owner can replace an entire history. Hash chain is not trusted timestamping.','Registry cannot discover unregistered experiments or authenticate external invocations.','Forward capture is local-clock evidence, not independently notarized performance.','All contract data_vintages are declared preselection inputs. Streaming information and outcomes must be separately timestamped in captures; do not predeclare future-known input bytes as available.'],'execution_authorized':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);sub=p.add_subparsers(dest='command',required=True)
    a=sub.add_parser('register');a.add_argument('contract',type=Path);a.add_argument('prompt',type=Path)
    a=sub.add_parser('result');a.add_argument('attempt_id');a.add_argument('status',choices=['complete','failed','abandoned']);a.add_argument('artifact',type=Path);a.add_argument('--accounting',type=Path);a.add_argument('--benchmark',type=Path)
    a=sub.add_parser('forward');a.add_argument('attempt_id');a.add_argument('decision_at');a.add_argument('target_at');a.add_argument('prediction',type=Path)
    sub.add_parser('audit');args=p.parse_args();r=Registry(args.root)
    if args.command=='register':result=r.register(json.loads(args.contract.read_text(encoding='utf-8-sig')),args.prompt)
    elif args.command=='result':result=r.record_result(args.attempt_id,args.status,args.artifact,args.accounting,args.benchmark)
    elif args.command=='forward':result=r.capture_forward(args.attempt_id,args.decision_at,args.target_at,args.prediction)
    else:result=r.audit()
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
