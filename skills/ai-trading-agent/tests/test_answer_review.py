"""Real delivered-answer binding and declared-review boundaries; synthetic only."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import answer_review as module
import test_request_coverage as fixture


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def location(raw, needle=None):
    needle = raw[:10] if needle is None else needle
    start = raw.index(needle)
    return {'start_byte': start, 'end_byte': start + len(needle), 'sha256': sha(needle)}


class AnswerReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.RequestCoverageTests('test_complete_authored_delivery_without_compositor_or_annex')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.root = f.root.resolve()
        f.input['request']['review_request'] = 'Check amount, currency and period; preserve unknowns and relevant alternatives.'
        f.input['observation'].update(currency='EUR', period='2032-Q1')
        f.write_sources(); f.compose()
        self.original = (self.root / 'original.json').read_bytes()
        self.protocol = {'schema_version': 1, 'id': 'synthetic-review', 'adopted_at': '2032-01-01T09:00:00Z',
            'original_request': self.ref('original.json'), 'sources': [{'id': 'supplied', 'artifact': self.ref('original.json')}],
            'units': [{'id': uid, 'requirement': 'Check the supplied ' + uid,
                       'request_spans': [location(self.original, uid.encode())], 'required_source_ids': ['supplied']}
                      for uid in ('amount', 'currency', 'period')], 'max_material_error_units': 0}
        self.doc = {'schema_version': 1, 'protocol': {}, 'reviewed_at': '2032-01-01T10:02:00Z',
            'reviewer': {'id': 'synthetic-evaluator', 'kind': 'automated'},
            'delivery': self.delivery('delivery', 'request_coverage'), 'reviews': []}
        first = (self.root / 'delivery/first-response.md').read_bytes()
        for uid, needle in [('amount', b'12.75'), ('currency', b'EUR'), ('period', b'2032-Q1')]:
            self.doc['reviews'].append({'unit_id': uid, 'status': 'SATISFIED', 'material_error': False,
                'issues': [], 'rationale': 'Synthetic declared judgment; the checker does not grade it.',
                'answer_spans': [{'artifact': 'first_response', 'span': location(first, needle)}],
                'source_reviews': [{'source_id': 'supplied', 'status': 'REVIEWED',
                                    'spans': [location(self.original, needle)]}]})
        self.adopt()

    def ref(self, name):
        return {'path': name, 'sha256': sha((self.root / name).read_bytes())}

    def delivery(self, name, kind):
        first = 'report/first-response.md' if kind == 'canonical_response' else 'first-response.md'
        return {'kind': kind, 'directory': name, 'receipt_sha256': self.ref(name + '/receipt.json')['sha256'],
                'first_response_sha256': self.ref(name + '/' + first)['sha256'],
                'response_sha256': self.ref(name + '/response.json')['sha256'], 'captured_at': '2032-01-01T10:00:00Z'}

    def adopt(self):
        path = self.root / 'review-protocol.json'
        path.write_text(json.dumps(self.protocol), encoding='utf8')
        self.doc['protocol'] = self.ref(path.name)
        self.pin = self.doc['protocol']['sha256']

    def assess(self):
        return module.assess(self.doc, self.root, self.pin)

    def test_real_mixed_delivery_positive_is_read_only_and_never_semantically_certified(self):
        before = {p.relative_to(self.root).as_posix(): sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()}
        result = self.assess()
        self.assertEqual(result['status'], 'WITHIN_DECLARED_TOLERANCE')
        self.assertEqual(result['material_error_units'], 0)
        self.assertTrue(result['declared_material_error_tolerance_met'])
        self.assertEqual(result['status_counts']['SATISFIED'], 3)
        for key in ['whole_answer_correctness_verified', 'request_semantic_completeness_verified',
                    'source_authenticity_verified', 'source_absence_established', 'execution_authorized',
                    'human_activity_authenticated', 'capture_clocks_authenticated']:
            self.assertFalse(result[key])
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): sha(p.read_bytes()) for p in self.root.rglob('*') if p.is_file()})

    def test_actual_canonical_response_replay_works_without_authored_claim_overrides(self):
        directory = self.fixture.add_annex(canonical=True)
        self.doc['delivery'] = self.delivery(directory.name, 'canonical_response')
        raw = (directory / 'report/first-response.md').read_bytes()
        for row in self.doc['reviews']:
            row['answer_spans'] = [{'artifact': 'first_response', 'span': location(raw)}]
        result = self.assess()
        self.assertEqual(result['status'], 'WITHIN_DECLARED_TOLERANCE')
        self.assertTrue(result['semantic_judgments_are_reviewer_declarations'])
        self.assertFalse(result['whole_answer_correctness_verified'])

    def test_currency_period_amount_errors_are_retained_counted_once_and_exceed_tolerance(self):
        for row in self.doc['reviews']:
            row.update(status='MATERIAL_ERROR', material_error=True, issues=[row['unit_id'], 'attribution'])
        result = self.assess()
        self.assertEqual(result['status'], 'REQUIRES_ESCALATION')
        self.assertEqual(result['material_error_units'], 3)
        self.assertFalse(result['declared_material_error_tolerance_met'])
        self.assertEqual(result['reviews'], self.doc['reviews'])
        self.protocol['max_material_error_units'] = 3; self.adopt()
        result = self.assess()
        self.assertEqual(result['status'], 'WITHIN_DECLARED_TOLERANCE')
        self.assertEqual(result['material_error_units'], 3)
        self.assertFalse(result['whole_answer_correctness_verified'])

    def test_omitted_and_unsupported_can_be_material_errors_and_never_favorable_zeros(self):
        for status in ('OMITTED', 'UNSUPPORTED'):
            with self.subTest(status=status):
                row = self.doc['reviews'][0]
                row.update(status=status, material_error=True, issues=['omitted_alternative'])
                result = self.assess()
                self.assertEqual(result['material_error_units'], 1)
                self.assertFalse(result['declared_material_error_tolerance_met'])
                self.assertEqual(result['status'], 'REQUIRES_ESCALATION')
                row['material_error'] = False
                result = self.assess()
                self.assertTrue(result['declared_material_error_tolerance_met'])
                self.assertEqual(result['status'], 'REQUIRES_ESCALATION')
                row['material_error'] = None
                result = self.assess()
                self.assertIsNone(result['declared_material_error_tolerance_met'])
                self.assertEqual(result['status'], 'INCOMPLETE_DECLARED_REVIEW')

    def test_missing_and_explicit_unreviewed_units_remain_distinct_from_zero_errors(self):
        self.doc['reviews'].pop()
        self.doc['reviews'][0].update(status='UNREVIEWED', material_error=None, answer_spans=[])
        result = self.assess()
        self.assertEqual(result['missing_unit_ids'], ['period'])
        self.assertEqual(result['status_counts']['UNREVIEWED'], 2)
        self.assertIsNone(result['declared_material_error_tolerance_met'])
        self.assertEqual(result['status'], 'INCOMPLETE_DECLARED_REVIEW')

    def test_supplied_but_unreviewed_evidence_is_not_absent_or_satisfied(self):
        source = self.doc['reviews'][0]['source_reviews'][0]
        source.update(status='SUPPLIED_UNREVIEWED', spans=[])
        with self.assertRaisesRegex(ValueError, 'UNREVIEWED_SOURCE_CANNOT_SUPPORT_SATISFIED'):
            self.assess()
        self.doc['reviews'][0].update(status='UNSUPPORTED', material_error=None, issues=['source_status'])
        result = self.assess()
        self.assertEqual(result['supplied_unreviewed_source_ids'], ['supplied'])
        self.assertFalse(result['source_absence_established'])
        self.assertEqual(result['status'], 'INCOMPLETE_DECLARED_REVIEW')
        self.assertIsNone(result['declared_material_error_tolerance_met'])

    def test_protocol_threshold_original_and_source_tampering_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_PROTOCOL_PIN_MISMATCH'):
            module.assess(self.doc, self.root, '0' * 64)
        (self.root / 'review-protocol.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH_MISMATCH'): self.assess()
        self.adopt()
        (self.root / 'original.json').write_bytes(self.original + b' ')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH_MISMATCH'): self.assess()

    def test_actual_delivery_markdown_json_and_resigned_inventory_drift_are_rejected(self):
        for name in ('first-response.md', 'response.json'):
            path = self.root / 'delivery' / name; original = path.read_bytes()
            with self.subTest(name=name):
                path.write_bytes(original + b' ')
                try:
                    with self.assertRaises(ValueError): self.assess()
                finally: path.write_bytes(original)
        receipt = self.root / 'delivery/receipt.json'; original_receipt = receipt.read_bytes()
        path = self.root / 'delivery/first-response.md'; path.write_bytes(path.read_bytes() + b'\nUnreviewed contradictory prose.')
        changed = json.loads(original_receipt)
        changed['artifacts'] = fixture.source.file_inventory(self.root / 'delivery')
        receipt.write_bytes(fixture.source.encode(changed))
        self.doc['delivery']['receipt_sha256'] = sha(receipt.read_bytes())
        self.doc['delivery']['first_response_sha256'] = sha(path.read_bytes())
        with self.assertRaises(ValueError): self.assess()

    def test_hash_valid_unrelated_originals_do_not_qualify_delivery(self):
        (self.root / 'unrelated.json').write_text('{"value": 33}')
        self.protocol['sources'][0]['artifact'] = self.ref('unrelated.json'); self.adopt()
        with self.assertRaisesRegex(ValueError, 'REVIEW_SOURCE_NOT_IN_DELIVERED_CORPUS'): self.assess()

    def test_unknown_duplicate_units_missing_source_status_and_edited_locators_refuse(self):
        original = copy.deepcopy(self.doc)
        mutations = [lambda d: d['reviews'].append(copy.deepcopy(d['reviews'][0])),
                     lambda d: d['reviews'][0].update(unit_id='unregistered'),
                     lambda d: d['reviews'][0].update(source_reviews=[]),
                     lambda d: d['reviews'][0]['answer_spans'][0]['span'].update(sha256='0' * 64),
                     lambda d: d['reviews'][0].update(material_error=0)]
        for mutate in mutations:
            self.doc = copy.deepcopy(original); mutate(self.doc)
            with self.assertRaises(ValueError): self.assess()

    def test_adoption_capture_order_and_unknown_materiality_threshold_are_strict(self):
        self.doc['delivery']['captured_at'] = '2032-01-01T08:00:00Z'
        with self.assertRaisesRegex(ValueError, 'REVIEW_CLOCK_ORDER'): self.assess()
        self.doc['delivery']['captured_at'] = '2032-01-01T10:00:00Z'
        self.protocol['max_material_error_units'] = True; self.adopt()
        with self.assertRaisesRegex(ValueError, 'ABSOLUTE_ERROR_TOLERANCE'): self.assess()
        raw = 'a€b'.encode()
        with self.assertRaisesRegex(ValueError, 'UTF8_SPAN_BOUNDARY'):
            module.span({'start_byte': 2, 'end_byte': 3, 'sha256': sha(raw[2:3])}, raw)

    def test_traversal_named_private_path_and_actual_reparse_are_refused(self):
        reader = module.Reader(self.root)
        for name in ('../original.json', 'private-runtime/record.json', 'sec-contact.json'):
            with self.assertRaises(ValueError): reader.read({'path': name, 'sha256': sha(self.original)})
        link = self.root / 'linked.json'
        try: os.symlink(self.root / 'original.json', link)
        except (OSError, NotImplementedError) as error: self.skipTest('Native symlink unavailable: ' + str(error))
        with self.assertRaisesRegex(ValueError, 'REPARSE_ARTIFACT_REJECTED'):
            reader.read({'path': link.name, 'sha256': sha(self.original)})

    def test_readonly_cli_reports_complete_and_incomplete_without_dispatch(self):
        path = self.root / 'review.json'; path.write_text(json.dumps(self.doc), encoding='utf8')
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONOPTIMIZE='0')
        env['PYTHONPATH'] = os.pathsep.join([str(Path(module.__file__).parent), str(fixture.source.ROOT / 'scripts')])
        command = [sys.executable, '-X', 'utf8', '-B', module.__file__, str(path), '--evidence-root', str(self.root), '--protocol-sha256', self.pin]
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'], 'WITHIN_DECLARED_TOLERANCE')
        self.doc['reviews'].pop(); path.write_text(json.dumps(self.doc), encoding='utf8')
        result = subprocess.run(command, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)['status'], 'INCOMPLETE_DECLARED_REVIEW')


if __name__ == '__main__':
    unittest.main(verbosity=2)
