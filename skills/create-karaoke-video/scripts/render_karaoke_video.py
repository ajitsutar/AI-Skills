#!/usr/bin/env python3
"""Render a still-image karaoke video with authoritative user lyrics."""

import argparse
import contextlib
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
from pathlib import Path


_PUBLICATION_LOCKS_GUARD = threading.Lock()
_PUBLICATION_LOCKS = {}


def _lexists(path):
    return os.path.lexists(os.fspath(path))


@contextlib.contextmanager
def _publication_lock(lock_path):
    """Serialize publishers in this process and across cooperating processes."""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = os.path.normcase(str(lock_path.parent.resolve() / lock_path.name))
    with _PUBLICATION_LOCKS_GUARD:
        thread_lock = _PUBLICATION_LOCKS.setdefault(lock_key, threading.RLock())

    with thread_lock:
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _remove_if_linked_to(destination, staged):
    if not _lexists(destination):
        return
    try:
        if os.path.samefile(destination, staged):
            Path(destination).unlink()
    except (FileNotFoundError, OSError):
        return


def _restore_backups(backups):
    errors = []
    # The MP4 is the commit marker, so restore it last.
    for destination, backup in reversed(backups):
        if not _lexists(backup):
            continue
        if _lexists(destination):
            errors.append(f"could not restore {destination}; backup retained at {backup}")
            continue
        try:
            os.replace(backup, destination)
        except OSError as exc:
            errors.append(f"could not restore {destination} from {backup}: {exc}")
    return errors


def publish_rendered_pair(staged_video, output, staged_ass, ass_output, overwrite=False):
    """Publish ASS first and MP4 last under a rollback-safe cross-process lock."""
    staged_video = Path(staged_video)
    staged_ass = Path(staged_ass)
    output = Path(output)
    ass_output = Path(ass_output)
    if output.parent.resolve() != ass_output.parent.resolve():
        raise SystemExit("MP4 and ASS outputs must share one destination directory.")
    for staged in (staged_video, staged_ass):
        if not staged.is_file() or staged.is_symlink():
            raise SystemExit(f"Staged render is missing or unsafe: {staged}")
    for destination in (output, ass_output):
        if _lexists(destination) and (not destination.is_file() or destination.is_symlink()):
            raise SystemExit(f"Refusing to replace a non-regular output path: {destination}")

    lock_path = output.parent / f".{output.name}.publish.lock"
    with _publication_lock(lock_path):
        existing = [path for path in (output, ass_output) if _lexists(path)]
        if existing and not overwrite:
            raise SystemExit(
                "Refusing to overwrite an output created during rendering: "
                + ", ".join(str(path) for path in existing)
            )

        backups = []
        published = []
        try:
            if overwrite:
                # Remove the MP4 commit marker before its corresponding ASS.
                for destination in (output, ass_output):
                    if not _lexists(destination):
                        continue
                    if not destination.is_file() or destination.is_symlink():
                        raise SystemExit(f"Refusing to replace a non-regular output path: {destination}")
                    backup = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.bak")
                    os.replace(destination, backup)
                    backups.append((destination, backup))

            # Hard links are atomic, no-clobber publications on Windows and POSIX.
            # The MP4 appears last and acts as the completed-pair marker.
            os.link(staged_ass, ass_output)
            published.append((ass_output, staged_ass))
            os.link(staged_video, output)
            published.append((output, staged_video))
        except BaseException as exc:
            for destination, staged in reversed(published):
                _remove_if_linked_to(destination, staged)
            restore_errors = _restore_backups(backups)
            detail = f" ({'; '.join(restore_errors)})" if restore_errors else ""
            if isinstance(exc, SystemExit):
                raise SystemExit(f"{exc}{detail}") from exc
            raise SystemExit(f"Failed to publish rendered MP4/ASS pair: {exc}{detail}") from exc

        for staged in (staged_ass, staged_video):
            try:
                staged.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"WARNING: Published output is complete, but staged-file cleanup failed: {exc}", file=sys.stderr)
        for _, backup in backups:
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                print(f"WARNING: Published output is complete, but backup cleanup failed: {exc}", file=sys.stderr)


def parse_time(value):
    value = str(value).strip().replace(",", ".")
    if not value:
        raise ValueError("empty time")
    parts = value.split(":")
    try:
        if len(parts) == 1:
            result = float(parts[0])
        elif len(parts) == 2:
            seconds = float(parts[1])
            if not 0 <= seconds < 60:
                raise ValueError("seconds must be below 60")
            result = int(parts[0]) * 60 + seconds
        elif len(parts) == 3:
            minutes = int(parts[1])
            seconds = float(parts[2])
            if not 0 <= minutes < 60 or not 0 <= seconds < 60:
                raise ValueError("minutes and seconds must be below 60")
            result = int(parts[0]) * 3600 + minutes * 60 + seconds
        else:
            raise ValueError(f"unsupported time format: {value}")
    except ValueError as exc:
        raise ValueError(f"invalid time {value!r}: {exc}") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"time must be a finite non-negative value: {value}")
    return result


def ass_time(seconds):
    total_cs = max(0, int(round(float(seconds) * 100)))
    total_seconds, centis = divmod(total_cs, 100)
    total_minutes, secs = divmod(total_seconds, 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def escape_ass(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", r"\N")
    )


def _explicit_or_path(explicit, executable):
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate.resolve())
        found = shutil.which(explicit)
        if found:
            return found
        raise SystemExit(f"{executable} executable not found: {explicit}")
    return shutil.which(executable)


def find_ffmpeg(explicit=None):
    found = _explicit_or_path(explicit, "ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise SystemExit("FFmpeg not found. Install ffmpeg or imageio-ffmpeg, or pass --ffmpeg.")


def find_ffprobe(ffmpeg, explicit=None):
    found = _explicit_or_path(explicit, "ffprobe")
    if found:
        return found
    sibling = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    return str(sibling) if sibling.is_file() else None


def ffmpeg_duration(ffmpeg, audio, ffprobe=None):
    if ffprobe:
        probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(Path(audio).resolve()),
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            try:
                duration = float(probe.stdout.strip())
                if math.isfinite(duration) and duration > 0:
                    return duration
            except ValueError:
                pass

    proc = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-i", str(Path(audio).resolve())],
        capture_output=True,
        text=True,
    )
    text = proc.stderr + proc.stdout
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        raise SystemExit("Could not determine audio duration; install ffprobe or pass --duration.")
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def lyric_lines(path):
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"Lyrics file not found: {path}")
    lines = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text:
            lines.append(text)
    if not lines:
        raise SystemExit("Lyrics file contains no non-blank lines.")
    return lines


def load_csv(path):
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = [field.strip().lower() for field in (reader.fieldnames or [])]
        if "start" not in fields:
            raise SystemExit("CSV timings must include a start column; end and text are optional.")
        for line_number, raw in enumerate(reader, start=2):
            row = {str(key).strip().lower(): value for key, value in raw.items() if key is not None}
            if not (row.get("start") or "").strip():
                raise SystemExit(f"CSV timing row {line_number} has no start value.")
            try:
                start = parse_time(row["start"])
                end = parse_time(row["end"]) if (row.get("end") or "").strip() else None
            except ValueError as exc:
                raise SystemExit(f"CSV timing row {line_number}: {exc}") from exc
            rows.append({"start": start, "end": end, "text": (row.get("text") or "").strip()})
    return rows


def load_lrc(path):
    rows = []
    pattern = re.compile(r"\[(\d+:\d+(?:[.,]\d+)?)\]")
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), start=1):
        matches = list(pattern.finditer(raw))
        if not matches:
            continue
        text = raw[matches[-1].end() :].strip()
        if not text:
            continue
        for match in matches:
            try:
                start = parse_time(match.group(1))
            except ValueError as exc:
                raise SystemExit(f"LRC line {line_number}: {exc}") from exc
            rows.append({"start": start, "end": None, "text": text})
    return rows


def load_srt(path):
    content = Path(path).read_text(encoding="utf-8-sig").strip()
    if not content:
        return []
    rows = []
    timing_re = re.compile(
        r"(?P<start>\d{1,3}:\d{2}:\d{2}[,.]\d+)\s*-->\s*"
        r"(?P<end>\d{1,3}:\d{2}:\d{2}[,.]\d+)"
    )
    for block_number, block in enumerate(re.split(r"\r?\n\s*\r?\n", content), start=1):
        lines = block.splitlines()
        timing_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = timing_re.search(lines[timing_index])
        if not match:
            raise SystemExit(f"SRT block {block_number} has an invalid timing line.")
        text = " ".join(line.strip() for line in lines[timing_index + 1 :] if line.strip())
        rows.append(
            {
                "start": parse_time(match.group("start")),
                "end": parse_time(match.group("end")),
                "text": text,
            }
        )
    return rows


def load_ass(path):
    rows = []
    in_events = False
    fields = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_events = line.casefold() == "[events]"
            continue
        if not in_events:
            continue
        if line.casefold().startswith("format:"):
            fields = [field.strip().casefold() for field in line.split(":", 1)[1].split(",")]
            continue
        if not line.casefold().startswith("dialogue:"):
            continue
        if not fields or not {"start", "end", "text"}.issubset(fields):
            raise SystemExit("ASS [Events] section needs a Format line containing Start, End, and Text.")
        values = line.split(":", 1)[1].lstrip().split(",", len(fields) - 1)
        if len(values) != len(fields):
            raise SystemExit(f"ASS dialogue line {line_number} does not match its Format line.")
        event = dict(zip(fields, values))
        text = re.sub(r"\{[^}]*\}", "", event["text"])
        text = text.replace(r"\N", " ").replace(r"\n", " ").replace(r"\h", " ").strip()
        rows.append({"start": parse_time(event["start"]), "end": parse_time(event["end"]), "text": text})
    return rows


def load_timings(path):
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"Timing file not found: {path}")
    suffix = path.suffix.lower()
    loaders = {".csv": load_csv, ".lrc": load_lrc, ".srt": load_srt, ".ass": load_ass}
    if suffix not in loaders:
        raise SystemExit("Timing file must use .csv, .lrc, .srt, or .ass.")
    rows = loaders[suffix](path)
    if not rows:
        raise SystemExit(f"Timing file contains no usable events: {path}")
    return rows


def _normalized_lyric(text):
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def apply_authoritative_lyrics(rows, lines, allow_mismatch=False):
    if len(rows) != len(lines):
        raise SystemExit(
            f"Timing event count ({len(rows)}) does not match lyric line count ({len(lines)}). "
            "Make the timing file contain exactly one event per non-blank lyric line."
        )
    merged = []
    for index, (row, lyric) in enumerate(zip(rows, lines), start=1):
        timing_text = row.get("text") or ""
        if timing_text and _normalized_lyric(timing_text) != _normalized_lyric(lyric) and not allow_mismatch:
            raise SystemExit(
                f"Timing text differs from authoritative lyrics at line {index}. "
                "Correct the timing file or pass --allow-timing-text-mismatch to map by line order."
            )
        merged.append({**row, "text": lyric})
    return merged


def complete_ends(rows, duration):
    duration = float(duration)
    if not math.isfinite(duration) or duration <= 0:
        raise SystemExit("Audio duration must be a finite positive number.")
    completed = []
    previous_start = None
    for index, source in enumerate(rows, start=1):
        start = float(source["start"])
        if not math.isfinite(start) or start < 0 or start >= duration:
            raise SystemExit(f"Timing row {index} start must be within the audio duration.")
        if previous_start is not None and start <= previous_start:
            raise SystemExit("Timing rows must be in strictly increasing start-time order.")
        completed.append({**source, "start": start})
        previous_start = start

    for index, row in enumerate(completed):
        start = row["start"]
        next_start = completed[index + 1]["start"] if index + 1 < len(completed) else None
        end = row.get("end")
        if end is None:
            if next_start is None:
                end = min(duration, start + 5.0)
            else:
                gap = min(0.04, max(0.001, (next_start - start) / 4))
                end = next_start - gap
        else:
            end = float(end)
        if not math.isfinite(end) or end <= start:
            raise SystemExit(f"Timing row {index + 1} must end after it starts.")
        if end > duration + 0.001:
            raise SystemExit(f"Timing row {index + 1} ends after the audio duration.")
        if next_start is not None and end > next_start + 0.0001:
            raise SystemExit(f"Timing row {index + 1} overlaps the next lyric line.")
        row["end"] = min(end, duration)
    return completed


def draft_timings(lines, duration, start=5.0, end=None):
    duration = float(duration)
    start = float(start)
    end = min(duration, max(start + 1.0, duration - 5.0)) if end is None else float(end)
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end > duration or end <= start:
        raise SystemExit("Draft timing range must be finite, positive, ordered, and within the audio duration.")
    step = (end - start) / len(lines)
    gap = min(0.04, step / 4)
    return [
        {
            "start": start + index * step,
            "end": end if index == len(lines) - 1 else start + (index + 1) * step - gap,
            "text": text,
        }
        for index, text in enumerate(lines)
    ]


def _pillow():
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ModuleNotFoundError as exc:
        raise SystemExit("Pillow is required for rendering. Install it with: python -m pip install Pillow") from exc
    return Image, ImageDraw, ImageFilter, ImageFont


def _scalable_title_font(ImageFont, size=50):
    candidates = (
        "DejaVuSans.ttf",
        "Arial.ttf",
        "LiberationSans-Regular.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    raise SystemExit("No scalable title font found; install DejaVu Sans/Arial or omit --title.")


def make_background(path, title=None):
    Image, ImageDraw, ImageFilter, ImageFont = _pillow()
    width, height = 1920, 1080
    image = Image.new("RGB", (width, height), (5, 12, 28))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (int(5 + 14 * ratio), int(12 + 10 * ratio), int(28 + 32 * ratio))
        draw.line((0, y, width, y), fill=color)

    glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((420, 40, 1500, 1120), fill=(23, 95, 125, 115))
    glow = glow.filter(ImageFilter.GaussianBlur(150))
    image = Image.alpha_composite(image.convert("RGBA"), glow)
    if title:
        title_draw = ImageDraw.Draw(image)
        font = _scalable_title_font(ImageFont, 50)
        title_draw.text((70, 50), title, fill=(220, 235, 245, 220), font=font)
    image.convert("RGB").save(path, quality=95)


def style_header(font_name="Arial"):
    if any(character in font_name for character in ",\r\n"):
        raise SystemExit("ASS font name cannot contain commas or newlines.")
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Current,{font_name},64,&H0000D7FF,&H00F7F8FF,&H00100804,&H80000000,0,0,0,0,100,100,0,0,1,4,1,5,60,60,40,1
Style: Dim,{font_name},42,&H00D5DAE8,&H00D5DAE8,&H00100804,&H80000000,0,0,0,0,100,100,0,0,1,3,1,5,80,80,40,1
Style: Far,{font_name},34,&H0099A1B5,&H0099A1B5,&H00100804,&H80000000,0,0,0,0,100,100,0,0,1,2,1,5,80,80,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def karaoke_text(text, start, end):
    words = text.split()
    if not words:
        return ""
    total_cs = max(1, int(round((end - start) * 100)))
    weights = [max(1, sum(character.isalnum() for character in word)) for word in words]
    weight_sum = sum(weights)
    chunks = []
    cumulative = 0
    previous_boundary = 0
    for index, (word, weight) in enumerate(zip(words, weights)):
        cumulative += weight
        boundary = total_cs if index == len(words) - 1 else round(total_cs * cumulative / weight_sum)
        duration = max(0, boundary - previous_boundary)
        previous_boundary = boundary
        chunks.append(f"{{\\kf{duration}}}{escape_ass(word)}" + (" " if index < len(words) - 1 else ""))
    return "".join(chunks)


def event(layer, start, end, style, text, y, fade=80):
    tag = f"{{\\an5\\pos(960,{y})\\fad({fade},{fade})}}"
    return f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{tag}{text}\n"


def build_ass(rows, path, font_name="Arial"):
    output = [style_header(font_name)]
    y_map = {-2: 325, -1: 430, 0: 540, 1: 665, 2: 760}
    for index, row in enumerate(rows):
        start, end, text = row["start"], row["end"], row["text"]
        for relative in (-2, -1, 1, 2):
            neighbor = index + relative
            if 0 <= neighbor < len(rows):
                style = "Dim" if abs(relative) == 1 else "Far"
                output.append(event(0, start, end, style, escape_ass(rows[neighbor]["text"]), y_map[relative]))
        output.append(event(2, start, end, "Current", karaoke_text(text, start, end), y_map[0]))
    Path(path).write_text("".join(output), encoding="utf-8-sig")


def render(ffmpeg, audio, background, ass_file, output, duration):
    audio = Path(audio).resolve()
    background = Path(background).resolve()
    ass_file = Path(ass_file).resolve()
    output = Path(output).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", ass_file.name):
        raise SystemExit("Temporary ASS filename must contain only safe ASCII filename characters.")
    command = [
        ffmpeg,
        "-y",
        "-nostdin",
        "-hide_banner",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(background),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        f"ass=filename={ass_file.name}",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output),
    ]
    subprocess.run(command, check=True, cwd=str(ass_file.parent))
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit("FFmpeg reported success but did not create a non-empty MP4.")


def verify_rendered_output(ffmpeg, output, expected_duration, ffprobe=None):
    output = Path(output).resolve()
    actual_duration = None
    if ffprobe:
        probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration:stream=codec_type",
                "-of",
                "json",
                str(output),
            ],
            capture_output=True,
            text=True,
        )
        if probe.returncode != 0:
            raise SystemExit(f"ffprobe could not inspect rendered MP4: {probe.stderr.strip()}")
        try:
            metadata = json.loads(probe.stdout)
            actual_duration = float(metadata["format"]["duration"])
            stream_types = {stream.get("codec_type") for stream in metadata.get("streams", [])}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SystemExit("ffprobe returned incomplete rendered-MP4 metadata.") from exc
        if not {"audio", "video"}.issubset(stream_types):
            raise SystemExit("Rendered MP4 must contain both an audio and a video stream.")
    else:
        actual_duration = ffmpeg_duration(ffmpeg, output)

    tolerance = max(0.75, float(expected_duration) * 0.002)
    if not math.isfinite(actual_duration) or abs(actual_duration - float(expected_duration)) > tolerance:
        raise SystemExit(
            f"Rendered MP4 duration {actual_duration:.3f}s does not match expected "
            f"{float(expected_duration):.3f}s (tolerance {tolerance:.3f}s)."
        )

    decoded = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(output),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    if decoded.returncode != 0:
        raise SystemExit(f"Rendered MP4 failed decode verification: {decoded.stderr.strip()}")


def validate_paths(audio, lyrics, timings, output, overwrite=False):
    inputs = {Path(audio).resolve(), Path(lyrics).resolve()}
    if timings:
        inputs.add(Path(timings).resolve())
    output = Path(output).resolve()
    ass_output = output.with_suffix(".ass")
    if output.suffix.lower() != ".mp4":
        raise SystemExit("Output filename must end in .mp4.")
    if output in inputs or ass_output in inputs:
        raise SystemExit("Output MP4/ASS paths must not collide with an input file.")
    existing = [path for path in (output, ass_output) if path.exists()]
    if existing and not overwrite:
        raise SystemExit(
            "Refusing to overwrite existing output. Pass --overwrite to replace: "
            + ", ".join(str(path) for path in existing)
        )
    return output, ass_output


def main():
    parser = argparse.ArgumentParser(description="Render a 1080p karaoke MP4 from audio and authoritative lyrics.")
    parser.add_argument("--audio", required=True, help="Input audio file.")
    parser.add_argument("--lyrics", required=True, help="Authoritative plain lyrics text file.")
    parser.add_argument("--timings", help="CSV, LRC, SRT, or ASS timing file with one event per lyric line.")
    parser.add_argument("--output", required=True, help="Destination .mp4 path.")
    parser.add_argument("--title", default="")
    parser.add_argument("--font-name", default="Arial", help="Installed font family used by libass.")
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--ffprobe", default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--draft-start", type=float, default=5.0)
    parser.add_argument("--draft-end", type=float, default=None)
    parser.add_argument("--allow-timing-text-mismatch", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    audio = Path(args.audio)
    lyrics = Path(args.lyrics)
    if not audio.is_file():
        raise SystemExit(f"Audio file not found: {audio}")
    if not lyrics.is_file():
        raise SystemExit(f"Lyrics file not found: {lyrics}")
    if args.timings and not Path(args.timings).is_file():
        raise SystemExit(f"Timing file not found: {args.timings}")

    output, ass_output = validate_paths(audio, lyrics, args.timings, args.output, args.overwrite)
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    ffprobe = find_ffprobe(ffmpeg, args.ffprobe)
    duration = args.duration if args.duration is not None else ffmpeg_duration(ffmpeg, audio, ffprobe)
    if not math.isfinite(duration) or duration <= 0:
        raise SystemExit("Duration must be a finite positive number.")

    lines = lyric_lines(lyrics)
    if args.timings:
        timing_rows = load_timings(args.timings)
        rows = apply_authoritative_lyrics(timing_rows, lines, args.allow_timing_text_mismatch)
        rows = complete_ends(rows, duration)
    else:
        print("WARNING: No timings supplied. Creating a rough evenly spaced draft.", file=sys.stderr)
        rows = draft_timings(lines, duration, args.draft_start, args.draft_end)

    with tempfile.TemporaryDirectory(prefix=f".{output.stem}-render-", dir=output.parent) as temporary:
        temporary = Path(temporary)
        background = temporary / "background.png"
        temporary_ass = temporary / "captions.ass"
        temporary_video = temporary / "video.mp4"
        make_background(background, args.title)
        build_ass(rows, temporary_ass, args.font_name)
        render(ffmpeg, audio, background, temporary_ass, temporary_video, duration)
        verify_rendered_output(ffmpeg, temporary_video, duration, ffprobe)
        publish_rendered_pair(temporary_video, output, temporary_ass, ass_output, args.overwrite)

    print(output)
    print(ass_output)


if __name__ == "__main__":
    main()
