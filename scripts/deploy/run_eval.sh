#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
OUT_DIR="${VIGIL_OUT_DIR:-outputs/eval}"
RUN_ARGS=(
  --pack-file "${VIGIL_PACK:-canonical}"
  --profile "${VIGIL_PROFILE:-pure_rgb_dialogue_history_baseline}"
  --out-dir "$OUT_DIR"
  --workers "${VIGIL_WORKERS:-1}"
  --max-auto-workers "${VIGIL_MAX_AUTO_WORKERS:-4}"
  --boot-concurrency "${VIGIL_BOOT_CONCURRENCY:-0}"
  --render-concurrency "${VIGIL_RENDER_CONCURRENCY:-0}"
  --episode-timeout-s "${VIGIL_EPISODE_TIMEOUT_S:-1800}"
  --max-steps "${VIGIL_MAX_STEPS:-0}"
  --start-index "${VIGIL_START_INDEX:-0}"
  --width "${VIGIL_WIDTH:-640}"
  --height "${VIGIL_HEIGHT:-480}"
)
for pair in "VIGIL_EPISODE_ROOT:episode-root" "VIGIL_SCENE_ROOT:scene-root" \
            "VIGIL_MAX_EPISODES:max-episodes" "VIGIL_PROMPT_POLICY_NAME:prompt-policy-name" \
            "VIGIL_PROMPT_POLICY_VERSION:prompt-policy-version"; do
  variable="${pair%%:*}"
  option="${pair#*:}"
  value="${!variable:-}"
  if [[ -n "$value" ]]; then RUN_ARGS+=("--$option" "$value"); fi
done
if [[ "${VIGIL_RESUME_EXISTING:-0}" == 1 ]]; then RUN_ARGS+=(--resume-existing); fi
if [[ "${VIGIL_NO_FRAMES:-0}" == 1 ]]; then RUN_ARGS+=(--no-frames); fi
if [[ "${VIGIL_RENDER_DEPTH:-0}" == 1 ]]; then RUN_ARGS+=(--render-depth); fi

# CLI arguments come last and override the operational environment defaults.
# Model settings are resolved by the Python CLI, including provider API keys.
for arg in "$@"; do
  if [[ "$arg" == --help || "$arg" == -h ]]; then
    exec "$PYTHON_BIN" -m vigil.cli run-pack --help
  fi
done
previous=""
for arg in "$@"; do
  if [[ "$previous" == --out-dir ]]; then OUT_DIR="$arg"; fi
  if [[ "$arg" == --out-dir=* ]]; then OUT_DIR="${arg#*=}"; fi
  previous="$arg"
done
mkdir -p "$OUT_DIR"
"$PYTHON_BIN" -m vigil.cli run-pack "${RUN_ARGS[@]}" "$@" 2>&1 | tee -a "$OUT_DIR/run_pack.log"
