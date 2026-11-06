[Documentation](../README.md) / Reference

# Feedback retry correction — 2026-11-02

Five feedback retry cells in the published table used the wrong fallback metric.
The shared benchmark scorer is unchanged. All 10 paired runs (20,000 archived
episodes) pass the corrected reference; their published W/B/FR/NR deltas,
too-far means, blocked-path means and baseline retry means remain unchanged.

## Root cause and corrected values

The original table-audit helper `compute_table5_events` used
`same_interact_retry_count` when an aggregate loaded, but counted
`interaction_no_effect` plus `interaction_not_available` when it could not load
the aggregate. The affected feedback aggregates are truncated. The failure-label
proxy reproduces all five published cells to displayed precision, while the
intact episode traces establish the actual repeated-interaction counts.

| Feedback model | Published mean | Wrong fallback mean | Correct retry mean | Correct total / 1,000 |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.5-27B | 0.16 | 0.156 | **0.371** | 371 |
| Qwen3-VL-32B | 0.42 | 0.419 | **2.278** | 2,278 |
| Qwen3-VL-32B (T) | 0.41 | 0.415 | **1.484** | 1,484 |
| InternVL3.5-38B | 0.01 | 0.008 | **1.189** | 1,189 |
| MiMo-Embodied-7B | 0.39 | 0.394 | **2.461** | 2,461 |

For a two-decimal corrected table, use 0.37, 2.28, 1.48, 1.19 and 2.46.
Each repeated executed `interact_pixel` signature after its first occurrence
counts once, including non-adjacent repeats and successful repeated interactions.
The signature includes the intent and executed arguments after coordinate
adaptation. Changing view does not reset the episode-local signature set. Means
use all 1,000 episodes, including episodes with zero interactions.

An interaction failure is not necessarily a repeated interaction. A successful
action can repeat a previous signature. HTTP retries and model-format correction
requests are separate mechanisms and do not enter this metric.

## Reproduce the correction

The release freezes published decimal values **and** corrected integer event
counts in `data/reproduction/paper_v4_feedback_targets.json`. Supply private
baseline and feedback maps from model IDs to their respective aggregate paths.
Use the same source maps selected by the paper audit; do not select by model name
alone. Exact per-episode hashes and experiment-arm profiles enter the report.

```bash
python scripts/reproduce/check_feedback_results.py \
  --baseline-map /path/to/main-source-map.json \
  --feedback-map /path/to/feedback-source-map.json \
  --episode-files --reference corrected \
  --out outputs/feedback-corrected.json
```

`--episode-files` explicitly reads every canonical `<episode_id>.json` beside
the mapped aggregate (or directly in a mapped directory). It requires complete
IDs, matching task families, expected profiles, terminal evidence, settlement
step counts and W/B agreement with the shared scorer. Missing files or selected
infrastructure errors fail. It never silently substitutes another metric because
an aggregate is missing or malformed. Without this flag, aggregates must parse
and contain the complete selection.

Run again with `--reference published` to check the original table: **5/10 models
pass and five retry cells fail**, as expected. The corrected report retains those
published mismatches as well. It does not relabel the original table as matching.

Raw rollouts and source maps remain outside the public export. Model identity is
checked where recorded; a source map is still a caller assertion for episode
files without model metadata. This is an offline evidence correction, not a new
online experiment. The published manuscript still needs its five cells updated.
