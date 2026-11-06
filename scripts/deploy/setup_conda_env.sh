#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

CONDA_BIN="${VIGIL_CONDA_EXE:-conda}"
ENV_NAME="${VIGIL_CONDA_ENV:-vigil-release}"
ENV_PREFIX="${VIGIL_CONDA_PREFIX:-}"
INSTALL_SPEC="${VIGIL_INSTALL_SPEC:-.[dev,thor]}"

if ! command -v "$CONDA_BIN" >/dev/null 2>&1; then
  echo "[setup] ERROR: conda is not available: $CONDA_BIN" >&2
  echo "[setup] Set VIGIL_CONDA_EXE=/path/to/conda or install Miniconda/Miniforge first." >&2
  exit 2
fi

if [[ -n "$ENV_PREFIX" ]]; then
  if [[ ! -x "$ENV_PREFIX/bin/python" ]]; then
    "$CONDA_BIN" create -y -p "$ENV_PREFIX" python=3.10 pip
  fi
  CONDA_RUN=("$CONDA_BIN" run -p "$ENV_PREFIX")
  ENV_LABEL="$ENV_PREFIX"
else
  if ! "$CONDA_BIN" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    "$CONDA_BIN" create -y -n "$ENV_NAME" python=3.10 pip
  fi
  CONDA_RUN=("$CONDA_BIN" run -n "$ENV_NAME")
  ENV_LABEL="$ENV_NAME"
fi

"${CONDA_RUN[@]}" python -m pip install -e "$INSTALL_SPEC"
"${CONDA_RUN[@]}" python -m pytest
"${CONDA_RUN[@]}" python -m vigil.cli print-env

echo "[setup] OK: conda env ready: $ENV_LABEL"
