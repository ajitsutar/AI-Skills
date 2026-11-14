"""Atomic publication path support without guessed host length limits."""
import errno
import os
from pathlib import Path
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
    root = root.resolve()
    difference = length - len(str(root)) - 1
    if not 1 <= difference <= 200:
        raise ValueError('TEST_REQUIRES_A_SHORT_SCRATCH_ROOT')
    target = root / ('d' * difference)
    target.mkdir()
    assert len(str(target)) == length
    return target


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
        long_base = extended / ('a' * 100)
        long_root = long_base / ('b' * 100)
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
        long_base = extended / ('p' * 100)
        self.output = long_base / ('q' * 100)
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
