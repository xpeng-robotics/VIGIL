[Documentation](../README.md) / Reference

# Scoring

VIGIL separates physical completion from correct terminal reporting. The paper
reports two binary outcomes, evaluated at episode closure:

- **W**: the final primary semantic world predicate is satisfied.
- **B**: final semantic W is true and the agent submits a terminal `report`
  whose status matches the deterministic report rule.

World completion at an earlier step is not final W. A simulator action succeeding,
a claimed terminal `success`, or a correct negative report does not establish B.
World completion does not stop the live episode; a report is still required.

## Output fields

| Paper quantity | Current output field |
| --- | --- |
| B, per episode | `success` / `score_summary.success` |
| Mean B | `success_rate` |
| W, per episode | `score_summary.diagnostics.world_success` |
| Mean W | `world_success_rate` |
| Closure gap | `world_success_rate - success_rate` |
| Strict world/benchmark variants | `strict_world_success_rate`, `strict_success_rate` |

`episode_score` is a compatibility alias for the legacy composite
`primary_score`, and `mean_episode_score` equals `mean_primary_score`.
**Neither field is the paper's binary B.** The composite combines success,
progress, efficiency and compliance with weights 0.60/0.15/0.15/0.10, then caps
protocol failure at 0.02, false report at 0.08, and terminal no-report at 0.10.
The composite is retained for historical aggregate parity.

## Report matching

For goal-directed tasks, `success` matches W=true; `fail`, `unsafe`, or `invalid`
match W=false. A correct negative report remains B=0. State-verification tasks
require the expected `on`/`off` or `open`/`closed` label and a publicly observable
target state at closure. A correct state label with W=false remains B=0.

- FR (`false_report`): submitted report content does not match the final world
  or expected categorical state. This includes false-success and false-negative
  reports and incorrect state labels.
- NR (`fail_no_report`): the episode ends without a report at its step budget.
- IL (`invalid_action_limit_exceeded`): the invalid-action limit forces closure.

The broader count of all episodes without a report also includes other forced
closures; it must not be substituted for the paper's NR definition.

## Replay and evidence

Interaction retry counts repeated executed `interact_pixel` signatures within
each episode, including non-adjacent repeats. It is independent of failure labels
and API retries. See the [five-cell feedback correction](FEEDBACK_CORRECTION.md).

Live traces carry a final `settlement` and per-step `judge_result` records.
Release-trace scoring checks cached world/report outcomes, budgets, step counts,
and available failure/progress evidence before accepting the settlement. A
contradiction raises an error, including during resume. Removing the cache from
a complete live trace reproduces its settlement. Legacy progress fields retain
their cumulative maxima; W always uses the final judged world predicate.
Simple traces without detailed judge records use their final step and report.
It never infers W from the outer terminal-status label.

Reference-result imports retain settlement-based compatibility for historical
files that lack full evidence. Rescoring those imports alone is not an
independent world/report audit; use the paper gate with complete raw traces.

The paper gate independently derives W/B from per-step judge and report evidence
and compares them with the current scorer. Every step must contain boolean world
evidence, a report must be terminal, and settlement step counts must match.
Thus merely copying a cached
`score_summary` cannot pass the audit. See [PAPER_ALIGNMENT.md](PAPER_ALIGNMENT.md).

```bash
vigil score-trace outputs/eval/traces/<episode_id>.json
vigil score-traces outputs/eval/traces --out outputs/aggregate_score.json
```
