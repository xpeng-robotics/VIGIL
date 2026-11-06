#!/usr/bin/env bash
# Open the source-release workbench with Python's standard library.
set -euo pipefail
RELEASE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$RELEASE_ROOT"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  VIGIL_PYTHON="$PYTHON_BIN"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  VIGIL_PYTHON="$VIRTUAL_ENV/bin/python"
elif [[ -x "$RELEASE_ROOT/.venv/bin/python" ]]; then
  VIGIL_PYTHON="$RELEASE_ROOT/.venv/bin/python"
else
  VIGIL_PYTHON=""
  for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      VIGIL_PYTHON="$candidate"
      break
    fi
  done
fi
if ! command -v "$VIGIL_PYTHON" >/dev/null 2>&1; then
  echo 'Python 3.10+ is required. Install it, or set PYTHON_BIN=/path/to/python.' >&2
  exit 2
fi
if ! "$VIGIL_PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo 'Python 3.10+ is required. Set PYTHON_BIN to the interpreter you want to use.' >&2
  exit 2
fi
export PYTHONPATH="$RELEASE_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$VIGIL_PYTHON" -u -m vigil.cli ui --port 0 "$@"
