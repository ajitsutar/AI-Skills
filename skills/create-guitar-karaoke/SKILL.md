---
name: create-guitar-karaoke
description: Create guitar-karaoke mixes and still-image videos by muting an aggregate guitar estimate across a song or chosen sections, or removing verified supplied lead, solo guitar, rhythm, or custom stems while retaining vocals. Use for guitar removal, backing tracks, practice mixes, stem subtraction, and YouTube-ready guitar karaoke; do not use for vocal or lyric karaoke.
---

# Create Guitar Karaoke

Create a practice MP3 from a lawfully obtained song, keep the vocals and other instruments, and remove the requested guitar part for either the whole song or selected sections. Optionally create a still-image MP4 and assist with an authorized YouTube upload.

Resolve `scripts/` and `references/` relative to this `SKILL.md`, never relative to the current working directory.

## Resolve the Request

Identify four things before processing:

1. Source audio path.
2. Target: all guitars, lead guitar, rhythm guitar, or a supplied custom stem.
3. Scope: whole song, selected windows, or everywhere except selected windows.
4. Deliverables: uncompressed float WAV, MP3, still image, MP4, and/or upload.

Translate natural-language requests with this table:

| User intent | Stem | Scope | Default result |
| --- | --- | --- | --- |
| Remove all guitars for the whole song | Aggregate guitar | Whole | Default guitar-labelled estimate across the song; coverage and bleed vary |
| Remove all guitars in these sections | Aggregate guitar | Windows | Default guitar-labelled estimate only in the selected sections |
| Remove just the lead solos | Lead stem if available; otherwise aggregate guitar | Solo windows | Role-specific with a verified lead stem; fallback also removes rhythm guitar inside the windows |
| Remove just rhythm guitar | Rhythm stem | Whole or windows | Role-specific only with a compatible rhythm stem |
| Keep solos but remove backing guitars | Aggregate guitar | Outside solo windows | Approximation: all guitars remain during the solo windows |
| Remove a supplied instrument stem | User-supplied stem | Whole, windows, or outside windows | Follows the supplied stem after alignment, polarity, and gain are verified |

Never describe aggregate-guitar windowing as semantic lead/rhythm separation. If the requested exact stem is unavailable, state the limitation and ask before using an approximation that materially changes the result.

Read [references/modes-and-backends.md](references/modes-and-backends.md) when choosing a separation method or handling lead-versus-rhythm requests.

## Workflow

1. Verify the user supplied or lawfully controls the audio. Never commit source audio, stems, checkpoints, credentials, cookies, or generated song outputs to the skill repository. Upload only a final deliverable when the user explicitly authorizes it.
2. Resolve target and scope from the table above.
3. Resolve timing:
   - Prefer timestamps from the user.
   - Otherwise inspect the exact local master, not a music video with a potentially different intro or edit.
   - Use waveform, spectrogram, lyric gaps, and listening checks. Treat web timestamps as hints until aligned to the local file.
   - Include solo sections that overlap vocals; vocals are retained because the guitar stem is subtracted from the original mix.
4. Choose the stem source:
   - For aggregate guitar, use the open-source `audio-separator` workflow and verified BS-RoFormer-SW checkpoint in `scripts/build_guitar_karaoke.py`.
   - For exact lead-only or rhythm-only work, use a verified compatible separator or a user-supplied full-length stem, then pass it with `--stem-file` and the matching `--stem-kind`.
5. Before a full-song CPU run, process a representative 20-25-second smoke-test window and audition the target, retained vocals, and leakage.
6. Keep processing in 32-bit float WAV, encode MP3 once, and render video from the uncompressed edited master.
7. Verify representative points inside and outside every edit window. Let the user audition a short failure point before uploading when separation quality is uncertain.

## Commands

Install prerequisites in an isolated environment after obtaining approval for downloads:

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -r "<skill-dir>/scripts/requirements.txt"
```

macOS, Linux, or WSL:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r '<skill-dir>/scripts/requirements.txt'
```

FFmpeg must also be installed and available on `PATH`, or supplied with `--ffmpeg`.

In the commands below, replace `<skill-dir>` with the directory containing this `SKILL.md`. Replace `<python>` with the isolated interpreter: `& ".\.venv\Scripts\python.exe"` in PowerShell, or `./.venv/bin/python` on macOS, Linux, or WSL.

Remove aggregate guitar from the entire song:

```text
<python> "<skill-dir>/scripts/build_guitar_karaoke.py" "song.mp3" --scope whole --work-dir "work/song" --output "outputs/song - All Guitars Removed.mp3"
```

Remove aggregate guitar only during lead-solo windows while retaining vocals:

```text
<python> "<skill-dir>/scripts/build_guitar_karaoke.py" "song.mp3" --scope windows --window "01:20.00-01:45.50" --window "02:50.25-03:10.00" --window "04:05.00-end" --work-dir "work/song" --output "outputs/song - Solo Sections Guitar Muted.mp3"
```

Remove an exact full-length rhythm stem supplied by another separator:

```text
<python> "<skill-dir>/scripts/build_guitar_karaoke.py" "song.mp3" --scope whole --stem-file "stems/rhythm-guitar.wav" --stem-kind rhythm-guitar --work-dir "work/song-rhythm" --output "outputs/song - Rhythm Guitar Removed.mp3"
```

Approximate a rhythm-muted practice mix by removing aggregate guitar everywhere except the known lead windows:

```text
<python> "<skill-dir>/scripts/build_guitar_karaoke.py" "song.mp3" --scope outside-windows --window "01:20.00-01:45.50" --window "02:50.25-03:10.00" --window "04:05.00-end" --work-dir "work/song-rhythm-approx" --output "outputs/song - Backing Guitars Reduced.mp3"
```

The script splits long material into context-padded tiles, verifies the model checkpoint before inference, crossfades the estimates, subtracts the selected stem from the original master, copies only descriptive metadata, and writes a JSON report. Use `--stage prepare`, `--stage separate`, or `--stage mix` to resume a long CPU workflow; immutable resume arguments are checked against the manifest. Use a fresh work directory per source. Add `--overwrite` only for an intentional deliverable redo and `--cleanup-unused-stems` only after verification.

## Still Image and Video

Use a user-provided, licensed, public-domain, or newly generated image. Do not download or reuse album art merely because it appears online.

```text
<python> "<skill-dir>/scripts/make_practice_still.py" --image "background.png" --title "SONG TITLE" --subtitle "GUITAR KARAOKE" --output "outputs/song-still.png"
```

Pass `--image` and `--video-output` to `build_guitar_karaoke.py` to render a 1080p H.264/AAC MP4 from the uncompressed edited audio.

Read [references/quality-video-and-upload.md](references/quality-video-and-upload.md) before final verification or any upload.

## Quality Rules

- The helper intentionally converts working audio to 44.1 kHz stereo for the pinned model. Report this conversion when the source format differs.
- Use 10 seconds of model context and 0.35-second raised-cosine edit fades unless listening tests justify different values.
- Split long spans into bounded model tiles. The mixer still holds several full-length arrays, so honor its RAM preflight for unusually long material.
- Expect six generated model stems and substantial temporary disk use. Check free space and optionally clean unused stems only after successful verification.
- Keep the decoded 32-bit float mix unchanged outside the selected subtraction envelope. MP3 and video outputs are fully re-encoded and may receive one global headroom gain.
- Do not claim that vocals are perfectly unchanged: model leakage can remove a small amount of other content with the guitar estimate.
- Do not silently substitute a center-cancel, EQ filter, or aggregate guitar stem for exact lead/rhythm separation.
- Report the model, stem kind, scope, windows, approximations, and validation results to the user.

## YouTube Boundary

Only upload when the user explicitly authorizes it and specifies visibility. Use the available authenticated browser or API without exposing credentials. Stop for CAPTCHA, sign-in, two-factor authentication, copyright acknowledgements, or any irreversible confirmation the user must personally handle. Content ID claims can still occur even for unlisted videos.
