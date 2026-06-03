# AI Skills

Public-ready exports of reusable Codex/Claude Code compatible agent skills.

## Included Skills

- `create-karaoke-video`: Create YouTube-ready karaoke videos from audio and user-provided lyrics, with optional vocal removal, timing, ASS subtitles, and MP4 rendering.
- `concert-ticket-checkout`: Assist with browser-based concert ticket searches, seat comparison, cart setup, checkout review, and user-supervised purchasing boundaries.
- `linkedin-knowledge-digest`: Filter LinkedIn feed and inbox activity into concise knowledge-bearing digests with clickable source links while excluding career milestones, hiring posts, self-promotion, and low-value outreach.
- `travel-deal-finder`: Compare current travel deals across flights, hotels, packages, and rental cars with clear ranking rules and source verification.

## Layout

Each skill lives under `skills/<skill-name>` and keeps the standard Codex skill structure:

- `SKILL.md`
- `agents/openai.yaml`
- `references/`
- `scripts/`

## Use With Codex

Copy a skill folder into your Codex skills directory:

```powershell
Copy-Item -Recurse skills\<skill-name> $env:CODEX_HOME\skills\
```

If `CODEX_HOME` is not set, use your Codex home directory and copy the selected skill into its `skills` folder.

## Use With Claude Code

Claude Code can use these skills because each skill is a directory with a `SKILL.md` file and optional supporting files.

For personal skills available across projects:

```powershell
New-Item -ItemType Directory -Force $HOME\.claude\skills
Copy-Item -Recurse .\skills\create-karaoke-video $HOME\.claude\skills\
Copy-Item -Recurse .\skills\linkedin-knowledge-digest $HOME\.claude\skills\
Copy-Item -Recurse .\skills\travel-deal-finder $HOME\.claude\skills\
```

For project skills checked into a specific repo:

```powershell
New-Item -ItemType Directory -Force .\.claude\skills
Copy-Item -Recurse .\skills\create-karaoke-video .\.claude\skills\
Copy-Item -Recurse .\skills\linkedin-knowledge-digest .\.claude\skills\
Copy-Item -Recurse .\skills\travel-deal-finder .\.claude\skills\
```

On macOS, Linux, or WSL, use the same target paths with `cp -R`:

```bash
mkdir -p ~/.claude/skills
cp -R skills/create-karaoke-video ~/.claude/skills/
cp -R skills/linkedin-knowledge-digest ~/.claude/skills/
cp -R skills/travel-deal-finder ~/.claude/skills/
```

Restart Claude Code after copying the folders, then ask:

```text
List all available Skills
```

Claude Code invokes skills automatically from the `description` field in `SKILL.md`. You do not need to type `$create-karaoke-video`, `$linkedin-knowledge-digest`, or `$travel-deal-finder`; those names are Codex-friendly invocation hints and are not required by Claude Code.

The `agents/openai.yaml` files are Codex metadata. Claude Code users can leave them in place, but Claude Code does not require them.

Claude Code subagents can also use these skills. To preload one into a subagent, add a `skills` field to the subagent frontmatter:

```yaml
---
name: travel-researcher
description: Finds and compares travel deals
skills:
  - travel-deal-finder
---
```

## Safety Process

Before publishing or updating this repository:

1. Export only skill source files and supporting references.
2. Do not include local task folders, browser/session data, generated outputs, audio/video files, lyrics supplied by users, credentials, keys, tokens, cookies, or personal paths.
3. Replace copyrighted or user-specific examples with generic placeholders.
4. Run the safety scan:

```powershell
python scripts/safety_scan.py
```

The scan is a guardrail, not a substitute for review. Manually inspect every match before publishing.

## Dependencies

Some skill scripts call optional third-party tools such as FFmpeg, Pillow, or Demucs. Dependencies are not vendored in this repository.

## License

No license has been selected yet. Add a license before inviting reuse or contributions from others.
