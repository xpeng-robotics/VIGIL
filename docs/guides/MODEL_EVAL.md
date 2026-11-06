[Documentation](../README.md) / Guides

# Connect a model

VIGIL sends the task instruction, current RGB frame and episode-local history to
your model, then executes one JSON action. Choose a vision-capable endpoint and
verify one complete episode before increasing the workload.

Install evaluation support first: `python -m pip install -e ".[thor]"`.
Use [installation](INSTALLATION.md) if you still need an environment or simulator.

## Configure an endpoint

Create a configuration directly, then check it before running one episode:

```bash
vigil init --model YOUR_VISION_MODEL --base-url http://127.0.0.1:8000/v1
vigil doctor
vigil smoke --out-dir outputs/first-run
```

Replace the endpoint and model identifier. Set `VIGIL_API_KEY` or the provider's
key environment variable if authentication is required. `init` never reads a
key from the environment into the file and never replaces an existing config.
Without `--model`, `vigil init` still creates an editable template. Native
providers can omit `--base-url`, for example `vigil init --backend gemini --model YOUR_MODEL`.
See [configuration files](../reference/USAGE.md#configure-and-check-a-model) for native-provider templates.

New configurations default to temperature **0.6**, top-p **0.9** and **4096**
output tokens across the CLI, UI and all providers. Existing explicit settings
remain authoritative. These defaults changed on 2026-11-04; they are not a
paper-reproduction preset. To retain the earlier Qwen experiment's sampling,
specify `--temperature 0.2 --top-p 0.9 --max-tokens 4096` together with its
recorded data, prompt policy, coordinates, retry settings and runtime.
Changed experimental conditions require a new output directory.

Alternatively, set environment variables and use `--no-config` if a local file exists.
OpenAI-compatible endpoints include OpenAI Chat Completions, vLLM, and LiteLLM:

```bash
export VIGIL_BACKEND="openai-compatible"
export VIGIL_MODEL_BASE_URL="https://your-endpoint.example/v1/chat/completions"
export VIGIL_MODEL_NAME="your-model-name"
export VIGIL_API_KEY="..."
```

Official provider examples:

```bash
export VIGIL_BACKEND="gemini"
export VIGIL_MODEL_NAME="your-gemini-model"
export GEMINI_API_KEY="..."

export VIGIL_BACKEND="anthropic"
export VIGIL_MODEL_NAME="your-anthropic-model"
export ANTHROPIC_API_KEY="..."
```

The runner sends text plus the current RGB frame. OpenAI-compatible endpoints receive an `image_url` data URL; Gemini and Anthropic use their native image content formats.

For endpoints that do not reliably support OpenAI `response_format={"type":"json_object"}`, set `VIGIL_SUPPORTS_JSON_MODE=0`. The local vLLM helper does this by default.

## Use environment settings

```bash
vigil run --no-config \
  --max-episodes 10 \
  --out-dir outputs/smoke
```

Remove `--max-episodes` for the full canonical 1000-episode run.
Use `--workers N` to run multiple episodes concurrently within one job:

```bash
vigil run --no-config \
  --workers 8 \
  --out-dir outputs/eval
```

## Serve a model with vLLM

```bash
bash scripts/deploy/run_vllm_local.sh \
  --model-path /path/to/model \
  --model-name my-vlm \
  --tensor-parallel-size 1 \
  -- \
  --max-episodes 10 \
  --out-dir outputs/vllm-smoke
```

The arguments before `--` configure vLLM. Arguments after `--` are forwarded to `scripts/deploy/run_eval.sh`.

For multi-GPU local serving:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 bash scripts/deploy/run_vllm_local.sh \
  --model-path /path/to/model \
  --model-name my-vlm \
  --tensor-parallel-size 4 \
  -- \
  --max-episodes 10 \
  --out-dir outputs/vllm-smoke
```

## Run one episode

```bash
vigil run-episode \
  ithor_fp1_s1_pixel_grounding_easy_fridge_ground_001 \
  --episode-root data/episodes \
  --scene-root data/scenes \
  --out-dir outputs/eval
```

Equivalent explicit endpoint form:

```bash
vigil run-episode \
  ithor_fp1_s1_pixel_grounding_easy_fridge_ground_001 \
  --backend openai-compatible \
  --base-url "$VIGIL_MODEL_BASE_URL" \
  --model "$VIGIL_MODEL_NAME" \
  --coord-mode normalized_1000 \
  --coord-prompt-mode explicit \
  --out-dir outputs/eval
```

Outputs:

```text
outputs/eval/
  frames/<episode_id>/step_*.png
  traces/<episode_id>.json
  scores/<episode_id>.score.json
```

Use a fresh output directory. A direct `run-episode` refuses existing rollout
evidence and does not create pack status or an aggregate. Prefer `smoke` for one
canonical task with the complete run/verification workflow; use `run` for batches.

## Deterministic scripted run

For exercising the simulator without a model endpoint:

```bash
vigil run-episode \
  ithor_fp1_s1_pixel_grounding_easy_fridge_ground_001 \
  --script-actions '[{"skill_name":"report","arguments":{"status":"fail","summary":"scripted stop"}}]' \
  --out-dir outputs/scripted
```

This still requires AI2-THOR because it starts the simulator. ProcTHOR episodes additionally require `data/scenes/<scene_ref>/house.json`, which is included for the canonical 1000 pack.

## Run the full pack

```bash
vigil run-pack \
  --pack-file data/benchmark/packs/mixed_mainline_manual_revised_1000_v2.json \
  --episode-root data/episodes \
  --scene-root data/scenes \
  --workers 8 \
  --out-dir outputs/eval
```

Use `--max-episodes N` for a short smoke subset before launching the full 1000 episodes.

## Aggregate results

```bash
vigil score-traces outputs/eval/traces --out results/aggregate_score.json
```

## Action contract

Models must return exactly one JSON object:

```json
{"skill_name": "navigate", "arguments": {"mode": "turn_left", "magnitude": 30}}
```

Supported VIGIL-native skills:

- `navigate`: required `mode` in `forward`, `backward`, `turn_left`, `turn_right`; required `magnitude`. For forward/backward, `magnitude` is a positive integer step count. For turns, it is degrees.
- `look`: required `direction` in `up`, `down`; required `magnitude` in degrees.
- `interact_pixel`: required `intent`; required `x` and `y` unless `intent` is `drop`. Use `ground` for click/tap/point/locate requests that only ask the model to indicate a visible target without changing world state.
- `report`: required `status` in `success`, `fail`, `unsafe`, `invalid`, `on`, `off`, `open`, `closed`; required short `summary`.

## Output retention and resume

`--no-frames` removes temporary PNGs after the episode while preserving RGB model
input. It does not enable a text-only benchmark. For visual review, retain frames.

Pack runs default to one worker and a 1800-second subprocess timeout. Set
`--workers N` for your available resources; `--episode-timeout-s 0` explicitly
opts into in-process execution without the episode wall-time bound.
The configured timeout includes simulator startup and model calls, but excludes
waiting for a worker/render slot. Changing it requires a new output directory.

Use `--resume-existing` with the original experiment configuration. Only matching,
parseable trace/score pairs whose scores agree with recomputation are skipped.
Simulator/model request errors are retried on resume. A different model, prompt,
code version or executable data requires a fresh output directory. Runs produced
before `run_config.json` was introduced can still be scored, but cannot be resumed.
Task selection and worker count may change between resumes of the same experiment;
the aggregate and summary describe only the episodes selected by the latest command.

`vigil report outputs/eval` displays W/B and diagnostics. A standalone
`score-traces outputs/eval/traces` follows `run_status.json` when present and
requires the selection to be complete. Without status it discovers trace files.
Use explicit file paths for a different subset, and a new `--out` to preserve
the original evidence. Offline scoring makes no model requests.

Next: [run and verify an evaluation](EVALUATION.md), or use [deployment](DEPLOYMENT.md) for another simulation host.
