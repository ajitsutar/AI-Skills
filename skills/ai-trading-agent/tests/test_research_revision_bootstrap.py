"""Pinned-file bootstrap and real native-review state transitions; no semantic grader."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research_revision as m


def full_span(raw):
    return {'start_byte': 0, 'end_byte': len(raw), 'sha256': m.review.sha(raw)}


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.environ.get('RESEARCH_REVISION_TEST_ROOT') or tempfile.gettempdir()) / ('review-bootstrap-' + uuid.uuid4().hex)
        self.base.mkdir()
        self.original = self.base / 'original'; self.original.mkdir()
        self.request = b'Assess the release and identify any unsupported comparisons.\r\n'
        self.sources = {'release': b'{"currency":"EUR","revenue":23}\r\n',
                        'context': b'Fictional excerpt; no earlier period supplied.\r\n'}
        (self.original / 'request.txt').write_bytes(self.request)
        for sid, raw in self.sources.items(): (self.original / (sid + '.txt')).write_bytes(raw)
        self.manifest = {'schema_version': 1, 'sources': [
            {'id': sid, 'path': sid + '.txt', 'sha256': m.review.sha(raw), 'format': 'text'}
            for sid, raw in self.sources.items()]}
        self.manifest_path = self.original / 'manifest.json'; self.write_manifest()
        self.run = self.base / 'run'

    def write_manifest(self):
        self.manifest_raw = m.encode(self.manifest); self.manifest_path.write_bytes(self.manifest_raw)

    def boot(self, **overrides):
        args = dict(root=self.run, request_path=self.original / 'request.txt', request_sha256=m.review.sha(self.request),
                    source_manifest_path=self.manifest_path, manifest_sha256=m.review.sha(self.manifest_raw),
                    source_root=self.original, adopted_at='2036-01-01T10:00:00Z')
        args.update(overrides); return m.bootstrap_run(**args)

    def draft(self, created):
        return m.freeze_draft(self.run, b'The source lacks a prior-period comparison.\n',
                              b'{"comparison":"unresolved"}\n', '2036-01-01T10:01:00Z',
                              expected_head_sha256=created['head_sha256'])

    def document(self, created, draft, status='SATISFIED'):
        protocol = json.loads((self.run / 'protocol.json').read_bytes())
        raw = (self.run / draft['delivery']['first_response']['path']).read_bytes()
        return {'schema_version': 1, 'protocol': created['protocol'],
                'reviewed_at': '2036-01-01T10:02:00Z', 'reviewer': {'id': 'synthetic-native-reviewer', 'kind': 'automated'},
                'delivery': draft['delivery'], 'reviews': [
                    {'unit_id': unit['id'], 'status': status, 'material_error': False,
                     'issues': [] if status == 'SATISFIED' else ['omitted_alternative'],
                     'rationale': 'Synthetic native judgment for transition testing, not automated financial grading.',
                     'answer_spans': [{'artifact': 'first_response', 'span': full_span(raw)}] if status == 'SATISFIED' else [],
                     'source_reviews': [{'source_id': sid, 'status': 'REVIEWED', 'spans': [full_span(self.sources[sid])]}
                                        for sid in unit['required_source_ids']]}
                    for unit in protocol['units']]}

    def test_no_protocol_input_creates_protocol_and_real_head(self):
        created = self.boot(); state = m.verify(self.run, created['head_sha256'])
        self.assertEqual(state['workflow_state'], 'DRAFT_REQUIRED')
        self.assertEqual(state['drafts'], []); self.assertEqual(state['reviews'], [])
        p = json.loads((self.run / 'protocol.json').read_bytes())
        self.assertEqual(p['units'][0]['request_spans'], [full_span(self.request)])
        self.assertEqual(p['units'][0]['required_source_ids'], list(self.sources))
        self.assertEqual((self.run / 'bootstrap-manifest.json').read_bytes(), self.manifest_raw)
        self.assertEqual({r['id'] for r in p['sources']}, set(self.sources))

    def test_crlf_nonascii_and_bom_are_never_normalized(self):
        self.request = '\ufeffExamine the société release.\r\nState unknowns.\r\n'.encode('utf8')
        (self.original / 'request.txt').write_bytes(self.request)
        self.sources['context'] = '\ufeffÉvidence en français.\r\nNo earlier observation.\r\n'.encode('utf8')
        (self.original / 'context.txt').write_bytes(self.sources['context'])
        self.manifest['sources'][1]['sha256'] = m.review.sha(self.sources['context']); self.write_manifest()
        created = self.boot(); self.assertEqual((self.run / 'request.md').read_bytes(), self.request)
        for sid, raw in self.sources.items(): self.assertEqual((self.run / 'sources' / (sid + '.bin')).read_bytes(), raw)
        p = json.loads((self.run / 'protocol.json').read_bytes()); m.review.span(p['units'][0]['request_spans'][0], self.request)
        m.verify(self.run, created['head_sha256'])

    def test_original_manifest_mapping_and_relocation_replay(self):
        created = self.boot(); relocated = self.base / 'relocated'; shutil.copytree(self.run, relocated)
        self.assertEqual(m.verify(relocated, created['head_sha256']), m.verify(self.run, created['head_sha256']))
        raw = (relocated / 'bootstrap-manifest.json').read_bytes(); self.assertEqual(raw, self.manifest_raw)

    def test_wrong_request_manifest_or_source_pin_before_output(self):
        for overrides in ({'request_sha256': '0'*64}, {'manifest_sha256': '0'*64}):
            with self.assertRaises(ValueError): self.boot(**overrides)
            self.assertFalse(self.run.exists())
        self.manifest['sources'][0]['sha256'] = '0'*64; self.write_manifest()
        with self.assertRaises(ValueError): self.boot()
        self.assertFalse(self.run.exists())

    def test_source_subset_cannot_replace_externally_pinned_manifest(self):
        old_pin = m.review.sha(self.manifest_raw); self.manifest['sources'].pop(); self.write_manifest()
        with self.assertRaises(ValueError): self.boot(manifest_sha256=old_pin)
        self.assertFalse(self.run.exists())

    def test_extra_manifest_fields_and_duplicate_json_keys_refuse(self):
        self.manifest['selected_source_ids'] = ['release']; self.write_manifest()
        with self.assertRaises(ValueError): self.boot()
        self.manifest_path.write_bytes(b'{"schema_version":1,"sources":[],"sources":[]}')
        with self.assertRaises(ValueError): self.boot(manifest_sha256=m.review.sha(self.manifest_path.read_bytes()))
        self.assertFalse(self.run.exists())

    def test_missing_manifest_or_source_fields_refuse_before_output(self):
        original = copy.deepcopy(self.manifest)
        for key in ('id', 'path', 'sha256', 'format'):
            self.manifest = copy.deepcopy(original); del self.manifest['sources'][0][key]; self.write_manifest()
            with self.assertRaises(ValueError): self.boot()
            self.assertFalse(self.run.exists())
        self.manifest = {'schema_version': 1}; self.write_manifest()
        with self.assertRaises(ValueError): self.boot()
        self.assertFalse(self.run.exists())

    def test_duplicate_ids_paths_and_case_aliases_refuse(self):
        original = copy.deepcopy(self.manifest)
        for key, value in [('id', 'release'), ('id', 'RELEASE'), ('path', 'release.txt'), ('path', 'RELEASE.txt')]:
            self.manifest = copy.deepcopy(original); self.manifest['sources'][1][key] = value; self.write_manifest()
            with self.assertRaises(ValueError): self.boot()
            self.assertFalse(self.run.exists())

    def test_source_paths_cannot_escape_or_name_authentication_files(self):
        for name in ('../outside.txt', '/absolute', 'C:/outside', 'dir\\source.txt', './release.txt', '.ssh/id_rsa'):
            self.manifest['sources'][0]['path'] = name; self.write_manifest()
            with self.assertRaises((ValueError, FileNotFoundError)): self.boot()
            self.assertFalse(self.run.exists())
        with self.assertRaises(ValueError): m._input_path(self.original / 'Cookies')

    def test_missing_binary_and_unsupported_source_refuse(self):
        (self.original / 'release.txt').unlink()
        with self.assertRaises(FileNotFoundError): self.boot()
        raw = b'\x00\x01binary'; (self.original / 'release.txt').write_bytes(raw)
        self.manifest['sources'][0]['sha256'] = m.review.sha(raw); self.write_manifest()
        with self.assertRaises(ValueError): self.boot()
        self.manifest['sources'][0]['format'] = 'pdf'; self.write_manifest()
        with self.assertRaises(ValueError): self.boot()
        self.assertFalse(self.run.exists())

    def test_symlink_source_rejected_before_output(self):
        link = self.original / 'linked.txt'
        try: link.symlink_to(self.original / 'release.txt')
        except OSError: self.skipTest('Host does not permit creation of test symlinks')
        self.manifest['sources'][0]['path'] = 'linked.txt'; self.write_manifest()
        with self.assertRaises(ValueError): self.boot()
        self.assertFalse(self.run.exists())

    def test_optional_native_material_units_and_reserved_unit_refusal(self):
        unit = {'id': 'comparison', 'requirement': 'Assess supported and missing comparisons.',
                'request_spans': [full_span(self.request)], 'required_source_ids': ['release', 'context']}
        created = self.boot(material_units=[unit]); p = json.loads((self.run / 'protocol.json').read_bytes())
        self.assertEqual(p['units'][1], unit); self.assertEqual(len(p['units']), 2)
        unit['id'] = m.WHOLE_REQUEST_ID
        with self.assertRaises(ValueError): self.boot(root=self.base / 'bad', material_units=[unit])
        self.assertFalse((self.base / 'bad').exists()); m.verify(self.run, created['head_sha256'])

    def test_favorable_judgment_is_not_an_input_unit(self):
        unit = {'id': 'x', 'requirement': 'Assess the request.', 'request_spans': [full_span(self.request)],
                'required_source_ids': [], 'status': 'SATISFIED'}
        with self.assertRaises(ValueError): self.boot(material_units=[unit])
        self.assertFalse(self.run.exists())

    def test_post_staging_source_change_raises_and_preserves_failed_run(self):
        original = m.create_run
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.original / 'context.txt').write_bytes(b'Changed after staging.\n'); return result
        with patch.object(m, 'create_run', side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'CHANGED_DURING_BOOTSTRAP'): self.boot()
        self.assertTrue(self.run.exists())
        self.assertEqual((self.run / 'sources/context.bin').read_bytes(), self.sources['context'])

    def test_no_review_final_is_rejected_and_explicitly_required(self):
        created = self.boot(); draft = self.draft(created)
        self.assertEqual(draft['workflow_state'], 'REVIEW_REQUIRED')
        with self.assertRaisesRegex(ValueError, 'LATEST_DRAFT_REVIEW_REQUIRED'):
            m.select_final(self.run, draft['draft_id'], expected_head_sha256=draft['head_sha256'])
        self.assertEqual(m.verify(self.run)['workflow_state'], 'REVIEW_REQUIRED')
        self.assertFalse((self.run / 'delivery-notice.md').exists())

    def test_real_self_native_review_and_selection_are_separate(self):
        created = self.boot(); draft = self.draft(created)
        recorded = m.record_review(self.run, self.document(created, draft), reviewer_mode='self_native', expected_head_sha256=draft['head_sha256'])
        selected = m.select_final(self.run, draft['draft_id'], expected_head_sha256=recorded['head_sha256'])
        self.assertEqual(selected['workflow_state'], 'DELIVERY_SELECTED')
        self.assertFalse(selected['disposition']['whole_answer_correctness_verified'])
        self.assertEqual(m.verify(self.run)['reviews'][0]['reviewer_mode'], 'self_native')

    def test_adverse_review_and_changed_draft_keep_original_findings(self):
        created = self.boot(); draft = self.draft(created); doc = self.document(created, draft, 'OMITTED')
        recorded = m.record_review(self.run, doc, reviewer_mode='self_native', expected_head_sha256=draft['head_sha256'])
        changed = m.freeze_draft(self.run, b'New complete draft with qualified comparison.\n', b'{"comparison":"unknown"}',
                                  '2036-01-01T10:03:00Z', expected_head_sha256=recorded['head_sha256'], parent_draft_id=draft['draft_id'])
        with self.assertRaises(ValueError): m.record_review(self.run, doc, reviewer_mode='self_native', expected_head_sha256=changed['head_sha256'])
        state = m.verify(self.run); self.assertEqual(state['workflow_state'], 'REVIEW_REQUIRED')
        self.assertEqual(state['reviews'][0]['document']['reviews'][0]['status'], 'OMITTED')
        self.assertEqual(len(state['drafts']), 2)

    def test_adverse_final_disposition_is_visible_not_auto_satisfied(self):
        created = self.boot(); draft = self.draft(created)
        recorded = m.record_review(self.run, self.document(created, draft, 'OMITTED'), reviewer_mode='self_native', expected_head_sha256=draft['head_sha256'])
        final = m.select_final(self.run, draft['draft_id'], expected_head_sha256=recorded['head_sha256'])
        self.assertEqual(final['disposition']['final_status'], 'DELIVERED_WITH_LIMITATIONS')
        self.assertIn('OMITTED', (self.run / 'delivery-notice.md').read_text())

    def test_retained_manifest_tampering_or_protocol_inventory_edit_refuses(self):
        created = self.boot(); manifest = self.run / 'bootstrap-manifest.json'; raw = manifest.read_bytes(); manifest.write_bytes(raw + b' ')
        with self.assertRaises(ValueError): m.verify(self.run, created['head_sha256'])
        manifest.write_bytes(raw); protocol = self.run / 'protocol.json'; p = json.loads(protocol.read_bytes()); p['units'][0]['required_source_ids'].pop(); protocol.write_bytes(m.encode(p))
        with self.assertRaises(ValueError): m.verify(self.run)

    def test_actual_cli_bootstrap_and_wrong_action_options(self):
        command = [sys.executable, '-B', str(Path(m.__file__)), 'bootstrap', '--run', str(self.run),
                   '--request', str(self.original / 'request.txt'), '--request-sha256', m.review.sha(self.request),
                   '--source-manifest', str(self.manifest_path), '--manifest-sha256', m.review.sha(self.manifest_raw),
                   '--source-root', str(self.original), '--adopted-at', '2036-01-01T10:00:00Z']
        result = subprocess.run(command, capture_output=True); self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout); m.verify(self.run, value['head_sha256'])
        wrong = subprocess.run([sys.executable, '-B', str(Path(m.__file__)), 'verify', '--run', str(self.run), '--source-root', str(self.original)], capture_output=True)
        self.assertEqual(wrong.returncode, 2); self.assertIn(b'BOOTSTRAP_OPTIONS_REQUIRE_BOOTSTRAP_ACTION', wrong.stdout)

if __name__ == '__main__': unittest.main(verbosity=2)
