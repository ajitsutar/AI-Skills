"""Original-object delivery: source scope, missing meaning and separate annexes."""
from copy import deepcopy
import hashlib
import json
from decimal import Decimal
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import request_coverage as module
import test_request_coverage as category_tests


class RequestObjectCoverageTests(unittest.TestCase):
    # Reuse artifact construction, not tests or their category assumptions.
    compose = category_tests.RequestCoverageTests.compose
    response = category_tests.RequestCoverageTests.response
    add_annex = category_tests.RequestCoverageTests.add_annex

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='object-coverage-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = {'purpose': 'Review the supplied maintenance record and its limits.',
            'supporting_file': 'notes/context.json', 'requested_work': ['review observations'],
            'restrictions': {'network': False, 'scope': 'supplied only'}}
        self.context = {'maintenance': {'temperature': 18.25, 'unit': 'C', 'last_verified': None},
            'availability': False, 'remaining_units': 0, 'future_plan': None,
            'unusual/key~name': {'common_note': 'A common retained observation.'}}
        self.manifest = self.root / 'ingress.json'
        self.plan_path = self.root / 'plan.json'; self.output = self.root / 'delivery'
        self.write_sources()
        self.plan = {'kind': 'ORIGINAL_OBJECTS', 'request_ref': {'source_id': 'req', 'pointer': ''},
            'contexts': [{'id': 'supporting-context', 'link_pointer': '/supporting_file', 'source_id': 'ctx'}],
            'rows': [self.row(sid, key) for sid, value in [('req', self.original), ('ctx', self.context)] for key in value]}

    def write_sources(self):
        sources = []
        for sid, name, value in [('req', 'original/request.json', self.original),
                                  ('ctx', 'original/notes/context.json', self.context),
                                  ('other', 'unselected.json', {'common': 'Independent retained context.'})]:
            raw = json.dumps(value).encode(); path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
            sources.append({'id': sid, 'path': name, 'format': 'json', 'sha256': hashlib.sha256(raw).hexdigest()})
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': sources}))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def row(self, sid, key):
        return {'source_ref': {'source_id': sid, 'pointer': module.member_pointer(key)},
            'disposition': 'AUTHORED_ANALYSIS',
            'meaning': 'This retained member describes only the supplied observation and its declared scope.',
            'limitations': ['The declaration is not independently authenticated; relevance requires review.'],
            'evidence_refs': [], 'supporting_annex_ids': []}

    def test_full_original_objects_unknown_types_order_and_no_input_mutation(self):
        before = (self.root / 'original/notes/context.json').read_bytes()
        self.plan['rows'].reverse(); self.compose(); result = self.response()
        self.assertEqual(result['status'], 'ORIGINAL_OBJECT_MEMBER_ROWS_PRESENT')
        self.assertEqual(result['original_request']['original_value'], self.original)
        self.assertEqual(result['original_contexts'][0]['original_value'], self.context)
        actual = {r['source_ref']['pointer']: r['original_value'] for r in result['rows'] if r['source_ref']['source_id'] == 'ctx'}
        self.assertIs(actual['/availability'], False)
        self.assertIsNone(actual['/future_plan'])
        self.assertIs(type(actual['/remaining_units']), int)
        self.assertEqual(actual['/remaining_units'], 0)
        self.assertEqual(actual['/unusual~1key~0name'], self.context['unusual/key~name'])
        self.assertEqual(result['coverage']['represented_members'], len(self.original) + len(self.context))
        self.assertEqual(result['rows'][0]['source_ref'], {'source_id': 'req', 'pointer': '/purpose'})
        self.assertEqual(before, (self.root / 'original/notes/context.json').read_bytes())
        self.assertFalse(result['request_correctness_verified'])
        self.assertFalse(result['coverage']['nested_meaning_completeness_verified'])

    def test_missing_original_member_retains_failure_without_complete_response(self):
        self.plan['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_ORIGINAL_OBJECT_MEMBERS'): self.compose()
        self.assertTrue((self.output / 'failure.json').exists())
        self.assertFalse((self.output / 'first-response.md').exists())
        self.assertFalse((self.output / 'receipt.json').exists())

    def test_new_original_member_cannot_be_hidden_by_an_old_plan(self):
        self.context['new_scope'] = {'uncertain': None}; self.write_sources()
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_ORIGINAL_OBJECT_MEMBERS'): self.compose()

    def test_duplicate_member_does_not_replace_an_omission(self):
        self.plan['rows'][-1] = deepcopy(self.plan['rows'][0])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_OBJECT_MEMBER_ROW'): self.compose()

    def test_partial_nested_member_is_not_complete_member(self):
        self.plan['rows'][-1]['source_ref']['pointer'] += '/common_note'
        with self.assertRaisesRegex(ValueError, 'UNREQUESTED_OR_PARTIAL_OBJECT_MEMBER'): self.compose()

    def test_absent_linked_context_cannot_be_silently_dropped(self):
        self.plan['contexts'] = []
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_ORIGINAL_CONTEXT_OBJECTS'): self.compose()

    def test_wrong_context_source_pointer_or_request_subset_rejected(self):
        for change in ('source', 'link', 'subset', 'duplicate', 'invented_inventory'):
            plan = deepcopy(self.plan)
            if change == 'source': plan['contexts'][0]['source_id'] = 'other'
            elif change == 'link': plan['contexts'][0]['link_pointer'] = '/requested_work'
            elif change == 'subset': plan['request_ref']['pointer'] = '/restrictions'
            elif change == 'duplicate': plan['contexts'].append(deepcopy(plan['contexts'][0]))
            else: plan['member_inventory'] = []
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.assemble(module.validate_plan(plan), module.Corpus(self.manifest, self.pin, self.root), self.root / 'none')

    def test_changed_or_unsafe_original_link_rejected(self):
        for value in ('notes/missing.json', '../outside.json', 'C:/elsewhere.json'):
            self.original['supporting_file'] = value; self.write_sources()
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.assemble(module.validate_plan(self.plan), module.Corpus(self.manifest, self.pin, self.root), self.root / 'none')

    def test_empty_meaning_limits_and_unsupported_disposition_rejected(self):
        for key, value in [('meaning', '  '), ('limitations', []), ('limitations', ['']),
                           ('disposition', 'SKIPPED'), ('evidence_refs', [{'source_id': 'ctx', 'pointer': '/absent'}]),
                           ('supporting_annex_ids', ['missing'])]:
            plan = deepcopy(self.plan); plan['rows'][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                module.assemble(module.validate_plan(plan), module.Corpus(self.manifest, self.pin, self.root), self.root / 'none')

    def test_annex_disposition_needs_an_actual_checked_annex(self):
        self.plan['rows'][0]['disposition'] = 'SUPPORTED_ANNEX'
        with self.assertRaisesRegex(ValueError, 'SUPPORTED_ANNEX_REFERENCE_REQUIRED'): self.compose()

    def test_complete_mixed_answer_with_portable_canonical_annex_and_own_hash(self):
        self.add_annex(canonical=True)
        self.plan['rows'][0]['disposition'] = 'SUPPORTED_ANNEX'
        self.compose(); result = self.response()
        self.assertEqual(result['annexes'][0]['status'], 'ANNEX_CONTRACT_REPLAYED_ONLY')
        self.assertFalse(result['rows'][0]['annex_relevance_verified'])
        self.assertNotEqual(result['first_response_sha256'], result['annexes'][0]['first_response_sha256'])
        moved = self.root / 'moved'; shutil.copytree(self.output, moved); module.verify(moved)
        first = moved / 'annexes/supported-annex/report/first-response.md'
        first.write_bytes(first.read_bytes() + b'\nChanged annex.\n')
        with self.assertRaises(ValueError): module.verify(moved)

    def test_changed_source_hash_blocks_delivery_even_when_unselected(self):
        (self.root / 'unselected.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.compose()

    def test_changed_output_or_retained_source_cannot_verify(self):
        self.compose()
        published = self.root / 'published.md'
        published.write_bytes((self.output / 'first-response.md').read_bytes() + b'\nAll facts verified.\n')
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_BRIEFING_DIFFERS'): module.verify(self.output, published)
        response = self.response(); response['rows'][-1]['authored_content_status'] = 'VERIFIED'
        changed = self.root / 'published.json'; changed.write_text(json.dumps(response))
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_DELIVERY_RESPONSE_DIFFERS'): module.verify(self.output, published_response=changed)
        (self.output / 'originals/original/notes/context.json').write_text('{}')
        with self.assertRaises(ValueError): module.verify(self.output)

    def test_irrelevant_meaning_and_nonanalytical_rationale_never_become_semantic_pass(self):
        self.plan['rows'][-1]['disposition'] = 'NON_ANALYTICAL_CONTEXT'
        self.plan['rows'][-1]['meaning'] = 'An unsupported relevance assertion, deliberately not graded by this helper.'
        self.compose(); result = self.response()
        self.assertFalse(result['coverage']['semantic_completeness_verified'])
        self.assertFalse(result['request_correctness_verified'])
        self.assertEqual(result['rows'][-1]['authored_content_status'], 'SEMANTICALLY_UNVERIFIED')
        self.assertIn('not proof', (self.output / 'first-response.md').read_text(encoding='utf8'))

    def test_renamed_context_links_and_multiple_links_keep_exact_inventory(self):
        self.original['renamed-reference'] = self.original.pop('supporting_file')
        self.original['second-reference'] = 'notes/context.json'
        self.plan['contexts'] = [{'id': 'one', 'link_pointer': '/renamed-reference', 'source_id': 'ctx'},
                                 {'id': 'two', 'link_pointer': '/second-reference', 'source_id': 'ctx'}]
        self.plan['rows'] = [self.row(sid, key) for sid, obj in [('req', self.original), ('ctx', self.context)] for key in obj]
        self.write_sources(); self.compose(); result = self.response()
        self.assertEqual(len(result['original_contexts']), 2)
        self.assertEqual(len(result['rows']), len(self.original) + len(self.context))

    def numeric_sources(self):
        # Literal independent source tokens: never construct them through float.
        values = '[1e-410,-1e-410,1e410,-1e410,0.234567890123456789012345678901,900719925474099312345678901,-0,-0.00,0,0.0,1E+00,7.5000,"1e-410",null,false]'
        request_raw = ('{"purpose":"Review exact supplied measurements.","supporting_file":"notes/context.json",'
                       '"root_number":1e-410,"nested":{"values":' + values + '}}').encode()
        context_raw = ('{"measurements":' + values + ',"detail":{"nested":[{"value":1e410}]},'
                       '"precision":0.234567890123456789012345678901}').encode()
        self.original = json.loads(request_raw, parse_float=str, parse_int=str)
        self.context = json.loads(context_raw, parse_float=str, parse_int=str)
        self.plan['rows'] = [self.row(sid, key) for sid, obj in [('req', self.original), ('ctx', self.context)] for key in obj]
        self.plan['rows'][0]['evidence_refs'] = [
            {'source_id': 'ctx', 'pointer': '/measurements'}, {'source_id': 'req', 'pointer': '/root_number'},
            {'source_id': 'ctx', 'pointer': '/precision'}, {'source_id': 'ctx', 'pointer': '/detail/nested/0/value'}]
        manifest = json.loads(self.manifest.read_bytes())
        for sid, raw in [('req', request_raw), ('ctx', context_raw)]:
            entry = next(row for row in manifest['sources'] if row['id'] == sid)
            (self.root / entry['path']).write_bytes(raw); entry['sha256'] = hashlib.sha256(raw).hexdigest()
        self.manifest.write_text(json.dumps(manifest)); self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
        return request_raw, context_raw

    @staticmethod
    def number_tokens(raw):
        # Independent decoder observes output lexemes instead of coercing floats.
        return json.loads(raw, parse_int=lambda value: ('JSON_NUMBER', value),
                          parse_float=lambda value: ('JSON_NUMBER', value))

    def test_exact_numeric_tokens_at_every_original_binding_and_readable_projection(self):
        request_raw, context_raw = self.numeric_sources(); self.compose()
        response_raw = (self.output / 'response.json').read_bytes()
        response = self.number_tokens(response_raw)
        expected_request, expected_context = self.number_tokens(request_raw), self.number_tokens(context_raw)
        self.assertEqual(response['original_request']['original_value'], expected_request)
        self.assertEqual(response['original_contexts'][0]['original_value'], expected_context)
        rows = {(row['source_ref']['source_id'], row['source_ref']['pointer']): row for row in response['rows']}
        self.assertEqual(rows['req', '/root_number']['original_value'], ('JSON_NUMBER', '1e-410'))
        self.assertEqual(rows['req', '/nested']['original_value'], expected_request['nested'])
        self.assertEqual(rows['ctx', '/measurements']['original_value'], expected_context['measurements'])
        evidence = rows['req', '/purpose']['supporting_original_evidence']
        self.assertEqual(evidence[0]['original_value'], expected_context['measurements'])
        self.assertEqual(evidence[1]['original_value'], ('JSON_NUMBER', '1e-410'))
        self.assertEqual(evidence[2]['original_value'], ('JSON_NUMBER', '0.234567890123456789012345678901'))
        self.assertEqual(evidence[3]['original_value'], ('JSON_NUMBER', '1e410'))
        numbers = json.loads(response_raw, parse_float=Decimal)['original_contexts'][0]['original_value']['measurements']
        self.assertGreater(numbers[0], 0); self.assertLess(numbers[1], 0)
        self.assertTrue(numbers[2].is_finite()); self.assertTrue(numbers[3].is_finite())
        self.assertEqual(numbers[4], Decimal('0.234567890123456789012345678901'))
        self.assertEqual(numbers[5], 900719925474099312345678901)
        self.assertEqual(expected_context['measurements'][6:12], [
            ('JSON_NUMBER', '-0'), ('JSON_NUMBER', '-0.00'), ('JSON_NUMBER', '0'),
            ('JSON_NUMBER', '0.0'), ('JSON_NUMBER', '1E+00'), ('JSON_NUMBER', '7.5000')])
        self.assertIsInstance(expected_context['measurements'][12], str)
        self.assertIsNone(expected_context['measurements'][13]); self.assertIs(expected_context['measurements'][14], False)
        text = (self.output / 'first-response.md').read_text(encoding='utf8')
        blocks = [text.split('```json\n')[i].split('\n```', 1)[0] for i in range(1, text.count('```json\n') + 1)]
        readable = self.number_tokens(blocks[0])
        self.assertEqual(readable['request']['original_value'], expected_request)
        self.assertEqual(readable['contexts'][0]['original_value'], expected_context)
        self.assertEqual((self.root / 'original/request.json').read_bytes(), request_raw)

    def test_exact_numbers_relocate_and_reject_changed_published_number_or_original(self):
        self.numeric_sources(); self.compose()
        moved = self.root / 'relocated'; shutil.copytree(self.output, moved)
        module.verify(moved, moved / 'first-response.md', moved / 'response.json')
        original = (moved / 'response.json').read_bytes(); self.assertIn(b'1e-410', original)
        changed = self.root / 'changed-number.json'; changed.write_bytes(original.replace(b'1e-410', b'0.0', 1))
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_DELIVERY_RESPONSE_DIFFERS'):
            module.verify(moved, published_response=changed)
        original = moved / 'originals/original/notes/context.json'
        original.write_bytes(original.read_bytes().replace(b'1e410', b'1e409', 1))
        with self.assertRaises(ValueError): module.verify(moved)

    def test_duplicate_keys_and_nonfinite_originals_cannot_complete(self):
        for index, raw in enumerate((b'{"value":1,"value":2}', b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}')):
            self.write_sources(); self.output = self.root / ('invalid-' + str(index))
            path = self.root / 'original/notes/context.json'; path.write_bytes(raw)
            manifest = json.loads(self.manifest.read_bytes())
            next(row for row in manifest['sources'] if row['id'] == 'ctx')['sha256'] = hashlib.sha256(raw).hexdigest()
            self.manifest.write_text(json.dumps(manifest)); self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()
            with self.subTest(raw=raw), self.assertRaises(ValueError): self.compose()
            self.assertFalse((self.output / 'receipt.json').exists())
            self.assertFalse((self.output / 'first-response.md').exists())

    def test_object_encoder_rejects_unapproved_values_and_depth_before_receipt(self):
        for value in (1.5, float('inf'), Decimal('1.25'), module._OriginalNumber('Infinity'), module._OriginalNumber('01')):
            with self.subTest(value=value), self.assertRaises(ValueError): module.encode_objects(value)
        from unittest.mock import patch
        with patch.object(module, 'MAX_OBJECT_DEPTH', 2):
            with self.assertRaisesRegex(ValueError, 'EXACT_OBJECT_DEPTH_EXCEEDED'): self.compose()
        self.assertFalse((self.output / 'receipt.json').exists())
        self.assertFalse((self.output / 'first-response.md').exists())

    def test_numeric_like_strings_and_json_escapes_remain_strings(self):
        self.context = {'text': '1e410', 'quoted': '"value":1e-410', 'line': 'a\nb', 'slash': '\\', 'unicode': '\u2603'}
        self.plan['rows'] = [self.row(sid, key) for sid, obj in [('req', self.original), ('ctx', self.context)] for key in obj]
        self.write_sources(); self.compose()
        self.assertEqual(self.response()['original_contexts'][0]['original_value'], self.context)

    def test_output_bound_does_not_create_success_for_truncated_numbers(self):
        from unittest.mock import patch
        with patch.object(module.source, 'MAX_FILE', 8):
            with self.assertRaisesRegex(ValueError, 'EXACT_OBJECT_OUTPUT_TOO_LARGE'):
                module.encode_objects(module._OriginalNumber('123456789'))


if __name__ == '__main__':
    unittest.main()
