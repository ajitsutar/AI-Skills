#!/usr/bin/env python3
"""Optional SAM Audio adapter for text- and span-prompted separation.

The heavy optional dependencies are imported only after argument parsing so that
``--help`` remains usable in the base guitar-karaoke environment.  The adapter
uses Meta's public SAM Audio API and writes an isolated target, its residual,
and a JSON provenance report.  It does not inspect or accept credentials.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


DEFAULT_MODEL = "facebook/sam-audio-large"
SCHEMA_VERSION = 1
MAX_TAIL_ADJUSTMENT_SECONDS = 0.01
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE
)


class UserError(RuntimeError):
    """A concise, actionable failure safe to print without a traceback."""


@dataclass(frozen=True)
class Runtime:
    torch: Any
    torchaudio: Any
    soundfile: Any
    SAMAudio: Any
    SAMAudioProcessor: Any
    huggingface_hub: Any


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Use the optional Meta SAM Audio backend to separate one prompted "
            "target and residual into exact-length float WAV files."
        )
    )
    parser.add_argument("input", nargs="?", type=Path, help="source audio file")
    parser.add_argument("--prompt", help="lowercase noun/verb phrase, e.g. 'lead electric guitar'")
    parser.add_argument("--output-dir", type=Path, help="directory for the two WAVs and JSON report")
    parser.add_argument("--prefix", help="safe filename prefix; defaults to the input stem")
    parser.add_argument(
        "--positive-span", nargs=2, action="append", metavar=("START", "END"), default=[],
        help="repeatable time range where the target is present (seconds, MM:SS, or HH:MM:SS)",
    )
    parser.add_argument(
        "--negative-span", nargs=2, action="append", metavar=("START", "END"), default=[],
        help="repeatable time range where the target is absent",
    )
    parser.add_argument(
        "--predict-spans", action="store_true",
        help="let SAM Audio predict event spans for a text-only prompt",
    )
    parser.add_argument(
        "--reranking-candidates", type=int, default=1,
        help="text-only candidates to generate and rank (default: 1)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Hugging Face model id (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--device", default="auto", metavar="auto|cpu|cuda|cuda:N",
        help="inference device; auto prefers CUDA and otherwise uses CPU",
    )
    parser.add_argument(
        "--local-files-only", action="store_true",
        help="forbid network access and require locally cached model files",
    )
    parser.add_argument(
        "--preflight", action="store_true",
        help="check optional dependencies, hardware, and gated-model accessibility without inference",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace all three existing outputs transactionally")
    return parser


def parse_timestamp(value: str) -> float:
    text = value.strip()
    if not text:
        raise UserError("A span timestamp is empty.")
    parts = text.split(":")
    if len(parts) > 3:
        raise UserError(f"Invalid timestamp {value!r}; use seconds, MM:SS, or HH:MM:SS.")
    try:
        numbers = [float(part) for part in parts]
    except ValueError as exc:
        raise UserError(f"Invalid timestamp {value!r}; use seconds, MM:SS, or HH:MM:SS.") from exc
    if any(not math.isfinite(number) or number < 0 for number in numbers):
        raise UserError(f"Timestamp {value!r} must contain finite non-negative values.")
    if len(numbers) > 1 and any(number >= 60 for number in numbers[1:]):
        raise UserError(f"Timestamp {value!r} has a minutes/seconds field outside 0-59.")
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60.0 + number
    return seconds


def build_anchors(
    positive: Sequence[Sequence[str]], negative: Sequence[Sequence[str]], duration: float
) -> list[list[float | str]]:
    if not math.isfinite(duration) or duration <= 0:
        raise UserError("The source duration must be positive and finite.")
    if negative and not positive:
        raise UserError("A span prompt needs at least one --positive-span; negative spans are optional examples.")
    anchors: list[list[float | str]] = []
    for sign, groups in (("+", positive), ("-", negative)):
        for group in groups:
            start, end = (parse_timestamp(group[0]), parse_timestamp(group[1]))
            if start >= end:
                raise UserError(f"Span {group[0]}-{group[1]} must have START before END.")
            tolerance = max(1e-6, duration * 1e-9)
            if start >= duration or end > duration + tolerance:
                raise UserError(
                    f"Span {group[0]}-{group[1]} exceeds the {duration:.6f}-second source."
                )
            anchors.append([sign, start, min(end, duration)])
    anchors.sort(key=lambda item: (float(item[1]), float(item[2]), str(item[0])))
    for index, first in enumerate(anchors):
        for second in anchors[index + 1 :]:
            if float(second[1]) >= float(first[2]):
                break
            if first[0] != second[0]:
                raise UserError(
                    "Positive and negative span prompts overlap: "
                    f"{first[1]}-{first[2]} and {second[1]}-{second[2]}."
                )
    return anchors


def safe_prefix(value: str) -> str:
    prefix = INVALID_FILENAME.sub("_", value).strip().rstrip(".")
    if not prefix or prefix in {".", ".."} or WINDOWS_RESERVED.match(prefix):
        raise UserError("The output prefix is empty or reserved after filename sanitization.")
    if len(prefix) > 160:
        raise UserError("The output prefix is too long; use at most 160 characters.")
    return prefix


def plan_outputs(input_path: Path, output_dir: Path, prefix: str | None) -> dict[str, Path]:
    chosen = safe_prefix(prefix if prefix is not None else input_path.stem)
    root = output_dir.expanduser().resolve(strict=False)
    return {
        "target": root / f"{chosen} - SAM Audio target.wav",
        "residual": root / f"{chosen} - SAM Audio residual.wav",
        "report": root / f"{chosen} - SAM Audio report.json",
    }


def validate_output_paths(input_path: Path, outputs: dict[str, Path], overwrite: bool) -> None:
    source = input_path.resolve(strict=True)
    resolved = [path.resolve(strict=False) for path in outputs.values()]
    if len(set(resolved)) != len(resolved):
        raise UserError("Target, residual, and report paths must be distinct.")
    if source in resolved:
        raise UserError("An output path resolves to the source audio; refusing to replace the input.")
    existing = [str(path) for path in outputs.values() if path.exists()]
    if existing and not overwrite:
        raise UserError("Output already exists; use --overwrite to replace the complete set: " + ", ".join(existing))


def _import_optional(name: str, install_hint: str) -> Any:
    try:
        return importlib.import_module(name)
    except (ImportError, OSError) as exc:
        raise UserError(f"Optional dependency {name!r} is unavailable. {install_hint}") from exc


def load_runtime() -> Runtime:
    if sys.version_info < (3, 11):
        raise UserError("SAM Audio requires Python 3.11 or newer.")
    hint = "Install the official facebookresearch/sam-audio project in an isolated environment."
    torch = _import_optional("torch", hint)
    torchaudio = _import_optional("torchaudio", hint)
    soundfile = _import_optional("soundfile", "Install soundfile in the same isolated environment.")
    sam_audio = _import_optional("sam_audio", hint)
    hub = _import_optional("huggingface_hub", hint)
    try:
        sam_model = sam_audio.SAMAudio
        sam_processor = sam_audio.SAMAudioProcessor
    except AttributeError as exc:
        raise UserError("The installed sam_audio package lacks SAMAudio or SAMAudioProcessor.") from exc
    return Runtime(torch, torchaudio, soundfile, sam_model, sam_processor, hub)


def resolve_device(torch: Any, requested: str) -> tuple[str, dict[str, Any]]:
    value = requested.strip().lower()
    if value == "auto":
        value = "cuda" if bool(torch.cuda.is_available()) else "cpu"
    if value == "cpu":
        return "cpu", {
            "requested": requested,
            "resolved": "cpu",
            "cuda_available": bool(torch.cuda.is_available()),
            "warning": "CPU inference is experimental and can be extremely slow or memory intensive.",
        }
    match = re.fullmatch(r"cuda(?::(\d+))?", value)
    if not match:
        raise UserError("--device must be auto, cpu, cuda, or cuda:N.")
    if not bool(torch.cuda.is_available()):
        raise UserError("CUDA was requested but this PyTorch runtime cannot access a CUDA device.")
    index = int(match.group(1) or 0)
    count = int(torch.cuda.device_count())
    if index >= count:
        raise UserError(f"CUDA device {index} was requested, but only {count} device(s) are visible.")
    properties = torch.cuda.get_device_properties(index)
    return f"cuda:{index}", {
        "requested": requested,
        "resolved": f"cuda:{index}",
        "cuda_available": True,
        "cuda_device_count": count,
        "device_name": str(getattr(properties, "name", "unknown")),
        "total_memory_bytes": int(getattr(properties, "total_memory", 0)),
        "torch_cuda_version": str(getattr(getattr(torch, "version", None), "cuda", None)),
    }


def _safe_exception(exc: BaseException) -> str:
    text = str(exc)
    text = re.sub(r"hf_[A-Za-z0-9]{12,}", "[redacted]", text)
    text = re.sub(r"\bBearer\s+\S+", "Bearer [redacted]", text, flags=re.I)
    text = re.sub(r"([?&](?:token|access_token|auth)=)[^&\s]+", r"\1[redacted]", text, flags=re.I)
    return text[:500]


def check_model_access(hub: Any, model_id: str, local_files_only: bool) -> dict[str, Any]:
    """Check cached files or authenticated HEAD access without loading weights."""
    try:
        if local_files_only:
            snapshot = hub.snapshot_download(repo_id=model_id, local_files_only=True)
            snapshot_path = Path(snapshot).resolve()
            config = snapshot_path / "config.json"
            weight_files = sorted(
                path for path in snapshot_path.rglob("*")
                if path.is_file() and path.suffix.lower() in {".pt", ".bin", ".safetensors"}
                and not path.name.endswith(".incomplete") and path.stat().st_size > 0
            )
            if not config.is_file() or config.stat().st_size <= 0 or not weight_files:
                raise UserError(
                    "The local SAM Audio snapshot lacks a nonempty config.json or model weight file."
                )
            return {
                "status": "local-files-present",
                "snapshot": str(snapshot_path),
                "weight_file_count": len(weight_files),
                "full_load_still_required": True,
            }

        # token=True delegates to Hugging Face's configured authentication.  The
        # adapter never retrieves or displays the token itself.  HEAD each gated
        # artifact rather than treating public repository metadata as proof.
        info = hub.HfApi().model_info(repo_id=model_id, token=True)
        names = [str(getattr(item, "rfilename", "")) for item in getattr(info, "siblings", [])]
        weights = sorted(
            name for name in names
            if Path(name).suffix.lower() in {".pt", ".bin", ".safetensors"}
        )
        required = ["config.json", *weights]
        if not weights:
            raise UserError("The model repository metadata lists no supported weight artifact.")
        checked: list[dict[str, Any]] = []
        revision = str(getattr(info, "sha", "unknown"))
        for filename in required:
            url = hub.hf_hub_url(repo_id=model_id, filename=filename, revision=revision)
            metadata = hub.get_hf_file_metadata(url=url, token=True)
            size = getattr(metadata, "size", None)
            if size is not None and int(size) <= 0:
                raise UserError(f"The gated model artifact {filename!r} is empty.")
            checked.append({"filename": filename, "size_bytes": int(size) if size is not None else None})
        return {
            "status": "authenticated-artifact-heads-accessible",
            "revision": revision,
            "verified_files": checked,
        }
    except UserError:
        raise
    except Exception as exc:  # the hub changes its public exception subclasses across releases
        mode = "local cache" if local_files_only else "the gated Hugging Face repository"
        raise UserError(
            f"SAM Audio model {model_id!r} is inaccessible through {mode}. "
            "Request/accept access and use the existing Hugging Face authentication, or select "
            f"a permitted local snapshot. Backend detail: {_safe_exception(exc)}"
        ) from exc


def preflight(runtime: Runtime, args: argparse.Namespace) -> dict[str, Any]:
    device, hardware = resolve_device(runtime.torch, args.device)
    access = check_model_access(runtime.huggingface_hub, args.model, args.local_files_only)
    return {
        "schema_version": SCHEMA_VERSION,
        "backend": "sam-audio",
        "model_id": args.model,
        "device": device,
        "hardware": hardware,
        "model_access": access,
        "dependencies": {
            "torch": str(getattr(runtime.torch, "__version__", "unknown")),
            "torchaudio": str(getattr(runtime.torchaudio, "__version__", "unknown")),
        },
        "downloads_performed_by_preflight": False,
        "inference_performed": False,
        "credentials_inspected": False,
    }


def source_info(soundfile: Any, path: Path) -> dict[str, Any]:
    try:
        info = soundfile.info(str(path))
    except Exception as exc:
        raise UserError(
            "Could not read exact source audio metadata. Decode the source to PCM WAV first. "
            f"Backend detail: {_safe_exception(exc)}"
        ) from exc
    frames, rate, channels = int(info.frames), int(info.samplerate), int(info.channels)
    if frames <= 0 or rate <= 0 or channels <= 0:
        raise UserError("The source has invalid frame, sample-rate, or channel metadata.")
    return {
        "frames": frames,
        "sample_rate": rate,
        "channels": channels,
        "duration_seconds": frames / rate,
        "format": str(getattr(info, "format", "unknown")),
        "subtype": str(getattr(info, "subtype", "unknown")),
    }


def run_official_api(
    runtime: Runtime,
    model_id: str,
    source: Path,
    prompt: str,
    anchors: list[list[float | str]],
    device: str,
    local_files_only: bool,
    predict_spans: bool,
    reranking_candidates: int,
    revision: str | None = None,
    local_snapshot: str | None = None,
) -> tuple[Any, int, dict[str, Any]]:
    if local_files_only:
        if not local_snapshot:
            raise UserError("Local-only loading requires the snapshot path verified by preflight.")
        load_source = local_snapshot
        load_kwargs: dict[str, Any] = {"local_files_only": True}
    else:
        if not revision or revision == "unknown":
            raise UserError("Remote loading requires the exact revision verified by preflight.")
        load_source = model_id
        load_kwargs = {"revision": revision}
    try:
        model = runtime.SAMAudio.from_pretrained(load_source, **load_kwargs)
        processor = runtime.SAMAudioProcessor.from_pretrained(load_source, **load_kwargs)
        model = model.eval().to(device)
        processor_kwargs: dict[str, Any] = {
            "audios": [str(source)],
            "descriptions": [prompt],
        }
        if anchors:
            processor_kwargs["anchors"] = [anchors]
        batch = processor(**processor_kwargs).to(device)
        with runtime.torch.inference_mode():
            if anchors:
                result = model.separate(batch)
            else:
                result = model.separate(
                    batch,
                    predict_spans=predict_spans,
                    reranking_candidates=reranking_candidates,
                )
    except RuntimeError as exc:
        detail = _safe_exception(exc)
        if "out of memory" in detail.lower():
            raise UserError(
                f"SAM Audio ran out of memory on {device}; no outputs were committed. Backend detail: {detail}"
            ) from exc
        raise UserError(f"SAM Audio inference failed; no outputs were committed. Backend detail: {detail}") from exc
    except (OSError, ValueError) as exc:
        raise UserError(
            "SAM Audio model loading or processing failed. Confirm gated access, the local cache, "
            f"and the input format. Backend detail: {_safe_exception(exc)}"
        ) from exc
    except Exception as exc:
        raise UserError(
            "SAM Audio model loading or processing failed; no outputs were committed. "
            f"Backend detail: {_safe_exception(exc)}"
        ) from exc
    if not hasattr(result, "target") or not hasattr(result, "residual"):
        raise UserError("SAM Audio returned no target/residual pair.")
    try:
        model_rate = int(processor.audio_sampling_rate)
    except (AttributeError, TypeError, ValueError) as exc:
        raise UserError("SAMAudioProcessor did not expose a valid audio_sampling_rate.") from exc
    if model_rate <= 0:
        raise UserError("SAMAudioProcessor returned a non-positive audio_sampling_rate.")
    return result, model_rate, {
        "requested_model_id": model_id,
        "from_pretrained_source": str(load_source),
        "revision": revision if not local_files_only else None,
        "local_files_only": bool(local_files_only),
    }


def single_waveform(value: Any, label: str) -> Any:
    if isinstance(value, (list, tuple)):
        if len(value) != 1:
            raise UserError(f"SAM Audio returned {len(value)} {label} items for one input; expected one.")
        value = value[0]
    ndim = int(getattr(value, "ndim", -1))
    if ndim == 3 and int(value.shape[0]) == 1:
        value = value[0]
        ndim = int(value.ndim)
    if ndim == 1:
        value = value.unsqueeze(0)
    elif ndim == 2 and int(value.shape[0]) > 8 and int(value.shape[1]) <= 8:
        value = value.transpose(0, 1)
    elif ndim != 2:
        raise UserError(f"SAM Audio returned unsupported {label} shape {getattr(value, 'shape', None)}.")
    if int(value.shape[0]) < 1 or int(value.shape[0]) > 8 or int(value.shape[-1]) < 1:
        raise UserError(f"SAM Audio returned invalid {label} shape {tuple(value.shape)}.")
    return value


def validate_frame_adjustment(
    resampled_frames: int, output_frames: int, output_rate: int
) -> tuple[int, int]:
    adjustment = output_frames - resampled_frames
    tolerance_frames = max(2, int(math.ceil(output_rate * MAX_TAIL_ADJUSTMENT_SECONDS)))
    if abs(adjustment) > tolerance_frames:
        raise UserError(
            "SAM Audio returned a materially different duration after resampling: "
            f"expected {output_frames} frames, got {resampled_frames} "
            f"(allowed tail tolerance: {tolerance_frames} frames). No outputs were committed."
        )
    return adjustment, tolerance_frames


def validate_output_channels(source_channels: int, target: Any, residual: Any) -> None:
    target_channels = int(target.shape[0])
    residual_channels = int(residual.shape[0])
    if target_channels != source_channels or residual_channels != source_channels:
        raise UserError(
            "SAM Audio channel mismatch: source has "
            f"{source_channels} channel(s), target has {target_channels}, and residual has "
            f"{residual_channels}. Mono estimates are not eligible for subtraction from a stereo "
            "master; use a mono evaluation source or a backend that preserves matching channels."
        )


def resample_and_fit(
    runtime: Runtime, waveform: Any, native_rate: int, output_rate: int, output_frames: int
) -> tuple[Any, dict[str, int]]:
    torch = runtime.torch
    waveform = waveform.detach().to(device="cpu", dtype=torch.float32)
    native_frames = int(waveform.shape[-1])
    if native_rate != output_rate:
        waveform = runtime.torchaudio.functional.resample(
            waveform, orig_freq=native_rate, new_freq=output_rate
        )
    resampled_frames = int(waveform.shape[-1])
    adjustment, tolerance_frames = validate_frame_adjustment(
        resampled_frames, output_frames, output_rate
    )
    if resampled_frames > output_frames:
        waveform = waveform[..., :output_frames]
    elif resampled_frames < output_frames:
        waveform = torch.nn.functional.pad(waveform, (0, output_frames - resampled_frames))
    if not bool(torch.isfinite(waveform).all().item()):
        raise UserError("SAM Audio output contains NaN or infinite samples.")
    return waveform.contiguous(), {
        "native_frames": native_frames,
        "resampled_frames": resampled_frames,
        "final_frames": int(waveform.shape[-1]),
        "tail_frame_adjustment": adjustment,
        "tail_tolerance_frames": tolerance_frames,
    }


def _new_temp(directory: Path, suffix: str) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=".sam-audio-", suffix=suffix, dir=str(directory))
    os.close(descriptor)
    path = Path(name)
    path.unlink()
    return path


def write_verified_float_wav(
    soundfile: Any, path: Path, waveform: Any, sample_rate: int, expected_frames: int
) -> dict[str, Any]:
    soundfile.write(
        str(path), waveform.transpose(0, 1).numpy(), sample_rate, format="WAV", subtype="FLOAT"
    )
    info = soundfile.info(str(path))
    if int(info.frames) != expected_frames or int(info.samplerate) != sample_rate:
        raise UserError(
            f"Output verification failed for {path.name}: got {info.frames} frames at {info.samplerate} Hz."
        )
    return {
        "frames": int(info.frames),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "format": str(info.format),
        "subtype": str(info.subtype),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bundle_lock_path(finals: Sequence[Path]) -> Path:
    parents = {path.parent.resolve(strict=True) for path in finals}
    if len(parents) != 1:
        raise UserError("All SAM Audio outputs must share one existing directory.")
    identity = "\n".join(sorted(os.path.normcase(str(path.resolve(strict=False))) for path in finals))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return next(iter(parents)) / f".sam-audio-bundle-{digest}.lock"


@contextmanager
def bundle_lock(finals: Sequence[Path]):
    lock_path = bundle_lock_path(finals)
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise UserError(
            f"Another process holds the SAM Audio output lock: {lock_path}. "
            "Wait for it to finish; remove the lock only after confirming no writer is active."
        ) from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        descriptor = -1
        yield lock_path
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def validate_final_targets(finals: Sequence[Path], overwrite: bool) -> None:
    existing: list[str] = []
    for path in finals:
        if path.is_symlink():
            raise UserError(f"Refusing to replace symlink output target: {path}")
        if path.exists():
            if not path.is_file():
                raise UserError(f"Refusing to replace non-file output target: {path}")
            existing.append(str(path))
    if existing and not overwrite:
        raise UserError("Output appeared during processing; nothing was committed: " + ", ".join(existing))


def commit_bundle(staged: dict[Path, Path], overwrite: bool) -> None:
    """Install a same-directory output set, rolling back partial commits."""
    finals = list(staged)
    with bundle_lock(finals):
        validate_final_targets(finals, overwrite)
        if not overwrite:
            installed: list[Path] = []
            try:
                for final, temporary in staged.items():
                    os.link(temporary, final)
                    installed.append(final)
                for temporary in staged.values():
                    temporary.unlink(missing_ok=True)
                return
            except Exception as exc:
                for path in installed:
                    path.unlink(missing_ok=True)
                raise UserError(
                    f"Could not safely commit the output set; partial files were removed: {_safe_exception(exc)}"
                ) from exc

        backups: dict[Path, Path] = {}
        installed = []
        committed = False
        try:
            for final in finals:
                if final.exists():
                    backup = _new_temp(final.parent, ".backup")
                    os.replace(final, backup)
                    backups[final] = backup
            for final, temporary in staged.items():
                os.replace(temporary, final)
                installed.append(final)
            committed = True
        except Exception as exc:
            for final in installed:
                final.unlink(missing_ok=True)
            restore_failures: list[str] = []
            for final, backup in backups.items():
                if backup.exists():
                    try:
                        os.replace(backup, final)
                    except Exception as restore_exc:
                        restore_failures.append(
                            f"{final} <- preserved backup {backup}: {_safe_exception(restore_exc)}"
                        )
            if restore_failures:
                raise UserError(
                    "Could not replace the output set, and automatic restoration was incomplete. "
                    "Recovery backups were preserved: " + "; ".join(restore_failures)
                ) from exc
            raise UserError(
                f"Could not replace the output set; previous files were restored: {_safe_exception(exc)}"
            ) from exc
        finally:
            if committed:
                for backup in backups.values():
                    backup.unlink(missing_ok=True)


def validate_arguments(args: argparse.Namespace) -> tuple[Path, str]:
    if args.input is None or args.output_dir is None or args.prompt is None:
        raise UserError("Inference requires INPUT, --prompt, and --output-dir.")
    source = args.input.expanduser().resolve(strict=False)
    if not source.is_file():
        raise UserError(f"Input audio does not exist or is not a file: {source}")
    prompt = args.prompt.strip()
    if not prompt or "\n" in prompt or "\r" in prompt:
        raise UserError("--prompt must be one non-empty line.")
    if len(prompt) > 500:
        raise UserError("--prompt is too long; use a concise noun or verb phrase.")
    if args.reranking_candidates < 1:
        raise UserError("--reranking-candidates must be at least 1.")
    if (args.positive_span or args.negative_span) and args.predict_spans:
        raise UserError("Do not combine explicit spans with --predict-spans.")
    if (args.positive_span or args.negative_span) and args.reranking_candidates != 1:
        raise UserError("Candidate reranking is supported here only for text-only prompting.")
    if not args.model.strip():
        raise UserError("--model cannot be empty.")
    return source, prompt


def separate(args: argparse.Namespace, runtime: Runtime) -> dict[str, Any]:
    source, prompt = validate_arguments(args)
    metadata = source_info(runtime.soundfile, source)
    anchors = build_anchors(args.positive_span, args.negative_span, metadata["duration_seconds"])
    outputs = plan_outputs(source, args.output_dir, args.prefix)
    validate_output_paths(source, outputs, args.overwrite)
    outputs["target"].parent.mkdir(parents=True, exist_ok=True)
    device, hardware = resolve_device(runtime.torch, args.device)
    access = check_model_access(runtime.huggingface_hub, args.model, args.local_files_only)

    result, model_rate, model_load = run_official_api(
        runtime, args.model, source, prompt, anchors, device, args.local_files_only,
        args.predict_spans, args.reranking_candidates,
        revision=None if args.local_files_only else access["revision"],
        local_snapshot=access.get("snapshot"),
    )
    target = single_waveform(result.target, "target")
    residual = single_waveform(result.residual, "residual")
    validate_output_channels(metadata["channels"], target, residual)
    target, target_adjustment = resample_and_fit(
        runtime, target, model_rate, metadata["sample_rate"], metadata["frames"]
    )
    residual, residual_adjustment = resample_and_fit(
        runtime, residual, model_rate, metadata["sample_rate"], metadata["frames"]
    )
    staged = {final: _new_temp(final.parent, final.suffix + ".tmp") for final in outputs.values()}
    try:
        target_meta = write_verified_float_wav(
            runtime.soundfile, staged[outputs["target"]], target, metadata["sample_rate"], metadata["frames"]
        )
        residual_meta = write_verified_float_wav(
            runtime.soundfile, staged[outputs["residual"]], residual, metadata["sample_rate"], metadata["frames"]
        )
        report = {
            "schema_version": SCHEMA_VERSION,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "backend": "sam-audio",
            "backend_api": "SAMAudio/SAMAudioProcessor.from_pretrained + model.separate",
            "model_id": args.model,
            "model_access": access,
            "model_load": model_load,
            "device": device,
            "hardware": hardware,
            "source": {
                "path": str(source),
                "sha256": sha256_file(source),
                **metadata,
            },
            "prompt": {
                "description": prompt,
                "mode": "text-and-span" if anchors else "text",
                "anchors": anchors,
                "predict_spans": bool(args.predict_spans),
                "reranking_candidates": args.reranking_candidates,
            },
            "native_model_sample_rate": model_rate,
            "outputs": {
                "target": {
                    "path": str(outputs["target"]),
                    "sha256": sha256_file(staged[outputs["target"]]),
                    **target_meta,
                    **target_adjustment,
                },
                "residual": {
                    "path": str(outputs["residual"]),
                    "sha256": sha256_file(staged[outputs["residual"]]),
                    **residual_meta,
                    **residual_adjustment,
                },
            },
            "license": "Meta SAM License (custom terms; operator review and acceptance required)",
            "limitations": [
                "Prompted separation is experimental and can contain target omissions or non-target bleed.",
                "A lead-guitar prompt does not guarantee exact lead-versus-rhythm guitar separation.",
                "SAM Audio target and residual are generated outputs and are not guaranteed to sum exactly to the source.",
                "Tail trimming or zero-padding used only to restore the exact source frame count is recorded per output.",
            ],
        }
        staged[outputs["report"]].write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        commit_bundle(staged, args.overwrite)
        return report
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        runtime = load_runtime()
        if args.preflight:
            print(json.dumps(preflight(runtime, args), indent=2, sort_keys=True))
            return 0
        report = separate(args, runtime)
        print(json.dumps({
            "target": report["outputs"]["target"]["path"],
            "residual": report["outputs"]["residual"]["path"],
            "report": str(plan_outputs(args.input, args.output_dir, args.prefix)["report"]),
        }, indent=2))
        return 0
    except UserError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
