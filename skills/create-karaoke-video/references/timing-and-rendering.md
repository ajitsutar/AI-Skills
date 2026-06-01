# Timing And Rendering

## Timing Sources

Prefer timing sources in this order:

1. User-provided LRC/SRT/ASS/timestamps.
2. Timing metadata from an official or clearly relevant source, used only as timing guidance.
3. A transcription/alignment pass on the original audio or vocal stem.
4. Manual phrase timing from waveform peaks, lyric structure, and listening/visual inspection.

When only plain lyrics are provided, create a timing draft and inspect it. Singing, reverb, and background music often make ASR unreliable; treat ASR output as timing hints, not gospel.

## CSV Timing Format

The bundled renderer accepts CSV with either:

```csv
start,end,text
00:10.00,00:13.40,First lyric line
00:13.40,00:18.25,Second lyric line
```

or:

```csv
start,text
00:10.00,First lyric line
00:13.40,Second lyric line
```

Supported time forms: `SS`, `MM:SS`, `MM:SS.xx`, or `HH:MM:SS.xx`.

## LRC Timing Format

LRC is also accepted:

```text
[00:10.00]First lyric line
[00:13.40]Second lyric line
```

Blank lyric lines are ignored for timing. Use blank lines in the plain lyrics file only for grouping or readability.

## Alignment Notes

- Use the user-provided lyric text for displayed captions.
- Split very long lyric lines into shorter phrase lines before timing.
- If rendering word-style highlighting from line timings, distribute highlight duration across words by character length. This is approximate but visually useful.
- For fast taans, sargam, ad libs, or vocal runs, create short phonetic/sargam lines instead of repeating the chorus unless the singer is actually repeating it.
- Keep the final line visible only until the vocal phrase ends; do not stretch it across a long instrumental outro.

## Rendering Checks

After rendering, inspect:

- MP4 duration matches the audio.
- Audio is the intended mode: instrumental/no-vocals, original, or both.
- Captions are readable in the first verse, chorus, and late section.
- No line overlaps or text overflow on 1920x1080.
- Output file is in the task `outputs` folder if the workspace has one.
