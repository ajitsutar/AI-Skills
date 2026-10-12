# Install linkedin-knowledge-digest

This folder is the complete skill source package. Keep `SKILL.md` and all its
subfolders together. No files from another skill or the repository root are
required to use it. Runtime tools, Python/Node packages, model downloads and
authenticated services are separate prerequisites described in [SKILL.md](SKILL.md).

## Codex or another Agent Skills host

Copy this entire `linkedin-knowledge-digest` folder into the skills directory used by your host.
Do not install two copies of the same skill. Select `$linkedin-knowledge-digest` in Codex, or use
your host's skill selector. `agents/openai.yaml` supplies Codex presentation metadata.

## Claude Code: one standalone skill

Copy this entire folder to `~/.claude/skills/linkedin-knowledge-digest/` (or your project's
`.claude/skills/linkedin-knowledge-digest/`). Invoke `/linkedin-knowledge-digest`. No repository plugin is needed.

The optional specialized agent is included in `agents/linkedin-digest-agent.md`. To use it,
copy that file to `~/.claude/agents/` (or your project's `.claude/agents/`) after
installing the skill. It preloads the standalone skill by its unqualified name.
The nested `agents/plugin/` variant is only for the repository-wide `ai-skills`
plugin; do not copy that variant into your standalone agents directory.

## ZIP upload

For a host that accepts skill ZIPs, zip this entire folder so the archive contains
`linkedin-knowledge-digest/SKILL.md` and its sibling resources. Do not zip only `SKILL.md`.
Keep generated outputs, environments and account configuration outside the package.
Uploading the package does not configure external tools or grant transaction authority.

## License and provenance

Keep [LICENSE](LICENSE), [PROVENANCE.md](PROVENANCE.md) and
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) with the folder when copying or
redistributing it. External runtimes, services and retrieved content retain their
own terms.
