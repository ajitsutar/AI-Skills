"""Source-bound insider rows with local units, mechanisms and identity limits.

Code/footnote interpretation uses a bounded offline schema, not filing-law advice.
Other disclosure populations never supply insider currency, ownership or amendments.
"""
from copy import deepcopy
from datetime import date
from decimal import Context, Decimal, localcontext
import re
from pathlib import Path

import supplied_research as store
from analyst_revisions import number,raw_reference

METHOD='source-bound-insider-disclosures-1'
MECHANISMS={'P':'PURCHASE','S':'SALE','A':'AWARD','F':'TAX_WITHHOLDING','M':'OPTION_EXERCISE'}
SHARE_SIGN={'P':1,'S':-1,'A':1,'F':-1,'M':1}
CASH_SIGN={'P':-1,'S':1,'M':-1}
IDENTITIES=('insider_id','reporting_owner','owner_name')
ROW_FIELDS=('id','transaction_date','filed_at','code','quantity','price','currency','price_currency',
            'ownership','footnote','amendment','amends','holdings_before','holdings_after')+IDENTITIES


def numeric(value,nonnegative=True):
    result=number(value)
    store.require(not nonnegative or result>=0,'INSIDER_NONNEGATIVE_REPORTED_NUMBER_REQUIRED')
    return result


def exact_product(a,b):
    a,b=numeric(a),numeric(b)
    with localcontext(Context(prec=max(50,len(a.as_tuple().digits)+len(b.as_tuple().digits)+3))):return a*b


def exact_sum(values):
    values=list(values)
    if not values:return Decimal(0)
    precision=max(50,max(v.adjusted() for v in values)-min(v.as_tuple().exponent for v in values)+len(str(len(values)))+3)
    with localcontext(Context(prec=precision)):return sum(values,Decimal(0))


def iso_day(value):
    store.require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}',value),'INSIDER_ISO_DATE_REQUIRED')
    return date.fromisoformat(value)


def row_currency(row):
    supplied={key:row[key] for key in ('currency','price_currency') if key in row}
    for value in supplied.values():store.require(value is None or type(value) is str and re.fullmatch(r'[A-Z]{3}',value),'ROW_CURRENCY_CODE_REQUIRED')
    known={v for v in supplied.values() if v is not None}
    if len(known)>1:return {'value':None,'status':'CONFLICTING_ROW_LOCAL_CURRENCY','original_fields':supplied}
    return {'value':next(iter(known),None),'status':'EXPLICIT_ROW_CURRENCY' if known else 'UNSPECIFIED_IN_INSIDER_ROW','original_fields':supplied}


def footnote_findings(row,known_ids):
    text=row.get('footnote','')
    store.require(type(text) is str,'INSIDER_FOOTNOTE_STRING_REQUIRED')
    # Narrow positive grammar. A matching phrase is attributed to the supplied
    # footnote; it does not prove motive, discretion, compliance or knowledge.
    declared=re.fullmatch(r'open[- ]market discretionary (purchase|sale)\.?',text.strip(),re.I)
    discretionary=bool(declared)
    conflict=bool(declared and {'purchase':'P','sale':'S'}[declared.group(1).lower()]!=row.get('code'))
    negation=bool(re.search(r'\b(?:not|no|never|non)\b',text,re.I))
    planned=not negation and bool(re.search(r'\b(?:under (?:a )?prearranged plan|plan adopted \d{4}-\d{2}-\d{2})\b',text,re.I))
    refs=re.findall(r'\blinked to ([A-Za-z0-9][A-Za-z0-9_.-]*)\b',text,re.I)
    dates=re.findall(r'\bplan adopted (\d{4}-\d{2}-\d{2})\b',text,re.I)
    for value in dates:iso_day(value)
    return {'original_text':text,'explicit_discretionary_phrase':discretionary,'explicit_plan_phrase':planned,
            'code_and_literal_discretionary_footnote_conflict':conflict,'negation_marker_present':negation,
            'plan_adoption_dates_as_reported':dates,
            'linked_ids_as_reported':[{'id':value,'present_in_same_original_insider_list':value in known_ids} for value in refs],
            'interpretation_scope':'BOUNDED_LITERAL_FOOTNOTE_FINDINGS_NOT_MOTIVE_OR_LEGAL_CERTIFICATION'}


def analyze(corpus):
    datasets=[];unsupported=[]
    for sid,source in corpus.sources.items():
        if source['format']!='json':continue
        doc=source['document']
        if type(doc) is not dict or 'insider_rows' not in doc:
            unsupported.append(sid);continue
        original=doc['insider_rows'];store.require(type(original) is list and len(original)<=512,'BOUNDED_INSIDER_ROWS_REQUIRED')
        ids=[]
        for row in original:
            store.require(type(row) is dict and type(row.get('id')) is str and row['id'].strip(),'INSIDER_ROW_ID_REQUIRED')
            store.require(row['id'] not in ids,'DUPLICATE_INSIDER_ROW_ID');ids.append(row['id'])
        raw=raw_reference(doc,corpus);rows=[];share_terms=[];cash_groups={}
        for index,row in enumerate(original):
            store.require(type(row.get('code')) is str,'INSIDER_CODE_REQUIRED')
            code=row['code'];qty=numeric(row['quantity']);price=numeric(row['price']);tx=iso_day(row['transaction_date']);filed=iso_day(row['filed_at'])
            store.require(filed>=tx,'INSIDER_FILING_PRECEDES_TRANSACTION')
            currency=row_currency(row);note=footnote_findings(row,set(ids));product=exact_product(qty,price)
            identities={k:deepcopy(row[k]) for k in IDENTITIES if k in row}
            store.require(all(v is None or type(v) is str and v.strip() for v in identities.values()),'INSIDER_IDENTITY_STRING_REQUIRED')
            owner=row.get('ownership');store.require(owner is None or type(owner) is str and owner.strip(),'OWNERSHIP_FIELD_STRING_REQUIRED')
            mechanism=MECHANISMS.get(code,'UNSUPPORTED_TRANSACTION_CODE')
            if note['code_and_literal_discretionary_footnote_conflict']:
                discretion='UNRESOLVED_CODE_FOOTNOTE_CONFLICT'
            elif mechanism in ('AWARD','TAX_WITHHOLDING','OPTION_EXERCISE'):
                discretion='NOT_CLASSIFIED_AS_DISCRETIONARY_PURCHASE_OR_SALE'
            elif note['explicit_plan_phrase'] or note['linked_ids_as_reported']:
                discretion='REPORTED_PLAN_OR_LINKED_TRANSACTION_NOT_NEW_DISCRETION_PROOF'
            elif note['explicit_discretionary_phrase']:
                discretion='SUPPLIED_FOOTNOTE_DECLARES_DISCRETIONARY'
            else:discretion='DISCRETION_UNRESOLVED'
            signed_qty=(qty if SHARE_SIGN[code]>0 else qty.copy_negate()) if code in SHARE_SIGN else None
            cash=(product if CASH_SIGN[code]>0 else product.copy_negate()) if code in CASH_SIGN else None
            result={'id':row['id'],'source_ref':{'source_id':sid,'pointer':'/insider_rows/'+str(index),'sha256':source['sha256']},
                'original_fields':{k:deepcopy(row[k]) for k in ROW_FIELDS if k in row},'uninterpreted_row_fields':sorted(set(row)-set(ROW_FIELDS)),
                'code':code,'code_mechanism':mechanism,'discretion_status':discretion,'footnote':note,
                'transaction_date':row['transaction_date'],'filed_at':row['filed_at'],'filing_lag_calendar_days':(filed-tx).days,
                'quantity':str(qty),'price':str(price),'price_currency':currency,'ownership_as_supplied':owner,
                'identity_fields_as_supplied':identities,'identity_status':'DECLARED_ROW_IDENTITY' if any(identities.values()) else 'IDENTITY_UNSPECIFIED_IN_ROW',
                'insider_amendment_fields':{k:deepcopy(row[k]) for k in ('amendment','amends') if k in row},
                'insider_amendment_status':'ROW_FIELDS_RETAINED_NOT_APPLIED' if any(k in row for k in ('amendment','amends')) else 'NOT_SUPPLIED_IN_ROW',
                'holdings_fields_as_supplied':{k:deepcopy(row[k]) for k in ('holdings_before','holdings_after') if k in row},
                'holdings_status':'ROW_FIELDS_RETAINED_NOT_COMPLETE_HISTORY_PROOF' if any(k in row for k in ('holdings_before','holdings_after')) else 'NOT_SUPPLIED_IN_ROW',
                'quantity_times_price':{'value':str(product),'currency':currency['value'],'currency_status':currency['status'],
                    'meaning':'REPORTED_QUANTITY_TIMES_PRICE_ONLY_NOT_ACTUAL_CASH_TAX_OR_PROFIT'},
                'signed_listed_row_quantity':str(signed_qty) if signed_qty is not None else None,
                'cash_proxy':{'value':str(cash) if cash is not None else None,'currency':currency['value'],
                    'included':code in CASH_SIGN,'basis':'PURCHASE_NEGATIVE_EXERCISE_NEGATIVE_SALE_POSITIVE; awards/withholding excluded',
                    'meaning':'CONDITIONAL_REPORTED_ROW_PROXY_NOT_SETTLED_CASH_OR_PROFIT'},
                'current_holdings_established':False,'motive_or_advance_knowledge_established':False}
            rows.append(result)
            if signed_qty is not None:share_terms.append(signed_qty)
            if cash is not None:
                group=(currency['status'],currency['value']);cash_groups.setdefault(group,[]).append((row['id'],cash))
        groups=[{'row_ids':[key for key,_ in values],'currency':ccy,'currency_status':status,
                 'raw_signed_numeric_sum':str(exact_sum(value for _,value in values)),
                 'unit_compatibility_verified':False,'owner_aggregation_verified':False,
                 'meaning':'CONDITIONAL_LISTED_ROW_ARITHMETIC_ONLY_NOT_NET_CASH_OR_HOLDINGS'} for (status,ccy),values in cash_groups.items()]
        datasets.append({'source_id':sid,'source_sha256':source['sha256'],'issuer_as_supplied':deepcopy(doc.get('issuer')),
            'rows':rows,'listed_row_quantity_arithmetic':{'value':str(exact_sum(share_terms)),
                'all_codes_supported':all(row['code'] in SHARE_SIGN for row in rows),'scope':'RECOGNIZED_LISTED_ROWS_ONLY',
                'owner_aggregation_verified':False,'complete_history_verified':False,'current_holdings_established':False},
            'cash_proxy_groups':groups,'different_currency_groups_combined':False,
            'other_original_members_not_used_for_insider_units_or_identity':sorted(set(doc)-{'insider_rows','issuer','source'}),
            'other_population_amendments_applied_to_insiders':False,
            'original_source_metadata':deepcopy(doc.get('source')),
            'raw_source_binding':{k:v for k,v in raw.items() if k!='text'},
            'source_scope':'Original structured insider rows only. Other original contexts remain in the full coverage inventory.'})
    import institution_disclosures
    store.require(Path(institution_disclosures.__file__).resolve()==store.ROOT/'scripts/institution_disclosures.py','INSTITUTION_IMPLEMENTATION_OUTSIDE_SKILL')
    return {'method':METHOD,'status':'PARTIAL_SOURCE_BOUND_DISCLOSURE_REVIEW','datasets':datasets,
            'institution_snapshots':institution_disclosures.analyze(corpus),
            'unsupported_json_sources':unsupported,'all_original_sources_bound':list(corpus.sources),
            'currency_inherited_from_other_contexts':False,'semantic_completeness_verified':False,
            'source_authenticity_verified':False,'actual_filing_retrieval_performed':False,'execution_authorized':False}
