import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_sources as module


class AnalystSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.request = {'as_of': '2026-04-20T12:00:00Z',
                        'cohort': {'issuer': 'SYN', 'currency': 'USD',
                                   'price_basis': 'common_share_unadjusted',
                                   'target_horizon': 'forward_12_months'},
                        'extraction_profile': {'formats': ['json_records', 'labelled_sentences']}}

    def tearDown(self):
        self.temp.cleanup()

    def row(self, **changes):
        return {'firm_id': 'Quill', 'analyst_id': 'AnalystQ', 'issuer': 'SYN',
                'currency': 'USD', 'target': 63.5, 'issued_at': '2026-04-02T10:00:00Z',
                'published_at': '2026-04-02T11:00:00Z', 'observed_at': '2026-04-02T12:00:00Z',
                'url': 'https://example.test/research', 'price_basis': 'common_share_unadjusted',
                'target_horizon': 'forward_12_months', 'access': 'FULL_REPORT', **changes}

    def run_sources(self, sources, request=None):
        entries = []
        for i, (name, value, fmt) in enumerate(sources):
            raw = value if isinstance(value, bytes) else (json.dumps(value).encode() if fmt == 'json'
                                                        else value.encode())
            (self.root / name).write_bytes(raw)
            entries.append({'id': 'source' + str(i), 'path': name,
                            'sha256': hashlib.sha256(raw).hexdigest(), 'format': fmt})
        manifest = self.root / 'manifest.json'
        manifest.write_text(json.dumps({'schema_version': 1, 'sources': entries}))
        pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
        return module.analyze(request or self.request, manifest, pin, self.root)

    def test_real_producer_to_eligible_helper(self):
        out = self.run_sources([('document.json', self.row(), 'json')])
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'], 63.5)
        self.assertEqual(out['records'][0]['bindings']['target']['source_ref']['pointer'], '/target')
        self.assertFalse(out['source_authenticity_verified'])

    def test_supplemental_revision_not_filename_selected(self):
        newer = self.row(target=71, issued_at='2026-04-09T10:00:00Z',
                         published_at='2026-04-09T11:00:00Z', observed_at='2026-04-09T12:00:00Z')
        out = self.run_sources([('main.json', self.row(), 'json'), ('misc.json', newer, 'json')])
        self.assertEqual(out['observed_latest']['by_firm'][0]['selected_records'][0]['fields']['target'], 71)
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'], 71)

    def test_unknown_horizon_not_inherited_from_request(self):
        newer = self.row(target=71, issued_at='2026-04-09T10:00:00Z', target_horizon=None)
        out = self.run_sources([('main.json', self.row(), 'json'), ('misc.json', newer, 'json')])
        self.assertEqual(out['observed_latest']['by_firm'][0]['selected_records'][0]['fields']['target'], 71)
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'], 63.5)
        self.assertIsNone(out['records'][1]['fields']['target_horizon'])
        self.assertIn('Older eligible rows', out['limits'][2])

    def test_no_literal_targets(self):
        request = {**self.request, 'individual_targets': [self.row(firm_id='Fabricated')]}
        with self.assertRaisesRegex(ValueError, 'NO_LITERAL_TARGETS'):
            self.run_sources([('main.json', self.row(), 'json')], request)

    def test_no_literal_profile_overrides(self):
        request = copy.deepcopy(self.request)
        request['extraction_profile']['defaults'] = {'target_horizon': 'forward_12_months'}
        with self.assertRaisesRegex(ValueError, 'SUPPORTED_PROFILE'):
            self.run_sources([('main.json', self.row(), 'json')], request)

    def test_partial_revision_preserved_without_year_inference(self):
        text = 'Quill initiated new coverage April 9: FY2030 adjusted EPS USD 3.70; target USD 71.'
        out = self.run_sources([('note.txt', text, 'text')])
        self.assertEqual(out['records'][0]['fields']['target'], 71)
        self.assertIsNone(out['records'][0]['fields']['issued_at'])
        self.assertEqual(out['records'][0]['uninterpreted_fields']['issue_date_text']['value'], 'April 9')
        self.assertIn('FY2030 adjusted EPS USD 3.70', out['records'][0]['uninterpreted_fields']['context']['value'])
        self.assertIn('April 9', out['report']['text'])
        self.assertIn('"target": 71.0', out['report']['text'])
        self.assertIn('"firm_id": "Quill"', out['report']['text'])
        self.assertIn(text, out['report']['text'])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')
        self.assertEqual(out['eligible_cohort']['result']['consensus']['status'], 'UNAVAILABLE')

    def test_labelled_sentence_missing_clocks_not_invented(self):
        text = ('Firm Quill, analyst Ava, issued 2026-04-02T10:00:00Z: SYN target USD 63.5 '
                'per common share; horizon forward_12_months; access FULL_REPORT. No split adjustment.')
        out = self.run_sources([('note.txt', text, 'text')])
        self.assertEqual(out['records'][0]['fields']['target'], 63.5)
        self.assertIsNone(out['records'][0]['fields']['published_at'])
        self.assertEqual(out['eligible_cohort']['result']['consensus']['status'], 'UNAVAILABLE')
        for binding in out['records'][0]['bindings'].values():
            ref = binding['source_ref']
            self.assertEqual(text[ref['start']:ref['end']], ref['excerpt'])

    def test_provider_constituents_not_invented(self):
        out = self.run_sources([('pool.txt', 'Provider Orion consensus target 70 from three firms.', 'text')])
        self.assertEqual(out['records'], [])
        self.assertEqual(len(out['coverage']['unresolved_candidates']), 1)

    def test_unknown_json_target_text_is_gap(self):
        out = self.run_sources([('doc.json', {'body': 'Target USD 91 from unnamed firm'}, 'json')])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')

    def test_binary_source_is_gap(self):
        out = self.run_sources([('blob.bin', b'opaque', 'bytes')])
        self.assertEqual(out['coverage']['unsupported_sources'], ['source0'])

    def test_no_match_does_not_prove_absence(self):
        out = self.run_sources([('doc.txt', 'unrelated inventory', 'text')])
        self.assertFalse(out['coverage']['semantic_completeness_verified'])
        self.assertFalse(out['coverage']['source_absence_established'])

    def test_same_time_conflict(self):
        out = self.run_sources([('doc.json', [self.row(), self.row(target=82)], 'json')])
        self.assertEqual(out['observed_latest']['by_firm'][0]['status'], 'CONFLICTING_LATEST')
        self.assertEqual(out['eligible_cohort']['result']['consensus']['status'], 'UNAVAILABLE')

    def test_distinct_horizons(self):
        out = self.run_sources([('doc.json', [self.row(), self.row(firm_id='Other', target=82,
                               target_horizon='forward_52_weeks')], 'json')])
        self.assertEqual(out['eligible_cohort']['result']['consensus']['independent_firms'], 1)

    def test_cross_record_metadata_not_borrowed(self):
        out = self.run_sources([('doc.json', {'issuer': 'SYN', 'items': [{'firm_id': 'Quill', 'target': 63}]}, 'json')])
        self.assertIsNone(out['records'][0]['fields']['issuer'])

    def test_adjacent_amount_not_target(self):
        out = self.run_sources([('doc.json', {**self.row(), 'revenue': 6350}, 'json')])
        self.assertEqual(out['records'][0]['fields']['target'], 63.5)

    def test_invalid_roles_stay_gap(self):
        out = self.run_sources([('doc.json', self.row(firm_id=42), 'json')])
        self.assertEqual(out['records'], [])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')

    def test_null_target_does_not_sort_or_compute(self):
        out = self.run_sources([('doc.json', self.row(target=None), 'json')])
        self.assertEqual(out['observed_latest']['by_firm'], [])

    def test_exact_replay_and_report_hash(self):
        first = self.run_sources([('doc.json', self.row(), 'json')])
        second = self.run_sources([('doc.json', self.row(), 'json')])
        self.assertEqual(first, second)
        self.assertEqual(first['report']['sha256'], hashlib.sha256(first['report']['text'].encode()).hexdigest())
        self.assertFalse(first['report']['whole_report_semantic_pass'])

    def test_source_tamper(self):
        self.run_sources([('doc.json', self.row(), 'json')])
        manifest = self.root / 'manifest.json'
        pin = hashlib.sha256(manifest.read_bytes()).hexdigest()
        (self.root / 'doc.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            module.analyze(self.request, manifest, pin, self.root)

    def test_wrong_manifest_pin(self):
        self.run_sources([('doc.json', self.row(), 'json')])
        with self.assertRaisesRegex(ValueError, 'MANIFEST_HASH_MISMATCH'):
            module.analyze(self.request, self.root / 'manifest.json', '0' * 64, self.root)

    def test_future_issue_not_latest(self):
        out = self.run_sources([('doc.json', self.row(issued_at='2027-01-01T10:00:00Z'), 'json')])
        self.assertEqual(out['observed_latest']['by_firm'], [])
        self.assertEqual(len(out['observed_latest']['excluded_future_record_ids']), 1)
        self.assertEqual(out['observed_latest']['unresolved_record_ids'], [])
        self.assertEqual(out['eligible_cohort']['result']['consensus']['status'], 'UNAVAILABLE')

    def test_other_issuer_does_not_displace_requested_issuer(self):
        other = self.row(issuer='OTHER', target=104, issued_at='2026-04-09T10:00:00Z')
        out = self.run_sources([('record.json', [self.row(), other], 'json')])
        latest = out['observed_latest']
        self.assertEqual(latest['by_firm'][0]['selected_records'][0]['fields']['target'], 63.5)
        self.assertEqual(len(latest['excluded_other_issuer_record_ids']), 1)

    def test_mixed_latest_horizon_preserved_in_report(self):
        other = self.row(target=104, target_horizon='forward_52_weeks')
        out = self.run_sources([('record.json', [self.row(), other], 'json')])
        latest = out['observed_latest']['by_firm'][0]
        self.assertEqual(latest['status'], 'MIXED_LATEST_DIMENSIONS')
        self.assertEqual(len(latest['selected_records']), 2)
        self.assertIn('forward_52_weeks', out['report']['text'])
        self.assertIn('common_share_unadjusted', out['report']['text'])
        self.assertIn('USD', out['report']['text'])

    def test_unknown_issuer_not_filled_from_request(self):
        out = self.run_sources([('record.json', self.row(issuer=None), 'json')])
        self.assertEqual(out['observed_latest']['by_firm'], [])
        self.assertEqual(len(out['observed_latest']['unresolved_record_ids']), 1)

    def test_known_future_publication_excluded(self):
        out = self.run_sources([('record.json', self.row(published_at='2027-01-01T10:00:00Z'), 'json')])
        self.assertEqual(out['observed_latest']['by_firm'], [])
        self.assertEqual(len(out['observed_latest']['excluded_future_record_ids']), 1)

    def test_partial_record_visible_in_generated_report(self):
        out = self.run_sources([('record.json', self.row(issued_at=None), 'json')])
        self.assertIn('"target": 63.5', out['report']['text'])
        self.assertIn('"issued_at": null', out['report']['text'])

    def test_provider_json_pool_is_unresolved(self):
        out = self.run_sources([('record.json', {'provider_consensus': {'mean': 71, 'count': 3}}, 'json')])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')
        self.assertEqual(out['records'], [])

    def test_extra_target_narrative_in_supported_object_is_gap(self):
        out = self.run_sources([('record.json', {**self.row(), 'note': 'Other firm target 81'}, 'json')])
        self.assertEqual(len(out['records']), 1)
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')

    def test_generic_labelled_record_full_producer(self):
        request = copy.deepcopy(self.request)
        request['extraction_profile']['formats'].append('labelled_records')
        text = '; '.join(key + ': ' + str(value) for key, value in self.row().items())
        out = self.run_sources([('record.txt', text, 'text')], request)
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'], 63.5)
        for binding in out['records'][0]['bindings'].values():
            ref = binding['source_ref']
            self.assertEqual(text[ref['start']:ref['end']], ref['excerpt'])

    def test_duplicate_text_role_blocked(self):
        request = copy.deepcopy(self.request)
        request['extraction_profile']['formats'].append('labelled_records')
        out = self.run_sources([('record.txt', 'firm_id: Quill; target: 63; target: 81', 'text')], request)
        self.assertEqual(out['records'], [])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')

    def test_array_prose_retained_as_gap(self):
        out = self.run_sources([('record.json', ['The new target is USD 81'], 'json')])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')

    def test_same_values_wrong_roles_not_promoted(self):
        out = self.run_sources([('record.json', {'firm_id': 'Quill', 'revenue': 63.5,
                               'target_note': 'unknown'}, 'json')])
        self.assertEqual(out['records'], [])
        self.assertEqual(out['coverage']['status'], 'INCOMPLETE')

    def test_no_numeric_precision_loss(self):
        raw = json.dumps(self.row()).replace('63.5', '63.123456789012345678901').encode()
        out = self.run_sources([('record.json', raw, 'json')])
        self.assertEqual(out['records'], [])
        self.assertIn('PRECISION_UNSUPPORTED', out['coverage']['unresolved_candidates'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
