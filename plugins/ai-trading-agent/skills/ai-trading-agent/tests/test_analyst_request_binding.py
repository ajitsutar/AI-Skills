"""Original-request authority, literal compatibility and native replay regressions."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import analyst_sources as analyst
import final_report as final
import supplied_research as bridge


class AnalystRequestBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='analyst-binding-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sources = self.root / 'sources'; self.sources.mkdir()
        self.manifest = self.root / 'ingress.json'
        self.dimensions = {'issuer': 'SYNB', 'currency': 'EUR', 'price_basis': 'class_b_unit_original',
                           'target_horizon': 'forward_12_months'}
        self.cutoff = '2034-05-20T12:00:00Z'
        self.profile = {'formats': ['json_records', 'labelled_sentences']}
        self.bound = {'original_request_ref': {'source_id': 'original', 'pointer': ''},
                      'extraction_profile': self.profile}
        self.literal = {'as_of': self.cutoff, 'cohort': self.dimensions,
                        'extraction_profile': self.profile}
        self.original = {**self.dimensions, 'as_of': self.cutoff,
                         'individual_targets': [self.row('North', 42), self.row('South', 54)],
                         'max_target_age_days': 60, 'max_quote_age_hours': 24,
                         'quote': {'issuer': 'SYNB', 'price': 40}, 'analyst_track_records': []}

    def row(self, firm, target, **changes):
        return {**self.dimensions, 'firm_id': firm, 'analyst_id': firm+'Analyst', 'target': target,
                'issued_at': '2034-04-15T10:00:00Z', 'access': 'FULL_REPORT',
                'source': {'published_at': '2034-04-15T11:00:00Z', 'observed_at': '2034-04-15T12:00:00Z',
                           'url': 'https://example.test/'+firm}, **changes}

    def prepare(self, documents=None):
        documents = documents if documents is not None else [('original', self.original, 'json')]
        rows = []
        for sid, value, fmt in documents:
            raw = value if isinstance(value, bytes) else json.dumps(value).encode() if fmt == 'json' else value.encode()
            name = sid+'.'+('json' if fmt == 'json' else 'txt')
            (self.sources/name).write_bytes(raw)
            rows.append({'id': sid, 'path': name, 'format': fmt, 'sha256': hashlib.sha256(raw).hexdigest()})
        self.manifest.write_bytes(bridge.encode({'schema_version': 1, 'sources': rows}))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def analyze(self, request=None):
        return analyst.analyze(self.bound if request is None else request, self.manifest, self.pin, self.sources)

    def compose(self, request=None, name='report'):
        plan = {'output_contract': final.STRICT, 'sections': [{'kind': 'source_report',
                'producer': 'analyst_sources', 'request': self.bound if request is None else request}]}
        path = self.root/(name+'-plan.json'); path.write_bytes(bridge.encode(plan))
        final.compose(path, self.root/name, self.manifest, self.pin, self.sources)
        return self.root/name

    def test_source_reference_derives_exact_cohort_policy_and_provenance(self):
        self.prepare(); out = self.analyze()
        stats = out['eligible_cohort']['result']['consensus']
        self.assertEqual((stats['independent_firms'], stats['mean'], stats['range_width'], stats['iqr']), (2, 48, 12, 6))
        bound = out['request_binding']
        self.assertEqual(bound['status'], 'SOURCE_REQUEST_BOUND')
        self.assertEqual(bound['effective_filters']['cohort'], self.dimensions)
        self.assertEqual(bound['effective_filters']['max_target_age_days'], 60)
        for key in (*analyst.DIMENSIONS, 'as_of', 'max_target_age_days', 'max_quote_age_hours'):
            row = bound['fields'][key]
            self.assertEqual(row['source_ref'], {'source_id': 'original', 'pointer': '/'+key})
            self.assertEqual(row['source_sha256'], hashlib.sha256((self.sources/'original.json').read_bytes()).hexdigest())
            self.assertEqual(row['source_value'], self.original[key])
        self.assertIn('quote', bound['unconsumed_original_members'])
        self.assertFalse(bound['fields']['max_quote_age_hours']['used_for_selection'])
        self.assertNotIn('quote_status', stats)

    def test_legacy_wrong_parser_label_rejects_instead_of_empty_success(self):
        self.prepare(); request = copy.deepcopy(self.literal)
        request['cohort']['price_basis'] = 'common_share_unadjusted'
        with self.assertRaisesRegex(ValueError, 'FILTER_MISMATCH:price_basis'):
            self.analyze(request)
        with self.assertRaisesRegex(ValueError, 'FILTER_MISMATCH:price_basis'):
            self.compose(request)
        self.assertTrue((self.root/'report/failure.json').is_file())
        self.assertFalse((self.root/'report/first-response.md').exists())

    def test_each_changed_filter_rejected(self):
        self.prepare()
        for key, value in [('issuer','OTHER'),('currency','GBP'),('target_horizon','forward_52_weeks'),
                           ('price_basis','different_basis'),('as_of','2034-05-19T12:00:00Z'),
                           ('max_target_age_days',90),('max_quote_age_hours',96)]:
            with self.subTest(field=key):
                request = copy.deepcopy(self.literal)
                if key in analyst.DIMENSIONS: request['cohort'][key] = value
                else: request[key] = value
                with self.assertRaisesRegex(ValueError, 'FILTER_MISMATCH:'+key): self.analyze(request)

    def test_matching_legacy_uses_original_nondefault_age(self):
        self.original['max_target_age_days'] = 10
        self.prepare(); out = self.analyze(self.literal)
        self.assertEqual(out['eligible_cohort']['result']['consensus']['independent_firms'], 0)
        self.assertEqual(out['request_binding']['effective_filters']['max_target_age_days'], 10)
        self.assertTrue(all(row['reason']=='STALE_TARGET' for row in out['eligible_cohort']['result']['excluded']))

    def test_missing_age_uses_disclosed_default_not_source_value(self):
        del self.original['max_target_age_days']; self.prepare(); out = self.analyze()
        binding = out['request_binding']['fields']['max_target_age_days']
        self.assertEqual(binding['origin'], 'DOCUMENTED_DEFAULT')
        self.assertEqual(binding['effective_value'], 90)
        self.assertIsNone(binding['source_ref']); self.assertIsNone(binding['source_value'])

    def test_bound_form_forbids_literal_overrides(self):
        self.prepare()
        for field, value in [('cohort',self.dimensions),('as_of',self.cutoff),('max_target_age_days',1),('defaults',{})]:
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'NO_LITERAL_OVERRIDES'):
                self.analyze({**self.bound, field:value})

    def test_multiple_roots_require_selection_even_if_values_equal(self):
        self.prepare([('original',self.original,'json'),('second',self.original,'json')])
        with self.assertRaisesRegex(ValueError, 'REQUEST_AMBIGUOUS'): self.analyze(self.literal)
        out = self.analyze()
        self.assertEqual(out['request_binding']['candidate_original_request_ids'], ['original','second'])
        self.assertEqual(out['request_binding']['original_request_ref']['source_id'], 'original')

    def test_explicit_selection_does_not_borrow_from_other_root(self):
        other = copy.deepcopy(self.original); other['price_basis'] = 'other_class'; other['individual_targets'] = []
        self.prepare([('original',self.original,'json'),('second',other,'json')])
        request = copy.deepcopy(self.bound); request['original_request_ref']['source_id'] = 'second'
        out = self.analyze(request)
        self.assertEqual(out['request_binding']['effective_filters']['cohort']['price_basis'], 'other_class')
        self.assertEqual(out['eligible_cohort']['result']['consensus']['independent_firms'], 0)

    def test_missing_null_malformed_dimensions_cannot_fallback(self):
        for field in (*analyst.DIMENSIONS, 'as_of', 'individual_targets'):
            for mode in ('absent','null'):
                with self.subTest(field=field,mode=mode):
                    doc = copy.deepcopy(self.original)
                    if mode == 'absent': del doc[field]
                    else: doc[field] = None
                    self.prepare([('original',doc,'json')])
                    with self.assertRaises(ValueError): self.analyze(self.literal)

    def test_unrecognized_original_policy_is_not_ignored(self):
        doc = {**self.original, 'exclude_firms':['North']}
        self.prepare([('original',doc,'json')])
        with self.assertRaisesRegex(ValueError, 'SCHEMA_UNSUPPORTED'): self.analyze(self.literal)

    def test_invalid_age_policy_rejects(self):
        for value in (True, None, 0, -1, '30', float('inf')):
            with self.subTest(value=value):
                doc = {**self.original,'max_target_age_days':value}
                self.prepare([('original',doc,'json')])
                with self.assertRaises(ValueError): self.analyze()

    def test_decimal_age_retains_source_representation(self):
        self.original['max_target_age_days'] = 40.5; self.prepare(); out = self.analyze()
        row = out['request_binding']['fields']['max_target_age_days']
        self.assertEqual(row['effective_value'],40.5)
        self.assertEqual((row['source_value_type'],row['source_value']),('decimal','40.5'))

    def test_lossy_decimal_age_not_rounded(self):
        raw = json.dumps(self.original).replace('"max_target_age_days": 60','"max_target_age_days": 60.123456789123456789').encode()
        self.prepare([('original',raw,'json')])
        with self.assertRaisesRegex(ValueError,'PRECISION_UNSUPPORTED'): self.analyze()

    def test_unrepresentable_age_has_explicit_failure(self):
        self.original['max_target_age_days'] = 10**400
        self.prepare()
        with self.assertRaisesRegex(ValueError,'PRECISION_UNSUPPORTED'): self.analyze()

    def test_source_text_label_is_not_alias_for_original_share_basis(self):
        note = ('Firm West, analyst Willow, issued 2034-04-15T10:00:00Z: SYNB target EUR 66 '
                'per common share; horizon forward_12_months; access FULL_REPORT. No split adjustment.')
        self.prepare([('original',self.original,'json'),('text-note',note,'text')])
        out = self.analyze()
        self.assertEqual(out['eligible_cohort']['result']['consensus']['independent_firms'],2)
        text_record = next(r for r in out['records'] if r['source_id']=='text-note')
        self.assertEqual(text_record['fields']['price_basis'],'common_share_unadjusted')
        self.assertTrue(any(r['record_id']==text_record['record_id'] and 'COHORT_MISMATCH:price_basis' in r['reasons']
                            for r in out['eligible_cohort']['excluded']))

    def test_record_only_literal_route_and_default_provenance(self):
        self.prepare([('records',{'individual_targets':self.original['individual_targets']},'json')])
        out = self.analyze(self.literal)
        self.assertEqual(out['request_binding']['status'],'DECLARED_FILTER_ONLY')
        self.assertEqual(out['eligible_cohort']['result']['consensus']['mean'],48)
        self.assertEqual(out['request_binding']['fields']['price_basis']['origin'],'DECLARED_FILTER')
        self.assertEqual(out['request_binding']['fields']['max_target_age_days']['origin'],'DOCUMENTED_DEFAULT')

    def test_nested_root_reference_is_not_guessed(self):
        self.prepare([('original',{'wrapper':self.original},'json')])
        request = copy.deepcopy(self.bound); request['original_request_ref']['pointer']='/wrapper'
        with self.assertRaisesRegex(ValueError,'ROOT_REFERENCE_REQUIRED'): self.analyze(request)

    def test_missing_or_text_reference_rejects(self):
        self.prepare([('original','No JSON contract here.','text')])
        with self.assertRaisesRegex(ValueError,'REQUEST_NOT_FOUND'): self.analyze()

    def test_duplicate_key_in_source_rejects(self):
        raw = json.dumps(self.original).replace('"issuer": "SYNB"','"issuer": "SYNB", "issuer": "ALT"',1).encode()
        self.prepare([('original',raw,'json')])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_JSON_KEY'): self.analyze()

    def test_input_manifest_pin_cannot_be_replaced(self):
        self.prepare(); (self.sources/'original.json').write_text('{}')
        with self.assertRaises(ValueError): self.analyze()

    def test_unknown_row_dimensions_never_filled_from_root(self):
        self.original['individual_targets'][0]['currency'] = None
        self.prepare(); out = self.analyze()
        self.assertEqual(out['eligible_cohort']['result']['consensus']['independent_firms'],1)
        self.assertTrue(any('UNKNOWN:currency' in r['reasons'] for r in out['eligible_cohort']['excluded']))

    def test_bridge_and_canonical_response_replay_exact_binding(self):
        self.prepare(); request = self.root/'source-request.json'
        request.write_bytes(bridge.encode({'producer':'analyst_sources','producer_request':self.bound}))
        output = self.root/'source-run'
        bridge.run(request,output,self.manifest,self.pin,self.sources)
        self.assertEqual(bridge.verify(output)['status'],'SOURCE_REPLAY_AND_SAVED_REPORT_MATCH')
        report = self.compose(); metadata = self.root/'metadata.json'
        metadata.write_bytes(bridge.encode({'case_id':'synthetic-binding','runtime_model_metadata':{'model':'test','effort':'test'}}))
        export = self.root/'response'
        final.export_response(report,metadata,export)
        self.assertEqual(final.verify_response(export)['status'],'COMPLETED_CANONICAL_RESPONSE_EXPORT')
        response = json.loads((export/'response.json').read_bytes())
        result = response['rows'][0]['result']
        self.assertEqual(result['request_binding']['effective_filters']['cohort'],self.dimensions)
        self.assertEqual(result['eligible_cohort']['result']['consensus']['iqr'],6)
        self.assertIn('class_b_unit_original',(export/'report/first-response.md').read_text())
        self.assertFalse(response['whole_report_semantic_pass'])

    def test_changed_plan_filter_fails_even_with_resigned_inventory(self):
        self.prepare(); report = self.compose(self.literal)
        path = report/'original-plan.json'; plan = json.loads(path.read_bytes())
        plan['sections'][0]['request']['cohort']['price_basis']='common_share_unadjusted'
        path.write_bytes(bridge.encode(plan))
        receipt = json.loads((report/'receipt.json').read_bytes())
        receipt['artifacts']=bridge.file_inventory(report)
        (report/'receipt.json').write_bytes(bridge.encode(receipt))
        with self.assertRaises(ValueError): final.verify(report)


if __name__ == '__main__':
    unittest.main()
