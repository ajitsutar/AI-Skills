"""Semantic analyst-table extraction from retained text, with explicit access/basis.

No network, inferred report access, publisher-average blending or target forecasts.
"""
from html.parser import HTMLParser
import html
import re
from datetime import datetime,date
from quant_common import digest, require, timestamp, cli


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.rows=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.rows.append([])
        if tag=='tr':self.row=[]
        if tag in {'td','th'} and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in {'td','th'} and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None


def plain(s):
    s=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',s)
    s=re.sub(r'【\d+†([^】]+)】',r'\1',s)
    return ' '.join(html.unescape(s).split())


def extract(document):
    cutoff=timestamp(document['as_of']);source=document['source']
    require(source.get('url') and source.get('id'),'SOURCE_ID_AND_URL_REQUIRED')
    require(timestamp(source['available_at'])<=cutoff,'FUTURE_SOURCE')
    require(source['access'] in {'aggregate_table','attributed_excerpt','full_report'},'ACCESS_LEVEL')
    require(all(document.get(k) for k in ['issuer_id','currency','share_basis','target_horizon']),'COHORT_METADATA_REQUIRED')
    text=document['text'];require(isinstance(text,str),'TEXT_REQUIRED')
    if document['format']=='html':
        parser=Tables();parser.feed(text);rows=parser.rows
    elif document['format']=='markdown':
        rows=[]
        for line in text.splitlines():
            line=re.sub(r'^\s*L\d+(?:@P\d+)?:\s*','',line)
            if '|' in line:rows.append([plain(c) for c in line.strip().strip('|').split('|')])
            elif not line.strip():rows.append([])
    else:raise ValueError('UNSUPPORTED_TABLE_FORMAT')
    aliases={'analyst':'analyst','analyst name':'analyst','firm':'firm','broker':'firm',
             'price target':'target','target':'target','date':'date','issued':'date',
             'rating':'rating','action':'action'}
    headers=None;records=[];excluded=[]
    for index,row in enumerate(rows):
        if not row:headers=None;continue
        normalized=[re.sub(r'[^a-z ]','',x.lower()).strip() for x in row]
        candidate={}
        for i,name in enumerate(normalized):
            if name in aliases and aliases[name] not in candidate:candidate[aliases[name]]=i
        if {'analyst','firm','target','date'}<=set(candidate):headers=candidate;continue
        if not headers or all(re.fullmatch(r'[-: ]*',x) for x in row):continue
        if any('more analyst ratings' in x.lower() for x in row):
            excluded.append({'source_row':index,'reason':'NAVIGATION_ROW','raw':row});continue
        if len(row)<=max(headers.values()):
            excluded.append({'source_row':index,'reason':'INCOMPLETE_ROW','raw':row});continue
        fields={k:row[i] for k,i in headers.items()}
        targets=re.findall(r'(?<!\w)\$?([0-9][0-9,]*(?:\.[0-9]+)?)',fields['target'])
        if not fields['analyst'] or not fields['firm'] or not targets:
            excluded.append({'source_row':index,'reason':'MISSING_ANALYST_FIRM_OR_TARGET','raw':row});continue
        # Only simple target or previous -> current target is supported. Do not
        # parse upside percentages or narrative embedded in a target cell.
        residue=re.sub(r'\$?[0-9][0-9,]*(?:\.[0-9]+)?','',fields['target']).strip()
        if not ((len(targets)==1 and residue=='') or
                (len(targets)==2 and residue in {'→','->','to'})):
            excluded.append({'source_row':index,'reason':'AMBIGUOUS_TARGET_CELL','raw':row});continue
        values=[float(v.replace(',','')) for v in targets]
        if any(not 0<v<1e12 for v in values):
            excluded.append({'source_row':index,'reason':'TARGET_RANGE','raw':row});continue
        issued=None
        for pattern in ['%Y-%m-%d','%b %d, %Y','%B %d, %Y']:
            try:issued=datetime.strptime(fields['date'],pattern).date().isoformat();break
            except ValueError:pass
        if issued is None or issued>min(cutoff.date(),timestamp(source['available_at']).date()).isoformat():
            excluded.append({'source_row':index,'reason':'UNKNOWN_OR_FUTURE_REPORTED_DATE','raw':row});continue
        records.append({'analyst_name':fields['analyst'],'firm_name':fields['firm'],
                        'reported_date':issued,'original_report_issue_time':None,
                        'target':values[-1],'previous_target':values[0] if len(values)==2 else None,
                        'rating':fields.get('rating'),'action':fields.get('action'),
                        'issuer_id':document['issuer_id'],'currency':document['currency'],
                        'share_basis':document['share_basis'],'target_horizon':document['target_horizon'],
                        'access':source['access'],'source_id':source['id'],'source_row':index,'raw_cells':row})
    conflicts=[];bykey={}
    for r in records:
        key=(r['firm_name'].casefold(),r['analyst_name'].casefold(),r['reported_date'])
        if key in bykey and bykey[key]['target']!=r['target']:
            conflicts.append({'identity':list(key),'targets':[bykey[key]['target'],r['target']]})
        bykey[key]=r
    return {'status':'CONFLICTS_PRESENT' if conflicts else 'EXTRACTED' if records else 'NO_SUPPORTED_TABLE',
            'records':records,'excluded':excluded,'conflicts':conflicts,'source':source,
            'text_sha256':digest(text),'input_sha256':digest(document),'full_report_access_inferred':False,
            'consensus_computed':False,'limitation':'Reported dates remain provider-attributed; original report timing, firm identity and access are not independently authenticated. Unknown horizons are not promoted to twelve months.'}


def earnings_basis(document):
    """Compute individually identified multiples and preserve incompatible cohorts."""
    quote=document['quote'];require(quote.get('currency') and quote.get('share_basis'),'QUOTE_BASIS')
    require(not isinstance(quote['price'],bool),'PRICE_RANGE')
    price=float(quote['price']);require(price>0 and price<1e12,'PRICE_RANGE')
    cutoff=timestamp(document['as_of']);require(timestamp(quote['available_at'])<=cutoff,'FUTURE_QUOTE')
    results=[];require(len({r['id'] for r in document['estimates']})==len(document['estimates']),'UNIQUE_ESTIMATE_IDS')
    for row in document['estimates']:
        require(row.get('source') and row.get('id'),'ESTIMATE_SOURCE_ID')
        require(timestamp(row['available_at'])<=cutoff,'FUTURE_ESTIMATE')
        missing=[k for k in ['period_start','period_end','period_type','accounting_basis','share_basis','currency'] if not row.get(k)]
        if row.get('period_start') and row.get('period_end'):
            require(date.fromisoformat(row['period_start'])<=date.fromisoformat(row['period_end']),'EARNINGS_PERIOD_ORDER')
        mismatch=row.get('share_basis')!=quote['share_basis'] or row.get('currency')!=quote['currency']
        eps=row.get('eps');valid=type(eps) in (float,int) and eps>0 and eps<1e12
        status='UNRESOLVED_BASIS' if missing else 'INCOMPATIBLE_WITH_QUOTE' if mismatch else 'NONPOSITIVE_OR_UNKNOWN_EPS' if not valid else 'COMPUTED_EXPLICIT_BASIS'
        results.append({'id':row['id'],'status':status,'multiple':price/eps if status=='COMPUTED_EXPLICIT_BASIS' else None,
                        'cohort':{k:row.get(k) for k in ['period_start','period_end','period_type','accounting_basis','share_basis','currency']},
                        'missing_basis':missing,'source':row['source']})
    return {'results':results,'input_sha256':digest(document),'averaged_multiples':False,
            'limitation':'Separate fiscal/rolling and GAAP/adjusted cohorts. The calculation does not certify forecasts or establish fair value.'}


if __name__=='__main__':cli({'extract':extract,'earnings_basis':earnings_basis})
