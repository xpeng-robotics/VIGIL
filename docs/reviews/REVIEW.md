[Documentation](../README.md) / [Review archive](README.md)

# Code and result-integrity review

Current archive coverage is recorded in the [2026-10-30 rollout audit](ROLLOUT_SCORE_REVIEW.md):
both 20-model W/B panels and all ten feedback outcome pairs have been rechecked.
The older verification scopes below describe their respective review dates.

Review date: 2026-10-28. The original 203 tests passed before this review.
Adversarial checks still reproduced substantive failures; a passing test count
alone did not establish result integrity.

| Priority | Finding and consequence | Resolution |
| --- | --- | --- |
| P1 | Release rescoring trusted cached settlement flags even when final step evidence disagreed. A modified world/report flag could change W/B and pass resume when the saved score was regenerated. | Validate cached outcomes, budgets, counts and available diagnostics against step evidence; reject contradictions. Share report matching and recoverable-failure definitions with the live judge. |
| P1 | The paper gate selected the last available world judgment, permitting missing final evidence, non-boolean truth values or actions after a terminal report. | Require world evidence on every step, terminal report placement and matching step counts. |
| P1 | Request extensions could replace the recorded model/messages/token budget. Gemini ignored extensions and JSON-mode configuration; native backends ignored top-k. Gemini thought text could be parsed as the action. | Reject conflicting extension keys; forward native settings; separate Gemini thought parts from final response content. |
| P1 | Concurrent pack commands could write one directory, and a report after an interrupted resume could display an older aggregate without identifying the unfinished run. | Lock the output directory for the live pack operation; persist selection and completion status; reject incomplete reports. |
| P2 | Export/import could turn an invalid action into a valid one, changing action-validity metrics. Standalone episode execution returned success on simulator failure. | Preserve explicit action validity in release-derived result traces while retaining historical simulator-failure semantics. Return nonzero for standalone infrastructure/API errors. |

Core changes are in `benchmark/settlement.py`, `benchmark/scoring.py`,
`paper_alignment.py`, `backends/*`, `run_state.py` and `cli.py`.
Regression cases are in `tests/test_review_integrity.py`.
Running the selected new failure-injection cases against the pre-review source
produced 23 failures and one pass; these cases pass after the fixes.
The final full suite passes all 243 tests. Shell syntax and a one-episode offline
CLI dry-run also pass. Local machine-readable summaries are written under
`outputs/review/` and are excluded from the public export.

| Alignment layer | Evidence in this review | Scope |
| --- | --- | --- |
| Task contracts | All 1,000 executable episode definitions, each under four synthetic event sequences: ordinary action, success report, negative report and protocol-limit exhaustion. | 4,000 runtime-settlement / uncached-trace / exported-result comparisons. This does not execute Unity or a model. |
| Scoring edge cases | Grounded success, premature report, false-negative report, world regression, categorical state reports, recoverable actions and protocol failures. | Check settlement fields and aggregate metrics across serialization/rescoring. |
| Published target files | Re-read arXiv v4 Tables 10 and 15; compare overall and all eight family W/B counts for every model. | 40 rows, 720 numeric cells, zero mismatches. Target transcription only. |
| Historical trajectory alignment | Available local historical aggregates contain summaries rather than complete per-episode trace evidence; some runs are incomplete. | Not verified by this review. Prior recorded archive passes do not certify the stricter current checker. |
| Fresh rollout reproduction | No real provider or simulator run performed in this review. | Not verified. |

Paper source: [arXiv:2605.08747v4](https://arxiv.org/html/2605.08747v4).
The release defaults use the neutral-report prompt. Main-panel historical
requests and the neutral-report sensitivity experiment are distinct conditions;
identical scoring does not imply identical trajectories or scores under the
release defaults.

The existing [paper alignment notes](../reference/PAPER_ALIGNMENT.md#feedback-intervention-coverage)
also record unresolved Table 3 feedback retry discrepancies. Those archived
measurements were not rerun here and must not be described as newly verified.
The full feedback-table gate remains unresolved.

For a fresh local review run:

```bash
python -m pytest -p no:cacheprovider
python scripts/reproduce/check_paper_results.py \
  --source-map /path/to/complete_archived_sources.json \
  --out outputs/paper-alignment.json
```

The second command requires complete raw archives. Neither a copied target file
nor synthetic event tests substitute for those inputs. Reference-result imports
retain historical settlement compatibility; the independent paper checker is
required when validating those imported archives.

## Live API follow-up: 2026-10-29

Two integration defects were fixed: the Gemini adapter ignored a configured
API-key header, and OpenAI-compatible / Gemini adapters could treat an HTTP 200
gateway error as an empty model answer. Gemini now honors custom authentication
headers; invalid API envelopes raise request failures. Gemini safety blocks
remain model responses. All 88 targeted backend, usability and result-integrity
tests pass, including eight new regression cases.

An existing model gateway `gemini-3-flash-preview` endpoint completed a real RGB smoke
episode, followed by an eight-episode integration experiment. The subset was
selected before execution: canonical zero-based indices
`0, 136, 250, 396, 500, 628, 750, 878`, one per task family, alternating iTHOR and
ProcTHOR. Local simulation used two workers; no new cluster jobs were submitted.
The smoke episode is separate and is not added to the subset aggregate.

The eight-episode run completed 81 agent steps with W = 4/8 and B = 4/8, zero
infrastructure errors and zero protocol failures. Three episodes falsely
reported success; one exhausted its step budget without reporting. Removing
cached settlement metadata and reconstructing outcomes from step evidence
matched every online settlement. Per-episode scores and the entire aggregate
also matched independent recomputation exactly.

Conditions: RGB-only neutral-report profile, 640 x 480 frames, explicit
normalized-1000 coordinates, temperature 0.2, top-p 0.9, 4096 output tokens,
Gemini thought summaries enabled, JSON response mode, original episode step
budgets and zero protocol repair retries. Local artifacts are under
`outputs/live-eval/<run>/`, including RGB frames, traces,
`run_config.json`, scores and `alignment_audit.json`.
This verifies real execution and internal scoring consistency for this subset.
It does not reproduce the full 1000-episode benchmark or published paper scores.

## Release usability and inspection follow-up: 2026-10-29

The public workbench now ships in the source export and wheel with two recorded
RGB episodes. Configuration, task selection, progress, cancellation and replay
share the CLI/runtime/scoring path. The workbench stage passed 273 source and
export tests, plus a clean installed-wheel demo check.

Root `AGENTS.md`, Chinese onboarding, a documentation map and separate installation,
deployment, evaluation and trace-analysis guides now cover the public workflow.
The GNU-only progress script was replaced with a portable `vigil progress` wrapper.
`vigil verify-run` publicly exposes the offline settlement/score/aggregate audit,
with optional per-step PNG-header checks. It passed against both the bundled demo
and the saved eight-episode experiment; this follow-up made no new model calls.

The complete source suite now passes 295 tests. Added checks cover inconsistent
artifacts, incomplete runs, invalid selection and step order, optional frames,
the shell wrapper, exported instructions and relative documentation links.
See [the change log](../development/CHANGELOG.md) for implementation and test references.
Cloud recipes and multi-node serving still need validation on the target system.
