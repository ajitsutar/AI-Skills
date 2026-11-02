"""Conservative SEC companyfacts retrieval and dated candidate extraction.

API facts are extraction candidates, not verified normalization records. Original
filings and accounting-basis reviews remain necessary, particularly for banks/REITs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from quant_common import digest, require, scalar, timestamp


def cik_number(cik):
    require(isinstance(cik, str) and bool(re.fullmatch(r'\d{1,10}', cik)) and int(cik) > 0, 'CIK_REQUIRED')
    return str(int(cik)).zfill(10)


def extract(payload, cik, information_cutoff, concepts):
    identity = cik_number(cik)
    require(str(payload['cik']).zfill(10) == identity, 'ISSUER_CIK_MISMATCH')
    cutoff = timestamp(information_cutoff)
    require(concepts and len({c['name'] for c in concepts}) == len(concepts), 'UNIQUE_CONCEPT_REQUESTS')
    facts, gaps = [], []
    for spec in concepts:
        # Explicit taxonomy/tag/unit; do not equate economically different labels.
        namespace, tag, unit = spec['namespace'], spec['tag'], spec['unit']
        require(namespace in {'us-gaap', 'ifrs-full', 'dei'}, 'API_TAXONOMY_UNSUPPORTED')
        block = payload.get('facts', {}).get(namespace, {}).get(tag, {})
        candidates = []
        for row in block.get('units', {}).get(unit, []):
            if row.get('form') not in {'10-K', '10-K/A', '10-Q', '10-Q/A', '20-F', '20-F/A', '40-F', '40-F/A'}:
                continue
            filed = date.fromisoformat(row['filed'])
            # API date alone cannot prove availability before the same day's close.
            available_by = datetime.combine(filed+timedelta(days=1), time.min,
                                            ZoneInfo('America/New_York')).astimezone(timezone.utc)
            end = date.fromisoformat(row['end'])
            if available_by > cutoff or end > cutoff.date():
                continue
            start = row.get('start')
            require(start is None or date.fromisoformat(start) <= end, 'REVERSED_FINANCIAL_PERIOD')
            acc = row['accn']
            require(bool(re.fullmatch(r'\d{10}-\d{2}-\d{6}', acc)), 'ACCESSION_INVALID')
            value = scalar(row['val'], spec['name'])
            candidates.append({'name': spec['name'], 'concept': namespace+':'+tag,
                'unit': unit, 'value': value, 'period_start': start, 'period_end': row['end'],
                'filed': row['filed'], 'available_by_conservative': available_by.isoformat(),
                'accession': acc, 'form': row['form'], 'api_fact_sha256': digest(row),
                'filing_index_url': 'https://www.sec.gov/Archives/edgar/data/'+str(int(cik))+'/'+acc.replace('-', '')+'/'+acc+'-index.html'})
        # Preserve all known revisions; a latest-filing guess cannot resolve a basis conflict.
        unique = {digest(r): r for r in candidates}
        selected = sorted(unique.values(), key=lambda r: (r['period_end'], r['period_start'] or '', r['filed'], r['accession']))
        if not selected:
            gaps.append({'name': spec['name'], 'reason': 'NO_ADMISSIBLE_FACT_AT_CUTOFF',
                         'next_source': 'Issuer filing/earnings supplement; reviewed transcription if standard API tag absent'})
        facts.extend(selected)
    return {'status': 'EXTRACTION_CANDIDATES', 'cik': identity, 'facts': facts, 'gaps': gaps,
            'payload_sha256': digest(payload), 'information_cutoff': information_cutoff,
            'filing_eligibility_established': False,
            'limitation': 'API omits original context/accuracy and many custom tags. Verify units, legal entity, GAAP/non-GAAP basis, original filing and amendments before normalization.'}


def coverage_plan(normalization_input):
    """Recompute diagnostics and assign actual missing fields to source reviews."""
    from financial_normalize import normalize
    normalization_result = normalize(normalization_input)
    routes = {
                'corporate': ['SEC companyfacts candidates', 'Original issuer 10-K/10-Q notes', 'Reviewed capex/debt components'],
                'bank': ['Holding-company filing/Pillar 3 supplement', 'Standardized CET1 and RWA', 'Tangible common equity and loan-scope reconciliation'],
                'equity_reit': ['Issuer supplemental tables', 'Unadjusted Nareit FFO-to-GAAP bridge', 'Property purchases/development without duplicate capex'],
                'insurer': ['Statutory/GAAP reconciliation and segment underwriting data', 'Reserve adequacy and capital review'],
                'other_financial': ['Parent common equity and common-income filing notes', 'Funding and leverage review']}
    tasks = [{'issuer_id': issuer['issuer_id'], 'adapter': issuer['adapter'],
              'field': gap['field'], 'reason': gap['reason'], 'sources_to_review': routes[issuer['adapter']]}
             for issuer in normalization_result['issuers'] for gap in issuer['gaps']]
    return {'status': 'PRIMARY_EVIDENCE_REQUIRED' if tasks else 'NORMALIZATION_COMPONENTS_READY',
            'normalization_input_sha256': digest(normalization_input), 'tasks': tasks,
            'ready_issuers': [i['issuer_id'] for i in normalization_result['issuers'] if i['status'] == 'READY'],
            'filing_eligibility_established': False,
            'limitation': 'FFIEC bank-subsidiary data are not interchangeable with listed holding-company financials. Never label missing specialized metrics permanently unsupported or silently use corporate multiples.'}


def fetch(cik, user_agent, output, session=None):
    """One public SEC request, no retries on denial, no arbitrary URLs/credentials."""
    import requests
    identity = cik_number(cik)
    require(isinstance(user_agent, str) and len(user_agent) >= 8 and '@' in user_agent
            and '\n' not in user_agent and '\r' not in user_agent, 'SEC_CONTACT_USER_AGENT_REQUIRED')
    output = Path(output)
    require(not output.exists(), 'OUTPUT_MUST_NOT_EXIST')
    url = 'https://data.sec.gov/api/xbrl/companyfacts/CIK'+identity+'.json'
    client = session or requests.Session()
    try:
        response = client.get(url, headers={'User-Agent': user_agent, 'Accept': 'application/json'},
                              timeout=30, allow_redirects=False)
        require(response.status_code == 200, 'SEC_UNAVAILABLE_STATUS:'+str(response.status_code))
        require(len(response.content) <= 50_000_000, 'SEC_RESPONSE_TOO_LARGE')
        payload = response.json()
        require(str(payload['cik']).zfill(10) == identity, 'SEC_RESPONSE_CIK_MISMATCH')
        output.mkdir(parents=True)
        (output/'companyfacts.json').write_bytes(response.content)
        receipt = {'uri': url, 'cik': identity, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                   'content_sha256': hashlib.sha256(response.content).hexdigest(),
                   'source': 'SEC companyfacts', 'credentials_retained': False}
        (output/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
        return receipt
    finally:
        if session is None:
            client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    acquire = sub.add_parser('fetch')
    acquire.add_argument('--cik', required=True)
    acquire.add_argument('--user-agent', required=True)
    acquire.add_argument('--output', required=True, type=Path)
    select = sub.add_parser('extract')
    select.add_argument('input', type=Path)
    args = parser.parse_args()
    if args.operation == 'fetch':
        result = fetch(args.cik, args.user_agent, args.output)
    else:
        result = extract(**json.loads(args.input.read_text(encoding='utf-8-sig')))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
