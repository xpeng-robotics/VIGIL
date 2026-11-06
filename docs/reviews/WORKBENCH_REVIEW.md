[Documentation](../README.md) / [Review archive](README.md)

# Workbench and repository review — 2026-10-29

The previous test suite passed, but adversarial cases still exposed result-integrity,
credential-handling and filesystem-boundary problems. This review covered the UI,
launch path, CLI report, subprocess configuration, trace loading and shared scoring.
Seventeen new failure-injection cases failed before their corresponding fixes.

## Findings and fixes

| Priority | Reproduction and consequence | Resolution |
| --- | --- | --- |
| P1 | Change only `aggregate_score.json.success_rate` from 0.5 to 1.0 in the two-episode example. The UI and `vigil report` displayed 100% B although one episode failed. | Run-directory reports and the UI now use the shared `verify-run` evidence check before showing final W/B. The UI caches successful checks only while the status, trace, score and aggregate file metadata remain unchanged. |
| P1 | Replace a trace/judge boolean with the string `"false"`. Python truth-value coercion could treat it as true and let malformed evidence influence scores. | Require actual boolean values in release trace fields and present judge evidence. Apply the same checks to in-memory settlement inputs. Nullable strict/report fields retain their explicit null semantics. |
| P1 | Configure a key in a file, then run a pack with episode subprocesses. The parent copied the key into each child's command-line arguments. | Pass the effective key through a separate child environment, remove unrelated provider keys there, and leave the parent's environment unchanged. Explicit user-provided CLI secrets should still be avoided in favor of config/environment credentials. |
| P1 | Replace a previously discovered run directory with a symlink outside the results root, or symlink its model metadata to an outside JSON file. Cached run registration did not preserve the intended boundary. | Recheck the registered run's resolved location against the original results root and constrain metadata reads to the run. |
| P2 | Put a JSON array in one run's status file. Listing all results raised an exception and prevented the workbench from loading normally. | Validate run JSON objects and selected IDs; mark that run invalid while keeping the remaining library available. Clear the previous run's displayed metrics when switching runs. |
| P2 | Launch on a system where `python3` is older than 3.10 despite a suitable versioned interpreter being installed, or use an occupied/invalid port. | The source launcher discovers a supported interpreter and selects an available port. Explicit invalid ports and missing interpreters produce actionable messages. |
| P2 | Request one RGB frame from a large run. The endpoint loaded every episode's score and enumerated every frame directory first. | Frame requests now check run membership directly; episode replay loads that episode's row. A regression test forbids a frame request from loading the full run detail. |

Implementation: [workbench](../../vigil/web/app.py), [CLI](../../vigil/cli.py),
[trace validation](../../vigil/eval/traces.py),
[settlement](../../vigil/eval/settlement.py),
[subprocess runner](../../vigil/eval/process.py), [launcher](../../start.sh).
Regression evidence: [adversarial cases](../../tests/test_workbench_review.py),
[credential forwarding](../../tests/test_usability.py),
[HTTP/replay cases](../../tests/test_web_app.py), [launcher cases](../../tests/test_launcher.py).

The stronger report check exposed an old test fixture that omitted the runtime's
saved settlement. The fixture now writes a complete trace/score pair; the check
was not relaxed to make an incomplete fixture pass.

The final source suite passes 319 tests. Browser checks covered the overview,
recorded RGB replay, moving between actions, local setup checks, task search and
family filtering. The existing eight-episode live recording still passes all
settlement, score and aggregate checks across 81 steps. No new model request or
simulator evaluation was used for this review.

## Usability changes

The overview now puts the actual recorded RGB trajectory beside the primary
actions. A dark navigation rail, clearer typography, quieter surfaces and separate
workflow cards make setup, evidence and results easier to distinguish. The replay
keeps the model decision, executed action and evaluator evidence together. Keyboard
focus, a skip link, current-page semantics, a named replay dialog and reduced-motion
handling are included. No external frontend assets or build step were added.

From the source release, `bash start.sh` opens the workbench without package
installation. macOS also has `start.command`. The UI identifies missing simulator
packages and gives an install command for the interpreter actually running it.
An attempt to run without the simulator is rejected before creating an experiment.
The existing `pip install -e .` / `vigil ui` workflow remains available.

## Scope and remaining limits

This work does not change prompts, task budgets or RGB input. Strict loading now
rejects malformed boolean fields; valid existing recorded traces remain scorable.
As with other code changes, old experiment fingerprints cannot be reused to resume
under new code without starting a new output directory.

Artifact verification establishes consistency of saved evidence, not simulator
authenticity or full benchmark coverage. Standalone aggregate files without a run
status can still be displayed by `report`, but lack the trace chain needed for this
run-directory check. Historical imports retain their separate compatibility path.

The UI is a personal loopback/SSH tool. File metadata caching is intended to notice
ordinary artifact changes, not defend against an attacker modifying files during
verification. Cloud and multi-node serving recipes still require target-host
validation. Complete historical paper reproduction and publication/license gates
remain open as recorded in [paper alignment](../reference/PAPER_ALIGNMENT.md) and
[the release checklist](../development/RELEASE_CHECKLIST.md).
