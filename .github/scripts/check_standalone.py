#!/usr/bin/env python3
"""Copy each skill alone and run its existing offline checks from an unrelated cwd.

Maintainer/CI tooling only: nothing in a skill imports or calls this script.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from validate_portability import validate_skill

ROOT = Path(__file__).resolve().parents[2]
PYTHON_TESTS = {
    "create-guitar-karaoke": ["scripts/test_build_guitar_karaoke.py"],
    "create-karaoke-video": ["scripts/test_create_karaoke_video.py"],
    "deal-watch-alerts": ["scripts/test_deal_memory.py"],
    "travel-deal-finder": ["scripts/test_rank_offers.py"],
}
JS_TESTS = {
    "linkedin-knowledge-digest": [
        "scripts/test_linkedin_candidates.js", "scripts/test_linkedin_scan_orchestrator.js",
        "scripts/test_linkedin_digest_delivery.js",
    ],
}


def check(source: Path, structure_only: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="standalone-skill-") as temp:
        isolated = Path(temp)
        copied = isolated / source.name
        # Validate symlinks before copying; never dereference a hidden dependency.
        validate_skill(source)
        shutil.copytree(source, copied, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        validate_skill(copied)
        cwd = isolated / "unrelated-working-directory"
        cwd.mkdir()
        if not structure_only:
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            commands = [[sys.executable, "-X", "utf8", "-B", str(copied / test)]
                        for test in PYTHON_TESTS.get(source.name, [])]
            for test in JS_TESTS.get(source.name, []):
                node = shutil.which("node")
                if not node:
                    raise RuntimeError("Node is required to test the LinkedIn skill")
                commands.append([node, str(copied / test)])
            if source.name == "robinhood-ai-trading-agent":
                commands.append([sys.executable, "-X", "utf8", "-B", "-m", "unittest",
                                 "discover", "-s", str(copied / "tests"), "-v"])
            for command in commands:
                subprocess.run(command, cwd=cwd, env=env, check=True)
        print(f"STANDALONE COPY PASSED: {source.name}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structure-only", action="store_true",
                        help="Check copied resources and metadata without running helper tests")
    args = parser.parse_args()
    for source in sorted((ROOT / "skills").iterdir()):
        if source.is_dir():
            check(source, args.structure_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
