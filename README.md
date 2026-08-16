# AI Skills

Shareable source exports of reusable Agent Skills, packaged as a native Claude Code plugin with matching specialized agents and usable as standalone Codex skills. See the license status below before reuse or redistribution.

## Included Skills

- `create-karaoke-video`: Create YouTube-ready karaoke videos from audio and user-provided lyrics, with optional vocal removal, timing, ASS subtitles, and MP4 rendering.
- `create-guitar-karaoke`: Create guitar-muted practice mixes and still-image videos with whole-song and selected-window aggregate-guitar modes, plus exact lead, rhythm, or custom removal when a verified semantic stem is supplied.
- `concert-ticket-checkout`: Assist with browser-based concert ticket searches, seat comparison, cart setup, checkout review, and user-supervised purchasing boundaries.
- `deal-watch-alerts`: Build configurable deal-watch automations that verify selected variants, condition rules, thresholds, duplicate memory, and optional chat/email/SMS alerts.
- `linkedin-knowledge-digest`: Filter LinkedIn feed and inbox activity into concise knowledge-bearing digests with clickable source links while excluding career milestones, hiring posts, self-promotion, and low-value outreach.
- `travel-deal-finder`: Compare current travel deals across flights, hotels, packages, and rental cars with clear ranking rules and source verification.

## Layout

Each skill lives under `skills/<skill-name>` and keeps the standard Codex skill structure:

- `SKILL.md`
- `agents/openai.yaml`
- `references/`
- `scripts/`

Claude-specific packaging lives alongside the skills:

- `.claude-plugin/plugin.json`: native Claude Code plugin manifest.
- `.claude-plugin/marketplace.json`: installable marketplace catalog for this repository.
- `agents/`: one Claude Code agent per skill, each preloading only its matching skill.

## Use With Codex

Copy a skill folder into your Codex skills directory:

```powershell
Copy-Item -Recurse skills\<skill-name> $env:CODEX_HOME\skills\
```

On macOS or Linux:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R "skills/<skill-name>" "${CODEX_HOME:-$HOME/.codex}/skills/"
```

If `CODEX_HOME` is not set, use your Codex home directory and copy the selected skill into its `skills` folder.

## Use With Claude Code (Recommended)

Install the repository as a native plugin. This loads all six skills and their matching agents without copying folders or depending on the current working directory.

In Claude Code:

```text
/plugin marketplace add https://github.com/ajitsutar/AI-Skills.git
/plugin install ai-skills@ajitsutar-ai-skills
/reload-plugins
```

Verify installation with `/skills`, `/agents`, and `/doctor`. Plugin skills use namespaced commands such as:

```text
/ai-skills:create-guitar-karaoke
/ai-skills:travel-deal-finder
/ai-skills:linkedin-knowledge-digest
```

The matching agents are:

- `@ai-skills:concert-ticket-agent`
- `@ai-skills:deal-watch-agent`
- `@ai-skills:guitar-karaoke-agent`
- `@ai-skills:karaoke-video-agent`
- `@ai-skills:linkedin-digest-agent`
- `@ai-skills:travel-deal-agent`

Claude can delegate automatically from each agent's description, or the user can invoke an agent explicitly with `@agent-name`. Each agent preloads only its corresponding skill to keep context focused.

For local development from a clone, start Claude Code with:

```bash
claude --plugin-dir .
```

In PowerShell, the same command is:

```powershell
claude --plugin-dir .
```

Then use `/reload-plugins` after edits. Plugin installations use the repository commit SHA as the version, so updates do not require maintaining a separate version string.

## Standalone Claude Skills

Claude Code can also discover these skills from `~/.claude/skills/` or a project's `.claude/skills/` directory. Copy any or all of the skill folders there. For example:

```bash
mkdir -p ~/.claude/skills
cp -R skills/concert-ticket-checkout ~/.claude/skills/
cp -R skills/create-guitar-karaoke ~/.claude/skills/
cp -R skills/create-karaoke-video ~/.claude/skills/
cp -R skills/deal-watch-alerts ~/.claude/skills/
cp -R skills/linkedin-knowledge-digest ~/.claude/skills/
cp -R skills/travel-deal-finder ~/.claude/skills/
```

PowerShell equivalent:

```powershell
New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
Copy-Item -Recurse skills\concert-ticket-checkout "$HOME\.claude\skills\"
Copy-Item -Recurse skills\create-guitar-karaoke "$HOME\.claude\skills\"
Copy-Item -Recurse skills\create-karaoke-video "$HOME\.claude\skills\"
Copy-Item -Recurse skills\deal-watch-alerts "$HOME\.claude\skills\"
Copy-Item -Recurse skills\linkedin-knowledge-digest "$HOME\.claude\skills\"
Copy-Item -Recurse skills\travel-deal-finder "$HOME\.claude\skills\"
```

If the top-level skills directory did not exist when the session started, restart Claude Code once. Otherwise Claude detects skill changes live. Standalone skills can be invoked with `/skill-name` or preloaded into a custom agent:

```yaml
---
name: guitar-practice-producer
description: Creates guitar-muted practice tracks
skills:
  - create-guitar-karaoke
---
```

The per-skill `agents/openai.yaml` files are Codex metadata. Claude Code ignores them; its plugin agents are the Markdown files in the repository-level `agents/` directory.

## Safety Process

Before publishing or updating this repository:

1. Export only skill source files and supporting references.
2. Do not include local task folders, browser/session data, generated outputs, audio/video files, lyrics supplied by users, credentials, keys, tokens, cookies, or personal paths.
3. Replace copyrighted or user-specific examples with generic placeholders.
4. Run the safety scan:

```powershell
python scripts/safety_scan.py
```

5. Validate the Claude package with Anthropic's CLI:

```bash
claude plugin validate .
```

The scan is a guardrail, not a substitute for review. Manually inspect every match before publishing.

## Dependencies

Some skill scripts call optional third-party tools such as FFmpeg, Pillow, Demucs, or audio-separator. Dependencies and model checkpoints are not vendored in this repository.

Agents inherit the tools and MCP servers enabled in the user's Claude Code session. Live browser, web, Slack/email, or other external operations require the corresponding configured capability and authenticated session; the agents stop clearly when a required capability is unavailable.

## License

No license has been selected yet. Public visibility does not grant permission to reuse or redistribute the repository. Choose a license before inviting reuse or contributions. Separately downloaded model checkpoints are not covered by this repository and may have different or undocumented terms.
