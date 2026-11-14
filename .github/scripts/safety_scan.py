#!/usr/bin/env python3
"""Scan this repository for common export-safety mistakes."""

from __future__ import annotations

import ast
import hashlib
import io
import json
import re
import sys
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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

# Only the exact reviewed upstream notice may contain these public author emails.
# Normalize line endings through read_text so the allowance survives Git checkout.
PUBLIC_LICENSE_EMAIL_EXCEPTIONS = {
    "skills/ai-trading-agent/ARCH-LICENSE.txt": "c6e622bd89db4e13315f4e91605ff96fcbb9012d78ee74e429855870b203eed6",
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


def sbom_package_identifier_spans(text: str, relative_path: str) -> list[tuple[int, int]]:
    """Recognize structured PyPI name@version identifiers, never arbitrary emails.

    Exact JSON string values must agree with a component's name, numeric release
    version, bom-ref and PyPI purl. Other fields and all other detectors still run.
    """
    profiles = {'windows-cp312-core', 'windows-cp312-data-quant'}
    allowed = {f'skills/ai-trading-agent/environments/{p}/sbom.cdx.json' for p in profiles}
    if relative_path not in allowed:
        return []
    try:
        document = json.loads(text)
        if not isinstance(document, dict) or document.get('bomFormat') != 'CycloneDX':
            return []
        identifiers = set()
        for component in document.get('components', []):
            if not isinstance(component, dict):
                continue
            name, version = component.get('name'), component.get('version')
            if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:[-_.][a-z0-9]+)*', name):
                continue
            if not isinstance(version, str) or not re.fullmatch(r'\d+(?:\.\d+)*(?:\.?(?:a|b|rc|post|dev)\d+)?', version):
                continue
            ref = name + '@' + version
            purl = 'pkg:pypi/' + ref
            if component.get('bom-ref') == ref and component.get('purl') == purl:
                identifiers.update((ref, purl))
        return [(m.start(), m.end()) for m in re.finditer(r'"(?:\\.|[^"\\])*"', text)
                if json.loads(m.group()) in identifiers]
    except (ValueError, TypeError, AttributeError):
        return []


def python_fixture_spans(text: str, relative_path: str) -> dict[str, list[tuple[int, int]]]:
    """Identify empty assignments and narrowly reviewed synthetic test strings.

    These are match-level exceptions, not file or detector exemptions. Invalid
    Python gets no exceptions. Reserved domains are accepted only in plain string
    literals in this package's test modules. Public-host URL rejection fixtures
    and the SEC index's public boilerplate also require their exact test context
    and literal value; arbitrary contacts elsewhere in those files remain findings.
    """
    spans: dict[str, list[tuple[int, int]]] = {'password assignment': [], 'personal email': []}
    if not relative_path.endswith('.py'):
        return spans
    try:
        tree = ast.parse(text)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, ValueError, RecursionError, tokenize.TokenError):
        return spans
    lines = text.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))

    def position(line: int, byte_column: int) -> int:
        # AST columns are UTF-8 byte offsets; regex spans are character offsets.
        return offsets[line - 1] + len(lines[line - 1].encode('utf-8')[:byte_column].decode('utf-8'))

    def bounds(node: ast.AST) -> tuple[int, int]:
        return (position(node.lineno, node.col_offset), position(node.end_lineno, node.end_col_offset))

    string_spans = [(offsets[token.start[0] - 1] + token.start[1],
                     offsets[token.end[0] - 1] + token.end[1])
                    for token in tokens if token.type == tokenize.STRING]
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    is_test = re.fullmatch(r'skills/ai-trading-agent/tests/test_[A-Za-z0-9_]+\.py', relative_path) is not None
    reserved_domains = {'example.invalid', 'example.com', 'example.org', 'example.net'}
    # The strings exercise rejection, not authentication. Changing a value or
    # moving it out of the named test removes the exception.
    rejection_literals = {
        ('test_borrow_intake.py', 'BorrowCaptureTests',
         'test_exact_route_rejects_credentials_queries_redirects_and_other_files'): {
            'ftp://shortstock@ftp2.interactivebrokers.com/usa.txt',
            'ftp://shortstock:password@ftp2.interactivebrokers.com/usa.txt'},
        ('test_market_sources.py', 'SecDailyIndexTests',
         'test_exact_index_url_requires_consistent_calendar_and_no_proxy_query_or_redirect'): {'user@www.sec.gov'},
        ('test_sec_identity.py', 'SecIdentityTests',
         'test_exact_https_identity_families_and_narrow_ftp_provenance'): {'ftp://secret@ftp2.interactivebrokers.com/usa.txt'},
    }
    public_index_prefix = (
        'Description:           Master Index of EDGAR Dissemination Feed\n'
        'Last Data Received:    November 12, 2026\nComments:              webmaster@sec.gov\n\n'
        'CIK|Company Name|Form Type|Date Filed|Filename\n'
        '--------------------------------------------------------------------------------\n')
    email_pattern = next(pattern for label, pattern in TEXT_PATTERNS if label == 'personal email')
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant) and node.value.value == ''):
            start, _ = bounds(node.targets[0])
            value_start, _ = bounds(node.value)
            if re.fullmatch(r'[A-Za-z_]\w*\s*=\s*', text[start:value_start]):
                spans['password assignment'].append((start, value_start))
        if not is_test or not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        ancestors = []
        current = node
        while current in parents:
            current = parents[current]
            ancestors.append(current)
        if any(isinstance(parent, ast.JoinedStr) for parent in ancestors):
            continue
        classes = [parent.name for parent in ancestors if isinstance(parent, ast.ClassDef)]
        methods = [parent.name for parent in ancestors if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef))]
        context = (Path(relative_path).name, classes[0] if classes else '', methods[0] if methods else '')
        exact_rejection = node.value in rejection_literals.get(context, set())
        assignment = parents.get(node)
        public_header = (relative_path == 'skills/ai-trading-agent/tests/test_market_sources.py'
                         and classes == ['SecDailyIndexTests'] and not methods
                         and isinstance(assignment, ast.Assign) and len(assignment.targets) == 1
                         and isinstance(assignment.targets[0], ast.Name) and assignment.targets[0].id == 'PREFIX'
                         and node.value == public_index_prefix)
        start, end = bounds(node)
        for match in email_pattern.finditer(text, start, end):
            if not any(a <= match.start() and match.end() <= b for a, b in string_spans):
                continue
            domain = match.group().rsplit('@', 1)[1].lower()
            if domain in reserved_domains or exact_rejection or public_header:
                spans['personal email'].append(match.span())
    return spans


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
        identifier_spans = sbom_package_identifier_spans(text, rel.as_posix())
        fixture_spans = python_fixture_spans(text, rel.as_posix())
        for label, pattern in TEXT_PATTERNS:
            if (label == "personal email"
                    and PUBLIC_LICENSE_EMAIL_EXCEPTIONS.get(rel.as_posix())
                    == hashlib.sha256(text.encode("utf-8")).hexdigest()):
                continue
            for match in pattern.finditer(text):
                if any(a <= match.start() and match.end() <= b for a, b in fixture_spans.get(label, [])):
                    continue
                if label == 'personal email' and any(a <= match.start() and match.end() <= b for a, b in identifier_spans):
                    continue
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
