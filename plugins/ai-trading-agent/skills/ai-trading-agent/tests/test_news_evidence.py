import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import news_evidence as ne


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = {
            'published_at': '2028-02-01T10:00:00Z', 'first_observed_at': '2028-02-01T10:01:00Z',
            'issuer': 'EXAMPLE', 'metric': 'revenue', 'period': 'FY2028', 'currency': 'EUR',
            'unit': 'million', 'accounting_basis': 'IFRS', 'low': 40, 'high': 60,
        }
        later = dict(self.raw, published_at='2028-02-02T10:00:00Z', first_observed_at='2028-02-02T10:01:00Z', low=45, high=65)
        self.request = {'as_of': '2028-02-03T00:00:00Z',
                        'previous': self.make('old', self.raw), 'current': self.make('new', later)}

    def make(self, name, data):
        path = self.root / (name + '.json')
        path.write_text(json.dumps(data), encoding='utf-8')
        return {'id': name, 'source': {'path': path.name, 'sha256': ne.digest(path.read_bytes())},
                'clocks': {'publication': {'kind': 'source', 'pointer': '/published_at'},
                           'observation': {'kind': 'source', 'pointer': '/first_observed_at'}},
                'fields': {k: {'kind': 'source', 'pointer': '/' + k}
                           for k in (*ne.DIMENSIONS, 'low', 'high', 'accounting_basis')}}

    def test_source_bound_comparable_ranges(self):
        out = ne.compare(self.request, self.root)
        self.assertEqual(out['comparison_status'], 'SOURCE_BOUND_DISCLOSURE_CHANGE')
        self.assertEqual(out['arithmetic']['midpoint_change_pct'], '10.0')
        self.assertEqual(out['arithmetic']['range_direction'], 'RAISED_RANGE')
        self.assertFalse(out['source_authenticity_verified'])

    def test_unknown_clocks_and_basis_keep_executable_arithmetic(self):
        for key in ['previous', 'current']:
            self.request[key]['clocks']['observation'] = {'kind': 'unknown'}
            self.request[key]['fields']['accounting_basis'] = {'kind': 'unknown'}
        out = ne.compare(self.request, self.root)
        self.assertEqual(out['comparison_status'], 'ARITHMETIC_ONLY')
        self.assertEqual(out['arithmetic']['midpoint_change'], '5')
        self.assertIsNone(out['records'][0]['clocks']['observation']['value'])
        self.assertIsNone(out['records'][0]['fields']['accounting_basis']['value'])

    def test_observation_is_not_publication(self):
        self.request['current']['clocks']['publication']['pointer'] = '/first_observed_at'
        with self.assertRaisesRegex(ValueError, 'CLOCK_ROLE'):
            ne.compare(self.request, self.root)

    def test_caller_override_cannot_replace_source_time(self):
        self.request['current']['clocks']['publication']['value'] = self.request['as_of']
        with self.assertRaisesRegex(ValueError, 'CLOCK_VALUE_DIFFERS'):
            ne.compare(self.request, self.root)

    def test_late_observed_revision_retains_equal_publication(self):
        revised = dict(self.raw, first_observed_at='2028-02-02T11:00:00Z', low=42, high=62)
        self.request['current'] = self.make('revision', revised)
        out = ne.compare(self.request, self.root)
        self.assertEqual(out['publication_order'], 'SAME_PUBLICATION')
        self.assertEqual(out['comparison_status'], 'ARITHMETIC_ONLY')
        self.assertEqual(out['arithmetic']['midpoint_change'], '2')
        self.assertEqual(out['records'][1]['clocks']['publication']['value'], self.raw['published_at'])

    def test_unknown_or_assumed_clock_is_never_promoted(self):
        for kind in ['unknown', 'assumption']:
            spec = {'kind': kind}
            if kind == 'assumption':
                spec.update(value=self.request['as_of'], reason='Declared fictional availability convention')
            self.request['current']['clocks']['observation'] = spec
            out = ne.compare(self.request, self.root)
            self.assertEqual(out['comparison_status'], 'ARITHMETIC_ONLY')
            self.assertEqual(out['records'][1]['clocks']['observation']['kind'], kind)

    def test_declared_basis_not_evidence(self):
        self.request['current']['fields']['accounting_basis'] = {'kind': 'declared', 'value': 'IFRS', 'reason': 'Sensitivity only'}
        self.assertEqual(ne.compare(self.request, self.root)['comparison_status'], 'ARITHMETIC_ONLY')

    def test_source_basis_requires_same_metric_object(self):
        data = dict(self.raw, other={'metric': 'operating margin', 'accounting_basis': 'IFRS'})
        self.request['previous'] = self.make('othermetric', data)
        self.request['previous']['fields']['accounting_basis']['pointer'] = '/other/accounting_basis'
        with self.assertRaisesRegex(ValueError, 'BASIS_METRIC_SCOPE'):
            ne.compare(self.request, self.root)

    def test_lexical_basis_cannot_migrate_from_margin_to_revenue(self):
        raw = b'Forecast revenue 90 to 100 million. IFRS operating margin is 9 percent.'
        spec = {'kind': 'source_phrase', 'span': [0, len(raw)], 'value': 'IFRS'}
        with self.assertRaisesRegex(ValueError, 'BASIS_PHRASE_DOES_NOT_BIND'):
            ne.basis(raw, spec, 'revenue')
        self.assertEqual(ne.basis(raw, spec, 'operating margin')['value'], 'IFRS')

    def test_supported_basis_phrases_and_original_text_spans(self):
        for text in ['FY2028 IFRS revenue guidance is 40 to 60 million.',
                     'FY2028 revenue guidance is EUR 40 to 60 million on a IFRS basis.']:
            spec = {'kind': 'source_phrase', 'span': [0, len(text)], 'value': 'IFRS'}
            self.assertEqual(ne.basis(text.encode(), spec, 'revenue')['kind'], 'source')
        doc = json.dumps({'body': 'revenue 40 to 60 million'}).encode()
        self.assertEqual(ne.field(doc, {'kind': 'source', 'pointer': '/body', 'span': [8, 10]})['value'], '40')

    def test_known_future_publication_excluded_despite_early_observation(self):
        future = dict(self.raw, published_at='2028-02-04T00:00:00Z', first_observed_at='2028-02-02T00:00:00Z')
        self.request['current'] = self.make('future', future)
        out = ne.compare(self.request, self.root)
        self.assertEqual(out['comparison_status'], 'EXCLUDED_AT_CUTOFF')
        self.assertIsNone(out['arithmetic'])

    def test_changed_dimensions_do_not_get_numeric_comparison(self):
        self.request['current'] = self.make('otherbasis', dict(self.raw, accounting_basis='adjusted'))
        out = ne.compare(self.request, self.root)
        self.assertEqual(out['comparison_status'], 'NOT_COMPARABLE')
        self.assertIsNone(out['arithmetic'])

    def test_invalid_numeric_source_not_fixed_by_declared_override(self):
        for value in [True, 'NaN', 'Infinity']:
            self.request['current'] = self.make('badnum', dict(self.raw, low=value))
            with self.assertRaises(ValueError):
                ne.compare(self.request, self.root)
        self.request['current'] = self.make('num', self.raw)
        self.request['current']['fields']['low']['value'] = 41
        with self.assertRaisesRegex(ValueError, 'DIFFERS_FROM_SOURCE'):
            ne.compare(self.request, self.root)

    def test_file_tampering_and_parent_escape_rejected(self):
        (self.root / 'old.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'):
            ne.compare(self.request, self.root)
        self.request['previous']['source']['path'] = '../old.json'
        with self.assertRaisesRegex(ValueError, 'UNSAFE_SOURCE_PATH'):
            ne.compare(self.request, self.root)

    def test_text_clock_labels_preserve_roles_and_unknowns(self):
        raw = b'Published: 2028-02-01T10:00:00Z\r\nFirst observed: 2028-02-02T11:00:00Z\r\n'
        self.assertEqual(ne.clock(raw, {'kind': 'source', 'label': 'Published'}, 'publication')['value'], '2028-02-01T10:00:00Z')
        with self.assertRaisesRegex(ValueError, 'ROLE_BINDING'):
            ne.clock(raw, {'kind': 'source', 'label': 'First observed'}, 'publication')
        with self.assertRaisesRegex(ValueError, 'AMBIGUOUS'):
            ne.clock(raw + raw, {'kind': 'source', 'label': 'Published'}, 'publication')

    def test_same_instant_different_offsets_not_new_publication(self):
        self.request['current'] = self.make('offset', dict(self.raw, published_at='2028-02-01T11:00:00+01:00'))
        self.assertEqual(ne.compare(self.request, self.root)['publication_order'], 'SAME_PUBLICATION')

    def test_output_claim_requires_actual_emitted_label(self):
        output = {'method': 'fixture-helper', 'records': [{'review_events': ['REVIEW'], 'count': 1}]}
        path = self.root / 'output.json'; path.write_text(json.dumps(output))
        request = {'output': {'path': path.name, 'sha256': ne.digest(path.read_bytes())}, 'claims': [
            {'id': 'present', 'pointer': '/records/0/review_events', 'relation': 'contains', 'value': 'REVIEW'},
            {'id': 'invented', 'pointer': '/records/0/review_events', 'relation': 'contains', 'value': 'WITHDRAWAL_HINT'},
            {'id': 'missing', 'pointer': '/records/1/review_events', 'value': []},
            {'id': 'bool-is-not-one', 'pointer': '/records/0/count', 'value': True},
        ]}
        result = ne.audit_claims(request, self.root)
        self.assertEqual(result['status'], 'CLAIM_MISMATCH')
        self.assertEqual([r['supported'] for r in result['claims']], [True, False, False, False])
        self.assertEqual(result['claims'][1]['actual'], ['REVIEW'])

    def test_cli_compare_and_audit_preserve_existing_output(self):
        module = Path(ne.__file__)
        req = self.root / 'request.json';req.write_text(json.dumps(self.request))
        out = self.root / 'result.json'
        cmd = [sys.executable, '-B', str(module), 'compare', str(req), str(self.root), str(out)]
        done = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        before = out.read_bytes()
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertEqual(before, out.read_bytes())
        audit = {'output': {'path': out.name, 'sha256': ne.digest(before)}, 'claims': [
            {'id': 'range', 'pointer': '/arithmetic/range_direction', 'value': 'RAISED_RANGE'}]}
        req2 = self.root / 'audit.json';req2.write_text(json.dumps(audit))
        done = subprocess.run([sys.executable, '-B', str(module), 'audit', str(req2), str(self.root), str(self.root/'audit-result.json')], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['status'], 'PASS')

    def test_duplicate_json_keys_and_invalid_pointer_fail(self):
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_JSON_KEY'):
            ne.decode(b'{"x":1,"x":2}')
        with self.assertRaisesRegex(ValueError, 'INVALID_POINTER_ESCAPE'):
            ne.pointer({}, '/~2')

    def test_original_archive_record_scope_preserves_clock_role(self):
        archive = self.root / 'archive.json'
        archive.write_text(json.dumps({'documents': [self.raw, dict(self.raw, published_at='2028-02-02T10:00:00Z')]}))
        request = copy.deepcopy(self.request)
        request['previous']['source'] = {'path': archive.name, 'sha256': ne.digest(archive.read_bytes()), 'record_pointer': '/documents/0'}
        request['current']['source'] = dict(request['previous']['source'], record_pointer='/documents/1')
        before = json.dumps(request, sort_keys=True)
        result = ne.compare(request, self.root)
        self.assertEqual(result['publication_order'], 'LATER_DISCLOSURE')
        self.assertEqual(result['records'][0]['source']['record_pointer'], '/documents/0')
        self.assertEqual(json.dumps(request, sort_keys=True), before)
        request['current']['clocks']['publication']['pointer'] = '/documents/0/published_at'
        with self.assertRaises(KeyError):
            ne.compare(request, self.root)

    def test_empty_claim_list_never_produces_vacuous_pass(self):
        out = self.root / 'out.json';out.write_text('{"method":"fixture"}')
        ref = {'path': out.name, 'sha256': ne.digest(out.read_bytes())}
        with self.assertRaisesRegex(ValueError, 'NONEMPTY_CLAIMS'):
            ne.audit_claims({'output': ref, 'claims': []}, self.root)
        claim = {'id': 'duplicate', 'pointer': '/method', 'value': 'fixture'}
        with self.assertRaisesRegex(ValueError, 'UNIQUE_CLAIM_IDS'):
            ne.audit_claims({'output': ref, 'claims': [claim, claim]}, self.root)

    def test_negated_compound_and_clipped_basis_not_promoted(self):
        for phrase in ['Non-GAAP revenue guidance is EUR 12 to 14 million.',
                       'Not GAAP revenue guidance is EUR 12 to 14 million.',
                       'non IFRS revenue guidance is 12 to 14 million.',
                       'This is not reported as GAAP revenue.',
                       'GAAP revenue is not the reported basis.']:
            basis = 'IFRS' if 'IFRS' in phrase else 'GAAP'
            for start in [0, phrase.index(basis)]:
                with self.subTest(phrase=phrase, start=start):
                    with self.assertRaisesRegex(ValueError, 'BASIS_PHRASE'):
                        ne.basis(phrase.encode(), {'kind':'source_phrase','span':[start,len(phrase)],'value':basis}, 'revenue')
        for basis in ['non-GAAP', 'adjusted', 'IFRS']:
            phrase = basis + ' revenue guidance is EUR 12 to 14 million.'
            self.assertEqual(ne.basis(phrase.encode(), {'kind':'source_phrase','span':[0,len(phrase)],'value':basis}, 'revenue')['value'], basis)

    def test_decimal_source_token_above_binary_integer_precision_preserved(self):
        self.assertEqual(ne.field(b'{"low":9007199254740993.0}', {'kind':'source','pointer':'/low'})['value'], '9007199254740993.0')
        for side, val in [('previous','9007199254740993.0'),('current','9007199254740994.0')]:
            path=self.root/(side+'.json')
            data=dict(self.raw)
            data['published_at']='2028-02-01T10:00:00Z' if side=='previous' else '2028-02-02T10:00:00Z'
            data['first_observed_at']='2028-02-02T12:00:00Z'
            text=json.dumps(data).replace('"low": 40','"low": '+val).replace('"high": 60','"high": '+val)
            path.write_text(text)
            self.request[side]['source']={'path':path.name,'sha256':ne.digest(path.read_bytes())}
        out=ne.compare(self.request,self.root)
        self.assertEqual(out['arithmetic']['midpoint_change'],'1.0')
        self.assertEqual(out['arithmetic']['previous_midpoint'],'9007199254740993.0')

    def test_precision_outside_contract_rejected_not_rounded(self):
        for value in ['1e40', '1000000000000000000000001', '1e-25']:
            with self.assertRaisesRegex(ValueError,'NUMERIC_PRECISION_OUTSIDE'):
                ne.number(value)

    def test_claim_audit_does_not_round_large_decimal_output(self):
        p=self.root/'large.json';p.write_text('{"method":"fixture","value":9007199254740993.0}')
        req={'output':{'path':p.name,'sha256':ne.digest(p.read_bytes())},'claims':[{'id':'rounded','pointer':'/value','value':9007199254740992.0}]}
        self.assertEqual(ne.audit_claims(req,self.root)['status'],'CLAIM_MISMATCH')

    def test_equal_decimal_override_preserves_number_vs_string_types(self):
        self.assertEqual(ne.field(b'{"low":1.1}', {'kind':'source','pointer':'/low','value':1.1})['value'],'1.1')
        with self.assertRaisesRegex(ValueError,'FIELD_VALUE_DIFFERS'):
            ne.field(b'{"low":"1.1"}', {'kind':'source','pointer':'/low','value':1.1})

    def test_scoped_decimal_record_keeps_exact_type_for_override(self):
        doc={'documents':[dict(self.raw,low=1.1,high=2.1)]}
        p=self.root/'scoped.json';p.write_text(json.dumps(doc))
        item=copy.deepcopy(self.request['previous'])
        item['source']={'path':p.name,'sha256':ne.digest(p.read_bytes()),'record_pointer':'/documents/0'}
        item['fields']['low']['value']=1.1
        self.assertEqual(ne.record(item,self.root)['fields']['low']['value'],'1.1')


if __name__ == '__main__':
    unittest.main()
