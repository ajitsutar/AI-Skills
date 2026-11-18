"""Reported institution snapshots and explicit same-scope amendment chains.

All comparisons are supplied-record arithmetic, not positions, trades or legal advice.
"""
from copy import deepcopy
from decimal import Context, Decimal, localcontext

import supplied_research as store
from insider_disclosures import numeric, iso_day, exact_sum
from analyst_revisions import raw_reference

DIMENSIONS=('manager','issuer','security_id','share_class','ownership_scope',
            'account_id','subaccount_id','holding_unit','shares_unit','unit')


def difference(before,after):
    a,b=numeric(before),numeric(after)
    delta=exact_sum([b,a.copy_negate()])
    with localcontext(Context(prec=50)):
        pct=str(delta/a*Decimal(100)) if a else None
    return {'reported_share_difference':str(delta),'percent_of_prior_reported_shares':pct,
            'percentage_precision':50,'percentage_status':'DEFINED' if a else 'UNDEFINED_ZERO_PRIOR',
            'meaning':'REPORTED_SNAPSHOT_DIFFERENCE_NOT_PURCHASES_SALES_OR_CURRENT_HOLDINGS'}


def analyze(corpus):
    datasets=[]
    for sid,source in corpus.sources.items():
        doc=source.get('document')
        if source['format']!='json' or type(doc) is not dict or 'institutions' not in doc:continue
        original=doc['institutions']
        store.require(type(original) is list and len(original)<=512,'BOUNDED_INSTITUTION_ROWS_REQUIRED')
        rows=[];groups={}
        for index,row in enumerate(original):
            store.require(type(row) is dict,'INSTITUTION_ROW_REQUIRED')
            period=iso_day(row['report_period']);filed=iso_day(row['filed'])
            store.require(filed>=period,'INSTITUTION_FILING_PRECEDES_PERIOD')
            shares=numeric(row['shares']);amend=row.get('amendment',False)
            store.require(type(amend) is bool,'INSTITUTION_AMENDMENT_BOOLEAN')
            scope={key:row.get(key,doc.get('issuer') if key=='issuer' else None) for key in DIMENSIONS}
            store.require(all(value is None or type(value) is str and value.strip() for value in scope.values()),'INSTITUTION_SCOPE_STRING_REQUIRED')
            ref={'source_id':sid,'pointer':'/institutions/'+str(index),'sha256':source['sha256']}
            entry={'record_index':index,'source_ref':ref,'original_fields':deepcopy(row),'scope_as_supplied':scope,
                   'issuer_origin':'ROW' if 'issuer' in row else 'DOCUMENT' if 'issuer' in doc else 'UNSPECIFIED',
                   'report_period':row['report_period'],'filed':row['filed'],'shares':str(shares),
                   'amendment':amend,'amends_filing_as_supplied':row.get('amends'),
                   'report_to_filing_calendar_days':(filed-period).days,
                   'information_available_no_earlier_than_declared_filing':row['filed'],
                   'legal_lateness_or_compliance_established':False}
            rows.append(entry)
            key=tuple(scope[k] for k in DIMENSIONS)+(row['report_period'],)
            groups.setdefault(key,[]).append(entry)
        snapshots=[]
        for key,items in groups.items():
            links=[];problems=[];children={r['record_index']:[] for r in items}
            bases=[r for r in items if not r['amendment']]
            for row in items:
                target=row['amends_filing_as_supplied']
                if not row['amendment']:
                    if target is not None:problems.append({'record_index':row['record_index'],'status':'AMENDS_WITHOUT_AMENDMENT_FLAG'})
                    continue
                matches=[p for p in items if p['filed']==target and p['record_index']!=row['record_index']]
                if len(matches)!=1:
                    problems.append({'record_index':row['record_index'],'status':'MISSING_OR_AMBIGUOUS_SAME_SCOPE_PREDECESSOR'});continue
                prior=matches[0]
                if row['filed']<=prior['filed']:
                    problems.append({'record_index':row['record_index'],'status':'NONFORWARD_AMENDMENT_DATE'});continue
                children[prior['record_index']].append(row['record_index'])
                links.append({'prior_record_index':prior['record_index'],'amendment_record_index':row['record_index'],
                              'amendment_after_prior_calendar_days':(iso_day(row['filed'])-iso_day(prior['filed'])).days,
                              'meaning':'REPLACES_SAME_REPORTED_PERIOD_VALUE_NOT_ADDITIONAL_POSITION'})
            if len(bases)!=1:problems.append({'status':'MISSING_OR_MULTIPLE_ORIGINAL_SNAPSHOTS'})
            if any(len(v)>1 for v in children.values()):problems.append({'status':'BRANCHING_AMENDMENT_CHAIN'})
            if len(links)!=len(items)-len(bases):problems.append({'status':'INCOMPLETE_AMENDMENT_CHAIN'})
            chain=[]
            if not problems:
                current=bases[0]['record_index']
                while current not in chain:
                    chain.append(current)
                    if not children[current]:break
                    current=children[current][0]
                if len(chain)!=len(items):problems.append({'status':'DISCONNECTED_AMENDMENT_CHAIN'})
            effective=rows[chain[-1]] if chain and not problems else None
            snapshots.append({'scope_as_supplied':dict(zip(DIMENSIONS,key[:-1])),'report_period':key[-1],
                'original_record_indices':[r['record_index'] for r in bases],
                'all_record_indices':[r['record_index'] for r in items],'amendment_links':links,'unresolved':problems,
                'status':'EXPLICIT_REPORTED_CHAIN_RESOLVED' if effective else 'UNRESOLVED_REPORTED_CHAIN',
                'effective_record_index':effective['record_index'] if effective else None,
                'effective_reported_shares':effective['shares'] if effective else None,
                'effective_information_available_from':effective['filed'] if effective else None,
                'current_holdings_established':False})
        comparisons=[];populations={}
        for snap in snapshots:
            populations.setdefault(tuple(snap['scope_as_supplied'][k] for k in DIMENSIONS),[]).append(snap)
        for scope,snaps in populations.items():
            snaps.sort(key=lambda s:s['report_period'])
            for before,after in zip(snaps,snaps[1:]):
                row={'scope_as_supplied':dict(zip(DIMENSIONS,scope)),'prior_period':before['report_period'],
                     'later_period':after['report_period'],'prior_record_index':before['effective_record_index'],
                     'later_record_index':after['effective_record_index'],'unknown_scope_dimensions':[k for k,v in zip(DIMENSIONS,scope) if v is None],
                     'complete_entity_perimeter_established':False,'security_identity_verified':False,
                     'current_holdings_established':False,'transactions_or_motives_established':False}
                if scope[0] is None or scope[1] is None or before['effective_record_index'] is None or after['effective_record_index'] is None:
                    row['status']='UNRESOLVED_SCOPE_OR_CHAIN';row['arithmetic']=None
                else:
                    row['status']='MATCHED_REPORTED_SCOPE_ONLY';row['arithmetic']=difference(Decimal(before['effective_reported_shares']),Decimal(after['effective_reported_shares']))
                    row['information_available_from']=max(before['effective_information_available_from'],after['effective_information_available_from'])
                    original=after['original_record_indices']
                    if len(original)==1 and original[0]!=after['effective_record_index']:
                        row['superseded_original_comparison']={'record_index':original[0],'arithmetic':difference(Decimal(before['effective_reported_shares']),Decimal(rows[original[0]]['shares'])),
                            'status':'SUPERSEDED_FOR_LATER_REPORTED_PERIOD_NOT_ADDITIONAL_OBSERVATION',
                            'original_filing_available_from':rows[original[0]]['filed']}
                comparisons.append(row)
        raw=raw_reference(doc,corpus)
        datasets.append({'source_id':sid,'source_sha256':source['sha256'],'rows':rows,'snapshots':snapshots,'comparisons':comparisons,
            'original_source_metadata':deepcopy(doc.get('source')),'raw_source_binding':{k:v for k,v in raw.items() if k!='text'},
            'other_disclosure_populations_used_as_institution_positions':False,
            'limitations':['Declared manager and issuer scope is not a verified entity perimeter, affiliate or beneficial-owner aggregation.',
                'Unspecified security class, derivatives, shorts, subaccounts and economic exposure remain unresolved.',
                'Filing and amendment availability differ from reporting period and current positions; no legal deadline is inferred.',
                'No complete intervening transaction history, acquisition cost, motive, or later position is established.']})
    return {'method':'source-bound-institution-snapshots-1','datasets':datasets,'cross_source_chains_combined':False,
            'actual_filing_retrieval_performed':False,'source_authenticity_verified':False,'current_holdings_established':False}
