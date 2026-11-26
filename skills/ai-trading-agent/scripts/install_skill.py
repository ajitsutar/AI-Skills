"""Optional personal installation; never overwrite an existing skill.

No authentication, dependency installation, configuration or scheduling is performed.
Not required for local examples. Destination must be explicitly supplied.
"""
import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from research_preflight import package_integrity


def install(source, destination, *, require_release=False):
    source, destination = Path(source).resolve(), Path(destination).expanduser().resolve()
    if destination == source or source in destination.parents or destination in source.parents:
        raise ValueError("Destination must be separate from the source package")
    if destination.exists():
        raise FileExistsError("Destination exists; preserve it and choose a new destination")
    verify = require_release or (source / "PACKAGE-MANIFEST.json").exists()
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "runtime", "*.db", "*.db-wal", "*.db-shm")
    if verify:
        baseline = package_integrity(source)
        if baseline["status"] != "VERIFIED":
            raise ValueError("Release integrity failed: " + ", ".join(baseline["errors"]))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".skill-install-", dir=destination.parent) as scratch:
            staged = Path(scratch) / "package"
            staged.mkdir()
            manifest_file = source / "PACKAGE-MANIFEST.json"
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            for name in [*manifest["files"], manifest_file.name]:
                target = staged / name
                if staged not in target.resolve().parents:
                    raise ValueError("Invalid release member")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target)
            if package_integrity(staged) != baseline:
                raise ValueError("Staged copy differs from the verified release")
            # POSIX rename can replace an empty directory; reserve its name exclusively.
            # Windows rename itself refuses an existing destination.
            if os.name == "nt":
                staged.rename(destination)
            else:
                destination.mkdir()
                reservation = destination.stat()
                try:
                    staged.rename(destination)
                except OSError:
                    if destination.exists() and os.path.samestat(reservation, destination.stat()):
                        destination.rmdir()
                    raise
    else:
        shutil.copytree(source, destination, ignore=ignore)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    print("Copied skill to", install(Path(__file__).resolve().parents[1], args.destination, require_release=True))
    print("No broker connection, live trading, or schedules were enabled.")


if __name__ == "__main__":
    main()
