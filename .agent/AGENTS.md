# VIGIL project instructions

These instructions live in `.agent/AGENTS.md`; the repository root intentionally
has no AGENTS.md. Coding assistants must load this file explicitly through the
README or contributor guide, then follow the relevant `.agent/skills/` workflow.

## Purpose and first steps

Make the public release easy to install, run, inspect and reproduce. A new user
should reach the recorded RGB replay with `bash start.sh` or an installed `vigil ui`, then
configure a model and run one real episode before scaling up.

Read [README.md](../README.md), [the documentation map](../docs/README.md), and the guide
for the task at hand. Chinese onboarding is in [README.zh-CN.md](../docs/README.zh-CN.md).
Use the existing public CLI and workbench. Keep examples portable and independent
of private services. A downloaded release may have no Git history; do not assume
Git, a simulator, a model key or a GPU is installed.

## Common workflows

Use Python 3.10+. From the repository root, with the selected environment activated:

```bash
python -m pip install -e ".[dev]"
python -m pytest
vigil validate-pack
vigil catalog
vigil run --dry-run --max-episodes 3 --out-dir outputs/check-selection
vigil verify-run vigil/web/demo --require-frames
```

For visual inspection: `vigil ui`. For an existing experiment:
`vigil ui --results-dir /path/to/run` and `vigil verify-run /path/to/run`.
`--results-dir` only selects existing results; new UI runs use `--out-dir`
(default `outputs`). These inspection commands require neither an API key nor the simulator extra.
The source launcher needs only Python 3.10+ and selects an available local port;
`start.command` is the macOS entry. Keep launcher changes covered by their tests.
`vigil progress /path/to/run` reports saved progress; it does not validate metrics.

For an authorized live evaluation, install `.[thor]`, configure with `vigil init`
or the UI, check `vigil doctor`, then run `vigil smoke --out-dir outputs/new-smoke`.
An existing model endpoint is preferred when one is provided. Only start model
servers, allocate cloud resources, or run large evaluations when those operations
are within the user's requested scope. Reading or reviewing the code is not a
request to launch evaluation or GPU jobs. Continue already authorized work without
asking for the same permission again. Stop only processes owned by this work.

## Architecture and benchmark contract

- `vigil/agent/`: model agent, prompts, history, parsing and provider backends.
- `vigil/eval/`: episode execution, judging, settlement, scoring and inspection.
- `vigil/data/`: pack loading, path discovery, selection and pure task conditions.
- `vigil/envs/`: simulator adapters and rendering.
- `vigil/web/`: local workbench; launches the public CLI and reads shared scores.
- `vigil/cli.py`: argument parsing, command dispatch and presentation.
- `vigil/eval/batch.py`: shared pack execution, workers, recovery and cancellation.
- `vigil/eval/state.py`: fingerprints, resume and output locking.
- `data/`: canonical 1,000-episode pack, executable tasks and scene assets.

Keep imports directional: agent/data do not import eval/envs/web; envs does not
import eval; offline commands must not load the simulator. Optional AI2-THOR
imports belong at explicit adapter construction. Do not restore global historical
module aliases. Public root API symbols resolve lazily.

Read [the architecture map](../docs/development/ARCHITECTURE.md) for extension points. Project
skills live in `.agent/skills/`; load the matching file when working on that task:

- [Onboarding](skills/vigil-onboarding/SKILL.md): installation, README and UI startup.
- [Evaluation](skills/vigil-evaluation/SKILL.md): authorized runs and safe recovery.
- [Trace review](skills/vigil-trace-review/SKILL.md): evidence and W/B consistency.
- [Release](skills/vigil-release/SKILL.md): wheel/export assets and publication checks.

Preserve RGB-only model input and the episode-local history contract. Evaluator
state may appear in saved evidence and replay, but must not become model input.
Keep provider reasoning and inline think blocks out of subsequent assistant
history and correction requests. Validate parsed public actions before simulator
execution; parser success does not permit direct simulator calls or missing
required arguments. Never recover an executable action from an
unfinished reasoning block. Raw provider output belongs in trace evidence.
Structured decoding or native tool calling changes the experimental condition;
record it explicitly and validate the full request/response/history protocol.
Keep original task budgets by default (`--max-steps 0`). Do not silently change
prompts, action parsing, coordinate adapters, sampling or retry behavior to improve
scores. Record deliberate experimental changes and use a fresh output directory.

World completion W is `world_success_rate`; report-dependent success B is
`success_rate`. `mean_primary_score` is a different legacy composite. Simulator
and request failures are infrastructure failures, not valid failed task results.
Never expose stale aggregate scores as final while a run is incomplete.

Resume requires matching runtime, model, data and profile fingerprints. Do not
edit a stored fingerprint to bypass the check. `verify-run` checks saved evidence
consistency for the selected episodes; it does not prove a fresh simulator run,
full pack coverage or paper reproduction. Keep offline fixtures, recorded demos,
new live experiments and historical paper alignment clearly labeled.

## Implementation and verification

Keep the core and UI free of mandatory third-party runtime dependencies. Simulator
and development packages are optional extras. No frontend build, CDN or cloud
account should be needed to browse recorded results. Keep credentials out of
responses, logs, example files, screenshots and public exports. Do not print local
configuration files containing keys. Preserve user changes and existing results.

Run relevant tests for behavior changes. Scoring or contract changes require the
settlement, scoring, integrity and paper-alignment suites. CLI, backend or UI
changes require their corresponding suites. A release candidate requires the
complete offline suite and verification of the bundled demo. Offline tests can
open loopback sockets and local subprocesses; they do not require a model service.
Test the installed wheel from outside the checkout when changing package assets.

Update user-facing guides and [CHANGELOG.md](../docs/development/CHANGELOG.md) for public changes.
New root documents or helper scripts must be added to the allowlist in
`scripts/release/export_public_release.py`; new Python files and `docs/*.md` are collected
automatically. Export to a new directory, then run checks inside that exact copy:

```bash
python scripts/release/export_public_release.py /path/to/new-release
```

Keep machine-specific configuration and experiment output outside the export.
Do not publish or mark the release ready while the project license or publication
checks in [RELEASE_CHECKLIST.md](../docs/development/RELEASE_CHECKLIST.md) remain unresolved.
Report what changed, commands actually tested, evidence paths and remaining limits.

## Code Review Rules

Prioritize false success, dropped failures, changed metric denominators, leaked
privileged observations, mixed experiments, stale results, orphan processes,
credential exposure, broken installation and missing wheel/export assets.
Support findings with a concrete trigger and file location. Do not claim live
validation from mocked tests, syntax checks, a successful import or a text API ping.
