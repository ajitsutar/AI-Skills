#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Optional personal installation. No default destination, overwrite or auth.
python3 "$SOURCE_DIR/scripts/install_skill.py" "$@"
