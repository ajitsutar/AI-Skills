# Provenance

Repository-authored code and documentation are offered under [LICENSE](LICENSE).
External packages, model weights, fonts and user media retain their own terms;
see [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

The separation helper calls Demucs or audio-separator as an external program. The renderer calls
Pillow and FFmpeg, writes standard ASS subtitles, and can locate FFmpeg through
imageio-ffmpeg. Dependency implementations, model weights, fonts, song recordings
and lyrics are not bundled. Tests use synthetic text and bytes.

The separation wrapper requires a model-use record before running either backend.
Its source-code MIT grant and the external programs' software licenses do not
license pretrained weights. The optional MelBand adapter names and verifies the
checkpoint/config registered by audio-separator v0.48.0; neither file is bundled.
Model restrictions and pinned provenance are documented in the third-party notices.

For future imported snippets or assets, record source, revision, affected files,
modifications and license, and preserve applicable notices with the standalone
skill. Keep historical source-audit reports in the local archive.
