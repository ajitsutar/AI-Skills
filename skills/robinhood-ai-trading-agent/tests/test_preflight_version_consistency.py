import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import research_preflight as preflight


class VersionConsistencyTests(unittest.TestCase):
    def check_package(self, skill, version='5.1.2', manifest_version='5.1.2'):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'SKILL.md').write_text(skill, encoding='utf-8')
            (root / 'VERSION').write_text(version, encoding='utf-8')
            files = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                     for name in ('SKILL.md', 'VERSION')}
            (root / 'PACKAGE-MANIFEST.json').write_text(json.dumps(dict(version=manifest_version, files=files)), encoding='utf-8')
            with patch.object(preflight, 'ROOT', root):
                return preflight.package_integrity()

    def test_rehashed_stale_header_is_still_invalid(self):
        result = self.check_package('Package version: **5.1.1 - October 23, 2026**.')
        self.assertEqual(result['status'], 'INVALID')
        self.assertEqual(result['errors'], ['SKILL_PACKAGE_VERSION_MISMATCH'])

    def test_history_examples_and_quoted_labels_do_not_change_active_version(self):
        result = self.check_package('Package version: **5.1.2 - October 24, 2026**.\n'
              'Historical version 4.15.1 is retained.\n> Package version: 4.15.1\n'
              '```markdown\nPackage version: 4.15.2\n```\n'
              '~~~\nPackage version: 4.15.3\n~~~\n')
        self.assertEqual(result['status'], 'VERIFIED')

    def test_missing_multiple_and_invalid_active_labels_block(self):
        cases = [('Historical version 5.1.2', 'SKILL_PACKAGE_VERSION_MISSING'),
                 ('Package version: 5.1.2\nPackage version: 5.1.2', 'SKILL_PACKAGE_VERSION_MULTIPLE'),
                 ('Package version: 5.1.2\nPackage version: 5.1.1', 'SKILL_PACKAGE_VERSION_MISMATCH'),
                 ('Package version: forthcoming', 'SKILL_PACKAGE_VERSION_INVALID'),
                 ('Package version: 5.1.2.9', 'SKILL_PACKAGE_VERSION_INVALID')]
        for text, expected in cases:
            with self.subTest(text=text):
                result = self.check_package(text)
                self.assertEqual(result['status'], 'INVALID')
                self.assertIn(expected, result['errors'])

    def test_manifest_and_version_still_must_match(self):
        result = self.check_package('Package version: 5.1.2', manifest_version='5.1.1')
        self.assertIn('VERSION_MISMATCH', result['errors'])


if __name__ == '__main__':
    unittest.main()
