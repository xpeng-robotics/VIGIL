[Documentation](../README.md) / [Review archive](README.md)

# Rollout scoring audit — 2026-10-30

The current checker passes all **20 main-paper models and all 20 neutral-report
models**, each with 1,000 episodes. All ten feedback pairs also match the paper's
W/B/FR/NR deltas. The five feedback retry discrepancies were resolved by the
[2026-11-02 table correction](../reference/FEEDBACK_CORRECTION.md); the published cells still need updating.
This is an offline evidence audit; no model service, simulator or GPU job was started.

**2026-11-03 follow-up:** the current source again passes the main 20/20,
neutral 20/20 and corrected-feedback 10/10 scoring gates. Its 635 offline tests
pass. The recorded eight-family run verifies 81 steps with W=4/8 and B=4/8;
offline rescoring of that run, its one-episode smoke and the bundled replay also
passes. These are saved results, not fresh model calls. Separate local simulator
diagnostics found ten invalid Dresser setup definitions on two cached builds;
see the [runtime audit](ORIGINAL_RUNTIME_AUDIT.md).
Historical judge/score agreement does not validate those initializations.

## Findings and fixes

1. **P1 — infrastructure failures disappeared from offline scoring.** A historical
   directory contains 248 completed episodes and 752 `*.error.json` timeout
   records. `score-traces DIRECTORY` ignored the errors and returned W=42.3387%,
   B=39.9194% with a denominator of 248. These are completed-subset rates, not a
   valid 1,000-episode result. Directory scoring now rejects those error records.
   Aggregate imports reject declared errors, missing episodes and inconsistent
   counts. Tracked incomplete runs and unfinished or infrastructure-failed traces
   also fail. Explicit completed-file subsets remain supported; they establish
   only their selected coverage.
2. **P1 — the paper gate trusted report-match flags.** A success record whose
   executed report was changed to `fail` could retain B=1 when its saved flags
   claimed a match. The checker now requires the actual report invocation and
   derives matching from its status, final W and expected state-report evidence.
   Contradictions fail the gate.
3. **P1 — failed batch execution wrote aggregates before checking request
   failures.** A trace carrying a model-request error entered the denominator.
   Finalization now records `infrastructure_error`, returns nonzero and does not
   generate final aggregate metrics. Resume retries the affected episode.
4. **Historical data limitations remain.** Two inspected directories have stale
   aggregates that do not cover their 1,000 current episode files. Some old
   revisions omit step diagnostics or differ in report semantics. Their stored
   summaries can rescore identically while an uncached reconstruction differs.
   They must not be chosen as paper references solely by model or profile name.

The timeout example uses `pure_rgb_dialogue_history_proprio_minimal`, which is
the paper's minimal action-feedback profile. Its incomplete candidate does not
establish a paper row. A different complete Doubao archive does: W=52.5%, B=49.7%.

## What was checked

The expanded inventory includes previously omitted local archives outside the
original project checkout. It confirms **31 models with complete
runs, across 197 directories**, containing 197,000 result records and 2,650,202
steps including copies and different conditions. At least 11 directories duplicate
another aggregate byte for byte. No scores are pooled across these runs.

The five 23-model archive cohorts comprise two baseline runs, snapshot control,
minimal action feedback and neutral reporting. Four cohorts have 23 complete
1,000-episode directories each. The feedback cohort has 22 complete directories;
its Qwen3.5-4B candidate contains only 906 task files. In all 22 complete feedback
directories, the preferred aggregate is truncated but the individual episode
files retain complete results. The audit reads those files instead.

| Paper evidence | Coverage | Current result |
| --- | ---: | --- |
| Main panel | 20 × 1,000 | All overall/family W/B counts and scorer/trace outcomes match |
| Neutral-report panel | 20 × 1,000 | All overall/family W/B counts and scorer/trace outcomes match |
| Feedback intervention | 10 × 1,000, paired with existing baselines | All ΔW/ΔB/ΔFR/ΔNR match; five retry cells corrected from full traces |

The main open-model sources and neutral-report sources are pinned to separate
archive cohorts. Another baseline repeat has different trajectories and scores.
Model and profile names alone cannot
identify a paper reference. Exact source maps and hashes are retained locally.

The separate scalar-score audit covers **18 runs, 18,000 episodes and 211,877
steps**. All stored `score_summary` objects match the compatibility scorer, but
that alone is not independent verification: this import path uses the archived
settlement.

For the following eight-reference scalar-score subset, the strengthened checker independently
verified final per-step W, actual terminal reports, report matching, complete
canonical coverage and overall plus all eight family W/B counts. Settlements
were also rebuilt without their cached copies. All scalar scores and available
scalar diagnostics match at a 1e-9 tolerance, with **zero differences**. The
historical state-family naming alias was normalized, as in public aggregate
comparison.

| Archived model | Episodes | W | B | Overall / family W/B |
| --- | ---: | ---: | ---: | --- |
| Doubao Seed 1.8 | 1,000 | 40.4% | 37.1% | Match |
| Claude Sonnet 4 | 1,000 | 25.2% | 21.1% | Match |
| GPT-5.4 | 1,000 | 29.2% | 24.7% | Match |
| Gemini 3.1 Pro Preview | 1,000 | 57.7% | 56.4% | Match |
| Qwen3-VL-235B | 1,000 | 35.2% | 30.5% | Match |
| Qwen3.5-397B | 1,000 | 42.9% | 33.8% | Match |
| Qwen3.6-27B | 1,000 | 46.7% | 37.8% | Match |
| Qwen3.6-35B | 1,000 | 29.9% | 20.6% | Match |

**194 settlements retain violation annotations absent from their step judges**:
Gemini 1, Qwen3.6-27B 23 and Qwen3.6-35B 170. These cannot be recovered losslessly
from those step records. W/B, scalar scores, invalid-action counts and terminal
reasons still match. The audit does not invent missing evidence or rewrite the
historical results.

Other same-profile repeats differ from published targets despite internally
consistent W/B. Five earlier development directories contain twelve episodes
that violate the current report-match evidence rule. They are not substituted
for the identified paper sources. See [paper alignment](../reference/PAPER_ALIGNMENT.md) for
the five feedback retry corrections and their cause.

The bundled two-episode replay, all six curated cases, the existing eight-family
API run, its one-episode smoke run and another two-episode local run pass
`verify-run --require-frames`. One incomplete local run is correctly rejected.
These selections overlap and use different conditions; they are not pooled into
a benchmark score.

## Evidence and limits

The expanded inventory is under `outputs/result-inventory/`, excluded from exports:

- `README.zh-CN.md`, `experiment-catalog.csv` and `run-catalog.json`: local paths,
  per-model directory counts, experiment conditions and partial records.
- `main-source-map.json`, `neutral-source-map.json` and their `*-paper-audit.json`
  reports: two current 20/20 passes, canonical coverage, hashes and family counts.
- `feedback-source-map.json` and `feedback-audit.json`: ten paired sources,
  matching outcome deltas and the five retry differences identified at that time;
  [the correction](../reference/FEEDBACK_CORRECTION.md) records the subsequent resolution.
- `complete-run-validation.json`: all 197 complete directories, aggregate or
  individual-file evidence, truncations and legacy inconsistencies.

Scalar-score and regression evidence remains under `outputs/rollout-score-review/`:

- `historical-runs.json`: per-run counts, source-tree hashes and concrete episode
  examples; `audit_history.py` reproduces the scan.
- `current-paper-candidates.json`: current checker results, family counts and
  uncached field differences; `check_current_paper_candidates.py` reruns the checks.
- `dropped-errors-before.json` and `dropped-errors-after.json`: reproduction on
  the original historical timeout directory before and after the fix.
- `release-runs.json`: verification of the available release-format records.
- `regressions-before.txt`, `regressions-after.txt`, `full-suite.txt`: regression
  and full offline test evidence. The complete suite passes **407 tests**.

Raw simulator `post_state` is absent from the historical step environment records
inspected here. This audit checks saved oracle/judge evidence through settlement
and scoring; it cannot independently reconstruct world predicates from simulator
state or prove image/state synchronization. W/B alignment for both 20-model
panels is verified; uncached reconstruction of every scalar score remains scoped
to the eight-reference subset. This does not certify fresh-rollout reproduction,
the unchanged published feedback retry cells, or public release readiness.

For a completed release-format run, use `vigil verify-run RUN --require-frames`.
For historical full-pack imports, use `scripts/reproduce/run_metric_alignment.sh` with an
explicit reference aggregate, then `scripts/reproduce/check_paper_results.py` with the
correct source map. A successful `score-traces` alone is not the paper gate.
