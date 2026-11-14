"""Synthetic offline packet support, separation, clock and byte controls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import institutional_research as research
import review_packet as module


class ReviewPacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='offline-review-packet-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'sources'; self.source.mkdir()
        self.output = self.root / 'private'; self.output.mkdir()
        self.manifest = self.source / 'ingress.json'; self.request_path = self.source / 'request.json'
        self.sources = {}
        criterion = {'id': 'decision-quality', 'criterion': 'Identify and qualify one material decision-relevant evidence gap.',
                     'assessment_kind': 'evidence_review', 'required_roles': ['source_inputs', 'identity_coverage']}
        self.add('protocol', {'id': 'synthetic-protocol', 'adopted_at': '2026-10-01T13:00:00Z', 'revision': 1,
                              'case_ids': ['synthetic-case'], 'criteria': [criterion]})
        protocol_pin = self.sources['protocol']['sha256']
        self.add('roster', {'protocol_sha256': protocol_pin, 'case_ids': ['synthetic-case']})
        self.add('inputs', 'Synthetic original source evidence; no participant answer.')
        self.add('neutral', 'Review the supplied research evidence and disclose unresolved gaps.')
        self.add('brief', 'Exact retained synthetic brief: identity and costs require qualification.')
        self.add('selection', {'case_id': 'synthetic-case', 'scope': 'Explicit fictional issuer; not all-market discovery',
                               'selection_method': 'Prespecified fictional issuer and retained input set.',
                               'status': 'COMPLETE_DECLARED_SCOPE', 'source_ids': ['inputs']})
        self.add('identity', {'case_id': 'synthetic-case', 'scope': 'Supplied fictional issuer mapping', 'status': 'MATCHED_DECLARED_IDENTITY', 'source_ids': ['inputs']})
        self.add('cutoff', {'source_cutoff_at': '2026-10-01T14:30:00Z'})
        self.add('decision', {'decision_at': '2026-10-01T14:32:00Z'})
        stable = {'id': 'first-response-v1', 'kind': 'first_response', 'object_sha256': self.sources['brief']['sha256'],
                  'bytes': len(self.sources['brief']['raw']), 'metadata': {'parent_id': 'synthetic-protocol'}}
        entry = {**stable, 'recorded_at': '2026-10-01T14:31:00Z'}
        self.add('entry', entry)
        self.add('transaction', {'schema_version': 1, 'idempotency_key': research._digest(stable), 'entry': entry})
        self.add('commit', {'id': entry['id'], 'entry_sha256': self.sources['entry']['sha256'], 'object_sha256': self.sources['brief']['sha256']})
        self.add('capture', {'entry_source_id': 'entry', 'transaction_source_id': 'transaction', 'commit_source_id': 'commit', 'object_source_id': 'brief'})
        self.add('criteria', {'protocol_sha256': protocol_pin, 'criteria': [criterion]})
        self.request = {'schema_version': 1, 'packet_id': 'synthetic-review', 'case_id': 'synthetic-case', 'revision': 1,
                        'review_at': '2026-10-02T15:00:00Z', 'adopted_protocol_sha256': protocol_pin, 'evidence': []}
        for role, sid in [('adopted_protocol', 'protocol'), ('registered_roster', 'roster'), ('source_inputs', 'inputs'),
                          ('neutral_instructions', 'neutral'), ('brief', 'brief'), ('selection_coverage', 'selection'),
                          ('identity_coverage', 'identity'), ('source_cutoff', 'cutoff'), ('decision_clocks', 'decision'),
                          ('original_response_capture', 'capture'), ('scoring_criteria', 'criteria')]:
            allowed = module.ARMS if role in {'source_inputs', 'neutral_instructions'} else ['brief_assisted'] if role == 'brief' else []
            at = '2026-10-01T14:31:00Z' if role in {'brief', 'original_response_capture'} else '2026-10-01T14:32:00Z' if role == 'decision_clocks' else '2026-10-01T13:00:00Z'
            self.request['evidence'].append({'id': role, 'role': role, 'source_id': sid, 'allowed_arms': allowed, 'available_at': at})
        self.write()

    def add(self, sid, value):
        raw = module.encode(value) if isinstance(value, dict) else value.encode()
        self.sources[sid] = {'raw': raw, 'sha256': hashlib.sha256(raw).hexdigest(), 'format': 'json' if isinstance(value, dict) else 'text'}

    def write(self):
        entries = []
        for sid, source in self.sources.items():
            path = sid + '.bin'; (self.source / path).write_bytes(source['raw'])
            entries.append({'id': sid, 'path': path, 'format': source['format'], 'sha256': source['sha256']})
        self.manifest.write_bytes(module.encode({'schema_version': 1, 'sources': entries}))
        self.pin = module.raw_hash(self.manifest.read_bytes())
        self.request_path.write_bytes(module.encode(self.request))

    def analyze(self):
        return module.analyze(self.request, self.manifest, self.pin, self.source)

    def prepare(self):
        self.write()
        return module.prepare(self.request_path, self.manifest, self.pin, self.source, self.output)

    def test_complete_packet_seals_exact_arm_bytes_and_replays_idempotently(self):
        result = self.prepare()
        self.assertTrue(result['dispatch_ready']); self.assertEqual(result['integrity_status'], 'VERIFIED')
        self.assertFalse(result['scored_criterion_verdicts_produced'])
        self.assertEqual(result['review_at'], self.request['review_at'])
        self.assertEqual(result['adopted_protocol_sha256'], self.request['adopted_protocol_sha256'])
        self.assertEqual(result['registered_case_ids'], ['synthetic-case'])
        folder = Path(result['packet_directory'])
        only = {p.name for p in (folder / 'participants/source_only').iterdir()}
        assisted = {p.name for p in (folder / 'participants/brief_assisted').iterdir()}
        self.assertEqual(only, {'source_inputs.bin', 'neutral_instructions.bin'})
        self.assertEqual(assisted, only | {'brief.bin'})
        self.assertEqual((folder / 'participants/brief_assisted/brief.bin').read_bytes(), self.sources['brief']['raw'])
        self.assertEqual(result['packet_sha256'], self.prepare()['packet_sha256'])
        for arm in module.ARMS:
            for item in only:
                self.assertEqual((folder / 'participants' / arm / item).read_bytes(), (folder / 'participants/source_only' / item).read_bytes())

    def test_remove_each_required_role_remains_unassessed(self):
        original = deepcopy(self.request)
        for role in module.REQUIRED:
            self.request = deepcopy(original)
            self.request['evidence'] = [x for x in self.request['evidence'] if x['role'] != role]
            with self.subTest(role=role):
                result = self.analyze()
                self.assertFalse(result['dispatch_ready'])
                self.assertIn('MISSING_ROLE:' + role, result['issues'])
                self.assertTrue(all(row['score'] is None for row in result['criterion_coverage']))

    def test_changed_common_original_or_participant_bytes_detected(self):
        (self.source / 'inputs.bin').write_bytes(b'Changed common input')
        with self.assertRaisesRegex(ValueError, 'INGRESS_SOURCE_HASH_MISMATCH'):
            self.analyze()
        self.write(); result = self.prepare(); folder = Path(result['packet_directory'])
        (folder / 'participants/source_only/source_inputs.bin').write_bytes(b'Changed after seal')
        with self.assertRaisesRegex(ValueError, 'SEALED_PACKET_BYTES_CHANGED'):
            module.verify(folder, result['packet_sha256'])

    def test_original_journal_binding_and_actual_decision_clocks_required(self):
        self.add('commit', {'id': 'first-response-v1', 'entry_sha256': '0' * 64, 'object_sha256': self.sources['brief']['sha256']})
        self.write(); result = self.analyze()
        self.assertIn('ORIGINAL_RESPONSE_JOURNAL_BINDING_MISMATCH', result['issues'])
        self.add('decision', {'decision_at': '2026-10-01T14:30:30Z'})
        self.write(); self.assertIn('ORIGINAL_RESPONSE_CLOCK_ORDER_UNESTABLISHED', self.analyze()['issues'])

    def test_composes_native_journal_with_fractional_metadata(self):
        from datetime import datetime, timezone
        from unittest.mock import patch
        class FixedClock:
            @staticmethod
            def now(_):
                return datetime(2026, 10, 1, 14, 31, tzinfo=timezone.utc)
        journal = self.root / 'native-journal'; journal.mkdir()
        with patch.object(research, 'datetime', FixedClock):
            research._record(journal, 'first-response-v1', 'first_response', self.sources['brief']['raw'],
                             {'fractional_metadata': 12.5, 'parent_id': 'synthetic-protocol'})
        for sid, section in [('entry', 'entries'), ('transaction', 'transactions'), ('commit', 'commits')]:
            raw = (journal / section / 'first-response-v1.json').read_bytes()
            self.sources[sid] = {'raw': raw, 'sha256': module.raw_hash(raw), 'format': 'json'}
        self.write(); self.assertTrue(self.analyze()['dispatch_ready'])

    def test_protocol_mismatch_and_unsupported_claims_unassessed(self):
        self.add('criteria', {'protocol_sha256': '0' * 64, 'criteria': [
            {'id': 'edge', 'criterion': 'Establish actual profitable edge.', 'assessment_kind': 'investment_efficacy', 'required_roles': ['source_inputs']}]})
        self.write(); result = self.analyze()
        self.assertIn('PROTOCOL_REVISION_MISMATCH:scoring_criteria', result['issues'])
        self.assertEqual(result['criterion_coverage'][0]['status'], 'UNASSESSED')
        self.assertIsNone(result['criterion_coverage'][0]['score'])

    def test_late_evidence_requires_new_review_preserving_original(self):
        result = self.prepare(); folder = Path(result['packet_directory']); original = (folder / 'packet.json').read_bytes()
        next(x for x in self.request['evidence'] if x['role'] == 'source_inputs')['available_at'] = '2026-10-01T14:33:00Z'
        self.write()
        with self.assertRaisesRegex(ValueError, 'IMMUTABLE_ARTIFACT_CONFLICT'):
            self.prepare()
        self.request.update(revision=2, parent_packet_sha256=result['packet_sha256'])
        revised = self.prepare()
        self.assertFalse(revised['dispatch_ready']); self.assertIn('POST_CUTOFF_EVIDENCE:source_inputs', revised['issues'])
        self.assertEqual((folder / 'packet.json').read_bytes(), original)
        self.assertTrue(module.verify(folder, result['packet_sha256'])['dispatch_ready'])

    def test_declared_arm_leaks_private_roles_and_known_answer_bytes_refused(self):
        original = deepcopy(self.request)
        for role in ('private_contact', 'runtime_configuration'):
            self.request = deepcopy(original); self.request['evidence'][0]['role'] = role
            with self.subTest(role=role), self.assertRaisesRegex(ValueError, 'PRIVATE_RUNTIME_EVIDENCE_REFUSED'):
                self.analyze()
        self.request = deepcopy(original)
        next(x for x in self.request['evidence'] if x['role'] == 'brief')['allowed_arms'] = module.ARMS
        with self.assertRaisesRegex(ValueError, 'ARM_INPUT_POLICY_VIOLATION'):
            self.analyze()
        self.request = deepcopy(original)
        self.add('answer', 'A known forbidden answer is not a source input.')
        self.request['evidence'].append({'id': 'answer', 'role': 'source_only_answer', 'source_id': 'answer', 'allowed_arms': [], 'available_at': '2026-10-02T14:00:00Z'})
        self.add('inputs', 'A known forbidden answer is not a source input. Copied into another file.')
        self.write(); self.assertIn('KNOWN_ANSWER_OR_FUTURE_OUTCOME_LEAK:source_inputs', self.analyze()['issues'])

    def test_brief_alias_in_source_only_detected(self):
        self.add('inputs', self.sources['brief']['raw'].decode())
        self.write(); self.assertIn('BRIEF_LEAKED_TO_SOURCE_ONLY:source_inputs', self.analyze()['issues'])

    def test_known_rubric_and_future_outcome_aliases_detected(self):
        self.add('inputs', self.sources['criteria']['raw'].decode())
        self.write(); self.assertIn('EVALUATOR_CRITERIA_LEAKED_TO_PARTICIPANT:source_inputs', self.analyze()['issues'])
        self.add('future', 'Exact future outcome: synthetic return is negative 10 percent.')
        self.request['evidence'].append({'id': 'future', 'role': 'future_outcomes', 'source_id': 'future',
                                         'allowed_arms': [], 'available_at': '2026-10-02T14:00:00Z'})
        self.add('inputs', self.sources['future']['raw'].decode())
        self.write(); self.assertIn('KNOWN_ANSWER_OR_FUTURE_OUTCOME_LEAK:source_inputs', self.analyze()['issues'])

    def test_every_declared_evaluator_only_role_alias_is_blocked(self):
        original = deepcopy(self.sources)
        evaluator = [x for x in self.request['evidence'] if not x['allowed_arms']]
        for item in evaluator:
            self.sources = deepcopy(original)
            protected = self.sources[item['source_id']]['raw']
            self.add('inputs', protected.decode())
            self.write()
            with self.subTest(role=item['role']):
                result = self.analyze()
                self.assertFalse(result['dispatch_ready'])
                self.assertIn('source_inputs', result['blocked_participant_evidence_ids'])
                self.assertTrue(any('EVALUATOR_ONLY_EVIDENCE_LEAKED_TO_PARTICIPANT:source_inputs:' + item['role'] in code
                                    for code in result['issues']))
                self.assertTrue(all('source_inputs' not in {x['evidence_id'] for x in items}
                                    for items in result['participants'].values()))
        self.sources = original
        self.write(); self.assertTrue(self.analyze()['dispatch_ready'])

    def test_native_journal_metadata_alias_and_embedded_protocol_are_blocked(self):
        original = deepcopy(self.sources)
        for sid in ('entry', 'transaction', 'commit', 'protocol'):
            self.sources = deepcopy(original)
            raw = self.sources[sid]['raw']
            self.add('inputs', ('Prefix of a disguised source\n' + raw.decode() + '\nSuffix'))
            self.write()
            with self.subTest(source=sid):
                result = self.analyze()
                self.assertFalse(result['dispatch_ready'])
                self.assertIn('source_inputs', result['blocked_participant_evidence_ids'])

    def test_protocol_alias_never_materializes_in_prepared_participant_files(self):
        # Retains the original independent review's exact second-ID/path attack.
        protocol_raw = self.sources['protocol']['raw']
        self.add('inputs', protocol_raw.decode())
        prepared = self.prepare(); folder = Path(prepared['packet_directory'])
        self.assertEqual(prepared['status'], 'UNASSESSED')
        self.assertFalse(prepared['dispatch_ready'])
        self.assertEqual(prepared['integrity_status'], 'VERIFIED')
        self.assertEqual((folder / 'sealed/inputs.bin').read_bytes(), protocol_raw)
        for arm in module.ARMS:
            self.assertFalse((folder / 'participants' / arm / 'source_inputs.bin').exists())
        checked = module.verify(folder, prepared['packet_sha256'])
        self.assertFalse(checked['dispatch_ready'])
        self.assertEqual(checked['blocked_participant_evidence_ids'], ['source_inputs'])

    def test_unselected_common_source_and_missing_selection_method_unassessed(self):
        self.add('selection', {'case_id': 'synthetic-case', 'scope': 'Retained explicit scope.', 'source_ids': ['protocol']})
        self.write(); result = self.analyze()
        self.assertFalse(result['dispatch_ready'])
        self.assertIn('PARTICIPANT_INPUT_OUTSIDE_RETAINED_SELECTION', result['issues'])
        self.assertIn('SELECTION_METHOD_UNESTABLISHED', result['issues'])

    def test_path_escape_and_mocked_reparse_rejected_before_source_read(self):
        value = json.loads(self.manifest.read_bytes()); value['sources'][0]['path'] = '../unrelated-file'
        self.manifest.write_bytes(module.encode(value)); pin = module.raw_hash(self.manifest.read_bytes())
        with self.assertRaisesRegex(ValueError, 'BOUNDED_RELATIVE_PATH_REQUIRED'):
            module.analyze(self.request, self.manifest, pin, self.source)
        from unittest.mock import patch
        real_stat = Path.stat
        class Reparse:
            st_file_attributes = 0x400
            st_mode = real_stat(self.source / 'inputs.bin').st_mode
        target = self.source / 'inputs.bin'
        def controlled_stat(path, *args, **kwargs):
            if path == target:
                return Reparse()
            return real_stat(path, *args, **kwargs)
        with patch.object(Path, 'stat', controlled_stat), self.assertRaisesRegex(ValueError, 'LINK_OR_REPARSE_POINT_REFUSED'):
            module.no_links(target)

    def test_timing_missing_is_unassessed_never_zero(self):
        self.add('criteria', {'protocol_sha256': self.request['adopted_protocol_sha256'], 'criteria': [
            {'id': 'elapsed', 'criterion': 'Retain actual measured machine review duration.', 'assessment_kind': 'machine_duration', 'required_roles': ['machine_review_timing']}]})
        self.write(); result = self.analyze()
        self.assertFalse(result['dispatch_ready'])
        self.assertEqual(result['criterion_coverage'][0]['missing_roles'], ['machine_review_timing'])
        self.assertIsNone(result['criterion_coverage'][0]['score'])

    def test_measured_timing_and_explicit_assisted_provenance(self):
        criterion = {'id': 'measured', 'criterion': 'Retain actually measured machine durations with explicit clocks.',
                     'assessment_kind': 'machine_duration', 'required_roles': ['machine_review_timing']}
        protocol = json.loads(self.sources['protocol']['raw']); protocol['criteria'] = [criterion]
        self.add('protocol', protocol); pin = self.sources['protocol']['sha256']
        self.request['adopted_protocol_sha256'] = pin
        roster = json.loads(self.sources['roster']['raw']); roster['protocol_sha256'] = pin
        self.add('roster', roster); self.add('criteria', {'protocol_sha256': pin, 'criteria': [criterion]})
        timing = {'measurement': 'actual_machine_duration',
                  'source_only': {'started_at': '2026-10-02T14:00:00Z', 'finished_at': '2026-10-02T14:01:00Z'},
                  'brief_assisted': {'started_at': '2026-10-02T14:02:00Z', 'finished_at': '2026-10-02T14:03:00Z'}}
        self.add('timing', timing); self.add('provenance', {'retained_brief_sha256': self.sources['brief']['sha256']})
        self.request['evidence'].extend([
            {'id': 'timing', 'role': 'machine_review_timing', 'source_id': 'timing', 'allowed_arms': [], 'available_at': '2026-10-02T14:03:00Z'},
            {'id': 'provenance', 'role': 'provenance_metadata', 'source_id': 'provenance', 'allowed_arms': ['brief_assisted'], 'available_at': '2026-10-01T14:31:00Z'}])
        self.write(); result = self.analyze()
        self.assertTrue(result['dispatch_ready'])
        self.assertNotIn('provenance', {x['evidence_id'] for x in result['participants']['source_only']})
        self.assertIn('provenance', {x['evidence_id'] for x in result['participants']['brief_assisted']})
        timing['source_only']['finished_at'] = '2026-10-03T14:00:00Z'
        self.add('timing', timing); self.write(); result = self.analyze()
        self.assertFalse(result['dispatch_ready'])
        self.assertIn('MACHINE_MEASUREMENT_NOT_AVAILABLE_AT_REVIEW:source_only', result['criterion_coverage'][0]['issues'])

    def test_parent_pin_missing_and_unrelated_extra_files_refused(self):
        self.request['revision'] = 2
        with self.assertRaisesRegex(ValueError, 'SHA256_REQUIRED'):
            self.analyze()
        self.request['revision'] = 1; result = self.prepare(); folder = Path(result['packet_directory'])
        (folder / 'unlisted-answer.txt').write_text('Unlisted file cannot enter a verified packet.')
        with self.assertRaisesRegex(ValueError, 'PACKET_FILE_INVENTORY_MISMATCH'):
            module.verify(folder, result['packet_sha256'])

    def test_protocol_revision_retains_predecessor_and_later_adoption(self):
        first = self.prepare(); prior_hash = self.request['adopted_protocol_sha256']
        protocol = json.loads(self.sources['protocol']['raw'])
        protocol.update(revision=2)
        def replace_protocol():
            self.add('protocol', protocol)
            pin = self.sources['protocol']['sha256']; self.request['adopted_protocol_sha256'] = pin
            for sid in ('roster', 'criteria'):
                value = json.loads(self.sources[sid]['raw']); value['protocol_sha256'] = pin
                self.add(sid, value)
            self.request.update(revision=2, parent_packet_sha256=first['packet_sha256'])
        replace_protocol()
        with self.assertRaisesRegex(ValueError, 'CHANGED_PROTOCOL_MUST_RETAIN_PREDECESSOR'):
            self.prepare()
        protocol.update(predecessor_protocol_sha256=prior_hash)
        replace_protocol()
        # Same adoption clock cannot silently adopt a materially new protocol.
        with self.assertRaisesRegex(ValueError, 'CHANGED_PROTOCOL_REQUIRES_NEW_ADOPTION_CLOCK'):
            self.prepare()
        protocol['adopted_at'] = '2026-10-01T13:30:00Z'
        replace_protocol(); revised = self.prepare()
        self.assertTrue(revised['dispatch_ready'])
        self.assertTrue(module.verify(first['packet_directory'], first['packet_sha256'])['dispatch_ready'])

    def test_empty_common_input_unassessed(self):
        self.add('inputs', ' ')
        self.write(); result = self.analyze()
        self.assertFalse(result['dispatch_ready'])
        self.assertIn('EMPTY_PARTICIPANT_EVIDENCE:source_inputs', result['issues'])

    def test_cli_offline_prepare_and_verify(self):
        script = Path(module.__file__)
        command = [sys.executable, '-B', str(script), 'prepare', '--request', str(self.request_path),
                   '--manifest', str(self.manifest), '--manifest-sha256', self.pin, '--source-root', str(self.source),
                   '--private-output-root', str(self.output)]
        prepared = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        result = json.loads(prepared.stdout)
        verified = subprocess.run([sys.executable, '-B', str(script), 'verify', '--packet-directory', result['packet_directory'],
                                   '--packet-sha256', result['packet_sha256']], capture_output=True, text=True)
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertTrue(json.loads(verified.stdout)['dispatch_ready'])


if __name__ == '__main__':
    unittest.main()
