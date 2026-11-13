"""Generic source/claim counterexamples; no campaign inputs or expected answers."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import source_claims as subject


class SourceClaimsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'manifest.json'

    def ingress(self, entries):
        sources = []
        for sid, fmt, document in entries:
            raw = json.dumps(document).encode() if fmt == 'json' else document.encode() if isinstance(document, str) else document
            path = sid + '.source'
            (self.root / path).write_bytes(raw)
            sources.append({'id': sid, 'path': path, 'sha256': hashlib.sha256(raw).hexdigest(), 'format': fmt})
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': sources}), encoding='utf-8')
        self.pin = subject.digest(self.manifest.read_bytes())
        return subject.Corpus(self.manifest, self.pin)

    def audit(self, request):
        return subject.audit(request, self.manifest, self.pin)

    def test_source_key_present_adapter_unbound_is_not_absence(self):
        self.ingress([('filing', 'json', {'cash_distributed_common': 19, 'nullable': None})])
        result = self.audit({'operation': 'presence', 'terms': ['common'], 'assert_claims': ['source_absent']})
        self.assertEqual(result['predicate'], 'SOURCE_CANDIDATE_PRESENT')
        self.assertEqual(result['binding_state'], 'UNBOUND')
        self.assertEqual(result['claim_verdict'], 'REJECTED')
        self.assertEqual(result['scan']['candidates'][0]['source_ref']['pointer'], '/cash_distributed_common')
        self.assertFalse(result['facts'][0]['semantic_scope_verified'])

    def test_exact_binding_is_independent_of_lexical_presence(self):
        self.ingress([('filing', 'json', {'scope': 'common', 'other': 9})])
        request = {'operation': 'presence', 'terms': ['common'],
                   'binding': {'value': 'common', 'source_ref': {'source_id': 'filing', 'pointer': '/scope'}},
                   'assert_claims': ['source_candidate_present', 'adapter_value_bound']}
        self.assertEqual(self.audit(request)['claim_verdict'], 'WITHIN_DECLARED_CONTRACT')
        request['binding']['value'] = 'preferred'
        result = self.audit(request)
        self.assertEqual(result['binding_state'], 'INVALID')
        self.assertTrue(result['scan']['candidates'])
        self.assertEqual(result['claim_verdict'], 'REJECTED')

    def test_no_hits_cannot_prove_semantic_absence(self):
        self.ingress([('notes', 'text', 'ordinary equity distributions described here')])
        result = self.audit({'operation': 'presence', 'terms': ['common'], 'assert_claims': ['source_absent']})
        self.assertFalse(result['source_absence_established'])
        self.assertEqual(result['claim_verdict'], 'REJECTED')

    def test_no_substring_false_match_and_empty_terms_fail(self):
        self.ingress([('notes', 'text', 'commodity sales and uncommon costs')])
        result = self.audit({'operation': 'presence', 'terms': ['common']})
        self.assertEqual(result['scan']['candidates'], [])
        with self.assertRaisesRegex(ValueError, 'SEARCH_TERMS'):
            self.audit({'operation': 'presence', 'terms': ['']})

    def test_binary_and_tampered_sources_fail_closed(self):
        self.ingress([('binary', 'bytes', b'opaque')])
        result = self.audit({'operation': 'coverage', 'terms': ['target'], 'assert_claims': ['configured_scan_reconciled']})
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['scan']['unsupported_sources'], ['binary'])
        (self.root / 'binary.source').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            self.audit({'operation': 'presence', 'terms': ['target']})

    def accounting_source(self, basis='weighted_average_diluted', attribution='diluted_income_available_to_common'):
        return {'income': {'value': 18, 'attribution': attribution, 'period_start': '2034-01-01',
                           'period_end': '2034-12-31', 'issuer': 'Example Issuer', 'currency': 'EUR', 'unit_scale': 1000},
                'shares': {'value': 6, 'basis': basis, 'period_start': '2034-01-01',
                           'period_end': '2034-12-31', 'issuer': 'Example Issuer', 'unit_scale': 1000}}

    def accounting_request(self, data):
        return {'operation': 'accounting', **{group: {field: {'source_id': 'filing', 'pointer': '/' + group + '/' + field}
                for field in data[group]} for group in ('income', 'shares')}}

    def test_weighted_diluted_eps_requires_matched_original_metadata(self):
        data = self.accounting_source()
        self.ingress([('filing', 'json', data)])
        request = self.accounting_request(data)
        request['assert_claims'] = ['diluted_eps']
        result = self.audit(request)
        self.assertEqual(result['eps'], 3)
        self.assertEqual(result['classification'], 'DILUTED_EPS_SOURCE_BOUND')
        self.assertIsNone(result['pe'])
        self.assertEqual(result['claim_verdict'], 'WITHIN_DECLARED_CONTRACT')

    def test_dated_shares_leave_arithmetic_but_block_eps_claim(self):
        data = self.accounting_source(basis='as_of_date', attribution='consolidated_net_income')
        del data['shares']['period_start']
        self.ingress([('filing', 'json', data)])
        request = self.accounting_request(data)
        request['assert_claims'] = ['diluted_eps', 'pe']
        result = self.audit(request)
        self.assertEqual(result['raw_operand_ratio'], 3)
        self.assertIsNone(result['eps'])
        self.assertEqual(result['classification'], 'DIAGNOSTIC_RATIO_ONLY')
        self.assertEqual(result['claim_verdict'], 'REJECTED')

    def test_missing_attribution_mismatched_period_and_scale_are_not_inferred(self):
        data = self.accounting_source()
        data['shares']['period_end'] = '2033-12-31'
        del data['income']['attribution']
        del data['shares']['unit_scale']
        self.ingress([('filing', 'json', data)])
        result = self.audit(self.accounting_request(data))
        self.assertIsNone(result['eps'])
        self.assertTrue(any('period_end' in x for x in result['reasons']))
        self.assertTrue(any('attribution' in x for x in result['reasons']))
        self.assertTrue(any('unit_scale' in x for x in result['reasons']))

    def test_basic_eps_scales_original_operands_and_rejects_nonstrings(self):
        data = self.accounting_source(basis='weighted_average_basic', attribution='income_available_to_common')
        data['shares']['unit_scale'] = 1
        self.ingress([('filing', 'json', data)])
        result = self.audit(self.accounting_request(data))
        self.assertEqual(result['eps'], 3000)
        self.assertEqual(result['allowed_claims'], ['basic_eps'])
        data['income']['issuer'] = data['shares']['issuer'] = True
        data['income']['currency'] = 'euro'
        self.ingress([('filing', 'json', data)])
        result = self.audit(self.accounting_request(data))
        self.assertIsNone(result['eps'])
        self.assertIn('ISSUER_IDENTITY_NOT_ESTABLISHED:income', result['reasons'])
        self.assertIn('INCOME_CURRENCY_NOT_ESTABLISHED', result['reasons'])

    def test_accounting_metadata_cannot_be_borrowed_from_other_record(self):
        data = self.accounting_source(attribution='consolidated_net_income')
        data['unrelated_income'] = dict(data['income'], attribution='diluted_income_available_to_common')
        self.ingress([('filing', 'json', data)])
        request = self.accounting_request(data)
        request['income']['attribution']['pointer'] = '/unrelated_income/attribution'
        result = self.audit(request)
        self.assertIsNone(result['eps'])
        self.assertEqual(result['classification'], 'DIAGNOSTIC_RATIO_ONLY')

    def test_accounting_metadata_cannot_be_borrowed_from_other_source(self):
        data = self.accounting_source(attribution='consolidated_net_income')
        other = self.accounting_source()
        self.ingress([('filing', 'json', data), ('other', 'json', other)])
        request = self.accounting_request(data)
        request['income']['attribution']['source_id'] = 'other'
        self.assertIsNone(self.audit(request)['eps'])

    def test_same_object_different_numeric_or_metadata_role_cannot_be_borrowed(self):
        data = self.accounting_source()
        data['income']['other_income'] = 24
        data['income']['other_attribution'] = data['income']['attribution']
        self.ingress([('filing', 'json', data)])
        for role, key in [('value', 'other_income'), ('attribution', 'other_attribution')]:
            with self.subTest(role=role):
                request = self.accounting_request(data)
                request['income'][role]['pointer'] = '/income/' + key
                result = self.audit(request)
                self.assertIsNone(result['eps'])
                self.assertIn('ACCOUNTING_FIELD_ROLE_MISMATCH:income.' + role, result['reasons'])

    def test_boolean_numbers_zero_denominator_and_type_mismatches_reject(self):
        for field, value in [('value', True), ('value', 0), ('unit_scale', -1)]:
            with self.subTest(field=field, value=value):
                data = self.accounting_source()
                data['shares'][field] = value
                self.ingress([('filing', 'json', data)])
                with self.assertRaises(ValueError):
                    self.audit(self.accounting_request(data))

    def test_explicit_embedded_json_span_preserves_prefix_and_key_context(self):
        data = self.accounting_source()
        segment = json.dumps(data)
        raw = 'Illustrative filing header\n' + segment + '\nEnd.'
        corpus = self.ingress([('filing', 'text', raw)])
        ref = {'source_id': 'filing', 'start': raw.index('{'), 'end': raw.index('{') + len(segment),
               'excerpt': segment, 'pointer': '/shares/basis'}
        self.assertEqual(corpus.resolve(ref), 'weighted_average_diluted')
        ref['excerpt'] = segment.replace('diluted', 'basic')
        with self.assertRaisesRegex(ValueError, 'SPAN_MISMATCH'):
            corpus.resolve(ref)

    def corpus_setup(self):
        corpus = self.ingress([('initial', 'text', 'Firm Cedar target EUR 41\n'),
                               ('revision', 'text', 'Firm Cedar revised target EUR 47\n')])
        scan = corpus.scan(['target'])
        return corpus, scan['candidates']

    def coverage_request(self, candidates):
        return {'operation': 'coverage', 'terms': ['target'],
                'records': [{'record_id': 'row-' + str(i), 'source_refs': [candidate['source_ref']]}
                            for i, candidate in enumerate(candidates)],
                'dispositions': [{'candidate_id': candidate['candidate_id'], 'status': 'extracted',
                                  'record_ids': ['row-' + str(i)], 'reason': 'Reviewed source target disclosure'}
                                 for i, candidate in enumerate(candidates)]}

    def test_omitted_revision_file_is_detected_without_filename_rules(self):
        _, candidates = self.corpus_setup()
        request = self.coverage_request(candidates[:1])
        request['assert_claims'] = ['configured_scan_reconciled', 'complete_corpus']
        result = self.audit(request)
        self.assertEqual(len(result['unresolved_candidate_ids']), 1)
        self.assertEqual(result['status'], 'INCOMPLETE')
        self.assertEqual(result['claim_verdict'], 'REJECTED')

    def test_every_candidate_reconciled_still_does_not_prove_semantic_completeness(self):
        _, candidates = self.corpus_setup()
        result = self.audit(self.coverage_request(candidates))
        self.assertEqual(result['status'], 'CONFIGURED_SCAN_RECONCILED')
        self.assertFalse(result['whole_source_semantic_completeness'])

    def test_unrelated_reference_cannot_cover_a_candidate(self):
        _, candidates = self.corpus_setup()
        request = self.coverage_request(candidates)
        request['records'][1]['source_refs'] = [candidates[0]['source_ref']]
        with self.assertRaisesRegex(ValueError, 'DOES_NOT_COVER'):
            self.audit(request)

    def test_unknown_duplicate_and_unlinked_records_reject(self):
        _, candidates = self.corpus_setup()
        request = self.coverage_request(candidates)
        request['dispositions'].append(deepcopy(request['dispositions'][0]))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_CANDIDATE'):
            self.audit(request)
        request = self.coverage_request(candidates)
        request['records'].append({'record_id': 'orphan', 'source_refs': [candidates[0]['source_ref']]})
        self.assertEqual(self.audit(request)['unlinked_record_ids'], ['orphan'])

    def analyst_request(self, candidates):
        request = self.coverage_request(candidates)
        rows = []
        for i, candidate in enumerate(candidates):
            ref = candidate['source_ref']
            sid = ref['source_id']
            stamp = '2034-11-0' + str(i + 1) + 'T12:00:00Z'
            rows.append({'record_id': 'row-' + str(i), 'issuer': 'Example Issuer', 'currency': 'EUR',
                         'price_basis': 'current_ordinary_share', 'target_horizon': 'forward_12_months',
                         'firm_id': 'Cedar', 'analyst_id': 'Analyst A', 'access': 'ATTRIBUTED_EXCERPT',
                         'issued_at': stamp, 'target': [41, 47][i],
                         'source': {'path': sid + '.source', 'sha256': candidate['source_sha256'],
                                    'url': 'https://example.invalid/' + sid, 'published_at': stamp,
                                    'observed_at': stamp, 'locator': 'Line 1', 'verbatim_excerpt': ref['excerpt']}})
        return {'operation': 'analyst_corpus', 'coverage': request,
                'analysis': {'as_of': '2034-11-03T12:00:00Z', 'issuer': 'Example Issuer', 'currency': 'EUR',
                             'price_basis': 'current_ordinary_share', 'target_horizon': 'forward_12_months',
                             'individual_targets': rows}}

    def test_latest_selection_runs_only_after_newer_candidate_included(self):
        _, candidates = self.corpus_setup()
        request = self.analyst_request(candidates[:1])
        result = self.audit(request)
        self.assertIsNone(result['analysis'])
        self.assertEqual(result['status'], 'BLOCKED_INCOMPLETE_CORPUS')
        result = self.audit(self.analyst_request(candidates))
        self.assertEqual(result['analysis']['consensus']['mean'], 47)
        self.assertEqual(result['analysis']['individual_targets_used'][0]['record_id'], 'row-1')

    def test_analysis_row_set_and_excerpt_must_match_coverage(self):
        _, candidates = self.corpus_setup()
        request = self.analyst_request(candidates)
        request['analysis']['individual_targets'].pop()
        with self.assertRaisesRegex(ValueError, 'RECORD_SET_MISMATCH'):
            self.audit(request)
        request = self.analyst_request(candidates)
        request['analysis']['individual_targets'][1]['source']['verbatim_excerpt'] = 'Firm Cedar'
        with self.assertRaisesRegex(ValueError, 'OMITS_LINKED_CANDIDATE'):
            self.audit(request)

    def test_cli_decimal_targets_are_not_excluded_as_nonnumeric(self):
        _, candidates = self.corpus_setup()
        request = self.analyst_request(candidates)
        request['analysis']['individual_targets'][0]['target'] = 41.25
        request['analysis']['individual_targets'][1]['target'] = 47.75
        source = self.root / 'request.json'
        source.write_text(json.dumps(request))
        output = self.root / 'result.json'
        self.assertEqual(subject.main(['--manifest', str(self.manifest), '--manifest-sha256', self.pin,
                                       '--input', str(source), '--output', str(output)]), 0)
        report = json.loads(output.read_text())
        self.assertEqual(report['analysis']['consensus']['mean'], 47.75)

    def test_unrepresentable_downstream_decimal_is_rejected_not_rounded(self):
        _, candidates = self.corpus_setup()
        request = self.analyst_request(candidates)
        request['analysis']['individual_targets'][1]['target'] = Decimal('47.1234567890123456789')
        with self.assertRaisesRegex(ValueError, 'PRECISION_UNSUPPORTED'):
            self.audit(request)

    def test_cli_rejected_claim_retains_machine_report_and_nonzero_exit(self):
        self.ingress([('note', 'text', 'Common shares described')])
        request = self.root / 'request.json'
        request.write_text(json.dumps({'operation': 'presence', 'terms': ['common'], 'assert_claims': ['source_absent']}))
        output = self.root / 'report.json'
        argv = ['--manifest', str(self.manifest), '--manifest-sha256', self.pin,
                '--input', str(request), '--output', str(output)]
        self.assertEqual(subject.main(argv), 2)
        self.assertEqual(json.loads(output.read_text())['claim_verdict'], 'REJECTED')
        with self.assertRaises(FileExistsError):
            subject.main(argv)


if __name__ == '__main__':
    unittest.main()
