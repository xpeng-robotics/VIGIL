[Documentation](../README.md) / [Review archive](README.md)

# Repository reliability review — 2026-10-29, second pass

This pass examined directory rescoring, provider failure handling and batch worker
orchestration after the workbench review. Eighteen failure-injection cases failed
before their fixes. They represent four issue groups, not eighteen independent bugs.
Tests use temporary artifacts, dummy credentials and local workers. No model
request, simulator evaluation or GPU workload was launched.

## Local acceptance follow-up (2026-11-02)

- **P1 — Failed scene setup could enter model evaluation.** Initial teleport and
  setup actions were unchecked; a failed action could leave a different starting
  state and still trigger a model call. Creation, teleport and setup now require
  confirmed success before the first turn. Repeated state setters are accepted
  only with independent metadata confirming the exact object's requested state.
  The trace retains these initialization checks without exposing them to the
  model. Other failures remain simulator errors and close the controller. Eleven
  injected cases failed before this fix; successful setup ordering is unchanged.
- **P2 — Resume did not distinguish renderer host architectures.** Identical
  package versions on ARM/x86 or Linux/macOS could produce the same runtime fields.
  Operating system and process architecture now participate in the fingerprint.
- Removed the unused dataset-download dependency from evaluation installation.
  The release reads bundled houses directly. A fresh x86_64 Python environment
  installed the recorded package constraints and passed two real scene checks
  using the cached macOS Unity build; see [runtime scope](../reference/RUNTIME.md).

The two warning-scene checks use privileged masks solely for evaluator diagnostics,
make no model requests and do not enter benchmark scores. House/task bytes and
the scoring formula are unchanged. Scene provenance now includes all house hashes
and verified source revision/index pairs for the 47 imported dataset scenes.

## Earlier nested evidence and provider response follow-up (2026-11-02)

- **P1 — Parent-directory scoring bypassed nested run selections and state.**
  With a failed episode selected and an old successful trace retained, scoring
  the run returned B=0%, while scoring its parent returned B=50%. A nested running
  run was also accepted. Recursive discovery now applies each run's status,
  complete selection and trace identity checks before reading its evidence.
- **P1 — Different recorded experiments could be combined.** Distinct episode
  IDs from two models passed duplicate detection and produced one aggregate.
  Available `run_config.json` files must now match exactly for all input forms,
  including explicit trace files. Matching shards remain supported. Legacy files
  without fingerprints still require independent compatibility review.
- **P1 — Broken inner API fields became model failures.** An empty OpenAI choice,
  empty Gemini candidate or null Anthropic text field was accepted as model text.
  Supported envelopes and text fields now require valid types; malformed payloads
  raise request errors. Empty, truncated, refused and safety-blocked model outputs
  remain model outcomes. Request payloads, prompts and retry policies are unchanged;
  see [the response contract](../reference/API_ALIGNMENT.md#retries-and-resuming).
- **P2 — Partial output directories could lose their evidence.** A directory
  containing only old frames or run metadata, without a recorded fingerprint,
  was accepted as a fresh run. These artifacts now require matching experiment
  identity and explicit recovery, preserving existing bytes on rejection.

The regression cases exercise nested completion/selection, missing selected traces,
matching and incompatible shards, malformed fingerprints, provider responses and
partial-output recovery. Tests inject local responses and use copied recordings;
they do not run a model or simulator. Original data and recorded media are unchanged.

## Earlier API and rollout follow-up (2026-11-02)

- **P1 — Offline eval accepted broken rollout sequences.** Changing a recorded
  step index to 99 still allowed `score-traces` to return metrics, while
  `verify-run` rejected it. Offline scoring, verification and resume now share
  completed-trace structure and infrastructure checks in `vigil/eval/traces.py`.
- **P1 — Inspection commands could destroy their evidence.** `score-trace
  INPUT --out INPUT` replaced the trace with a score; a direct `run-episode`
  could replace prior outputs without a matching experiment fingerprint. Score
  writes are now exclusive, and standalone rollouts require a fresh evidence
  directory under a writer lock. Pack workers retain fingerprint-checked recovery.
- **P2 — Replica rotation reset in every worker.** Isolated episode workers each
  started their compatible API counter at zero. Their first requests all hit the
  first URL, concentrating short rollouts on one replica. The batch parent now
  offsets each child's replica list by episode index. Payloads are unchanged;
  replicas must still serve the same model/settings.
- **P2 — The workbench hid effective concurrency.** Raising workers above four
  left the default four-renderer cap in place. The UI now exposes startup and
  render limits, forwards them to the public CLI, and displays the effective
  episode/request upper bound. There is no independent API RPM/TPM limiter.

Regression tests cover original-evidence preservation, malformed step order,
fresh-interpreter replica selection, UI limit validation and real local process
startup/render ceilings. Saved recording rescoring is offline. Historical raw
results retain settlement-based compatibility; it is not fresh model evaluation
or independent proof of world completion. The review below is the earlier audit.

## Earlier findings

| Priority | Concrete trigger and impact | Fix |
| --- | --- | --- |
| P1 | A trace directory has one successful episode and a truncated, empty-object or malformed failed trace. Directory discovery silently skips the broken file, producing 100% B over one episode instead of rejecting incomplete evidence. A missing selected trace similarly reduces the denominator. | Directory scoring rejects unreadable JSON and malformed trace files. When a run status exists, both the run directory and its `traces` directory require all selected IDs and verify the trace identity. |
| P1 | An HTTP 401 body or transport exception echoes a credential. All three provider clients included the raw value in their raised error; exception chaining also exposed the original value in formatted tracebacks. The agent records these errors in trace evidence. | Redact the effective key and its URL/JSON encodings before truncating error detail. Suppress the unsanitized exception chain. Keep the provider and HTTP status available for diagnosis. |
| P1 | An Anthropic-compatible gateway returns HTTP 200 with an error object or a malformed response envelope. The adapter accepts it as an empty model response; the agent attributes it to model protocol failure, allowing a service failure to be counted as a valid failed task. | Validate the response envelope and raise a request error. Preserve real empty/truncated model outputs and refusal messages as model responses. |
| P1 | One episode worker raises or times out in a multi-worker run. Leaving the executor context waits for the remaining queue, so more episodes keep starting after the fatal error and the recorded state stays `running`. | Propagate cancellation immediately from the first failing worker, cancel queued futures, stop active isolated episode processes, preserve the first error and record `failed` or `cancelled`. |

The selection behavior also closes a usability gap: previously documented directory
rescoring could include old unselected results after resuming a different subset.
It now follows `run_status.json`, matching run verification. Users can still choose
another subset by supplying explicit trace files. This changes directory input
selection, not episode judging, prompts, model input, task budgets or score formulas.

## Implementation and evidence

- [Directory scoring](../../vigil/eval/offline.py): strict discovery, required selection
  and identity checks; valid score files and metadata remain usable in mixed folders.
- [Shared error redaction](../../vigil/agent/backends/base.py),
  [compatible API](../../vigil/agent/backends/openai_compatible.py),
  [Gemini](../../vigil/agent/backends/gemini.py),
  [Anthropic](../../vigil/agent/backends/anthropic.py): safe request failures and correct
  infrastructure attribution.
- [Batch runner](../../vigil/cli.py) and [process runner](../../vigil/eval/process.py):
  first-error cancellation, process cleanup and explicit final state.
- [New failure-injection tests](../../tests/test_adversarial_review.py), existing
  [process lifecycle tests](../../tests/test_process_runner.py) and
  [configuration/resume tests](../../tests/test_usability.py).

The new suite includes compatibility cases for untracked result folders, selected
trace identity and legitimate model refusals. Existing process tests exercise real
temporary child lifetimes, cancellation and process groups. The batch fault tests
inject a failing worker while another worker waits for cancellation; they make no
real evaluation calls.

The stricter Anthropic response check also exposed an older test fixture that
returned a Gemini response to both providers. That fixture now returns the correct
provider envelope; its sampling and reasoning-separation assertions remain intact.

The full source suite passes 341 tests. The existing eight-episode live recording
still passes all settlement, score and aggregate checks over 81 steps, with W and B
both 4/8. This is offline parity checking of prior live evidence, not a new API run.

## Limits

Directory rescoring is still not evidence certification. It requires completed
status when present and compares available experiment fingerprints, but it cannot
establish compatibility for untracked legacy files or prove full-pack coverage.
Use `verify-run` and review experiment identity before combining results.

Cancellation is bounded by process isolation in the default execution path. With
`--episode-timeout-s 0`, already-running in-process calls can delay shutdown. A host
crash or forced kill can prevent the final status write. Recorded infrastructure
failure traces remain diagnostic evidence; they do not produce final task metrics.

Credential redaction covers the configured key and standard encodings in error
messages; it cannot undo secrets already written by an earlier version or protect
arbitrary secrets embedded in user-supplied endpoint URLs or custom request fields.

Existing real recordings can establish scoring parity under these changes, but
not a fresh full benchmark run. Cloud/multi-node deployment, complete historical
paper reproduction and publication/license gates remain as described in the
[release checklist](../development/RELEASE_CHECKLIST.md).
