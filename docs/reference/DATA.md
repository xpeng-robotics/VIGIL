[Documentation](../README.md) / Reference

# Data

The default is `mixed_mainline_manual_revised_1000_v2`: the pinned upstream
revised selection plus nine explicit Drawer-target corrections. See the
[adoption record](../reviews/REVISED_DATA_ADOPTION.md), the original
[comparison](../reviews/REVISED_PACK_COMPARISON.md), and the machine-readable
[correction manifest](../../data/provenance/task_corrections.json).

The source release contains one canonical benchmark pack, its 1,000 executable
episode JSONs, and the 456 ProcTHOR house specifications needed by those episodes:

```text
data/benchmark/packs/mixed_mainline_manual_revised_1000_v2.json
data/episodes/<episode_id>/episode.json
data/scenes/<scene_ref>/house.json
```

## Task families

| Family | What the agent does | Tasks | Step budget |
| --- | --- | ---: | ---: |
| PG — Pixel grounding | Select the instructed object in the image | 125 | 5 |
| DA — Distance approach | Move close enough to the target | 125 | 12 |
| VS — View search | Find a target outside the initial view | 125 | 20 |
| SV — State verification | Inspect and report an object's state | 125 | 5 |
| AI — Approach and interact | Approach a visible target and change its state | 125 | 25 |
| SI — Search and interact | Find an unseen target, then interact | 125 | 35 |
| SM — Sequential manipulation | Complete an ordered manipulation sequence | 125 | 30–45 |
| CR — Constraint resolving | Resolve a dependency before the target action | 125 | 40 |

Each family contains 125 tasks. Simulator binaries and model weights are installed separately.

## Coverage and size

Inspect coverage and task examples directly from the executable definitions:

```bash
python -m vigil catalog
python -m vigil catalog --task-family SI --json
```

These commands do not start a model or simulator. A wheel-only installation needs
`VIGIL_DATA_ROOT` pointing to the extracted release data.

The 0.1.0 canonical pack is balanced across eight task families, with 125 tasks
per family. It is **not balanced between simulators**:

| Task family | iTHOR tasks | ProcTHOR tasks | Total |
| --- | ---: | ---: | ---: |
| PG — Pixel grounding | 17 | 108 | 125 |
| DA — Distance approach | 39 | 86 | 125 |
| VS — View search | 16 | 109 | 125 |
| SV — State verification | 29 | 96 | 125 |
| AI — Approach and interact | 23 | 102 | 125 |
| SI — Search and interact | 22 | 103 | 125 |
| SM — Sequential manipulation | 87 | 38 | 125 |
| CR — Constraint resolving | 25 | 100 | 125 |
| **Total** | **258** | **742** | **1,000** |

The tasks reference **67 distinct iTHOR scene names and 456 ProcTHOR house
specifications**: 523 runtime scene identifiers/specifications. Multiple tasks can
use the same scene. This count does not establish 523 unique floor-plan geometries.
Count ProcTHOR scenes by the resolved `scene_ref`; many use the generic
`scene_id: "Procedural"` and would otherwise collapse into one entry.

The scene JSONs occupy approximately 38.6 MB and executable definitions 3.6 MB
(uncompressed, decimal MB). Recorded examples and presentation media add to the
source archive. `docs/development/release_manifest.json` records file paths and SHA-256 hashes for
each exported copy; archive sizes depend on compression. A wheel contains code,
UI and the two-episode demo, without the full task or scene data.

SM budgets are 30 steps for 123 tasks, 35 for one, and 45 for one. Other family
budgets are unchanged. These revised inputs require new rollouts. The frozen
`data/reproduction/paper_v4_pack.json` remains available only for historical
score alignment; its old task selection must not be substituted into new runs.

The [revision comparison](../../data/provenance/revision_comparison.json) records
the current inputs against a retained pre-revision snapshot matching the frozen
paper IDs. Of 953 shared IDs, 909 retain equal episode/scene JSON and 44 have
changed inputs; there are 47 removals and 47 additions. Only 908 shared tasks
retain identical file bytes; one other task has a formatting-only house change.
Use these groups for diagnostics, without changing the current 1,000-task
denominator. See the [comparison scope](../reviews/REVISED_DATA_ADOPTION.md#compare-the-corrected-release-with-the-original-selection)
before attributing score differences to the model or evaluator.

Use the complete source archive for the simplest setup: extract it and run
`bash start.sh` with Python 3.10+. There is no need to download the full
ProcTHOR-10K dataset to execute these bundled tasks. If using a separately
installed wheel, set `VIGIL_DATA_ROOT=/path/to/extracted-release/data` for task
discovery. See [installation](../guides/INSTALLATION.md) for simulator setup.

## What the scene files contain

`house.json` stores room and wall geometry, doors, windows, object placement and
runtime asset identifiers. All 456 bundled houses declare schema `1.0.0`.
They do not contain Unity players, meshes or texture bundles. iTHOR scene names
resolve against the separately installed AI2-THOR runtime; no matching local
`house.json` is expected for those 67 scene names.

The simulator downloads/caches its runtime separately. A fresh offline machine
cannot render from the source archive alone. Model weights and model serving
software are also external. Recorded replay and offline scoring need neither
the simulator nor a model endpoint.

Episode files include the initial agent pose, setup actions, task instruction,
budgets and evaluator success conditions. These and the scene metadata are
evaluator inputs. The default model receives RGB observations and the public
interaction contract, not privileged scene or success-condition metadata.

## Provenance and validation scope

The public [scene provenance manifest](../../data/provenance/scenes.json) records
every house hash, source category and available index/seed. The 47 imported houses
match the parsed JSON values of ProcTHOR-10K `train` entries at
[revision 439193522244720b86d8c81cde2e51e3a4d150cf](https://github.com/allenai/procthor-10k/tree/439193522244720b86d8c81cde2e51e3a4d150cf).
The compressed source SHA-256 matches that revision's Git LFS object; the manifest
records the archive hash and individual indices. There are no parsed-value
differences between those entries and the bundled houses.

The remaining 409 generated scenes are distributed as frozen house snapshots.
These exact files, not regeneration from a seed, are the inputs for reproducing
evaluation. Available catalog seeds are retained as historical identifiers;
rebuilding the scene generator is outside this release's reproduction contract.
The raw authoring catalogs are excluded. See [third-party notices](../../licenses/THIRD_PARTY_NOTICES.md)
for upstream attribution and preserved license texts. Original VIGIL code, task
definitions and benchmark annotations use [Apache-2.0](../../LICENSE); redistributed
third-party materials retain their upstream terms.

The static audit parsed all 1,000 executable configs with the public loader and
resolved all 742 ProcTHOR task references to the 456 included houses. No required
house is missing, no unreferenced house is included, and all 456 house file hashes
are distinct. This proves file and reference completeness, not successful rendering
or task solvability on every supported runtime.

Two house files retain nonempty generation warnings about unreachable points:
`procthor_faucet_seed123` and `procthor_vacuumcleaner_seed366`. Each is used by one
PG task. The warned points differ from the prescribed initial positions. Both
tasks passed a targeted initialization, RGB and target-grounding check on the
[recorded macOS runtime](RUNTIME.md). This diagnostic used evaluator-only masks
to select a pixel, made no model calls, and does not validate every navigation
point or establish full-pack solvability. The warnings and task data are unchanged.
Full runtime coverage and frozen-reference score alignment remain separate
[release checks](../development/RELEASE_CHECKLIST.md).

## Pack Row Schema

Each `episodes` row contains fields such as:

- `episode_id`
- `sample_id`
- `task_family`
- `functional_template`
- `target_object_type`
- `scene_id`
- `scene_ref`
- `aux_difficulty`
- `primary_capabilities`

The executable episode config is resolved separately by `episode_id`, normally from:

```text
data/episodes/<episode_id>/episode.json
```

The same layout can be mirrored to Hugging Face later; the local runner assumes these relative paths unless `--episode-root` or `--scene-root` is overridden.

## Executable Episode Schema

A full episode JSON should contain:

- `episode_id`
- `scene`
- `agent_init`
- `scene_setup`
- `task`
- `budget`
- `success_condition`
- `trace_hints`

The release loader supports both canonical pack manifest rows and full executable episode configs.

## Trace Schema

A scored episode trace is a JSON object with:

- `episode_id`
- `profile`
- `max_steps`
- `terminal_status`
- `steps`

Each step may contain:

- `step_index`
- `action`: an object with `skill_name` and `arguments`
- `action_valid`
- `env_status`
- `judge_success`
- `progress` in `[0, 1]`
- `terminal`

The scorer treats task success as primary. `progress`, `action_validity`, and `efficiency` are reported as diagnostics for analysis.
