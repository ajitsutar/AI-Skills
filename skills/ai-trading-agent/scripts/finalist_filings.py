"""Batch point-in-time SEC companyfacts discovery, original-filing extraction and normalization."""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.request import Request, build_opener
from zipfile import BadZipFile, ZipFile

import filing_documents
from deterministic_rank import digest
from filing_extract import extract_html
from financial_normalize import ADAPTER_FIELDS, normalize, policy
from primary_financial_data import cik_number, extract
from price_audit import timestamp


SEC_BULK = {'companyfacts.zip': 'https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip',
            'submissions.zip': 'https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip'}


def acquire_bulk(output):
    """Download both official nightly ZIPs once into an explicitly chosen private directory."""
    if os.environ.get('AI_TRADING_NETWORK_MODE', 'online') != 'online':
        raise ValueError('NETWORK_DISABLED_OR_INVALID_NETWORK_MODE')
    contact = os.environ.get('AI_TRADING_SEC_USER_AGENT', '')
    if (not re.search(r'[^\s@]+@[^\s@]+\.[^\s@]+', contact) or '\n' in contact
            or '\r' in contact or len(contact) > 240):
        raise ValueError('PRIVATE_IDENTIFYING_SEC_USER_AGENT_REQUIRED')
    root = filing_documents._output_dir(output)
    receipts = {}
    opener = build_opener(filing_documents._NoRedirect())
    for name, url in SEC_BULK.items():
        target = root / name
        total, sha = 0, hashlib.sha256()
        started = time.monotonic()
        owned = None
        try:
            req = Request(url, headers={'User-Agent': contact, 'Accept-Encoding': 'identity'})
            with opener.open(req, timeout=60) as response, target.open('xb') as stream:
                owned = os.fstat(stream.fileno())
                if response.geturl() != url or response.status != 200:
                    raise ValueError('SEC_BULK_SOURCE_OR_STATUS_MISMATCH')
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 4 * 1024**3 or time.monotonic() - started > 1800:
                        raise ValueError('SEC_BULK_SIZE_OR_TIME_LIMIT')
                    stream.write(chunk)
                    sha.update(chunk)
            with ZipFile(target) as archive:
                if not archive.infolist():
                    raise ValueError('SEC_BULK_ARCHIVE_EMPTY')
        except (OSError, ValueError, BadZipFile):
            if owned is not None:
                try:
                    if os.path.samestat(owned, target.lstat()):
                        target.unlink()
                except FileNotFoundError:
                    pass
            raise
        receipts[name] = {'url': url, 'bytes': total, 'sha256': sha.hexdigest(),
                          'retrieved_at': filing_documents.now()}
        _save(root / (name + '.receipt.json'), receipts[name])
    return receipts


class BulkMembers:
    """Read named members without expanding either nightly archive."""

    def __init__(self, archive):
        self.archive = archive
        self.count = Counter(archive.namelist())

    def read(self, name):
        if self.count[name] != 1:
            raise ValueError('MISSING_OR_AMBIGUOUS_BULK_MEMBER:' + name)
        info = self.archive.getinfo(name)
        if info.file_size > 64 * 1024 * 1024:
            raise ValueError('SEC_MEMBER_EXCEEDS_64_MIB')
        raw = self.archive.read(info)
        return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _save(path, obj):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(obj, stream, indent=2, allow_nan=False)
        stream.write('\n')


def _filings(columns, accessions):
    keys = ('accessionNumber', 'form', 'filingDate', 'primaryDocument')
    arrays = [columns[k] for k in keys]
    if not all(isinstance(v, list) and len(v) == len(arrays[0]) for v in arrays):
        raise ValueError('MISALIGNED_SUBMISSIONS_COLUMNS')
    return [dict(zip(keys, row)) for row in zip(*arrays) if row[0] in accessions]


def _select(submissions, issuer, candidates):
    cik = cik_number(issuer['cik'])
    name = 'CIK' + cik + '.json'
    index, sha = submissions.read(name)
    if cik_number(str(index['cik'])) != cik:
        raise ValueError('SUBMISSIONS_CIK_MISMATCH')
    provenance = {name: sha}
    # Select only independently identified accessions from the eligible API rows.
    eligible = {(r['accession'], r['form'], r['filed']) for r in candidates['facts']}
    wanted = {r[0] for r in eligible}
    if len(wanted) != len(eligible):
        raise ValueError('CONFLICTING_COMPANYFACTS_ACCESSION_METADATA')
    if 'accessions' in issuer:
        selected = issuer['accessions']
        if not isinstance(selected, list) or not selected or not all(isinstance(x, str) for x in selected):
            raise ValueError('EXPLICIT_ACCESSION_LIST_REQUIRED')
        if len(set(selected)) != len(selected) or set(selected) - wanted:
            raise ValueError('REQUESTED_ACCESSION_OUTSIDE_ADMISSIBLE_COMPANYFACTS')
        wanted = set(selected)
    else:
        wanted = {acc for acc, _, day in sorted(eligible, key=lambda r: (r[2], r[0]), reverse=True)[:8]}
    rows = _filings(index['filings']['recent'], wanted)
    for historical in index['filings'].get('files', []):
        missing = wanted - {r['accessionNumber'] for r in rows}
        if not missing:
            break
        first, last = historical['filingFrom'], historical['filingTo']
        if not any(first <= day <= last and acc in missing for acc, form, day in eligible):
            continue
        old_name = historical['name']
        if not re.fullmatch(r'CIK' + cik + r'-submissions-[0-9]+\.json', old_name):
            raise ValueError('UNEXPECTED_HISTORICAL_SUBMISSIONS_MEMBER')
        older, old_sha = submissions.read(old_name)
        provenance[old_name] = old_sha
        rows.extend(_filings(older, missing))
    indexed = {}
    for row in rows:
        acc = row['accessionNumber']
        if (acc, row['form'], row['filingDate']) not in eligible or acc in indexed:
            raise ValueError('CONFLICTING_ACCESSION_METADATA:' + acc)
        filename = row['primaryDocument']
        url = 'https://www.sec.gov/Archives/edgar/data/' + str(int(cik)) + '/' + acc.replace('-', '') + '/' + filename
        filing_documents.validate_sec_url(url)
        indexed[acc] = {**row, 'url': url}
    if wanted - indexed.keys():
        raise ValueError('ACCESSIONS_MISSING_FROM_SUBMISSIONS')
    ordered = sorted(indexed.values(), key=lambda r: (r['filingDate'], r['accessionNumber']), reverse=True)
    return ordered, provenance


def _issuer(issuer, request, facts_zip, submissions, run, originals, fetch, stopped):
    cik = cik_number(issuer['cik'])
    original_reviews = issuer.get('reviewed_originals', {})
    if not isinstance(original_reviews, dict) or any(not isinstance(v, dict) for v in original_reviews.values()):
        raise ValueError('REVIEWED_ORIGINALS_MUST_MAP_ACCESSIONS_TO_REVIEWS')
    latest_review = issuer.get('latest_public_period_review', {})
    if not isinstance(latest_review, dict):
        raise ValueError('LATEST_PUBLIC_PERIOD_REVIEW_MUST_BE_AN_OBJECT')
    transcriptions = issuer.get('reviewed_transcriptions', [])
    if not isinstance(transcriptions, list) or any(not isinstance(r, dict) for r in transcriptions):
        raise ValueError('REVIEWED_TRANSCRIPTIONS_MUST_BE_A_LIST_OF_RECORDS')
    if any(r.get('entity_id') != cik or not isinstance(r.get('review'), dict)
           or not isinstance(r.get('concept'), str) for r in transcriptions):
        raise ValueError('REVIEWED_TRANSCRIPTION_ENTITY_CONCEPT_OR_REVIEW_INVALID')
    raw, sha = facts_zip.read('CIK' + cik + '.json')
    candidates = extract(raw, cik, request['information_cutoff'], request['concepts'])
    _save(run / 'companyfacts-candidates.json', candidates)
    filings, provenance = _select(submissions, issuer, candidates)
    scope = {k: issuer[k] for k in ('issuer_id', 'adapter', 'ttm_start', 'financial_period_end')}
    scope['entity_id'] = cik
    scope['latest_public_period_review'] = latest_review
    document = {'schema_version': 1, 'policy_sha256': digest(policy()),
                'information_cutoff': request['information_cutoff'], 'issuers': [scope],
                'sources': [], 'documents': [], 'transcriptions': transcriptions}
    disposition = []
    for filing in filings:
        acc = filing['accessionNumber']
        row = {'accession': acc, 'url': filing['url'], 'filed': filing['filingDate'], 'source_verified': False}
        disposition.append(row)
        try:
            metadata = {'source_id': acc, 'form_type': filing['form'], 'accession': acc}
            target = run / acc
            review = original_reviews.get(acc, {})
            if originals is not None:
                local = originals / ('CIK' + cik) / acc / filing['primaryDocument']
                if not local.resolve().is_relative_to(originals.resolve()):
                    raise ValueError('RETAINED_ORIGINAL_OUTSIDE_INPUT_ROOT')
                report = filing_documents.ingest_document(local, target, source_url=filing['url'],
                            retrieved_at=filing_documents.now(), **metadata)
                verified = (review.get('sha256') == report['raw_sha256'] and review.get('url') == filing['url']
                            and isinstance(review.get('evidence'), str) and bool(review['evidence'].strip()))
                evidence = review.get('evidence') if verified else 'Original supplied without a matching source review'
            else:
                if not fetch or stopped[0]:
                    raise ValueError('ORIGINAL_REQUIRES_EXPLICIT_FETCH_OR_RETAINED_INPUT')
                time.sleep(0.2)
                report = filing_documents.fetch_document(filing['url'], target, **metadata)
                verified = True
                evidence = 'Original bytes fetched from indexed SEC primary document'
            original = (target / 'original.bin').read_bytes()
            if hashlib.sha256(original).hexdigest() != report['raw_sha256']:
                raise ValueError('RETAINED_FILING_BYTES_CHANGED')
            content, _ = filing_documents._decode(original, '')
            inline = extract_html(content)
            extract_sha = digest(inline)
            row.update(source_verified=bool(verified), raw_sha256=report['raw_sha256'])
            source = {'source_id': acc, 'document_origin': 'regulatory_filing',
                      'delivery': 'regulator' if fetch and originals is None else 'mirror',
                      'distribution_host': 'www.sec.gov' if originals is None else 'retained copy',
                      'uri': filing['url'],
                      'publication': {'precision': 'date', 'date': filing['filingDate'],
                                      'timezone': 'America/New_York'},
                      'retrieved_at': report['identity']['retrieved_at'],
                      'content_sha256': report['raw_sha256'], 'extract_sha256': extract_sha,
                      'verification': {'status': 'verified' if verified else 'unverified',
                                       'method': 'SEC acquisition or reviewed original digest',
                                       'evidence': [evidence], 'primary_content_matched': bool(verified)}}
            document['sources'].append(source)
            document['documents'].append({'source_id': acc, 'extract': inline, 'extract_sha256': extract_sha})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row['reason'] = str(exc)
            if any(code in str(exc) for code in ('SEC_HTTP_ERROR_403', 'SEC_HTTP_ERROR_429')):
                stopped[0] = True
    _save(run / 'normalization-input.json', document)
    result = normalize(document)
    _save(run / 'normalization.json', result)
    ready = bool(filings) and all(r['source_verified'] for r in disposition) and result['status'] == 'READY'
    return {'issuer_id': issuer['issuer_id'], 'cik': cik, 'status': 'FILING_VERIFIED' if ready else 'UNVERIFIED',
            'filing_verified': ready, 'companyfacts_member_sha256': sha, 'submissions_members': provenance,
            'companyfacts_gaps': candidates['gaps'], 'selected_filings': disposition,
            'normalization_status': result['status'], 'gaps': result['issuers'][0]['gaps']}


def run_batch(request, facts_archive, submissions_archive, output, originals=None, fetch_documents=False):
    """A partial batch retains one outcome for every requested issuer and original evidence off-package."""
    timestamp(request['information_cutoff'])
    issuers = request['issuers']
    if not isinstance(issuers, list) or not issuers or not request['concepts']:
        raise ValueError('NONEMPTY_ISSUERS_AND_CONCEPTS_REQUIRED')
    ciks = [cik_number(i['cik']) for i in issuers]
    if (len(set(ciks)) != len(ciks) or len({i['issuer_id'] for i in issuers}) != len(issuers)
            or any(i['adapter'] not in ADAPTER_FIELDS for i in issuers)):
        raise ValueError('UNIQUE_ISSUERS_CIKS_AND_SUPPORTED_ADAPTERS_REQUIRED')
    if fetch_documents and originals is not None:
        raise ValueError('SELECT_ONE_ORIGINAL_FILING_ROUTE')
    if fetch_documents and (os.environ.get('AI_TRADING_NETWORK_MODE', 'online') != 'online'
                            or not os.environ.get('AI_TRADING_SEC_USER_AGENT')):
        raise ValueError('ONLINE_MODE_AND_PRIVATE_SEC_CONTACT_REQUIRED')
    if originals is not None:
        originals = Path(originals)
    with ZipFile(facts_archive) as facts, ZipFile(submissions_archive) as subs:
        facts_zip, submissions = BulkMembers(facts), BulkMembers(subs)
        root = filing_documents._output_dir(output)
        rows, stopped = [], [False]
        for issuer, cik in zip(issuers, ciks):
            run = root / ('CIK' + cik)
            run.mkdir()
            try:
                row = _issuer(issuer, request, facts_zip, submissions, run, originals, fetch_documents, stopped)
            except (BadZipFile, OSError, ValueError, KeyError, TypeError) as exc:
                row = {'issuer_id': issuer['issuer_id'], 'cik': cik, 'status': 'UNVERIFIED',
                       'filing_verified': False, 'reason': str(exc)}
            _save(run / 'review.json', row)
            rows.append(row)
    result = {'information_cutoff': request['information_cutoff'], 'request_sha256': digest(request),
              'issuers': rows, 'requested': len(rows), 'filing_verified': sum(r['filing_verified'] for r in rows),
              'sec_fetch_stopped_by_provider': stopped[0]}
    _save(root / 'batch-review.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ['fetch-bulk']:
        parser.add_argument('operation', choices=['fetch-bulk'])
        parser.add_argument('output', type=Path)
        print(json.dumps(acquire_bulk(parser.parse_args().output), indent=2))
        return
    for arg in ('request', 'companyfacts_zip', 'submissions_zip', 'output'):
        parser.add_argument(arg, type=Path)
    route = parser.add_mutually_exclusive_group()
    route.add_argument('--originals', type=Path)
    route.add_argument('--fetch-documents', action='store_true')
    args = parser.parse_args()
    result = run_batch(json.loads(args.request.read_text(encoding='utf-8-sig')), args.companyfacts_zip,
                       args.submissions_zip, args.output, args.originals, args.fetch_documents)
    print(json.dumps({k: v for k, v in result.items() if k != 'issuers'}, indent=2))


if __name__ == '__main__':
    main()
