#!/usr/bin/env python3
"""Build guitar-muted practice audio and an optional still-image video.

The default path separates an aggregate guitar stem with BS-Roformer-SW.
An aligned external lead, rhythm, or custom stem can be supplied instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


MODEL_FILENAME = "BS-Roformer-SW.ckpt"
MODEL_LABEL = "BS-Roformer-SW"
EXPECTED_MODEL_SHA256 = "24e7d35ee9c64415673d3fd33e06a67cac2c103c5df6267ba1576459c775916e"
MODEL_CONFIG_FILENAME = "BS-Roformer-SW.yaml"
EXPECTED_CONFIG_SHA256 = "b558996f1e25eb48798bd6502505a5de94c4f966d6edfb1a0420f06cc40b501a"
SEPARATOR_VERSION = "0.44.5"
TARGET_SAMPLE_RATE = 44_100
MIN_MODEL_CLIP_SECONDS = 11.0
TOOL_VERSION = "1.0.1"
MANIFEST_SCHEMA_VERSION = 2
REPORT_SCHEMA_VERSION = 1
ATTESTATION_SCHEMA_VERSION = 1
SEPARATOR_SETTINGS = {
    "model_filename": MODEL_FILENAME,
    "output_format": "WAV",
    "sample_rate": TARGET_SAMPLE_RATE,
    "normalization": 1.0,
    "amplification": 0.0,
    "use_soundfile": True,
    "mdxc_overlap": 8,
    "mdxc_batch_size": 1,
    "mdxc_pitch_shift": 0,
}


def audio_modules():
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise SystemExit(
            "Missing audio libraries. Install the skill's pinned requirements.txt in an "
            "isolated environment."
        ) from exc
    return np, sf


def display_command(command: Iterable[str]) -> str:
    return shlex.join(str(part) for part in command)


def run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    print(f"+ {display_command(command)}", flush=True)
    subprocess.run(command, check=True, env=env)


def temporary_sibling(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{destination.stem}.", suffix=destination.suffix, dir=destination.parent
    )
    os.close(descriptor)
    return Path(name)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def require_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in value)
    ):
        raise SystemExit(f"{label} must be a complete SHA-256 digest. Rerun --stage prepare.")
    return value.lower()


def program_version(command: list[str]) -> str:
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    output = (completed.stdout or completed.stderr).strip()
    return output.splitlines()[0] if output else "unknown"


def available_memory_bytes() -> int | None:
    try:
        if os.name == "nt":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available_physical)
            return None
        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages * page_size)
    except (AttributeError, OSError, ValueError):
        return None


def is_within(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def validate_paths(args: argparse.Namespace, *, will_mix: bool) -> None:
    source = args.input.expanduser().resolve()
    work_dir = args.work_dir.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Input audio does not exist: {source}")
    if work_dir.exists() and not work_dir.is_dir():
        raise SystemExit(f"--work-dir is not a directory: {work_dir}")
    if args.image and not args.image.expanduser().resolve().is_file():
        raise SystemExit(f"Still image does not exist: {args.image.expanduser().resolve()}")
    model_dir = (args.model_dir or work_dir / "models").expanduser().resolve()
    generated_dirs = [work_dir / "clips", work_dir / "stems", model_dir]
    internal_files = {
        work_dir / "master.wav",
        work_dir / "external-stem.wav",
        work_dir / "manifest.json",
        work_dir / "edited-float-master.wav",
    }
    protected = {source}
    if args.stem_file:
        protected.add(args.stem_file.expanduser().resolve())
    if args.image:
        protected.add(args.image.expanduser().resolve())

    for path in protected:
        if path in internal_files or any(is_within(path, directory) for directory in generated_dirs):
            raise SystemExit(
                f"Input path is inside a generated work location and could be overwritten: {path}"
            )
    if not will_mix:
        return
    assert args.output is not None
    destinations: dict[str, Path] = {
        "output": args.output.expanduser().resolve(),
        "report": (args.report or work_dir / "report.json").expanduser().resolve(),
    }
    if args.video_output:
        destinations["video output"] = args.video_output.expanduser().resolve()
    if len(set(destinations.values())) != len(destinations):
        raise SystemExit("Output, report, and video paths must be different files.")
    if destinations["output"].suffix.lower() not in (".mp3", ".wav"):
        raise SystemExit("--output must end in .mp3 or .wav")
    if destinations["report"].suffix.lower() != ".json":
        raise SystemExit("--report must end in .json")
    for label, path in destinations.items():
        if path in protected:
            raise SystemExit(f"Refusing to overwrite an input with {label}: {path}")
        if path in internal_files or any(
            is_within(path, directory) for directory in generated_dirs
        ):
            raise SystemExit(f"{label.capitalize()} collides with generated work state: {path}")
        if path.exists() and not args.overwrite:
            raise SystemExit(f"{label.capitalize()} already exists: {path}. Use --overwrite to replace it.")


def resolve_program(explicit: str | None, name: str, env_name: str | None = None) -> str:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)
    if env_name and os.environ.get(env_name):
        candidates.append(os.environ[env_name])
    discovered = shutil.which(name)
    if discovered:
        candidates.append(discovered)
    if os.name == "nt" and not name.lower().endswith(".exe"):
        discovered_exe = shutil.which(f"{name}.exe")
        if discovered_exe:
            candidates.append(discovered_exe)

    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path.resolve())
        found = shutil.which(candidate)
        if found:
            return found
    hint = f" Pass --{name.replace('_', '-')} PATH." if explicit is None else ""
    raise SystemExit(f"Could not find {name}.{hint}")


def resolve_separator(explicit: str | None) -> str:
    if explicit:
        return resolve_program(explicit, "audio-separator")
    found = shutil.which("audio-separator")
    if found:
        return found
    suffix = ".exe" if os.name == "nt" else ""
    adjacent = Path(sys.executable).resolve().parent / f"audio-separator{suffix}"
    if adjacent.is_file():
        return str(adjacent)
    raise SystemExit(
        "Could not find audio-separator in the active environment. Install the skill's "
        "pinned scripts/requirements.txt first."
    )


def parse_timestamp(value: str, *, allow_end: bool = False) -> float | None:
    text = value.strip().lower()
    if allow_end and text == "end":
        return None
    if not text:
        raise ValueError("empty timestamp")
    parts = text.split(":")
    if len(parts) > 3:
        raise ValueError(f"invalid timestamp: {value}")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {value}") from exc
    if any(number < 0 for number in numbers):
        raise ValueError(f"timestamp cannot be negative: {value}")
    if len(numbers) == 1:
        return numbers[0]
    if len(numbers) == 2:
        return numbers[0] * 60 + numbers[1]
    return numbers[0] * 3600 + numbers[1] * 60 + numbers[2]


def format_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"
    return f"{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def parse_windows(raw_windows: list[str], frames: int, sample_rate: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    duration = frames / sample_rate
    for raw in raw_windows:
        start_text, separator, end_text = raw.partition("-")
        if not separator:
            raise SystemExit(
                f"Invalid window {raw!r}. Use START-END, for example 03:56.2-04:46.8."
            )
        try:
            start_seconds = parse_timestamp(start_text)
            end_seconds = parse_timestamp(end_text, allow_end=True)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        assert start_seconds is not None
        if end_seconds is None:
            end_seconds = duration
        if start_seconds >= end_seconds:
            raise SystemExit(f"Window start must precede end: {raw}")
        if start_seconds >= duration or end_seconds <= 0:
            raise SystemExit(f"Window falls outside the {duration:.3f}-second source: {raw}")
        start_frame = max(0, min(frames, round(start_seconds * sample_rate)))
        end_frame = max(0, min(frames, round(end_seconds * sample_rate)))
        if start_frame < end_frame:
            windows.append((start_frame, end_frame))

    windows.sort()
    merged: list[list[int]] = []
    for start, end in windows:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def complement(windows: list[tuple[int, int]], frames: int) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    cursor = 0
    for start, end in windows:
        if cursor < start:
            result.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < frames:
        result.append((cursor, frames))
    return result


def processing_spans(
    scope: str, windows: list[tuple[int, int]], frames: int
) -> list[tuple[int, int]]:
    if scope == "whole":
        return [(0, frames)]
    if not windows:
        raise SystemExit(f"--scope {scope} requires at least one --window START-END.")
    if scope == "windows":
        return windows
    spans = complement(windows, frames)
    if not spans:
        raise SystemExit("The supplied windows cover the whole song; outside-windows is empty.")
    return spans


def decode_audio(ffmpeg: str, source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg,
            "-nostdin",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "2",
            "-ar",
            str(TARGET_SAMPLE_RATE),
            "-c:a",
            "pcm_f32le",
            str(destination),
        ]
    )


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    temporary = temporary_sibling(path)
    try:
        temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def prepare(args: argparse.Namespace, ffmpeg: str) -> dict[str, Any]:
    np, sf = audio_modules()
    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Input audio does not exist: {source}")

    work_dir = args.work_dir.expanduser().resolve()
    clips_dir = work_dir / "clips"
    stems_dir = work_dir / "stems"
    models_dir = (args.model_dir or work_dir / "models").expanduser().resolve()
    for directory in (work_dir, clips_dir, stems_dir, models_dir):
        directory.mkdir(parents=True, exist_ok=True)

    master_path = work_dir / "master.wav"
    decode_audio(ffmpeg, source, master_path)
    master, sample_rate = sf.read(master_path, dtype="float32", always_2d=True)
    if sample_rate != TARGET_SAMPLE_RATE or master.shape[1] != 2:
        raise SystemExit(f"Unexpected decoded master format: {master.shape}@{sample_rate}")
    frames = len(master)
    windows = parse_windows(args.window, frames, sample_rate)
    spans = processing_spans(args.scope, windows, frames)

    source_peak = float(np.max(np.abs(master))) if frames else 0.0
    preparation_scale = min(1.0, args.prepare_peak / max(source_peak, 1e-12))
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "source": str(source),
        "source_sha256": hash_file(source),
        "work_dir": str(work_dir),
        "master_wav": str(master_path),
        "master_wav_sha256": hash_file(master_path),
        "sample_rate": sample_rate,
        "frames": frames,
        "duration_seconds": frames / sample_rate,
        "source_peak": source_peak,
        "preparation_scale": preparation_scale,
        "preparation_peak_target": args.prepare_peak,
        "scope": args.scope,
        "stem_kind": args.stem_kind,
        "stem_source": "external" if args.stem_file else MODEL_LABEL,
        "fade_seconds": args.fade,
        "context_seconds": args.context,
        "chunk_seconds": args.chunk_seconds,
        "windows": [
            {
                "start_frame": start,
                "end_frame": end,
                "start": format_timestamp(start / sample_rate),
                "end": format_timestamp(end / sample_rate),
            }
            for start, end in windows
        ],
        "processing_spans": [
            {"start_frame": start, "end_frame": end} for start, end in spans
        ],
        "models_dir": str(models_dir),
        "stems_dir": str(stems_dir),
        "tiles": [],
        "python_version": sys.version.split()[0],
        "ffmpeg_version": program_version([ffmpeg, "-version"]),
    }

    if args.stem_file:
        stem_source = args.stem_file.expanduser().resolve()
        if not stem_source.is_file():
            raise SystemExit(f"External stem does not exist: {stem_source}")
        external_path = work_dir / "external-stem.wav"
        decode_audio(ffmpeg, stem_source, external_path)
        manifest["external_stem_source"] = str(stem_source)
        manifest["external_stem_source_sha256"] = hash_file(stem_source)
        manifest["external_stem_wav"] = str(external_path)
        manifest["external_stem_wav_sha256"] = hash_file(external_path)
        manifest["external_stem_offset_seconds"] = args.stem_offset
        manifest["external_stem_gain"] = args.stem_gain
    else:
        context_frames = round(args.context * sample_rate)
        chunk_frames = max(1, round(args.chunk_seconds * sample_rate))
        minimum_frames = math.ceil(MIN_MODEL_CLIP_SECONDS * sample_rate)
        tile_number = 0
        for span_start, span_end in spans:
            core_start = span_start
            while core_start < span_end:
                core_end = min(span_end, core_start + chunk_frames)
                clip_start = max(0, core_start - context_frames)
                clip_end = min(frames, core_end + context_frames)
                clip_audio = master[clip_start:clip_end]
                source_frames = len(clip_audio)
                peak = float(np.max(np.abs(clip_audio))) if source_frames else 0.0
                scale = preparation_scale
                scaled = clip_audio * np.float32(scale)
                if len(scaled) < minimum_frames:
                    padding = np.zeros((minimum_frames - len(scaled), 2), dtype="float32")
                    scaled = np.concatenate((scaled, padding), axis=0)

                tile_number += 1
                fingerprint = hashlib.sha256()
                fingerprint.update(scaled.tobytes(order="C"))
                fingerprint.update(
                    f"{clip_start}:{source_frames}:{core_start}:{core_end}:{sample_rate}".encode()
                )
                clip_path = clips_dir / (
                    f"tile_{tile_number:03d}_{fingerprint.hexdigest()[:12]}.wav"
                )
                sf.write(clip_path, scaled, sample_rate, subtype="FLOAT")
                manifest["tiles"].append(
                    {
                        "number": tile_number,
                        "clip_wav": str(clip_path),
                        "clip_start_frame": clip_start,
                        "clip_source_frames": source_frames,
                        "clip_written_frames": len(scaled),
                        "core_start_frame": core_start,
                        "core_end_frame": core_end,
                        "input_scale": scale,
                        "source_peak": peak,
                        "tile_fingerprint": fingerprint.hexdigest(),
                        "clip_sha256": hash_file(clip_path),
                    }
                )
                core_start = core_end

    manifest_path = work_dir / "manifest.json"
    write_manifest(manifest_path, manifest)
    total_seconds = sum((end - start) / sample_rate for start, end in spans)
    print(
        f"Prepared {len(manifest['tiles'])} model tile(s) for {total_seconds:.2f}s of "
        f"active material; manifest: {manifest_path}"
    )
    return manifest


def load_manifest(work_dir: Path) -> dict[str, Any]:
    resolved_work_dir = work_dir.expanduser().resolve()
    path = resolved_work_dir / "manifest.json"
    if not path.is_file():
        raise SystemExit(f"Manifest not found: {path}. Run --stage prepare first.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Manifest is unreadable or invalid JSON: {path}") from exc
    if not isinstance(manifest, dict):
        raise SystemExit(f"Manifest must contain a JSON object: {path}")
    schema = manifest.get("schema_version")
    if schema != MANIFEST_SCHEMA_VERSION:
        raise SystemExit(
            f"Unsupported manifest schema {schema!r}; expected {MANIFEST_SCHEMA_VERSION}. "
            "Rerun --stage prepare with this version of the skill."
        )
    required = {
        "source",
        "source_sha256",
        "work_dir",
        "master_wav",
        "master_wav_sha256",
        "sample_rate",
        "frames",
        "scope",
        "stem_kind",
        "stem_source",
        "fade_seconds",
        "models_dir",
        "stems_dir",
        "tiles",
        "windows",
    }
    missing = sorted(required.difference(manifest))
    if missing:
        raise SystemExit(
            "Manifest is missing required fields: " + ", ".join(missing) + ". Rerun prepare."
        )

    manifest["source_sha256"] = require_sha256(
        manifest["source_sha256"], "Manifest source_sha256"
    )
    manifest["master_wav_sha256"] = require_sha256(
        manifest["master_wav_sha256"], "Manifest master_wav_sha256"
    )
    try:
        recorded_work_dir = Path(manifest["work_dir"]).expanduser().resolve()
        master_path = Path(manifest["master_wav"]).expanduser().resolve()
        stems_dir = Path(manifest["stems_dir"]).expanduser().resolve()
    except (TypeError, ValueError, OSError) as exc:
        raise SystemExit("Manifest contains an invalid generated path. Rerun prepare.") from exc
    if recorded_work_dir != resolved_work_dir:
        raise SystemExit(
            "Manifest work_dir does not match the directory from which it was loaded. "
            "Rerun prepare in this work directory."
        )
    if master_path != resolved_work_dir / "master.wav":
        raise SystemExit("Manifest master_wav is outside the expected work state. Rerun prepare.")
    if stems_dir != resolved_work_dir / "stems":
        raise SystemExit("Manifest stems_dir is outside the expected work state. Rerun prepare.")

    tiles = manifest["tiles"]
    if not isinstance(tiles, list):
        raise SystemExit("Manifest tiles must be a list. Rerun prepare.")
    if manifest["stem_source"] == "external":
        external_required = {
            "external_stem_source",
            "external_stem_source_sha256",
            "external_stem_wav",
            "external_stem_wav_sha256",
            "external_stem_offset_seconds",
            "external_stem_gain",
        }
        external_missing = sorted(external_required.difference(manifest))
        if external_missing:
            raise SystemExit(
                "External-stem manifest fields are missing: "
                + ", ".join(external_missing)
                + ". Rerun prepare."
            )
        manifest["external_stem_source_sha256"] = require_sha256(
            manifest["external_stem_source_sha256"], "Manifest external_stem_source_sha256"
        )
        manifest["external_stem_wav_sha256"] = require_sha256(
            manifest["external_stem_wav_sha256"], "Manifest external_stem_wav_sha256"
        )
        try:
            Path(manifest["external_stem_source"]).expanduser().resolve()
            external_wav = Path(manifest["external_stem_wav"]).expanduser().resolve()
        except (TypeError, ValueError, OSError) as exc:
            raise SystemExit("Manifest external-stem path is invalid. Rerun prepare.") from exc
        if external_wav != resolved_work_dir / "external-stem.wav":
            raise SystemExit(
                "Manifest external_stem_wav is outside the expected work state. Rerun prepare."
            )
        if tiles:
            raise SystemExit("An external-stem manifest must not contain model tiles. Rerun prepare.")
    elif manifest["stem_source"] == MODEL_LABEL:
        if not tiles:
            raise SystemExit("Model manifest contains no prepared tiles. Rerun prepare.")
        clips_dir = resolved_work_dir / "clips"
        tile_required = {
            "clip_wav",
            "clip_start_frame",
            "clip_source_frames",
            "clip_written_frames",
            "core_start_frame",
            "core_end_frame",
            "input_scale",
            "clip_sha256",
        }
        for index, tile in enumerate(tiles, start=1):
            if not isinstance(tile, dict):
                raise SystemExit(f"Manifest tile {index} must be an object. Rerun prepare.")
            tile_missing = sorted(tile_required.difference(tile))
            if tile_missing:
                raise SystemExit(
                    f"Manifest tile {index} is missing fields: "
                    + ", ".join(tile_missing)
                    + ". Rerun prepare."
                )
            tile["clip_sha256"] = require_sha256(
                tile["clip_sha256"], f"Manifest tile {index} clip_sha256"
            )
            try:
                clip_path = Path(tile["clip_wav"]).expanduser().resolve()
            except (TypeError, ValueError, OSError) as exc:
                raise SystemExit(f"Manifest tile {index} has an invalid clip path.") from exc
            if not is_within(clip_path, clips_dir):
                raise SystemExit(
                    f"Manifest tile {index} points outside the expected clips directory. "
                    "Rerun prepare."
                )
    else:
        raise SystemExit(
            f"Unsupported manifest stem_source {manifest['stem_source']!r}. Rerun prepare."
        )
    return manifest


def expected_guitar_stem(manifest: dict[str, Any], tile: dict[str, Any]) -> Path:
    stems_dir = Path(manifest["stems_dir"])
    clip_stem = Path(tile["clip_wav"]).stem
    return stems_dir / f"{clip_stem}_(guitar)_{MODEL_LABEL}.wav"


def separator_version(separator: str) -> str:
    completed = subprocess.run(
        [separator, "--version"], check=True, capture_output=True, text=True
    )
    output = (completed.stdout or completed.stderr).strip()
    version = output.rsplit(" ", 1)[-1]
    if version != SEPARATOR_VERSION:
        raise SystemExit(
            f"audio-separator {SEPARATOR_VERSION} is required by this workflow; found {output!r}."
        )
    return version


def attestation_path(stem_path: Path) -> Path:
    return stem_path.with_suffix(stem_path.suffix + ".attestation.json")


def validated_clip_hash(tile: dict[str, Any]) -> str:
    clip_path = Path(tile["clip_wav"])
    if not clip_path.is_file():
        raise SystemExit(f"Prepared model clip is missing: {clip_path}. Rerun --stage prepare.")
    current = hash_file(clip_path)
    recorded = tile.get("clip_sha256")
    if not recorded:
        raise SystemExit("Prepared model clip has no recorded SHA-256. Rerun --stage prepare.")
    if current != recorded:
        raise SystemExit(
            f"Prepared model clip no longer matches its SHA-256: {clip_path}. "
            "Rerun --stage prepare."
        )
    return current


def attestation_core(
    tile: dict[str, Any], checkpoint_hash: str, config_hash: str, version: str
) -> dict[str, Any]:
    return {
        "attestation_schema_version": ATTESTATION_SCHEMA_VERSION,
        "clip_sha256": validated_clip_hash(tile),
        "model_checkpoint_sha256": checkpoint_hash,
        "model_config_sha256": config_hash,
        "audio_separator_version": version,
        "settings": dict(SEPARATOR_SETTINGS),
    }


def cache_is_valid(
    tile: dict[str, Any], stem_path: Path, checkpoint_hash: str, config_hash: str, version: str
) -> bool:
    sidecar = attestation_path(stem_path)
    if not stem_path.is_file() or not sidecar.is_file():
        return False
    try:
        recorded = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    expected = attestation_core(tile, checkpoint_hash, config_hash, version)
    if any(recorded.get(key) != value for key, value in expected.items()):
        return False
    return recorded.get("stem_sha256") == hash_file(stem_path)


def verify_manifest_model_assets(manifest: dict[str, Any]) -> tuple[str, str, str]:
    models_dir = Path(manifest["models_dir"])
    checkpoint = models_dir / MODEL_FILENAME
    config = models_dir / MODEL_CONFIG_FILENAME
    if not checkpoint.is_file() or not config.is_file():
        raise SystemExit(
            "The attested model checkpoint/config are missing. Run --stage separate first."
        )
    checkpoint_hash = hash_file(checkpoint)
    config_hash = hash_file(config)
    if checkpoint_hash.lower() != EXPECTED_MODEL_SHA256:
        raise SystemExit(
            f"Unexpected {MODEL_FILENAME} SHA-256: {checkpoint_hash}. Refusing to mix."
        )
    if config_hash.lower() != EXPECTED_CONFIG_SHA256:
        raise SystemExit(
            f"Unexpected {MODEL_CONFIG_FILENAME} SHA-256: {config_hash}. Refusing to mix."
        )
    recorded_checkpoint = manifest.get("model_checkpoint_sha256")
    recorded_config = manifest.get("model_config_sha256")
    version = manifest.get("audio_separator_version")
    if recorded_checkpoint != checkpoint_hash or recorded_config != config_hash:
        raise SystemExit(
            "Manifest model hashes are missing or do not match the current model files. "
            "Run --stage separate first."
        )
    if version != SEPARATOR_VERSION:
        raise SystemExit(
            f"Manifest requires attested audio-separator {SEPARATOR_VERSION}; found {version!r}. "
            "Run --stage separate first."
        )
    return checkpoint_hash, config_hash, version


def clear_invalid_model_cache(manifest: dict[str, Any], tiles: list[dict[str, Any]]) -> None:
    stems_dir = Path(manifest["stems_dir"]).resolve()
    for tile in tiles:
        stem_path = expected_guitar_stem(manifest, tile)
        for path in (stem_path, attestation_path(stem_path)):
            resolved = path.resolve()
            if not is_within(resolved, stems_dir):
                raise SystemExit(f"Refusing to clear a cache path outside stems_dir: {resolved}")
            path.unlink(missing_ok=True)


def validate_model_stem_file(stem_path: Path, tile: dict[str, Any]) -> None:
    _, sf = audio_modules()
    try:
        info = sf.info(stem_path)
    except (OSError, RuntimeError) as exc:
        raise SystemExit(f"Generated model stem is unreadable: {stem_path}") from exc
    expected_frames = int(tile["clip_written_frames"])
    if (
        info.samplerate != TARGET_SAMPLE_RATE
        or info.channels != 2
        or info.frames != expected_frames
    ):
        raise SystemExit(
            f"Unexpected generated model stem format: {stem_path} is "
            f"{info.frames} frames, {info.channels} channel(s) at {info.samplerate} Hz; "
            f"expected {expected_frames} frames, 2 channels at {TARGET_SAMPLE_RATE} Hz."
        )


def separate(args: argparse.Namespace, manifest: dict[str, Any], ffmpeg: str) -> None:
    if manifest["stem_source"] == "external":
        print("External stem supplied; model separation is not needed.")
        return
    separator = resolve_separator(args.audio_separator)
    version = separator_version(separator)
    print(f"Verified audio-separator {version}.")
    stems_dir = Path(manifest["stems_dir"])
    models_dir = Path(manifest["models_dir"])
    checkpoint = models_dir / MODEL_FILENAME
    config = models_dir / MODEL_CONFIG_FILENAME
    environment = os.environ.copy()
    ffmpeg_dir = str(Path(ffmpeg).resolve().parent)
    environment["PATH"] = ffmpeg_dir + os.pathsep + environment.get("PATH", "")
    if not checkpoint.is_file() or not config.is_file():
        estimated_model_bytes = 705_000_000
        free_bytes = shutil.disk_usage(models_dir).free
        if free_bytes < math.ceil(estimated_model_bytes * 1.15):
            raise SystemExit("Insufficient free disk space for the model checkpoint.")
        run(
            [
                separator,
                "--model_filename",
                MODEL_FILENAME,
                "--model_file_dir",
                str(models_dir),
                "--download_model_only",
            ],
            env=environment,
        )
    if not checkpoint.is_file() or not config.is_file():
        raise SystemExit("Separator did not create the expected checkpoint and config files.")
    checkpoint_hash = hash_file(checkpoint)
    config_hash = hash_file(config)
    if checkpoint_hash.lower() != EXPECTED_MODEL_SHA256:
        raise SystemExit(
            f"Unexpected {MODEL_FILENAME} SHA-256: {checkpoint_hash}. Refusing inference."
        )
    if config_hash.lower() != EXPECTED_CONFIG_SHA256:
        raise SystemExit(
            f"Unexpected {MODEL_CONFIG_FILENAME} SHA-256: {config_hash}. Refusing inference."
        )

    tiles = manifest["tiles"]
    for tile in tiles:
        validated_clip_hash(tile)
    missing = [
        tile
        for tile in tiles
        if args.force_separate
        or not cache_is_valid(
            tile,
            expected_guitar_stem(manifest, tile),
            checkpoint_hash,
            config_hash,
            version,
        )
    ]
    manifest["model_checkpoint_sha256"] = checkpoint_hash
    manifest["model_config_sha256"] = config_hash
    manifest["audio_separator_version"] = version
    write_manifest(Path(manifest["work_dir"]) / "manifest.json", manifest)
    if not missing:
        print("All attested guitar stems match the input, model, config, and settings.")
        return

    estimated_stem_bytes = sum(
        int(tile["clip_written_frames"]) * 2 * 4 * 6 for tile in missing
    )
    required_free = math.ceil(estimated_stem_bytes * 1.15)
    free_bytes = shutil.disk_usage(stems_dir).free
    if free_bytes < required_free:
        raise SystemExit(
            f"Insufficient free disk space for separation: need about "
            f"{required_free / 2**30:.2f} GiB, have {free_bytes / 2**30:.2f} GiB."
        )
    # An invalid or force-refreshed output must not survive a separator run and then be
    # re-attested merely because the backend did not overwrite a near-silent stem.
    clear_invalid_model_cache(manifest, missing)
    command = [separator, *[tile["clip_wav"] for tile in missing]]
    command.extend(
        [
            "--model_filename",
            str(SEPARATOR_SETTINGS["model_filename"]),
            "--model_file_dir",
            str(models_dir),
            "--output_dir",
            str(stems_dir),
            "--output_format",
            str(SEPARATOR_SETTINGS["output_format"]),
            "--sample_rate",
            str(SEPARATOR_SETTINGS["sample_rate"]),
            "--normalization",
            str(SEPARATOR_SETTINGS["normalization"]),
            "--amplification",
            str(SEPARATOR_SETTINGS["amplification"]),
            "--mdxc_overlap",
            str(SEPARATOR_SETTINGS["mdxc_overlap"]),
            "--mdxc_batch_size",
            str(SEPARATOR_SETTINGS["mdxc_batch_size"]),
            "--mdxc_pitch_shift",
            str(SEPARATOR_SETTINGS["mdxc_pitch_shift"]),
        ]
    )
    if SEPARATOR_SETTINGS["use_soundfile"]:
        command.append("--use_soundfile")
    run(command, env=environment)

    absent = [expected_guitar_stem(manifest, tile) for tile in missing]
    absent = [path for path in absent if not path.is_file()]
    if absent:
        raise SystemExit(
            "Separator completed but expected guitar stems are missing:\n"
            + "\n".join(str(path) for path in absent)
        )
    for tile in missing:
        stem_path = expected_guitar_stem(manifest, tile)
        validate_model_stem_file(stem_path, tile)
        attestation = attestation_core(tile, checkpoint_hash, config_hash, version)
        attestation["stem_sha256"] = hash_file(stem_path)
        write_manifest(attestation_path(stem_path), attestation)


def cosine_fade_in(np, length: int):
    if length <= 0:
        return np.empty(0, dtype="float32")
    phase = np.arange(length, dtype="float32") / max(length, 1)
    return 0.5 - 0.5 * np.cos(np.pi * phase)


def cosine_fade_out(np, length: int):
    if length <= 0:
        return np.empty(0, dtype="float32")
    phase = np.arange(length, dtype="float32") / max(length, 1)
    return 0.5 + 0.5 * np.cos(np.pi * phase)


def make_window_mask(np, frames: int, windows: list[dict[str, Any]], fade_frames: int):
    mask = np.zeros(frames, dtype="float32")
    for window in windows:
        start = int(window["start_frame"])
        end = int(window["end_frame"])
        fade_start = max(0, start - fade_frames)
        fade_end = min(frames, end + fade_frames)
        if fade_start < start:
            mask[fade_start:start] = np.maximum(
                mask[fade_start:start], cosine_fade_in(np, start - fade_start)
            )
        mask[start:end] = 1.0
        if end < fade_end:
            mask[end:fade_end] = np.maximum(
                mask[end:fade_end], cosine_fade_out(np, fade_end - end)
            )
    return mask


def make_scope_envelope(np, manifest: dict[str, Any]):
    frames = int(manifest["frames"])
    if manifest["scope"] == "whole":
        return np.ones(frames, dtype="float32")
    fade_frames = round(float(manifest["fade_seconds"]) * int(manifest["sample_rate"]))
    mask = make_window_mask(np, frames, manifest["windows"], fade_frames)
    if manifest["scope"] == "windows":
        return mask
    return 1.0 - mask


def tile_blend_weights(np, tile: dict[str, Any], count: int):
    start = int(tile["clip_start_frame"])
    core_start = int(tile["core_start_frame"])
    core_end = int(tile["core_end_frame"])
    global_frames = start + np.arange(count)
    weights = np.ones(count, dtype="float32")
    left = global_frames < core_start
    if np.any(left):
        span = max(core_start - start, 1)
        phase = (global_frames[left] - start) / span
        weights[left] = 0.5 - 0.5 * np.cos(np.pi * phase)
    right = global_frames >= core_end
    if np.any(right):
        clip_source_end = start + int(tile["clip_source_frames"])
        span = max(clip_source_end - core_end, 1)
        phase = (global_frames[right] - core_end) / span
        weights[right] = 0.5 + 0.5 * np.cos(np.pi * phase)
    return weights


def load_estimate(manifest: dict[str, Any]):
    np, sf = audio_modules()
    frames = int(manifest["frames"])
    sample_rate = int(manifest["sample_rate"])
    if manifest["stem_source"] == "external":
        external_path = Path(manifest["external_stem_wav"])
        recorded_hash = require_sha256(
            manifest.get("external_stem_wav_sha256"), "External decoded stem SHA-256"
        )
        if not external_path.is_file():
            raise SystemExit("Decoded external stem or its SHA-256 is missing. Rerun prepare.")
        if hash_file(external_path) != recorded_hash:
            raise SystemExit("Decoded external stem no longer matches its preparation SHA-256.")
        source_path = Path(manifest["external_stem_source"])
        recorded_source_hash = require_sha256(
            manifest.get("external_stem_source_sha256"), "External source stem SHA-256"
        )
        if not source_path.is_file():
            raise SystemExit(
                "External stem source is missing; keep it available through the mix stage "
                "so its preparation SHA-256 can be verified."
            )
        if hash_file(source_path) != recorded_source_hash:
            raise SystemExit("External stem source no longer matches its preparation SHA-256.")
        stem, stem_rate = sf.read(
            external_path, dtype="float32", always_2d=True
        )
        if stem_rate != sample_rate or stem.shape[1] != 2:
            raise SystemExit(f"Unexpected external stem format: {stem.shape}@{stem_rate}")
        offset_seconds = float(manifest.get("external_stem_offset_seconds", 0.0))
        offset_frames = round(offset_seconds * sample_rate)
        if offset_frames == 0 and len(stem) != frames:
            raise SystemExit(
                "With zero --stem-offset, the external stem must have exactly the same "
                f"decoded frame count as the master ({len(stem)} != {frames})."
            )
        aligned = np.zeros((frames, 2), dtype="float32")
        source_start = max(0, -offset_frames)
        destination_start = max(0, offset_frames)
        count = min(len(stem) - source_start, frames - destination_start)
        if count <= 0:
            raise SystemExit("--stem-offset moves the entire external stem outside the master.")
        gain = float(manifest.get("external_stem_gain", 1.0))
        aligned[destination_start : destination_start + count] = (
            stem[source_start : source_start + count] * np.float32(gain)
        )
        return aligned

    checkpoint_hash, config_hash, version = verify_manifest_model_assets(manifest)
    for tile in manifest["tiles"]:
        stem_path = expected_guitar_stem(manifest, tile)
        if not cache_is_valid(tile, stem_path, checkpoint_hash, config_hash, version):
            raise SystemExit(
                f"Model stem attestation failed: {stem_path}. Run --stage separate first."
            )

    accumulator = np.zeros((frames, 2), dtype="float32")
    weight_sum = np.zeros(frames, dtype="float32")
    for tile in manifest["tiles"]:
        stem_path = expected_guitar_stem(manifest, tile)
        if not stem_path.is_file():
            raise SystemExit(f"Missing guitar stem: {stem_path}. Run --stage separate first.")
        stem, stem_rate = sf.read(stem_path, dtype="float32", always_2d=True)
        if stem_rate != sample_rate or stem.shape[1] != 2:
            raise SystemExit(f"Unexpected model stem format: {stem.shape}@{stem_rate}")
        expected_frames = int(tile["clip_written_frames"])
        if len(stem) != expected_frames:
            raise SystemExit(
                f"Model stem frame count no longer matches its prepared clip: "
                f"{len(stem)} != {expected_frames} for {stem_path}. Run --stage separate."
            )
        stem_peak = float(np.max(np.abs(stem))) if len(stem) else 0.0
        if stem_peak >= 0.999999:
            raise SystemExit(
                f"Model stem reached the separator normalization ceiling ({stem_peak:.6f}): "
                f"{stem_path}. Re-prepare with a lower value such as --prepare-peak 0.8 "
                "and re-separate before subtraction."
            )
        start = int(tile["clip_start_frame"])
        count = min(int(tile["clip_source_frames"]), len(stem), frames - start)
        if count <= 0:
            continue
        scale = float(tile["input_scale"])
        restored = stem[:count] / np.float32(scale)
        weights = tile_blend_weights(np, tile, count)
        accumulator[start : start + count] += restored * weights[:, None]
        weight_sum[start : start + count] += weights

    valid = weight_sum > 1e-6
    envelope = make_scope_envelope(np, manifest)
    if np.any((envelope > 1e-4) & ~valid):
        raise SystemExit("Model tiles do not cover the complete subtraction envelope.")
    accumulator[valid] /= weight_sum[valid, None]
    accumulator[~valid] = 0.0
    return accumulator


def rms_db(np, audio) -> float:
    if audio.size == 0:
        return -math.inf
    mean_square = float(np.mean(np.square(audio, dtype="float64")))
    return 10 * math.log10(max(mean_square, 1e-20))


def encode_mp3(
    ffmpeg: str,
    mix_wav: Path,
    destination: Path,
    bitrate: str,
    delivery_gain: float,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = temporary_sibling(destination)
    command = [
        ffmpeg,
        "-nostdin",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(mix_wav),
        "-map",
        "0:a:0",
        "-map_metadata",
        "-1",
        "-c:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        "-id3v2_version",
        "3",
    ]
    if delivery_gain < 1.0:
        command.extend(["-af", f"volume={delivery_gain:.12g}"])
    command.append(str(temporary))
    try:
        run(command)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def copy_safe_metadata(source: Path, destination: Path, title: str | None) -> dict[str, Any]:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return {"copied": False, "reason": "mutagen unavailable"}

    source_audio = MutagenFile(source, easy=True)
    destination_audio = MutagenFile(destination, easy=True)
    if source_audio is None or destination_audio is None:
        return {"copied": False, "reason": "unsupported source or destination tags"}
    if destination_audio.tags is None:
        destination_audio.add_tags()
    safe_keys = (
        "album",
        "albumartist",
        "artist",
        "composer",
        "copyright",
        "date",
        "discnumber",
        "genre",
        "title",
        "tracknumber",
    )
    copied: list[str] = []
    for key in safe_keys:
        values = source_audio.get(key)
        if values:
            destination_audio[key] = list(values)
            copied.append(key)
    if title:
        destination_audio["title"] = [title]
        if "title" not in copied:
            copied.append("title")
    destination_audio.save()
    return {"copied": True, "fields": sorted(copied)}


def media_info(path: Path) -> dict[str, Any]:
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return {}
    audio = MutagenFile(path, easy=True)
    if audio is None or not getattr(audio, "info", None):
        return {}
    result: dict[str, Any] = {
        "duration_seconds": float(getattr(audio.info, "length", 0.0)),
    }
    bitrate = getattr(audio.info, "bitrate", None)
    if bitrate is not None:
        result["bitrate"] = int(bitrate)
    sample_rate = getattr(audio.info, "sample_rate", None)
    if sample_rate is not None:
        result["sample_rate"] = int(sample_rate)
    if audio.tags:
        tags: dict[str, list[str]] = {}
        for key, values in audio.tags.items():
            sequence = [values] if isinstance(values, (str, bytes)) else values
            tags[str(key)] = [str(value) for value in sequence]
        result["tags"] = tags
    return result


def render_video(
    ffmpeg: str,
    mix_wav: Path,
    image: Path,
    destination: Path,
    delivery_gain: float,
) -> None:
    if not image.is_file():
        raise SystemExit(f"Still image does not exist: {image}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = temporary_sibling(destination)
    command = [
            ffmpeg,
            "-nostdin",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-framerate",
            "1",
            "-i",
            str(image),
            "-i",
            str(mix_wav),
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-tune",
            "stillimage",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
    ]
    if delivery_gain < 1.0:
        command.extend(["-af", f"volume={delivery_gain:.12g}"])
    command.extend(
        [
            "-shortest",
            "-movflags",
            "+faststart",
            str(temporary),
        ]
    )
    try:
        run(command)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def decode_test(ffmpeg: str, path: Path) -> None:
    run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-f",
            "null",
            os.devnull,
        ]
    )


def cleanup_unused_stems(manifest: dict[str, Any]) -> int:
    stems_dir = Path(manifest["stems_dir"]).resolve()
    keep = {expected_guitar_stem(manifest, tile).resolve() for tile in manifest["tiles"]}
    removed = 0
    for tile in manifest["tiles"]:
        prefix = Path(tile["clip_wav"]).stem
        for path in stems_dir.glob(f"{prefix}_*.wav"):
            resolved = path.resolve()
            if resolved not in keep and is_within(resolved, stems_dir):
                path.unlink()
                removed += 1
    return removed


def mix(args: argparse.Namespace, manifest: dict[str, Any], ffmpeg: str) -> dict[str, Any]:
    np, sf = audio_modules()
    frames = int(manifest["frames"])
    estimated_memory = frames * 36
    available_memory = available_memory_bytes()
    if (
        available_memory is not None
        and estimated_memory > available_memory * 0.80
        and not args.allow_high_memory
    ):
        raise SystemExit(
            f"Mixing is estimated to need about {estimated_memory / 2**30:.2f} GiB, "
            f"but only {available_memory / 2**30:.2f} GiB is currently available. "
            "Free memory, shorten the source, or use --allow-high-memory after review."
        )

    master_path = Path(manifest["master_wav"])
    recorded_master_hash = require_sha256(
        manifest.get("master_wav_sha256"), "Decoded master SHA-256"
    )
    if not master_path.is_file():
        raise SystemExit("Decoded master is missing. Rerun --stage prepare.")
    if hash_file(master_path) != recorded_master_hash:
        raise SystemExit("Decoded master no longer matches its preparation hash.")
    master, sample_rate = sf.read(manifest["master_wav"], dtype="float32", always_2d=True)
    if sample_rate != int(manifest["sample_rate"]) or len(master) != frames:
        raise SystemExit("Decoded master no longer matches the preparation manifest.")

    estimate = load_estimate(manifest)
    envelope = make_scope_envelope(np, manifest)
    active = envelope > 1e-6
    estimate *= envelope[:, None]
    removed_rms = rms_db(np, estimate[active])
    master -= estimate
    edited_peak = float(np.max(np.abs(master))) if len(master) else 0.0
    delivery_gain = min(1.0, args.delivery_peak / max(edited_peak, 1e-12))

    fade_frames = round(float(manifest["fade_seconds"]) * sample_rate)
    boundary_steps: list[float] = []
    for window in manifest["windows"]:
        start = int(window["start_frame"])
        end = int(window["end_frame"])
        for boundary in (start - fade_frames, start, end, end + fade_frames):
            if 0 < boundary < len(master):
                boundary_steps.append(float(np.max(np.abs(master[boundary] - master[boundary - 1]))))

    work_dir = Path(manifest["work_dir"])
    mix_wav = work_dir / "edited-float-master.wav"
    sf.write(mix_wav, master, sample_rate, subtype="FLOAT")

    assert args.output is not None
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata_result: dict[str, Any] = {}
    if output.suffix.lower() == ".wav":
        temporary = temporary_sibling(output)
        try:
            shutil.copyfile(mix_wav, temporary)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    elif output.suffix.lower() == ".mp3":
        encode_mp3(ffmpeg, mix_wav, output, args.bitrate, delivery_gain)
        metadata_result = copy_safe_metadata(
            Path(manifest["source"]), output, args.title
        )
    else:
        raise SystemExit("--output must end in .mp3 or .wav")
    decode_test(ffmpeg, output)
    output_info = media_info(output)
    output_duration = output_info.get("duration_seconds")
    if output_duration is not None and abs(output_duration - frames / sample_rate) > 0.25:
        raise SystemExit(
            f"Output duration check failed: {output_duration:.3f}s versus "
            f"{frames / sample_rate:.3f}s source."
        )

    video_output: str | None = None
    video_media_info: dict[str, Any] = {}
    if args.video_output or args.image:
        if not (args.video_output and args.image):
            raise SystemExit("Use --image and --video-output together.")
        video = args.video_output.expanduser().resolve()
        render_video(
            ffmpeg,
            mix_wav,
            args.image.expanduser().resolve(),
            video,
            delivery_gain,
        )
        decode_test(ffmpeg, video)
        video_media_info = media_info(video)
        video_duration = video_media_info.get("duration_seconds")
        if video_duration is not None and abs(video_duration - frames / sample_rate) > 0.30:
            raise SystemExit(
                f"Video duration check failed: {video_duration:.3f}s versus "
                f"{frames / sample_rate:.3f}s source."
            )
        video_output = str(video)

    cleaned_stems = cleanup_unused_stems(manifest) if args.cleanup_unused_stems else 0
    report = {
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "source": Path(manifest["source"]).name,
        "source_sha256": manifest.get("source_sha256"),
        "output": output.name,
        "output_sha256": hash_file(output),
        "video_output": Path(video_output).name if video_output else None,
        "video_sha256": hash_file(Path(video_output)) if video_output else None,
        "model": manifest["stem_source"],
        "model_checkpoint_sha256": manifest.get("model_checkpoint_sha256"),
        "model_config_sha256": manifest.get("model_config_sha256"),
        "audio_separator_version": manifest.get("audio_separator_version"),
        "python_version": manifest.get("python_version"),
        "ffmpeg_version": manifest.get("ffmpeg_version"),
        "stem_kind": manifest["stem_kind"],
        "scope": manifest["scope"],
        "windows": manifest["windows"],
        "external_stem_offset_seconds": manifest.get("external_stem_offset_seconds"),
        "external_stem_gain": manifest.get("external_stem_gain"),
        "sample_rate": sample_rate,
        "channels": 2,
        "frames": len(master),
        "duration_seconds": len(master) / sample_rate,
        "model_tiles": len(manifest["tiles"]),
        "fade_seconds": manifest["fade_seconds"],
        "removed_signal_rms_dbfs": removed_rms,
        "source_peak": float(manifest["source_peak"]),
        "edited_float_peak": edited_peak,
        "delivery_peak_target": args.delivery_peak,
        "lossy_delivery_gain": delivery_gain,
        "lossy_delivery_gain_db": 20 * math.log10(max(delivery_gain, 1e-20)),
        "outside_envelope_unchanged_in_float_mix": True,
        "maximum_boundary_sample_step": max(boundary_steps, default=0.0),
        "estimated_mix_memory_bytes": estimated_memory,
        "metadata": metadata_result,
        "output_media_info": output_info,
        "video_media_info": video_media_info,
        "edited_float_master_sha256": hash_file(mix_wav),
        "unused_stem_files_removed": cleaned_stems,
        "semantic_note": (
            "The aggregate guitar-labelled estimate was removed; this is not separate "
            "lead/rhythm isolation and coverage or bleed can vary."
            if manifest["stem_kind"] == "aggregate-guitar"
            else f"Removal follows the supplied {manifest['stem_kind']} stem at the "
            "recorded offset and gain; alignment remains user-verified."
        ),
    }
    report_path = (args.report or work_dir / "report.json").expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_report = temporary_sibling(report_path)
    try:
        temporary_report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_report, report_path)
    finally:
        temporary_report.unlink(missing_ok=True)
    print(f"Wrote audio: {output}")
    if delivery_gain < 1.0 and output.suffix.lower() == ".mp3":
        print(f"Applied {report['lossy_delivery_gain_db']:.2f} dB global gain for MP3 headroom.")
    if video_output:
        print(f"Wrote video: {video_output}")
    if cleaned_stems:
        print(f"Removed {cleaned_stems} unused generated stem file(s).")
    print(f"Wrote report: {report_path}")
    return report


def validate_resume_arguments(args: argparse.Namespace, manifest: dict[str, Any]) -> None:
    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Resume input audio does not exist: {source}")
    if source != Path(manifest["source"]).resolve():
        raise SystemExit(
            f"Resume input does not match the manifest: {source} != {manifest['source']}"
        )
    recorded_source_hash = require_sha256(
        manifest.get("source_sha256"), "Source audio SHA-256"
    )
    if hash_file(source) != recorded_source_hash:
        raise SystemExit("Resume input contents no longer match the preparation manifest.")
    if args.scope is not None and args.scope != manifest["scope"]:
        raise SystemExit(
            f"Resume scope does not match the manifest: {args.scope} != {manifest['scope']}"
        )
    if args.window:
        parsed = parse_windows(args.window, int(manifest["frames"]), int(manifest["sample_rate"]))
        stored = [
            (int(window["start_frame"]), int(window["end_frame"]))
            for window in manifest["windows"]
        ]
        if parsed != stored:
            raise SystemExit("Resume windows do not match the preparation manifest.")
    if args.stem_kind is not None and args.stem_kind != manifest["stem_kind"]:
        raise SystemExit("Resume --stem-kind does not match the preparation manifest.")
    if args.stem_file is not None:
        stored_source = manifest.get("external_stem_source")
        if stored_source is None or args.stem_file.expanduser().resolve() != Path(stored_source).resolve():
            raise SystemExit("Resume --stem-file does not match the preparation manifest.")
    comparisons = (
        ("fade", "fade_seconds"),
        ("context", "context_seconds"),
        ("chunk_seconds", "chunk_seconds"),
        ("prepare_peak", "preparation_peak_target"),
        ("stem_offset", "external_stem_offset_seconds"),
        ("stem_gain", "external_stem_gain"),
    )
    for argument_name, manifest_name in comparisons:
        value = getattr(args, argument_name)
        stored = manifest.get(manifest_name)
        if value is not None:
            if stored is None or not math.isclose(
                float(value), float(stored), rel_tol=0.0, abs_tol=1e-9
            ):
                raise SystemExit(
                    f"Resume --{argument_name.replace('_', '-')} does not match the manifest."
                )
    if args.model_dir is not None and args.model_dir.expanduser().resolve() != Path(
        manifest["models_dir"]
    ).resolve():
        raise SystemExit("Resume --model-dir does not match the preparation manifest.")
    args.scope = manifest["scope"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Remove an aggregate or supplied guitar stem from a whole song, selected "
            "windows, or everywhere outside selected windows."
        )
    )
    parser.add_argument("input", type=Path, help="Source audio file")
    parser.add_argument(
        "--scope",
        choices=("whole", "windows", "outside-windows"),
        help="Where the selected stem is subtracted; required for prepare/all",
    )
    parser.add_argument(
        "--window",
        action="append",
        default=[],
        metavar="START-END",
        help="Repeatable MM:SS, HH:MM:SS, or seconds range; END may be 'end'",
    )
    parser.add_argument(
        "--stem-file",
        type=Path,
        help="Aligned full-length lead, rhythm, aggregate, or custom stem; skips model separation",
    )
    parser.add_argument(
        "--stem-kind",
        choices=("aggregate-guitar", "lead-guitar", "rhythm-guitar", "custom"),
        help="Semantic label; required with --stem-file, otherwise aggregate-guitar",
    )
    parser.add_argument(
        "--stem-offset",
        type=float,
        help="Seconds where external stem frame zero lands in the master; default: 0",
    )
    parser.add_argument(
        "--stem-gain",
        type=float,
        help="Linear gain applied to an external stem before subtraction; default: 1",
    )
    parser.add_argument(
        "--stage",
        choices=("all", "prepare", "separate", "mix"),
        default="all",
        help="Run the full workflow or resume one stage",
    )
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Required for all/mix stages")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--image", type=Path, help="Still image for optional video")
    parser.add_argument("--video-output", type=Path, help="Optional MP4 output")
    parser.add_argument("--title", help="Optional replacement MP3 title tag")
    parser.add_argument("--bitrate", default="320k", help="MP3 bitrate, default: 320k")
    parser.add_argument("--delivery-peak", type=float, default=0.95, help="Lossy-output sample-peak target, default: 0.95")
    parser.add_argument("--prepare-peak", type=float, help="Model-input peak target, default: 0.95")
    parser.add_argument("--fade", type=float, help="Boundary fade seconds, default: 0.35")
    parser.add_argument("--context", type=float, help="Model context seconds, default: 10")
    parser.add_argument(
        "--chunk-seconds",
        type=float,
        help="Maximum model core tile duration, default: 90 seconds",
    )
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--audio-separator", help="Path to audio-separator executable")
    parser.add_argument("--ffmpeg", help="Path to FFmpeg executable")
    parser.add_argument("--force-separate", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing deliverables")
    parser.add_argument("--allow-high-memory", action="store_true")
    parser.add_argument(
        "--cleanup-unused-stems",
        action="store_true",
        help="After successful verification, delete generated non-guitar stem WAVs",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    preparing = args.stage in ("all", "prepare")
    mixing = args.stage in ("all", "mix")
    if mixing and args.output is None:
        parser.error("--output is required for --stage all or mix")
    if preparing and args.scope is None:
        parser.error("--scope is required for --stage all or prepare")
    if args.fade is not None and args.fade < 0:
        parser.error("--fade must be nonnegative")
    if args.context is not None and args.context <= 0:
        parser.error("--context must be positive")
    if args.chunk_seconds is not None and args.chunk_seconds <= 0:
        parser.error("--chunk-seconds must be positive")
    if not 0 < args.delivery_peak <= 1.0:
        parser.error("--delivery-peak must be greater than zero and at most 1.0")
    if args.prepare_peak is not None and not 0 < args.prepare_peak < 1.0:
        parser.error("--prepare-peak must be greater than zero and below 1.0")
    if args.stem_gain is not None and args.stem_gain == 0:
        parser.error("--stem-gain cannot be zero; use a negative value only to correct polarity")
    if args.video_output and args.video_output.suffix.lower() != ".mp4":
        parser.error("--video-output must end in .mp4")
    if bool(args.video_output) != bool(args.image):
        parser.error("Use --image and --video-output together")

    if preparing:
        if args.stem_file is not None:
            if args.stem_kind is None:
                parser.error("--stem-file requires an explicit --stem-kind")
            args.stem_offset = 0.0 if args.stem_offset is None else args.stem_offset
            args.stem_gain = 1.0 if args.stem_gain is None else args.stem_gain
        else:
            if args.stem_kind not in (None, "aggregate-guitar"):
                parser.error(
                    "lead-guitar, rhythm-guitar, and custom labels require --stem-file. "
                    "The default BS-RoFormer backend produces only aggregate-guitar."
                )
            if args.stem_offset is not None or args.stem_gain is not None:
                parser.error("--stem-offset and --stem-gain require --stem-file")
            args.stem_kind = "aggregate-guitar"
            args.stem_offset = 0.0
            args.stem_gain = 1.0
        args.fade = 0.35 if args.fade is None else args.fade
        args.context = 10.0 if args.context is None else args.context
        args.chunk_seconds = 90.0 if args.chunk_seconds is None else args.chunk_seconds
        args.prepare_peak = 0.95 if args.prepare_peak is None else args.prepare_peak
        if args.scope == "whole" and args.window:
            parser.error("--window is not used with --scope whole")
        validate_paths(args, will_mix=mixing)

    ffmpeg = resolve_program(args.ffmpeg, "ffmpeg", "FFMPEG_BINARY")
    if preparing:
        manifest = prepare(args, ffmpeg)
    else:
        manifest = load_manifest(args.work_dir)
        validate_resume_arguments(args, manifest)
        if args.model_dir is None:
            args.model_dir = Path(manifest["models_dir"])
        if args.stem_file is None and manifest.get("external_stem_source"):
            args.stem_file = Path(manifest["external_stem_source"])
        validate_paths(args, will_mix=mixing)
    if args.stage == "prepare":
        return 0
    if args.stage in ("all", "separate"):
        separate(args, manifest, ffmpeg)
    if args.stage == "separate":
        return 0
    mix(args, manifest, ffmpeg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
