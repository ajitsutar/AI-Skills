#!/usr/bin/env python3
"""Check that preserving a public upstream notice does not weaken export scanning."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import safety_scan


class PublicNoticeTests(unittest.TestCase):
    def setUp(self):
        self.name = next(iter(safety_scan.PUBLIC_LICENSE_EMAIL_EXCEPTIONS))
        self.notice = (safety_scan.ROOT / self.name).read_text(encoding="utf-8")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / self.name
        self.path.parent.mkdir(parents=True)

    def findings(self, text):
        self.path.write_text(text, encoding="utf-8")
        with patch.object(safety_scan, "ROOT", self.root):
            return safety_scan.scan()

    def test_exact_reviewed_notice_is_allowed(self):
        self.assertEqual(self.findings(self.notice), [])

    def test_windows_line_endings_are_allowed(self):
        self.path.write_bytes(self.notice.replace("\n", "\r\n").encode())
        with patch.object(safety_scan, "ROOT", self.root):
            self.assertEqual(safety_scan.scan(), [])

    def test_modified_notice_does_not_inherit_email_exception(self):
        extra = "\nprivate" + "@" + "example.invalid\n"
        self.assertTrue(any("personal email" in s for s in self.findings(self.notice + extra)))

    def test_same_content_at_other_path_is_not_exempt(self):
        (self.root / "unreviewed.txt").write_text(self.notice, encoding="utf-8")
        with patch.object(safety_scan, "ROOT", self.root):
            self.assertTrue(any("personal email" in s for s in safety_scan.scan()))

    def test_email_exception_never_disables_secret_detection(self):
        modified = self.notice + "\n" + "sk-" + "a" * 24 + "\n"
        digest = hashlib.sha256(modified.encode()).hexdigest()
        with patch.dict(safety_scan.PUBLIC_LICENSE_EMAIL_EXCEPTIONS, {self.name: digest}):
            self.assertTrue(any("OpenAI-style key" in s for s in self.findings(modified)))


if __name__ == "__main__":
    unittest.main()
