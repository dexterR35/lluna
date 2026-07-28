#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$script_dir"

if [[ ! -x "$script_dir/midgardEnv/bin/python" ]]; then
  echo "Midgard environment is missing. Run ./install.sh first." >&2
  exit 2
fi

exec "$script_dir/midgardEnv/bin/python" midgard.py "$@"
