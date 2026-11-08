#!/usr/bin/env python3
"""Experimental CPU lead/rhythm split for an authorized aggregate-guitar stem.

The listra92 checkpoint predicts one lead-guitar estimate. Rhythm guitar is the
mixture-consistent residual ``aggregate_guitar - lead``. The checkpoint is not
bundled or downloaded, and inference is refused until a reviewed rights record
authorizes the exact checkpoint and config for the intended use.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, NoReturn


MODEL_NAME = "Mel-Band RoFormer Lead/Rhythm Guitar by listra92"
MODEL_LABEL = "listra92-melband-lead-rhythm-experimental"
MODEL_SHA256 = "b3c47bca33609ca1ba0bb2d2076410bfd1eb941b051b72afc1f3e24d12b17eef"
MODEL_ARCHIVE_URL = (
    "https://huggingface.co/noblebarkrr/mvsepless_resources/resolve/main/"
    "mel_band_roformer/mbr_lead_rhythm_guitar_listra92.ckpt"
)
CONFIG_SHA256 = "8a27209d94bbadc4b83e0124b7689872684664fed7c3fd89780443610985f79d"
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "vendor" / "listra92_roformer" / "lead_rhythm.json"

SAMPLE_RATE = 44_100
CHANNELS = 2
CHUNK_FRAMES = 132_300
STEP_FRAMES = 66_150
FADE_FRAMES = 13_230
LEAD_NAME = "lead-guitar.wav"
RHYTHM_NAME = "rhythm-guitar.wav"
REPORT_NAME = "lead-rhythm-report.json"
RIGHTS_SCHEMA_VERSION = 1

RIGHTS_TEXT_FIELDS = (
    "rights_holder",
    "license_name",
    "terms_source",
    "permitted_use",
    "reviewed_by",
)
RIGHTS_TRUE_FIELDS = (
    "covers_model_weights",
    "covers_config",
    "intended_use_permitted",
)
UNVERIFIED_RIGHTS_VALUES = {
    "unknown",
    "unverified",
    "none",
    "n/a",
    "todo",
    "accepted risk",
}
_PUBLICATION_LOCKS_GUARD = threading.Lock()
_PUBLICATION_LOCKS: dict[str, threading.RLock] = {}


def fail(message: str) -> NoReturn:
    raise SystemExit(message)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolved_file(path: Path, label: str) -> Path:
    candidate = path.expanduser().resolve()
    if not candidate.is_file():
        fail(f"{label} does not exist or is not a file: {candidate}")
    return candidate


def validate_config(path: Path = CONFIG_PATH) -> tuple[dict[str, Any], str]:
    path = resolved_file(path, "Bundled lead/rhythm config")
    actual_hash = hash_file(path)
    if actual_hash != CONFIG_SHA256:
        fail(
            "Bundled lead/rhythm config hash mismatch; do not run an unknown config. "
            f"Expected {CONFIG_SHA256}, got {actual_hash}."
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"Bundled lead/rhythm config is unreadable: {error}")
    if not isinstance(config, dict):
        fail("Bundled lead/rhythm config must contain one JSON object.")
    if config.get("sample_rate") != SAMPLE_RATE or config.get("stereo") is not True:
        fail("Bundled lead/rhythm config must remain stereo at 44.1 kHz.")
    if config.get("num_stems") != 1:
        fail("Bundled lead/rhythm config must predict exactly one lead stem.")
    window_sizes = config.get("multi_stft_resolutions_window_sizes")
    if not isinstance(window_sizes, list) or not window_sizes:
        fail("Bundled lead/rhythm config has invalid multi-STFT window sizes.")
    config["multi_stft_resolutions_window_sizes"] = tuple(window_sizes)
    return config, actual_hash


def validate_checkpoint(path: Path) -> tuple[Path, str]:
    checkpoint = resolved_file(path, "Lead/rhythm checkpoint")
    actual_hash = hash_file(checkpoint)
    if actual_hash != MODEL_SHA256:
        fail(
            "Lead/rhythm checkpoint hash mismatch; the file was not used. "
            f"Expected {MODEL_SHA256}, got {actual_hash}."
        )
    return checkpoint, actual_hash


def read_rights_evidence(path: Path) -> tuple[Path, dict[str, Any], str]:
    evidence_path = resolved_file(path, "Model rights evidence")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"Model rights evidence must be valid JSON: {error}")
    if not isinstance(evidence, dict):
        fail("Model rights evidence must contain one JSON object.")
    if evidence.get("schema_version") != RIGHTS_SCHEMA_VERSION:
        fail(f"Model rights evidence schema_version must be {RIGHTS_SCHEMA_VERSION}.")
    for field in RIGHTS_TEXT_FIELDS:
        value = evidence.get(field)
        if (
            not isinstance(value, str)
            or not value.strip()
            or value.strip().casefold() in UNVERIFIED_RIGHTS_VALUES
        ):
            fail(f"Model rights evidence requires a verified {field!r} string.")
    for field in RIGHTS_TRUE_FIELDS:
        if evidence.get(field) is not True:
            fail(f"Model rights evidence requires {field!r}: true.")
    checkpoint_hash = str(evidence.get("checkpoint_sha256", "")).casefold()
    config_hash = str(evidence.get("config_sha256", "")).casefold()
    if checkpoint_hash != MODEL_SHA256 or config_hash != CONFIG_SHA256:
        fail(
            "Model rights evidence does not match the pinned lead/rhythm checkpoint "
            "and bundled config."
        )
    return evidence_path, evidence, hash_file(evidence_path)


def require_experimental_acknowledgement(args: argparse.Namespace) -> None:
    if not args.experimental:
        fail(
            "This backend is experimental. Pass --experimental only after accepting "
            "that lead/rhythm labels can bleed and are not exact."
        )
    if not args.acknowledge_role_bleed:
        fail(
            "Pass --acknowledge-role-bleed to confirm that the predicted lead and "
            "residual rhythm stems require listening validation."
        )
    if args.model_license_evidence is None:
        fail(
            "Inference requires --model-license-evidence for the exact checkpoint and "
            "config. Experimental acknowledgement does not establish model rights."
        )


def load_runtime() -> tuple[Any, Any, Any, Any]:
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from vendor.listra92_roformer.mel_band_roformer import MelBandRoformer
    except ImportError as error:
        fail(
            "Lead/rhythm runtime is incomplete. Install the isolated dependencies from "
            "scripts/requirements-lead-rhythm.txt. Missing import: "
            f"{error.name or error}"
        )
    return np, sf, torch, MelBandRoformer


def load_audio(source: Path, np: Any, sf: Any) -> tuple[Any, int]:
    try:
        mix, sample_rate = sf.read(source, dtype="float32", always_2d=True)
    except Exception as error:
        fail(f"Could not decode aggregate-guitar stem {source}: {error}")
    if sample_rate != SAMPLE_RATE:
        fail(f"Aggregate-guitar stem must be {SAMPLE_RATE} Hz; got {sample_rate} Hz.")
    if getattr(mix, "ndim", None) != 2 or mix.shape[1] != CHANNELS:
        fail("Aggregate-guitar stem must be stereo.")
    if len(mix) == 0:
        fail("Aggregate-guitar stem is empty.")
    if not np.isfinite(mix).all():
        fail("Aggregate-guitar stem contains NaN or infinite samples.")
    return mix, sample_rate


def load_model(
    checkpoint: Path,
    config: dict[str, Any],
    threads: int,
    *,
    torch_module: Any | None = None,
    model_class: Any | None = None,
) -> Any:
    if torch_module is None or model_class is None:
        _, _, imported_torch, imported_model = load_runtime()
        torch_module = imported_torch if torch_module is None else torch_module
        model_class = imported_model if model_class is None else model_class
    torch_module.set_num_threads(threads)
    torch_module.manual_seed(42)
    with contextlib.redirect_stdout(sys.stderr):
        model = model_class(**config)
        state = torch_module.load(
            checkpoint,
            map_location="cpu",
            weights_only=True,
        )
        model.load_state_dict(state, strict=True)
        model.eval()
    return model


def infer_lead(
    mix: Any,
    model: Any,
    np: Any,
    torch: Any,
    *,
    chunk_frames: int = CHUNK_FRAMES,
    step_frames: int = STEP_FRAMES,
    fade_frames: int = FADE_FRAMES,
    show_progress: bool = True,
) -> Any:
    if not (0 < fade_frames < step_frames <= chunk_frames):
        fail("Invalid internal overlap/add settings.")
    length = len(mix)
    audio = torch.from_numpy(mix.T.copy()).to(dtype=torch.float32, device="cpu")
    padded = length > 2 * step_frames
    if padded:
        audio = torch.nn.functional.pad(audio, (step_frames, step_frames), mode="reflect")

    result = torch.zeros_like(audio)
    counter = torch.zeros(audio.shape[-1], dtype=audio.dtype, device="cpu")
    window = torch.ones(chunk_frames, dtype=audio.dtype, device="cpu")
    window[:fade_frames] = torch.linspace(
        0, 1, fade_frames, dtype=audio.dtype, device="cpu"
    )
    window[-fade_frames:] = torch.linspace(
        1, 0, fade_frames, dtype=audio.dtype, device="cpu"
    )
    total_frames = audio.shape[-1]
    last_percent = -1
    with torch.inference_mode():
        for start in range(0, total_frames, step_frames):
            part = audio[:, start : start + chunk_frames]
            size = part.shape[-1]
            if size < chunk_frames:
                pad_mode = "reflect" if size > chunk_frames // 2 else "constant"
                part = torch.nn.functional.pad(
                    part,
                    (0, chunk_frames - size),
                    mode=pad_mode,
                )
            prediction = model(part.unsqueeze(0))
            if getattr(prediction, "ndim", None) != 3:
                fail("Lead model returned an unexpected tensor rank.")
            prediction = prediction[0, ..., :size]
            if tuple(prediction.shape) != (CHANNELS, size):
                fail(
                    "Lead model returned an unexpected shape: "
                    f"{tuple(prediction.shape)}; expected {(CHANNELS, size)}."
                )
            blend = window.clone()
            if start == 0:
                blend[:fade_frames] = 1
            if start + size >= total_frames:
                blend[-fade_frames:] = 1
            result[:, start : start + size] += prediction * blend[:size]
            counter[start : start + size] += blend[:size]
            percent = min(100, round((start + size) / total_frames * 100))
            if show_progress and (percent == 100 or percent >= last_percent + 5):
                print(f"Lead/rhythm inference {percent}%", file=sys.stderr, flush=True)
                last_percent = percent
    if bool((counter <= 0).any().item()):
        fail("Internal overlap/add coverage failed; no output was published.")
    result /= counter
    if padded:
        result = result[:, step_frames:-step_frames]
    lead = result.detach().cpu().numpy().T.astype(np.float32, copy=False)
    if lead.shape != mix.shape or not np.isfinite(lead).all():
        fail("Lead model produced invalid audio; no output was published.")
    return lead


def split_residual(mix: Any, lead: Any, np: Any) -> tuple[Any, float]:
    if getattr(lead, "shape", None) != getattr(mix, "shape", None):
        fail("Lead estimate shape does not match the aggregate-guitar input.")
    rhythm = (mix - lead).astype(np.float32, copy=False)
    if not np.isfinite(rhythm).all():
        fail("Residual rhythm calculation produced invalid audio.")
    reconstruction = lead + rhythm
    max_error = float(np.max(np.abs(reconstruction - mix)))
    return rhythm, max_error


def output_paths(output_dir: Path) -> tuple[Path, Path, Path]:
    root = output_dir.expanduser().resolve()
    return root / LEAD_NAME, root / RHYTHM_NAME, root / REPORT_NAME


def validate_output_paths(
    source: Path,
    checkpoint: Path,
    evidence_path: Path,
    destinations: tuple[Path, ...],
    overwrite: bool,
) -> None:
    protected = {source.resolve(), checkpoint.resolve(), evidence_path.resolve(), CONFIG_PATH.resolve()}
    for destination in destinations:
        if destination.resolve() in protected:
            fail(f"Output cannot replace an input or evidence file: {destination}")
        if _lexists(destination):
            if not destination.is_file() or destination.is_symlink():
                fail(f"Output path is not a regular file: {destination}")
            if not overwrite:
                fail(f"Output exists; pass --overwrite for an intentional redo: {destination}")


@contextmanager
def publication_lock(lock_path: Path, timeout_seconds: float = 30.0) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_key = os.path.normcase(str(lock_path.parent.resolve() / lock_path.name))
    with _PUBLICATION_LOCKS_GUARD:
        thread_lock = _PUBLICATION_LOCKS.setdefault(lock_key, threading.RLock())
    with thread_lock, lock_path.open("a+b") as handle:
        if handle.seek(0, os.SEEK_END) == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        deadline = time.monotonic() + timeout_seconds
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        fail(f"Timed out waiting for output lock: {lock_path}")
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        fail(f"Timed out waiting for output lock: {lock_path}")
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def _remove_if_linked_to(destination: Path, staged: Path) -> None:
    if not _lexists(destination):
        return
    try:
        if os.path.samefile(destination, staged):
            destination.unlink()
    except (FileNotFoundError, OSError):
        return


def _restore_backups(backups: list[tuple[Path, Path]]) -> list[str]:
    errors: list[str] = []
    for destination, backup in reversed(backups):
        if not _lexists(backup):
            continue
        if _lexists(destination):
            errors.append(f"could not restore {destination}; backup retained at {backup}")
            continue
        try:
            os.replace(backup, destination)
        except OSError as error:
            errors.append(f"could not restore {destination} from {backup}: {error}")
    return errors


def publish_stage(
    staged: dict[Path, Path],
    *,
    overwrite: bool,
    lock_path: Path,
) -> None:
    destinations = tuple(staged)
    for destination, source in staged.items():
        if destination.parent.resolve() != lock_path.parent.resolve():
            fail("All lead/rhythm outputs must share the locked destination directory.")
        if not source.is_file() or source.is_symlink():
            fail(f"Staged output is missing or unsafe: {source}")
        if _lexists(destination) and (not destination.is_file() or destination.is_symlink()):
            fail(f"Refusing to replace a non-regular output path: {destination}")
    with publication_lock(lock_path):
        for destination in destinations:
            if _lexists(destination):
                if not destination.is_file() or destination.is_symlink():
                    fail(f"Output path became a directory: {destination}")
                if not overwrite:
                    fail(f"Output appeared during processing and was preserved: {destination}")

        backups: list[tuple[Path, Path]] = []
        published: list[tuple[Path, Path]] = []
        try:
            if overwrite:
                for destination in destinations:
                    if _lexists(destination):
                        backup = destination.with_name(
                            f".{destination.name}.{uuid.uuid4().hex}.bak"
                        )
                        os.replace(destination, backup)
                        backups.append((destination, backup))
            for destination, source in staged.items():
                # Atomic no-clobber on Windows and POSIX; a raced output is preserved.
                os.link(source, destination)
                published.append((destination, source))
        except BaseException as error:
            for destination, source in reversed(published):
                _remove_if_linked_to(destination, source)
            restore_errors = _restore_backups(backups)
            detail = f" ({'; '.join(restore_errors)})" if restore_errors else ""
            if isinstance(error, SystemExit):
                raise SystemExit(f"{error}{detail}") from error
            raise SystemExit(f"Failed to publish lead/rhythm outputs: {error}{detail}") from error

        for source in staged.values():
            try:
                source.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                print(
                    f"WARNING: Output is complete but staged cleanup failed: {error}",
                    file=sys.stderr,
                )
        for _, backup in backups:
            try:
                backup.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                print(
                    f"WARNING: Output is complete but backup cleanup failed: {error}",
                    file=sys.stderr,
                )


def validate_written_wav(path: Path, sf: Any, expected_frames: int) -> None:
    try:
        info = sf.info(path)
    except Exception as error:
        fail(f"Could not inspect staged WAV {path}: {error}")
    if (
        info.samplerate != SAMPLE_RATE
        or info.channels != CHANNELS
        or info.frames != expected_frames
        or info.subtype != "FLOAT"
    ):
        fail(f"Staged WAV failed format validation: {path}")


def build_report(
    *,
    source: Path,
    source_hash: str,
    frames: int,
    checkpoint: Path,
    checkpoint_hash: str,
    config_hash: str,
    evidence_path: Path,
    evidence: dict[str, Any],
    evidence_hash: str,
    lead_path: Path,
    rhythm_path: Path,
    lead_hash: str,
    rhythm_hash: str,
    threads: int,
    max_error: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "experimental",
        "model": {
            "label": MODEL_LABEL,
            "name": MODEL_NAME,
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": checkpoint_hash,
            "config_sha256": config_hash,
            "archive_reference": MODEL_ARCHIVE_URL,
            "upstream_public_provenance_status": "unverified",
        },
        "rights_evidence": {
            "schema_version": RIGHTS_SCHEMA_VERSION,
            "sha256": evidence_hash,
        },
        "input": {
            "aggregate_guitar_stem": str(source),
            "sha256": source_hash,
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "frames": frames,
        },
        "inference": {
            "device": "cpu",
            "threads": threads,
            "chunk_frames": CHUNK_FRAMES,
            "step_frames": STEP_FRAMES,
            "overlap_fraction": 0.5,
            "fade_frames": FADE_FRAMES,
            "lead_definition": "model prediction",
            "rhythm_definition": "aggregate_guitar_minus_lead",
            "max_abs_reconstruction_error": max_error,
        },
        "outputs": {
            "lead": {"path": str(lead_path), "sha256": lead_hash},
            "rhythm": {"path": str(rhythm_path), "sha256": rhythm_hash},
        },
        "warnings": [
            "Lead/rhythm roles can bleed and are not exact semantic ground truth.",
            "The residual can contain non-rhythm content already present in the aggregate guitar stem.",
            "The public community checkpoint lacks verified original training provenance and public redistribution terms.",
        ],
    }


def run_split(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    require_experimental_acknowledgement(args)
    evidence_path, evidence, evidence_hash = read_rights_evidence(args.model_license_evidence)
    config, config_hash = validate_config()
    source = resolved_file(args.input, "Aggregate-guitar stem")
    checkpoint, checkpoint_hash = validate_checkpoint(args.checkpoint)
    if not 1 <= args.threads <= 64:
        fail("--threads must be between 1 and 64.")
    lead_path, rhythm_path, report_path = output_paths(args.output_dir)
    destinations = (lead_path, rhythm_path, report_path)
    validate_output_paths(
        source,
        checkpoint,
        evidence_path,
        destinations,
        args.overwrite,
    )

    np, sf, torch, model_class = load_runtime()
    mix, sample_rate = load_audio(source, np, sf)
    if sample_rate != SAMPLE_RATE:
        fail("Internal sample-rate validation failed.")
    model = load_model(
        checkpoint,
        config,
        args.threads,
        torch_module=torch,
        model_class=model_class,
    )
    print(
        "Experimental lead/rhythm inference · 50% overlap · CPU · roles may bleed",
        file=sys.stderr,
        flush=True,
    )
    lead = infer_lead(mix, model, np, torch)
    rhythm, max_error = split_residual(mix, lead, np)

    output_root = args.output_dir.expanduser().resolve()
    if output_root.exists() and not output_root.is_dir():
        fail(f"--output-dir is not a directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / ".lead-rhythm.publish.lock"
    with tempfile.TemporaryDirectory(prefix=".lead-rhythm-stage-", dir=output_root) as temporary:
        stage = Path(temporary)
        staged_lead = stage / LEAD_NAME
        staged_rhythm = stage / RHYTHM_NAME
        staged_report = stage / REPORT_NAME
        sf.write(staged_lead, lead, SAMPLE_RATE, subtype="FLOAT")
        sf.write(staged_rhythm, rhythm, SAMPLE_RATE, subtype="FLOAT")
        validate_written_wav(staged_lead, sf, len(mix))
        validate_written_wav(staged_rhythm, sf, len(mix))
        lead_hash = hash_file(staged_lead)
        rhythm_hash = hash_file(staged_rhythm)
        report = build_report(
            source=source,
            source_hash=hash_file(source),
            frames=len(mix),
            checkpoint=checkpoint,
            checkpoint_hash=checkpoint_hash,
            config_hash=config_hash,
            evidence_path=evidence_path,
            evidence=evidence,
            evidence_hash=evidence_hash,
            lead_path=lead_path,
            rhythm_path=rhythm_path,
            lead_hash=lead_hash,
            rhythm_hash=rhythm_hash,
            threads=args.threads,
            max_error=max_error,
        )
        staged_report.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        publish_stage(
            {
                lead_path: staged_lead,
                rhythm_path: staged_rhythm,
                report_path: staged_report,
            },
            overwrite=args.overwrite,
            lock_path=lock_path,
        )
    return lead_path, rhythm_path, report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Experimentally split an authorized 44.1 kHz stereo aggregate-guitar "
            "stem into a listra92 lead estimate and mixture-consistent rhythm residual."
        ),
        epilog=(
            "No model is downloaded. Public provenance and redistribution terms for "
            "the pinned checkpoint are unresolved. A reviewed rights-evidence record "
            "is mandatory; experimental acknowledgement is not permission."
        ),
    )
    parser.add_argument("input", type=Path, help="authorized aggregate-guitar stem WAV")
    parser.add_argument("--checkpoint", type=Path, required=True, help="local pinned listra92 checkpoint")
    parser.add_argument(
        "--model-license-evidence",
        type=Path,
        help="reviewed JSON rights record covering the exact checkpoint/config and intended use",
    )
    parser.add_argument("--output-dir", type=Path, required=True, help="directory for lead/rhythm WAVs and report")
    parser.add_argument("--threads", type=int, default=4, help="CPU inference threads (default: 4)")
    parser.add_argument(
        "--experimental",
        action="store_true",
        help="acknowledge this is an experimental backend, not exact role separation",
    )
    parser.add_argument(
        "--acknowledge-role-bleed",
        action="store_true",
        help="acknowledge that lead/rhythm bleed requires listening validation",
    )
    parser.add_argument("--overwrite", action="store_true", help="replace existing deliverables transactionally")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    lead, rhythm, report = run_split(args)
    print(json.dumps({"lead": str(lead), "rhythm": str(rhythm), "report": str(report)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
