#!/usr/bin/env python3
"""Scan this repository for common export-safety mistakes."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THIS_FILE = Path(__file__).resolve()

FORBIDDEN_EXTENSIONS = {
    ".env",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".mp3",
    ".m4a",
    ".wav",
    ".flac",
    ".aac",
    ".ogg",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".ckpt",
    ".onnx",
    ".pth",
    ".pt",
    ".safetensors",
    ".ass",
    ".srt",
    ".lrc",
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
}

TEXT_PATTERNS = [
    (
        "private key block",
        re.compile(r"BEGIN (?:RSA |OPENSSH |DSA |EC |PGP |ENCRYPTED )?PRIVATE KEY"),
    ),
    ("OpenAI-style key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("GitHub token", re.compile(r"(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]+)")),
    ("Anthropic-style key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{30,}")),
    ("GitLab token", re.compile(r"glpat-[A-Za-z0-9_-]{20,}")),
    ("npm token", re.compile(r"npm_[A-Za-z0-9]{20,}")),
    ("Stripe live secret", re.compile(r"sk_live_[A-Za-z0-9]{16,}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]+")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("bearer token", re.compile(r"bearer\s+[A-Za-z0-9._-]{16,}", re.IGNORECASE)),
    ("authorization header", re.compile(r"authorization\s*:", re.IGNORECASE)),
    ("API key assignment", re.compile(r"api[_-]?key\s*[:=]", re.IGNORECASE)),
    ("client secret assignment", re.compile(r"client[_-]?secret\s*[:=]", re.IGNORECASE)),
    ("password assignment", re.compile(r"(password|passwd|pwd)\s*[:=]", re.IGNORECASE)),
    ("personal email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("local user path", re.compile(r"(C:\\Users\\|/Users/|/home/)", re.IGNORECASE)),
]


def is_skipped(path: Path) -> bool:
    resolved = path.resolve()
    if resolved == THIS_FILE:
        return True
    parts = set(path.relative_to(ROOT).parts)
    return ".git" in parts or "__pycache__" in parts


def is_probably_text(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
        return True
    except UnicodeDecodeError:
        return False


def scan() -> list[str]:
    findings: list[str] = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or is_skipped(path):
            continue

        rel = path.relative_to(ROOT)
        suffixes = {suffix.lower() for suffix in path.suffixes}
        if suffixes & FORBIDDEN_EXTENSIONS and not path.name.casefold().endswith(".env.example"):
            findings.append(f"forbidden extension: {rel}")
            continue

        if not is_probably_text(path):
            findings.append(f"binary or non-utf8 file: {rel}")
            continue

        text = path.read_text(encoding="utf-8")
        for label, pattern in TEXT_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append(f"{label}: {rel}:{line_no}")
    return findings


def main() -> int:
    findings = scan()
    if findings:
        print("Safety scan found possible issues:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Safety scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
