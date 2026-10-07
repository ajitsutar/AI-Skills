"""Optional personal installation; never overwrite an existing skill.

No authentication, dependency installation, configuration or scheduling is performed.
Not required for local examples. Destination must be explicitly supplied.
"""
import argparse
import shutil
from pathlib import Path


def install(source, destination):
    source, destination = Path(source).resolve(), Path(destination).expanduser().resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Destination must be separate from the source package")
    if destination.exists():
        raise FileExistsError("Destination exists; preserve it and choose a new destination")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", ".venv", "runtime", "*.db", "*.db-wal", "*.db-shm"))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print("Copied skill to", install(Path(__file__).resolve().parents[1], args.destination))
    print("No broker connection, live trading, or schedules were enabled.")


if __name__ == "__main__":
    main()
