[Documentation](../README.md) / Reference

# Paper results and reproducibility

The release includes frozen paper counts, companion audit summaries and scripts
for checking archived results. Complete historical trajectories and serving
configurations are not bundled; the historical checks below require those
original archives. The corrected executable benchmark supports new evaluations,
not an exact rerun of the published experiments.

The target is [VIGIL, arXiv:2605.08747v4](https://arxiv.org/html/2605.08747v4)
(2 June 2026), specifically the ten anchor rows in Table 2 and the full
20-model panel in Table 10. The machine-readable targets in
`data/reproduction/paper_v4_targets.json` were extracted from this version.
They retain integer W/B counts overall and for all eight task families.
The ten overlapping anchor rows were checked against the full panel.

Do not select a reference by model name alone. A later repeat, a neutral-report
run, and the paper baseline are different experimental records. For example:

| Model | Paper W | Paper B |
| --- | ---: | ---: |
| Qwen3.6-27B | 46.7% | 37.8% |
| Qwen3.5-27B | 42.0% | 36.2% |

The Qwen3.6 repeat with B=35.1% and the Qwen3.5 neutral-report run with B=36.3%
remain useful reference runs, but do not define the main paper rows. A filename
containing `paper_v4` is also insufficient: confirm its contents against the
published version, including model selection and family values.

## Deterministic paper-result gate

Provide a private JSON map from the model IDs in the target file to archived
aggregate JSONs containing the complete per-episode `trace` and `settlement`:

```json
{
  "qwen3.6-27b": "/path/to/paper-qwen36/aggregate.json",
  "qwen3.5-27b": "/path/to/paper-qwen35/core.aggregate.json"
}
```

The example is partial; the full gate requires all 20 model sources.

```bash
python scripts/reproduce/check_paper_results.py \
  --source-map /path/to/private_source_map.json \
  --out outputs/paper-alignment.json
```

The check defaults to the frozen `data/reproduction/paper_v4_pack.json`, not
the revised executable pack. It requires exactly those 1,000 unique IDs and the
correct task families. It independently derives final W and report-dependent B
from the step trace, compares them with the current scorer, and checks every
published overall/family count. Missing sources, duplicate IDs, wrong model or
profile, wrong family membership, absent judge evidence and mismatches fail the
gate. Source and normalized outcome hashes are recorded for later review.

The [expanded 2026-10-30 audit](../reviews/ROLLOUT_SCORE_REVIEW.md) reran the current checker
against all 20 main-paper archives: **20,000 episodes, 20/20 models passed**,
all overall/family W/B counts matched and zero scorer/step-evidence W/B
disagreements. The initial eight-model scope omitted a separate local archive
root; those sources have now been included. Exact paths for the selected
open-model baseline cohort and the distinct repeat are retained in private maps.

Uncached reconstruction of all scalar score fields was additionally checked
for eight references (8,000 episodes); missing historical violation annotations
are reported separately. Raw trajectories are not bundled, so an external
recipient needs the archives and the corresponding source map to rerun the gate.
A target table or a saved PASS report alone is not an independent reproduction.

## Neutral-report sensitivity gate

Table 15 is frozen separately in `data/reproduction/paper_v4_neutral_targets.json`.
Use the same checker with the matching 20 neutral-report archives:

```bash
python scripts/reproduce/check_paper_results.py \
  --targets data/reproduction/paper_v4_neutral_targets.json \
  --source-map /path/to/private_neutral_source_map.json \
  --out outputs/paper-neutral-alignment.json
```

The baseline and sensitivity manifests deliberately contain different model
panels and different target values. Keep their source maps separate. All 20
neutral-report runs from the identified sensitivity cohort (another 20,000 archived episodes)
now pass the current checker: **20/20 models**, with exact overall/family counts
and zero scorer/step-evidence W/B disagreements. Their source map is separate
from the main-panel map.

## Feedback intervention coverage

All ten paired feedback sources have now been located and verified against
Table 3: **10,000 feedback episodes**, with exact W/B/FR/NR deltas for every
anchor model. These include Gemini (W=71.6%, B=69.4%), Doubao (52.5%, 49.7%),
Qwen3.6-27B (54.7%, 49.9%), GPT-5.4 (33.7%, 27.0%) and Claude Sonnet 4
(27.9%, 22.0%), in addition to the five previously identified open-model sources.

The smaller Qwen3.6 repeat and the 248-completed/752-timeout Doubao candidate
are different records; complete paper-matching sources exist elsewhere locally.
`pure_rgb_dialogue_history_proprio_minimal` is the minimal action-feedback
profile used for this intervention. The earlier review incorrectly excluded it
based on the word “proprio”. Several feedback aggregates are truncated; the
verification reads all 1,000 intact episode files in those directories instead.

The five retry discrepancies have been traced to an incorrect failure-label
fallback in the original table-audit helper when feedback aggregates were
truncated. Complete per-episode evidence gives corrected means of 0.371, 2.278,
1.484, 1.189 and 2.461 for Qwen3.5-27B, Qwen3-VL-32B, Qwen3-VL-32B (T),
InternVL3.5-38B and MiMo-Embodied-7B respectively. All other table cells retain
their original values. The scorer's retry definition is unchanged.

The new paired checker passes all ten corrected references (20,000 baseline and
feedback episodes), while explicitly retaining the five published mismatches.
See [the correction, root cause and reproducible commands](FEEDBACK_CORRECTION.md).
The published manuscript still needs those cells updated; the original Table 3
check correctly remains a failure for five rows. This does not infer fresh
online rollout parity.

## Frozen inputs and protocol

The current formatter uses episode-local step labels and excludes dataset IDs from
model-visible frame metadata. The [frame-ID review](../reviews/FRAME_ID_REVIEW.md)
documents an answer-cue leak in the earlier release runtime. Historical input
formatters or saved requests need separate inspection; the score gates above
verify outcomes, not absence of model-input leakage.

The original paper-aligned pack had 125 episodes in each of eight families. Its 1,000
executable episode JSONs and 465 referenced ProcTHOR house JSONs were compared
with the source experiment repository and were identical as JSON values.
Pack-file hashes may differ after removing authoring metadata; do not interpret
that as proof of different simulator inputs, or ignore executable-content drift.
The gate preserves that original pack hash. Current corrected data has a different
hash and selection; running it is a new experiment, not exact reproduction of
those historical table values.

The baseline exposes current RGB and 20 text-only dialogue turns. Hidden world
state and segmentation stay evaluator-only; no depth, pose, structured memory or
action-success feedback is exposed. Rendering is 640x480, field of view 90 degrees,
visibility distance 6 m, and interaction distance 1.5 m, with per-episode initial
pose and scene setup. The family step/invalid-action budgets are:

| Family | Paper name | Steps | Invalid actions |
| --- | --- | ---: | ---: |
| S1 | PG | 5 | 3 |
| S2 | DA | 12 | 4 |
| S3 | VS | 20 | 6 |
| S4 | SV | 5 | 2 |
| T1 | AI | 25 | 8 |
| T2 | SI | 35 | 10 |
| T3 | SM | 30 | 10 |
| T4 | CR | 40 | 12 |

See [SCORING.md](SCORING.md) for the W/B contract. `mean_primary_score` is a
legacy composite diagnostic, not paper B.

## Release defaults versus historical requests

The release defaults are `4096` tokens, temperature `0.6`, empty coordinate modes,
1 worker and neutral-report `2026-05-02-neutral-report`. The paper's main comparison uses
the native-public-evidence prompt; neutral-report is a separate sensitivity
experiment in Table 15. Sharing that prompt family does not establish identical
sampling budgets, serving settings, coordinates or trajectories.

`scripts/reproduce/run_historical_reference.sh` explicitly selects the reconstructed
Qwen3.6 request conditions: temperature 0.2, 4096 tokens, normalized coordinates, legacy prompt,
100 workers and recorded correction retries. Its default data follows the current
release: using it without the original complete task/scene inputs is a new-data
experiment under a historical request profile. Override worker/render limits to
match host capacity. It is not a universal preset for
all paper models. Model-specific budgets and coordinate conventions must be
recovered from their own manifests and runtime configuration.

Historical manifests report dirty worktrees and lack some immutable checkpoint,
server-default and decoder-seed information. A supplied legacy policy name or
reference hash does not prove byte-identical prompt reconstruction. New policy
hashes are computed from current content; the historical reference hash is
recorded separately. Each model turn also records its actual system-prompt hash.

Offline trace agreement establishes scoring and result-table alignment. It does
not establish fresh online rollout parity. Before claiming online reproduction,
record checkpoint identity, serving/Unity versions, request settings and actual
prompt hashes, then run the full pack and report stochastic repeat variability.
The public release currently exposes the baseline profile; the action-feedback
intervention and other ablations must be identified separately from that baseline.

Provider transport, image bytes and coordinate audit details are in
[API alignment](API_ALIGNMENT.md). Model/request changes require a fresh output directory.
