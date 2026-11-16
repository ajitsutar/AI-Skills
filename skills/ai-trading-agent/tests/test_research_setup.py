"""Workflow setup records actual local probes without promoting host declarations."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import research_setup as module


class ResearchSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'release.html'
        self.source.write_bytes(b'<p>Fictional supplied source.</p>')
        self.preflight = {'package_integrity': {'status': 'VERIFIED'},
                          'dependencies': {'yfinance': {'status': 'UNAVAILABLE'}}}
        self.stub = patch.object(module.research_preflight, 'check', return_value=self.preflight)
        self.check = self.stub.start()
        self.addCleanup(self.stub.stop)

    def test_optional_dependencies_do_not_block_supplied_source_lane(self):
        result = module.setup('earnings_guidance', self.root / 'setup',
                              sources=[self.source], host='Codex', declared_tools=['browser'])
        self.assertEqual(result['status'], 'READY_FOR_LOCAL_EVIDENCE_PREPARATION')
        self.check.assert_called_once_with()
        self.assertEqual(result['sources'][0]['sha256'], module.hashlib.sha256(self.source.read_bytes()).hexdigest())
        self.assertEqual(result['native_tools'], [{'name': 'browser', 'status': 'DECLARED_NOT_TESTED'}])
        self.assertEqual(result['private_output']['status'], 'WRITE_READ_REMOVE_OBSERVED')
        self.assertFalse((self.root / 'setup' / 'write-probe.tmp').exists())
        self.assertFalse(result['execution_authorized'])

    def test_missing_source_preserves_attempt_and_one_changed_input_retry(self):
        first = module.setup('event_research', self.root / 'failed-source',
                             sources=[self.root / 'missing.html'])
        self.assertEqual(first['status'], 'LIMITED_SETUP')
        self.assertEqual(first['sources'][0]['status'], 'UNAVAILABLE')
        self.assertEqual(first['bounded_recovery']['maximum_new_setup_attempts'], 1)
        raw = (self.root / 'failed-source' / 'setup.json').read_bytes()
        second = module.setup('event_research', self.root / 'supplied-source', sources=[self.source])
        self.assertEqual(second['status'], 'READY_FOR_LOCAL_EVIDENCE_PREPARATION')
        self.assertEqual((self.root / 'failed-source' / 'setup.json').read_bytes(), raw)

    def test_invalid_package_cannot_be_reported_ready(self):
        self.preflight['package_integrity']['status'] = 'INVALID'
        result = module.setup('earnings_guidance', self.root / 'invalid-package', sources=[self.source])
        self.assertEqual(result['status'], 'LIMITED_SETUP')
        self.assertIn('PACKAGE_INTEGRITY_UNVERIFIED', [r['issue'] for r in result['bounded_recovery']['steps']])

    def test_missing_workflow_module_has_truthful_native_fallback(self):
        with patch.object(module.importlib, 'import_module', side_effect=ImportError('missing optional runtime')):
            result = module.setup('options_activity', self.root / 'missing-helper', sources=[self.source])
        self.assertEqual(result['status'], 'LIMITED_SETUP')
        self.assertEqual(result['workflow_modules'][0]['status'], 'UNAVAILABLE')
        self.assertIn('WORKFLOW_HELPER_UNAVAILABLE', [r['issue'] for r in result['bounded_recovery']['steps']])

    def test_actual_refresh_and_options_integrations_are_available(self):
        for workflow in ('refresh', 'options_activity'):
            with self.subTest(workflow=workflow):
                result = module.setup(workflow, self.root / workflow, sources=[self.source])
                self.assertEqual(result['status'], 'READY_FOR_LOCAL_EVIDENCE_PREPARATION')
                self.assertTrue(all(r['status'] == 'IMPORTABLE_CALLABLES_PRESENT'
                                    for r in result['workflow_modules']))

    def test_existing_output_and_skill_directory_are_never_reused(self):
        existing = self.root / 'existing'; existing.mkdir()
        marker = existing / 'retained.txt'; marker.write_text('retain')
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT'):
            module.setup('event_research', existing)
        self.assertEqual(marker.read_text(), 'retain')
        with self.assertRaisesRegex(ValueError, 'NEW_PRIVATE_OUTPUT'):
            module.setup('event_research', ROOT / 'forbidden-output')
        self.check.assert_not_called()

    def test_fixture_invokes_existing_session_and_extraction_not_host_equivalence(self):
        result = module.exercise(self.root / 'fixture', host='Codex Windows')
        self.assertEqual(result['status'], 'LOCAL_SETUP_AND_PACKET_OBSERVED')
        self.assertEqual(result['packet_status'], 'EVIDENCE_WITH_LIMITATIONS')
        packet = json.loads((self.root / 'fixture/session/packet.json').read_bytes())
        self.assertEqual(len(packet['filing_extractions']), 1)
        self.assertFalse(result['full_answer_or_review_demonstrated'])
        self.assertFalse(result['live_acquisition_demonstrated'])
        self.assertFalse(result['other_hosts_demonstrated'])
        self.assertEqual(len(result['session_sha256']), 64)
        self.assertEqual(len(result['packet_sha256']), 64)

    def test_failed_fixture_keeps_source_and_failure_receipt(self):
        with patch.object(module.research_session, 'prepare_packet', side_effect=ValueError('fixture failure')):
            result = module.exercise(self.root / 'failed-fixture')
        self.assertEqual(result['status'], 'FIXTURE_FAILED')
        self.assertTrue((self.root / 'failed-fixture/fictional-release.html').is_file())
        self.assertTrue((self.root / 'failed-fixture/session/session.json').is_file())
        self.assertEqual(json.loads((self.root / 'failed-fixture/exercise.json').read_bytes())['status'], 'FIXTURE_FAILED')


if __name__ == '__main__':
    unittest.main()
