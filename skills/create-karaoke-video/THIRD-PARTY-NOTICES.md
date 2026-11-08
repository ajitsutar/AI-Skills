# Third-party notices

The skill's [MIT license](LICENSE) covers its own code and documentation; it does
not relicense external software, checkpoints, fonts, audio, or lyrics. The
dependencies below are installed separately, not vendored in this folder.

## Runtime components

| Component | Use | Upstream terms and credits |
| --- | --- | --- |
| [Demucs](https://github.com/adefossez/demucs) | Optional vocal separation through its command line | [MIT](https://github.com/adefossez/demucs/blob/main/LICENSE); copyright Meta Platforms, Inc. and affiliates. Maintained by Alexandre Défossez. Checkpoint status is separate below. |
| [audio-separator 0.48.0](https://github.com/nomadkaraoke/python-audio-separator/tree/v0.48.0) | Optional registered MelBand Roformer vocal separation | [MIT](https://raw.githubusercontent.com/nomadkaraoke/python-audio-separator/v0.48.0/LICENSE); copyright 2023 karaokenerds. Installed separately through the pinned optional requirements file; its checkpoint/config status is separate below. |
| [Pillow](https://pillow.readthedocs.io/en/stable/about.html#license) | Background and title rendering | MIT-CMU; PIL/Pillow contributors. Its distribution can include libraries with additional notices. |
| [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg) | Optional FFmpeg executable discovery | [BSD-2-Clause](https://github.com/imageio/imageio-ffmpeg/blob/main/LICENSE); imageio contributors. Its Python wrapper license does not replace the terms of any FFmpeg binary supplied with a wheel. |
| [FFmpeg and ffprobe](https://ffmpeg.org/legal.html) | Encode, inspect, and verify video/audio | LGPL-2.1-or-later baseline; optional GPL components change the applicable build terms. Use the notices and build configuration of the installed executable. |
| [libass](https://github.com/libass/libass) | ASS subtitle rendering inside FFmpeg | [ISC](https://github.com/libass/libass/blob/master/COPYING); libass contributors. |
| libx264 | H.264 encoder selected by the renderer | FFmpeg's [licensing page](https://ffmpeg.org/legal.html) identifies libx264 as a GPL component. The skill does not distribute an encoder binary. |

Package versions and transitive dependencies depend on the installed environment.
If distributing that environment or binaries, include the exact packages' and
builds' required license/notice files and satisfy their source-distribution terms
where applicable. This dependency summary is not a replacement for those notices.

## Model weights

In [Demucs issue 327](https://github.com/facebookresearch/demucs/issues/327),
maintainer Alexandre Défossez states that the pretrained weights are outside the
MIT license and provided for scientific purposes. The newer default `htdemucs`
model card, [`adefossez/HTDemucs`](https://huggingface.co/adefossez/HTDemucs),
identifies checkpoint `955717e8` but contained no explicit weight-specific license
declaration when checked on October 12, 2026. Its link to the code repository is
not treated here as a superseding general-use grant.

Weights are downloaded by Demucs, not bundled with this skill. General karaoke,
personal practice, YouTube publication, and commercial work must not be assumed
to qualify as scientific research. Use separately permitted weights or a
licensed instrumental for those activities. Review the selected model's actual
terms; other models or permissions can differ.

The opt-in audio-separator adapter is restricted to the v0.48.0 registry entry
`vocals_mel_band_roformer.ckpt` / `vocals_mel_band_roformer.yaml`, labeled there
as MelBand Roformer vocals by Kimberley Jensen. The upstream
[model registry](https://raw.githubusercontent.com/nomadkaraoke/python-audio-separator/v0.48.0/audio_separator/models.json)
identifies the files; its
[checksum manifest](https://raw.githubusercontent.com/nomadkaraoke/python-audio-separator/v0.48.0/audio_separator/model-checksums.json)
records checkpoint SHA-256
`87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e`
and config SHA-256
`b958b29c8f7195f0d86bee6759a33980db675c4ecaf2fcaa80fa125828e6cd38`.
The pinned software verifies downloads/cache entries, and this wrapper verifies
both files again after inference and before publication. Model files are stored
only in the external cache chosen by `--model-dir` and are not distributed here.
Registry metadata and hashes establish identity, not a license grant. The
matching original checkpoint is published in Kimberley Jensen's
[Hugging Face model repository](https://huggingface.co/KimberleyJSN/melbandroformer),
whose current model card declares MIT. Its verified
[April 22, 2026 commit](https://huggingface.co/KimberleyJSN/melbandroformer/commit/ac9b0614ab3cd7f77219e18ba494dfd93956c348)
changed the card's license metadata from GPL-3.0 to MIT. Record this
checkpoint-specific primary evidence with `rights_basis: open_license`; do not
substitute audio-separator's software license as the evidence.

The separator requires `--rights-record` and `--use-category`. The JSON record
must contain:

| Field | Meaning |
| --- | --- |
| `model` | Exact value passed to `--model`. |
| `use_category` | Same as `--use-category`: `scientific_research`, `personal`, `publication`, or `commercial`. |
| `intended_use` | Specific description of the actual activity. |
| `rights_basis` | `scientific_purposes` only for actual scientific research, `open_license` with checkpoint-specific license evidence, or `separate_permission`. |
| `evidence` | Source or local permission record establishing terms for the selected weights and intended use, not merely the software's MIT license. |
| `confirmed_by_operator` | JSON `true` after the operator has reviewed that evidence. |

Missing, mismatched, or unsupported records fail before either backend is checked,
executed, or allowed to create a model cache/output directory. This is an operator assertion and consistency check, not an independent
license verifier. Do not generate a record solely to bypass the check. Keep any
private permission evidence outside the shared skill. The renderer works with
already supplied audio without using or downloading a separation model.

## Fonts, formats, and user content

The renderer uses installed fonts and does not embed font files in the generated
MP4. Font names are references to external resources: [DejaVu](https://dejavu-fonts.github.io/License.html)
retains Bitstream/Arev terms with DejaVu changes in the public domain;
[Liberation](https://github.com/liberationfonts/liberation-fonts/blob/main/LICENSE)
uses SIL Open Font License 1.1; Arial is governed by its installed distribution's
terms. Microsoft's [font FAQ](https://learn.microsoft.com/en-us/typography/fonts/font-faq)
distinguishes rendered video captions from redistributing font files.

ASS headers and karaoke tags follow the documented
[ASS subtitle format](https://aegisub.org/docs/latest/ass_tags/); no Aegisub
implementation is bundled. Audio and lyrics supplied for a render retain their
own rights. A license for this skill or its tools does not authorize publishing
those materials.
