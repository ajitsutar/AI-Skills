#!/usr/bin/env python
import argparse
import contextlib
import importlib.util
import os
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
        raise SystemExit("Generated stem was outside the isolated Demucs output directory.") from exc

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


def main():
    parser = argparse.ArgumentParser(description="Run Demucs vocal separation and print the no-vocals stem path.")
    parser.add_argument("audio", help="Input audio file, such as MP3, M4A, WAV, or FLAC.")
    parser.add_argument("--outdir", default="work/separated", help="Separation output directory.")
    parser.add_argument("--model", default="htdemucs", help="Demucs model name.")
    parser.add_argument("--device", default=None, help="Optional Demucs device, such as cpu or cuda.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing complete track output.")
    args = parser.parse_args()

    audio = Path(args.audio)
    if not audio.is_file():
        raise SystemExit(f"Audio file not found: {audio}")

    ensure_demucs_available()
    outdir = Path(args.outdir).resolve()
    if outdir.exists() and not outdir.is_dir():
        raise SystemExit(f"Separation output path is not a directory: {outdir}")
    outdir.mkdir(parents=True, exist_ok=True)
    job_outdir = Path(tempfile.mkdtemp(prefix=".demucs-job-", dir=outdir))

    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems",
        "vocals",
        "-n",
        args.model,
        "-o",
        str(job_outdir),
    ]
    if args.device:
        cmd.extend(["--device", args.device])
    cmd.append(str(audio))

    try:
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            raise SystemExit(f"Demucs failed with exit code {exc.returncode}") from exc

        generated = find_no_vocals(job_outdir, args.model, audio)
        if not generated:
            raise SystemExit(f"Could not find the no_vocals stem produced under {job_outdir}")
        no_vocals = publish_track(job_outdir, generated, outdir, args.overwrite, audio)
    finally:
        shutil.rmtree(job_outdir, ignore_errors=True)

    print(no_vocals.resolve())


if __name__ == "__main__":
    main()
