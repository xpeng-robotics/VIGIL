[Documentation](../README.md) / [Review archive](README.md)

# Onboarding and repository review

Reviewed on 2026-11-02. This compares documented user journeys and code entry
points, not benchmark scores or a ranking of community adoption.

## Reference projects

| Project | Useful onboarding pattern | Application to VIGIL |
| --- | --- | --- |
| [RobotAgentBench](https://github.com/AetherLabsAI/RobotAgentBench) | Explains task scope first, offers a CPU-only catalog, then walks through one concrete task and its required resources | Put the eight families before setup; add an offline catalog; keep a one-episode path before batch evaluation |
| [EmbodiedBench](https://github.com/EmbodiedBench/EmbodiedBench) | Describes supported environments and model access separately; exposes shared environment interfaces | Keep one evaluation path behind CLI and UI, with explicit provider and simulator setup |
| [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) | Separates dataset acquisition, task inspection, training and evaluation | Make included source data versus external simulator assets explicit; keep task inspection independent of evaluation |
| [ESI-Bench](https://github.com/ESI-Bench/ESI-Bench) | Makes task data and execution code visible as distinct parts of the repository | Preserve `data/` assets and the `vigil/` runtime namespace, with a short repository map |
| [Embodied First Exam](https://github.com/mll-lab-nu/embodied-first-exam) | Explains its task/execution contract before directing users into its harness | State RGB-only observations, pixel actions, terminal reports and W/B before advanced reproduction details |

These projects use different embodiments, simulators and agent interfaces. Their
dependencies and execution settings are not copied into VIGIL.

## Findings and changes

**P1 — Several paths looked like the main starting point.** `start.sh`, installed
UI, `quickstart.sh`, evaluation wrappers and reproduction scripts appeared across
flat documentation. The former quickstart also installed development packages
and ran the entire test suite. That is unnecessary work for someone inspecting
a recording or evaluating a model. The READMEs now show one progression: replay,
catalog, install/configure, one episode, inspect, then scale up. Ordinary users
need the public CLI; maintenance helpers live under four purpose-specific folders.

**P1 — Documentation navigation mixed current operations with review history.**
The previous map presented more than twenty equally weighted rows. Guides,
contracts, contributor instructions and historical reviews now have separate
directories and an audience-oriented index. The obsolete architecture redirect
was removed, and script references/imports/export allowlists were updated.

**P1 — Model setup required hand-editing JSON for the first run.** `vigil init`
now accepts `--model` and `--base-url`. It preserves exclusive file creation and
owner-only permissions, rejects credentials embedded in URLs, and leaves keys
in the caller's environment. The blank template and native-provider defaults
remain supported. The UI uses the same configuration and evaluator contracts.

**P1 — Installed UI and source launchers had different default port behavior.**
`vigil ui` now chooses an available loopback port, matching `bash start.sh`.
An explicit `--port` still supports SSH forwarding. No evaluation is triggered by
opening the UI.

**P2 — Task listing did not explain the benchmark.** `vigil catalog` now shows
task families, examples, budgets and selected data coverage. It reads executable
episodes: pack rows can have abbreviated scene metadata and must not be used to
infer the simulator distribution. `--task-family`, `--max-episodes` and `--json`
support focused inspection. Missing executable data fails with a nonzero exit.

**Assistant placement follows the requested project convention.** All coding
instructions are in `.agent/AGENTS.md` and `.agent/skills/`; there is no root
AGENTS.md. README and the contributor guide link to that location. Tools that only
auto-discover root instructions must be explicitly directed to `.agent/AGENTS.md`.

## Architecture decision and limits

### Follow-up code review

Three reproducible boundary bugs were corrected after the layout change:

- **P1 — A missing run status bypassed report verification.** Passing a directory
  with only an old aggregate printed final-looking W/B and exited successfully.
  `vigil/cli.py` now requires `run_status.json` for run directories and files
  beside run artifacts. Independent aggregates remain inspectable with an
  unverified label and display-field validation in `vigil/eval/reporting.py`.
- **P1 — Working-directory files could replace executable tasks.** An unrelated
  file named after a pack episode took precedence over `--episode-root` in
  `vigil/data/paths.py`. Pack catalog, diagnostics, fingerprinting and execution
  now resolve only from that root. Subprocess workers receive the resolved task
  file; direct `run-episode` file input is retained.
- **P2 — Global UI configuration selection was discarded.**
  `vigil --config selected.json ui` opened `vigil.json` because the subparser's
  default overwrote the explicit global value. `vigil/cli.py` now preserves it,
  carries custom `init` paths into the UI suggestion, and rejects the previously
  ignored UI `--no-config` option with actionable guidance.

Regressions cover both worker paths, configuration flag positions, a missing run
status, independent summaries and invalid counts/rates. These are offline tests;
they do not establish live model or simulator performance. Runtime fingerprints
change with these fixes: use a fresh output directory rather than modifying a
stored experiment fingerprint.

### Retained structure

Keep `vigil/agent`, `eval`, `data`, `envs` and `web`. They separate model input,
evaluation truth, loading, simulation and presentation. Their module count alone
does not justify merging scoring, settlement or transport code. The changes here
organize entry points and ownership without adding a second runner, rewriting
metrics, or changing prompts, images, action parsing or coordinates.

Validate catalog/configuration behavior, import boundaries, launcher behavior,
all local documentation links, the source exporter and the full offline suite.
Test the wheel outside the checkout and verify the bundled RGB replay. Those
checks do not establish new simulator execution or model quality. Scene source
revisions, the fixed simulator environment and other outstanding publication
items remain in the [release checklist](../development/RELEASE_CHECKLIST.md).
