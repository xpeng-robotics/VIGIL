---
name: vigil-evaluation
description: Configure and run authorized VIGIL model evaluations, select tasks, inspect progress and resume matching experiments.
---

Read [model configuration](../../../docs/guides/MODEL_EVAL.md) and
[evaluation workflow](../../../docs/guides/EVALUATION.md). Work from the release root.

Use an existing endpoint when supplied. `vigil init` creates a portable config;
keep keys out of tool output and public files. `vigil doctor` checks readiness.
`--check-model` sends a text request, while `vigil smoke` runs a real RGB episode;
do not confuse either with full benchmark validation.

Preview selection with `vigil list-episodes` or `vigil run --dry-run` when helpful.
Paper-facing family aliases are PG/DA/VS/SV/AI/SI/SM/CR. Start an authorized live
check with one episode and a fresh output directory. Increase workers only within
the requested scale and host capacity. Model serving and GPU allocation are
separate operations, not implicit consequences of reviewing evaluation code.

Preserve the baseline's RGB-only input, per-episode history and original budgets
(`--max-steps 0`). Record deliberate experimental changes. Resume only with matching
runtime, model, profile and data fingerprints; never edit stored fingerprints.

After execution run `vigil verify-run PATH --require-frames` and `vigil report PATH`.
Use `vigil progress PATH` for saved progress, not metric validation. Distinguish
valid task failures from infrastructure failures and never present incomplete
runs' old aggregates as final. Report the actual episode selection and evidence.
