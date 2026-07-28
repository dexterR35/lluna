#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$script_dir"

if command -v python3.12 >/dev/null 2>&1; then
  python_cmd="python3.12"
elif command -v python >/dev/null 2>&1; then
  python_cmd="python"
else
  echo "Python 3.12 was not found. Install 64-bit Python 3.12 and retry." >&2
  exit 2
fi

"$python_cmd" install.py "$@"
