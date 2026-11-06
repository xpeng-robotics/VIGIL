[Documentation](../README.md) / Reference

# Usage

For a guided path, see [installation](../guides/INSTALLATION.md), [deployment](../guides/DEPLOYMENT.md),
[efficient evaluation](../guides/EVALUATION.md) and [trajectory analysis](../guides/TRACE_ANALYSIS.md).

## Offline run inspection

```bash
vigil progress /path/to/run
vigil verify-run /path/to/run --require-frames
vigil report /path/to/run
```

`progress` shows saved file counts for the latest selected IDs, without claiming
that those files are valid final results. `verify-run` rebuilds settlement from
steps and compares per-episode scores and the selected aggregate. It requires a
completed release-format pack run. Omit `--require-frames` for `--no-frames` runs.
Both inspection commands support `--json` and make no model or simulator calls.

## Visual Quickstart

From an extracted source release, `bash start.sh` opens the UI immediately with
Python 3.10+, without installing a package. It chooses an available port. Use the
following installation when you also want the `vigil` command in your environment.

```bash
python -m pip install -e .
vigil ui
```

The workbench opens in your browser. Explore the bundled real RGB example
without a model key or simulator. For your own evaluations, install `.[thor]`,
restart the workbench, then use **Run an evaluation** to save model settings,
check the environment and select tasks. Start with one episode.
**Results & replay** shows progress, W/B metrics and step-by-step visual evidence.
The [workbench guide](../guides/WORKBENCH.md) covers remote access, saved results and stopping runs.

## Inspect the task catalog

```bash
vigil catalog
vigil catalog --task-family SI --max-episodes 10
vigil catalog --json
```

This reads executable task definitions and reports family counts, examples,
budgets and scene references for the selected tasks. It requires the source
release data, but no configuration, model, simulator or GPU. Use `list-episodes`
for individual IDs. `catalog --episode-root PATH --pack-file FILE` supports an
explicit data location. An empty selection or missing task definition is an error.

## Environment Setup

Use Python 3.10+. The package supports offline listing, validation and scoring
without installing a simulator. Real episodes additionally need AI2-THOR:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[thor]"
```

For tests, add the `dev` extra: `python -m pip install -e ".[dev,thor]"`.
The core installation is `python -m pip install -e .`.

AI2-THOR requires a compatible Linux or macOS rendering environment. On Linux,
prepare either a working display/graphics driver or headless rendering:

```bash
export VIGIL_THOR_PLATFORM=cloud
vigil doctor --check-simulator
```

`cloud` selects AI2-THOR's `CloudRendering`; it does not provision a cloud server.
See the [upstream installation and headless setup](https://ai2thor.allenai.org/ithor/documentation/).
The first simulator launch may download runtime assets to `~/.ai2thor`.
The checked-in ProcTHOR house JSONs do not include that runtime. On Apple Silicon,
verify the installed runtime with the simulator check before a full run; an ARM
Python package import alone does not establish simulator compatibility.

Start with one worker. Hardware requirements depend on render resolution and
concurrency; this release has no measured minimum RAM/VRAM table. Increase workers
after a successful smoke run and observing memory use. A remote model endpoint
still needs local simulator rendering.

## Offline Check

```bash
python -m pip install -e ".[dev]"
python -m pytest
vigil validate-pack
vigil run --dry-run --max-episodes 3 --out-dir outputs/check-selection
```

These are contributor checks in your selected environment. No simulator or model
is called. Normal replay and evaluation do not require running the developer suite.

## Configure and Check a Model

```bash
vigil init --model YOUR_VISION_MODEL --base-url http://127.0.0.1:8000/v1
# Set VIGIL_API_KEY if your server requires authentication.
vigil doctor
vigil smoke
vigil run
```

`ui` opens the visual workbench; `smoke` runs one episode; `run` runs the canonical pack and is an alias of
`run-pack`. Results and W/B summaries are saved under `outputs/smoke` and
`outputs/eval` respectively. Running `vigil` with no arguments shows this workflow.

For an existing host with two renderer GPUs, `--workers 16 --render-concurrency 16
--boot-concurrency 4 --render-devices 0,1` assigns eight live renderer slots per
device. `--render-devices` requires positive `--episode-timeout-s`; it does not
provision hardware or configure the model server. See [concurrency controls](../guides/EVALUATION.md#understand-the-concurrency-controls).

`vigil.json` is automatically read from the current working directory. It contains
model settings only; task selection and execution settings remain CLI flags.
A minimal OpenAI-compatible configuration is:

```json
{
  "backend": "openai-compatible",
  "base_url": "http://127.0.0.1:8000/v1",
  "model": "your-model-name",
  "api_key": ""
}
```

For these endpoints, a server root or `/v1` is expanded to the chat-completions
path. A custom full endpoint is used unchanged. Leave `api_key` empty for an
unauthenticated local endpoint, or to fall back to the environment's key.

Use `vigil init --backend anthropic`, `--backend gemini` or `--backend openai`
for a native provider template; no URL is needed. An existing file is never
replaced. Use `vigil init models/another.json` to create another configuration,
then `vigil smoke --config models/another.json` to select it.

Settings resolve field by field in this order: **CLI > file > environment > defaults**.
`--no-config` disables file loading. A file selecting a native backend uses its
default URL unless the file or CLI supplies a URL, so an old shell endpoint does
not redirect it to another provider. Keys are not printed or stored in result
configuration files. The generated `vigil.json` is ignored by git.

Optional file settings include `temperature`, `top_p`, `top_k`, `max_tokens`,
`timeout`, `supports_json_mode` and `extra_body`. Use JSON `null` to omit a sampling
field, or `false` for `supports_json_mode` when the endpoint lacks JSON mode.

`extra_body` is for provider extensions such as `chat_template_kwargs` or Gemini
`generationConfig.thinkingConfig`. It cannot replace the model, messages, or
dedicated generation settings. All backends forward an explicitly configured
`top_k`; leave it null when the selected model does not support that parameter.
Gemini thought parts are recorded separately from the final action response.
Unknown settings and invalid types produce an error naming the field.

The OpenAI-compatible backend also accepts comma-separated replica URLs through
`VIGIL_MODEL_BASE_URLS`. Use `--no-config` and omit a single `--base-url` override
to retain the list. Replicas must serve the same model and generation setup.
Within a process, requests rotate through the list. Isolated pack workers offset
their starting replica by selected episode index, avoiding first-request traffic
concentrating on the first URL. This does not deploy replicas, provide failover,
enforce per-endpoint quotas or promise equal load across unrelated jobs.

The environment-only workflow remains available:

```bash
cp examples/config/.env.example .env
# Edit .env, then:
source .env
vigil smoke --no-config
```

OpenAI-compatible endpoints use `VIGIL_BACKEND`, `VIGIL_MODEL_BASE_URL`,
`VIGIL_MODEL_NAME` and optionally `VIGIL_API_KEY`. Native backends also accept
`GEMINI_API_KEY` / `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or `OPENAI_API_KEY`.
When using only environment variables, clear a previous endpoint when switching
providers. An explicit `--base-url` replaces the `VIGIL_MODEL_BASE_URLS` pool.

`doctor` checks the Python version, simulator package, all executable episode/scene
files, output writability and model configuration. Static checks do not guarantee
runtime or endpoint readiness. Additional probes are explicit:

```bash
vigil doctor --check-simulator  # starts a scene and checks RGB
vigil doctor --check-model      # sends a text request; uses API quota
vigil doctor --json             # machine-readable static checks
```

## First Real Episode

```bash
vigil smoke --out-dir outputs/first-run
vigil report outputs/first-run
```

Install `.[thor]` and configure your model before invoking this command.
`smoke` runs one canonical episode by default through the same runner and scorer
as `run-pack`. Task failure is a valid result; infrastructure or model request
errors produce a nonzero exit. This verifies the complete RGB/model/action loop.

Without a model, exercise the simulator with scripted actions:

```bash
vigil smoke --script-actions '[{"skill_name":"report","arguments":{"status":"fail","summary":"scripted stop"}}]' --out-dir outputs/scripted
```

## Data and Selection

The canonical pack is the default, equivalent to `--pack-file canonical`.
The CLI locates data from the current checkout or the source/editable installation.
For a wheel installed separately, point `VIGIL_DATA_ROOT` at the release's `data/`
directory. Data is not bundled in the wheel or downloaded automatically.
Explicit `--pack-file`, `--episode-root` and `--scene-root` paths remain supported.

```bash
vigil validate-pack
vigil list-profiles
vigil list-episodes --max-episodes 10
vigil list-episodes --task-family SV --json
vigil run-pack --dry-run --max-episodes 3 --out-dir results/dryrun
```

Repeat `--task-family` or `--difficulty` to include several values. Index/limit
selection applies after filtering, for both real and dry-runs. A dry-run only
checks manifest/profile/selection wiring; use `doctor` for executable assets.

## Full Run and Resume

```bash
vigil run-pack --workers 4 --out-dir outputs/full
vigil run-pack --workers 4 --out-dir outputs/full --resume-existing
```

The default is one worker. `--workers 0` chooses at most four workers and the CPU
count; change that cap explicitly with `--max-auto-workers`. Render concurrency
is separately bounded. The default `--episode-timeout-s 1800` bounds each episode
in a subprocess, including startup and model calls but excluding slot wait time.
Use `0` explicitly for in-process execution without that wall-time bound.

`run_config.json` records model settings without the API key, profile and code/data
fingerprints. Resuming requires the same experiment settings; a changed model,
prompt, data or runtime code requires a new output directory. Only consistent
trace/score pairs are skipped. Invalid pairs and infrastructure failures are rerun.
Legacy directories without this manifest can be rescored but cannot be resumed.
Changing task selection or worker count is allowed; the latest aggregate covers
only the latest selection. Changing an API key does not invalidate results.

The endpoint helper uses the same CLI configuration:

```bash
bash scripts/deploy/run_eval.sh --max-episodes 3 --out-dir outputs/small
bash scripts/deploy/run_vllm_local.sh --model-path /path/to/model --model-name my-vlm -- --max-episodes 3 --out-dir outputs/local
```

## Results

```text
outputs/full/
  run_config.json
  model_config.json
  aggregate_score.json
  summary.txt
  episode_logs/
  frames/<episode_id>/step_*.png
  traces/<episode_id>.json
  scores/<episode_id>.score.json
```

`--no-frames` uses temporary images and removes them at episode completion; RGB
input to the model is preserved. Keep frames for visual review. Episode logs are
written for subprocess execution. Summaries report final world completion W and
report-dependent benchmark success B; neither is the legacy composite score.

```bash
vigil report outputs/full
vigil score-trace outputs/full/traces/<episode_id>.json
vigil score-traces outputs/full/traces --out results/aggregate_score.json
```

`run_status.json` records the latest selected episode IDs. Reports reject an
unfinished run, a missing status file or infrastructure errors, even if an older
aggregate remains in the directory. A standalone aggregate outside a run is
labeled **UNVERIFIED stored summary**; valid counts and rates do not prove trace
consistency or full coverage. Only one pack process can write a directory
at a time. Standalone `run-episode` also exits nonzero on simulator/API failures.

Directory-based `score-traces` uses the recorded selection when a run status is
present; otherwise it discovers trace files beneath the directory. See
[SCORING.md](SCORING.md) for metric definitions and [MODEL_EVAL.md](../guides/MODEL_EVAL.md)
for the model/action contract.
