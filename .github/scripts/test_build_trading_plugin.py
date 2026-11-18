#!/usr/bin/env python3
"""Regression checks for deterministic plugin generation and safe refusal."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import build_trading_plugin as builder


class TradingPluginBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / builder.SKILL
        self.source.mkdir(parents=True)
        self.files = {'VERSION': b'5.13.12\n', 'SKILL.md': b'Fictional test instructions\n',
                      'README.md': b'Test guide\n', 'INSTALL.md': b'Test setup\n',
                      'EXAMPLE-PROMPTS.md': b'Test prompts\n', 'scripts/calculate.py': b'print(2 + 2)\n'}
        for name, data in self.files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.refresh_source_manifest()
        listing = self.root / 'docs/ai-trading-agent'
        (listing / 'assets').mkdir(parents=True)
        self.listing_path = listing / 'plugin.json'
        self.listing = {'name': 'ai-trading-agent', 'version': '5.13.12'}
        self.listing_path.write_text(json.dumps(self.listing), encoding='utf-8')
        for name in builder.ICONS:
            (listing / 'assets' / name).write_bytes(b'\x89PNG\r\n\x1a\n' + name.encode())
        (self.root / 'LICENSE').write_bytes(b'Test license\n')
        self.destination = self.root / builder.DESTINATION

    def refresh_source_manifest(self):
        doc = {'version': self.files['VERSION'].decode().strip(),
               'files': {name: hashlib.sha256(data).hexdigest() for name, data in self.files.items()}}
        (self.source / 'PACKAGE-MANIFEST.json').write_text(json.dumps(doc), encoding='utf-8')

    def test_build_preserves_sources_and_repeated_check_is_read_only(self):
        count = builder.build(self.root, check=False)
        self.assertEqual(count, len(self.files) + 6)
        for name, data in self.files.items():
            self.assertEqual((self.destination / builder.SKILL / name).read_bytes(), data)
        before = {p.relative_to(self.destination): p.read_bytes() for p in self.destination.rglob('*') if p.is_file()}
        self.assertEqual(builder.build(self.root, check=True), count)
        self.assertEqual(builder.build(self.root, check=False), count)
        after = {p.relative_to(self.destination): p.read_bytes() for p in self.destination.rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_check_rejects_missing_or_changed_outputs_without_repairing(self):
        builder.build(self.root, check=False)
        changed = self.destination / builder.SKILL / 'README.md'
        changed.write_bytes(b'Changed locally\n')
        missing = self.destination / 'LICENSE'
        missing.unlink()
        with self.assertRaisesRegex(builder.BuildError, 'stale'):
            builder.build(self.root, check=True)
        self.assertEqual(changed.read_bytes(), b'Changed locally\n')
        self.assertFalse(missing.exists())
        builder.build(self.root, check=False)
        self.assertEqual(changed.read_bytes(), self.files['README.md'])
        self.assertTrue(missing.is_file())

    def test_unexpected_files_and_empty_directories_are_preserved_and_rejected(self):
        builder.build(self.root, check=False)
        extra = self.destination / 'personal-notes.txt'
        extra.write_bytes(b'Keep this file\n')
        (self.destination / 'unowned-empty-directory').mkdir()
        for check in (False, True):
            with self.subTest(check=check), self.assertRaisesRegex(builder.BuildError, 'Unexpected'):
                builder.build(self.root, check=check)
        self.assertEqual(extra.read_bytes(), b'Keep this file\n')
        self.assertTrue((self.destination / 'unowned-empty-directory').is_dir())

    def test_build_refuses_unmarked_preexisting_directory(self):
        self.destination.mkdir(parents=True)
        path = self.destination / 'README.md'
        path.write_bytes(b'Hand-maintained content\n')
        with self.assertRaisesRegex(builder.BuildError, 'generator marker'):
            builder.build(self.root, check=False)
        self.assertEqual(path.read_bytes(), b'Hand-maintained content\n')

    def test_listing_version_must_match_source_before_any_output_is_written(self):
        self.listing['version'] = '5.13.11'
        self.listing_path.write_text(json.dumps(self.listing), encoding='utf-8')
        with self.assertRaisesRegex(builder.BuildError, 'version differs'):
            builder.build(self.root, check=False)
        self.assertFalse(self.destination.exists())

    def test_canonical_hash_drift_is_rejected_before_copying(self):
        (self.source / 'scripts/calculate.py').write_bytes(b'print(999)\n')
        with self.assertRaisesRegex(builder.BuildError, 'hash mismatch'):
            builder.build(self.root, check=False)
        self.assertFalse(self.destination.exists())

    def test_unmanifested_canonical_file_is_rejected(self):
        (self.source / 'unreviewed.txt').write_text('Not in the canonical manifest', encoding='utf-8')
        with self.assertRaisesRegex(builder.BuildError, 'inventory differs'):
            builder.build(self.root, check=False)
        self.assertFalse(self.destination.exists())

    def test_future_version_update_remains_bound_to_canonical_bytes(self):
        builder.build(self.root, check=False)
        self.files['VERSION'] = b'5.13.13\n'
        (self.source / 'VERSION').write_bytes(self.files['VERSION'])
        self.refresh_source_manifest()
        self.listing['version'] = '5.13.13'
        self.listing_path.write_text(json.dumps(self.listing), encoding='utf-8')
        with self.assertRaisesRegex(builder.BuildError, 'stale'):
            builder.build(self.root, check=True)
        builder.build(self.root, check=False)
        self.assertEqual((self.destination / builder.SKILL / 'VERSION').read_bytes(), b'5.13.13\n')
        self.assertEqual(json.loads((self.destination / 'plugin.json').read_text())['version'], '5.13.13')
        builder.build(self.root, check=True)

    def create_symlink(self, link, target, *, directory=False):
        try:
            link.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f'Symlink creation unavailable: {exc}')

    def test_source_symlink_is_rejected(self):
        link = self.source / 'redirected.txt'
        self.create_symlink(link, self.source / 'README.md')
        with self.assertRaisesRegex(builder.BuildError, 'Symlink/reparse'):
            builder.build(self.root, check=False)

    def test_destination_parent_symlink_is_rejected(self):
        other = self.root / 'other'
        other.mkdir()
        self.create_symlink(self.root / 'plugins', other, directory=True)
        with self.assertRaisesRegex(builder.BuildError, 'Symlink/reparse'):
            builder.build(self.root, check=False)
        self.assertEqual(list(other.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
