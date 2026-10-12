# Modes and Separation Backends

## Default: Authorized Supplied Stems

Use a full-length, aligned stem from the user or an independently authorized separator. Pass `--stem-file` and `--stem-kind aggregate-guitar|lead-guitar|rhythm-guitar|custom`. The helper's supplied-stem path does not need `audio-separator`, a model cache, or model downloads. Confirm the stem's actual content, its permission for the intended use, and alignment to the exact audio master.

## Optional Local Model Adapter

The helper retains an adapter for `BS-Roformer-SW.ckpt` through `audio-separator` 0.44.5. It is **not an automatically downloaded default**. The public checkpoint's trainer and weight license could not be established; neither this skill's MIT license nor the separator's software MIT license grants rights to that checkpoint. The adapter requires already obtained local checkpoint/config files plus a reviewed rights record. A record documents the operator's review; the script cannot authenticate a legal grant.

The model exposes six labels: bass, drums, other, vocals, guitar, and piano. Its single `guitar` label does not distinguish guitar roles, and coverage varies by mix.

Official project and model registry:

- <https://github.com/nomadkaraoke/python-audio-separator>
- <https://raw.githubusercontent.com/nomadkaraoke/python-audio-separator/v0.44.5/audio_separator/models.json>

Do not vendor the roughly 699 MB checkpoint. The helper never requests a missing checkpoint/config download: it stops before invoking the backend when either is missing or its hash differs. The externally installed separator may access its own registry metadata; keep its dependencies and cache outside the skill.

Before enabling this path, establish permission for the exact weights, configuration, and intended use from an authorized rights holder. Do not substitute a mirror's label, architecture license, or acknowledgement of risk. If terms remain unknown, use the supplied-stem path. Record the actual evidence in a task-local JSON file with:

- `schema_version`: `1`
- `checkpoint_sha256`: `24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e`
- `config_sha256`: `b558996f1e25eb48798bd6502505a5de94c4f966d6edfb1a0420f06cc40b501a`
- Nonempty `rights_holder`, `license_name`, `terms_source` (official URL or local grant reference), `permitted_use` (specific to this task), and `reviewed_by`.
- `covers_model_weights`, `covers_config`, and `intended_use_permitted`: true only after reviewing the grant.

Keep permission documents private and outside the repository. The manifest records the rights file and its SHA-256; resume/mix reject changed or missing evidence. The report contains the evidence hash, not the private grant text. Old model manifests without this record must be prepared again. The record is not permission in itself.

After rights are established, install `scripts/requirements-separator.txt`, place `BS-Roformer-SW.ckpt` and `BS-Roformer-SW.yaml` in a local model directory, and run:

```text
<python> "<skill-dir>/scripts/build_guitar_karaoke.py" "song.wav" --scope whole --model-dir "authorized-models" --model-license-evidence "model-rights.json" --work-dir "work/song" --output "outputs/guitar-muted.wav"
```

We did not silently replace this checkpoint with Demucs `htdemucs_6s`: the Demucs maintainer [distinguished model-weight terms from the software MIT license](https://github.com/facebookresearch/demucs/issues/327). That statement predates some newer models; it is not a verified commercial grant for the six-stem weights. A clearly licensed replacement can be added after its specific terms and output behavior are validated.

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
