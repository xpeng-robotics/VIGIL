#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
MODE="${1:---check}"
if [[ $# -gt 0 ]]; then shift; fi
case "$MODE" in
  --check|--smoke) ;;
  -h|--help)
    echo 'Usage: bash scripts/deploy/quickstart.sh [--check | --smoke] [CLI options]'
    echo '--check installs test dependencies, runs tests and a dry-run (default).'
    echo '--smoke installs evaluation dependencies and runs one real episode; no developer tests.'
    echo 'Headless Linux smoke runs use CloudRendering unless VIGIL_THOR_PLATFORM is explicitly set.'
    echo 'VIGIL_SKIP_INSTALL=1 reuses an already prepared environment.'
    exit 0 ;;
  *) echo "Unknown mode: $MODE; use --check or --smoke." >&2; exit 2 ;;
esac
CONDA_BIN="${VIGIL_CONDA_EXE:-conda}"
ENV_NAME="${VIGIL_CONDA_ENV:-vigil-release}"
ENV_PREFIX="${VIGIL_CONDA_PREFIX:-}"
USE_CONDA="${VIGIL_USE_CONDA:-auto}"
INSTALL_SPEC="${VIGIL_INSTALL_SPEC:-.[dev]}"
if [[ "$MODE" == --smoke ]]; then INSTALL_SPEC="${VIGIL_INSTALL_SPEC:-.[thor]}"; fi

if [[ "$USE_CONDA" != 0 ]] && command -v "$CONDA_BIN" >/dev/null 2>&1; then
  if [[ -n "$ENV_PREFIX" ]]; then
    if [[ ! -x "$ENV_PREFIX/bin/python" ]]; then
      "$CONDA_BIN" create -y -p "$ENV_PREFIX" python=3.10 pip
    fi
    PY=("$CONDA_BIN" run --no-capture-output -p "$ENV_PREFIX" python)
  else
    if ! "$CONDA_BIN" env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
      "$CONDA_BIN" create -y -n "$ENV_NAME" python=3.10 pip
    fi
    PY=("$CONDA_BIN" run --no-capture-output -n "$ENV_NAME" python)
  fi
elif [[ "$USE_CONDA" == 1 ]]; then
  echo "Conda requested but unavailable: $CONDA_BIN. Set VIGIL_CONDA_EXE or VIGIL_USE_CONDA=0." >&2
  exit 2
else
  PY=("${PYTHON_BIN:-python3}")
  if ! "${PY[@]}" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
    echo 'Python 3.10+ is required. Set PYTHON_BIN to a suitable Python, or use Conda.' >&2
    exit 2
  fi
  if [[ "${VIGIL_SKIP_INSTALL:-0}" != 1 ]]; then
    VENV_DIR="${VIGIL_VENV_DIR:-$REPO_ROOT/.venv}"
    if [[ ! -x "$VENV_DIR/bin/python" ]]; then "${PY[@]}" -m venv "$VENV_DIR"; fi
    PY=("$VENV_DIR/bin/python")
  fi
fi
"${PY[@]}" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else "Python 3.10+ is required.")'
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
if [[ "${VIGIL_SKIP_INSTALL:-0}" != 1 ]]; then
  "${PY[@]}" -m pip install -e "$INSTALL_SPEC"
fi
if [[ "$MODE" == --smoke ]]; then
  if [[ "$(uname -s)" == Linux && -z "${DISPLAY:-}" && -z "${VIGIL_THOR_PLATFORM+x}" ]]; then
    export VIGIL_THOR_PLATFORM=cloud
    echo '[quickstart] No DISPLAY on Linux; using CloudRendering (requires a working Vulkan driver).'
  fi
  "${PY[@]}" -m vigil.cli smoke --pack-file "${VIGIL_PACK:-canonical}" --out-dir "${VIGIL_OUT_DIR:-outputs/smoke}" "$@"
else
  if ! "${PY[@]}" -c 'import pytest' >/dev/null 2>&1; then
    echo 'pytest is missing. Install with python -m pip install -e ".[dev]", or unset VIGIL_SKIP_INSTALL.' >&2
    exit 2
  fi
  "${PY[@]}" -m pytest -p no:cacheprovider
  "${PY[@]}" -m vigil.cli run-pack --pack-file "${VIGIL_PACK:-canonical}" --dry-run --out-dir "${VIGIL_OUT_DIR:-results/quickstart}" "$@"
  echo '[quickstart] Offline checks passed. No simulator or model was executed.'
  echo '[quickstart] Next: configure the model, then bash scripts/deploy/quickstart.sh --smoke'
fi
