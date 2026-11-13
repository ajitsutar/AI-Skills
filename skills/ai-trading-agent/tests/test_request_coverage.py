"""Synthetic scope-loss, authored-limit and linked-annex delivery checks."""
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
import request_coverage as module
import supplied_research as source


class RequestCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='request-coverage-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.original = {'requested_categories': ['maintenance', 'capacity', 'unmapped-specialty'],
            'alternate_subset': ['maintenance'], 'source_scope': 'Only retained records; future route proposals stay unexecuted.',
            'alternate_scope': 'Anything', 'alternate_rules': {'network': True},
            'session_rules': {'network': False, 'broker_or_account_actions': False,
                              'purchases_trials_or_plan_changes': False, 'new_credential_requests': False}}
        self.input = {'request': self.original, 'observation': {'id': 'ordinary-note', 'value': 12.75,
            'scope': 'A supplied example, not a forecast'}, 'access': {'subscription_state': 'expired', 'body_fields': []},
            'common_disclosure': 'A common supplied record for a supported annex.'}
        self.manifest = self.root / 'ingress.json'; self.write_sources()
        self.plan = {'request_ref': {'source_id': 'original', 'pointer': '/request'},
            'categories_pointer': '/requested_categories', 'source_scope_pointer': '/source_scope',
            'constraints_pointer': '/session_rules', 'rows': [self.row(c) for c in self.original['requested_categories']]}
        self.plan_path = self.root / 'plan.json'; self.output = self.root / 'delivery'

    def write_sources(self):
        raw = json.dumps(self.input).encode(); (self.root / 'original.json').write_bytes(raw)
        self.manifest.write_text(json.dumps({'schema_version': 1, 'sources': [
            {'id': 'original', 'path': 'original.json', 'format': 'json', 'sha256': hashlib.sha256(raw).hexdigest()}]}))
        self.pin = hashlib.sha256(self.manifest.read_bytes()).hexdigest()

    def row(self, category):
        return {'category': category,
            'observations': [{'source_ref': {'source_id': 'original', 'pointer': '/observation'},
                              'interpretation': 'The retained note is limited to its declared scope.'}],
            'analysis': 'This category has a retained observation and an unresolved coverage question.',
            'free_source_plan': {'routes': [{'source_kind': 'Original public documentation',
                'purpose': 'Check the named unresolved coverage question.',
                'stopping_condition': 'Stop after the original documentation and one independent corroborating source.',
                'execution_status': 'NOT_EXECUTED'}], 'no_route_reason': None},
            'optional_access': {'assessment': 'Access is expired; continue independent supported work.',
                'improvement_or_no_need_reason': 'Existing renewed access could add archive depth if supplied; no purchase is required.',
                'source_refs': [{'source_id': 'original', 'pointer': '/access'}]},
            'remaining_gaps': ['Coverage beyond the retained note is not established.'], 'supporting_annex_ids': []}

    def compose(self):
        self.plan_path.write_text(json.dumps(self.plan), encoding='utf8')
        return module.compose(self.plan_path, self.output, self.manifest, self.pin, self.root)

    def response(self):
        return json.loads((self.output / 'response.json').read_bytes())

    def add_annex(self, canonical=False):
        plan = {'output_contract': final_report.STRICT, 'sections': [
            {'kind': 'source_claim', 'request': {'operation': 'presence', 'terms': ['common']}}]}
        path = self.root / 'annex-plan.json'; path.write_text(json.dumps(plan))
        report = self.root / 'checked-report'
        final_report.compose(path, report, self.manifest, self.pin, self.root)
        if canonical:
            metadata = self.root / 'metadata.json'
            metadata.write_text(json.dumps({'case_id': 'ordinary-research', 'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'}}))
            export = self.root / 'checked-response'
            final_report.export_response(report, metadata, export)
            directory, first = export, export / 'report/first-response.md'
        else:
            directory, first = report, report / 'first-response.md'
        annex = {'id': 'supported-annex', 'kind': 'canonical_response' if canonical else 'final_report',
            'directory': directory.name, 'receipt_sha256': hashlib.sha256((directory / 'receipt.json').read_bytes()).hexdigest(),
            'first_response_sha256': hashlib.sha256(first.read_bytes()).hexdigest()}
        if canonical: annex['response_sha256'] = hashlib.sha256((directory / 'response.json').read_bytes()).hexdigest()
        self.plan['annexes'] = [annex]
        self.plan['rows'][0]['supporting_annex_ids'] = [annex['id']]
        return directory

    def test_complete_authored_delivery_without_compositor_or_annex(self):
        receipt = self.compose(); response = self.response()
        self.assertEqual(receipt['status'], 'STRUCTURAL_SCOPE_AND_BYTES_CHECKED')
        self.assertEqual(response['coverage']['original_categories'], self.original['requested_categories'])
        self.assertEqual([r['category'] for r in response['rows']], self.original['requested_categories'])
        self.assertEqual(response['annexes'], [])
        self.assertFalse(response['request_correctness_verified'])
        self.assertFalse(response['coverage']['semantic_completeness_verified'])
        self.assertEqual(response['authored_content_status'], 'SEMANTICALLY_UNVERIFIED')
        self.assertEqual(response['rows'][0]['observations'][0]['original_value']['value'], 12.75)
        self.assertEqual(response['first_response_sha256'], hashlib.sha256((self.output / 'first-response.md').read_bytes()).hexdigest())
        self.assertNotEqual(response['method'], final_report.ENVELOPE_METHOD)

    def test_declared_metadata_and_original_hashes_preserve_neutral_protocol_fields(self):
        metadata = {'case_id': 'synthetic-source-briefing',
            'runtime_model_metadata': {'model': 'unknown', 'effort': 'unknown'},
            'evidence_paths': [{'path': 'retained-calculation.json', 'sha256': '1' * 64}]}
        metadata_path = self.root / 'metadata.json'; metadata_path.write_text(json.dumps(metadata))
        self.plan_path.write_text(json.dumps(self.plan))
        module.compose(self.plan_path, self.output, self.manifest, self.pin, self.root, metadata_path)
        response = self.response()
        self.assertEqual(response['case_id'], metadata['case_id'])
        self.assertEqual(response['candidate_version'], (source.ROOT / 'VERSION').read_text().strip())
        self.assertEqual(response['input_hashes'], {'original.json': hashlib.sha256((self.root / 'original.json').read_bytes()).hexdigest()})
        self.assertEqual(response['runtime_model_metadata'], metadata['runtime_model_metadata'])
        self.assertEqual(response['evidence_paths'], metadata['evidence_paths'])
        self.assertEqual(response['metadata_status'], 'PARTICIPANT_DECLARATIONS_NOT_VERIFIED')
        self.assertNotEqual(response['artifact_association_method'], final_report.ENVELOPE_METHOD)
        module.verify(self.output)

    def test_missing_category_retains_diagnostic_and_does_not_export_complete_answer(self):
        self.plan['rows'].pop()
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_REQUEST_SCOPE'): self.compose()
        failure = json.loads((self.output / 'failure.json').read_bytes())
        self.assertIn('unmapped-specialty', failure['error'])
        self.assertTrue((self.output / 'original-plan.json').is_file())
        self.assertFalse((self.output / 'receipt.json').exists())
        self.assertFalse((self.output / 'first-response.md').exists())

    def test_duplicate_category_cannot_fill_missing_category(self):
        self.plan['rows'][-1] = deepcopy(self.plan['rows'][0])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_CATEGORY_ROW'): self.compose()

    def test_alternate_subset_pointer_and_literal_scope_are_rejected(self):
        self.plan['categories_pointer'] = '/alternate_subset'
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_COMPLETE_CATEGORY_INVENTORY'): self.compose()

    def test_literal_categories_cannot_override_original(self):
        self.plan['requested_categories'] = ['maintenance']
        with self.assertRaisesRegex(ValueError, 'DELIVERY_FIELDS_REQUIRED'): self.compose()

    def test_unrequested_row_rejected_and_original_order_retained(self):
        self.plan['rows'].reverse(); self.compose()
        self.assertEqual([r['category'] for r in self.response()['rows']], self.original['requested_categories'])

    def test_unrecognized_category_remains_visible_with_supported_limits(self):
        self.plan['rows'][-1]['observations'] = []
        self.plan['rows'][-1]['free_source_plan'] = {'routes': [], 'no_route_reason': 'The exclusive supplied-source scope permits no additional route.'}
        self.compose(); row = self.response()['rows'][-1]
        self.assertEqual(row['category'], 'unmapped-specialty')
        self.assertEqual(row['observations'], [])
        self.assertTrue(row['authored_remaining_gaps'])
        self.assertFalse(self.response()['request_correctness_verified'])

    def test_recognized_original_constraint_pointer_cannot_be_redirected(self):
        self.plan['constraints_pointer'] = '/alternate_rules'
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_SESSION_RULES_REQUIRED'): self.compose()

    def test_source_scope_pointer_cannot_be_redirected(self):
        self.plan['source_scope_pointer'] = '/alternate_scope'
        with self.assertRaisesRegex(ValueError, 'ORIGINAL_SOURCE_SCOPE_REQUIRED'): self.compose()

    def test_original_constraints_and_failed_access_are_preserved(self):
        self.compose(); response = self.response()
        self.assertEqual(response['original_constraints']['value'], self.original['session_rules'])
        self.assertEqual(response['original_source_scope']['value'], self.original['source_scope'])
        access = response['rows'][0]['optional_access']['original_access_records'][0]
        self.assertEqual(access['original_value']['subscription_state'], 'expired')
        self.assertEqual(response['rows'][0]['free_source_plan']['routes'][0]['execution_status'], 'NOT_EXECUTED')
        self.assertFalse(response['execution_authorized'])

    def test_route_proposal_cannot_be_claimed_executed(self):
        self.plan['rows'][0]['free_source_plan']['routes'][0]['execution_status'] = 'EXECUTED'
        with self.assertRaisesRegex(ValueError, 'PROSPECTIVE_ROUTE_NOT_EXECUTED'): self.compose()

    def test_irrelevant_authored_text_is_not_certified_by_structural_success(self):
        self.plan['rows'][0]['analysis'] = 'An irrelevant assertion that this adapter cannot grade.'
        self.compose(); response = self.response()
        self.assertEqual(response['status'], 'REQUESTED_CATEGORY_ROWS_PRESENT')
        self.assertEqual(response['rows'][0]['authored_content_status'], 'SEMANTICALLY_UNVERIFIED')
        self.assertFalse(response['request_correctness_verified'])
        self.assertFalse(response['coverage']['semantic_completeness_verified'])

    def test_original_byte_tampering_blocks_delivery(self):
        (self.root / 'original.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'HASH_MISMATCH'): self.compose()

    def test_complete_mixed_delivery_keeps_exact_annex_separate(self):
        original = self.add_annex(); first = (original / 'first-response.md').read_bytes()
        self.compose(); response = self.response()
        self.assertEqual((self.output / 'annexes/supported-annex/first-response.md').read_bytes(), first)
        self.assertNotEqual((self.output / 'first-response.md').read_bytes(), first)
        self.assertFalse(response['annexes'][0]['complete_briefing_verified'])
        self.assertEqual(len(response['rows']), 3)
        self.assertEqual(response['artifact_association_method'], module.METHOD)

    def test_canonical_annex_and_portable_read_only_verification(self):
        self.add_annex(canonical=True); self.compose()
        copied = self.root / 'relocated'; shutil.copytree(self.output, copied)
        before = source.file_inventory(copied)
        module.verify(copied)
        self.assertEqual(source.file_inventory(copied), before)
        final_report.verify_response(copied / 'annexes/supported-annex')

    def test_annex_tampering_is_not_hidden_by_complete_category_rows(self):
        directory = self.add_annex()
        with (directory / 'first-response.md').open('ab') as stream: stream.write(b'Altered annex')
        with self.assertRaises(ValueError): self.compose()
        self.assertFalse((self.output / 'receipt.json').exists())

    def test_only_bounded_checked_report_annexes_are_accepted(self):
        self.plan['annexes'] = [{'id': 'anything', 'kind': 'arbitrary_directory', 'directory': '.',
            'receipt_sha256': '0' * 64, 'first_response_sha256': '0' * 64}]
        with self.assertRaisesRegex(ValueError, 'SUPPORTED_CHECKED_ANNEX'): self.compose()

    def test_published_text_or_json_tampering_rejected(self):
        self.compose()
        first = self.root / 'changed.md'; first.write_bytes((self.output / 'first-response.md').read_bytes() + b'Extra unreviewed claim')
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_BRIEFING_DIFFERS'): module.verify(self.output, first)
        response = self.response(); response['original_constraints']['value']['network'] = True
        changed = self.root / 'changed.json'; changed.write_text(json.dumps(response))
        with self.assertRaisesRegex(ValueError, 'PUBLISHED_DELIVERY_RESPONSE_DIFFERS'): module.verify(self.output, published_response=changed)

    def test_resigned_inventory_cannot_certify_authored_content(self):
        self.compose(); response = self.response(); response['request_correctness_verified'] = True
        (self.output / 'response.json').write_bytes(source.encode(response))
        path = self.output / 'receipt.json'; receipt = json.loads(path.read_bytes())
        receipt['artifacts'] = source.file_inventory(self.output); path.write_bytes(source.encode(receipt))
        with self.assertRaisesRegex(ValueError, 'DELIVERY_REPLAY_MISMATCH'): module.verify(self.output)

    def test_existing_output_is_not_overwritten_or_deleted(self):
        self.compose(); before = source.file_inventory(self.output)
        with self.assertRaises(FileExistsError): self.compose()
        self.assertEqual(source.file_inventory(self.output), before)


if __name__ == '__main__':
    unittest.main()
