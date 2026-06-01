#!/usr/bin/env python
import argparse
import csv
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

WIDTH = 1920
HEIGHT = 1080


def parse_time(value):
    value = str(value).strip()
    if not value:
        raise ValueError("empty time")
    parts = value.split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"unsupported time format: {value}")


def ass_time(seconds):
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - math.floor(seconds)) * 100))
    if centis == 100:
        secs += 1
        centis = 0
    if secs == 60:
        minutes += 1
        secs = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def escape_ass(text):
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def find_ffmpeg(explicit=None):
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise SystemExit("FFmpeg not found. Install ffmpeg or imageio-ffmpeg, or pass --ffmpeg.")


def ffmpeg_duration(ffmpeg, audio):
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", str(audio)], capture_output=True, text=True)
    text = proc.stderr + proc.stdout
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        raise SystemExit("Could not determine audio duration; pass --duration.")
    return int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))


def lyric_lines(path):
    lines = []
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        text = line.strip()
        if text:
            lines.append(text)
    return lines


def load_csv(path):
    rows = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "start" not in reader.fieldnames or "text" not in reader.fieldnames:
            raise SystemExit("CSV timings must include at least start,text columns.")
        for row in reader:
            text = (row.get("text") or "").strip()
            if not text:
                continue
            start = parse_time(row["start"])
            end = parse_time(row["end"]) if row.get("end") else None
            rows.append({"start": start, "end": end, "text": text})
    return rows


def load_lrc(path):
    rows = []
    pattern = re.compile(r"\[(\d+:\d+(?:\.\d+)?)\](.*)")
    for raw in Path(path).read_text(encoding="utf-8-sig").splitlines():
        match = pattern.match(raw.strip())
        if not match:
            continue
        text = match.group(2).strip()
        if text:
            rows.append({"start": parse_time(match.group(1)), "end": None, "text": text})
    return rows


def load_timings(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".lrc":
        return load_lrc(path)
    return load_csv(path)


def complete_ends(rows, duration):
    for i, row in enumerate(rows):
        if row["end"] is None:
            next_start = rows[i + 1]["start"] if i + 1 < len(rows) else min(duration, row["start"] + 5.0)
            row["end"] = max(row["start"] + 0.8, next_start - 0.04)
        else:
            row["end"] = max(row["start"] + 0.8, row["end"])
    return rows


def draft_timings(lines, duration, start=5.0, end=None):
    end = end if end is not None else max(start + 1, duration - 5.0)
    step = (end - start) / max(1, len(lines))
    rows = []
    for i, text in enumerate(lines):
        rows.append({"start": start + i * step, "end": start + (i + 1) * step - 0.04, "text": text})
    return rows


def make_background(path, title=None):
    img = Image.new("RGB", (WIDTH, HEIGHT), (8, 11, 20))
    px = img.load()
    for y in range(HEIGHT):
        dy = y / (HEIGHT - 1)
        for x in range(WIDTH):
            dx = x / (WIDTH - 1)
            px[x, y] = (18 + int(38 * dx), 15 + int(22 * dy), 30 + int(44 * dy))

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(-WIDTH, WIDTH, 96):
        draw.line((i, 0, i + WIDTH, HEIGHT), fill=(255, 255, 255, 12), width=2)
    for y in (445, 620):
        draw.rectangle((0, y, WIDTH, y + 2), fill=(255, 224, 148, 36))
    draw.rectangle((0, 0, WIDTH, HEIGHT), outline=(255, 255, 255, 26), width=16)

    if title:
        draw.text((WIDTH / 2, 118), title, fill=(255, 230, 150, 180), anchor="mm")

    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    vignette = Image.new("L", (WIDTH, HEIGHT), 0)
    vdraw = ImageDraw.Draw(vignette)
    vdraw.ellipse((-260, -260, WIDTH + 260, HEIGHT + 260), fill=220)
    vignette = vignette.filter(ImageFilter.GaussianBlur(120))
    dark = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 135))
    img = Image.composite(img, Image.alpha_composite(img, dark), Image.eval(vignette, lambda p: 255 - p))
    img.convert("RGB").save(path, quality=95)


def style_header():
    return f"""[Script Info]
Title: Karaoke
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {WIDTH}
PlayResY: {HEIGHT}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Current,Segoe UI Semibold,64,&H0000D7FF,&H00F7F8FF,&H00100804,&H80000000,0,0,0,0,100,100,0,0,1,4,1,5,60,60,40,1
Style: Dim,Segoe UI Semibold,42,&H00D5DAE8,&H00D5DAE8,&H00100804,&H80000000,0,0,0,0,100,100,0,0,1,3,1,5,80,80,40,1
Style: Far,Segoe UI Semibold,34,&H0099A1B5,&H0099A1B5,&H00100804,&H80000000,0,0,0,0,100,100,0,0,1,2,1,5,80,80,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def karaoke_text(text, start, end):
    words = text.split()
    if not words:
        return ""
    total_cs = max(1, int(round((end - start) * 100)))
    weights = [max(1, len(re.sub(r"[^A-Za-z0-9]", "", word))) for word in words]
    weight_sum = max(1, sum(weights))
    chunks = []
    used = 0
    for i, (word, weight) in enumerate(zip(words, weights)):
        if i == len(words) - 1:
            dur = max(1, total_cs - used)
        else:
            dur = max(1, round(total_cs * weight / weight_sum))
            used += dur
        chunks.append(f"{{\\kf{dur}}}{escape_ass(word)}" + (" " if i < len(words) - 1 else ""))
    return "".join(chunks)


def event(layer, start, end, style, text, y, fade=80):
    tag = f"{{\\an5\\pos(960,{y})\\fad({fade},{fade})}}"
    return f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style},,0,0,0,,{tag}{text}\n"


def build_ass(rows, path):
    out = [style_header()]
    y_map = {-2: 325, -1: 430, 0: 540, 1: 665, 2: 760}
    for i, row in enumerate(rows):
        start, end, text = row["start"], row["end"], row["text"]
        window_end = end
        for rel in (-2, -1, 1, 2):
            j = i + rel
            if 0 <= j < len(rows):
                style = "Dim" if abs(rel) == 1 else "Far"
                out.append(event(0, start, window_end, style, escape_ass(rows[j]["text"]), y_map[rel]))
        out.append(event(2, start, end, "Current", karaoke_text(text, start, end), y_map[0]))
    Path(path).write_text("".join(out), encoding="utf-8-sig")


def render(ffmpeg, audio, background, ass_file, output, duration):
    subtitle_path = str(Path(ass_file).resolve()).replace("\\", "/").replace(":", r"\:")
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loop",
        "1",
        "-framerate",
        "30",
        "-t",
        f"{duration:.2f}",
        "-i",
        str(background),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-vf",
        f"ass='{subtitle_path}'",
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
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(description="Render a 1080p karaoke MP4 from audio, lyrics, and optional timings.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--lyrics", required=True, help="Plain lyrics text file.")
    parser.add_argument("--timings", help="CSV or LRC timing file.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--duration", type=float, default=None)
    parser.add_argument("--draft-start", type=float, default=5.0)
    parser.add_argument("--draft-end", type=float, default=None)
    args = parser.parse_args()

    audio = Path(args.audio)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg(args.ffmpeg)
    duration = args.duration if args.duration else ffmpeg_duration(ffmpeg, audio)
    if args.timings:
        rows = complete_ends(load_timings(args.timings), duration)
    else:
        print("WARNING: No timings supplied. Creating a rough evenly spaced draft.", file=sys.stderr)
        rows = draft_timings(lyric_lines(args.lyrics), duration, args.draft_start, args.draft_end)

    background = output.with_suffix(".background.png")
    ass_file = output.with_suffix(".ass")
    make_background(background, args.title)
    build_ass(rows, ass_file)
    render(ffmpeg, audio, background, ass_file, output, duration)
    print(output.resolve())
    print(ass_file.resolve())


if __name__ == "__main__":
    main()
