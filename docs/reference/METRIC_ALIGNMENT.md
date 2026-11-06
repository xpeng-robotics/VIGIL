[Documentation](../README.md) / Reference

# Metric Alignment

For alignment to the published paper, use the version-pinned targets and
independent step-evidence gate in [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md).
Matching any historical aggregate does not establish that it is the paper row.

The release should be validated in two separate ways:

1. Metric-code alignment: the release scorer must give the same aggregate numbers as the reference VIGIL scorer for the same traces.
2. Online model smoke: the release runner must produce valid traces against a public endpoint or local vLLM server.

Do not use a weak model's score as the primary release gate. A model can run cleanly and still fail the task policy, for example by returning `report(status=success)` before executing `interact_pixel(intent=ground)` on a pixel-grounding task.

## Offline Metric-Code Gate

Use traces produced by the reference VIGIL implementation as the input. The paths below are placeholders; keep private storage paths outside the repository.

```bash
scripts/reproduce/run_metric_alignment.sh \
  --reference-path /path/to/reference_results_or_traces \
  --expected-aggregate /path/to/reference_aggregate_score.json
```

By default, the gate requires the exact episode IDs in the frozen 1,000-episode
paper selection, `data/reproduction/paper_v4_pack.json`. The corrected executable
pack has a different selection. Use `--pack-file` to select the intended cohort
explicitly. Empty results, duplicate episode IDs and inconsistent counts are
rejected. A subset pack is a diagnostic comparison and does not satisfy the full
release gate.

For comparisons between new rollouts and historical results, matching IDs alone
do not establish matching inputs. The corrected selection shares 953 IDs with
the frozen paper selection. A retained pre-revision snapshot has equal episode
and scene JSON for 909 of them; 44 shared tasks have changed inputs. The
[input comparison manifest](../../data/provenance/revision_comparison.json)
records these diagnostic groups and the 47 additions/removals. Report the full
1,000-task results separately from subgroup comparisons. Snapshot equality does
not prove historical executed bytes, rendered observations or checkpoint identity.

The reference path may point at release-style trace JSON files or reference per-episode result JSON files containing `trace` and `settlement`. The script writes `outputs/metric-alignment/release_rescore.json` by default and then runs `scripts/reproduce/compare_aggregates.py`.

If the full reference aggregate has not been located yet, use the embedded per-episode summaries as a diagnostic check only:

```bash
PYTHONPATH=. python scripts/reproduce/check_reference_results.py \
  --reference-path /path/to/reference_result_jsons
```

This command verifies that release scoring reproduces every `score_summary` field stored in the original result JSONs. It is useful for narrowing scorer drift, but it does not replace the full aggregate comparison gate above.

For manual triage, the script is equivalent to:

```bash
PYTHONPATH=. python -m vigil.cli score-traces \
  /path/to/reference_results_or_traces \
  --out outputs/metric-alignment/release_rescore.json

python scripts/reproduce/compare_aggregates.py \
  --expected /path/to/reference_aggregate_score.json \
  --actual outputs/metric-alignment/release_rescore.json
```

This should pass exactly, or within floating point tolerance. The comparator checks headline metrics, per-episode `score_summary` and diagnostics, terminal histograms, no-report analysis, behavior metrics, harness assistance, and aggregate buckets by task family, capability bucket, functional template, target group, and difficulty. If it fails, inspect the per-episode diff first; do not investigate model serving until this gate is clean.

Do not record private run names, account names, or artifact paths in this public document. Keep the exact reference paths and command outputs in the release validation notes outside the repository, and do not mark the release ready until at least one full 1000-episode reference aggregate passes this gate.

## Online Smoke Gate

Run a small subset through a configured model endpoint:

```bash
bash scripts/deploy/run_eval.sh \
  --base-url "$VIGIL_MODEL_BASE_URL" \
  --model "$VIGIL_MODEL_NAME" \
  --max-episodes 10 \
  --out-dir outputs/model-smoke
```

For local vLLM:

```bash
bash scripts/deploy/run_vllm_local.sh \
  --model-path /path/to/model \
  --model-name my-vlm \
  --tensor-parallel-size 1 \
  -- \
  --max-episodes 10 \
  --out-dir outputs/model-smoke
```

For this gate, check:

- No unresolved simulator, timeout, HTTP or model request failures.
- Investigate protocol errors and low `mean_action_validity`: malformed model
  actions are valid task outcomes; parser or schema regressions are implementation
  failures. Retain both kinds of evidence and do not silently retry task failures.
- Trace actions match the public action contract: `navigate`, `look`, `interact_pixel`, `report`.
- Pixel-grounding tasks select with `interact_pixel(intent=ground, x=..., y=...)`; `report` alone only stops the episode and does not prove success.

Model score is useful for model selection, but it is not enough to prove metric-code alignment.

## Full Release Gate

Before publishing:

```bash
PYTHONPATH=. python -m pytest -q
for script in scripts/*/*.sh; do bash -n "$script"; done
PYTHONPATH=. python -m pytest -q tests/test_release_hygiene.py
```

The hygiene test should pass without reporting private paths, internal platform names, or generated cache files.

## Triage

If offline aggregate comparison fails:

- `success` or `terminal_status` mismatch: check `judge_success`, `terminal_status`, and success-condition handling.
- `progress_score` mismatch: check `estimate_progress` and object visibility/distance fields.
- `action_validity` mismatch: check parser normalization and action validation.
- `efficiency` or `steps_taken` mismatch: check trace step count and early terminal handling.

If online smoke fails but offline comparison passes, the issue is usually model serving, prompt following, or model capability rather than metric-code parity.

## Reconstructed historical request conditions

The archived Qwen3.6 reference manifest points to evaluator commit
`92cdbba7365f74f64cfb7860d7db4368478b17d9`. Its committed model configuration differs from the
release defaults:

| Setting | Release default | Historical Qwen3.6 reference |
| --- | --- | --- |
| Generation budget | 4096 | 4096 |
| Temperature | 0.6 | 0.2 |
| Coordinate adapter | pixel coordinates | `normalized_1000` |
| Explicit coordinate hint | none | none |
| Prompt policy | neutral-report, `2026-05-02-neutral-report` | native public evidence, `2026-04-18` |
| Requested workers | 1 | 100 |
| Protocol correction retries | 0 | 1 |
| Observation-echo correction retries | 0 | 2 |

An empty coordinate field in the historical run manifest records the CLI
argument, not the effective model configuration. Historical interaction traces
explicitly record the normalized coordinate adapter. Likewise, the old model
registry specified 4096 output tokens; the historical launcher did not override
that budget. The Qwen3.6 reference traces record 1155 correction retries.

To select these historical **request-side** conditions explicitly against a
configured endpoint:

```bash
bash scripts/reproduce/run_historical_reference.sh \
  --base-url "$VIGIL_MODEL_BASE_URL" \
  --model "$VIGIL_MODEL_NAME" \
  --out-dir outputs/historical-reference
```

This helper selects `--coord-prompt-mode none` to preserve the historical prompt
while enabling the coordinate adapter. It does not change the release defaults.
The correction controls are `VIGIL_PROTOCOL_RETRY_LIMIT` and
`VIGIL_OBSERVATION_ECHO_RETRY_LIMIT`. Every correction attempt and available token
usage are retained in the trace; aggregate harness-assistance metrics include
the retries. Reasoning text is never substituted for a missing action.

The archived manifest reports an uncommitted working-tree diff. The recorded
commit therefore does not fully freeze the code that was executed. This helper
is a reconstructed request profile supported by the committed defaults, action
adapters and prompt-surface metadata, not proof of an identical historical run.

Archived result JSONs do not retain complete server usage or finish reasons.
Token counts reconstructed from stored text are estimates, and historical
reasoning may come from a different attempt than the final repaired action.
Record the checkpoint, serving version and server generation defaults separately
before claiming online reproduction. A release-default run and a historical
request-profile run are different experimental conditions.

## 2026-11-05 revised-pack model check

**Scope update:** this run predates the [frame-ID isolation fix](../reviews/FRAME_ID_REVIEW.md).
Its model-visible task IDs contained initial-state cues. The figures below describe
that earlier runtime; they do not measure the corrected observation contract.
Saved-score agreement remains valid. Post-fix performance requires a fresh run.

Qwen3.6-27B completed all **1,000 canonical tasks**, 125 per family, in a fresh
run using eight macOS simulator workers and a remote compatible model service.
No results were copied from the earlier interrupted run. There are no unresolved
infrastructure errors. Uncached settlement, saved per-task scores and the
recomputed aggregate agree: **W = 424/1000 (42.4%)**, **B = 360/1000 (36.0%)**.

The complete image audit decoded all **14,714 RGB frames** at 640 × 480 and
matched their bytes/hashes to recorded model input. All **4,686** recorded
normalized-coordinate conversions match executed pixel arguments. Saved turns
use `canonical_payload_v1` assistant history. These checks establish consistency
of this completed run; they do not establish that every task is solvable or that
the historical paper execution has been reproduced exactly.

| Family (125 tasks each) | Historical W | Current W | Historical B | Current B |
| --- | ---: | ---: | ---: | ---: |
| PG — Pixel grounding | 87.2% | 80.8% | 76.8% | 77.6% |
| DA — Distance approach | 56.8% | 33.6% | 55.2% | 32.0% |
| VS — View search | 47.2% | 40.0% | 44.0% | 38.4% |
| SV — State verification | 93.6% | 95.2% | 80.8% | 88.8% |
| AI — Approach and interact | 54.4% | 54.4% | 28.8% | 28.8% |
| SI — Search and interact | 12.8% | 14.4% | 7.2% | 8.8% |
| SM — Sequential manipulation | 14.4% | 11.2% | 6.4% | 7.2% |
| CR — Constraint resolving | 7.2% | 9.6% | 3.2% | 6.4% |
| **Full selection** | **46.7%** | **42.4%** | **37.8%** | **36.0%** |

The largest family difference is DA: W decreases by 23.2 percentage points and
B by 23.2 points. Dataset replacement alone does not explain the overall gap:

| Diagnostic group | Tasks per side | Historical W / B | Current W / B |
| --- | ---: | ---: | ---: |
| Equal parsed episode/scene inputs | 909 | 49.5% / 40.2% | 43.7% / 37.3% |
| Changed inputs with shared IDs | 44 | 13.6% / 13.6% | 13.6% / 13.6% |
| Removed historical / added current tasks | 47 / 47 | 23.4% / 14.9% | 44.7% / 31.9% |

These groups partition each 1,000-task selection. The 47 removed/added tasks are
different tasks, not paired observations. Of the 909 equal-JSON tasks, 908 are
also byte-identical (historical W/B 49.4%/40.2%, current 43.6%/37.3%); that subset
must not be added again. Group membership and input hashes are in the
[revision comparison manifest](../../data/provenance/revision_comparison.json).

The equal-input group loses 53 world completions and 26 benchmark successes;
the replacements add 10 and 8, respectively. The retained input snapshot does
not prove historical executed bytes. Historical checkpoint/serving identity and
dirty working-tree behavior are not fully frozen, and the current agent fixes
reasoning/history handling. This comparison does not isolate the cause of the
remaining score differences. Do not change prompts, retries or metrics merely
to make the historical numbers match.

### Recorded request and runtime settings

This run uses the historical request profile explicitly; general release defaults
remain unchanged. The simulator uses Python 3.11.15 x86_64, AI2-THOR 5.0.0 and
Unity `f0825767cd50d69f666c7f282e54abfe58f1e917` on macOS. The model service reports
vLLM 0.18.0, PyTorch 2.10.0+cu128 and Transformers 4.57.6, with native `qwen3`
reasoning parsing. It uses the model's chat template with thinking enabled, no
JSON response constraint and no native tool calling. A 25-file checkpoint,
tokenizer and template comparison matches the preceding deployment; this does
not establish identity with the historical paper checkpoint.

Prepare `reproduction-model.json` in your working directory. Replace the local
endpoint with your compatible service, and supply authentication through
`VIGIL_API_KEY` when required:

```json
{
  "backend": "openai-compatible",
  "base_url": "http://127.0.0.1:8000/v1",
  "model": "Qwen3.6-27B",
  "timeout": 600,
  "temperature": 0.2,
  "top_p": 0.9,
  "top_k": null,
  "max_tokens": 4096,
  "max_tokens_field": "max_tokens",
  "image_detail": "default",
  "coord_mode": "normalized_1000",
  "coord_prompt_mode": "none",
  "supports_json_mode": false,
  "protocol_retry_limit": 1,
  "observation_echo_retry_limit": 2,
  "request_max_retries": 3,
  "request_retry_delay_s": 2,
  "extra_body": {"chat_template_kwargs": {"enable_thinking": true}}
}
```

After installing the [matching simulator environment](RUNTIME.md) and checking
one real episode, use a fresh output directory for the full corrected pack:

```bash
vigil run --config reproduction-model.json \
  --profile pure_rgb_dialogue_history_baseline \
  --prompt-policy-name native_embodied_public_evidence \
  --prompt-policy-version 2026-04-18 --max-steps 0 \
  --workers 8 --render-concurrency 8 --boot-concurrency 2 \
  --episode-timeout-s 7200 --out-dir outputs/qwen36-revised
vigil verify-run outputs/qwen36-revised --require-frames
vigil score-traces outputs/qwen36-revised --out outputs/qwen36-rescored.json
vigil report outputs/qwen36-revised
```

The profile supplies current RGB plus 20 text dialogue turns, without privileged
observations or model-visible evaluator feedback. Keep the original task budgets.
The source pack SHA-256 is
`b277caa2fbf438595cb231472254bbef83d96d7cc563992e57853d87ecea794b`.
Runtime, model and profile fingerprints are retained with the run; a model name
alone does not freeze checkpoint or serving defaults. Transport retries are
separate from the explicitly enabled protocol/echo corrections. Generation
length, thinking and correction changes require separate experiments.

The observed end-to-end duration includes laptop sleep and network recovery, so
it is not a model-throughput measurement. Keep the simulation host awake as
described in the [evaluation guide](../guides/EVALUATION.md#keep-the-simulation-host-awake).
The macOS full run does not establish full-pack Linux execution or 16-worker GPU
rendering capacity. Exact distribution checks remain in the
[release checklist](../development/RELEASE_CHECKLIST.md).

## Subprocess concurrency

When per-episode timeouts are enabled, a render slot covers each episode child
process until it exits. A startup slot is released only after the child has
finished simulator reset and scene setup. Waiting for a slot does not consume
the episode timeout. On POSIX systems, timed-out child process groups, including
simulator descendants, are terminated before the slots are released.
