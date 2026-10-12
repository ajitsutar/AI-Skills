# Third-party notices

The skill's [MIT license](LICENSE) covers its own code and documentation; it does
not relicense external software, checkpoints, fonts, audio, or lyrics. The
dependencies below are installed separately, not vendored in this folder.

## Runtime components

| Component | Use | Upstream terms and credits |
| --- | --- | --- |
| [Demucs](https://github.com/adefossez/demucs) | Optional vocal separation through its command line | [MIT](https://github.com/adefossez/demucs/blob/main/LICENSE); copyright Meta Platforms, Inc. and affiliates. Maintained by Alexandre Défossez. Checkpoint status is separate below. |
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

The separator requires `--rights-record` and `--use-category`. The JSON record
must contain:

| Field | Meaning |
| --- | --- |
| `model` | Exact value passed to `--model`. |
| `use_category` | Same as `--use-category`: `scientific_research`, `personal`, `publication`, or `commercial`. |
| `intended_use` | Specific description of the actual activity. |
| `rights_basis` | `scientific_purposes` only for actual scientific research; otherwise `separate_permission`. |
| `evidence` | Source or local permission record establishing terms for the selected weights and intended use, not merely the software's MIT license. |
| `confirmed_by_operator` | JSON `true` after the operator has reviewed that evidence. |

Missing, mismatched, or unsupported records fail before Demucs is checked or
executed. This is an operator assertion and consistency check, not an independent
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
