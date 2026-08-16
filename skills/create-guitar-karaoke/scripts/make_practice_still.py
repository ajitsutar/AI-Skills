#!/usr/bin/env python3
"""Create a 1920x1080 title still from an authorized background image."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

WIDTH = 1920
HEIGHT = 1080


def load_pillow() -> None:
    global Image, ImageColor, ImageDraw, ImageFont, ImageOps
    try:
        from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps
    except ImportError as exc:
        raise SystemExit("Pillow is required: python -m pip install pillow") from exc


def font_candidates(bold: bool) -> list[Path]:
    names = (
        ["georgiab.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["georgia.ttf", "arial.ttf", "DejaVuSans.ttf"]
    )
    roots = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"),
        Path.home() / "Library/Fonts",
    ]
    return [root / name for root in roots for name in names]


def load_font(explicit: Path | None, size: int, *, bold: bool):
    if explicit:
        return ImageFont.truetype(str(explicit.expanduser()), size)
    for candidate in font_candidates(bold):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError as exc:
        raise SystemExit(
            "No scalable font was found. Supply --font and --bold-font with TrueType files."
        ) from exc


def cover(image: Image.Image) -> Image.Image:
    target_ratio = WIDTH / HEIGHT
    source_ratio = image.width / image.height
    if source_ratio > target_ratio:
        crop_width = round(image.height * target_ratio)
        left = (image.width - crop_width) // 2
        image = image.crop((left, 0, left + crop_width, image.height))
    else:
        crop_height = round(image.width / target_ratio)
        top = (image.height - crop_height) // 2
        image = image.crop((0, top, image.width, top + crop_height))
    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def fit_font(draw: ImageDraw.ImageDraw, text: str, explicit: Path | None, size: int, bold: bool):
    while size >= 28:
        font = load_font(explicit, size, bold=bold)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=2)
        if box[2] - box[0] <= WIDTH * 0.88:
            return font
        size -= 4
    return load_font(explicit, 28, bold=bold)


def centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    y: int,
    fill: tuple[int, int, int, int],
    stroke_width: int,
) -> None:
    box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_width)
    x = (WIDTH - (box[2] - box[0])) // 2
    draw.text(
        (x + 3, y + 5),
        text,
        font=font,
        fill=(0, 0, 0, 155),
        stroke_width=stroke_width + 1,
        stroke_fill=(0, 0, 0, 130),
    )
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=(5, 8, 12, 225),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--title", required=True)
    parser.add_argument("--subtitle", default="GUITAR KARAOKE")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--font", type=Path, help="Optional regular font file")
    parser.add_argument("--bold-font", type=Path, help="Optional title font file")
    parser.add_argument("--accent", default="#8B1924")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source = args.image.expanduser().resolve()
    output = args.output.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Background image does not exist: {source}")
    if output == source:
        raise SystemExit("Refusing to overwrite the background image with the output.")
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists: {output}. Use --overwrite to replace it.")
    if output.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise SystemExit("--output must end in .png, .jpg, or .jpeg")
    load_pillow()
    image = cover(ImageOps.exif_transpose(Image.open(source)).convert("RGB")).convert("RGBA")

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    gradient_height = 470
    for y in range(gradient_height):
        alpha = round(160 * (1 - y / gradient_height) ** 1.7)
        overlay_draw.line((0, y, WIDTH, y), fill=(3, 7, 14, alpha))
    image = Image.alpha_composite(image, overlay)

    draw = ImageDraw.Draw(image)
    title = args.title.strip().upper()
    subtitle = args.subtitle.strip().upper()
    title_font = fit_font(draw, title, args.bold_font or args.font, 104, True)
    subtitle_font = fit_font(draw, subtitle, args.font, 46, False)
    centered_text(draw, title, title_font, 88, (244, 240, 228, 255), 2)
    centered_text(draw, subtitle, subtitle_font, 226, (210, 214, 220, 255), 1)

    accent = ImageColor.getrgb(args.accent)
    draw.rounded_rectangle((690, 306, 1230, 313), radius=3, fill=(*accent, 235))

    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.stem}.", suffix=output.suffix, dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        image.convert("RGB").save(temporary, quality=96)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
