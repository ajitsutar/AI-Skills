"""Synthetic numeric delivery and recognized-root coverage regressions."""
import copy
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_evidence
import analyst_sources
import final_report
import supplied_research
from source_claims import Corpus


class AnalystNumericBoundariesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='analyst-numeric-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.sources = self.root / 'sources'
        self.sources.mkdir()
        self.manifest = self.root / 'manifest.json'
        self.cohort = {'issuer': 'SYNTH', 'currency': 'EUR',
                       'price_basis': 'common_share_unadjusted',
                       'target_horizon': 'forward_12_months'}
        self.as_of = '2034-08-19T18:00:00Z'
        self.request = {'original_request_ref': {'source_id': 'original', 'pointer': ''},
                        'extraction_profile': {'formats': ['json_records']}}

    def metadata(self):
        return {'published_at': '2034-08-18T13:00:00Z',
                'observed_at': '2034-08-18T14:00:00Z',
                'url': 'https://example.test/synthetic/analyst'}

    def target(self, firm, value):
        return {**self.cohort, 'firm_id': firm, 'analyst_id': 'Author' + firm,
                'target': value, 'issued_at': '2034-08-17T12:00:00Z',
                'access': 'FULL_REPORT', 'source': self.metadata()}

    def pool(self, **changes):
        return {**self.cohort, 'provider': 'Atlas', 'upstream': 'DeclaredFeed',
                'as_of': '2034-08-18', 'target_count': 7, 'mean': 107.25,
                'source': self.metadata(), **changes}

    def document(self, values=(54, 86, 102, 158), pools=()):
        return {**self.cohort, 'as_of': self.as_of,
                'individual_targets': [self.target('Firm' + str(i), v) for i, v in enumerate(values)],
                'provider_consensus': list(pools)}

    def prepare(self, document, raw=None, extra=None):
        raw = raw if raw is not None else json.dumps(document, allow_nan=False).encode()
        originals = {'original': raw, **(extra or {})}
        entries = []
        for sid, body in originals.items():
            (self.sources / (sid + '.json')).write_bytes(body)
            entries.append({'id': sid, 'path': sid + '.json', 'format': 'json',
                            'sha256': hashlib.sha256(body).hexdigest()})
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': entries}), encoding='utf8')
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        return raw

    def analyze(self, document, **kwargs):
        self.prepare(document, **kwargs)
        return analyst_sources.analyze(self.request, self.manifest, self.pin, self.sources)

    def native(self, document):
        raw = self.prepare(document)
        request = copy.deepcopy(document)
        for key in ('individual_targets', 'provider_consensus'):
            for i, row in enumerate(request.get(key, [])):
                row['record_id'] = key + str(i)
                row['source'].update(path='original.json', sha256=hashlib.sha256(raw).hexdigest(),
                                     verbatim_excerpt=raw.decode(), locator='whole synthetic original')
        if request.get('quote'):
            request['quote']['source'].update(path='original.json', sha256=hashlib.sha256(raw).hexdigest(),
                                              verbatim_excerpt=raw.decode(), locator='whole synthetic original')
        return analyst_evidence.review(request, self.sources)

    def deliver(self, document):
        raw = self.prepare(document)
        request = self.root / 'request.json'
        request.write_text(json.dumps({'producer': 'analyst_sources', 'producer_request': self.request}), encoding='utf8')
        supplied_research.run(request, self.root / 'bundle', self.manifest, self.pin, self.sources)
        supplied_research.verify(self.root / 'bundle')
        plan = self.root / 'plan.json'
        plan.write_text(json.dumps({'output_contract': final_report.STRICT,
            'sections': [{'kind': 'source_report', 'producer': 'analyst_sources', 'request': self.request}]}), encoding='utf8')
        report = self.root / 'report'
        final_report.compose(plan, report, self.manifest, self.pin, self.sources)
        final_report.verify(report)
        self.assertEqual((report / 'originals/original.json').read_bytes(), raw)
        metadata = self.root / 'metadata.json'
        metadata.write_text(json.dumps({'case_id': 'synthetic-numeric-boundary',
            'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'}}), encoding='utf8')
        exported = self.root / 'export'
        final_report.export_response(report, metadata, exported)
        final_report.verify_response(exported)
        response = json.loads((exported / 'response.json').read_bytes())
        return response['rows'][0]['result'], report, exported

    def test_provider_decimal_fields_numeric_spelling_and_exact_source_bindings(self):
        for key, value in [('mean', 107.25), ('median', 105.5), ('minimum', 80.25),
                           ('maximum', 140.75), ('mean', 107), ('mean', 107.0), ('mean', 0.1)]:
            with self.subTest(key=key, value=repr(value)):
                pool = self.pool(); pool.pop('mean'); pool[key] = value
                output = self.analyze(self.document(pools=[pool]))
                retained = output['eligible_cohort']['result']['provider_consensus'][0]
                binding = retained['bindings'][key]
                self.assertEqual(binding['source_ref'], {'source_id': 'original', 'pointer': '/provider_consensus/0/' + key})
                original = Corpus(self.manifest, self.pin, self.sources).resolve(binding['source_ref'])
                self.assertEqual(Decimal(str(retained[key])), Decimal(str(original)))
                self.assertEqual(binding['transform'], 'IDENTITY' if type(value) is int else 'DECIMAL')
                self.assertEqual(retained['source']['sha256'], hashlib.sha256((self.sources / 'original.json').read_bytes()).hexdigest())
                self.assertFalse(retained['source_authenticity_verified'])

    def test_provider_invalid_types_counts_and_ranges_keep_valid_neighbor(self):
        cases = [{'mean': v} for v in (True, '107.25', None, 0, -1)]
        cases += [{key: v} for key in ('target_count', 'analyst_count') for v in (True, 7.0, 2.5, 0, -1)]
        cases += [{'minimum': 120.25, 'maximum': 100.5}, {'minimum': 110.5, 'maximum': 120.5}]
        for changes in cases:
            with self.subTest(changes=changes):
                output = self.analyze(self.document(pools=[self.pool(provider='Good'), self.pool(provider='Bad', **changes)]))
                self.assertEqual([p['provider'] for p in output['eligible_cohort']['result']['provider_consensus']], ['Good'])
                self.assertEqual(output['eligible_cohort']['result']['consensus']['mean'], 100)
                gaps = output['coverage']['unresolved_candidates']
                self.assertEqual([g['source_ref']['pointer'] for g in gaps], ['/provider_consensus/1'])

    def test_provider_unsupported_decimal_precision_and_range_remain_explicit_gaps(self):
        document = self.document(pools=[self.pool()])
        for token in ('107.1234567890123456789', '1e309', '1e-400'):
            with self.subTest(token=token):
                raw = json.dumps(document).replace('107.25', token).encode()
                output = self.analyze(document, raw=raw)
                self.assertEqual(output['eligible_cohort']['result']['provider_consensus'], [])
                self.assertEqual(output['coverage']['unresolved_candidates'][0]['reason'], 'ANALYST_NUMBER_PRECISION_UNSUPPORTED')

    def test_nonfinite_json_provider_tokens_fail_closed(self):
        document = self.document(pools=[self.pool()])
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(token=token):
                raw = json.dumps(document).replace('107.25', token).encode()
                with self.assertRaises(ValueError):
                    self.analyze(document, raw=raw)
                self.assertFalse((self.root / 'export').exists())

    def test_decimal_provider_pools_survive_native_report_export_and_tamper_checks(self):
        document = self.document(pools=[self.pool(median=105.5, minimum=80.25, maximum=140.75),
                                       self.pool(provider='Beacon', mean=121.5, target_count=9)])
        native = self.native(document)
        output, report, exported = self.deliver(document)
        eligible = output['eligible_cohort']['result']
        self.assertEqual(eligible['consensus']['mean'], native['consensus']['mean'])
        self.assertEqual([p['mean'] for p in eligible['provider_consensus']], [107.25, 121.5])
        self.assertTrue(all(p['status'] == 'PROVIDER_REPORTED_NOT_COMBINED' for p in eligible['provider_consensus']))
        self.assertIn('107.25', (report / 'first-response.md').read_text(encoding='utf8'))
        response_path = exported / 'response.json'; original_response = response_path.read_bytes()
        response_path.write_bytes(original_response.replace(b'107.25', b'107.26'))
        with self.assertRaises(ValueError): final_report.verify_response(exported)
        response_path.write_bytes(original_response)
        original_path = report / 'originals/original.json'; original_path.write_bytes(original_path.read_bytes().replace(b'107.25', b'107.26'))
        with self.assertRaises(ValueError): final_report.verify(report)

    def test_large_equal_median_is_finite_through_native_and_canonical_export(self):
        document = self.document(values=[1e308, 1e308])
        native = self.native(document)
        self.assertEqual(native['consensus']['median'], 1e308)
        output, _, _ = self.deliver(document)
        consensus = output['eligible_cohort']['result']['consensus']
        self.assertEqual(consensus['median'], 1e308)
        self.assertEqual(consensus['mean'], 1e308)
        self.assertEqual(consensus['iqr_over_median'], 0)
        self.assertTrue(all(math.isfinite(v) for v in consensus.values() if isinstance(v, (int, float))))

    def test_unrepresentable_derived_ratios_raise_supported_range_error(self):
        document = self.document(values=[5e-324, 5e-324, 1e308])
        with self.assertRaisesRegex(ValueError, '^ANALYST_STATISTIC_RANGE_UNSUPPORTED$'):
            self.native(document)
        with self.assertRaisesRegex(ValueError, '^ANALYST_STATISTIC_RANGE_UNSUPPORTED$'):
            self.analyze(document)
        document = self.document(values=[1e308])
        document['quote'] = {**self.cohort, 'price': 1e-300, 'source': self.metadata()}
        with self.assertRaisesRegex(ValueError, '^ANALYST_STATISTIC_RANGE_UNSUPPORTED$'):
            self.native(document)
        # The source cohort producer explicitly does not consume quote analytics.
        output = self.analyze(document)
        self.assertIn('quote', output['request_binding']['unconsumed_original_members'])
        self.assertNotIn('median_implied_price_change_pct', output['eligible_cohort']['result']['consensus'])

    def test_ordinary_statistics_and_tiny_positive_median_are_unchanged(self):
        result = self.native(self.document())['consensus']
        for key, value in {'mean': 100, 'median': 94, 'q1': 78, 'q3': 116,
                           'iqr': 38, 'range_width': 104, 'iqr_over_median': 38/94}.items():
            self.assertEqual(result[key], value, key)
        tiny = self.native(self.document(values=[5e-324, 5e-324]))['consensus']
        self.assertEqual(tiny['median'], 5e-324)
        self.assertEqual(tiny['iqr_over_median'], 0)

    def test_original_roles_are_recognized_without_completeness_claim(self):
        document = self.document(values=[100]); document['max_target_age_days'] = 45
        output = self.analyze(document)
        self.assertEqual(output['coverage']['status'], 'SUPPORTED_GRAMMARS_SCANNED')
        self.assertEqual(output['coverage']['unresolved_candidates'], [])
        self.assertFalse(output['coverage']['semantic_completeness_verified'])
        self.assertFalse(output['coverage']['source_absence_established'])
        for field in ('target_horizon', 'max_target_age_days'):
            self.assertEqual(output['request_binding']['fields'][field]['source_ref']['pointer'], '/' + field)
        self.assertEqual(output['eligible_cohort']['result']['consensus']['mean'], 100)

    def test_genuine_unknown_children_and_noncanonical_objects_remain_unresolved(self):
        document = self.document(values=[100])
        document['individual_targets'] += ['A target outside the supported grammar.', {'target': {'amount': 125}}]
        output = self.analyze(document)
        self.assertEqual({g['source_ref']['pointer'] for g in output['coverage']['unresolved_candidates']},
                         {'/individual_targets/1', '/individual_targets/2/target'})
        self.assertEqual(output['coverage']['status'], 'INCOMPLETE')
        unknown = json.dumps({'container': {'target_horizon': 'forward_12_months', 'target_notes': 'Target unknown'}}).encode()
        output = self.analyze(self.document(), extra={'unknown': unknown})
        self.assertEqual({g['source_ref']['pointer'] for g in output['coverage']['unresolved_candidates']},
                         {'/container/target_horizon', '/container/target_notes'})

    def test_selected_original_does_not_hide_other_original_children(self):
        neighbor = self.document(values=[])
        neighbor['individual_targets'] = ['Unparsed target from another supplied original.']
        output = self.analyze(self.document(), extra={'neighbor': json.dumps(neighbor).encode()})
        self.assertEqual(output['request_binding']['candidate_original_request_ids'], ['neighbor', 'original'])
        self.assertEqual(output['coverage']['all_source_ids'], ['neighbor', 'original'])
        self.assertEqual(output['coverage']['unresolved_candidates'], [{
            'source_ref': {'source_id': 'neighbor', 'pointer': '/individual_targets/0'},
            'reason': 'UNSUPPORTED_TARGET_JSON'}])
        self.assertEqual(output['eligible_cohort']['result']['consensus']['mean'], 100)


if __name__ == '__main__':
    unittest.main()
