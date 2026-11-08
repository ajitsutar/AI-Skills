# Optional SAM Audio Backend

Use this adapter only when the operator has chosen prompted separation and has accepted the applicable upstream terms. It is an experimental alternative for producing a candidate custom stem; it does not replace the skill's supplied-stem validation or make lead/rhythm separation exact.

## Upstream and license

- Official code and usage: <https://github.com/facebookresearch/sam-audio>
- Official model collection: <https://huggingface.co/facebook/sam-audio-large>
- Official license: <https://github.com/facebookresearch/sam-audio/blob/main/LICENSE>

SAM Audio uses the custom **SAM License**, not this skill's MIT license. The checkpoints are gated on Hugging Face. Review and accept the current upstream terms for the intended use before loading a checkpoint. The helper neither accepts a token argument nor reads, displays, copies, or exports credentials. It relies only on authentication already configured for the standard Hugging Face client.

The remote preflight uses the Hugging Face client's existing authentication to make HEAD requests for the gated `config.json` and listed weight artifacts; public repository metadata alone is not treated as proof of access. With `--local-files-only`, it checks that a cached snapshot contains a nonempty config and at least one weight file, but only a later `from_pretrained` load can prove that the cache and all transitive dependencies are complete. Preflight does not load weights, download model artifacts, or run inference. The first non-local inference can download a large checkpoint through `from_pretrained`; obtain approval for that download and storage before running it.

## Isolated installation

Meta's repository currently requires Python 3.11 or newer and recommends a CUDA-capable GPU. Install the official project and this skill's `soundfile` dependency in a dedicated environment. Do not vendor the repository, weights, Hugging Face cache, or credentials into this skill.

Pin the official code instead of installing a moving branch. The commit below was the current upstream `main` revision verified on 2026-11-07 and includes the upstream predicted-span conditioning fix: <https://github.com/facebookresearch/sam-audio/commit/bb4c6999d2677c7402360e426afc01ddfad6dce0>.

```text
<python> -m pip install "git+https://github.com/facebookresearch/sam-audio.git@bb4c6999d2677c7402360e426afc01ddfad6dce0"
<python> -m pip install soundfile
```

This pins the SAM Audio repository itself; review its Git-based transitive dependencies separately because upstream currently declares some of them from moving branches.

Authenticate separately using the normal Hugging Face workflow after the account has been granted model access. Do not put a token in a command, report, source file, or task log.

## Preflight

```text
<python> "<skill-dir>/scripts/separate_prompted_audio.py" --preflight --device cuda --model facebook/sam-audio-large
```

Preflight checks imports, the requested CUDA index (or reports the CPU fallback), and authenticated HEAD access to the gated config and weight artifacts. It does not infer or create outputs. Use `--local-files-only` to forbid network model access and check for cached candidate files; this cache check is intentionally not described as proof of a complete loadable model.

If preflight reports inaccessible gated artifacts, request and accept access on the official model page and configure the existing Hugging Face authentication outside this helper. Do not inspect credential files or environment variables to troubleshoot it. A CUDA failure means the requested device is not visible to this PyTorch runtime; choose a working CUDA index or explicitly choose CPU, understanding that CPU inference can be impractically slow and memory intensive.

## Text prompt

Meta recommends a concise lowercase noun phrase or verb phrase. For example:

```text
<python> "<skill-dir>/scripts/separate_prompted_audio.py" "clip-mono.wav" \
  --prompt "lead electric guitar" \
  --output-dir "work/sam-audio-lead" \
  --device cuda
```

`--predict-spans` asks the model to predict event locations from a text-only prompt. `--reranking-candidates N` can improve selection at substantial latency and memory cost. Start with the default of one candidate for a representative short clip.

## Text plus time-span prompt

The helper maps positive and negative examples to Meta's documented `anchors` API. Each span accepts seconds, `MM:SS`, or `HH:MM:SS`:

```text
<python> "<skill-dir>/scripts/separate_prompted_audio.py" "clip-mono.wav" \
  --prompt "lead electric guitar" \
  --positive-span 00:12.40 00:20.25 \
  --positive-span 00:31.10 00:36.00 \
  --negative-span 00:02.00 00:08.00 \
  --output-dir "work/sam-audio-lead" \
  --device cuda
```

This becomes `anchors=[[['+', 12.4, 20.25], ['+', 31.1, 36.0], ['-', 2.0, 8.0]]]` in the processor call. At least one positive span is required when using anchors. Opposite-sign spans may not overlap. Explicit anchors cannot be combined with automatic span prediction or candidate reranking in this adapter.

Span prompts identify examples of the requested sound; they are not hard edit masks. If the desired final mix removes a stem only within selected song sections, first generate and audition the prompted full-length target, then apply the existing guitar-karaoke mixer's window envelope to that verified stem.

## Outputs and handoff

The helper stages and verifies three files, then commits them as one set:

- `... - SAM Audio target.wav`: the prompted sound estimate.
- `... - SAM Audio residual.wav`: the model's estimate of everything else.
- `... - SAM Audio report.json`: model, prompt, anchors, device, source hash and format, output hashes and formats, and any frame adjustment.

Both audio files are 32-bit float WAV. They are resampled from `SAMAudioProcessor.audio_sampling_rate` to the source sample rate and trimmed or zero-padded only within a 10 ms tail tolerance; a larger duration discrepancy aborts. The WAV headers and report are verified for the exact final rate and length. The helper also requires both model outputs to have exactly the source channel count. In particular, a mono SAM Audio estimate is rejected for a stereo source rather than being silently duplicated or treated as subtraction-ready. Start with a mono evaluation clip. Do not subtract its mono target from the stereo master; use a backend that preserves matching stereo channels for that operation.

Remote inference loads the exact model revision whose gated config and weight artifacts passed preflight HEAD checks. Local-only inference loads the resolved snapshot path checked by preflight. The report records the requested model id, actual `from_pretrained` source, revision, and local-only state.

Length and channel checks do not prove sample alignment; audition transients and verify polarity/gain before subtraction. Target and residual are generative outputs and are not guaranteed to sum exactly to the source.

Pass only a channel-compatible accepted target to the existing mixer as a supplied stem, for example with `--stem-file` and `--stem-kind lead-guitar`. Keep the JSON report beside the task output, not in the skill repository. `--overwrite` is required to replace an existing three-file set; the source file is never an allowed output path. The three-file commit uses a per-bundle cross-process lock and refuses directory or symlink destinations.

## Quality and exactness boundary

SAM Audio can respond to instrument descriptions, but a prompt such as `lead electric guitar` does **not** guarantee exact separation of lead guitar from rhythm guitar in an arbitrary mastered mix. Expect missed notes, rhythm bleed, vocals or other-instrument bleed, and generative differences. Positive solo spans can improve the semantic cue, but they do not turn the model into a verified Slash-only stem extractor.

Before a full song:

1. Run a short representative clip containing lead guitar, rhythm guitar, vocals, and a transition.
2. Audition both target and residual.
3. Check timing, phase, sample rate, frame count, and target leakage.
4. Use the result only as an experimental custom or lead candidate stem, and disclose that limitation in the final report.

Do not label the result as exact lead-only or rhythm-only separation unless independent listening and alignment checks on the actual master justify that claim.
