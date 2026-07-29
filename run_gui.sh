#!/usr/bin/env bash
set -euo pipefail

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$script_dir"

if [[ ! -x "$script_dir/midgardEnv/bin/python" ]]; then
  echo "Midgard environment is missing. Run ./install.sh first." >&2
  exit 2
fi

if ! "$script_dir/midgardEnv/bin/python" -c \
  "import struct,sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) and struct.calcsize('P') * 8 == 64 else 1)"
then
  echo "Midgard requires a 64-bit Python 3.12 environment. Run ./install.sh to repair it." >&2
  exit 3
fi

exec "$script_dir/midgardEnv/bin/python" midgard.py "$@"
