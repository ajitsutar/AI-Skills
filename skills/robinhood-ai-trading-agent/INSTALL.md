# Install robinhood-ai-trading-agent

This folder is the complete skill source package. Keep `SKILL.md` and all its
subfolders together. No files from another skill or the repository root are
required to use it. Runtime tools, Python/Node packages, model downloads and
authenticated services are separate prerequisites described in [SKILL.md](SKILL.md).

## Codex or another Agent Skills host

Copy this entire `robinhood-ai-trading-agent` folder into the skills directory used by your host.
Do not install two copies of the same skill. Select `$robinhood-ai-trading-agent` in Codex, or use
your host's skill selector. `agents/openai.yaml` supplies Codex presentation metadata.

## Claude Code: one standalone skill

Copy this entire folder to `~/.claude/skills/robinhood-ai-trading-agent/` (or your project's
`.claude/skills/robinhood-ai-trading-agent/`). Invoke `/robinhood-ai-trading-agent`. No repository plugin is needed.

The optional specialized agent is included in `agents/robinhood-trading-agent.md`. To use it,
copy that file to `~/.claude/agents/` (or your project's `.claude/agents/`) after
installing the skill. It preloads the standalone skill by its unqualified name.
The nested `agents/plugin/` variant is only for the repository-wide `ai-skills`
plugin; do not copy that variant into your standalone agents directory.

## ZIP upload

For a host that accepts skill ZIPs, zip this entire folder so the archive contains
`robinhood-ai-trading-agent/SKILL.md` and its sibling resources. Do not zip only `SKILL.md`.
Keep generated outputs, environments and account configuration outside the package.
Uploading the package does not configure external tools or grant transaction authority.

## License and notices

Keep the included [MIT License](LICENSE), [third-party notices](THIRD-PARTY-NOTICES.md)
and [arch license](ARCH-LICENSE.txt) in copies and ZIPs. MIT covers the
repository-authored skill code and documentation; dependencies, reports and market
data retain their own terms. [PROVENANCE.md](PROVENANCE.md) records the source audit
and the unresolved origin of the historical predecessor.
