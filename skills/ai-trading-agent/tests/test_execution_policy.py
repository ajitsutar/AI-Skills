"""Persistent execution policy settings, tested with local fictional files only."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from execution_policy import (SUPPORTED_MODES, read_policy, set_policy_mode, validate_policy_mode,
                              validate_task_policy, initialize_task_policy)


class ExecutionPolicyTests(unittest.TestCase):
    task_id = 'TASK-A'

    def read(self, path, task_id=None):
        return read_policy(path, self.task_id if task_id is None else task_id)

    def set(self, path, mode, create=False, task_id=None):
        return set_policy_mode(path, mode, self.task_id if task_id is None else task_id, create=create)

    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/execution_policy.py'),
                               *map(str, args), '--task-id', self.task_id], capture_output=True, text=True)

    def test_independent_tasks_initialize_paper_and_change_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = (Path(directory) / name for name in ('first.json', 'second.json'))
            for path, task in ((first, self.task_id), (second, 'TASK-B')):
                result = initialize_task_policy(path, task)
                self.assertEqual(read_policy(path, task),
                                 {'schema_version': 1, 'task_id': task, 'mode': 'paper'})
                self.assertEqual(result['kind'], 'EXECUTION_POLICY_INITIALIZATION')
                self.assertEqual(result['task_id'], task)
                self.assertEqual(result['policy_scope'], 'TASK')
                self.assertFalse(result['skill_submitted_order'])
            second_bytes = second.read_bytes()
            self.set(first, 'autonomous')
            self.assertEqual(self.read(first)['mode'], 'autonomous')
            self.assertEqual(read_policy(second, 'TASK-B')['mode'], 'paper')
            self.assertEqual(second.read_bytes(), second_bytes)

    def test_initialization_preserves_existing_task_setting_and_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            raw = b'{ "task_id":"TASK-A", "mode":"autonomous", "note":"keep" }\n'
            path.write_bytes(raw)
            result = initialize_task_policy(path, self.task_id)
            self.assertEqual(result['mode'], 'autonomous')
            self.assertFalse(result['policy_updated'])
            self.assertFalse(result['created'])
            self.assertIsNone(result['backup_path'])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_wrong_task_or_unbound_policy_never_reads_updates_or_initializes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            for policy in ({'mode': 'autonomous'}, {'task_id': 'TASK-B', 'mode': 'autonomous'},
                           {'task_id': self.task_id, 'mode': 'unsupported-mode'}):
                raw = json.dumps(policy).encode('utf-8'); path.write_bytes(raw)
                for operation in (lambda: self.read(path), lambda: self.set(path, 'paper'),
                                  lambda: initialize_task_policy(path, self.task_id)):
                    with self.assertRaises(ValueError):
                        operation()
                    self.assertEqual(path.read_bytes(), raw)
                    self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_invalid_or_missing_task_identifier_never_creates_or_infers_binding(self):
        policy = {'task_id': self.task_id, 'mode': 'paper'}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            for task in (None, '', ' ', ' TASK-A', 'TASK-A ', 'TASK\nA', False, 1):
                for operation in (lambda: validate_task_policy(policy, task),
                                  lambda: read_policy(path, task),
                                  lambda: initialize_task_policy(path, task),
                                  lambda: set_policy_mode(path, 'autonomous', task, create=True)):
                    with self.assertRaises(ValueError):
                        operation()
                self.assertEqual(list(Path(directory).iterdir()), [])
            for operation in (lambda: read_policy(path), lambda: initialize_task_policy(path),
                              lambda: set_policy_mode(path, 'autonomous', create=True)):
                with self.assertRaises(TypeError):
                    operation()

    def test_cli_initializes_task_and_requires_explicit_identifier(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            missing = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/execution_policy.py'),
                                      'init', str(path)], capture_output=True, text=True)
            self.assertEqual(missing.returncode, 2)
            self.assertFalse(path.exists())
            result = self.cli('init', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['mode'], 'paper')
            self.assertEqual(self.read(path)['task_id'], self.task_id)
            self.set(path, 'autonomous')
            before = path.read_bytes()
            result = self.cli('init', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['mode'], 'autonomous')
            self.assertEqual(path.read_bytes(), before)

    def test_exact_supported_mode_set_and_nested_values_cannot_select_mode(self):
        self.assertEqual(set(SUPPORTED_MODES), {'paper', 'approval', 'autonomous'})
        for mode in SUPPORTED_MODES:
            self.assertEqual(validate_policy_mode({'mode': mode}), mode)
        for value in (None, {}, [], 'autonomous', False, {'mode': True},
                      {'mode': 'unsupported-mode'}, {'mode': 'AUTONOMOUS'},
                      {'mode': ' autonomous '}, {'nested': {'mode': 'autonomous'}}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_policy_mode(value)

    def test_policy_values_must_be_finite_json(self):
        for value in (math.nan, math.inf, -math.inf, (1, 2), {1, 2}, object(), {1: 'x'}):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(ValueError):
                    validate_policy_mode({'mode': 'autonomous', 'extra': value})

    def test_read_rejects_malformed_duplicate_and_nonfinite_records(self):
        sources = ['{}', 'null', '[]', '{"mode":"unknown"}',
                   '{"mode":"paper","mode":"autonomous"}',
                   '{"mode":"paper","extra":{"x":1,"x":2}}',
                   '{"mode":"paper","amount":NaN}',
                   '{"mode":"paper","amount":Infinity}',
                   '{"mode":"paper","amount":1e9999}', '{broken}']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            for source in sources:
                path.write_text(source, encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.read(path)

    def test_missing_file_needs_explicit_create_and_invalid_create_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            with self.assertRaises(ValueError):
                self.read(path)
            with self.assertRaises(ValueError):
                self.set(path, 'autonomous')
            with self.assertRaises(ValueError):
                self.set(path, 'unsupported-mode', create=True)
            self.assertEqual(list(Path(directory).iterdir()), [])
            result = self.set(path, 'autonomous', create=True)
            self.assertTrue(result['created'])
            self.assertTrue(result['policy_updated'])
            self.assertIsNone(result['previous_mode'])
            self.assertIsNone(result['backup_path'])
            self.assertEqual(self.read(path), {'schema_version': 1, 'task_id': self.task_id, 'mode': 'autonomous'})
            self.assertFalse(result['skill_submitted_order'])

    def test_update_preserves_all_other_fields_and_exact_original_backup(self):
        original = {'schema_version': 3, 'task_id': self.task_id, 'mode': 'approval', 'account': 'FICTIONAL-ACCOUNT',
                    'limits': {'max_order_notional': '0013.3300', 'allow_leverage': False,
                               'unknown': None, 'count': 0},
                    'instructions': ['unchanged'], 'unicode_note': '\u20ac',
                    'nested': {'mode': 'paper'}}
        raw = ('\ufeff' + json.dumps(original, ensure_ascii=False, indent=4) + '\r\n').encode('utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            path.write_bytes(raw)
            result = self.set(path, 'autonomous')
            expected = copy.deepcopy(original); expected['mode'] = 'autonomous'
            self.assertEqual(self.read(path), expected)
            self.assertEqual(Path(result['backup_path']).read_bytes(), raw)
            self.assertEqual(result['previous_mode'], 'approval')
            self.assertFalse(result['created'])
            self.assertTrue(result['policy_updated'])
            self.assertFalse(result['external_permissions_changed'])
            self.assertEqual(result['scheduling_status'], 'NOT_CONFIGURED')

    def test_noop_set_preserves_bytes_and_does_not_create_backup(self):
        raw = b'{ "task_id" : "TASK-A", "mode" : "autonomous", "note" : "keep formatting" }\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'; path.write_bytes(raw)
            result = self.set(path, 'autonomous')
            self.assertEqual(path.read_bytes(), raw)
            self.assertFalse(result['policy_updated'])
            self.assertIsNone(result['backup_path'])
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_invalid_update_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            path.write_text('{"task_id":"TASK-A","mode":"paper","note":"keep"}', encoding='utf-8')
            raw = path.read_bytes()
            for mode in ('unsupported-mode', '', None, True):
                with self.assertRaises(ValueError):
                    self.set(path, mode)
                self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_malformed_existing_policy_is_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            raw = b'{"task_id":"TASK-A","mode":"paper","mode":"autonomous"}'
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.set(path, 'approval')
            self.assertEqual(path.read_bytes(), raw)

    def test_fresh_cli_process_observes_persisted_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            for index, mode in enumerate(('paper', 'autonomous', 'approval')):
                command = ('set', path, '--mode', mode) + (('--create',) if index == 0 else ())
                written = self.cli(*command)
                self.assertEqual(written.returncode, 0, written.stderr)
                observed = self.cli('show', path)
                self.assertEqual(observed.returncode, 0, observed.stderr)
                result = json.loads(observed.stdout)
                self.assertEqual(result['mode'], mode)
                self.assertEqual(result['policy']['mode'], mode)
                self.assertEqual(result['policy_source'], 'FILE')
                self.assertFalse(result['skill_submitted_order'])

    def test_show_redacts_private_fields_and_error_does_not_echo_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            path.write_text(json.dumps({'task_id': self.task_id, 'mode': 'autonomous', 'accountId': 'PRIVATE-ID',
                'routing': {'Authorization-Header': 'PRIVATE-TOKEN'}, 'limits': {'amount': '25.00'}}), encoding='utf-8')
            shown = self.cli('show', path)
            self.assertEqual(shown.returncode, 0, shown.stderr)
            self.assertNotIn('PRIVATE-', shown.stdout + shown.stderr)
            self.assertEqual(json.loads(shown.stdout)['policy']['limits']['amount'], '25.00')
            path.write_text('{"mode":"SECRET-MODE","token":"PRIVATE-TOKEN"}', encoding='utf-8')
            error = self.cli('show', path)
            self.assertEqual(error.returncode, 2)
            self.assertNotIn('PRIVATE-', error.stdout + error.stderr)
            self.assertNotIn('SECRET-MODE', error.stdout + error.stderr)
            self.assertNotIn('Traceback', error.stdout + error.stderr)

    def test_read_and_update_do_not_call_network_or_external_processes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            with patch('socket.socket', side_effect=AssertionError('No network')), \
                 patch('subprocess.run', side_effect=AssertionError('No subprocess')):
                self.set(path, 'paper', create=True)
                self.assertEqual(self.read(path)['mode'], 'paper')
                result = self.set(path, 'autonomous')
                self.assertFalse(result['skill_submitted_order'])

    def test_concurrent_external_edit_is_preserved_instead_of_overwritten(self):
        import execution_policy
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            original = b'{"task_id":"TASK-A","mode":"paper","note":"original"}'
            external = b'{"task_id":"TASK-A","mode":"approval","note":"concurrent editor"}'
            path.write_bytes(original)
            actual_read = execution_policy._read_bytes
            calls = []
            def changed_read(selected):
                if selected == path:
                    calls.append(selected)
                    if len(calls) == 2:
                        path.write_bytes(external)
                return actual_read(selected)
            with patch('execution_policy._read_bytes', side_effect=changed_read):
                with self.assertRaises(ValueError):
                    self.set(path, 'autonomous')
            self.assertEqual(path.read_bytes(), external)
            backups = list(Path(directory).glob('policy.json.backup-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertFalse(list(Path(directory).glob('.*')))

    def test_another_writer_lock_is_not_removed_or_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); path = folder / 'policy.json'
            path.write_bytes(b'{"task_id":"TASK-A","mode":"paper"}')
            lock = folder / '.policy.json.update.lock'; lock.write_bytes(b'other writer')
            with self.assertRaises(ValueError):
                self.set(path, 'autonomous')
            self.assertEqual(path.read_bytes(), b'{"task_id":"TASK-A","mode":"paper"}')
            self.assertEqual(lock.read_bytes(), b'other writer')

    def test_failed_atomic_replace_preserves_original_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'; original = b'{"task_id":"TASK-A","mode":"paper"}'
            path.write_bytes(original)
            with patch('execution_policy.os.replace', side_effect=OSError('fictional interruption')):
                with self.assertRaises(ValueError):
                    self.set(path, 'autonomous')
            self.assertEqual(path.read_bytes(), original)
            backups = list(Path(directory).glob('policy.json.backup-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertFalse(list(Path(directory).glob('.*')))

    def test_redirected_policy_path_refused_without_mutating_target(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); target = folder / 'target.json'; link = folder / 'link.json'
            target.write_text('{"task_id":"TASK-A","mode":"paper"}', encoding='utf-8'); before = target.read_bytes()
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest('This host cannot create a test symlink')
            with self.assertRaises(ValueError):
                self.read(link)
            with self.assertRaises(ValueError):
                self.set(link, 'autonomous')
            self.assertEqual(target.read_bytes(), before)

    def test_linked_ancestor_diagnostic_prevents_read_or_update(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory); path = folder / 'policy.json'
            path.write_bytes(b'{"task_id":"TASK-A","mode":"paper"}')
            before = path.read_bytes()
            with patch('execution_policy.Path.is_symlink', autospec=True,
                       side_effect=lambda selected: selected == folder):
                with self.assertRaises(ValueError):
                    self.read(path)
                with self.assertRaises(ValueError):
                    self.set(path, 'autonomous')
            self.assertEqual(path.read_bytes(), before)

    def test_risk_fixture_schemas_accept_the_same_three_mode_values(self):
        from risk_engine import validate_policy
        for template in ('policy.example.json', 'personal-policy.example.json'):
            original = json.loads((ROOT / 'templates' / template).read_text(encoding='utf-8'))
            for mode in SUPPORTED_MODES:
                with self.subTest(template=template, mode=mode):
                    policy = copy.deepcopy(original); policy['mode'] = mode
                    validate_policy(policy)
                    self.assertEqual(validate_policy_mode(policy), mode)


if __name__ == '__main__':
    unittest.main()
