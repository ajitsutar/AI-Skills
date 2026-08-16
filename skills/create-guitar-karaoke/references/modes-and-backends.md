# Modes and Separation Backends

## Default Open-Source Backend

Use `BS-Roformer-SW.ckpt` through the open-source `audio-separator` 0.44.5 code for the default aggregate-guitar workflow. The checkpoint exposes six labels: bass, drums, other, vocals, guitar, and piano. Its single `guitar` label does not distinguish lead, rhythm, acoustic, or other guitar roles, and its coverage varies by mix.

Official project and model registry:

- <https://github.com/nomadkaraoke/python-audio-separator>
- <https://raw.githubusercontent.com/nomadkaraoke/python-audio-separator/v0.44.5/audio_separator/models.json>

Do not vendor the roughly 699 MB checkpoint. Let the tool download it into the task's model cache after the user approves network use. The helper verifies SHA-256 `24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e` before inference. The wrapper's software license does not by itself establish a license for separately hosted model weights; confirm weight terms before redistribution.

Recommended settings for version 0.44.5:

```text
--model_filename BS-Roformer-SW.ckpt
--output_format WAV
--sample_rate 44100
--normalization 1.0
--amplification 0.0
--use_soundfile
--mdxc_overlap 8
--mdxc_batch_size 1
--mdxc_pitch_shift 0
```

Important version-specific behavior:

- `--mdxc_overlap` behaves as a hop measured in seconds in this release. `8` is a balanced CPU setting; `2` is substantially slower.
- `--single_stem Guitar` does not reduce the six-stem computation in this model branch. Expect all six output files.
- Do not enable DirectML or autocast for the normal CPU path.
- FFmpeg must be discoverable even when WAV and SoundFile output are used.
- Process multiple bounded clips in one command so the model loads once and handles clips sequentially.
- If memory still fails, try `--mdxc_override_model_segment_size --mdxc_segment_size 512 --mdxc_overlap 4`, accepting slower or lower-quality output.

The six-stem backend writes all six float WAVs even though this workflow uses only `guitar`. A normal song can require several gigabytes of temporary disk once context overlap, the checkpoint, clips, stems, and master are included. The helper checks estimated free space before inference. `--cleanup-unused-stems` removes only generated non-guitar stem WAVs after the final outputs decode successfully; keep them when independent QA is still needed.

Tiling limits model inference size, but the final mixer uses several full-duration arrays. Its RAM preflight is intentionally conservative. Do not bypass it with `--allow-high-memory` unless available memory and source duration have been reviewed.

## Exactness Matrix

| Requested result | Aggregate guitar model | Dedicated or supplied semantic stem |
| --- | --- | --- |
| Aggregate guitar-labelled estimate, whole song | Supported; coverage and bleed vary | Supported |
| Aggregate guitar-labelled estimate, selected windows | Supported; coverage and bleed vary | Supported |
| Lead only, whole song | Not supported | Supported with aligned lead stem |
| Lead only, solo windows | Approximation by aggregate windowing | Supported with aligned lead stem |
| Rhythm only | Not supported | Supported with aligned rhythm stem |
| Backing guitars outside solos | Approximation by inverse windowing | Supported if rhythm/backing stem exists |

"Supported" means the requested operation can be applied to that stem; it does not promise artifact-free or exhaustive guitar capture.

## Choosing a Lead/Rhythm Path

No standard open model used by this skill reliably divides an arbitrary commercial mix into separate lead and rhythm guitar stems. When exact lead or rhythm removal is requested:

1. Look for an already supplied, legally obtained, full-length stem aligned to the same master.
2. If a local lead/rhythm model is available, validate its documented output labels and audition its stems before mixing.
3. A third-party service may be used only with explicit permission to upload the audio and after disclosing account, credit, privacy, and licensing implications.
4. Otherwise offer one of the aggregate-guitar approximations and clearly state what additional guitar content it removes or preserves.

Never label a mid/side or EQ heuristic as exact semantic separation.

## Timestamp and Alignment Rules

- Prefer timestamps measured against the exact local audio.
- Convert `MM:SS`, `HH:MM:SS`, or seconds to sample positions only after decoding the master.
- Confirm that a music-video edit has not added an intro, dialogue, or silence.
- For a supplied external stem, verify sample rate, channel count, polarity, gain, and transient alignment against the master. With zero offset, the helper requires the exact decoded frame count. Use `--stem-offset` only after measuring where stem frame zero lands, and `--stem-gain` only after measuring a mixture-consistent scale. A stem derived from another master or edit may comb-filter or leave audible guitar.
- Keep the supplied source stem available through the mix stage. The helper revalidates both the original stem file and its decoded working WAV against the preparation hashes before subtraction.
- Lead solos may overlap vocals. Use the guitar stem and time mask; do not mute the entire mix or cut vocal passages.

## Why Subtraction Uses the Original Master

The output is computed as:

```text
edited = original_master - selected_stem * time_envelope
```

This retains the original float mix outside the envelope and avoids rebuilding the song from independently normalized stems. Short raised-cosine fades reduce clicks at edit boundaries. Context-padded model tiles are blended before subtraction so long-song processing does not introduce hard seams. The edited float master is not hard-clipped; lossy MP3/video delivery receives one global headroom gain only when needed.
