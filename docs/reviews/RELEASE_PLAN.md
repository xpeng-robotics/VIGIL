[Documentation](../README.md) / [Review archive](README.md)

# VIGIL Release Plan

## Goal

Release a public VIGIL package that reproduces the reference benchmark metrics while removing development-only code, private platform dependencies, private paths, and model-serving assumptions from the core repository.

The release gate is metric alignment, not a single model smoke score. A model can call the endpoint correctly and still fail the benchmark policy.

## Release Shape

- Core package: dataset loading, prompt construction, action parsing, AI2-THOR runner, trace schema, settlement, scoring, aggregate reporting.
- Public scripts: environment setup, local vLLM serving, model evaluation, trace rescoring, aggregate comparison.
- Optional internal validation: keep scheduler-specific launch wrappers outside the publish path, or generate them from public scripts with environment variables. The GitHub tree should not contain private paths, private domains, or organization-specific launcher details.
- Model serving: release code treats OpenAI-compatible endpoints and local vLLM as external services. It should not embed a model registry that assumes private storage.

## Current Status

Aligned and verified:

- The JSON action interface and judge/scoring path follow the reference contract. Historical prompt reconstruction is explicit and records actual content hashes; byte-identical historical prompt recovery is not established. See `PAPER_ALIGNMENT.md`.
- Aggregate output includes reference-style top-level metrics, recursive diagnostic objects, no-report analysis, behavior metrics, harness assistance, and buckets by task family, capability bucket, functional template, target group, and difficulty.
- The metric alignment comparator now recursively checks reference-declared aggregate fields while allowing release-only compatibility aliases.
- Public hygiene tests scan the release surface for private paths and platform terms.
- Runner now requires report closure instead of ending when world success is first observed.
- Pixel grounding records grounding hits and waits for report closure.
- State-report tasks normalize visible public evidence into labels such as `on`, `off`, `open`, and `closed`.
- The published v4 baseline and neutral-report panels each pass independent W/B audits for 20 models and 1000 episodes per model, including all task-family counts. Full legacy aggregate parity is also checked separately with tolerance `1e-9`; partial feedback-intervention coverage is recorded in `PAPER_ALIGNMENT.md`.

Known remaining release work:

- Decide whether to publish a small public golden-trace bundle so external users can run the same offline metric-code gate without access to private validation artifacts.
- T3/T4 style manipulation is judged through the reference `JudgeState/judge_step` path, but should still be represented in any public golden-trace bundle.
- Add final paper/project/dataset links before publishing. The approved Apache-2.0 license and third-party notices are included; retain them in every distribution.

## P0 Metric Alignment

1. Freeze golden traces from the reference implementation.

   Use a small but representative set first: S1 no-report, S1 ground plus report, S4 correct state report, S4 wrong report, T1/T2 world success without report, T3 placement strict/semantic cases, timeout, protocol failure, invalid action limit.

2. Make release rescoring match the reference aggregate.

   ```bash
   scripts/reproduce/run_metric_alignment.sh \
     --reference-path /path/to/reference_results_or_traces \
     --expected-aggregate /path/to/reference_aggregate_score.json
   ```

3. Compare the full reference aggregate, not only headline score fields.

   The comparator must check reference-declared diagnostic objects and buckets recursively. Missing fields such as `no_report_analysis`, `behavior_metrics_summary`, `harness_assistance_summary`, `by_capability_bucket`, `by_functional_template`, or `by_target_group` are P0 parity failures.

4. Keep judge pipeline parity locked.

   The release runner follows the reference pipeline:

   - `PublicThorEnv` executes actions and returns an environment-action result.
   - `sim_runner` owns episode-level `JudgeState` and calls `judge_step` per step.
   - Only `report`, unsafe/invalid terminal conditions, protocol terminal conditions, or budget exhaustion finalize the episode.
   - World success without report remains diagnostic progress and is capped by settlement.

5. Keep golden tests before broad model runs.

   Required tests:

   - S1 `interact_pixel(intent=ground)` without report scores as no-report failure.
   - S1 ground plus `report(status=success)` scores as closure success.
   - S4 visible on/off/open/closed reports match expected public evidence.
   - S4 hidden or unresolved public evidence expects conservative `fail`.
   - World-state success without report is not terminal success.
   - False success report is capped and marked in diagnostics.

## P1 Public Release Quality

- Keep the release scripts generic and parameterized through CLI flags or environment variables.
- Keep model-specific coordinate policy in public profiles or documented flags, not in private launch wrappers.
- Run `bash -n scripts/*/*.sh`, `pytest`, `validate-pack`, and the hygiene test before every release candidate.
- Confirm README, usage docs, and model-eval docs use only public paths and placeholders.
- Confirm generated outputs, caches, and local run artifacts are not staged.

## P2 Reproducibility

- Publish a tiny smoke pack for CI and a canonical public pack for benchmark use.
- Document expected runtime dependencies separately from model serving.
- Keep online model smoke as a health check: endpoint readiness, action validity, timeout rate, and protocol errors.
- Do not use model score as the metric-code release gate.

## Codex Reuse Plan

Use a Codex skill first, plus optional audit agents when needed.

Skill responsibilities:

- Inspect a benchmark repo for release hygiene.
- Compare release evaluator code against a reference implementation.
- Check prompt/parser/action/runner/judge/scoring/aggregate alignment.
- Run the standard commands: tests, hygiene scan, trace rescoring, aggregate comparison.
- Produce a short P0/P1 release risk report with file paths and next commands.

Agent responsibilities:

- Run an independent read-only audit in parallel, like the Harsh review pass.
- Focus on one bounded question, for example S4 state-report parity or aggregate schema parity.
- Do not replace the deterministic release gate; agents are reviewers, not gates.

Recommended skill name: `benchmark-release-auditor`.

Recommended skill contents:

- `SKILL.md`: concise workflow and trigger conditions.
- `references/vigil_alignment.md`: VIGIL-specific task-family and settlement notes.
- `scripts/release_hygiene_scan.sh`: deterministic scan wrapper.
- `scripts/compare_reference_aggregate.sh`: wrapper around the repo's aggregate comparator.

The local skill `benchmark-release-auditor` has been created after reference-trace aggregate parity passed, so future release audits can reuse the verified workflow.
