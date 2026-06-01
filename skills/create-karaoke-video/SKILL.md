---
name: create-karaoke-video
description: Create YouTube-ready karaoke videos from MP3, M4A, WAV, or similar audio and user-provided lyrics, with optional vocal removal, lyric cross-checking, vocal-based timing, ASS subtitle generation, and MP4 rendering. Use when the user invokes $create-karaoke-video or provides audio plus lyrics and asks for a karaoke video, sing-along video, lyric video, synced/timed lyrics, vocal removal, instrumental/no-vocals track, or YouTube-ready karaoke output.
---

# Create Karaoke Video

## New Chat Use

This skill is designed for reuse from any new Codex chat. If the user explicitly invokes `$create-karaoke-video`, follow this workflow without requiring them to repeat setup instructions.

Minimum useful inputs:

- Audio file path or uploaded audio file.
- Lyrics pasted in chat or provided as a text file.
- Vocal-removal preference: remove vocals, keep original audio, or make both.

Prompt template to offer users:

```text
Use $create-karaoke-video to create a YouTube-ready karaoke video from this audio file:
<audio path or attachment>

Remove vocals: yes

Lyrics:
<paste lyrics here>

Please cross-check obvious lyric issues, sync the words/lines to the vocals, render a 1080p MP4, and include the ASS subtitle/timing file.
```

## Workflow

Use this skill to create a finished karaoke video from an audio file and lyrics.

1. Resolve inputs: audio path, lyrics text/file, desired output name, video style, and vocal-removal preference.
2. Decide audio mode:
   - If the user explicitly asks to remove vocals, run vocal separation and use the instrumental/no-vocals stem.
   - If the user explicitly asks to keep the original audio, render with the original audio.
   - If ambiguous, ask one concise question: "Should I remove vocals, keep the original audio, or make both versions?"
3. Create or obtain timing:
   - Prefer user-provided timestamps, LRC, SRT, ASS, or line timing notes.
   - If only lyrics are provided, derive line timings from the original/vocal stem using speech or singing transcription, waveform inspection, and manual adjustment.
   - Do not invent exact timings without checking the audio. A rough evenly spaced render is only acceptable as a draft and must be labeled as such.
4. Render the video with `scripts/render_karaoke_video.py`.
5. Verify: duration, audio stream, readable captions at several timestamps, no lyric overlap, and YouTube-compatible MP4.

## Vocal Removal

Use `scripts/separate_vocals.py` as a wrapper around Demucs when vocal removal is requested.

Typical command:

```powershell
python <skill>/scripts/separate_vocals.py "song.mp3" --outdir "work/separated"
```

If Demucs is unavailable, install or request approval to install it when the task requires vocal removal:

```powershell
python -m pip install demucs
```

Use the separated `no_vocals` or instrumental stem for the final video. Keep the original audio available for transcription and timing because vocals are easier to align before removal.

## Timing Lyrics

Use the user's supplied lyric text as authoritative. Do not substitute full copyrighted lyrics from the web unless the user provided them or the use is otherwise clearly permitted. It is okay to use external timing metadata as a timing reference, but avoid reprinting large copyrighted lyric blocks in chat.

For timing details and file formats, read `references/timing-and-rendering.md` when needed.

Recommended timing file for the renderer is CSV:

```csv
start,end,text
00:10.00,00:13.40,First lyric line
00:13.40,00:18.25,Second lyric line
```

If only `start,text` is available, the renderer uses the next line start as the previous line end.

## Rendering

Use `scripts/render_karaoke_video.py` after audio and timings are ready.

Example:

```powershell
python <skill>/scripts/render_karaoke_video.py `
  --audio "work/separated/htdemucs/song/no_vocals.wav" `
  --lyrics "work/lyrics.txt" `
  --timings "work/timings.csv" `
  --title "Song Karaoke" `
  --output "outputs/song-karaoke.mp4"
```

The renderer creates a 1920x1080 MP4 with burned-in karaoke captions and a matching `.ass` subtitle file next to the output.

## Quality Rules

- Preserve user-provided lyrics exactly unless the user asks for cleanup.
- Keep vocal removal configurable; never assume the user wants it if they said otherwise.
- Use original audio for timing even when rendering the no-vocals stem.
- Check at least three representative frames after rendering.
- Save user-facing deliverables under the current task's `outputs` folder when available.
- Mention any uncertainty in lyric timing or vocal-separation quality.
