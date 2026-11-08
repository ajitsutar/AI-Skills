# Provenance

The scripts orchestrate external programs, manipulate supplied audio arrays and render title stills. No trained weights, music, album artwork, fonts or external binaries are bundled. The experimental lead/rhythm helper includes MIT-licensed Mel-Band RoFormer inference code under `scripts/vendor/listra92_roformer`, with its retained LICENSE and NOTICE.md identifying upstream revisions and modifications. That software license does not license the listra92 weights. Raised-cosine fades and overlap/add mixing are general signal-processing techniques. The Windows memory structure follows the documented [Microsoft MEMORYSTATUSEX interface](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/ns-sysinfoapi-memorystatusex).

The optional backend is credited to [Nomad Karaoke / python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator/tree/v0.48.0). Its [model registry](https://raw.githubusercontent.com/nomadkaraoke/python-audio-separator/v0.48.0/audio_separator/models.json) associates BS-Roformer-SW with the rehoster jarredou; this is not a verified original-trainer attribution. Current [model provenance notes](https://huggingface.co/lumabeat/bs-roformer-sw) identify the same pinned checkpoint hash and describe its trainer and license as unknown. The skill makes no claim to own or license that checkpoint.

The media adapter follows [ffprobe's documented JSON output](https://ffmpeg.org/ffprobe.html) and [FFmpeg stream-copy/metadata options](https://ffmpeg.org/ffmpeg.html); it does not vendor their source. Synthetic tests contain generated audio arrays rather than third-party recordings.

Metadata processing uses standard-library JSON and external FFmpeg/ffprobe commands.
The optional prompted adapter follows Meta's public SAMAudio/SAMAudioProcessor API;
it does not vendor SAM Audio code or weights. Its custom model license and gated
access remain separate from this skill's MIT license.
Authorized supplied stems are the default; no model is downloaded automatically.
The optional local model path requires asset hashes and a model-use rights record.
[Backend guidance](references/modes-and-backends.md) explains its scope.

The [MIT license](LICENSE) covers contributions the repository owner can license.
Third-party rights remain separate; retain [third-party notices](THIRD-PARTY-NOTICES.md).
Keep historical source-comparison reports in the local archive. Record original
sources, modifications and applicable licenses for future external contributions.
