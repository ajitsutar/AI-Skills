"""Atomic publication path support without guessed host length limits."""
import errno
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import institutional_research as research
import review_packet
import test_review_packet as packet_tests


def exact_length_directory(root, length):
    target = root.resolve()
    if length < len(str(target / 'd')):
        raise ValueError('TEST_REQUIRES_A_SHORT_SCRATCH_ROOT')
    while len(str(target)) < length:
        # Bound individual names while allowing shorter roots to need several
        # components. Account for an existing filesystem-root separator too.
        difference = length - len(str(target / 'd')) + 1
        width = min(difference, 200)
        if difference - width == 1:
            width -= 1  # Leave room for both a separator and the final name.
        target = target / ('d' * width)
        target.mkdir()
    assert len(str(target)) == length
    return target


def extended_fixture_paths(extended_root):
    base = extended_root / ('a' * 100)
    target = base
    while len(str(target)) <= 260:
        target = target / ('b' * 100)
    return base, target


class ExactLengthDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='path-builder-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def backing(self, name):
        root = Path('\\\\?\\' + str(self.root)) if os.name == 'nt' else self.root
        branch = root / name
        branch.mkdir()
        self.addCleanup(shutil.rmtree, branch)
        return branch

    def logical_posix(self, logical, name):
        # This is a logical POSIX spelling, not a claimed native Linux run.
        # Every mkdir still creates the same bounded component on this host.
        backing = self.backing(name)
        created = []
        class LogicalPosixDirectory:
            def __init__(self, spelling, physical):
                self.spelling, self.physical = PurePosixPath(spelling), physical
            def resolve(self): return self
            def __str__(self): return str(self.spelling)
            def __truediv__(self, component):
                return LogicalPosixDirectory(self.spelling / component, self.physical / component)
            def mkdir(self):
                self.physical.mkdir()
                created.append(self.physical)
        return LogicalPosixDirectory(logical, backing), created

    def test_short_logical_posix_roots_create_exact_223_with_real_bounded_components(self):
        for length in (17, 18, 21, 22, 23):
            with self.subTest(root_length=length):
                root, created = self.logical_posix('/tmp/pub-' + 'x' * (length - 9), 'root-' + str(length))
                target = exact_length_directory(root, 223)
                self.assertEqual(len(str(root)), length)
                self.assertEqual(len(str(target)), 223)
                self.assertTrue(target.physical.is_dir())
                self.assertTrue(created)
                self.assertTrue(all(path.is_dir() and 1 <= len(path.name) <= 200 for path in created))
                if length < 22: self.assertGreater(len(created), 1)

    def test_logical_posix_component_boundaries_leave_room_for_final_separator(self):
        for padding in (1, 2, 199, 200, 201, 202, 400, 401, 402):
            with self.subTest(padding=padding):
                root, created = self.logical_posix('/tmp/pub-xxxxxxxx', 'padding-' + str(padding))
                target = exact_length_directory(root, 17 + 1 + padding)
                self.assertEqual(len(str(target)), 17 + 1 + padding)
                self.assertTrue(target.physical.is_dir())
                self.assertTrue(all(1 <= len(path.name) <= 200 for path in created))
                if padding == 201: self.assertEqual([len(path.name) for path in created], [199, 1])

    def test_actual_native_root_builds_multiple_components_at_exact_length(self):
        root = self.backing('native')
        target_length = len(str(root)) + 403
        target = exact_length_directory(root, target_length)
        parts = target.relative_to(root).parts
        self.assertEqual(len(str(target)), target_length)
        self.assertTrue(target.is_dir())
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(1 <= len(part) <= 200 for part in parts))

    def test_logical_posix_filesystem_root_counts_its_existing_separator(self):
        root, created = self.logical_posix('/', 'filesystem-root')
        target = exact_length_directory(root, 223)
        self.assertEqual(len(str(target)), 223)
        self.assertTrue(target.physical.is_dir())
        self.assertTrue(all(1 <= len(path.name) <= 200 for path in created))

    def test_too_long_native_root_rejects_before_creating_any_directory(self):
        before = list(self.root.iterdir())
        for length in (len(str(self.root)) - 1, len(str(self.root)), len(str(self.root)) + 1):
            with self.subTest(target_length=length), self.assertRaisesRegex(ValueError, 'TEST_REQUIRES_A_SHORT_SCRATCH_ROOT'):
                exact_length_directory(self.root, length)
        self.assertEqual(list(self.root.iterdir()), before)

    def test_extended_fixture_exceeds_260_for_short_and_long_windows_roots(self):
        ci_root = PureWindowsPath('//?/C:/' + ('r' * 49))
        self.assertEqual(len(str(ci_root)), 56)  # Four-character prefix plus52.
        self.assertEqual(len(str(ci_root / ('a' * 100) / ('b' * 100))), 258)
        for root in (PureWindowsPath('//?/C:/'), ci_root,
                     PureWindowsPath('//?/C:/') / ('r' * 100) / ('s' * 100) / ('t' * 100)):
            with self.subTest(root=str(root)):
                base, target = extended_fixture_paths(root)
                self.assertEqual(base.parent, root)
                self.assertGreater(len(str(target)), 260)
                self.assertTrue(all(len(part) == 100 for part in target.relative_to(root).parts))
        self.assertEqual(len(str(extended_fixture_paths(ci_root)[1])), 359)


class PublicationPathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='pub-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_short_atomic_idempotent_conflict_and_compact_uuid_payload(self):
        names = {research._temporary_name() for _ in range(100)}
        self.assertEqual(len(names), 100)
        self.assertTrue(all(re.fullmatch(r'\.[A-Za-z0-9_-]{22}', name) for name in names))
        path = self.root / 'original.bin'
        research._publish(path, b'original')
        research._publish(path, b'original')
        with self.assertRaisesRegex(ValueError, 'IMMUTABLE_ARTIFACT_CONFLICT'):
            research._publish(path, b'replacement')
        self.assertEqual(path.read_bytes(), b'original')
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_real_261_character_old_temp_equivalent_uses_247_now(self):
        parent = exact_length_directory(self.root, 223)
        destination = parent / 'brief.bin'
        legacy = parent / ('.tmp-' + uuid.uuid4().hex)
        self.assertEqual(len(str(legacy)), 261)
        self.assertEqual(len(str(parent / research._temporary_name())), 247)
        self.assertLess(len(str(destination)), 247)
        # Observe this host rather than assuming every Windows host rejects261.
        created = False
        try:
            with legacy.open('xb'):
                created = True
        except OSError as error:
            self.assertTrue(isinstance(error, FileNotFoundError)
                            or error.errno == errno.ENAMETOOLONG or getattr(error, 'winerror', None) == 206)
        finally:
            if created:
                legacy.unlink()
        research._preflight_publications([destination])
        research._publish(destination, b'exact retained bytes')
        self.assertEqual(destination.read_bytes(), b'exact retained bytes')
        self.assertEqual(list(parent.iterdir()), [destination])

    def test_temp_collision_never_deletes_or_overwrites_an_unowned_file(self):
        fixed = uuid.UUID('01234567-89ab-4cde-8123-456789abcdef')
        with patch.object(research.uuid, 'uuid4', return_value=fixed):
            collision = self.root / research._temporary_name()
            collision.write_bytes(b'previous owner')
            with self.assertRaisesRegex(ValueError, 'TEMPORARY_NAME_COLLISIONS_NO_OVERWRITE'):
                research._publish(self.root / 'absent.bin', b'new')
        self.assertEqual(collision.read_bytes(), b'previous owner')
        self.assertEqual(list(self.root.iterdir()), [collision])

    def test_sync_or_hardlink_failure_preserves_original_error_and_cleans_temp(self):
        for name in ('fsync', 'link'):
            with self.subTest(operation=name), patch.object(research.os, name, side_effect=OSError('synthetic-resource-failure')):
                with self.assertRaisesRegex(OSError, 'synthetic-resource-failure'):
                    research._publish(self.root / 'absent.bin', b'new')
            self.assertEqual(list(self.root.iterdir()), [])

    def test_racing_final_destination_remains_create_only(self):
        path = self.root / 'raced.bin'
        def other_writer(source, destination):
            Path(destination).write_bytes(b'other writer')
            raise FileExistsError()
        with patch.object(research.os, 'link', side_effect=other_writer):
            with self.assertRaisesRegex(ValueError, 'IMMUTABLE_ARTIFACT_CONFLICT'):
                research._publish(path, b'our bytes')
        self.assertEqual(path.read_bytes(), b'other writer')
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_real_unsupported_component_has_actionable_error_and_no_artifact(self):
        first, unsupported = self.root / 'first.json', self.root / ('n' * 300)
        with self.assertRaisesRegex(ValueError, 'OUTPUT_PUBLICATION_PATH_UNAVAILABLE: choose a shorter existing private output root'):
            research._preflight_publications([first, unsupported])
        self.assertEqual(list(self.root.iterdir()), [])
        with self.assertRaisesRegex(ValueError, 'OUTPUT_PUBLICATION_PATH_UNAVAILABLE'):
            research._publish(unsupported, b'never committed')
        self.assertEqual(list(self.root.iterdir()), [])

    @unittest.skipUnless(os.name == 'nt', 'Native Windows invalid-name error control')
    def test_native_extended_unsupported_component_is_actionable_before_publication(self):
        extended = Path('\\\\?\\' + str(self.root.resolve()))
        unsupported = extended / ('n' * 300)
        with self.assertRaises(OSError):
            with unsupported.open('xb'):
                pass
        self.assertTrue(research._windows_invalid_path(unsupported))
        for operation in (research._preflight_publications,
                          lambda paths: research._publish(paths[0], b'never committed')):
            with self.assertRaisesRegex(ValueError, 'OUTPUT_PUBLICATION_PATH_UNAVAILABLE'):
                operation([unsupported])
            self.assertEqual(list(self.root.iterdir()), [])

    def test_valid_path_invalid_argument_is_not_relabelled_as_an_invalid_name(self):
        destination = self.root / 'retained.bin'
        for operation in ('metadata', 'open', 'link'):
            error = OSError(errno.EINVAL, 'synthetic non-path invalid argument')
            if operation == 'metadata':
                context = patch.object(Path, 'exists', side_effect=error)
            elif operation == 'open':
                context = patch.object(Path, 'open', side_effect=error)
            else:
                context = patch.object(research.os, 'link', side_effect=error)
            with self.subTest(operation=operation), context:
                with self.assertRaises(OSError) as raised:
                    if operation == 'link':
                        research._publish(destination, b'content')
                    else:
                        research._preflight_publications([destination])
                self.assertIs(raised.exception, error)
            self.assertEqual(list(self.root.iterdir()), [])

    def test_write_flush_and_fsync_invalid_argument_preserve_original_io_error(self):
        original_open = research._open_temporary
        for operation, native_error in ((op, code) for op in ('write', 'flush', 'fsync') for code in (None, 123)):
            error = OSError(errno.EINVAL, 'synthetic non-path ' + operation)
            if native_error is not None:
                error.winerror = native_error
            class FaultStream:
                def __init__(self, stream): self.stream = stream
                def __enter__(self): self.stream.__enter__(); return self
                def __exit__(self, *args): return self.stream.__exit__(*args)
                def write(self, data):
                    if operation == 'write': raise error
                    return self.stream.write(data)
                def flush(self):
                    if operation == 'flush': raise error
                    return self.stream.flush()
                def fileno(self): return self.stream.fileno()
            def faulty_open(parent, minimum_length=23):
                path, stream = original_open(parent, minimum_length)
                return path, FaultStream(stream)
            original_fsync = research.os.fsync
            def fsync(descriptor):
                if operation == 'fsync': raise error
                return original_fsync(descriptor)
            with self.subTest(operation=operation, winerror=native_error), patch.object(research, '_open_temporary', faulty_open), \
                    patch.object(research.os, 'fsync', fsync), \
                    patch.object(research, '_windows_invalid_path', return_value=True) as path_probe:
                with self.assertRaises(OSError) as raised:
                    research._publish(self.root / 'retained.bin', b'content')
                self.assertIs(raised.exception, error)
                path_probe.assert_not_called()
            self.assertEqual(list(self.root.iterdir()), [])

    @unittest.skipUnless(os.name == 'nt', 'Windows native error provenance controls')
    def test_native_path_error_codes_are_bounded_and_last_error_is_preserved(self):
        import ctypes
        from types import SimpleNamespace

        destination = self.root / 'retained.bin'
        for native_error in (123, 5, 87):
            error = OSError(errno.EINVAL, 'synthetic authoritative Windows error')
            error.winerror = native_error
            with self.subTest(authoritative=native_error), patch.object(Path, 'open', side_effect=error), \
                    patch.object(research, '_windows_invalid_path', side_effect=AssertionError('authoritative code must not be probed')):
                with self.assertRaises(ValueError if native_error == 123 else OSError) as raised:
                    research._preflight_publications([destination])
                if native_error == 123:
                    self.assertIn('OUTPUT_PUBLICATION_PATH_UNAVAILABLE', str(raised.exception))
                    self.assertIs(raised.exception.__cause__, error)
                else:
                    self.assertIs(raised.exception, error)
        previous = ctypes.get_last_error()
        self.addCleanup(ctypes.set_last_error, previous)
        for code in (2, 3, 5, 123, 206):
            error = OSError(errno.EINVAL, 'synthetic CRT error without winerror')
            def attributes(path):
                ctypes.set_last_error(code)
                return 0xFFFFFFFF
            with self.subTest(metadata_code=code), patch.object(Path, 'open', side_effect=error), \
                    patch.object(ctypes, 'WinDLL', return_value=SimpleNamespace(GetFileAttributesW=attributes)):
                ctypes.set_last_error(4321)
                with self.assertRaises(ValueError if code in (123, 206) else OSError) as raised:
                    research._preflight_publications([destination])
                self.assertEqual(ctypes.get_last_error(), 4321)
                if code in (123, 206):
                    self.assertIs(raised.exception.__cause__, error)
                else:
                    self.assertIs(raised.exception, error)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_journal_path_preflight_rejects_before_any_immutable_publication(self):
        original_open = Path.open
        def host_path_failure(path, mode='r', *args, **kwargs):
            if path.parent.name == 'commits' and mode == 'xb':
                raise FileNotFoundError(errno.ENOENT, 'synthetic host path limit', str(path))
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', host_path_failure), patch.object(research, '_publish', wraps=research._publish) as publisher:
            with self.assertRaisesRegex(ValueError, 'OUTPUT_PUBLICATION_PATH_UNAVAILABLE'):
                research._record(self.root, 'original', 'first_response', b'original bytes', {})
        self.assertEqual(publisher.call_count, 0)
        self.assertEqual([p for p in self.root.rglob('*') if p.is_file()], [])
        # Removing the host failure permits the original operation and recovery.
        original = research._record(self.root, 'original', 'first_response', b'original bytes', {})
        self.assertEqual(research._recover(self.root, 'original'), original)

    @unittest.skipUnless(os.name == 'nt', 'Windows explicit extended-path positive control')
    def test_explicit_supported_long_path_host_is_not_rejected_by_a_blanket_cap(self):
        absolute = str(self.root.resolve())
        extended = Path('\\\\?\\' + absolute)
        long_base, long_root = extended_fixture_paths(extended)
        long_root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, long_base)
        self.assertGreater(len(str(long_root)), 260)
        destination = long_root / 'retained.bin'
        research._preflight_publications([destination])
        research._publish(destination, b'long-path retained bytes')
        research._publish(destination, b'long-path retained bytes')
        self.assertEqual(destination.read_bytes(), b'long-path retained bytes')
        journal = long_root / 'journal'; journal.mkdir()
        first = research._record(journal, 'first', 'first_response', b'original', {})
        self.assertEqual(research._recover(journal, 'first'), first)


class PacketPathTests(unittest.TestCase):
    setUp = packet_tests.ReviewPacketTests.setUp
    add = packet_tests.ReviewPacketTests.add
    write = packet_tests.ReviewPacketTests.write
    analyze = packet_tests.ReviewPacketTests.analyze
    prepare = packet_tests.ReviewPacketTests.prepare
    def test_existing_identical_packet_needs_no_new_create_permission(self):
        first = self.prepare()
        original_open = Path.open
        def no_new_files(path, mode='r', *args, **kwargs):
            if mode == 'xb':
                raise PermissionError('synthetic read-only creation boundary')
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', no_new_files):
            repeated = self.prepare()
        self.assertEqual(first['packet_sha256'], repeated['packet_sha256'])
        self.assertTrue(repeated['dispatch_ready'])

    def test_packet_preflight_fails_before_any_packet_artifact_and_then_recovers(self):
        original_open = Path.open
        def unavailable_assisted_parent(path, mode='r', *args, **kwargs):
            if path.parent.name == 'brief_assisted' and mode == 'xb':
                raise FileNotFoundError(errno.ENOENT, 'synthetic host path limit', str(path))
            return original_open(path, mode, *args, **kwargs)
        with patch.object(Path, 'open', unavailable_assisted_parent), patch.object(research, '_publish', wraps=research._publish) as publisher:
            with self.assertRaisesRegex(ValueError, 'OUTPUT_PUBLICATION_PATH_UNAVAILABLE'):
                self.prepare()
        self.assertEqual(publisher.call_count, 0)
        self.assertEqual([p for p in self.output.rglob('*') if p.is_file()], [])
        result = self.prepare()
        self.assertTrue(result['dispatch_ready'])
        self.assertEqual(review_packet.verify(result['packet_directory'], result['packet_sha256'])['integrity_status'], 'VERIFIED')

    @unittest.skipUnless(os.name == 'nt', 'Windows explicit extended-path packet positive control')
    def test_complete_packet_under_supported_extended_long_output_root(self):
        extended = Path('\\\\?\\' + str(self.output.resolve()))
        long_base, self.output = extended_fixture_paths(extended)
        self.output.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, long_base)
        self.assertGreater(len(str(self.output)), 260)
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(first['packet_sha256'], second['packet_sha256'])
        self.assertTrue(first['dispatch_ready'])
        self.assertEqual(review_packet.verify(first['packet_directory'], first['packet_sha256'])['integrity_status'], 'VERIFIED')


if __name__ == '__main__':
    unittest.main()
