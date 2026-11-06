#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Explicit historical request profile; serving defaults must be recorded separately.
export VIGIL_TOP_K=""
export VIGIL_EXTRA_BODY_JSON=""
export VIGIL_PROTOCOL_RETRY_LIMIT=1
export VIGIL_OBSERVATION_ECHO_RETRY_LIMIT=2
export VIGIL_MODEL_REQUEST_MAX_RETRIES=3
export VIGIL_MODEL_REQUEST_RETRY_DELAY_S=2.0
bash "$REPO_ROOT/scripts/deploy/run_eval.sh" \
  --backend openai-compatible \
  --prompt-policy-name native_embodied_public_evidence \
  --prompt-policy-version 2026-04-18 \
  --max-tokens 4096 \
  --coord-mode normalized_1000 \
  --coord-prompt-mode none \
  --temperature 0.2 --top-p 0.9 \
  --supports-json-mode 0 --workers 100 --max-steps 0 \
  --timeout 180 --boot-concurrency 8 --render-concurrency 50 \
  "$@"
