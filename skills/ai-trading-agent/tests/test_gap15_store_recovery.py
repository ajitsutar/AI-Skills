"""Crash recovery and live exclusion on real component stores, using fictional streams."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import research_data_store
from research_data_store import Store, validate_request


def request(symbol):
    return {
        'provider': 'fixture', 'security_id': symbol, 'provider_symbol': symbol,
        'start': '2030-01-01', 'end': '2030-01-04', 'adjustment': 'unadjusted',
        'schema_version': '1', 'parser_version': '1', 'fields': ['Close'],
        'source_role': 'native_response', 'vintage': 'original',
    }


def hold_captures(store, control, symbols):
    if symbols == ['DISPATCH']:
        dispatch = store._dispatch

        @contextmanager
        def pause_after_dispatch():
            with dispatch():
                (control / 'DISPATCH.ready').touch()
                sys.stdin.buffer.read(1)
                yield

        with patch.object(store, '_dispatch', pause_after_dispatch):
            store.capture(request('DISPATCH'), lambda: [b'test'])
        return
    if symbols == ['PUBLISH']:
        write = research_data_store.atomic_json

        def pause_after_owner(path, *args, **kwargs):
            result = write(path, *args, **kwargs)
            if path.name == 'owner.json':
                (control / 'PUBLISH.ready').touch()
                sys.stdin.buffer.read(1)
            return result

        with patch.object(research_data_store, 'atomic_json', pause_after_owner):
            store.capture(request('PUBLISH'), lambda: [b'test'])
        return
    release = threading.Event()

    def capture(symbol):
        def stream():
            (control / (symbol + '.ready')).touch()
            release.wait()
            yield b'completed capture'
        return store.capture(request(symbol), stream)

    with ThreadPoolExecutor(max_workers=len(symbols)) as pool:
        futures = [pool.submit(capture, symbol) for symbol in symbols]
        try:
            sys.stdin.buffer.read(1)
        finally:
            release.set()
        for future in futures:
            future.result()


@contextmanager
def child_collector(root, control, symbols, limit=4):
    # A Windows venv launcher can start a second process. Hold a direct handle
    # to the process doing the stdlib-only captures, so kill() targets its owner.
    executable = sys._base_executable if os.name == 'nt' else sys.executable
    cmd = [executable, '-X', 'utf8', '-B', str(Path(__file__).resolve()),
           '--child', str(root), str(control), str(limit), *symbols]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                          stderr=subprocess.PIPE) as child:
        try:
            deadline = time.monotonic() + 15
            while any(not (control / (name + '.ready')).exists() for name in symbols):
                if child.poll() is not None:
                    raise RuntimeError(child.stderr.read().decode(errors='replace'))
                if time.monotonic() >= deadline:
                    raise TimeoutError('Collector did not enter all requested captures')
                time.sleep(.02)
            yield child
        finally:
            if child.poll() is None:
                try:
                    _, error = child.communicate(b'Q', timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate()
                    raise
                if child.returncode:
                    raise RuntimeError(error.decode(errors='replace'))


class StoreRecoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.control = Path(temp.name).resolve()
        self.root = self.control / 'store'
        self.store = Store(self.root, 'fixture', create=True, min_free_bytes=0)

    def test_resume_after_four_real_interrupted_captures(self):
        saved = self.store.capture(request('SAVED'), lambda: [b'prior completed record'])
        symbols = ['ONE', 'TWO', 'THREE', 'FOUR']
        with child_collector(self.root, self.control, symbols) as child:
            locks = [validate_request(request(symbol)) for symbol in symbols]
            self.assertTrue(all((self.root / 'locks' / (key + '.lock')).is_dir() for key in locks))
            child.kill()
            child.wait(timeout=10)

        target = self.control / 'request.json'
        target.write_text(json.dumps(request(symbols[0])), encoding='utf-8')
        payload = self.control / 'source.txt'
        payload.write_bytes(b'newly completed record')
        cli = subprocess.run(
            [sys.executable, '-X', 'utf8', '-B', str(SCRIPTS / 'research_data_store.py'),
             '--root', str(self.root), '--owner', 'fixture', 'capture-file', '--request',
             str(target), '--input', str(payload), '--resume'],
            capture_output=True, text=True, timeout=20)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        output = json.loads(cli.stdout)
        self.assertEqual(output['request_id'], locks[0])
        self.assertEqual(output['lock_recovery']['count'], 4)
        self.assertCountEqual(output['lock_recovery']['keys'], locks)
        receipts = list((self.root / 'attempts').glob('lock-recovery-*.json'))
        self.assertEqual(len(receipts), 4)
        durable = [json.loads(path.read_bytes()) for path in receipts]
        self.assertCountEqual([row['key'] for row in durable], locks)
        for row in durable:
            self.assertEqual((row['status'], row['pid']), ('RECLAIMED', child.pid))
            self.assertGreaterEqual(row['age_seconds'], 0)
        for key in locks:
            self.assertIn(key, cli.stderr)
        self.assertEqual(self.store.read_bytes(self.store.read_record(locks[0])), payload.read_bytes())
        self.assertEqual(self.store.read_record(saved['request_id']), saved)
        self.assertTrue(all(not (self.root / 'locks' / (key + '.lock')).exists() for key in locks))
        for symbol in symbols[1:]:
            self.store.capture(request(symbol), lambda: [b'complete'], resume=True)
        self.assertEqual(len(self.store.verify()['records']), 5)

    def test_completed_capture_releases_its_key_while_another_process_holds_dispatch(self):
        target = request('FINISHED')
        key = validate_request(target)
        with ExitStack() as workers:
            def produce():
                workers.enter_context(child_collector(self.root, self.control, ['DISPATCH']))
                yield b'completed before the other dispatcher resumed'

            record = self.store.capture(target, produce)
            self.assertEqual(self.store.read_record(key), record)
            self.assertFalse((self.root / 'locks' / (key + '.lock')).exists())

        def unexpected_fetch():
            self.fail('A finished capture should resume from its saved bytes')

        self.assertEqual(self.store.capture(target, unexpected_fetch, resume=True), record)

    def test_reader_of_owner_metadata_does_not_strand_a_completed_capture(self):
        target = request('READER')
        key = validate_request(target)
        lock = self.root / 'locks' / (key + '.lock')
        with ExitStack() as readers:
            def produce():
                reader = readers.enter_context((lock / 'owner.json').open('rb'))
                self.assertEqual(json.load(reader)['key'], key)
                yield b'completed despite the open metadata reader'

            record = self.store.capture(target, produce)
            self.assertEqual(self.store.read_record(key), record)

            # This reader may still keep one directory from retiring on Windows.
            # Other requests with available slots must continue to make progress.
            other = self.store.capture(request('SEPARATE'), lambda: [b'other completed record'])
            self.assertEqual(self.store.read_record(other['request_id']), other)

        def unexpected_fetch():
            self.fail('Reopening a completed capture should use its verified record')

        self.assertEqual(self.store.capture(target, unexpected_fetch, resume=True), record)
        self.assertFalse(lock.exists())

    def test_two_live_processes_enforce_bound_and_maintenance_exclusion(self):
        competing = Store(self.root, 'fixture', max_active_captures=2, min_free_bytes=0)
        with child_collector(self.root, self.control, ['LEFT'], limit=2):
            with child_collector(self.root, self.control, ['RIGHT'], limit=2):
                with self.assertRaisesRegex(ValueError, 'ACTIVE_CAPTURE_LIMIT'):
                    competing.capture(request('EXTRA'), lambda: [b'unexpected'], resume=True)
                with self.assertRaisesRegex(ValueError, 'CAPTURE_OR_MAINTENANCE_ACTIVE'):
                    with competing.lock('maintenance'):
                        self.fail('Maintenance entered while both collectors were active')
                for symbol in ['LEFT', 'RIGHT']:
                    key = validate_request(request(symbol))
                    self.assertTrue((self.root / 'locks' / (key + '.lock')).is_dir())
        self.assertEqual(len(competing.verify()['records']), 2)
        with competing.lock('maintenance'):
            with self.assertRaisesRegex(ValueError, 'CAPTURE_OR_MAINTENANCE_ACTIVE'):
                competing.capture(request('AFTER'), lambda: [b'unexpected'])

    def test_owner_record_and_uncertain_owners_survive_resume(self):
        symbol = 'UNCERTAIN'
        key = validate_request(request(symbol))
        directory = self.root / 'locks' / (key + '.lock')
        with child_collector(self.root, self.control, [symbol]) as child:
            original = json.loads((directory / 'owner.json').read_text(encoding='utf-8'))
            self.assertEqual(original['pid'], child.pid)
            self.assertEqual(original['hostname'].casefold(), socket.gethostname().casefold())
            self.assertEqual(original['owner'], 'fixture')
            self.assertEqual(original['store_id'], self.store.identity['store_id'])
            self.assertEqual(original['key'], key)
            self.assertIsNotNone(datetime.fromisoformat(original['started_at']).utcoffset())
            child.kill()
            child.wait(timeout=10)

        for altered in [dict(original, hostname='another-host.invalid'),
                        dict(original, store_id='another-store'), {'pid': child.pid}]:
            with self.subTest(altered_fields=sorted(altered)):
                contents = json.dumps(altered)
                (directory / 'owner.json').write_text(contents, encoding='utf-8')
                competing = Store(self.root, 'fixture', min_free_bytes=0, max_active_captures=1)
                with self.assertRaises((ValueError, RuntimeError)):
                    competing.capture(request('NEW'), lambda: [b'unexpected'], resume=True)
                self.assertEqual((directory / 'owner.json').read_text(encoding='utf-8'), contents)
                self.assertEqual(competing.recovery_summary()['count'], 0)

    def test_interruption_inside_dispatch_does_not_wedge_next_process(self):
        with child_collector(self.root, self.control, ['DISPATCH']) as child:
            dispatch = self.root / 'locks' / 'dispatch.lock'
            self.assertTrue(dispatch.is_file())
            child.kill()
            child.wait(timeout=10)
        resumed = Store(self.root, 'fixture', min_free_bytes=0)
        completed = resumed.capture(request('NEXT'), lambda: [b'recovered'], resume=True)
        self.assertEqual(resumed.read_bytes(completed), b'recovered')
        self.assertFalse(dispatch.exists())

    def test_unrecognized_dispatch_file_is_preserved(self):
        dispatch = self.root / 'locks' / 'dispatch.lock'
        dispatch.write_bytes(b'opaque foreign content')
        with self.assertRaises((ValueError, RuntimeError)):
            self.store.capture(request('NEXT'), lambda: [b'unexpected'], resume=True)
        self.assertEqual(dispatch.read_bytes(), b'opaque foreign content')

    def test_interruption_before_owner_publication_does_not_occupy_capture_slot(self):
        with child_collector(self.root, self.control, ['PUBLISH'], limit=1) as child:
            key = validate_request(request('PUBLISH'))
            self.assertFalse((self.root / 'locks' / (key + '.lock')).exists())
            child.kill()
            child.wait(timeout=10)
        resumed = Store(self.root, 'fixture', min_free_bytes=0, max_active_captures=1)
        completed = resumed.capture(request('PUBLISH'), lambda: [b'after restart'], resume=True)
        self.assertEqual(resumed.read_bytes(completed), b'after restart')

    def test_reused_pid_does_not_preserve_dead_owners_slot(self):
        symbol = 'REUSED'
        key = validate_request(request(symbol))
        record_path = self.root / 'locks' / (key + '.lock') / 'owner.json'
        with child_collector(self.root, self.control, [symbol]) as child:
            owner = json.loads(record_path.read_bytes())
            if not owner.get('process_start'):
                self.skipTest('Host does not expose process creation identity')
            child.kill()
            child.wait(timeout=10)
        # Model the OS reassigning the PID after a crash. The parent is alive
        # with a different process creation identity. All other fields are genuine.
        owner['pid'] = os.getpid()
        record_path.write_text(json.dumps(owner), encoding='utf-8')
        reopened = Store(self.root, 'fixture', min_free_bytes=0, max_active_captures=1)
        reopened.capture(request(symbol), lambda: [b'resumed'], resume=True)
        self.assertEqual(reopened.recovery_summary()['records'][0]['reason'], 'PID_REUSED')

    def test_ownerless_legacy_lock_requires_both_age_and_confirmed_idle_writers(self):
        key = validate_request(request('OLD'))
        existing = self.root / 'locks' / (key + '.lock')
        existing.mkdir()
        plain = Store(self.root, 'fixture', min_free_bytes=0, max_active_captures=1)
        confirmed = Store(self.root, 'fixture', min_free_bytes=0, max_active_captures=1,
                          legacy_writers_stopped=True)
        for store in [plain, confirmed]:
            with self.assertRaises((ValueError, RuntimeError)):
                store.capture(request('FRESH'), lambda: [b'unexpected'], resume=True)
            self.assertTrue(existing.is_dir())
        old_time = time.time() - 48 * 3600
        os.utime(existing, (old_time, old_time))
        with self.assertRaises((ValueError, RuntimeError)):
            plain.capture(request('FRESH'), lambda: [b'unexpected'], resume=True)
        self.assertTrue(existing.is_dir())
        confirmed.capture(request('FRESH'), lambda: [b'ok'], resume=True)
        self.assertFalse(existing.exists())
        self.assertEqual(confirmed.recovery_summary()['keys'], [key])


if __name__ == '__main__':
    if sys.argv[1:2] == ['--child']:
        root, control, limit, *symbols = sys.argv[2:]
        owner = json.loads((Path(root) / 'RESEARCH-STORE.json').read_bytes())['owner']
        hold_captures(Store(Path(root), owner, min_free_bytes=0, max_active_captures=int(limit)),
                      Path(control), symbols)
    else:
        unittest.main()
