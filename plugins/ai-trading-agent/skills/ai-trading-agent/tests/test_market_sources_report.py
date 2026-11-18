"""Synthetic original-job adapter and canonical delivery counterexamples."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import final_report
import market_sources
import market_sources_report as module
from test_market_sources import SOURCE, NOW


class MarketSourcesReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='market-sources-report-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.jobs = [{'adapter': 'finra_short_interest_csv', 'source': deepcopy(SOURCE),
                      'text_file': 'raw/positions.csv', 'id_prefix': 'synthetic-position'}]
        self.raw = b'Settlement Date,Symbol,Current Short,Average Daily Volume,Days to Cover\n20261030,TEST,1725,300,5.75\n'
        self.request = {'jobs_ref': {'source_id': 'jobs', 'pointer': '/jobs'},
                        'as_of_ref': {'source_id': 'clock', 'pointer': '/cutoff'}}
        self.clock = NOW
        self.context = {}
        self.write_sources()

    def write_sources(self):
        files = [('jobs', 'retained/jobs.json', 'json', json.dumps({'jobs': self.jobs}).encode()),
                 ('clock', 'clock.json', 'json', json.dumps({'cutoff': self.clock, **self.context}).encode()),
                 ('raw', 'retained/raw/positions.csv', 'text', self.raw),
                 ('unused', 'unselected.txt', 'text', b'Original scope remains retained.')]
        sources = []
        for sid, name, fmt, raw in files:
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            sources.append({'id': sid, 'path': name, 'format': fmt, 'sha256': hashlib.sha256(raw).hexdigest()})
        self.manifest = self.root / 'ingress.json'
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': sources}))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def analyze(self):
        return module.analyze(self.request, self.manifest, self.pin, self.root)

    def test_original_envelope_direct_native_equivalence_and_no_mutation(self):
        before = (self.root / 'retained/jobs.json').read_bytes()
        result = self.analyze(); row = result['rows'][0]
        native = deepcopy(self.jobs[0]); native.update(schema_version=1, as_of=NOW, text=self.raw.decode())
        native['source'].update(raw_sha256=hashlib.sha256(self.raw).hexdigest(),
                                decoded_content_sha256=hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(row['result'], market_sources.parse(native))
        record = row['result']['records'][0]
        self.assertTrue(record['eligible']); self.assertEqual(record['payload']['reported_days_to_cover'], 5.75)
        self.assertIsNone(record['source']['published_at'])
        self.assertEqual(record['available_at'], SOURCE['retrieved_at'])
        self.assertEqual(before, (self.root / 'retained/jobs.json').read_bytes())
        self.assertNotIn('schema_version', row['original_job'])
        self.assertFalse(result['whole_report_semantic_pass'])
        self.assertEqual(len(result['source_inventory']), 4)

    def test_every_job_retained_with_failure_then_native_rejected_alias_row(self):
        bad = deepcopy(self.jobs[0]); bad['adapter'] = 'unsupported'
        self.jobs.insert(0, bad)
        self.raw = b'Settlement Date,Symbol,Current Short,Short Interest\n20261030,TEST,1725,1800\n'
        self.write_sources(); result = self.analyze()
        self.assertEqual(result['original_job_count'], 2)
        self.assertEqual(result['failed_operations'], 1)
        self.assertEqual(result['rows'][0]['status'], 'FAILED')
        row = result['rows'][1]; self.assertEqual(row['status'], 'EXECUTED')
        self.assertEqual(row['returned_rows_with_parse_errors'], 1)
        record = row['result']['records'][0]
        self.assertFalse(record['eligible']); self.assertIn('Conflicting source field aliases', record['parse_error'])
        self.assertEqual(record['payload']['raw_fields']['Current Short'], '1725')
        self.assertIn('parse_error', result['report']['text'])

    def test_missing_clock_is_retained_failure_not_invented(self):
        self.request.pop('as_of_ref')
        row = self.analyze()['rows'][0]
        self.assertEqual(row['error']['message'], 'ORIGINAL_AS_OF_REFERENCE_REQUIRED')
        self.assertNotIn('result', row)

    def test_original_clock_used_and_conflicting_or_date_only_clocks_rejected(self):
        self.jobs[0]['as_of'] = NOW; self.jobs[0]['schema_version'] = 1
        self.write_sources(); self.request.pop('as_of_ref')
        self.assertEqual(self.analyze()['rows'][0]['status'], 'EXECUTED')
        self.request['as_of_ref'] = {'source_id': 'clock', 'pointer': '/cutoff'}
        self.clock = '2026-11-12T21:00:00Z'; self.write_sources()
        self.assertEqual(self.analyze()['rows'][0]['error']['message'], 'CONFLICTING_ORIGINAL_AS_OF_REFERENCES')
        self.clock = '2026-11-11'; self.write_sources()
        with self.assertRaisesRegex(ValueError, 'EXACT_ORIGINAL_AS_OF_REQUIRED'): self.analyze()

    def test_source_config_conflicts_cannot_be_silently_overridden(self):
        for key, value in [('text', 'different'), ('schema_version', 2), ('schema_version', True),
                           ('source', {'raw_sha256': '0' * 64}), ('text_file', '../escape.csv'),
                           ('text_file', 'raw/missing.csv')]:
            old = deepcopy(self.jobs)
            self.jobs[0][key] = value; self.write_sources()
            with self.subTest(key=key, value=value):
                self.assertEqual(self.analyze()['rows'][0]['status'], 'FAILED')
            self.jobs = old

    def test_subset_and_literal_overrides_unknown_sources_and_wrong_root_rejected(self):
        for change in ({'jobs': []}, {'as_of': NOW}, {'job_indexes': [0]}, {'raw_files': {}}):
            request = {**self.request, **change}
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.analyze(request, self.manifest, self.pin, self.root)
        self.request['jobs_ref']['source_id'] = 'absent'
        with self.assertRaises(ValueError): self.analyze()
        self.request['jobs_ref']['source_id'] = 'jobs'
        other = self.root / 'empty'; other.mkdir()
        with self.assertRaises(FileNotFoundError): module.analyze(self.request, self.manifest, self.pin, other)

    def test_all_original_bytes_and_manifest_pinned(self):
        (self.root / 'unselected.txt').write_text('altered')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.analyze()
        self.write_sources()
        (self.root / 'retained/raw/positions.csv').write_bytes(self.raw + b'changed')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.analyze()
        self.write_sources()
        with self.assertRaisesRegex(ValueError, 'MANIFEST_HASH_MISMATCH'):
            module.analyze(self.request, self.manifest, '0' * 64, self.root)

    def test_duplicate_raw_alias_paths_rejected(self):
        manifest = json.loads(self.manifest.read_bytes())
        duplicate = deepcopy(manifest['sources'][2]); duplicate['id'] = 'alias'
        manifest['sources'].append(duplicate); self.manifest.write_text(json.dumps(manifest))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        with self.assertRaises(ValueError): self.analyze()

    def test_json_adapter_matches_native_decoding_and_preserves_data_conflict(self):
        data = {'cik': '0000000002', 'tickers': ['TEST'], 'filings': {'recent': {
            'accessionNumber': ['0000000002-26-000001'], 'form': ['13F-HR'],
            'filingDate': ['2026-10-01'], 'reportDate': ['2026-09-30'],
            'acceptanceDateTime': ['2026-10-01T12:00:00Z'], 'primaryDocument': ['main.xml']}}}
        self.raw = json.dumps(data).encode(); self.jobs[0]['adapter'] = 'sec_submissions'; self.write_sources()
        row = self.analyze()['rows'][0]
        self.assertEqual(row['status'], 'EXECUTED'); self.assertEqual(len(row['result']['records']), 1)
        self.jobs[0]['data'] = {}; self.write_sources()
        self.assertEqual(self.analyze()['rows'][0]['error']['message'], 'ORIGINAL_DATA_CONFLICTS_WITH_RAW_SOURCE')

    def test_portable_canonical_projection_and_text_json_tamper_rejected(self):
        from test_source_metadata_fitness import historical
        self.context = {'arbitrary_archive': historical()}; self.write_sources()
        from test_market_flow import pressure_document
        from test_institutional_research import fixture
        manifest = json.loads(self.manifest.read_bytes())
        for sid, document in [('flow', pressure_document()), ('brief', fixture())]:
            raw = json.dumps(document).encode(); name = sid + '.json'; (self.root / name).write_bytes(raw)
            manifest['sources'].append({'id': sid, 'path': name, 'format': 'json',
                                        'sha256': hashlib.sha256(raw).hexdigest()})
        self.manifest.write_text(json.dumps(manifest)); self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        plan = self.root / 'plan.json'
        plan.write_text(json.dumps({'output_contract': final_report.STRICT, 'sections': [
            {'kind': 'source_report', 'producer': 'market_sources_report', 'request': self.request},
            {'kind': 'source_report', 'producer': 'market_flow_report', 'request': {
                'documents': [{'id': 'flow', 'source_ref': {'source_id': 'flow', 'pointer': ''}}],
                'operations': ['flow', 'positioning', 'squeeze']}},
            {'kind': 'source_report', 'producer': 'institutional_report', 'request': {
                'documents': [{'id': 'brief', 'source_ref': {'source_id': 'brief', 'pointer': ''}}],
                'operations': ['brief']}}]}))
        report = self.root / 'report'
        final_report.compose(plan, report, self.manifest, self.pin, self.root)
        metadata = self.root / 'metadata.json'; metadata.write_text(json.dumps({'case_id': 'synthetic-parser',
            'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'}}))
        export = self.root / 'export'; final_report.export_response(report, metadata, export)
        moved = self.root / 'moved'; shutil.copytree(export, moved)
        final_report.verify_response(moved)
        response = json.loads((export / 'response.json').read_bytes())
        self.assertEqual(len(response['rows']), 3)
        fitness = response['rows'][0]['result']['metadata_fitness']
        self.assertEqual(fitness['descriptors'][0]['fields']['row_first_available_at']['state'], 'NULL')
        self.assertIn('HISTORICAL_UNIVERSE_SUPPORT_NOT_ESTABLISHED', (report / 'first-response.md').read_text())
        self.assertEqual(fitness['source_binding']['clock_pointer'], '/cutoff')
        self.assertEqual(set(response['rows'][1]['result']['rows'][0]['operations']), {'flow', 'positioning', 'squeeze'})
        self.assertEqual(response['rows'][2]['result']['rows'][0]['operations']['brief']['status'], 'EXECUTED')
        row = response['rows'][0]['result']['rows'][0]
        self.assertEqual(row['result']['records'][0]['payload']['reported_days_to_cover'], 5.75)
        row['result']['records'][0]['eligible'] = False
        published = self.root / 'changed.json'; published.write_text(json.dumps(response))
        with self.assertRaises(ValueError): final_report.verify_response(export, published)
        text = self.root / 'changed.md'
        text.write_bytes((report / 'first-response.md').read_bytes() + b'\nAll source facts independently verified.\n')
        with self.assertRaises(ValueError): final_report.verify(report, text)

    def test_automatic_context_analysis_preserves_native_rows_and_source_hashes(self):
        from test_source_metadata_fitness import historical
        before = self.analyze()
        self.assertEqual(before['metadata_fitness']['status'], 'NO_SUPPORTED_DESCRIPTOR')
        self.context = {'renamed_context': {'nested': historical()}}; self.write_sources()
        after = self.analyze()
        self.assertEqual(before['rows'][0]['result'], after['rows'][0]['result'])
        self.assertEqual(before['rows'][0]['native_input_sha256'], after['rows'][0]['native_input_sha256'])
        self.assertEqual(set(self.request), {'jobs_ref', 'as_of_ref'})
        fitness = after['metadata_fitness']
        self.assertEqual(fitness['descriptors'][0]['source_ref']['pointer'], '/renamed_context/nested')
        self.assertIn('NO_LOOKAHEAD_SUPPORT_NOT_ESTABLISHED', after['report']['text'])
        (self.root / 'clock.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.analyze()


if __name__ == '__main__':
    unittest.main()
