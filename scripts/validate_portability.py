#!/usr/bin/env python3
"""Validate the repository's shared Codex and Claude Code skill contract."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PATH_REF_RE = re.compile(r"(?<![A-Za-z0-9_.-])((?:assets|references|scripts)/[A-Za-z0-9_.\-/]+)")
TEXT_SUFFIXES = {".md", ".py", ".js", ".json", ".yaml", ".yml", ".txt"}


class ValidationError(Exception):
    pass


def fail(message: str) -> None:
    raise ValidationError(message)


def unquote(value: str, source: Path) -> str:
    value = value.strip()
    if value.startswith('"'):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            fail(f"{source}: invalid quoted scalar: {exc}")
        if not isinstance(decoded, str):
            fail(f"{source}: expected a string scalar")
        return decoded
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def split_frontmatter(path: Path) -> tuple[list[str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        fail(f"{path}: missing opening YAML frontmatter marker")
    try:
        end = lines.index("---", 1)
    except ValueError:
        fail(f"{path}: missing closing YAML frontmatter marker")
    return lines[1:end], "\n".join(lines[end + 1 :])


def parse_flat_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    lines, body = split_frontmatter(path)
    values: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):\s*(.*)", line)
        if not match:
            fail(f"{path}: shared SKILL.md frontmatter must use flat scalar fields")
        key, raw = match.groups()
        if key in values:
            fail(f"{path}: duplicate frontmatter key {key!r}")
        values[key] = unquote(raw, path)
    return values, body


def parse_agent(path: Path) -> tuple[dict[str, str], list[str]]:
    lines, _ = split_frontmatter(path)
    scalars: dict[str, str] = {}
    skills: list[str] = []
    in_skills = False
    for line in lines:
        if not line.strip():
            continue
        if line == "skills:":
            if in_skills or "skills" in scalars:
                fail(f"{path}: duplicate skills field")
            scalars["skills"] = ""
            in_skills = True
            continue
        if in_skills and re.fullmatch(r"\s{2}-\s+.+", line):
            skills.append(unquote(re.sub(r"^\s{2}-\s+", "", line), path))
            continue
        in_skills = False
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):\s*(.*)", line)
        if not match:
            fail(f"{path}: unsupported or malformed agent frontmatter line: {line!r}")
        key = match.group(1)
        if key in scalars:
            fail(f"{path}: duplicate agent frontmatter field {key!r}")
        scalars[key] = unquote(match.group(2), path)
    return scalars, skills


def parse_openai_yaml(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "interface:":
        fail(f"{path}: first field must be interface:")
    values: dict[str, str] = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        match = re.fullmatch(r"  (display_name|short_description|default_prompt):\s*(.+)", line)
        if not match:
            fail(
                f"{path}: repository policy permits only the three portable presentation "
                f"fields under interface; found: {line!r}"
            )
        key, raw = match.groups()
        if not (raw.startswith('"') and raw.endswith('"')):
            fail(f"{path}: {key} must be a double-quoted string")
        if key in values:
            fail(f"{path}: duplicate interface field {key!r}")
        values[key] = unquote(raw, path)
    expected = {"display_name", "short_description", "default_prompt"}
    if set(values) != expected:
        fail(f"{path}: interface fields must be exactly {sorted(expected)}")
    return values


def validate_skill(skill_dir: Path, agent_skills: dict[str, list[Path]]) -> None:
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.is_file():
        fail(f"{skill_dir}: missing uppercase SKILL.md")
    values, body = parse_flat_frontmatter(skill_path)
    if set(values) != {"name", "description"}:
        fail(f"{skill_path}: portable frontmatter must contain only name and description")

    name = values["name"]
    description = values["description"]
    if name != skill_dir.name:
        fail(f"{skill_path}: name {name!r} does not match directory {skill_dir.name!r}")
    if len(name) > 64 or not NAME_RE.fullmatch(name):
        fail(f"{skill_path}: invalid portable skill name {name!r}")
    if not description or len(description) > 1024 or "<" in description or ">" in description:
        fail(f"{skill_path}: description is empty or violates the portable field contract")
    if len(skill_path.read_text(encoding="utf-8").splitlines()) > 500:
        fail(f"{skill_path}: keep SKILL.md at or below 500 lines")

    forbidden = {
        "${CLAUDE_": "Claude-only variable substitution",
        "$CLAUDE_": "Claude-only variable substitution",
        "$ARGUMENTS": "Claude-only argument substitution",
        "${CODEX_": "host-specific variable substitution",
        "$CODEX_HOME": "host-specific variable substitution",
    }
    for token, reason in forbidden.items():
        if token in body:
            fail(f"{skill_path}: shared instructions depend on {reason}: {token}")

    for match in PATH_REF_RE.finditer(body):
        relative = match.group(1).rstrip(".,;:)")
        resource = (skill_dir / Path(relative)).resolve()
        try:
            resource.relative_to(skill_dir.resolve())
        except ValueError:
            fail(f"{skill_path}: referenced resource escapes the skill directory: {relative}")
        if not resource.exists():
            fail(f"{skill_path}: referenced resource does not exist: {relative}")

    openai_path = skill_dir / "agents" / "openai.yaml"
    if not openai_path.is_file():
        fail(f"{skill_dir}: missing agents/openai.yaml")
    interface = parse_openai_yaml(openai_path)
    if not 25 <= len(interface["short_description"]) <= 64:
        fail(f"{openai_path}: short_description must contain 25-64 characters")
    if f"${name}" not in interface["default_prompt"]:
        fail(f"{openai_path}: default_prompt must mention ${name}")

    matches = agent_skills.get(f"ai-skills:{name}", [])
    if len(matches) != 1:
        fail(f"{skill_dir}: expected one Claude plugin agent preloading ai-skills:{name}, found {len(matches)}")


def validate_package(skill_names: set[str]) -> None:
    plugin_path = ROOT / ".claude-plugin" / "plugin.json"
    marketplace_path = ROOT / ".claude-plugin" / "marketplace.json"
    try:
        plugin = json.loads(plugin_path.read_text(encoding="utf-8"))
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"Claude plugin metadata is unreadable or invalid JSON: {exc}")
    if plugin.get("name") != "ai-skills":
        fail(f"{plugin_path}: plugin name must be ai-skills")
    version = plugin.get("version")
    if not isinstance(version, str) or not re.fullmatch(
        r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version
    ):
        fail(f"{plugin_path}: version must use stable MAJOR.MINOR.PATCH semver")
    entries = marketplace.get("plugins")
    if not isinstance(entries, list) or len(entries) != 1:
        fail(f"{marketplace_path}: expected exactly one plugin entry")
    entry = entries[0]
    if entry.get("name") != "ai-skills" or entry.get("source") != "./":
        fail(f"{marketplace_path}: plugin entry must use name ai-skills and source ./")
    if entry.get("version") != version:
        fail(f"{marketplace_path}: marketplace and plugin versions must match")

    agent_files = sorted((ROOT / "agents").glob("*.md"))
    if len(agent_files) != len(skill_names):
        fail("agents/: expected exactly one root Claude agent for every skill")
    for path in agent_files:
        fields, skills = parse_agent(path)
        if set(fields) != {"name", "description", "skills"}:
            fail(
                f"{path}: repository policy keeps plugin agents portable and must contain "
                "exactly name, description, and skills"
            )
        if not fields.get("name") or not fields.get("description"):
            fail(f"{path}: agent requires name and description")
        if not NAME_RE.fullmatch(fields["name"]):
            fail(f"{path}: invalid Claude agent name {fields['name']!r}")
        if len(skills) != 1 or skills[0].removeprefix("ai-skills:") not in skill_names:
            fail(f"{path}: agent must preload exactly one repository skill")


def validate_text_hygiene() -> None:
    bad_sequence = re.compile(
        "(?:"
        + chr(0x00C2)
        + "[\\u0080-\\u00bf]|"
        + chr(0x00C3)
        + "[\\u0080-\\u00bf]|"
        + chr(0x00E2)
        + "[\\u0080-\\u00bf\\u20ac].|"
        + chr(0xFFFD)
        + ")"
    )
    user_directory = "Users"
    personal_path = re.compile(
        rf"(?:[A-Za-z]:\\{user_directory}\\|/{user_directory}/)[^\s`\"']+"
    )
    scanners = {Path(__file__).resolve(), (ROOT / "scripts" / "safety_scan.py").resolve()}
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        if bad_sequence.search(text):
            fail(f"{path}: possible mojibake detected")
        if path.resolve() not in scanners and personal_path.search(text):
            fail(f"{path}: personal absolute path detected")
        if path.suffix == ".py":
            try:
                compile(text, str(path), "exec")
            except SyntaxError as exc:
                fail(f"{path}: Python syntax error: {exc}")


def validate_javascript() -> None:
    node = shutil.which("node")
    if not node:
        print("NOTICE: node is unavailable; JavaScript syntax check skipped")
        return
    for path in ROOT.rglob("*.js"):
        if ".git" in path.parts:
            continue
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        if result.returncode:
            fail(f"{path}: JavaScript syntax check failed:\n{result.stderr.strip()}")


def main() -> int:
    try:
        skill_dirs = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
        if not skill_dirs:
            fail("skills/: no skills found")

        agent_skills: dict[str, list[Path]] = {}
        for agent_path in sorted((ROOT / "agents").glob("*.md")):
            _, skills = parse_agent(agent_path)
            for skill in skills:
                agent_skills.setdefault(skill, []).append(agent_path)

        for skill_dir in skill_dirs:
            validate_skill(skill_dir, agent_skills)
        validate_package({path.name for path in skill_dirs})
        validate_text_hygiene()
        validate_javascript()
    except (ValidationError, OSError) as exc:
        print(f"PORTABILITY VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"PORTABILITY VALIDATION PASSED: {len(skill_dirs)} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
