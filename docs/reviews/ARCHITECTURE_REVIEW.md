[Documentation](../README.md) / [Review archive](README.md)

# Architecture review and corrections

The earlier candidate improved file names but did not enforce dependency boundaries.
This review separates repository layout, import behavior and benchmark semantics.

## Findings and concrete triggers

| Severity | Previous issue | Trigger and consequence | Correction |
| --- | --- | --- | --- |
| P1 | Package initialization loaded the whole implementation | Importing `AgentObservation` loaded 67 VIGIL modules, including the episode runtime and simulator adapter. A broken installed simulator could prevent agent-only tools and recorded replay from importing. | Root exports resolve on demand. Optional AI2-THOR imports occur only when a caller explicitly constructs the simulator. Cold-process tests prohibit optional runtime imports. |
| P2 | Offline state handling depended on execution | `eval/state.py` imported `resolve_episode_path` from the runner; the UI imported state helpers and inherited the runner's dependencies. | Task resolution belongs to `data/paths.py`. Offline CLI and recorded-workbench tests assert the simulator adapter and episode runner never load. |
| P2 | Environment code imported the evaluator | `envs/thor.py` depended on `eval/judge.py` and `eval/types.py`, while the runner depended on the environment. | Pure task-condition functions live in `data/conditions.py`; environment results live in `envs/types.py`. No environment module imports evaluation code. |
| P2 | CLI owned the execution scheduler | Resume, workers, cancellation, subprocess checks and aggregation lived inside the roughly 800-line CLI. | `eval/batch.py` owns pack execution; the CLI parses arguments, dispatches and presents results. The UI still uses this same CLI. |
| P2 | Unnecessary global module aliases obscured ownership | `_compat.py` installed 30 historical names into `sys.modules` and mutated package attributes on every import. | Removed pre-publication aliases. Documented root Python APIs and CLI commands remain; old internal paths have explicit migration guidance. |
| P3 | Physical layout and asset lookup were coupled | Paths used directory-depth calculations that had to change whenever a module moved. | A flat `vigil/` package and `vigil/paths.py` define package/source roots. Wheel tests run outside the checkout to detect accidental source-asset fallback. |

The former source locations were `src/vigil/__init__.py`, `src/vigil/_compat.py`,
`src/vigil/eval/state.py`, `src/vigil/envs/thor.py` and `src/vigil/cli.py`.
The current implementation is linked from [Architecture](../development/ARCHITECTURE.md).

## Why keep the package name?

`vigil` is the Python import namespace, not an extra execution layer. The repository
now uses `vigil/agent`, `vigil/eval`, `vigil/data`, `vigil/envs` and `vigil/web`
directly under its root. Removing the outer `src/` directory simplifies browsing
and allows `python -m vigil` from a fresh source checkout without installation.
The wheel still provides `import vigil` and the `vigil` executable.

Publishing generic top-level packages named `agent`, `data` or `eval` would spread
one project across common import names. Mapping a physical `src/agent` tree to
`vigil.agent` would also require extra source-launch/import machinery. The chosen
layout keeps physical paths and package names aligned. Both flat and src layouts
are supported by [PyPA](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/);
[setuptools](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html)
also recommends keeping package names and directories aligned.

Flat layout can hide missing wheel assets when tests run from the checkout.
Consequently, package discovery explicitly includes only `vigil` and `vigil.*`,
and release checks install the wheel in a separate environment and run it from
another directory, with no source tree on PYTHONPATH.

## Verification requirements

- Cold Python subprocesses exercise agent imports, task-condition evaluation,
  offline CLI commands, dry selection and recorded-workbench loading while a
  guard refuses AI2-THOR and other optional runtime packages.
- Import-boundary tests cover imports inside functions as well as module headers.
- CLI, backend, cancellation, launcher, settlement, scoring, integrity and
  historical alignment tests remain part of the complete offline suite.
- Pure condition functions and model prompt/request bodies retain their previous
  logic; extracting them must not alter saved trace settlement or score fields.
- The source launcher, editable installation and built wheel must resolve the
  correct UI, recorded evidence and external data from unrelated working directories.

This review does not establish a fresh simulator run, full model evaluation or
paper reproduction. Large historical judge/scoring functions remain explicit
contract implementations; further splitting should follow contract boundaries,
not an arbitrary file-size target. The batch service currently consumes the
validated CLI options; a separate typed batch API is not promised by this release.
