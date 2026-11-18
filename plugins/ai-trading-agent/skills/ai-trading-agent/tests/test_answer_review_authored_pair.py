"""Complete authored artifacts and original-text inputs; no semantic pass claims."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_answer_review as fixture
import answer_review as module


class AuthoredPairTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.AnswerReviewTests('test_real_mixed_delivery_positive_is_read_only_and_never_semantically_certified')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.root, self.doc, self.protocol = self.f.root, self.f.doc, self.f.protocol
        (self.root / 'request.txt').write_text('Check amount, currency and period.', encoding='utf8')
        self.protocol['original_request'] = self.f.ref('request.txt')
        raw = (self.root / 'request.txt').read_bytes()
        for row in self.protocol['units']:
            row['request_spans'] = [fixture.location(raw, row['id'].encode())]
        (self.root / 'authored.md').write_bytes((self.root / 'delivery/first-response.md').read_bytes())
        (self.root / 'authored.json').write_text('{"amount":12.75,"currency":"EUR","period":"2032-Q1"}', encoding='utf8')
        self.doc['delivery'] = {
            'kind':'authored_pair', 'first_response':self.f.ref('authored.md'),
            'response':self.f.ref('authored.json'), 'original_inputs':[self.f.ref('request.txt'),self.f.ref('original.json')],
            'captured_at':'2032-01-01T10:00:00Z'}
        self.f.adopt()

    def assess(self):
        return module.assess(self.doc, self.root, self.f.pin)

    def test_complete_free_text_authored_pair_is_bound_without_replay_or_semantic_claim(self):
        result = self.assess()
        self.assertEqual(result['status'], 'WITHIN_DECLARED_TOLERANCE')
        self.assertEqual(result['delivery_binding_kind'], 'authored_pair')
        self.assertFalse(result['generated_delivery_verifier_executed'])
        self.assertFalse(result['authored_pair_semantic_consistency_verified'])
        self.assertFalse(result['whole_answer_correctness_verified'])
        self.assertEqual(result['checked_artifacts']['authored.json'], self.f.ref('authored.json')['sha256'])

    def test_each_final_artifact_hash_drift_rejected(self):
        for name in ('authored.md','authored.json'):
            path = self.root/name; old=path.read_bytes();path.write_bytes(old+b' ')
            with self.assertRaisesRegex(ValueError,'ARTIFACT_HASH_MISMATCH'):self.assess()
            path.write_bytes(old)

    def test_source_omission_and_request_omission_rejected(self):
        original=copy.deepcopy(self.doc['delivery']['original_inputs'])
        for kept in (original[:1],original[1:]):
            self.doc['delivery']['original_inputs']=kept
            with self.assertRaisesRegex(ValueError,'REVIEW_SOURCE_NOT_IN_DELIVERED_CORPUS'):self.assess()
        self.doc['delivery']['original_inputs']=original

    def test_original_request_change_rejected(self):
        (self.root/'request.txt').write_text('Changed current question',encoding='utf8')
        with self.assertRaisesRegex(ValueError,'ARTIFACT_HASH_MISMATCH'):self.assess()

    def test_extra_or_duplicate_inputs_rejected(self):
        inputs=self.doc['delivery']['original_inputs']
        inputs.append(inputs[0])
        with self.assertRaisesRegex(ValueError,'DUPLICATE_ORIGINAL_INPUT'):self.assess()
        inputs.pop();(self.root/'extra.txt').write_text('unregistered',encoding='utf8');inputs.append(self.f.ref('extra.txt'))
        with self.assertRaisesRegex(ValueError,'AUTHORED_PAIR_EXACT_PROTOCOL_INPUTS_REQUIRED'):self.assess()

    def test_source_cannot_be_replaced_by_answer(self):
        self.doc['delivery']['first_response']=self.f.ref('request.txt')
        with self.assertRaisesRegex(ValueError,'ANSWER_CANNOT_REPLACE_ORIGINAL_INPUT'):self.assess()

    def test_distinct_outputs_required(self):
        self.doc['delivery']['first_response']=self.f.ref('authored.json')
        with self.assertRaisesRegex(ValueError,'DISTINCT_ANSWER_ARTIFACTS_REQUIRED'):self.assess()

    def test_invalid_response_schema_and_utf8_rejected(self):
        p=self.root/'authored.json'
        for raw in (b'[]',b'{}',b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff'):
            p.write_bytes(raw);self.doc['delivery']['response']=self.f.ref('authored.json')
            with self.subTest(raw=raw),self.assertRaises((ValueError,UnicodeError)):self.assess()

    def test_blank_or_invalid_markdown_rejected(self):
        p=self.root/'authored.md'
        for raw in (b' ',b'\xff'):
            p.write_bytes(raw);self.doc['delivery']['first_response']=self.f.ref('authored.md')
            with self.subTest(raw=raw),self.assertRaises(ValueError):self.assess()

    def test_negative_judgment_retained_not_blocked_or_relabelled(self):
        row=self.doc['reviews'][0];row.update(status='MATERIAL_ERROR',material_error=True,issues=['amount'])
        result=self.assess()
        self.assertEqual(result['status'],'REQUIRES_ESCALATION');self.assertEqual(result['material_error_units'],1)
        self.assertEqual(result['reviews'][0],row)

    def test_unsupported_source_and_omitted_unit_not_passing(self):
        self.doc['reviews'][0].update(status='UNREVIEWED',material_error=None,answer_spans=[])
        self.doc['reviews'][0]['source_reviews'][0].update(status='SUPPLIED_UNREVIEWED',spans=[])
        self.doc['reviews'].pop()
        result=self.assess();self.assertEqual(result['status'],'INCOMPLETE_DECLARED_REVIEW')
        self.assertIsNone(result['declared_material_error_tolerance_met'])

    def test_json_answer_spans_bound_independently(self):
        raw=(self.root/'authored.json').read_bytes()
        self.doc['reviews'][0]['answer_spans'].append({'artifact':'response','span':fixture.location(raw,b'12.75')})
        self.assertEqual(self.assess()['status'],'WITHIN_DECLARED_TOLERANCE')
        self.doc['reviews'][0]['answer_spans'][-1]['span']['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'BYTE_SPAN_HASH_MISMATCH'):self.assess()

if __name__=='__main__':unittest.main()
