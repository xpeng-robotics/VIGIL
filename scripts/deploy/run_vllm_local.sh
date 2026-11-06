#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

MODEL_PATH="${MODEL_PATH:-}"
MODEL_NAME="${VIGIL_MODEL_NAME:-}"
HOST="${VLLM_HOST:-127.0.0.1}"
PORT="${VLLM_PORT:-8000}"
API_KEY="${VIGIL_API_KEY:-local-token}"
DTYPE="${VLLM_DTYPE:-auto}"
MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-8192}"
GPU_MEMORY_UTILIZATION="${VLLM_GPU_MEMORY_UTILIZATION:-0.85}"
TENSOR_PARALLEL_SIZE="${VLLM_TENSOR_PARALLEL_SIZE:-1}"
CUDA_DEVICES="${CUDA_VISIBLE_DEVICES:-}"
WAIT_SECONDS="${VLLM_WAIT_SECONDS:-600}"
SHUTDOWN_TIMEOUT_SECONDS="${VLLM_SHUTDOWN_TIMEOUT_SECONDS:-30}"
VLLM_LOG="${VLLM_LOG:-outputs/vllm.log}"
VLLM_EXTRA_ARGS=()
RUN_EVAL_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  bash scripts/deploy/run_vllm_local.sh --model-path PATH_OR_HF_REPO [vLLM options] -- [run_eval options]

Starts a local vLLM OpenAI-compatible server, waits for readiness, then runs scripts/deploy/run_eval.sh.

vLLM options:
  --model-path PATH          Local model path or Hugging Face repo id
  --model-name NAME          Served model name; default: basename of model path/repo
  --host HOST                vLLM host, default: 127.0.0.1
  --port PORT                vLLM port, default: 8000
  --api-key KEY              Local API key, default: local-token
  --dtype DTYPE              vLLM dtype, default: auto
  --max-model-len N          vLLM max model length, default: 8192
  --gpu-memory-utilization F vLLM GPU memory fraction, default: 0.85
  --tensor-parallel-size N   vLLM tensor parallel size, default: 1
  --cuda-visible-devices CSV CUDA device list for this server
  --vllm-arg ARG             Extra single vLLM argument; repeat as needed
  --wait-seconds N           Readiness timeout, default: 600
  VLLM_SHUTDOWN_TIMEOUT_SECONDS
                             Graceful shutdown timeout before SIGKILL, default: 30
  --vllm-log PATH            vLLM log path, default: outputs/vllm.log

Examples:
  bash scripts/deploy/run_vllm_local.sh --model-path /path/to/model --model-name my-vlm -- --max-episodes 10 --out-dir outputs/smoke
  CUDA_VISIBLE_DEVICES=0,1,2,3 bash scripts/deploy/run_vllm_local.sh --model-path Qwen/Qwen2.5-VL-7B-Instruct --tensor-parallel-size 4 -- --max-episodes 10
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model-path) MODEL_PATH="$2"; shift 2 ;;
    --model-name) MODEL_NAME="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --api-key) API_KEY="$2"; shift 2 ;;
    --dtype) DTYPE="$2"; shift 2 ;;
    --max-model-len) MAX_MODEL_LEN="$2"; shift 2 ;;
    --gpu-memory-utilization) GPU_MEMORY_UTILIZATION="$2"; shift 2 ;;
    --tensor-parallel-size) TENSOR_PARALLEL_SIZE="$2"; shift 2 ;;
    --cuda-visible-devices) CUDA_DEVICES="$2"; shift 2 ;;
    --vllm-arg) VLLM_EXTRA_ARGS+=("$2"); shift 2 ;;
    --wait-seconds) WAIT_SECONDS="$2"; shift 2 ;;
    --vllm-log) VLLM_LOG="$2"; shift 2 ;;
    --) shift; RUN_EVAL_ARGS+=("$@"); break ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[run_vllm_local] unknown vLLM argument: $1" >&2; echo "[run_vllm_local] Put evaluation arguments after --." >&2; usage >&2; exit 2 ;;
  esac
done

if [[ -z "$MODEL_PATH" ]]; then
  echo "[run_vllm_local] --model-path or MODEL_PATH is required." >&2
  exit 2
fi
if [[ -z "$MODEL_NAME" ]]; then
  trimmed="${MODEL_PATH%/}"
  MODEL_NAME="${trimmed##*/}"
fi
if [[ -z "$MODEL_NAME" ]]; then
  echo "[run_vllm_local] --model-name is required when the model path has no basename." >&2
  exit 2
fi
case "$SHUTDOWN_TIMEOUT_SECONDS" in
  ''|*[!0-9]*)
    echo "[run_vllm_local] VLLM_SHUTDOWN_TIMEOUT_SECONDS must be a non-negative integer." >&2
    exit 2
    ;;
esac
if ! command -v vllm >/dev/null 2>&1; then
  echo "[run_vllm_local] vllm CLI not found. Install vLLM in the active environment first." >&2
  exit 2
fi

mkdir -p "$(dirname "$VLLM_LOG")"

VLLM_CMD=(
  vllm serve "$MODEL_PATH"
  --host "$HOST"
  --port "$PORT"
  --api-key "$API_KEY"
  --served-model-name "$MODEL_NAME"
  --dtype "$DTYPE"
  --max-model-len "$MAX_MODEL_LEN"
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION"
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"
)
VLLM_CMD+=("${VLLM_EXTRA_ARGS[@]}")

vllm_is_alive() {
  if [[ -n "${VLLM_PGID:-}" ]] && kill -0 -- "-$VLLM_PGID" 2>/dev/null; then
    return 0
  fi
  [[ -n "${VLLM_PID:-}" ]] && kill -0 "$VLLM_PID" 2>/dev/null
}

signal_vllm() {
  local signal="$1"
  if [[ -n "${VLLM_PGID:-}" ]]; then
    kill "-$signal" -- "-$VLLM_PGID" 2>/dev/null || true
  elif [[ -n "${VLLM_PID:-}" ]]; then
    kill "-$signal" "$VLLM_PID" 2>/dev/null || true
  fi
}

wait_for_vllm_exit() {
  local deadline=$((SECONDS + SHUTDOWN_TIMEOUT_SECONDS))
  while vllm_is_alive; do
    if (( SECONDS >= deadline )); then
      return 1
    fi
    sleep 1
  done
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if vllm_is_alive; then
    echo "[vllm] stopping pid=$VLLM_PID"
    signal_vllm TERM
    if ! wait_for_vllm_exit; then
      echo "[vllm] pid=$VLLM_PID did not stop after ${SHUTDOWN_TIMEOUT_SECONDS}s; sending SIGKILL"
      signal_vllm KILL
    fi
    wait "$VLLM_PID" 2>/dev/null || true
  fi
  exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "[vllm] starting model=$MODEL_NAME host=$HOST port=$PORT tp=$TENSOR_PARALLEL_SIZE"
echo "[vllm] log: $VLLM_LOG"
VLLM_PGID=""
if [[ -n "$CUDA_DEVICES" ]]; then
  if command -v setsid >/dev/null 2>&1; then
    CUDA_VISIBLE_DEVICES="$CUDA_DEVICES" setsid "${VLLM_CMD[@]}" >"$VLLM_LOG" 2>&1 &
    VLLM_PGID=$!
  else
    CUDA_VISIBLE_DEVICES="$CUDA_DEVICES" "${VLLM_CMD[@]}" >"$VLLM_LOG" 2>&1 &
  fi
else
  if command -v setsid >/dev/null 2>&1; then
    setsid "${VLLM_CMD[@]}" >"$VLLM_LOG" 2>&1 &
    VLLM_PGID=$!
  else
    "${VLLM_CMD[@]}" >"$VLLM_LOG" 2>&1 &
  fi
fi
VLLM_PID=$!
echo "[vllm] pid=$VLLM_PID; waiting for readiness"

wait_for_vllm() {
  local deadline=$((SECONDS + WAIT_SECONDS))
  while (( SECONDS < deadline )); do
    if ! kill -0 "$VLLM_PID" 2>/dev/null; then
      echo "[vllm] server exited before readiness. Last log lines:" >&2
      tail -80 "$VLLM_LOG" >&2 || true
      return 1
    fi
    if python3 - "$HOST" "$PORT" "$API_KEY" <<'PY' >/dev/null 2>&1
import json
import sys
import urllib.request

host, port, api_key = sys.argv[1], sys.argv[2], sys.argv[3]
request = urllib.request.Request(f"http://{host}:{port}/v1/models")
if api_key:
    request.add_header("Authorization", f"Bearer {api_key}")
with urllib.request.urlopen(request, timeout=5) as response:
    payload = json.loads(response.read().decode("utf-8"))
if not isinstance(payload, dict):
    raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 2
  done
  echo "[vllm] readiness timed out after ${WAIT_SECONDS}s. Last log lines:" >&2
  tail -80 "$VLLM_LOG" >&2 || true
  return 1
}

wait_for_vllm

echo "[vllm] ready"
BASE_URL="http://${HOST}:${PORT}/v1/chat/completions"
bash "$REPO_ROOT/scripts/deploy/run_eval.sh" \
  --backend openai-compatible \
  --base-url "$BASE_URL" \
  --model "$MODEL_NAME" \
  --api-key "$API_KEY" \
  --supports-json-mode 0 \
  "${RUN_EVAL_ARGS[@]}"
