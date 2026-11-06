---
name: vigil-trace-review
description: Review VIGIL trajectories and saved results for action, environment, settlement and score consistency without rerunning a model.
---

Read [trace analysis](../../../docs/guides/TRACE_ANALYSIS.md) and
[scoring](../../../docs/reference/SCORING.md). Work from the release root.

Start with `vigil verify-run PATH --require-frames`, then `vigil ui --results-dir PATH`.
Inspect model output → parsed action → coordinate adaptation → executed action →
environment evidence → judge → settlement. A visible frame precedes its displayed
action; a later frame can establish the action's effect. Judge overlays belong to
the reviewer and must not become model observations.

W is `world_success_rate`; B is `success_rate`. `mean_primary_score` is a separate
legacy composite. Do not combine curated cases with different experimental
profiles into a model score. The six film cases include two feedback interventions.

Prioritize false success, omitted failures, changed denominators, stale aggregates,
privileged-input leakage and mixed experiments. Support each finding with a
concrete trigger, artifact path and relevant step. Saved evidence verification
proves consistency of that selection, not a fresh run or paper reproduction.
For historical paper claims, consult [paper alignment](../../../docs/reference/PAPER_ALIGNMENT.md).

If changing evaluation behavior, run settlement, scoring, integrity and alignment
tests plus the affected runtime tests. Preserve original results as evidence.
