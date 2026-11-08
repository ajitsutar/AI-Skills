#!/usr/bin/env python
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path


_PUBLICATION_LOCKS_GUARD = threading.Lock()
_PUBLICATION_LOCKS = {}

AUDIO_SEPARATOR_VERSION = "0.48.0"
MELBAND_MODEL_FILENAME = "vocals_mel_band_roformer.ckpt"
MELBAND_CONFIG_FILENAME = "vocals_mel_band_roformer.yaml"
MELBAND_NO_VOCALS_STEM = "other"
MELBAND_MODEL_SHA256 = "87201f4d31afb5bc79993230fc49446918425574db48c01c405e44f365c7559e"
MELBAND_CONFIG_SHA256 = "b958b29c8f7195f0d86bee6759a33980db675c4ecaf2fcaa80fa125828e6cd38"


def _lexists(path):
    return os.path.lexists(os.fspath(path))


@contextlib.contextmanager
def _publication_lock(lock_path):
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


def find_no_vocals(job_outdir, model, audio):
    """Find the stem produced by one isolated Demucs invocation.

    ``job_outdir`` must be unique to the invocation. Searching a shared output
    tree can return a stale stem from a different track when Demucs changes or
    sanitizes an output directory name.
    """
    job_outdir = Path(job_outdir)
    expected = job_outdir / model / Path(audio).stem / "no_vocals.wav"
    if expected.is_file():
        return expected
    matches = [path for path in job_outdir.rglob("no_vocals.*") if path.is_file()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise SystemExit(
            "Demucs produced multiple no_vocals stems for one input; refusing to guess: "
            + ", ".join(str(path) for path in matches)
        )
    return None


def publish_track(job_outdir, stem, outdir, overwrite=False, input_audio=None):
    """Publish a complete track with no-clobber hard links and a final stem marker."""
    job_outdir = Path(job_outdir).resolve()
    stem = Path(stem).resolve()
    outdir = Path(outdir).resolve()
    try:
        relative_track = stem.parent.relative_to(job_outdir)
    except ValueError as exc:
        raise SystemExit("Generated stem was outside the isolated separation output directory.") from exc

    source_track = stem.parent
    destination = outdir / relative_track
    resolved_parent = destination.parent.resolve()
    if resolved_parent != outdir and outdir not in resolved_parent.parents:
        raise SystemExit("Refusing to publish a generated track outside the separation output directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.resolve() == source_track.resolve():
        raise SystemExit("Generated and published track directories must be different.")
    if input_audio is not None:
        input_audio = Path(input_audio).resolve()
        resolved_destination = destination.resolve()
        if input_audio == resolved_destination or resolved_destination in input_audio.parents:
            raise SystemExit("Refusing to replace a destination directory that contains the source audio.")
    if source_track.is_symlink() or not source_track.is_dir():
        raise SystemExit(f"Generated track directory is missing or unsafe: {source_track}")
    generated_symlinks = [path for path in source_track.rglob("*") if path.is_symlink()]
    if generated_symlinks:
        raise SystemExit(f"Generated track contains a symbolic link: {generated_symlinks[0]}")
    if not stem.is_file() or stem.is_symlink():
        raise SystemExit(f"Generated no_vocals stem is missing or unsafe: {stem}")

    lock_path = destination.parent / f".{destination.name}.publish.lock"
    backup = None
    with _publication_lock(lock_path):
        if _lexists(destination):
            if not overwrite:
                raise SystemExit(
                    f"Refusing to overwrite an existing separated track: {destination}. "
                    "Pass --overwrite to replace it."
                )
            if destination.is_symlink() or not destination.is_dir():
                raise SystemExit(f"Refusing to replace a non-directory output path: {destination}")
            backup = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.bak")
            os.replace(destination, backup)

        created_files = []
        created_directories = []
        try:
            # mkdir is the portable atomic no-clobber reservation for a directory.
            # Publish no_vocals last so its presence marks a complete track tree.
            destination.mkdir()
            created_directories.append(destination)
            source_directories = sorted(
                (path for path in source_track.rglob("*") if path.is_dir()),
                key=lambda path: len(path.relative_to(source_track).parts),
            )
            for source_directory in source_directories:
                target_directory = destination / source_directory.relative_to(source_track)
                target_directory.mkdir()
                created_directories.append(target_directory)

            source_files = [path for path in source_track.rglob("*") if path.is_file()]
            source_files.sort(key=lambda path: (path == stem, str(path.relative_to(source_track))))
            for source_file in source_files:
                target_file = destination / source_file.relative_to(source_track)
                os.link(source_file, target_file)
                created_files.append((target_file, source_file))
        except BaseException as exc:
            rollback_errors = []
            for target_file, source_file in reversed(created_files):
                try:
                    if _lexists(target_file) and os.path.samefile(target_file, source_file):
                        target_file.unlink()
                except OSError as rollback_exc:
                    rollback_errors.append(f"could not remove {target_file}: {rollback_exc}")
            for target_directory in reversed(created_directories):
                try:
                    target_directory.rmdir()
                except FileNotFoundError:
                    pass
                except OSError as rollback_exc:
                    rollback_errors.append(f"could not remove {target_directory}: {rollback_exc}")
            if backup is not None and _lexists(backup):
                if not _lexists(destination):
                    try:
                        os.replace(backup, destination)
                    except OSError as rollback_exc:
                        rollback_errors.append(f"prior output retained at {backup}: {rollback_exc}")
                else:
                    rollback_errors.append(f"prior output retained at {backup}")
            detail = f" ({'; '.join(rollback_errors)})" if rollback_errors else ""
            if isinstance(exc, SystemExit):
                raise SystemExit(f"{exc}{detail}") from exc
            raise SystemExit(f"Failed to publish separated track directory: {exc}{detail}") from exc

        published_stem = destination / stem.name
        if not published_stem.is_file() or published_stem.is_symlink():
            raise SystemExit("Published track did not contain the generated no_vocals stem.")
        if backup is not None:
            try:
                shutil.rmtree(backup)
            except OSError as exc:
                print(
                    f"WARNING: Published track is complete, but prior-output cleanup failed: {exc}",
                    file=sys.stderr,
                )
        return published_stem


def ensure_demucs_available():
    if importlib.util.find_spec("demucs") is None:
        raise SystemExit(
            "Demucs is not installed in this Python environment. "
            "Install it in an isolated environment with: python -m pip install demucs"
        )


def ensure_audio_separator_available(executable=None):
    """Return an audio-separator 0.48.0 executable or fail before inference."""
    candidate = executable
    if candidate:
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_file():
            candidate = str(candidate_path.resolve())
        else:
            candidate = shutil.which(candidate)
    else:
        candidate = shutil.which("audio-separator")
    if not candidate:
        raise SystemExit(
            "audio-separator is not installed or is not on PATH. Install the pinned "
            "dependency with: python -m pip install -r scripts/requirements-audio-separator.txt"
        )

    try:
        completed = subprocess.run(
            [candidate, "--version"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"Could not verify audio-separator version: {exc}") from exc
    version_text = f"{completed.stdout}\n{completed.stderr}".strip()
    match = re.search(
        r"audio[- ]separator(?:\.exe)?(?:\s+version)?\s+v?(\d+\.\d+\.\d+)",
        version_text,
        flags=re.IGNORECASE,
    )
    if match is None and re.fullmatch(r"v?(\d+\.\d+\.\d+)", version_text):
        match = re.fullmatch(r"v?(\d+\.\d+\.\d+)", version_text)
    version = match.group(1) if match else None
    if version != AUDIO_SEPARATOR_VERSION:
        observed = version or version_text or "unreported"
        raise SystemExit(
            f"audio-separator {AUDIO_SEPARATOR_VERSION} is required; found {observed}. "
            "Use the pinned requirements file in an isolated environment."
        )
    return candidate


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_melband_model_files(model_dir):
    """Verify the registered checkpoint and config against the v0.48.0 manifest."""
    model_dir = Path(model_dir)
    expected = {
        MELBAND_MODEL_FILENAME: MELBAND_MODEL_SHA256,
        MELBAND_CONFIG_FILENAME: MELBAND_CONFIG_SHA256,
    }
    for filename, expected_hash in expected.items():
        path = model_dir / filename
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"audio-separator did not provide the pinned model file: {path}")
        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise SystemExit(
                f"Refusing unverified audio-separator model file {path}: "
                f"expected SHA-256 {expected_hash}, got {actual_hash}."
            )


def find_audio_separator_no_vocals(job_outdir, audio):
    expected = Path(job_outdir) / "audio-separator" / Path(audio).stem / "no_vocals.wav"
    if expected.is_file() and not expected.is_symlink():
        return expected
    return None


def validate_audio_separator_output(stem, input_audio):
    """Validate the WAV and, when readable, its resampled source frame count."""
    try:
        import soundfile
    except ImportError as exc:
        raise SystemExit(
            "The audio-separator environment is missing soundfile; reinstall the pinned requirements."
        ) from exc
    try:
        output_info = soundfile.info(str(stem))
    except (OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"Cannot inspect the generated no-vocals WAV: {exc}") from exc
    if str(output_info.format).upper() != "WAV":
        raise SystemExit(f"Generated no-vocals output is not WAV: {output_info.format}")
    if output_info.samplerate != 44100 or output_info.frames <= 0:
        raise SystemExit(
            "Generated no-vocals WAV has an invalid sample rate or no audio frames: "
            f"{output_info.samplerate} Hz, {output_info.frames} frames."
        )

    # libsndfile cannot inspect every accepted compressed input (notably some
    # M4A builds). When it can, require the separator's 44.1 kHz output to
    # preserve the decoded source duration to within 10 ms of resampling.
    try:
        input_info = soundfile.info(str(input_audio))
    except (OSError, RuntimeError, ValueError):
        return
    if input_info.samplerate <= 0 or input_info.frames <= 0:
        raise SystemExit("Input audio metadata has an invalid sample rate or frame count.")
    expected_frames = round(input_info.frames * 44100 / input_info.samplerate)
    tolerance_frames = 441
    if abs(output_info.frames - expected_frames) > tolerance_frames:
        raise SystemExit(
            "Generated no-vocals WAV duration does not match the input: "
            f"expected about {expected_frames} frames at 44100 Hz, got {output_info.frames}."
        )


def validate_model_rights(path, model, use_category):
    """Check an operator's model-use record, not the legal validity of its claims."""
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Cannot read model rights record: {exc}") from exc
    if not isinstance(record, dict):
        raise SystemExit("Model rights record must be a JSON object.")
    if record.get("model") != model:
        raise SystemExit("Model rights record does not match the selected model.")
    if record.get("use_category") != use_category:
        raise SystemExit("Model rights record does not match the intended use category.")
    for field in ("intended_use", "evidence"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise SystemExit(f"Model rights record needs a non-empty {field}.")
    if record.get("confirmed_by_operator") is not True:
        raise SystemExit("Model rights record must be confirmed by the operator.")
    basis = record.get("rights_basis")
    if basis == "scientific_purposes":
        if use_category != "scientific_research":
            raise SystemExit(
                "Scientific-purpose model terms do not establish permission for this use. "
                "Use separately permitted weights or a licensed instrumental."
            )
    elif basis not in ("separate_permission", "open_license"):
        raise SystemExit(
            "Model rights record needs scientific_purposes, separate_permission, "
            "or open_license rights_basis."
        )
    return record


def main():
    parser = argparse.ArgumentParser(description="Run a vetted vocal separator and print the no-vocals stem path.")
    parser.add_argument("audio", help="Input audio file, such as MP3, M4A, WAV, or FLAC.")
    parser.add_argument("--outdir", default="work/separated", help="Separation output directory.")
    parser.add_argument(
        "--backend", choices=("demucs", "audio-separator"), default="demucs",
        help="Separation backend. Demucs remains the default for backward compatibility.",
    )
    parser.add_argument(
        "--model", default=None,
        help="Demucs model name, or the fixed registered audio-separator model filename.",
    )
    parser.add_argument("--rights-record", required=True, help="JSON record of model-specific permission and intended use.")
    parser.add_argument(
        "--use-category", required=True,
        choices=("scientific_research", "personal", "publication", "commercial"),
        help="Actual intended use; scientific-purpose terms do not cover the other categories.",
    )
    parser.add_argument("--device", default=None, help="Optional Demucs device, such as cpu or cuda.")
    parser.add_argument(
        "--audio-separator", default=None,
        help="Optional path or command name for the pinned audio-separator executable.",
    )
    parser.add_argument(
        "--model-dir", default="work/models/audio-separator",
        help="External audio-separator model cache; keep it outside this skill package.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing complete track output.")
    args = parser.parse_args()

    audio = Path(args.audio)
    if not audio.is_file():
        raise SystemExit(f"Audio file not found: {audio}")

    model = args.model or ("htdemucs" if args.backend == "demucs" else MELBAND_MODEL_FILENAME)
    if args.backend == "audio-separator" and model != MELBAND_MODEL_FILENAME:
        raise SystemExit(
            f"The audio-separator backend is pinned to registered model {MELBAND_MODEL_FILENAME}."
        )
    if args.backend == "audio-separator" and args.device:
        raise SystemExit("--device applies only to Demucs; audio-separator 0.48.0 selects its runtime device.")
    if args.backend == "demucs" and args.audio_separator:
        raise SystemExit("--audio-separator applies only to the audio-separator backend.")

    # Rights validation deliberately precedes dependency checks, cache creation,
    # model download, and output creation.
    validate_model_rights(args.rights_record, model, args.use_category)
    separator_executable = None
    if args.backend == "demucs":
        ensure_demucs_available()
    else:
        separator_executable = ensure_audio_separator_available(args.audio_separator)

    outdir = Path(args.outdir).resolve()
    if outdir.exists() and not outdir.is_dir():
        raise SystemExit(f"Separation output path is not a directory: {outdir}")
    outdir.mkdir(parents=True, exist_ok=True)
    job_outdir = Path(tempfile.mkdtemp(prefix=f".{args.backend}-job-", dir=outdir))

    try:
        if args.backend == "demucs":
            cmd = [
                sys.executable,
                "-m",
                "demucs",
                "--two-stems",
                "vocals",
                "-n",
                model,
                "-o",
                str(job_outdir),
            ]
            if args.device:
                cmd.extend(["--device", args.device])
            cmd.append(str(audio))
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as exc:
                raise SystemExit(f"Demucs failed with exit code {exc.returncode}") from exc
            generated = find_no_vocals(job_outdir, model, audio)
        else:
            model_dir = Path(args.model_dir).resolve()
            if model_dir.exists() and not model_dir.is_dir():
                raise SystemExit(f"Model cache path is not a directory: {model_dir}")
            model_dir.mkdir(parents=True, exist_ok=True)
            track_dir = job_outdir / "audio-separator" / audio.stem
            track_dir.mkdir(parents=True)
            cmd = [
                separator_executable,
                str(audio.resolve()),
                "--model_filename", MELBAND_MODEL_FILENAME,
                "--model_file_dir", str(model_dir),
                "--output_dir", str(track_dir),
                "--output_format", "WAV",
                "--single_stem", MELBAND_NO_VOCALS_STEM,
                "--custom_output_names", json.dumps({MELBAND_NO_VOCALS_STEM: "no_vocals"}, separators=(",", ":")),
                "--normalization", "1.0",
                "--amplification", "0.0",
                "--sample_rate", "44100",
                "--use_soundfile",
            ]
            environment = os.environ.copy()
            environment["AUDIO_SEPARATOR_MODEL_DIR"] = str(model_dir)
            try:
                subprocess.run(cmd, check=True, env=environment)
            except subprocess.CalledProcessError as exc:
                raise SystemExit(f"audio-separator failed with exit code {exc.returncode}") from exc
            verify_melband_model_files(model_dir)
            generated = find_audio_separator_no_vocals(job_outdir, audio)
            if generated:
                validate_audio_separator_output(generated, audio)

        if not generated:
            raise SystemExit(f"Could not find the no_vocals stem produced under {job_outdir}")
        no_vocals = publish_track(job_outdir, generated, outdir, args.overwrite, audio)
    finally:
        shutil.rmtree(job_outdir, ignore_errors=True)

    print(no_vocals.resolve())


if __name__ == "__main__":
    main()
