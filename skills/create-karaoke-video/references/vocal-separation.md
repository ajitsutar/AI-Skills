# Vocal Separation Backends

The helper exposes two local backends. Both require a model-use record before a
dependency check, cache creation, model download, or output creation. The record
documents the operator's review; it is not an independent license determination.

## Demucs

`demucs` remains the default for backward compatibility. Select a model with
`--model`; the default is `htdemucs`. Demucs code and pretrained weights have
different terms. See the model notice before choosing a use category.

```powershell
python "<skill-dir>/scripts/separate_vocals.py" "song.mp3" `
  --backend demucs --model htdemucs `
  --rights-record "work/model-rights.json" --use-category scientific_research `
  --outdir "work/separated"
```

## audio-separator MelBand Roformer

This adapter is deliberately narrow:

- `audio-separator[cpu]==0.48.0`
- registered checkpoint `vocals_mel_band_roformer.ckpt`
- registered config `vocals_mel_band_roformer.yaml`
- checkpoint SHA-256 `87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e`
- config SHA-256 `b958b29c8f7195f0d86bee6759a33980db675c4ecaf2fcaa80fa125828e6cd38`

The names come from the upstream v0.48.0 model registry and the hashes come from
its checksum manifest. `audio-separator` verifies downloads and cached files;
the wrapper also verifies both files after inference and before publication.
Weights and config are downloaded into the selected external model cache, never
vendored into this skill. A first run can therefore require network access and a
large download. Obtain approval before installing dependencies or downloading a
model. The original author's current Hugging Face model card declares MIT, and
its verified April 22, 2026 commit changed the card from GPL-3.0 to MIT. The
registered checkpoint hash matches that original file. Cite those primary sources
in an `open_license` rights record; do not infer terms from audio-separator's own
software license.

Install the exact optional dependency in an isolated environment:

```powershell
python -m pip install -r "<skill-dir>/scripts/requirements-audio-separator.txt"
```

Then run:

```powershell
python "<skill-dir>/scripts/separate_vocals.py" "song.mp3" `
  --backend audio-separator `
  --model vocals_mel_band_roformer.ckpt `
  --model-dir "work/models/audio-separator" `
  --rights-record "work/model-rights.json" --use-category publication `
  --outdir "work/separated"
```

The registered config names the non-vocal complement `other`, so the adapter
requests only that stem, writes WAV through soundfile at 44.1 kHz with
normalization 1.0 and amplification 0.0, and assigns the stable name
`no_vocals.wav`. The published result is
`work/separated/audio-separator/<track>/no_vocals.wav`.
Before publication, the wrapper also confirms a nonempty 44.1 kHz WAV and,
when libsndfile can inspect the source format, checks its resampled frame count
against the source duration.

`--device` is Demucs-only. audio-separator 0.48.0 selects its available runtime
device. Use `--audio-separator <path>` only when the pinned executable is not on
`PATH`.

## Rights Record

The JSON fields are defined in
[THIRD-PARTY-NOTICES.md](../THIRD-PARTY-NOTICES.md#model-weights). The `model`
field must be the exact Demucs model name or
`vocals_mel_band_roformer.ckpt`. Do not treat the separator software's MIT
license or registry inclusion as a license for the checkpoint. For this exact
checkpoint, use the original author's model card and
[verified license-change commit](https://huggingface.co/KimberleyJSN/melbandroformer/commit/ac9b0614ab3cd7f77219e18ba494dfd93956c348)
as the checkpoint-specific evidence.

Both backends run in an isolated job directory and publish the complete generated
track under a cross-process lock. Existing output is preserved unless
`--overwrite` is explicit. The completion stem is hard-linked last; a failed
publication rolls back newly linked files and restores the prior complete track
when possible.
