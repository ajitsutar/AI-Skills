# Provenance

This record covers the files in `create-karaoke-video`. The skill's own code and
documentation are offered under [LICENSE](LICENSE). External packages, model
weights, fonts, and user media retain their own terms; see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Repository history

The available Git history records these entries:

- [`c650629`](https://github.com/ajitsutar/AI-Skills/commit/c650629c836e63fafb2bd45ab0ddd82f04f3b8ac): skill instructions added on June 1, 2026.
- [`01cb8f6`](https://github.com/ajitsutar/AI-Skills/commit/01cb8f6f440ed10c489740c6617ec503ca0de704): rendering and Demucs command-line wrappers added on June 1, 2026.
- [`95468c1`](https://github.com/ajitsutar/AI-Skills/commit/95468c11275b4678818beee249dab2a8adbf837a): helper hardening and tests added on August 16, 2026.
- [`bbf1dfa`](https://github.com/ajitsutar/AI-Skills/commit/bbf1dfad445dc67fbd27cac40010278d723adea7): standalone installation and agent documents added.

These are repository-entry records, not independent certification of authorship
or ownership before the files entered Git.

## Implementation and review

The separation helper calls Demucs as an external program. The renderer calls
Pillow and FFmpeg, writes standard ASS subtitles, and optionally locates FFmpeg
through imageio-ffmpeg. No dependency implementation, model weights, fonts, song
recordings, or song lyrics are bundled. Tests use synthetic text and bytes.

An October 12, 2026 review of all nine then-tracked skill files and their Git
history found no confirmed unattributed third-party code or prose. Targeted
public searches and comparisons against the upstream Demucs CLI and
imageio-ffmpeg executable-selection helper found no substantial matching
functions or eight-line normalized blocks. That bounded search does not prove
originality and cannot cover private or unindexed sources.

Follow-up review found the upstream maintainer's scientific-purpose restriction
on pretrained Demucs weights. The separation wrapper now requires a model-use
record before running Demucs; the source-code MIT grant is not treated as a
license for those weights. See the model terms in the third-party notices.

For future imported snippets or assets, record the source URL, revision, affected
files, and license, and preserve applicable notices with the standalone skill.
