[Documentation](../README.md) / Guides

# Run an evaluation

Start with one complete episode, inspect its evidence, then increase the selection.
Before you begin, [install evaluation support](INSTALLATION.md) and
[connect your model](MODEL_EVAL.md). The commands below assume that setup is complete.

## Verify the first episode

Configure the model through `vigil ui` or `vigil init`. First verify one real task:

```bash
vigil doctor
vigil smoke --out-dir outputs/model-smoke
vigil verify-run outputs/model-smoke --require-frames
vigil ui --results-dir outputs/model-smoke
```

A valid task failure still demonstrates an executed evaluation. An API request
failure or simulator failure does not. Inspect both W/B and the failure reason.
The first canonical task is only a connection/action smoke test; it is not a
representative estimate of all eight task families.

Inspect the selection before spending API quota:

```bash
vigil list-episodes --max-episodes 10
vigil list-episodes --task-family SV --json
vigil run --dry-run --max-episodes 8 --out-dir outputs/selection-check
```

`--task-family` accepts PG, DA, VS, SV, AI, SI, SM and CR (case-insensitive),
as well as the original stored IDs. These are selection aliases; episode IDs and
scoring groups are unchanged. `--task-family` and `--difficulty` are repeatable. `--start-index` is zero-based
within the filtered selection; `--max-episodes` then limits its length. The first
eight rows are not automatically one episode per family. Use the UI to select
an intended diagnostic subset, and retain its IDs with the result.

## Understand the concurrency controls

| Setting | Meaning | Default |
| --- | --- | --- |
| `--workers` | Concurrent episode workers | 1; 0 chooses up to CPU count and the auto cap |
| `--max-auto-workers` | Cap when workers is 0 | 4 |
| `--boot-concurrency` | Simultaneous simulator starts | 0 resolves to `min(8, workers)` |
| `--render-concurrency` | Simultaneously live renderer processes | 0 resolves to `min(4, workers)` |
| `--render-devices` | Comma-separated renderer device IDs; split render slots across those devices | Unset; keep simulator/environment device selection |
| `--episode-timeout-s` | Per-episode process wall-time limit, including startup and API calls | 1800; 0 disables process isolation/time limit |
| `--timeout` | Timeout for a model request | 120 seconds |

The maximum active episodes is `min(selected tasks remaining, workers, render
concurrency)`. Each episode makes at most one model request at a time, so its API
request concurrency has the same upper bound. For example, `--workers 16` alone
still defaults to at most **4** active simulators/requests. To use eight, explicitly
set `--workers 8 --render-concurrency 8` after checking capacity. In the workbench,
open **Concurrency and API capacity** to set the startup/render limits and see
the effective upper bound. Its controls allow up to 16; larger jobs use the CLI.

There is no independent `--api-concurrency` or requests/tokens-per-minute limiter.
To cap this run at two simultaneous API requests, use `--workers 2` (or cap its
renderers at two). Other runs and machines have their own limits; use your API
gateway for a shared quota. API retries are sequential: the default two transport
retries mean up to three requests per model turn, without increasing simultaneous
requests. `--timeout` applies per HTTP attempt; the episode timeout includes
retries and their delays. Model protocol corrections are separate, disabled by
default, and change the experimental contract when enabled.

`--workers` is not a GPU count. Renderer slots can cap effective concurrency even
when more workers are requested. Increase workers after checking API quota,
renderer memory and CPU load. Increase renderer limits explicitly only when the
host supports them. Start-up concurrency can remain lower to avoid simultaneous
Unity launch spikes. A capacity example, after the smoke check:

```bash
vigil run --max-episodes 32 --workers 16 \
  --boot-concurrency 4 --render-concurrency 16 --out-dir outputs/capacity-check
vigil progress outputs/capacity-check
vigil verify-run outputs/capacity-check
```

Once the selected concurrency works, a full canonical run is:

```bash
vigil run --workers 16 --boot-concurrency 4 --render-concurrency 16 \
  --out-dir outputs/full
```

On a headless host with two assigned rendering GPUs, add `--render-devices 0,1`
to split the 16 live-renderer slots into eight per device. Device IDs are those
visible to the simulator, independently of the model server's tensor parallelism.
This flag does not allocate GPUs and requires subprocess isolation (the default
positive `--episode-timeout-s`). Each child receives its own device setting;
completed, failed and cancelled children return their slot. The device list is
part of the experiment fingerprint, and the actual device is saved in each trace.
Use a fresh output directory when changing the device list.

Remove selection filters as well as `--max-episodes` for all 1,000 tasks. Original
episode budgets are retained by default (`--max-steps 0`). Shortening budgets,
changing image dimensions or adding protocol retries changes the experiment.
Do not use those changes as undocumented throughput optimizations.

## Keep the simulation host awake

Local rollouts need the simulation host and its network connection to remain
available. On macOS, closing the lid can suspend simulation and API forwarding;
an idle-sleep inhibitor does not prevent lid-close sleep. Suspension can also
delay timeout enforcement. Keep the lid open or use an always-on evaluation host
for long runs. After waking, inspect `vigil progress RUN_DIR` and active processes
before launching another run. If the run has stopped with an infrastructure error,
use the matching resume workflow below; preserve completed results.

## Progress and output retention

```bash
vigil progress outputs/full
vigil progress outputs/full --json
```

Progress counts only the IDs selected in `run_status.json`, when present. Saved
files may contain infrastructure errors; counts are not successful episode counts
or verified final metrics. An abrupt kill or host failure can leave state `running`; the command
reads artifacts and does not assert that a process is still alive. Use the UI's
owned process state or your launch terminal to determine liveness.

Keep PNGs when reviewing behavior. `--no-frames` saves disk space by discarding
temporary images after execution; the model still receives RGB input. It prevents
later image replay and `verify-run --require-frames`. Traces and scores remain.
During execution, the UI shows the latest saved frame; full action/judge history
becomes available when an episode trace has been written.

## Resume an interrupted run

Use the original model, code, data, profile and execution settings:

```bash
vigil run --workers 16 --boot-concurrency 4 --render-concurrency 16 \
  --out-dir outputs/full --resume-existing
```

Verified completed trace/score pairs are reused. Missing, corrupt or infrastructure
failed episodes are executed again. A matching failed task is a valid result and
is not rerun just to improve its score. Use a fresh output directory for another
model, code version, prompt, image size or timeout. Upgrading this release's Python
code changes the runtime fingerprint; old outputs remain readable and scorable,
but cannot be resumed under different code by editing the manifest.
Operating system and Python process architecture are also part of the fingerprint;
switching between Linux/macOS or ARM/x86 requires a new experiment directory.

Partial output directories containing only frames or run metadata are also
protected. They require the original matching `run_config.json` and explicit
`--resume-existing`; if that fingerprint is missing, use a fresh output directory.

Task selection and worker counts may change within an otherwise identical
experiment. The latest aggregate and verification cover the latest selection only.
Old traces outside that selection may still be present. `score-traces DIR/traces`
and `score-traces DIR` use the IDs in `DIR/run_status.json` when it exists. A missing
or malformed selected trace aborts scoring instead of reducing the denominator.
To rescore a different subset, provide its trace file paths explicitly.

Only one pack writer may use a directory. For a long CLI run, keep its shell
alive or use your existing terminal multiplexer. Ctrl+C preserves completed
outputs and terminates owned episode processes. Each new UI run uses a new
directory; CLI `--resume-existing` is the recovery path for a compatible UI run,
using the saved selected pack and the original settings.

A fatal worker exception or episode process timeout cancels queued work and stops
active owned episode processes in the default isolated mode. The run records
`failed`; cancellation records `cancelled`. Completed files remain available for
resume. With `--episode-timeout-s 0`, workers share the parent process, so a running
call can delay shutdown; use the default isolation for bounded cancellation.
Recorded API/simulator error traces produce `infrastructure_error` state and exit
code 1, retaining diagnostic evidence. No new final aggregate is generated.

Initialization is part of that infrastructure check. Scene creation, the initial
teleport and every setup action must be confirmed before a model turn begins.
THOR can reject a repeated state setter because the object is already on/off or
open/closed. Such a setup is accepted only when metadata for that exact object
independently confirms the requested state (including the requested openness).
`initialization_checks` records this evidence in the trace, outside model input.
Other failed or unconfirmed setups abort the episode; they must not be scored as
model performance from an unintended starting state.

## Multiple evaluation machines

Each machine runs its own simulator workers and calls an existing model endpoint.
Use the same release/data/configuration, the same filter set and disjoint task
ranges. For the unfiltered 1,000-episode canonical pack, four equal selections are:

| Machine | Start index | Maximum episodes | Output directory |
| --- | --- | --- | --- |
| A | 0 | 250 | `outputs/shard-0` |
| B | 250 | 250 | `outputs/shard-1` |
| C | 500 | 250 | `outputs/shard-2` |
| D | 750 | 250 | `outputs/shard-3` |

Example command for B, after its local renderer check:

```bash
vigil run --start-index 250 --max-episodes 250 --workers 4 \
  --out-dir outputs/shard-1
vigil verify-run outputs/shard-1
```

Verify each run separately, then copy the complete run directories to one machine.
Before aggregating, check all four `run_config.json` files describe the intended
same experiment and that the union of `run_status.json` episode IDs exactly equals
the canonical pack, without repeats. Machine-specific differences require review;
matching selection size alone does not establish coverage. Then:

```bash
vigil score-traces outputs/shard-0/traces outputs/shard-1/traces \
  outputs/shard-2/traces outputs/shard-3/traces --out outputs/combined.json
vigil report outputs/combined.json
```

`score-traces` rejects duplicate episode IDs and requires a complete recorded
selection, including nested runs under a parent-directory input. Available
`run_config.json` fingerprints must match exactly; different models or settings
must be scored separately. Legacy files without fingerprints still require manual
compatibility review. It does not verify each run's saved scores or enforce
full-pack coverage. This is a manual distribution
recipe, not an automatic cluster scheduler or a certified merge command. Do not
combine different models or experiments into one benchmark result.

## Final checks and exit codes

```bash
vigil verify-run outputs/full --require-frames
vigil report outputs/full
```

Verification is read-only and recomputes settlement from steps, per-episode scores
and the aggregate. It does not call the model again. See [trace analysis](TRACE_ANALYSIS.md)
for what the check proves and how to inspect failures.

Successful CLI execution returns 0, including valid task failures. Pack execution
returns 1 for recorded simulator/model request failures. Invalid configuration or
verification failures normally return 2; interrupted CLI work returns 130. The
recorded `run_status.json` and trace evidence are the authority for interpreting
an experiment, not the presence of an aggregate file alone.
