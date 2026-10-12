# Third-party notices

The source package does not bundle the dependencies, model weights, executables, music, images or fonts below. This skill's [MIT license](LICENSE) does not relicense them. Retain the applicable notices and satisfy their distribution terms if you later build a package containing third-party files. Importing or invoking an installed dependency is distinct from copying its implementation into this source tree.

| Component | Use | Upstream terms/source |
| --- | --- | --- |
| NumPy 2.4.6 | Audio arrays and arithmetic | [BSD-3-Clause; NumPy Developers](https://raw.githubusercontent.com/numpy/numpy/v2.4.6/LICENSE.txt). Binary distributions can include separately licensed components. |
| Pillow 12.3.0 | Optional still-image rendering | [MIT-CMU; Pillow/PIL contributors](https://pillow.readthedocs.io/en/stable/about.html). Its packaged dependencies have their own terms. |
| SoundFile 0.14.0 | Float WAV I/O | [BSD-3-Clause; Bastian Bechtold and contributors](https://python-soundfile.readthedocs.io/en/latest/). Uses CFFI and LGPL libsndfile; platform wheels may bundle libsndfile and codecs. |
| FFmpeg and ffprobe | Decode, encode, stream-copy tags, inspect media | [LGPL-2.1-or-later, or GPL depending on the build](https://ffmpeg.org/legal.html). The optional H.264 video command requests libx264, a GPL component. These are separately installed command-line programs. |
| audio-separator 0.44.5 | Optional local aggregate-guitar inference | [MIT; copyright 2023 karaokenerds](https://raw.githubusercontent.com/nomadkaraoke/python-audio-separator/v0.44.5/LICENSE). Installed only through optional `requirements-separator.txt`; its transitive ML/audio packages have their own licenses. |
| BS-Roformer-SW checkpoint/config | Optional, user-supplied model assets | Rights not established by this package. [Model mirror documents unknown trainer/license](https://huggingface.co/lumabeat/bs-roformer-sw); a [second mirror identifies the same checkpoint hash](https://huggingface.co/FractalSurfer/BS-RoFormer-SW-6stem). The adapter requires task-specific reviewed rights evidence and local assets, and does not download them. |
| System/user fonts, source audio, stems, artwork | User inputs and rendered outputs | Their owners' terms apply. None is supplied or licensed by this package. |

Mutagen (GPL-2.0-or-later) was a direct dependency in historical versions. It is no longer directly imported or declared in this skill's requirement files; metadata work now uses external FFmpeg/ffprobe. An optional separator environment can still contain Mutagen or other packages through transitive dependencies. This change does not remove those packages' terms, other dependencies' copyleft terms, or grant new rights to historical distributions.

The requirement files pin direct packages, not every transitive package or binary build. They are not a complete software bill of materials. Before redistributing a runtime environment, inventory its actual resolved packages, codecs and model files, retain required license texts, and assess corresponding-source obligations and license compatibility for that distribution.

Demucs is not an automatic substitute for the unresolved checkpoint. Its [maintainer distinguished pretrained weights from the MIT software license](https://github.com/facebookresearch/demucs/issues/327). A mirror's MIT tag or a code-only license is insufficient evidence for the intended use of a particular weight file.
