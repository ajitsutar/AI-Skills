"""Offline supplied-corpus producer, fixed report and original-source replay.

Does not accept cached producer results, authenticate sources, grade free prose,
submit orders, or contact a network. Outputs are private and append-only.
"""
from pathlib import Path,PurePosixPath
from decimal import Decimal
import argparse,hashlib,importlib,json,os,stat,sys
from source_lineage import load_manifest,parse

ROOT=Path(__file__).resolve().parent.parent
METHOD='supplied-research-1'
PRODUCERS={'analyst_sources':'analyze','reit_sources':'analyze','source_claims':'audit','issuer_evidence':'analyze','market_flow_report':'analyze','institutional_report':'analyze','market_sources_report':'analyze'}
MAX_FILE=16*1024*1024;MAX_TOTAL=128*1024*1024;MAX_REPORT=1024*1024

def require(value,message):
    if not value:raise ValueError(message)
def digest(raw):return hashlib.sha256(raw).hexdigest()
def encode(value):
    def scalar(item):
        if isinstance(item,Decimal) and item.is_finite():return str(item)
        raise ValueError('UNSUPPORTED_OR_NONFINITE_RESULT_VALUE')
    return (json.dumps(value,sort_keys=True,indent=2,ensure_ascii=True,allow_nan=False,default=scalar)+'\n').encode('utf-8')
def safe(path):
    path=Path(path).absolute()
    for item in (*reversed(path.parents),path):
        try:info=item.lstat()
        except FileNotFoundError:continue
        require(not stat.S_ISLNK(info.st_mode) and not (getattr(info,'st_file_attributes',0)&1024),'LINKED_PATH_NOT_ALLOWED')
    return path.resolve(strict=False)
def read(path,limit=MAX_FILE):
    path=safe(path);require(path.is_file() and path.stat().st_size<=limit,'FILE_MISSING_OR_TOO_LARGE')
    raw=path.read_bytes();require(len(raw)<=limit,'FILE_TOO_LARGE');return raw
def write(root,name,raw):
    path=safe(root/name);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
def relative(name):
    p=PurePosixPath(name)
    require(isinstance(name,str) and bool(name) and not p.is_absolute() and '..' not in p.parts and
            ':' not in name and '\\' not in name and p.as_posix()==name,'UNSAFE_SOURCE_PATH')
    return name
def request(raw):
    doc=parse(raw)
    require(isinstance(doc,dict) and {'producer','producer_request'}<=set(doc) and
            set(doc)<={'producer','producer_request','unverified_prose'},'EXACT_REQUEST_FIELDS_REQUIRED')
    require(doc['producer'] in PRODUCERS and isinstance(doc['producer_request'],dict),'UNSUPPORTED_PRODUCER_OR_REQUEST')
    if 'unverified_prose' in doc:
        require(isinstance(doc['unverified_prose'],str) and doc['unverified_prose'].strip() and
                len(doc['unverified_prose'].encode())<=128*1024,'INVALID_UNVERIFIED_PROSE')
    return doc
def implementations():
    # Pin the installed Python implementation closure conservatively. No modules
    # are imported merely to inventory them; docs/tests are not execution inputs.
    return {p.name:digest(read(p)) for p in sorted((ROOT/'scripts').glob('*.py'))}
def produce(doc,manifest,pin,source_root):
    module=importlib.import_module(doc['producer'])
    require(Path(module.__file__).resolve()==(ROOT/'scripts'/(doc['producer']+'.py')).resolve(),'PRODUCER_OUTSIDE_SKILL')
    result=getattr(module,PRODUCERS[doc['producer']])(doc['producer_request'],manifest,pin,source_root)
    require(isinstance(result,dict),'PRODUCER_RESULT_OBJECT_REQUIRED')
    require(len(encode(result))<=MAX_FILE,'RESULT_TOO_LARGE')
    return result
def claim_summary(result):
    # A small fixed projection for the older source_claims producer. Complete
    # fields and lexical references remain in result.json, not recopied prose.
    keys=('operation','claim_verdict','classification','predicate','binding_state','binding_reason','status',
          'eps','raw_operand_ratio','allowed_claims','unsupported_claims','reasons','unresolved_candidate_ids',
          'unlinked_record_ids','source_absence_established','latest_selection_scope','limits')
    lines=['## Source claim assessment']
    for key in keys:
        if key in result:lines.append('- '+key+': '+json.dumps(result[key],ensure_ascii=True,default=str))
    scan=result.get('scan',result.get('coverage',{}).get('scan'))
    if isinstance(scan,dict):
        lines.append('- Configured lexical candidates: '+str(len(scan.get('candidates',[]))))
        lines.append('- Unsupported sources: '+json.dumps(scan.get('unsupported_sources',[]),ensure_ascii=True,default=str))
    lines.append('Source absence, whole-corpus semantic completeness and issuer authenticity are not established.')
    return '\n'.join(lines)+'\n'
def render(doc,result):
    if doc['producer']=='source_claims':body=claim_summary(result)
    else:
        report=result.get('report')
        require(isinstance(report,dict) and isinstance(report.get('text'),str) and report['text'].strip(),
                'PRODUCER_FIXED_REPORT_REQUIRED')
        body=report['text']
        require(report.get('sha256')==digest(body.encode('utf-8')),'PRODUCER_REPORT_HASH_MISMATCH')
        require(report.get('whole_report_semantic_pass') is False,'PRODUCER_REPORT_LIMIT_REQUIRED')
    text='# Supplied-source research\n\n'+body.rstrip()+'\n\n'
    text+='[Complete structured evidence](result.json) preserves the producer fields, source bindings and unresolved findings.\n'
    text+='Source replay checks the declared contract against retained bytes; it does not authenticate issuers or certify investment conclusions.\n'
    if 'unverified_prose' in doc:
        text+='\n## Unaudited prose\n\nThe following text is not certified by the source or report checks.\n\n'+doc['unverified_prose']+'\n'
    raw=text.encode('utf-8');require(len(raw)<=MAX_REPORT,'REPORT_TOO_LARGE');return raw
def file_inventory(root):
    result={}
    for path in sorted(root.rglob('*')):
        safe(path)
        if path.is_file() and path!=root/'receipt.json':result[path.relative_to(root).as_posix()]=digest(read(path))
    return result
def audit(directory,context):
    require(context['method']==METHOD and implementations()==context['implementation_sha256'],'IMPLEMENTATION_CHANGED')
    raw=read(directory/'original-request.json');require(digest(raw)==context['request_sha256'],'RETAINED_REQUEST_CHANGED')
    doc=request(raw);require(doc['producer']==context['producer'],'PRODUCER_IDENTITY_CHANGED')
    replay=produce(doc,directory/'ingress.json',context['manifest_sha256'],directory/'originals')
    require(encode(replay)==read(directory/'result.json'),'ORIGINAL_SOURCE_REPLAY_MISMATCH')
    expected=render(doc,replay);saved=read(directory/'report.md',MAX_REPORT)
    require(saved==expected,'SAVED_REPORT_MISMATCH')
    require(implementations()==context['implementation_sha256'],'IMPLEMENTATION_CHANGED_DURING_REPLAY')
    return {'method':METHOD,'status':'SOURCE_REPLAY_AND_SAVED_REPORT_MATCH','producer':doc['producer'],
            'original_manifest_sha256':context['manifest_sha256'],'request_sha256':context['request_sha256'],
            'result_sha256':digest(encode(replay)),'saved_report_sha256':digest(saved),
            'free_prose_status':'UNAUDITED_PROSE_PRESENT' if 'unverified_prose' in doc else 'NO_EXTRA_FREE_PROSE',
            'whole_report_semantic_pass':False,'source_authenticity_verified':False,'execution_authorized':False,
            'limits':['Exact replay of the declared producer and report, not proof of complete source interpretation or user-request coverage.',
                      'Producer partial, rejected, diagnostic and unknown results retain their original meaning; matching replay does not upgrade them.']}

def run(request_path,output_dir,manifest_path,expected_manifest_sha256,source_root=None):
    request_path,output,manifest=safe(request_path),safe(output_dir),safe(manifest_path)
    root=safe(source_root) if source_root is not None else manifest.parent
    require(not output.exists() and not output.is_relative_to(ROOT) and
            not request_path.is_relative_to(output) and not manifest.is_relative_to(output),'NEW_PRIVATE_OUTPUT_REQUIRED')
    output.mkdir(parents=True,exist_ok=False);stage='retain_request'
    try:
        raw=read(request_path);write(output,'original-request.json',raw);doc=request(raw)
        stage='retain_pinned_corpus';manifest_raw=read(manifest);require(digest(manifest_raw)==expected_manifest_sha256,'EXTERNAL_MANIFEST_PIN_MISMATCH')
        definition=parse(manifest_raw);require(isinstance(definition,dict) and isinstance(definition.get('sources'),list) and
                                             0<len(definition['sources'])<=10000,'INVALID_SOURCE_LIST')
        source_files={};total=0
        for row in definition['sources']:
            name=relative(row['path']);path=safe(root/name);require(path.is_relative_to(root),'SOURCE_PATH_ESCAPE')
            content=read(path);total+=len(content);require(total<=MAX_TOTAL,'SOURCE_CORPUS_TOO_LARGE')
            require(digest(content)==row['sha256'],'ORIGINAL_SOURCE_HASH_MISMATCH')
            require(name.casefold() not in {n.casefold() for n in source_files},'DUPLICATE_SOURCE_PATH')
            source_files[name]=content
        load_manifest(manifest,expected_manifest_sha256,root)
        write(output,'ingress.json',manifest_raw)
        for name,content in source_files.items():write(output,'originals/'+name,content)
        context={'method':METHOD,'producer':doc['producer'],'request_sha256':digest(raw),
                 'manifest_sha256':expected_manifest_sha256,'implementation_sha256':implementations()}
        write(output,'context.json',encode(context));stage='producer'
        result=produce(doc,output/'ingress.json',expected_manifest_sha256,output/'originals')
        write(output,'result.json',encode(result));stage='render'
        write(output,'report.md',render(doc,result));stage='original_source_and_report_replay'
        checked=audit(output,context);write(output,'audit.json',encode(checked))
        receipt={'method':METHOD,'status':'COMPLETED_SOURCE_REPLAY_AND_REPORT_MATCH','producer':doc['producer'],
                 'request_sha256':context['request_sha256'],'manifest_sha256':expected_manifest_sha256,
                 'result_sha256':checked['result_sha256'],'report_sha256':checked['saved_report_sha256'],
                 'audit_sha256':digest(encode(checked)),'artifacts':file_inventory(output),
                 'whole_report_semantic_pass':False,'source_authenticity_verified':False,'execution_authorized':False,
                 'free_prose_status':checked['free_prose_status'],'limits':checked['limits']}
        write(output,'receipt.json',encode(receipt));return receipt
    except Exception as exc:
        write(output,'failure.json',encode({'method':METHOD,'status':'FAILED_RETAINED_PARTIAL','stage':stage,
              'error_type':type(exc).__name__,'error':str(exc),'whole_report_semantic_pass':False}))
        raise

def verify(directory):
    directory=safe(directory);receipt=parse(read(directory/'receipt.json'));context=parse(read(directory/'context.json'))
    require(receipt['method']==METHOD and receipt['status']=='COMPLETED_SOURCE_REPLAY_AND_REPORT_MATCH' and
            receipt['whole_report_semantic_pass'] is False,'COMPLETED_RECEIPT_REQUIRED')
    require(receipt['artifacts']==file_inventory(directory),'RETAINED_ARTIFACT_SET_OR_BYTES_CHANGED')
    checked=audit(directory,context)
    require(encode(checked)==read(directory/'audit.json') and digest(read(directory/'audit.json'))==receipt['audit_sha256'] and
            checked['saved_report_sha256']==receipt['report_sha256'] and checked['result_sha256']==receipt['result_sha256'] and
            checked['original_manifest_sha256']==receipt['manifest_sha256'] and checked['request_sha256']==receipt['request_sha256'],
            'RECEIPT_AUDIT_MISMATCH')
    return checked

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='mode',required=True)
    a=sub.add_parser('run');a.add_argument('request');a.add_argument('--manifest',required=True)
    a.add_argument('--manifest-sha256',required=True);a.add_argument('--source-root');a.add_argument('--output',required=True)
    a=sub.add_parser('verify');a.add_argument('directory');args=p.parse_args(argv)
    try:
        result=(run(args.request,args.output,args.manifest,args.manifest_sha256,args.source_root) if args.mode=='run' else verify(args.directory))
        print(encode(result).decode(),end='');return 0
    except (ValueError,OSError,ImportError,KeyError,TypeError) as exc:
        print(json.dumps({'status':'FAILED','error':str(exc),'whole_report_semantic_pass':False}));return 1
if __name__=='__main__':sys.exit(main())
