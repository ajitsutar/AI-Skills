"""Portable own-record metadata counterexamples and native report replay."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_sources as module
import final_report
from source_claims import Corpus


class AnalystSourceMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='analyst-metadata-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.originals = self.root / 'originals'
        self.originals.mkdir()
        self.manifest = self.root / 'manifest.json'
        self.request = {
            'as_of': '2032-04-20T12:00:00Z',
            'cohort': {'issuer': 'SYN', 'currency': 'EUR',
                       'price_basis': 'common_share_unadjusted',
                       'target_horizon': 'forward_12_months'},
            'extraction_profile': {'formats': ['json_records']}}

    def row(self, **changes):
        return {
            'firm_id': 'Quill', 'analyst_id': 'ResearcherQ', 'issuer': 'SYN',
            'currency': 'EUR', 'target': 41, 'issued_at': '2032-04-04T10:00:00Z',
            'price_basis': 'common_share_unadjusted',
            'target_horizon': 'forward_12_months', 'access': 'FULL_REPORT',
            'source': {'published_at': '2032-04-04T11:00:00Z',
                       'observed_at': '2032-04-04T12:00:00Z',
                       'url': 'https://example.test/research/quill'}, **changes}

    def prepare(self, document):
        raw = json.dumps(document, ensure_ascii=False).encode('utf-8')
        (self.originals / 'record.json').write_bytes(raw)
        manifest = {'schema_version': 1, 'sources': [
            {'id': 'record', 'path': 'record.json', 'format': 'json',
             'sha256': hashlib.sha256(raw).hexdigest()}]}
        self.manifest.write_bytes(json.dumps(manifest).encode())
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        return raw

    def analyze(self, document):
        self.prepare(document)
        return module.analyze(self.request, self.manifest, self.pin, self.originals)

    def assert_unavailable(self, out):
        consensus = out['eligible_cohort']['result']['consensus']
        self.assertEqual(consensus['status'], 'UNAVAILABLE')
        self.assertEqual(consensus['independent_firms'], 0)

    def test_nested_metadata_exact_escaped_pointers(self):
        out = self.analyze({'bucket/~': [self.row()]})
        record = out['records'][0]
        corpus = Corpus(self.manifest, self.pin, self.originals)
        for key in module.SOURCE_METADATA:
            binding = record['bindings'][key]
            self.assertEqual(binding['source_ref']['pointer'], '/bucket~1~0/0/source/' + key)
            self.assertEqual(corpus.resolve(binding['source_ref']), record['fields'][key])
            self.assertEqual(binding['transform'], 'IDENTITY')
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'], 41)
        used = out['eligible_cohort']['result']['individual_targets_used'][0]
        self.assertEqual(used['source']['path'], 'record.json')
        self.assertEqual(used['source']['sha256'], hashlib.sha256((self.originals / 'record.json').read_bytes()).hexdigest())
        self.assertFalse(out['source_authenticity_verified'])

    def test_mixed_direct_nested_and_identical_duplicates(self):
        row = self.row()
        row['published_at'] = row['source'].pop('published_at')
        row['url'] = row['source']['url']
        out = self.analyze(row)
        bindings = out['records'][0]['bindings']
        self.assertEqual(bindings['published_at']['source_ref']['pointer'], '/published_at')
        self.assertEqual(bindings['observed_at']['source_ref']['pointer'], '/source/observed_at')
        self.assertEqual(bindings['url']['source_ref']['pointer'], '/url')
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'], 41)

    def test_direct_nested_conflicts_reject_record(self):
        for key, value in (('published_at', '2032-04-05T11:00:00Z'),
                           ('observed_at', '2032-04-05T12:00:00Z'),
                           ('url', 'https://other.test/report')):
            with self.subTest(key=key):
                row = self.row(**{key: value})
                out = self.analyze(row)
                self.assertEqual(out['records'], [])
                self.assertIn('CONFLICTING_SOURCE_METADATA:' + key,
                              [gap['reason'] for gap in out['coverage']['unresolved_candidates']])
                self.assert_unavailable(out)

    def test_null_conflict_is_not_backfilled(self):
        for key in module.SOURCE_METADATA:
            with self.subTest(key=key):
                for direct_null in (True, False):
                    row = self.row()
                    row[key] = None if direct_null else row['source'][key]
                    if not direct_null:
                        row['source'][key] = None
                    out = self.analyze(row)
                    self.assertEqual(out['records'], [])
                    self.assert_unavailable(out)

    def test_missing_or_null_metadata_stays_partial(self):
        for key in module.SOURCE_METADATA:
            for null in (False, True):
                with self.subTest(key=key, null=null):
                    row = self.row()
                    if null:
                        row['source'][key] = None
                    else:
                        del row['source'][key]
                    out = self.analyze(row)
                    self.assertIn(key, out['records'][0]['missing_fields'])
                    self.assert_unavailable(out)

    def test_invalid_metadata_types_are_unresolved(self):
        for key in module.SOURCE_METADATA:
            for value in ([], {}, True, 7):
                with self.subTest(key=key, value=value):
                    row = self.row()
                    row['source'][key] = value
                    out = self.analyze(row)
                    self.assertEqual(out['records'], [])
                    self.assert_unavailable(out)

    def test_non_object_source_is_unresolved(self):
        for value in (None, [], 'metadata', 1):
            with self.subTest(value=value):
                out = self.analyze(self.row(source=value))
                self.assertEqual(out['records'], [])
                self.assertIn('SOURCE_METADATA_OBJECT_REQUIRED',
                              [gap['reason'] for gap in out['coverage']['unresolved_candidates']])

    def test_invalid_clock_and_url_guards(self):
        for key, value in (('published_at', 'unknown'), ('observed_at', ''),
                           ('published_at', '2032-04-04T11:00:00'),
                           ('observed_at', '2032-04-04'),
                           ('url', 'http://example.test/report'), ('url', '')):
            with self.subTest(key=key, value=value):
                row = self.row()
                row['source'][key] = value
                out = self.analyze(row)
                self.assert_unavailable(out)
                self.assertTrue(out['eligible_cohort']['result']['excluded'])

    def test_future_publication_and_observation_stay_excluded(self):
        for key in ('published_at', 'observed_at'):
            with self.subTest(key=key):
                row = self.row()
                row['source'][key] = '2032-04-21T12:00:00Z'
                out = self.analyze(row)
                self.assert_unavailable(out)
                self.assertEqual(len(out['observed_latest']['excluded_future_record_ids']), 1)

    def test_invalid_chronology_stays_excluded(self):
        for key, value, reason in (
                ('observed_at', '2032-04-04T10:30:00Z', 'Evidence observed before its publication'),
                ('published_at', '2032-04-04T09:00:00Z', 'TARGET_ISSUED_AFTER_SOURCE_PUBLICATION')):
            with self.subTest(key=key):
                row = self.row()
                row['source'][key] = value
                out = self.analyze(row)
                self.assert_unavailable(out)
                self.assertIn(reason, [item['reason'] for item in out['eligible_cohort']['result']['excluded']])

    def test_ancestor_and_sibling_metadata_not_borrowed(self):
        row = self.row()
        metadata = row.pop('source')
        document = {**metadata, 'source': metadata, 'records': [row, {'source': metadata}]}
        out = self.analyze(document)
        for key in module.SOURCE_METADATA:
            self.assertIsNone(out['records'][0]['fields'][key])
        self.assert_unavailable(out)

    def test_other_roles_not_inherited_from_source(self):
        for key in ('firm_id', 'analyst_id', 'issuer', 'issued_at', 'access',
                    'currency', 'price_basis', 'target_horizon'):
            with self.subTest(key=key):
                row = self.row()
                row['source'][key] = row.pop(key)
                out = self.analyze(row)
                self.assertIsNone(out['records'][0]['fields'][key])
                self.assert_unavailable(out)

    def test_deeper_metadata_not_borrowed(self):
        row = self.row()
        row['source'] = {'metadata': row['source']}
        self.assert_unavailable(self.analyze(row))

    def test_reference_path_is_not_followed(self):
        # Extraction binds declarations in retained JSON. It never reads this
        # claimed publisher reference or represents its bytes as authenticated.
        row = self.row()
        row['source'].update(path='../nonexistent.txt', sha256='0' * 64,
                             verbatim_excerpt='Unverified external declaration')
        out = self.analyze(row)
        used = out['eligible_cohort']['result']['individual_targets_used'][0]
        self.assertEqual(used['source']['path'], 'record.json')
        self.assertFalse(out['source_authenticity_verified'])

    def test_source_tampering_blocks_analysis(self):
        self.prepare(self.row())
        (self.originals / 'record.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            module.analyze(self.request, self.manifest, self.pin, self.originals)

    def test_native_compositor_renders_filtered_cohort_and_replays(self):
        older = self.row(target=39, issued_at='2032-04-01T10:00:00Z')
        older['source'].update(published_at='2032-04-01T11:00:00Z', observed_at='2032-04-01T12:00:00Z')
        rows = [older, self.row(), self.row(firm_id='Reed', analyst_id='ResearcherR', target=53),
                self.row(firm_id='Ash', analyst_id='ResearcherA', target=77, access='ATTRIBUTED_EXCERPT'),
                self.row(firm_id='OtherHorizon', target=91, target_horizon='forward_52_weeks'),
                self.row(firm_id='OtherCurrency', target=92, currency='USD'),
                self.row(firm_id='Snippet', target=93, access='SNIPPET'),
                self.row(firm_id='Stale', target=82, issued_at='2031-11-01T10:00:00Z')]
        raw = self.prepare({'individual_targets': rows})
        plan = self.root / 'plan.json'
        plan.write_text(json.dumps({'sections': [{'kind': 'source_report',
            'producer': 'analyst_sources', 'request': self.request}]}), encoding='utf-8')
        output = self.root / 'report'
        receipt = final_report.compose(plan, output, self.manifest, self.pin, self.originals)
        result = json.loads((output / 'sections/000/producer/result.json').read_bytes())
        consensus = result['eligible_cohort']['result']['consensus']
        for key, expected in {'independent_firms': 3, 'mean': 57, 'median': 53,
                              'minimum': 41, 'maximum': 77, 'q1': 47, 'q3': 65}.items():
            self.assertEqual(consensus[key], expected)
        self.assertEqual(consensus['iqr_over_median'], 18 / 53)
        self.assertEqual({r['firm_id'] for r in result['eligible_cohort']['result']['individual_targets_used']},
                         {'Quill', 'Reed', 'Ash'})
        text = (output / 'first-response.md').read_text(encoding='utf-8')
        self.assertIn('"mean": 57', text)
        self.assertIn('"q1": 47', text)
        self.assertIn('"q3": 65', text)
        self.assertIn('REPORT_NOT_ACCESSED', text)
        self.assertIn('STALE_TARGET', text)
        self.assertFalse(receipt['whole_report_semantic_pass'])
        self.assertEqual((output / 'originals/record.json').read_bytes(), raw)
        self.assertEqual(final_report.verify(output)['final_response_sha256'], receipt['final_response_sha256'])


if __name__ == '__main__':
    unittest.main()
