#!/usr/bin/env python3
"""Regression checks for independently copied skill packages."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import validate_portability as validator


class StandalonePackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / "concert-ticket-checkout"
        shutil.copytree(validator.SKILLS_DIR / self.skill.name, self.skill)

    def test_copied_skill_needs_no_repository_or_plugin(self):
        with patch.object(validator, "ROOT", self.root / "missing-repository"):
            validator.validate_skill(self.skill)

    def test_standalone_copy_must_preserve_license_and_notices(self):
        for name in ("LICENSE", "PROVENANCE.md", "THIRD-PARTY-NOTICES.md"):
            with self.subTest(name=name):
                path = self.skill / name
                original = path.read_bytes()
                path.unlink()
                try:
                    with self.assertRaisesRegex(validator.ValidationError, "standalone notice"):
                        validator.validate_skill(self.skill)
                finally:
                    path.write_bytes(original)

    def test_empty_license_cannot_count_as_preserved_permission(self):
        (self.skill / "LICENSE").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(validator.ValidationError, "standalone notice"):
            validator.validate_skill(self.skill)

    def test_existing_reference_outside_skill_is_rejected(self):
        (self.root / "shared.md").write_text("Not bundled", encoding="utf-8")
        with (self.skill / "INSTALL.md").open("a", encoding="utf-8") as stream:
            stream.write("\n[Shared instructions](../shared.md)\n")
        with self.assertRaisesRegex(validator.ValidationError, "escapes"):
            validator.validate_skill(self.skill)

    def test_missing_local_reference_is_rejected(self):
        with (self.skill / "INSTALL.md").open("a", encoding="utf-8") as stream:
            stream.write("\n[Required helper](scripts/not-bundled.py)\n")
        with self.assertRaisesRegex(validator.ValidationError, "broken local link"):
            validator.validate_skill(self.skill)

    def test_standalone_agent_cannot_require_repository_namespace(self):
        agent = next((self.skill / "agents").glob("*.md"))
        text = agent.read_text(encoding="utf-8").replace(
            '- "concert-ticket-checkout"', '- "ai-skills:concert-ticket-checkout"')
        agent.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(validator.ValidationError, "expected preload"):
            validator.validate_skill(self.skill)

    def test_plugin_and_standalone_agent_cannot_drift(self):
        agent = next((self.skill / "agents").glob("*.md"))
        with agent.open("a", encoding="utf-8") as stream:
            stream.write("\nDifferent instructions\n")
        with self.assertRaisesRegex(validator.ValidationError, "drifted"):
            validator.validate_skill(self.skill)

    def test_missing_manifest_resource_is_rejected(self):
        manifest = {"files": {"missing.py": "0" * 64}, "version": "1.0.0"}
        (self.skill / "PACKAGE-MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(validator.ValidationError, "inventory"):
            validator.validate_skill(self.skill)


if __name__ == "__main__":
    unittest.main()
