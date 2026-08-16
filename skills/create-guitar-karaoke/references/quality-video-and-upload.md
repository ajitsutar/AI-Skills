# Quality, Video, and Upload

## Audio Verification

Before delivery:

1. Confirm the edited 32-bit float WAV has the same duration, sample rate, and channel count as the decoded source.
2. Confirm samples outside the requested envelope are unchanged in the uncompressed float domain.
3. Listen at every fade boundary and at the loudest guitar passage in each target section.
4. Listen to at least one overlapping-vocal passage. Check for vocal thinning, phase artifacts, cymbal loss, and piano leakage.
5. Compare the requested target with the actual stem kind in the JSON report.
6. Decode-test the final MP3 and inspect its duration, bitrate, and descriptive tags. Do not propagate stale loudness-normalization or encoder bookkeeping tags.

When a user identifies a failure point such as `4:10`, always audition that exact point after reprocessing.

## Still Image

Use an image the user provided or is authorized to use, or generate a new non-infringing image. A generic guitar-themed scene is safer than copied album art or an official music-video frame.

The supplied still helper makes a centered 1920 x 1080 crop, adds a restrained dark title gradient, and draws title/subtitle text. Inspect the output before rendering because font metrics vary by operating system.

## Video Rendering

Render from the uncompressed edited float WAV, not from the MP3, to avoid another lossy generation. If the float edit exceeds the configured delivery peak, apply the same single global headroom gain to MP3 and video audio. Recommended delivery is:

- 1920 x 1080
- H.264 video, `yuv420p`
- AAC audio at a high bitrate
- `faststart` enabled
- duration governed by the audio stream

After rendering, decode-test the MP4 and inspect at least the opening, one middle point, and the ending. Confirm that the still fills the frame and that the audio is the edited mix rather than the source.

## YouTube Upload

Uploading changes external state. Only proceed after the user explicitly asks for it and identifies the channel and visibility.

- Prefer `Unlisted` when requested.
- Use a title and description that accurately identify the work as a practice or guitar-karaoke mix.
- Do not claim ownership of the underlying song or composition.
- Expect possible Content ID matching, monetization restrictions, regional blocking, or removal even for unlisted uploads.
- Do not bypass copyright checks or advise evasion.
- Pause for CAPTCHA, authentication, two-factor prompts, copyright acknowledgements, or any confirmation that requires the account holder's judgment.
- If browser automation is unavailable or cannot isolate its own window, deliver the verified MP4 and concise manual upload steps.

Never commit the upload file, thumbnail, authentication state, or channel-specific private data to the skill repository.
