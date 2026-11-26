"""Invented originals and compressed archives exercise the same paths as the CLI."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from finalist_filings import acquire_bulk, run_batch, SEC_BULK
import test_financial_normalization as financial_fixtures


def issuer(number):
    cik = str(number).zfill(10)
    return {'issuer_id': 'FICT-' + cik, 'cik': cik, 'adapter': 'other_financial',
            'ttm_start': '2025-07-01', 'financial_period_end': '2026-06-30'}


def request(issuers):
    return {'issuers': issuers, 'information_cutoff': '2026-08-02T12:00:00Z',
            'concepts': [{'name': 'assets', 'namespace': 'us-gaap', 'tag': 'Assets', 'unit': 'USD'}]}


def archives(root, issuers):
    facts, subs = root / 'companyfacts.zip', root / 'submissions.zip'
    with ZipFile(facts, 'w') as f, ZipFile(subs, 'w') as s:
        for i in issuers:
            cik = i['cik']
            acc = cik + '-26-000001'
            later = cik + '-26-000002'
            rows = [{'accn': a, 'form': '10-Q', 'filed': day, 'end': '2026-06-30', 'val': 200000000}
                    for a, day in [(acc, '2026-07-31'), (later, '2026-08-03')]]
            f.writestr('CIK' + cik + '.json', json.dumps({'cik': int(cik), 'facts': {'us-gaap':
                       {'Assets': {'units': {'USD': rows}}}}}))
            oldname = 'CIK' + cik + '-submissions-001.json'
            s.writestr('CIK' + cik + '.json', json.dumps({'cik': cik, 'filings': {'recent':
                {'accessionNumber': [later], 'form': ['10-Q'], 'filingDate': ['2026-08-03'],
                 'primaryDocument': ['future.htm']}, 'files': [{'name': oldname,
                 'filingFrom': '2026-07-31', 'filingTo': '2026-07-31'}]}}))
            s.writestr(oldname, json.dumps({'accessionNumber': [acc], 'form': ['10-Q'],
                        'filingDate': ['2026-07-31'], 'primaryDocument': ['filing.htm']}))
    return facts, subs


class BatchTests(unittest.TestCase):
    def test_bad_nested_review_leaves_other_issuer_evidence_intact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            issuers = [issuer(1), issuer(2)]
            facts, subs = archives(root, issuers)
            for n, invalid in enumerate([{'reviewed_transcriptions': [None]}, {'reviewed_originals': []},
                                         {'reviewed_originals': {'x': None}}, {'latest_public_period_review': 3}]):
                with self.subTest(invalid=invalid):
                    rows = [{**issuers[0], **invalid}, issuers[1]]
                    result = run_batch(request(rows), facts, subs, root / str(n))
                    first, second = result['issuers']
                    self.assertEqual(result['requested'], 2)
                    self.assertFalse(first['filing_verified'])
                    self.assertIn('MUST_', first['reason'])
                    self.assertEqual(second['issuer_id'], issuers[1]['issuer_id'])
                    self.assertEqual(len(second['selected_filings']), 1)

    def test_competing_output_survives_network_or_exclusive_open_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            for failure in ('network', 'exclusive_open'):
                with self.subTest(failure=failure):
                    root = Path(temp).resolve() / failure
                    other = root / 'companyfacts.zip'
                    def competing(*args, **kwargs):
                        other.write_bytes(b'existing caller data')
                        if failure == 'network':
                            raise OSError('simulated failure')
                        return MagicMock()
                    with patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online',
                                    'AI_TRADING_SEC_USER_AGENT': 'Fictional contact@example.invalid'}), \
                         patch('finalist_filings.build_opener') as factory:
                        factory.return_value.open.side_effect = competing
                        with self.assertRaises(OSError):
                            acquire_bulk(root)
                    self.assertEqual(other.read_bytes(), b'existing caller data')

    def test_bulk_streams_named_archives_and_preserves_receipts_without_contact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            memory = io.BytesIO()
            with ZipFile(memory, 'w') as archive:
                archive.writestr('CIK0000000001.json', '{}')
            payload = memory.getvalue()
            def response(request, timeout):
                r = MagicMock()
                r.__enter__.return_value = r
                r.status = 200
                r.geturl.return_value = request.full_url
                r.read.side_effect = [payload, b'']
                return r
            with patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online',
                            'AI_TRADING_SEC_USER_AGENT': 'Fictional agent contact@example.invalid'}), \
                 patch('finalist_filings.build_opener') as factory:
                factory.return_value.open.side_effect = response
                receipts = acquire_bulk(root / 'bulk')
            self.assertEqual(set(receipts), set(SEC_BULK))
            for name, record in receipts.items():
                self.assertEqual((root / 'bulk' / name).read_bytes(), payload)
                self.assertEqual(record['sha256'], hashlib.sha256(payload).hexdigest())
                self.assertNotIn('@', json.dumps(record))

    def test_sixty_finalists_keep_all_outcomes_and_select_only_admissible_originals(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            issuers = [issuer(n) for n in range(1, 61)]
            facts, subs = archives(root, issuers[:-1])
            r = run_batch(request(issuers), facts, subs, root / 'out')
            self.assertEqual((r['requested'], r['filing_verified']), (60, 0))
            first, missing = r['issuers'][0], r['issuers'][-1]
            self.assertEqual(len(first['submissions_members']), 2)
            selected, = first['selected_filings']
            self.assertIn('-26-000001', selected['accession'])
            self.assertFalse(selected['source_verified'])
            self.assertIn('MISSING_OR_AMBIGUOUS', missing['reason'])
            self.assertEqual(json.loads((root / 'out/batch-review.json').read_text()), r)

    def test_reviewed_original_and_complete_basis_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            i = issuer(1)
            facts, subs = archives(root, [i])
            cik = i['cik']
            acc = cik + '-26-000001'
            directory = root / 'originals' / ('CIK' + cik) / acc
            directory.mkdir(parents=True)
            original = financial_fixtures.InlineTests.html().replace('>E</xbrli:identifier>', '>' + cik + '</xbrli:identifier>').encode()
            (directory / 'filing.htm').write_bytes(original)
            bounds = request([i])
            i['latest_public_period_review'] = {'status': 'reviewed', 'information_as_of': bounds['information_cutoff'],
                 'period_end': i['financial_period_end'], 'evidence': 'FICTIONAL dated review', 'source_ids': [acc]}
            i['reviewed_originals'] = {acc: {'sha256': hashlib.sha256(original).hexdigest(),
                 'url': 'https://www.sec.gov/Archives/edgar/data/1/' + acc.replace('-', '') + '/filing.htm',
                 'evidence': 'FICTIONAL retained hash matched indexed primary copy'}}
            items = [('common_income', '2025-07-01', '2026-06-30'), ('common_equity', None, '2025-06-30'),
                     ('common_equity', None, '2026-06-30')]
            items.extend((c, None, '2026-06-30') for c in ('debt_current', 'debt_noncurrent',
                         'finance_leases_current', 'finance_leases_noncurrent'))
            i['reviewed_transcriptions'] = [financial_fixtures.record(c, 30, cik, start, end, source=acc) for c, start, end in items]
            result = run_batch(bounds, facts, subs, root / 'pass', root / 'originals')
            self.assertTrue(result['issuers'][0]['filing_verified'], result['issuers'][0])
            i['reviewed_originals'][acc]['sha256'] = 'a' * 64
            result = run_batch(bounds, facts, subs, root / 'fail', root / 'originals')
            self.assertFalse(result['issuers'][0]['filing_verified'])
            self.assertEqual(result['issuers'][0]['normalization_status'], 'INCOMPLETE')

    def test_denial_stops_network_across_remaining_issuers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            issuers = [issuer(1), issuer(2)]
            facts, subs = archives(root, issuers)
            with patch.dict(os.environ, {'AI_TRADING_NETWORK_MODE': 'online', 'AI_TRADING_SEC_USER_AGENT': 'fictional'}), \
                 patch('finalist_filings.time.sleep'), patch('filing_documents.fetch_document',
                 side_effect=ValueError('SEC_HTTP_ERROR_429_NO_RETRY')) as fetch:
                r = run_batch(request(issuers), facts, subs, root / 'out', fetch_documents=True)
                self.assertTrue(r['sec_fetch_stopped_by_provider'])
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(r['filing_verified'], 0)
