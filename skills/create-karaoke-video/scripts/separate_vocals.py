#!/usr/bin/env python
import argparse
import subprocess
import sys
from pathlib import Path


def find_no_vocals(outdir, model, audio):
    expected = Path(outdir) / model / Path(audio).stem / "no_vocals.wav"
    if expected.exists():
        return expected
    matches = sorted(Path(outdir).rglob("no_vocals.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def main():
    parser = argparse.ArgumentParser(description="Run Demucs vocal separation and print the no-vocals stem path.")
    parser.add_argument("audio", help="Input audio file, such as MP3, M4A, WAV, or FLAC.")
    parser.add_argument("--outdir", default="work/separated", help="Separation output directory.")
    parser.add_argument("--model", default="htdemucs", help="Demucs model name.")
    parser.add_argument("--device", default=None, help="Optional Demucs device, such as cpu or cuda.")
    args = parser.parse_args()

    audio = Path(args.audio)
    if not audio.exists():
        raise SystemExit(f"Audio file not found: {audio}")

    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems",
        "vocals",
        "-n",
        args.model,
        "-o",
        args.outdir,
    ]
    if args.device:
        cmd.extend(["--device", args.device])
    cmd.append(str(audio))

    try:
        subprocess.run(cmd, check=True)
    except ModuleNotFoundError:
        raise SystemExit("Demucs is not installed. Install it with: python -m pip install demucs")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Demucs failed with exit code {exc.returncode}")

    no_vocals = find_no_vocals(args.outdir, args.model, audio)
    if not no_vocals:
        raise SystemExit(f"Could not find no_vocals stem under {args.outdir}")

    print(no_vocals.resolve())


if __name__ == "__main__":
    main()
