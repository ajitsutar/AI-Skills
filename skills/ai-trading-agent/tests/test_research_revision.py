"""Synthetic retained native declarations, replayed through real answer_review."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research_revision as module


def span(raw, needle):
    start = raw.index(needle)
    return {'start_byte': start, 'end_byte': start + len(needle), 'sha256': module.review.sha(needle)}


class ResearchRevisionTests(unittest.TestCase):
    def setUp(self):
        # Retain synthetic attempts, including failures, outside the package.
        parent = os.environ.get('RESEARCH_REVISION_TEST_ROOT')
        self.base = Path(parent or tempfile.gettempdir()) / ('research-revision-' + uuid.uuid4().hex)
        self.base.mkdir()
        self.root = self.base / 'run'
        self.request = b'Check amount and currency in this fictional release.'
        self.source = b'Fictional revenue: EUR 17 million.'
        self.markdown = b'Fictional revenue was EUR 17 million.\n'
        self.response = b'{"complete_answer":"Fictional revenue was EUR 17 million."}\n'
        self.units = [{'id': uid, 'requirement': 'Check ' + uid,
                       'request_spans': [span(self.request, uid.encode())], 'required_source_ids': ['release']}
                      for uid in ('amount', 'currency')]
        self.created = module.create_run(self.root, self.request, {'release': self.source}, self.units,
                                         '2035-01-01T09:00:00Z', max_corrections=1)
        self.head = self.created['head_sha256']
        self.draft = self.freeze()

    def freeze(self, markdown=None, parent=None, clock='2035-01-01T10:00:00Z'):
        value = module.freeze_draft(self.root, markdown or self.markdown, self.response, clock,
                                    expected_head_sha256=self.head, parent_draft_id=parent)
        self.head = value['head_sha256']
        return value

    def document(self, draft=None):
        draft = draft or self.draft
        raw = (self.root / draft['delivery']['first_response']['path']).read_bytes()
        return {'schema_version': 1, 'protocol': copy.deepcopy(self.created['protocol']),
                'reviewed_at': '2035-01-01T10:01:00Z', 'reviewer': {'id': 'native-synthetic-reviewer', 'kind': 'automated'},
                'delivery': copy.deepcopy(draft['delivery']),
                'reviews': [{'unit_id': uid, 'status': 'SATISFIED', 'material_error': False, 'issues': [],
                             'rationale': 'Synthetic native declaration, not a machine prose grade.',
                             'answer_spans': [{'artifact': 'first_response', 'span': span(raw, needle)}],
                             'source_reviews': [{'source_id': 'release', 'status': 'REVIEWED',
                                                 'spans': [span(self.source, needle)]}]}
                            for uid, needle in [('amount', b'17'), ('currency', b'EUR')]]}

    def record(self, document=None, mode='independent_native'):
        result = module.record_review(self.root, document or self.document(), reviewer_mode=mode,
                                       expected_head_sha256=self.head)
        self.head = result['head_sha256']
        return result

    def final(self, draft=None):
        result = module.select_final(self.root, (draft or self.draft)['draft_id'], expected_head_sha256=self.head)
        self.head = result['head_sha256']
        return result

    def test_actual_assessor_complete_pair_and_exact_final_notice(self):
        recorded = self.record()
        self.assertEqual(recorded['assessment']['method'], module.review.METHOD)
        self.assertEqual(recorded['assessment']['status'], 'WITHIN_DECLARED_TOLERANCE')
        self.assertFalse(recorded['assessment']['whole_answer_correctness_verified'])
        selected = self.final()
        self.assertEqual(selected['delivery'], self.draft['delivery'])
        self.assertEqual(selected['disposition']['final_status'], 'REVIEWED_DELIVERY')
        self.assertIn(b'declarations', (self.root / selected['delivery_notice']['path']).read_bytes())
        self.assertEqual(module.verify(self.root, self.head)['final']['delivery'], self.draft['delivery'])

    def test_corrected_complete_draft_preserves_original_and_parent_failure(self):
        doc = self.document()
        doc['reviews'][0].update(status='MATERIAL_ERROR', material_error=True, issues=['amount'],
                                 rationale='Fictional amount requires correction in this exercise.')
        self.record(doc)
        revised = self.freeze(self.markdown + b'Checked against the retained release.\n', self.draft['draft_id'],
                              clock='2035-01-01T10:02:00Z')
        next_doc = self.document(revised); next_doc['reviewed_at'] = '2035-01-01T10:03:00Z'
        self.record(next_doc)
        result = self.final(revised)
        state = module.verify(self.root, self.head)
        self.assertEqual(len(state['drafts']), 2)
        self.assertEqual(state['reviews'][0]['assessment']['material_error_units'], 1)
        self.assertEqual((self.root / 'drafts/000/first-response.md').read_bytes(), self.markdown)
        self.assertEqual(result['delivery']['first_response']['path'], 'drafts/001/first-response.md')

    def test_omission_is_retained_and_visible_never_a_pass(self):
        doc = self.document(); doc['reviews'][0].update(status='OMITTED', material_error=False,
                                                       issues=['omitted_alternative'], answer_spans=[],
                                                       rationale='A material alternative was omitted.')
        self.record(doc)
        selected = self.final()
        self.assertEqual(selected['disposition']['final_status'], 'DELIVERED_WITH_LIMITATIONS')
        notice = (self.root / 'delivery-notice.md').read_text(encoding='utf8')
        self.assertIn('OMITTED', notice); self.assertIn('material alternative was omitted', notice)
        self.assertIn('unreliable', notice)

    def test_missing_and_unreviewed_units_cannot_be_zero_error_pass(self):
        doc = self.document(); doc['reviews'].pop()
        doc['reviews'][0].update(status='UNREVIEWED', material_error=None, issues=[], answer_spans=[])
        self.record(doc, mode='self_native')
        selected = self.final()
        self.assertEqual(selected['disposition']['final_status'], 'REVIEW_INCOMPLETE')
        self.assertEqual(selected['disposition']['missing_unit_ids'], ['currency'])
        notice = (self.root / 'delivery-notice.md').read_text(encoding='utf8')
        self.assertIn('currency: UNREVIEWED', notice); self.assertIn('amount: UNREVIEWED', notice)
        self.assertIn('self_native', notice)

    def test_changed_sources_and_originals_fail_real_verifier(self):
        for name in ('request.md', 'sources/release.bin', 'protocol.json', 'drafts/000/response.json',
                     'drafts/000/first-response.md'):
            path = self.root / name; raw = path.read_bytes(); path.write_bytes(raw + b' ')
            try:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    self.record()
            finally:
                path.write_bytes(raw)

    def test_substituted_annex_and_protocol_are_rejected(self):
        doc = self.document(); doc['delivery']['first_response']['path'] = 'sources/release.bin'
        doc['delivery']['first_response']['sha256'] = module.review.sha(self.source)
        with self.assertRaisesRegex(ValueError, 'EXACT_COMPLETE_DRAFT_REVIEW_REQUIRED'):
            self.record(doc)
        doc = self.document(); doc['protocol']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'UNCHANGED_REVIEW_PROTOCOL_REQUIRED'):
            self.record(doc)

    def test_changed_draft_requires_new_actual_review_and_old_selection_refused(self):
        old = self.document(); self.record(old)
        revised = self.freeze(self.markdown + b'Additional complete material.\n', self.draft['draft_id'],
                              clock='2035-01-01T10:02:00Z')
        with self.assertRaisesRegex(ValueError, 'EXACT_COMPLETE_DRAFT_REVIEW_REQUIRED'):
            self.record(old)
        with self.assertRaisesRegex(ValueError, 'LATEST_DRAFT_REVIEW_REQUIRED'):
            self.final(revised)
        new = self.document(revised); new['reviewed_at'] = '2035-01-01T10:03:00Z'; self.record(new)
        with self.assertRaisesRegex(ValueError, 'EXACT_LATEST_DELIVERY_REQUIRED'):
            self.final(self.draft)

    def test_attempt_limit_cannot_reset_parent_or_create_again(self):
        with self.assertRaisesRegex(ValueError, 'FRESH_RUN_DIRECTORY_REQUIRED'):
            module.create_run(self.root, self.request, {'release': self.source}, self.units,
                              '2035-01-01T09:00:00Z', max_corrections=5)
        self.record()
        with self.assertRaisesRegex(ValueError, 'DRAFT_PARENT_MISMATCH'):
            self.freeze(parent=None)
        revised = self.freeze(parent=self.draft['draft_id'], clock='2035-01-01T10:02:00Z')
        new = self.document(revised); new['reviewed_at'] = '2035-01-01T10:03:00Z'; self.record(new)
        with self.assertRaisesRegex(ValueError, 'CORRECTION_ATTEMPT_LIMIT'):
            self.freeze(parent=revised['draft_id'], clock='2035-01-01T10:04:00Z')

    def test_package_output_boundary_precedes_writes_and_blocks_relocated_runs(self):
        package = self.base / 'synthetic-package'
        scripts = package / 'scripts'; scripts.mkdir(parents=True)
        script = scripts / 'research_revision.py'
        script.write_bytes(Path(module.__file__).read_bytes())
        spec = importlib.util.spec_from_file_location('synthetic_revision_boundary', script)
        relocated = importlib.util.module_from_spec(spec); spec.loader.exec_module(relocated)
        for target in (package / 'run', scripts / '..' / 'normalized-run'):
            with self.subTest(target=str(target)), self.assertRaisesRegex(
                    ValueError, 'OUTPUT_MUST_BE_OUTSIDE_INSTALLED_SKILL'):
                relocated.create_run(target, self.request, {'release': self.source}, self.units,
                                     '2035-01-01T09:00:00Z')
            self.assertFalse(target.exists(), 'Rejected output must leave no run artifacts.')
        # A formerly external run cannot be resumed after it is moved into a package.
        moved_run = package / 'moved-run'
        module.create_run(moved_run, self.request, {'release': self.source}, self.units,
                          '2035-01-01T09:00:00Z')
        with self.assertRaisesRegex(ValueError, 'OUTPUT_MUST_BE_OUTSIDE_INSTALLED_SKILL'):
            relocated.verify(moved_run)

    def test_external_head_detects_truncation_and_changed_frozen_limit(self):
        self.record()
        event = self.root / 'events/000002.json'; raw = event.read_bytes(); event.unlink()
        with self.assertRaisesRegex(ValueError, 'EXTERNAL_HEAD_PIN_MISMATCH'):
            module.verify(self.root, self.head)
        event.write_bytes(raw)
        run_path = self.root / 'run.json'; run = json.loads(run_path.read_bytes()); run['max_corrections'] = 5
        run_path.write_bytes(module.encode(run))
        with self.assertRaisesRegex(ValueError, 'EVENT_CHAIN_MISMATCH'):
            module.verify(self.root, self.head)

    def test_no_review_no_correction_no_final_and_no_replacement_review(self):
        with self.assertRaisesRegex(ValueError, 'PARENT_REVIEW_REQUIRED'):
            self.freeze(parent=self.draft['draft_id'])
        with self.assertRaisesRegex(ValueError, 'LATEST_DRAFT_REVIEW_REQUIRED'):
            self.final()
        self.record()
        with self.assertRaisesRegex(ValueError, 'ONE_REVIEW_PER_DRAFT'):
            self.record()
        self.final()
        with self.assertRaisesRegex(ValueError, 'FINAL_SELECTION_IS_TERMINAL'):
            self.record()

    def test_bad_source_locator_is_rejected_by_actual_assessor(self):
        doc = self.document(); doc['reviews'][0]['source_reviews'][0]['spans'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'BYTE_SPAN_HASH_MISMATCH'):
            self.record(doc)

    def test_notice_or_event_tampering_cannot_hide_unresolved_finding(self):
        doc = self.document(); doc['reviews'][0].update(status='UNSUPPORTED', material_error=False,
                                                       issues=['source_status'], rationale='No support for this inference.')
        self.record(doc); self.final()
        path = self.root / 'delivery-notice.md'; path.write_text('All clear.', encoding='utf8')
        with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH_MISMATCH'):
            module.verify(self.root, self.head)

    def test_cli_verifies_real_history_and_requires_external_mutation_pin(self):
        script = Path(module.__file__)
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(script), 'verify', '--run', str(self.root),
                                 '--expected-head-sha256', self.head], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([sys.executable, '-X', 'utf8', '-B', str(script), 'final', '--run', str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('EXTERNAL_HEAD_PIN_REQUIRED', result.stdout)

    def test_full_cli_create_freeze_review_final_uses_complete_pair(self):
        run = self.base / 'cli-run'

        def invoke(action, job, head=None):
            job_path = self.base / ('cli-' + action + '.json'); job_path.write_bytes(module.encode(job))
            command = [sys.executable, '-X', 'utf8', '-B', str(Path(module.__file__)), action,
                       '--run', str(run), '--job', str(job_path)]
            if head:
                command += ['--expected-head-sha256', head]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)

        created = invoke('create', {'request': self.request.decode(), 'sources': {'release': self.source.decode()},
                                    'units': self.units, 'adopted_at': '2035-01-01T09:00:00Z', 'max_corrections': 0})
        draft = invoke('freeze', {'markdown': self.markdown.decode(), 'response': self.response.decode(),
                                  'captured_at': '2035-01-01T10:00:00Z', 'parent_draft_id': None}, created['head_sha256'])
        document = self.document(); document['protocol'] = created['protocol']; document['delivery'] = draft['delivery']
        recorded = invoke('review', {'review_document': document, 'reviewer_mode': 'self_native'}, draft['head_sha256'])
        final = invoke('final', {'draft_id': draft['draft_id']}, recorded['head_sha256'])
        self.assertEqual(final['disposition']['final_status'], 'REVIEWED_DELIVERY')
        self.assertEqual((run / final['delivery']['first_response']['path']).read_bytes(), self.markdown)

    def test_replay_rejects_changed_assessment_and_missing_source_disposition(self):
        document = self.document(); document['reviews'][0]['source_reviews'] = []
        with self.assertRaisesRegex(ValueError, 'MISSING_SOURCE_REVIEW_DISPOSITION'):
            self.record(document)
        self.record()
        path = self.root / 'events/000002.json'; event = json.loads(path.read_bytes())
        event['payload']['assessment']['material_error_units'] = 5
        path.write_bytes(module.encode(event))
        with self.assertRaisesRegex(ValueError, 'REVIEW_ASSESSMENT_REPLAY_MISMATCH'):
            module.verify(self.root, self.head)


if __name__ == '__main__':
    unittest.main()
