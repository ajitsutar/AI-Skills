"""Typed report statements and exact saved-report coverage, not general prose truth.

Evidence must be externally retained helper output. Fixed renderers never accept
caller-written conclusions or substitute one objective/accounting label for another.
"""
import argparse
import difflib
from decimal import Decimal
import hashlib
import json
import operator
from pathlib import Path
import re

from news_evidence import decode, pointer, read_source
from source_claims import accounting as replay_accounting

METHOD = 'bound-report-claims-1.0.0'
OPS = {'>': operator.gt, '>=': operator.ge, '<': operator.lt, '<=': operator.le,
       '==': operator.eq, '!=': operator.ne}
PARAMETERS = {'annual_revenue_growth', 'terminal_ebit_margin', 'tax_rate',
              'net_debt_at_exit', 'annual_dilution', 'exit_ev_to_ebit',
              'cumulative_dividends_per_share'}
MEASURES = {'net_total_return_fraction', 'terminal_share_price',
            'present_value_of_modeled_distributions', 'dcf_discount_closure'}
MAX_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 128 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def numeric(value):
    require(type(value) in (int, float, str, Decimal), 'NUMERIC_VALUE_REQUIRED')
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError('NUMERIC_VALUE_REQUIRED') from exc
    require(number.is_finite(), 'FINITE_VALUE_REQUIRED')
    return number


def quoted(value):
    # All evidence strings are JSON-escaped; none can inject lines/claim markers.
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def exact_keys(obj, required, optional=()):
    require(isinstance(obj, dict) and set(required) <= set(obj)
            and set(obj) <= set(required) | set(optional), 'UNSUPPORTED_OR_MISSING_FIELDS')


def identifiers(rows):
    require(isinstance(rows, list) and rows, 'NONEMPTY_ROWS_REQUIRED')
    ids = [row['id'] for row in rows]
    require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids),
            'UNIQUE_ROW_IDS_REQUIRED')


def scenario(claim, evidence):
    exact_keys(claim, {'id', 'kind', 'evidence', 'objective_id', 'conditions', 'connective'}, {'assertion'})
    require(isinstance(evidence, dict) and evidence.get('scope', {}).get('kind') in
            {'SUPPLIED_ROWS', 'FINITE_CARTESIAN_DOMAIN'}, 'SCENARIO_OUTPUT_REQUIRED')
    rows, objectives = evidence['rows'], evidence['objectives']
    identifiers(rows); identifiers(objectives)
    require(len(rows) <= 4096 and evidence['scope']['row_count'] == len(rows), 'DOMAIN_ROW_COUNT')
    matching = [o for o in objectives if o['id'] == claim['objective_id']]
    require(len(matching) == 1, 'EXACT_OBJECTIVE_BINDING_REQUIRED')
    objective = matching[0]
    require(objective['measure'] in MEASURES, 'UNSUPPORTED_OBJECTIVE')
    definition = objective['definition']
    require(definition['measure'] == objective['measure'], 'OBJECTIVE_DEFINITION_MISMATCH')
    if objective['measure'] != 'dcf_discount_closure':
        units = {'net_total_return_fraction':('fraction','holding_period_return'),
                 'terminal_share_price':('currency_per_share','terminal_price'),
                 'present_value_of_modeled_distributions':('currency_per_share','present_value')}
        unit,basis = units[objective['measure']]
        original_target, retained_target = definition['target'], objective['target']
        require(objective['status']=='DEFINED' and definition['operator']==objective['operator'] and
                {k:v for k,v in original_target.items() if k!='value'} ==
                {k:v for k,v in retained_target.items() if k!='value'} and
                numeric(original_target['value'])==numeric(retained_target['value']),
                'OBJECTIVE_DEFINITION_MISMATCH')
        require(objective['target']['unit']==unit and objective['target']['valuation_basis']==basis and
                numeric(objective['target']['horizon_years'])>0, 'OBJECTIVE_DIMENSION_MISMATCH')
    conditions = claim['conditions']
    require(isinstance(conditions, list) and conditions and len(conditions) <= 32, 'CONDITIONS_REQUIRED')
    require(claim['connective'] in ('all', 'any'), 'EXPLICIT_AND_OR_REQUIRED')
    for condition in conditions:
        exact_keys(condition, {'parameter', 'operator', 'value'})
        require(condition['parameter'] in PARAMETERS and condition['operator'] in OPS, 'INVALID_CONDITION')
        numeric(condition['value'])
    successes, matches, unknown, necessity_bad, sufficiency_bad = [], [], [], [], []
    for row in rows:
        tests = [OPS[c['operator']](numeric(row['parameters'][c['parameter']]), numeric(c['value']))
                 for c in conditions]
        condition_met = all(tests) if claim['connective'] == 'all' else any(tests)
        observed = row['objectives'][objective['id']]
        require(observed['measure'] == objective['measure'], 'ROW_OBJECTIVE_MISMATCH')
        unavailable = objective['status'] == 'UNAVAILABLE_DCF_MODEL_NOT_EVALUATED'
        if unavailable:
            require(objective['measure'] == 'dcf_discount_closure' and observed['met'] is None
                    and observed['value'] is None, 'UNAVAILABLE_OBJECTIVE_HAS_RESULT')
            met = None
        elif observed['value'] is None:
            require(observed['met'] is None, 'NULL_OBJECTIVE_HAS_RESULT')
            met = None
        else:
            require(objective['measure'] != 'dcf_discount_closure' and objective['operator'] in OPS,
                    'UNSUPPORTED_DCF_OR_OPERATOR')
            require(numeric(observed['target']) == numeric(objective['target']['value']), 'TARGET_MISMATCH')
            met = OPS[objective['operator']](numeric(observed['value']), numeric(objective['target']['value']))
            require(type(observed['met']) is bool and observed['met'] == met, 'ROW_RESULT_CONTRADICTION')
        if condition_met: matches.append(row['id'])
        if met is True:
            successes.append(row['id'])
            if not condition_met: necessity_bad.append(row['id'])
        if met is None: unknown.append(row['id'])
        if condition_met and met is False: sufficiency_bad.append(row['id'])
    necessary = ('REFUTED' if necessity_bad else 'UNDETERMINED' if unknown else
                 'NO_SUCCESS_WITNESS' if not successes else 'HOLDS_ON_DECLARED_FINITE_DOMAIN')
    sufficient = ('REFUTED' if sufficiency_bad else 'NO_CONDITION_WITNESS' if not matches else
                  'UNDETERMINED' if set(matches) & set(unknown) else 'HOLDS_ON_DECLARED_FINITE_DOMAIN')
    assertion = claim.get('assertion')
    require(assertion in (None, 'necessary', 'sufficient', 'necessary_and_sufficient'), 'INVALID_ASSERTION')
    if assertion in ('necessary', 'necessary_and_sufficient'):
        require(necessary == 'HOLDS_ON_DECLARED_FINITE_DOMAIN', 'UNSUPPORTED_NECESSITY_ASSERTION')
    if assertion in ('sufficient', 'necessary_and_sufficient'):
        require(sufficient == 'HOLDS_ON_DECLARED_FINITE_DOMAIN', 'UNSUPPORTED_SUFFICIENCY_ASSERTION')
    relation = ' AND ' if claim['connective'] == 'all' else ' OR '
    condition_text = relation.join(c['parameter'] + ' ' + c['operator'] + ' ' + str(numeric(c['value']))
                                  for c in conditions)
    text = ('Retained helper evidence; source truth and original model execution are not verified here.\n'
            'Objective ' + quoted(objective['id']) + ': ' + objective['measure'] + '; definition ' +
            quoted(objective.get('definition', {})) + '.\nCondition: (' + condition_text + ').\n'
            'Necessary: ' + necessary + '; sufficient: ' + sufficient + '.\n'
            'Necessity counterexample row IDs: ' + quoted(necessity_bad) +
            '; sufficiency counterexample row IDs: ' + quoted(sufficiency_bad) + '.\n'
            'Objective-success row IDs: ' + quoted(successes) + '; unavailable row IDs: ' + quoted(unknown) + '.\n'
            'Scope: ' + evidence['scope']['kind'] + ', ' + str(len(rows)) +
            ' retained rows; no continuous-space or economic-feasibility proof. '
            'Evidence for this objective does not establish another objective or DCF discount closure.')
    if objective['measure'] == 'dcf_discount_closure':
        text += '\nDCF discount closure is unavailable: no evaluated DCF model/closure criterion is supplied.'
    return text, {'necessary':necessary, 'sufficient':sufficient, 'objective_id':objective['id'],
                  'necessity_counterexamples':necessity_bad, 'sufficiency_counterexamples':sufficiency_bad}


def accounting(claim, evidence):
    exact_keys(claim, {'id','kind','evidence','label'})
    require(evidence.get('method') == 'source-claims-1.0.0' and evidence.get('operation') == 'accounting',
            'SOURCE_ACCOUNTING_OUTPUT_REQUIRED')
    # Replay the existing accounting contract against retained field records.
    # This catches self-contradictory output; it does not replace original-source replay.
    bindings, request = {}, {}
    for group in ('income','shares'):
        request[group] = {}
        for field, record in evidence['bound_fields'].get(group,{}).items():
            reference = record['source_ref']
            key = quoted(reference)
            value = record['value']
            if field in ('value','unit_scale') and isinstance(value,str):
                require(re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?',value),
                        'MALFORMED_RETAINED_DECIMAL')
                value = numeric(value)
            require(key not in bindings or bindings[key] == value, 'CONFLICTING_RETAINED_SOURCE_FIELD')
            bindings[key] = value; request[group][field] = reference
    class RetainedFields:
        def resolve(self, reference):
            return bindings[quoted(reference)]
    replay = replay_accounting(request,RetainedFields())
    for field in ('classification','allowed_claims','reasons'):
        require(replay[field] == evidence[field], 'ACCOUNTING_CONTRACT_REPLAY_MISMATCH:'+field)
    for field in ('raw_operand_ratio','eps'):
        require((replay[field] is None and evidence[field] is None) or
                (replay[field] is not None and evidence[field] is not None and
                 numeric(replay[field]) == numeric(evidence[field])), 'ACCOUNTING_VALUE_REPLAY_MISMATCH:'+field)
    label = claim['label']
    require(label in {'diagnostic_ratio','basic_eps','diluted_eps','pe'}, 'ACCOUNTING_LABEL_UNSUPPORTED')
    if label == 'diagnostic_ratio':
        value = evidence['raw_operand_ratio']
        text = ('Unscaled diagnostic income/share operand ratio: ' + quoted(value) +
                '. This is not established reported EPS or P/E. Accounting classification: ' +
                quoted(evidence['classification']) + '; reasons: ' + quoted(evidence['reasons']) + '.')
    else:
        expected = {'basic_eps':'BASIC_EPS_SOURCE_BOUND','diluted_eps':'DILUTED_EPS_SOURCE_BOUND'}
        require(label in expected and label in evidence.get('allowed_claims', []) and
                evidence['classification'] == expected[label] and not evidence['reasons']
                and evidence['eps'] is not None, 'UNSUPPORTED_ACCOUNTING_LABEL')
        value = evidence['eps']; numeric(value)
        text = ('Retained fields classify as ' + label + ': ' + quoted(value) + '. Bound accounting fields: ' +
                quoted(evidence['bound_fields']) + '. Source authenticity and independent GAAP verification are not established; no P/E is inferred.')
    return text, {'label':label, 'value':value, 'classification':evidence['classification'],
                  'retained_field_contract_replayed':True,'original_source_replayed':False}


def cohort(claim, evidence):
    exact_keys(claim, {'id','kind','evidence'}, {'assert_record_ids'})
    require(evidence.get('method') == 'source-claims-1.0.0' and evidence.get('operation') == 'analyst_corpus',
            'CONFIGURED_CORPUS_OUTPUT_REQUIRED')
    coverage = evidence['coverage']
    require(evidence['status'] == 'REVIEWED_WITH_CONFIGURED_CORPUS_COVERAGE' and
            coverage['status'] == 'CONFIGURED_SCAN_RECONCILED' and
            not coverage['unresolved_candidate_ids'] and not coverage['unlinked_record_ids'] and
            not coverage['scan']['unsupported_sources'], 'INCOMPLETE_CORPUS_CANNOT_RENDER_LATEST_COHORT')
    analysis = evidence['analysis']
    require(analysis.get('method') == 'analyst-evidence-1.0.0', 'ANALYST_OUTPUT_REQUIRED')
    rows = analysis['individual_targets_used']
    require(isinstance(rows,list) and rows, 'NONEMPTY_COHORT_REQUIRED')
    ids, firms = [r['record_id'] for r in rows], [r['firm_id'] for r in rows]
    require(len(ids)==len(set(ids)) and len(firms)==len(set(firms)), 'DUPLICATE_COHORT_ID_OR_FIRM')
    require(set(ids) <= set(coverage['record_ids']), 'COHORT_NOT_IN_COVERAGE')
    excluded = {r['record_id'] for r in analysis['excluded']}
    require(not set(ids) & excluded, 'COHORT_CONTAINS_EXCLUDED_RECORD')
    require(set(ids) | excluded == set(coverage['record_ids']), 'COHORT_COVERAGE_PARTITION_MISMATCH')
    if 'assert_record_ids' in claim:
        require(isinstance(claim['assert_record_ids'],list) and len(claim['assert_record_ids'])==len(ids)
                and set(claim['assert_record_ids'])==set(ids), 'STALE_OR_OMITTED_COHORT_RECORD')
    require(analysis['consensus']['independent_firms']==len(rows), 'COHORT_COUNT_MISMATCH')
    lines = ['Retained helper-selected latest eligible cohort within its configured source scan; cutoff '+quoted(analysis['as_of'])+
             '; target horizon '+quoted(analysis['target_horizon'])+'.']
    for row in sorted(rows,key=lambda r:r['firm_id']):
        numeric(row['target'])
        lines.append('Firm '+quoted(row['firm_id'])+', record '+quoted(row['record_id'])+
                     ', issued '+quoted(row['issued_at'])+', target '+quoted(row['target'])+'.')
    lines += ['Full selected record IDs: '+quoted(sorted(ids))+'.',
              'Excluded records: '+quoted(analysis['excluded'])+'.',
              'Configured extraction/disposition judgments are reviewer supplied; original chronology/selection was not independently replayed here. This is not all real-world analysts, a primary valuation, or authenticated independent consensus.']
    return '\n'.join(lines), {'selected_record_ids':sorted(ids),'firm_count':len(rows),
                             'retained_coverage_partition_checked':True,'original_selection_replayed':False}


def presence(claim, evidence):
    """Source candidates are not adapter bindings or semantic absence proofs."""
    exact_keys(claim, {'id','kind','evidence'}, {'assertion'})
    require(evidence.get('method')=='source-claims-1.0.0' and evidence.get('operation')=='presence',
            'SOURCE_PRESENCE_OUTPUT_REQUIRED')
    scan=evidence['scan']; candidates=scan['candidates']; unsupported=scan['unsupported_sources']
    require(scan['scope']=='CONFIGURED_LEXICAL_SEARCH_OF_PINNED_CORPUS' and
            scan['semantic_completeness_verified'] is False and evidence['source_absence_established'] is False,
            'SOURCE_ABSENCE_OR_SEMANTIC_COMPLETENESS_UNSUPPORTED')
    require(isinstance(scan['terms'],list) and scan['terms'] and
            all(isinstance(t,str) and t.strip() for t in scan['terms']) and
            scan['match'] in ('any','all'), 'PRESENCE_SEARCH_CONTRACT_REQUIRED')
    sources=scan['sources_scanned']
    require(isinstance(sources,list) and sources and all(isinstance(s,str) and s for s in sources)
            and len(sources)==len(set(sources)), 'PRESENCE_SOURCE_INVENTORY_REQUIRED')
    require(isinstance(unsupported,list) and len(unsupported)==len(set(unsupported)) and
            set(unsupported)<=set(sources), 'UNSUPPORTED_SOURCE_INVENTORY_MISMATCH')
    require(isinstance(candidates,list), 'PRESENCE_CANDIDATES_REQUIRED')
    ids=[]
    for row in candidates:
        cid=row['candidate_id']; ids.append(cid)
        require(isinstance(cid,str) and cid and row['meaning_verified'] is False,
                'CANDIDATE_ID_OR_SEMANTIC_CLAIM')
        require(row['source_ref']['source_id'] in sources and
                row['source_ref']['source_id'] not in unsupported and
                re.fullmatch('[0-9a-f]{64}',row['source_sha256']), 'CANDIDATE_SOURCE_MISMATCH')
        require(isinstance(row['matched_terms'],list) and row['matched_terms'] and
                set(row['matched_terms'])<=set(scan['terms']) and
                (scan['match']=='any' or set(row['matched_terms'])==set(scan['terms'])), 'CANDIDATE_TERMS_MISMATCH')
    require(len(ids)==len(set(ids)), 'DUPLICATE_PRESENCE_CANDIDATE')
    binding=evidence['binding_state']
    require(binding in ('UNBOUND','EXACT_SOURCE_VALUE','SOURCE_VALUE_NULL','INVALID'), 'BINDING_STATE_REQUIRED')
    predicate='SOURCE_CANDIDATE_PRESENT' if candidates else 'NO_CONFIGURED_LEXICAL_MATCH'
    if unsupported:predicate+='_INCOMPLETE_SCAN'
    allowed=(['source_candidate_present'] if candidates else [])+(['adapter_value_bound'] if binding=='EXACT_SOURCE_VALUE' else [])
    require(evidence['predicate']==predicate and evidence['allowed_claims']==allowed,
            'PRESENCE_CONTRACT_CONTRADICTION')
    expected_facts=[{'predicate':predicate,'binding_state':binding,'semantic_scope_verified':False,
                     'source_refs':[c['source_ref'] for c in candidates]}]
    require(evidence['facts']==expected_facts, 'PRESENCE_FACTS_CONTRADICTION')
    require(claim.get('assertion') is None or claim['assertion'] in allowed,
            'UNSUPPORTED_PRESENCE_ASSERTION')
    lines=['Retained configured source search: terms '+quoted(scan['terms'])+'; match '+scan['match']+'.',
           'Scope: '+scan['scope']+'; sources '+quoted(sources)+'; unsupported sources '+quoted(unsupported)+'.',
           'Lexical result: '+predicate+'; adapter binding: '+binding+'; binding reason '+quoted(evidence['binding_reason'])+'.']
    for row in candidates:
        lines.append('Candidate '+quoted(row['candidate_id'])+': terms '+quoted(row['matched_terms'])+
                     '; value '+quoted(row['value'])+'; original reference '+quoted(row['source_ref'])+
                     '; source SHA256 '+row['source_sha256']+'.')
    lines.append('Adapter UNBOUND/INVALID or a null value does not establish source absence. '
                 'No configured lexical match also does not establish source absence. '
                 'Candidate meaning, semantic completeness, source authenticity and original scan execution are not verified here.')
    return '\n'.join(lines), {'predicate':predicate,'binding_state':binding,'candidate_ids':ids,
                              'source_absence_established':False,'original_scan_replayed':False,
                              'unsupported_sources':unsupported}


def compile_report(plan, raw_artifacts):
    """Pure entry point: exact artifact byte map, useful for independent testing."""
    exact_keys(plan, {'artifacts','segments'})
    require(isinstance(plan['artifacts'],dict) and plan['artifacts'] and
            set(raw_artifacts)==set(plan['artifacts']), 'ARTIFACT_SET_MISMATCH')
    documents={}
    for key,ref in plan['artifacts'].items():
        exact_keys(ref, {'path','sha256'})
        raw=raw_artifacts[key]
        require(isinstance(raw,bytes) and len(raw)<=MAX_BYTES and digest(raw)==ref['sha256'], 'ARTIFACT_HASH_OR_SIZE')
        documents[key]=decode(raw,exact_numbers=True)
    require(isinstance(plan['segments'],list) and 0<len(plan['segments'])<=1000, 'SEGMENTS_REQUIRED')
    pieces, rows, unverified, seen = [], [], [], set()
    cursor=0
    renderers={'scenario_condition':scenario,'accounting_label':accounting,'analyst_cohort':cohort,
               'source_presence':presence}
    for segment in plan['segments']:
        require(isinstance(segment,dict) and len(segment)==1, 'ONE_SEGMENT_KIND_REQUIRED')
        if 'unverified' in segment:
            text=segment['unverified']
            require(isinstance(text,str) and text.strip(), 'NONEMPTY_UNVERIFIED_TEXT_REQUIRED')
            unverified.append({'start':cursor,'end':cursor+len(text),'sha256':digest(text.encode()),
                               'status':'UNAUDITED_PROSE_NOT_CERTIFIED'})
        else:
            require('claim' in segment,'SEGMENT_KIND_REQUIRED')
            claim=segment['claim']; cid=claim.get('id')
            require(isinstance(cid,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,80}',cid) and cid not in seen,
                    'UNIQUE_SAFE_CLAIM_ID_REQUIRED')
            seen.add(cid)
            exact_keys(claim['evidence'],{'artifact','pointer'})
            ref=claim['evidence']; selected=pointer(documents[ref['artifact']],ref['pointer'])
            require(claim['kind'] in renderers, 'UNSUPPORTED_RENDERER')
            body,facts=renderers[claim['kind']](claim,selected)
            text='<!-- bound-claim:'+cid+' -->\n'+body+'\n<!-- /bound-claim:'+cid+' -->'
            rows.append({'id':cid,'kind':claim['kind'],'evidence':ref,'facts':facts,
                         'start':cursor,'end':cursor+len(text),'rendered_sha256':digest(text.encode())})
        pieces.append(text); cursor+=len(text)+2
    require(rows,'AT_LEAST_ONE_BOUND_CLAIM_REQUIRED')
    report='\n\n'.join(pieces)+'\n'
    require(len(report.encode())<=MAX_REPORT_BYTES,'REPORT_SIZE_LIMIT')
    return {'method':METHOD,'status':'PARTIAL_UNAUDITED_PROSE' if unverified else 'BOUND_RENDER_ONLY',
            'report':report,'report_sha256':digest(report.encode()),'claims':rows,'unverified_spans':unverified,
            'artifacts':plan['artifacts'],'plan_sha256':digest(json.dumps(plan,sort_keys=True,default=str).encode()),
            'source_authenticity_verified':False,'request_completeness_verified':False,
            'scope':'Typed statements from pinned outputs only; does not certify arbitrary prose, complete user-request coverage, source truth or execution authenticity.'}


def audit_saved_report(plan, raw_artifacts, saved_bytes):
    rendered=compile_report(plan,raw_artifacts)
    require(isinstance(saved_bytes,bytes) and len(saved_bytes)<=MAX_REPORT_BYTES,'SAVED_REPORT_SIZE')
    saved=saved_bytes.decode('utf-8')
    expected=rendered['report']
    differences=[{'operation':op,'expected_span':[i,j],'saved_span':[k,l],
                  'saved_span_sha256':digest(saved[k:l].encode())}
                 for op,i,j,k,l in difflib.SequenceMatcher(a=expected,b=saved,autojunk=False).get_opcodes()
                 if op!='equal']
    status=('SAVED_REPORT_MISMATCH' if differences else 'PARTIAL_UNAUDITED_PROSE'
            if rendered['unverified_spans'] else 'EXACT_BOUND_REPORT')
    return {'method':METHOD,'status':status,'saved_report_sha256':digest(saved_bytes),
            'expected_report_sha256':rendered['report_sha256'],'differences':differences,
            'unverified_spans':rendered['unverified_spans'],'claims':rendered['claims'],
            'plan_sha256':rendered['plan_sha256'],'artifacts':rendered['artifacts'],
            'whole_report_semantic_pass':False,'source_authenticity_verified':False,
            'scope':rendered['scope']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['render','audit']);parser.add_argument('plan')
    parser.add_argument('artifact_root');parser.add_argument('output');parser.add_argument('--report',required=True)
    args=parser.parse_args()
    plan=decode(Path(args.plan).read_bytes(),exact_numbers=True)
    raw={key:read_source(args.artifact_root,ref) for key,ref in plan['artifacts'].items()}
    destinations=[Path(args.output)] + ([Path(args.report)] if args.mode=='render' else [])
    require(len({p.resolve() for p in destinations})==len(destinations) and
            all(not p.exists() for p in destinations),'OUTPUT_EXISTS_OR_ALIASES')
    result=(compile_report(plan,raw) if args.mode=='render' else
            audit_saved_report(plan,raw,Path(args.report).read_bytes()))
    if args.mode=='render':
        with Path(args.report).open('xb') as stream:stream.write(result['report'].encode())
    with Path(args.output).open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False,default=str);stream.write('\n')
    print(json.dumps({'status':result['status'],'whole_report_semantic_pass':False}))


if __name__=='__main__':
    main()
