# AI Skills

Public-ready exports of reusable Codex skills.

## Included Skills

- `create-karaoke-video`: Create YouTube-ready karaoke videos from audio and user-provided lyrics, with optional vocal removal, timing, ASS subtitles, and MP4 rendering.
- `travel-deal-finder`: Compare current travel deals across flights, hotels, packages, and rental cars with clear ranking rules and source verification.

## Layout

Each skill lives under `skills/<skill-name>` and keeps the standard Codex skill structure:

- `SKILL.md`
- `agents/openai.yaml`
- `references/`
- `scripts/`

## Install Locally

Copy a skill folder into your Codex skills directory:

```powershell
Copy-Item -Recurse skills\<skill-name> $env:CODEX_HOME\skills\
```

If `CODEX_HOME` is not set, use your Codex home directory and copy the selected skill into its `skills` folder.

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
