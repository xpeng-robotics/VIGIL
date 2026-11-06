[Documentation](../README.md) / Guides

# Trajectory replay and result verification

Open a saved run to follow its observations and actions, then verify the
evidence before interpreting aggregate scores.

## Start from the recorded example

```bash
vigil ui
```

Choose **Explore a recorded run**, then select the success or failure
episode. The release contains two real recorded episodes with five RGB frames.
They are fixed evidence for learning the interface; opening them makes no new
model calls. They are not a full benchmark estimate.

For your own completed or running outputs:

```bash
vigil ui --results-dir /path/to/run
```

In **Results & replay**, choose a run and episode. Move the step slider, use the
step buttons or play the sequence. Inspect the RGB image and pixel marker beside
the model action, executed action, environment feedback, evaluator result and
available reasoning/raw response. The pixel marker is scaled to the displayed
image. Judge facts are evaluator evidence, not additional model observations.

Frames are the observations used for the corresponding action. A single frame
does not prove the action's resulting world state; inspect feedback and subsequent
steps. A model's claim of success is also not ground-truth completion.

## Understand the artifacts

| Artifact | What it records |
| --- | --- |
| `run_config.json` | Experiment identity and code/data/profile/model fingerprints; no API key |
| `run_status.json` | Latest selected IDs, completion state and recorded infrastructure errors |
| `model_config.json` | Model transport and generation metadata |
| `traces/<id>.json` | Ordered actions, responses, environment/judge evidence and settlement |
| `scores/<id>.score.json` | Shared scorer's per-episode result |
| `frames/<id>/step_000.png` | First saved RGB observation; subsequent steps use increasing indices |
| `aggregate_score.json` | Aggregate for the latest selection |
| `summary.txt` | Human-readable summary; incomplete runs are labeled |

UI and helper launches can also retain process logs. `run-episode` writes individual
trace/score/frame files; use `smoke` or `run` when you want the pack run status and
aggregate required by `verify-run`. Historical external formats can be scored by
`score-traces` where supported, but are not automatically imported into the UI.

## Which metric answers which question?

| Field | Meaning |
| --- | --- |
| W / `world_success_rate` | Was the world/task completion condition reached? |
| B / `success_rate` | Did the episode also satisfy the required reporting/termination behavior? |
| `mean_primary_score` | A separate legacy composite; do not label it W or B |

Follow [the scoring specification](../reference/SCORING.md) for task-specific reporting rules.
An incorrect report can fail B even when the world condition is reached. A
simulator or request error means the evaluation did not yield a valid task result;
the UI and `report` refuse to present incomplete pack metrics as final.

## Verify the complete evidence chain

For the current historical scoring findings and validated scope, see the
[rollout scoring audit](../reviews/ROLLOUT_SCORE_REVIEW.md). `score-traces` rejects unresolved
historical error records and incomplete runs instead of silently shrinking the
denominator. To inspect progress while a run is incomplete, use `vigil progress`.
Explicit completed-file subsets can be rescored, but do not prove full coverage.

The UI and `vigil report` already perform this check for completed run directories
before displaying final W/B. The explicit command below is useful for independent
inspection and saving an audit report. Run directories without `run_status.json`
are rejected, including when their aggregate is passed as a file path. Use
`progress` to inspect retained files or `score-traces` for an explicit subset.

A standalone aggregate outside a run directory remains readable with
`vigil report path/to/combined.json`. It is labeled **UNVERIFIED stored summary**:
displayed rates, counts and any included episode IDs are checked for validity,
but no run selection, step evidence or experiment compatibility is verified.

```bash
vigil verify-run outputs/my-run
vigil verify-run outputs/my-run --require-frames
vigil verify-run outputs/my-run --json > outputs/my-run-audit.json
vigil report outputs/my-run
```

`verify-run` requires a completed release-format run. In the order selected by
`run_status.json`, it checks unique valid episode IDs, matching nonempty finished
traces, consecutive step indices, absence of infrastructure errors, and no steps
after a terminal step. It removes the cached settlement and reconstructs it from
step evidence, compares that result with the saved settlement, recomputes each
score through the public scorer, and checks the aggregate exactly.

`--require-frames` additionally requires a PNG header at each expected step path.
It does not fully decode images or prove their visual content. Omit this flag for
runs intentionally saved with `--no-frames`. The default command writes nothing;
JSON redirection above saves a separate audit file. Inputs remain unchanged.

Expected success for the bundled example:

```bash
vigil verify-run vigil/web/demo --require-frames
# Verified 2 selected episodes, 5 steps; W: 1/2, B: 1/2.
```

An audit failure returns a nonzero status and identifies the mismatching artifact
or episode. Preserve the original files while diagnosing it. Recomputing metrics
does not repair missing evidence. A pass proves internal consistency of the saved
selection; it does not establish that observations are authentic, that a model
was called live, that all 1,000 tasks ran, or that paper results were reproduced.
Use [paper alignment](../reference/PAPER_ALIGNMENT.md) for the independent historical gate.

## Analyze one failure

1. Check run state and whether `env_status` or `error_type` records a simulator or
   model request error. Resolve infrastructure before interpreting model ability.
2. Inspect the last action and report. Did the model terminate early, claim success
   without evidence, choose the wrong state, or exhaust the original budget?
3. Replay the first step where execution diverges from the task. Compare the
   requested coordinates/arguments with the executed action and feedback.
4. Read `judge_result` and the final settlement together. Recoverable feedback
   such as a blocked path is not automatically an invalid action.
5. Verify the run before including its metrics in comparisons. Keep the selection,
   experiment settings and number of episodes beside W/B.

## Evaluate saved rollouts

Install only the core package (`python -m pip install -e .`). These commands need
no simulator, model configuration, API key or frames. They use deterministic
benchmark scoring; they do not ask another model to judge the trajectory.

| Available evidence | Command | Scope |
| --- | --- | --- |
| Completed release run | `vigil score-traces RUN_DIR --out NEW.json` | Rescore the recorded selected episodes |
| Release trace files, including `run-episode` output | `vigil score-traces TRACE_A.json TRACE_B.json --out NEW.json` | Rescore only those explicit files |
| One release or supported historical result | `vigil score-trace RESULT.json --out NEW.score.json` | One episode's score |
| Historical directory or aggregate containing full `results[].trace` and `settlement` | `vigil score-traces PATH --out NEW.json` | Compatibility scoring from saved historical evidence |
| Only aggregate numbers or model response text | `vigil report SUMMARY.json` for a valid summary | Cannot reconstruct task/world evidence; no new W/B evaluation |

For independent rescoring of one trace or a directory:

```bash
vigil score-trace outputs/my-run/traces/EPISODE_ID.json
vigil score-traces outputs/my-run/traces --out outputs/rescored.json
```

`--out` must be a new file. Both scoring commands refuse existing outputs,
including symlinks to inputs, instead of overwriting original evidence. Without
`--out`, JSON is printed to stdout. Keep shell redirection away from source files.
The original run's cached scores and aggregate are not updated by rescoring.

Release traces must have consecutive step indices starting at zero, no actions
after a terminal step, and no unresolved infrastructure failures. Resume and
`verify-run` enforce the same structural checks. A release aggregate written by
`score-traces` contains score summaries, not the full trace evidence: keep the
source trajectories to rescore again. Historical settlement compatibility does
not establish independent world verification; use the paper-alignment tools for
that claim. There is no simulator/API concurrency option for offline scoring.

Replace `EPISODE_ID` with an actual ID. If the run has `run_status.json`, scoring
either the run directory or its `traces` directory uses the recorded selection and
requires every selected trace. Old unselected files are excluded. Explicit file
paths allow a different subset. Without a run status, directory mode discovers
trace files; unreadable JSON or malformed files inside `traces` abort scoring.
Valid non-trace metadata in mixed directories is ignored. This prevents partial
or damaged evidence from silently shrinking the metric denominator.

These rules also apply to every nested run when you pass a parent directory.
A nested unfinished run fails the whole request; it is never silently skipped.
Nested completed runs retain their own recorded selections, excluding old files.
If adjacent `run_config.json` files are present, all included tracked experiments
must match exactly, including when traces are supplied as individual files. Score
different models/settings separately. Matching fingerprints do not prove full
coverage; missing fingerprints on legacy files do not establish compatibility.

Rescoring does not certify run completion or experiment compatibility. Use
`verify-run` to compare the latest selected run to its own saved aggregate.

## Missing images and remote use

If images are unavailable, the UI still shows recorded decisions and judgments
and labels missing frames. Keep each run's `frames/` directory beside `traces/`.
For remote viewing and copying results, follow [deployment](DEPLOYMENT.md).
The workbench only reads runs beneath its selected results directory and remains
a loopback-only personal tool.
