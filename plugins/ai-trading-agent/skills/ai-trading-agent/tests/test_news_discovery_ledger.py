"""Discovery routing regressions with synthetic sources, independent of private cases."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import news_analysis as na


class DiscoveryLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.aliases = {'NOVA': ['Nova Components'], 'BETA': ['Beta Services']}

    def record(self, text='Factory demand faces uncertainty', identity='source-1'):
        path = self.root / (identity + '.txt')
        raw = ('Publisher header\n' + text + '\n').encode('utf-8')
        path.write_bytes(raw)
        return {'id': identity, 'source_kind': 'publisher', 'access_tier': 'HEADLINE_ONLY',
                'source': {'path': path.name, 'sha256': hashlib.sha256(raw).hexdigest(), 'excerpt': text},
                'claimed_issuers': ['NOVA'], 'scope_issuers': []}

    def request(self, *records):
        return {'schema_version': 1, 'issuer_aliases': deepcopy(self.aliases), 'records': list(records)}

    def run_record(self, record):
        return na.discovery_ledger(self.request(record), self.root)['records'][0]

    def test_generic_headline_does_not_support_claim(self):
        result = na.discovery_ledger(self.request(self.record()), self.root)
        row = result['records'][0]
        self.assertEqual(row['text_candidates'], [])
        self.assertEqual(row['claim_diagnostics'][0]['status'], 'NO_MATCHING_TEXT_CANDIDATE')
        self.assertEqual(row['issuer_relevance'], 'UNRESOLVED')
        self.assertEqual(result['status'], 'DIAGNOSTICS_PRESENT')

    def test_scope_and_exchange_field_are_not_text_evidence(self):
        record = self.record()
        record.update(source_kind='exchange', scope_issuers=['NOVA'], exchange_fields={'IssueSymbol': 'NOVA'})
        row = self.run_record(record)
        self.assertEqual(row['declared_scope_issuers'], ['NOVA'])
        self.assertEqual(row['text_candidates'], [])
        self.assertEqual(row['claim_diagnostics'][0]['status'], 'NO_MATCHING_TEXT_CANDIDATE')

    def test_full_alias_is_candidate_not_verified_identity(self):
        row = self.run_record(self.record('Nova Components opens a plant'))
        self.assertEqual(row['text_candidates'], ['NOVA'])
        self.assertEqual(row['claim_diagnostics'][0]['status'], 'SUPPORTED_TEXT_CANDIDATE')
        self.assertEqual(row['issuer_relevance'], 'UNRESOLVED')
        self.assertFalse(row['semantic_identity_verified'])
        self.assertFalse(row['source_authenticity_verified'])

    def test_cashtag_and_multiple_candidates_remain_unresolved(self):
        row = self.run_record(self.record('$NOVA and Beta Services in market discussion'))
        self.assertEqual(row['text_candidates'], ['BETA', 'NOVA'])
        self.assertTrue(row['requires_semantic_review'])
        self.assertEqual(row['issuer_relevance'], 'UNRESOLVED')

    def test_disclaimer_and_negation_are_not_certified(self):
        row = self.run_record(self.record('This club is not Nova Components and has no relationship with it.'))
        self.assertEqual(row['text_candidates'], ['NOVA'])
        self.assertEqual(row['issuer_relevance'], 'UNRESOLVED')
        self.assertFalse(row['semantic_identity_verified'])

    def test_industry_context_without_named_company_remains_available(self):
        record = self.record()
        record['claimed_issuers'] = []
        record['industry_context'] = 'Industrial supply chain context; not issuer-specific.'
        result = na.discovery_ledger(self.request(record), self.root)
        self.assertEqual(len(result['records']), 1)
        self.assertEqual(result['records'][0]['declared_industry_context'], record['industry_context'])
        self.assertEqual(result['records'][0]['text_support_status'], 'NO_TEXT_CANDIDATE')
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')

    def test_tamper_does_not_leave_candidate_from_unverified_excerpt(self):
        record = self.record('Nova Components expands')
        (self.root / record['source']['path']).write_text('Different bytes', encoding='utf-8')
        row = self.run_record(record)
        self.assertEqual(row['source_binding']['diagnostic'], 'SOURCE_HASH_MISMATCH')
        self.assertEqual(row['text_candidates'], [])
        self.assertEqual(row['claim_diagnostics'][0]['status'], 'UNRESOLVED_INVALID_PROVENANCE')

    def test_invented_excerpt_not_in_verified_file(self):
        record = self.record()
        record['source']['excerpt'] = 'Nova Components expands'
        row = self.run_record(record)
        self.assertEqual(row['source_binding']['diagnostic'], 'EXCERPT_NOT_IN_SOURCE')
        self.assertEqual(row['text_support_status'], 'INVALID_PROVENANCE')

    def test_missing_file_is_retained_not_silently_dropped(self):
        record = self.record()
        (self.root / record['source']['path']).unlink()
        row = self.run_record(record)
        self.assertEqual(row['source_binding']['status'], 'INVALID')
        self.assertEqual(row['id'], record['id'])

    def test_absolute_foreign_and_parent_escape_paths_rejected(self):
        for value in ('../outside.txt', '/outside.txt', 'C:\\outside.txt', '\\\\host\\share\\item.txt'):
            with self.subTest(value=value):
                record = self.record()
                record['source']['path'] = value
                self.assertEqual(self.run_record(record)['source_binding']['status'], 'INVALID')

    def test_original_input_and_record_order_preserved_without_mutation(self):
        request = self.request(self.record(identity='second'), self.record(identity='first'))
        request['records'][0]['comment'] = 'Caller note remains declared'
        original = deepcopy(request)
        result = na.discovery_ledger(request, self.root)
        self.assertEqual(request, original)
        self.assertEqual(result['declared_input'], original)
        self.assertEqual([r['id'] for r in result['records']], ['second', 'first'])
        result['declared_input']['records'][0]['id'] = 'changed-copy'
        self.assertEqual(request, original)

    def test_empty_excerpt_bad_schema_duplicate_ids_and_bad_aliases_rejected(self):
        requests = []
        empty = self.request(self.record()); empty['records'][0]['source']['excerpt'] = ' '
        requests.append(empty)
        boolean = self.request(self.record()); boolean['schema_version'] = True
        requests.append(boolean)
        malformed = self.request(self.record()); malformed['issuer_aliases']['NOVA'] = 'Nova Components'
        requests.append(malformed)
        duplicate = self.request(self.record(), self.record())
        requests.append(duplicate)
        for request in requests:
            with self.subTest(request=request):
                with self.assertRaises(ValueError):
                    na.discovery_ledger(request, self.root)

    def test_bare_short_ticker_not_a_candidate(self):
        record = self.record('ALL and IT are ordinary words here')
        request = self.request(record)
        request['issuer_aliases'] = {'ALL': ['Allstate Corporation'], 'IT': ['Gartner']}
        self.assertEqual(na.discovery_ledger(request, self.root)['records'][0]['text_candidates'], [])

    def test_existing_matcher_reused_and_no_sentiment_or_timestamps_required(self):
        with patch.object(na, 'issuers', wraps=na.issuers) as matcher, \
                patch.object(na, 'sentiment', side_effect=AssertionError('No sentiment requested')):
            result = na.discovery_ledger(self.request(self.record()), self.root)
        matcher.assert_called_once()
        self.assertEqual(matcher.call_args.args[0]['scope_issuers'], [])
        self.assertNotIn('as_of', result)
        self.assertNotIn('language', result['records'][0])

    def test_cli_produces_checked_ledger(self):
        request = self.request(self.record())
        input_path, output_path = self.root / 'request.json', self.root / 'result.json'
        input_path.write_text(json.dumps(request), encoding='utf-8')
        completed = subprocess.run([sys.executable, '-B', str(SCRIPTS / 'news_analysis.py'), 'discovery',
                                    str(input_path), str(self.root), str(output_path)],
                                   text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(output_path.read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'DIAGNOSTICS_PRESENT')
        self.assertEqual(result['declared_input'], request)


if __name__ == '__main__':
    unittest.main()
