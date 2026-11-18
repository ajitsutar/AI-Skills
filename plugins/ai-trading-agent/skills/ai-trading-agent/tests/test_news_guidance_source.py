"""Portable synthetic regressions for source-bound guidance and withdrawals."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import news_evidence as ne
import news_analysis as na


class GuidanceSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.document = {'issuer': {'id': 'SYNTH', 'name': 'Synthetic Manufacturing'}, 'releases': [
            {'id': 'old', 'published_at': '2030-09-01T10:00:00Z', 'first_seen_at': '2030-09-01T10:02:00Z',
             'body': 'FY2031 IFRS revenue guidance is EUR 40 to 60 million.'},
            {'id': 'new', 'published_at': '2030-09-03T10:00:00Z', 'first_seen_at': '2030-09-03T10:02:00Z',
             'body': 'FY2031 IFRS revenue guidance is EUR 45 to 65 million. The company withdrew its adjusted cash earnings guidance.'}]}
        self.save_source()
        self.request = {'as_of': '2030-09-04T00:00:00Z', 'previous': self.row(0, 40, 60),
                        'current': self.row(1, 45, 65)}

    def save_source(self):
        self.source = self.root/'archive.json'
        self.source.write_text(json.dumps(self.document), encoding='utf-8')
        self.source_hash = ne.digest(self.source.read_bytes())

    def refresh(self, request):
        self.save_source()
        for key in ('previous', 'current'):
            if request.get(key):
                request[key]['source']['sha256'] = self.source_hash
        return request

    def span(self, index, value):
        text = self.document['releases'][index]['body']
        start = text.lower().index(value.lower())
        return {'kind': 'source', 'pointer': '/body', 'span': [start, start + len(value)]}

    def row(self, index, low, high):
        fields = {k: self.span(index, v) for k, v in {
            'metric': 'revenue', 'period': 'FY2031', 'currency': 'EUR', 'unit': 'million',
            'low': str(low), 'high': str(high)}.items()}
        fields['issuer'] = {'kind': 'source_context', 'container_pointer': '', 'pointer': '/issuer/id'}
        fields['accounting_basis'] = {'kind': 'source_phrase', 'pointer': '/body', 'value': 'IFRS'}
        return {'id': ['old', 'new'][index], 'status': 'issued',
                'source': {'path': 'archive.json', 'sha256': self.source_hash, 'record_pointer': '/releases/' + str(index)},
                'clocks': {'publication': {'kind': 'source', 'pointer': '/published_at'},
                           'observation': {'kind': 'source', 'pointer': '/first_seen_at'}}, 'fields': fields}

    def withdrawal(self, sentence='The company withdrew its adjusted cash earnings guidance.'):
        self.document['releases'][1]['body'] = sentence
        self.save_source()
        item = copy.deepcopy(self.request['current'])
        item['source']['sha256'] = self.source_hash
        item['status'] = 'withdrawn'
        item['fields'] = {'issuer': {'kind': 'source_context', 'container_pointer': '', 'pointer': '/issuer/id'},
                          'metric': self.span(1, 'adjusted cash earnings')}
        item['withdrawal'] = {'kind': 'source_phrase', 'pointer': '/body'}
        return {'as_of': self.request['as_of'], 'previous': None, 'current': item}

    def test_label_comparison_needs_no_url_or_calendar_dates(self):
        before = self.source.read_bytes()
        out = ne.guidance(self.request, self.root)
        self.assertEqual(out['arithmetic']['previous_midpoint'], '50')
        self.assertEqual(out['arithmetic']['current_midpoint'], '55')
        self.assertEqual(out['comparison_status'], 'ARITHMETIC_ONLY')
        self.assertEqual(out['period_evidence'][0]['label']['value'], 'FY2031')
        self.assertIsNone(out['period_evidence'][0]['start']['value'])
        self.assertIsNone(out['period_evidence'][0]['end']['value'])
        self.assertEqual(out['records'][0]['fields']['issuer']['kind'], 'source_context')
        self.assertFalse(out['records'][0]['fields']['issuer']['semantic_identity_verified'])
        self.assertEqual(self.source.read_bytes(), before)

    def test_existing_compare_algorithm_unchanged(self):
        self.assertEqual(ne.compare(self.request, self.root)['arithmetic'], ne.guidance(self.request, self.root)['arithmetic'])

    def test_invented_calendar_override_rejected(self):
        self.request['current']['fields']['period']['value'] = '2031-01-01/2031-12-31'
        with self.assertRaisesRegex(ValueError, 'FIELD_VALUE_DIFFERS'):
            ne.guidance(self.request, self.root)

    def test_exact_dates_cannot_be_declared(self):
        self.request['current']['period_boundaries'] = {
            'start': {'kind': 'declared', 'value': '2031-01-01', 'reason': 'FY label guess'}}
        with self.assertRaisesRegex(ValueError, 'EXACT_PERIOD_DATES_REQUIRE_SOURCE'):
            ne.guidance(self.request, self.root)

    def add_dates(self, item, index, start='2030-07-01', end='2031-06-30'):
        self.document['releases'][index].update(period_start=start, period_end=end)
        item['period_boundaries'] = {'start': {'kind': 'source', 'pointer': '/period_start'},
                                     'end': {'kind': 'source', 'pointer': '/period_end'}}

    def test_explicit_fiscal_dates_bound_and_mismatch_blocks_arithmetic(self):
        self.add_dates(self.request['previous'], 0)
        self.add_dates(self.request['current'], 1)
        self.refresh(self.request)
        out = ne.guidance(self.request, self.root)
        self.assertEqual(out['period_evidence'][1]['start']['value'], '2030-07-01')
        self.document['releases'][1]['period_end'] = '2031-09-30'
        self.refresh(self.request)
        out = ne.guidance(self.request, self.root)
        self.assertEqual(out['comparison_status'], 'NOT_COMPARABLE')
        self.assertIsNone(out['arithmetic'])

    def test_one_sided_boundary_is_not_matched(self):
        self.add_dates(self.request['current'], 1)
        self.refresh(self.request)
        out = ne.guidance(self.request, self.root)
        self.assertIn('EXACT_PERIOD_BOUNDARIES_NOT_MATCHED_BOTH_RECORDS', out['limitations'])
        del self.request['current']['period_boundaries']['end']
        with self.assertRaisesRegex(ValueError, 'REQUIRE_BOTH_DATES'):
            ne.guidance(self.request, self.root)

    def test_context_cannot_escape_to_sibling_or_other_dimension(self):
        for spec in [dict(kind='source_context', container_pointer='/releases/0', pointer='/issuer/id'),
                     dict(kind='source_context', container_pointer='', pointer='/releases/0/id')]:
            request = copy.deepcopy(self.request)
            request['current']['fields']['issuer'] = spec
            with self.assertRaisesRegex(ValueError, 'CONTEXT_BINDING'):
                ne.guidance(request, self.root)
        self.request['current']['fields']['currency'] = {'kind': 'source_context', 'container_pointer': '', 'pointer': '/issuer/id'}
        with self.assertRaisesRegex(ValueError, 'ONLY_FOR_ISSUER'):
            ne.guidance(self.request, self.root)

    def test_context_override_and_changed_source_rejected(self):
        self.request['current']['fields']['issuer']['value'] = 'OTHER'
        with self.assertRaisesRegex(ValueError, 'FIELD_VALUE_DIFFERS'):
            ne.guidance(self.request, self.root)
        self.request['current']['source']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SOURCE_HASH_MISMATCH'):
            ne.guidance(self.request, self.root)

    def test_withdrawal_unknown_dimensions_stay_unknown(self):
        request = self.withdrawal()
        before = self.source.read_bytes()
        out = ne.guidance(request, self.root)
        self.assertEqual(out['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')
        self.assertEqual(out['comparison_status'], 'SOURCE_BOUND_WITHDRAWAL_STATEMENT')
        for field in ('period', 'currency', 'unit', 'accounting_basis', 'low', 'high'):
            self.assertIsNone(out['records'][0]['fields'][field]['value'])
        for field in ('prior_range', 'arithmetic', 'range_change', 'midpoint_change'):
            self.assertIsNone(out[field])
        self.assertFalse(out['withdrawal_is_zero_guidance'])
        self.assertFalse(out['source_authenticity_verified'])
        self.assertEqual(self.source.read_bytes(), before)

    def test_withdrawal_cannot_reuse_other_metric_prior_range(self):
        request = self.withdrawal()
        request['previous'] = copy.deepcopy(self.request['previous'])
        self.refresh(request)
        out = ne.guidance(request, self.root)
        self.assertIsNone(out['prior_range'])
        self.assertEqual(out['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')
        self.assertIn('PRIOR_RANGE_DIMENSIONS_NOT_MATCHED', out['limitations'])

    def test_withdrawal_rejects_negated_conditional_and_clipped_context(self):
        for sentence in [
            'The company has not withdrawn its adjusted cash earnings guidance.',
            'If conditions weaken, the company withdrew its adjusted cash earnings guidance.',
            'The company may have withdrawn its adjusted cash earnings guidance.',
            'An analyst said the company withdrew its adjusted cash earnings guidance.',
            'The company plans to withdraw its adjusted cash earnings guidance.',
            'The company reaffirmed its adjusted cash earnings guidance.',
        ]:
            with self.subTest(sentence=sentence):
                request = self.withdrawal(sentence)
                if 'the company' in sentence:
                    start = sentence.index('the company')
                    request['current']['withdrawal']['span'] = [start, len(sentence)]
                with self.assertRaisesRegex(ValueError, 'WITHDRAWAL_PHRASE_UNRESOLVED'):
                    ne.guidance(request, self.root)

    def test_withdrawal_status_must_bind_selected_metric(self):
        request = self.withdrawal('The company withdrew its revenue guidance. Adjusted cash earnings guidance is unchanged.')
        request['current']['withdrawal']['span'] = [0, len('The company withdrew its revenue guidance.')]
        with self.assertRaisesRegex(ValueError, 'WITHDRAWAL_PHRASE_UNRESOLVED'):
            ne.guidance(request, self.root)

    def test_passive_withdrawal_statement(self):
        out = ne.guidance(self.withdrawal('Adjusted cash earnings guidance has been withdrawn.'), self.root)
        self.assertEqual(out['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')

    def test_bounded_withdrawal_span_in_multi_sentence_release(self):
        sentence = 'The company withdrew its adjusted cash earnings guidance.'
        request = self.withdrawal('Operations continue. ' + sentence + ' Revenue guidance is unchanged.')
        start = self.document['releases'][1]['body'].index(sentence)
        request['current']['withdrawal']['span'] = [start, start + len(sentence)]
        self.assertEqual(ne.guidance(request, self.root)['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')

    def test_line_wrapping_cannot_hide_withdrawal_qualifiers(self):
        sentence = 'The company withdrew its adjusted cash earnings guidance.'
        for prefix in ('It is not true that', 'If demand weakens,', 'An analyst said:'):
            for separator in ('\n', '\r\n', '; '):
                with self.subTest(prefix=prefix, separator=repr(separator)):
                    body = prefix + separator + sentence
                    request = self.withdrawal(body)
                    request['current']['withdrawal']['span'] = [len(prefix + separator), len(body)]
                    with self.assertRaisesRegex(ValueError, 'WITHDRAWAL_PHRASE_UNRESOLVED'):
                        ne.guidance(request, self.root)

    def test_wrapped_positive_and_real_sentence_boundary_remain_supported(self):
        for body in ('The company\nwithdrew its adjusted cash earnings guidance.',
                     'Operations continue.\nThe company withdrew its adjusted cash earnings guidance.'):
            with self.subTest(body=body):
                request = self.withdrawal(body)
                start = body.index('The company')
                request['current']['withdrawal']['span'] = [start, len(body)]
                self.assertEqual(ne.guidance(request, self.root)['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')

    def matched_withdrawal(self):
        request = copy.deepcopy(self.request)
        self.document['releases'][1].update(metric='revenue', guidance_status='withdrawn')
        request['current']['status'] = 'withdrawn'
        request['current']['withdrawal'] = {'kind': 'source', 'pointer': '/guidance_status'}
        del request['current']['fields']['low']
        del request['current']['fields']['high']
        return self.refresh(request)

    def test_matched_prior_range_retained_without_zero_change(self):
        request = self.matched_withdrawal()
        out = ne.guidance(request, self.root)
        self.assertEqual(out['classification'], 'WITHDRAWN')
        self.assertEqual(out['prior_range'], {'low': '40', 'high': '60'})
        self.assertIsNone(out['arithmetic'])
        self.assertIsNone(out['midpoint_change'])
        self.add_dates(request['previous'], 0)
        self.add_dates(request['current'], 1, end='2031-09-30')
        self.refresh(request)
        out = ne.guidance(request, self.root)
        self.assertEqual(out['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')
        self.assertIsNone(out['prior_range'])

    def test_declared_dimensions_cannot_bind_withdrawal_prior_range(self):
        request = self.matched_withdrawal()
        request['current']['fields']['period'] = {'kind': 'declared', 'value': 'FY2031', 'reason': 'assumed'}
        out = ne.guidance(request, self.root)
        self.assertEqual(out['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')
        self.assertIsNone(out['prior_range'])

    def test_structured_withdrawal_status_same_metric(self):
        request = self.withdrawal()
        self.document['releases'][1].update(metric='adjusted cash earnings', guidance_status='withdrawn')
        request['current']['fields']['metric'] = {'kind': 'source', 'pointer': '/metric'}
        request['current']['withdrawal'] = {'kind': 'source', 'pointer': '/guidance_status'}
        self.refresh(request)
        self.assertEqual(ne.guidance(request, self.root)['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')
        self.document['releases'][1]['guidance_status'] = 'reaffirmed'
        self.refresh(request)
        with self.assertRaisesRegex(ValueError, 'WITHDRAWAL_STATUS_METRIC_MISMATCH'):
            ne.guidance(request, self.root)

    def test_withdrawal_cannot_be_zero_or_declared_status(self):
        request = self.withdrawal()
        request['current']['fields']['low'] = {'kind': 'declared', 'value': 0, 'reason': 'withdrawal'}
        with self.assertRaisesRegex(ValueError, 'NOT_A_NUMERIC'):
            ne.guidance(request, self.root)
        del request['current']['fields']['low']
        request['current']['withdrawal'] = {'kind': 'declared', 'value': 'withdrawn', 'reason': 'assumption'}
        with self.assertRaisesRegex(ValueError, 'SOURCE_BOUND_WITHDRAWAL_REQUIRED'):
            ne.guidance(request, self.root)

    def test_future_or_unknown_clock_does_not_become_current_withdrawal(self):
        request = self.withdrawal()
        self.document['releases'][1]['published_at'] = '2030-09-05T10:00:00Z'
        self.refresh(request)
        out = ne.guidance(request, self.root)
        self.assertEqual(out['comparison_status'], 'EXCLUDED_AT_CUTOFF')
        self.assertIsNone(out['classification'])
        self.document['releases'][1]['published_at'] = '2030-09-03T10:00:00Z'
        self.refresh(request)
        request['current']['clocks']['observation'] = {'kind': 'unknown'}
        out = ne.guidance(request, self.root)
        self.assertEqual(out['comparison_status'], 'WITHDRAWAL_REVIEW_REQUIRED')
        self.assertIsNone(out['classification'])

    def test_same_publication_prior_is_not_new_withdrawal(self):
        request = self.withdrawal()
        request['previous'] = copy.deepcopy(self.request['previous'])
        self.document['releases'][1]['published_at'] = self.document['releases'][0]['published_at']
        self.refresh(request)
        out = ne.guidance(request, self.root)
        self.assertEqual(out['publication_order'], 'SAME_PUBLICATION')
        self.assertIsNone(out['classification'])

    def test_saved_claim_audit_rejects_invented_period_dates(self):
        out = ne.guidance(self.request, self.root)
        p = self.root/'result.json'
        p.write_text(json.dumps(out), encoding='utf-8')
        audit = ne.audit_claims({'output': {'path': p.name, 'sha256': ne.digest(p.read_bytes())},
            'claims': [{'id': 'invented-calendar', 'pointer': '/period_evidence/0/start/value', 'value': '2031-01-01'}]}, self.root)
        self.assertEqual(audit['status'], 'CLAIM_MISMATCH')

    def test_legacy_arithmetic_retains_explicit_declared_provenance(self):
        def legacy(index, low, high):
            row = self.document['releases'][index]
            return {'issuer': 'SYNTH', 'metric': 'revenue', 'period_start': '2030-07-01', 'period_end': '2031-06-30',
                    'currency': 'EUR', 'unit': 'million', 'accounting_basis': 'IFRS', 'status': 'issued', 'low': low, 'high': high,
                    'source': {'path': self.source.name, 'sha256': self.source_hash, 'source_kind': 'issuer',
                               'url': 'https://example.org/release', 'published_at': row['published_at'],
                               'observed_at': row['first_seen_at'], 'locator': 'synthetic release', 'verbatim_excerpt': row['body']}}
        out = na.guidance_change({'as_of': self.request['as_of'], 'previous': legacy(0, 40, 60), 'current': legacy(1, 45, 65)}, self.root)
        self.assertEqual(out['classification'], 'RAISED_RANGE')
        self.assertFalse(out['source_dimensions_verified'])
        self.assertEqual(out['dimension_provenance'], 'CALLER_DECLARED_NOT_SOURCE_VERIFIED')

    def test_guidance_cli_exclusive_output(self):
        req = self.root/'request.json';out = self.root/'output.json'
        req.write_text(json.dumps(self.withdrawal()), encoding='utf-8')
        command = [sys.executable, '-B', ne.__file__, 'guidance', str(req), str(self.root), str(out)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(out.read_text())['classification'], 'WITHDRAWAL_PRIOR_RANGE_UNKNOWN')
        original = out.read_bytes()
        run = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(out.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
