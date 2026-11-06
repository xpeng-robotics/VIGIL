[Documentation](../README.md) / [Review archive](README.md)

# Revised data adoption — 2026-11-03

The default executable pack is now `mixed_mainline_manual_revised_1000_v2`:
1,000 tasks, 125 per family, 258 iTHOR tasks and 742 ProcTHOR tasks, using
67 built-in scenes and 456 bundled houses. It adopts upstream revision
`342aff69e15c0d6fa2ca969b7105d91c329cdbad` and corrects the nine retained
non-openable Dresser targets. The earlier open-state seed297 task was already
removed by the upstream revision.

Each repaired task has a new ID ending in `__drawer_v2`. Setup, instruction,
report target, success condition and annotations bind the same real Drawer.
Only closed-state seed314 needs a new initial pose; that pose is frozen in its
definition. No runtime teleport fallback or scoring exception was added.
Original budgets are retained, including upstream's two SM exceptions at
35 and 45 steps. The other 123 SM tasks retain 30 steps.

| State | Scene seed | Drawer object ID | Visible description |
| --- | ---: | --- | --- |
| Closed | 212 | `4\|1___8` | Top-left drawer |
| Closed | 244 | `4\|0___1` | Top drawer |
| Closed | 314 | `4\|1___3` | Top-left drawer; corrected pose |
| Closed | 346 | `3\|2___9` | Top-left drawer |
| Closed | 611 | `4\|1___0` | Top drawer |
| Open | 109 | `5\|1___0` | Top drawer |
| Open | 276 | `5\|9___0` | Top drawer |
| Open | 346 | `3\|2___9` | Top-left drawer |
| Open | 459 | `4\|0___3` | Top-left drawer |

The [correction manifest](../../data/provenance/task_corrections.json) records
all old/new IDs and hashes, exact bindings, poses, visibility evidence and the
Unity build. The [scene manifest](../../data/provenance/scenes.json) covers the
47 imported and 409 generated frozen house snapshots.

All nine corrected observations were rendered and visually reviewed on the
[macOS reference runtime](../reference/RUNTIME.md). Each task then passed a
scripted correct report (W=1, B=1) and incorrect report (W=1, B=0). All 18 traces
agree with uncached settlement and score reconstruction. Authoring diagnostics
used evaluator metadata to identify drawers; models do not receive that metadata.
These checks establish the repairs' initialization/report behavior, not model
performance.

The full macOS initialization audit now covers all 1,000 tasks with zero failures:
527 fresh checks and 473 reused successful checks with identical episode/house
bytes, initialization code and Unity build. Every check requires successful
setup, nonblank 640 × 480 RGB, scene objects and all declared target IDs. This
does not establish navigation solvability or model success on every task.

A separate Linux Qwen3.6-27B smoke completed one real pixel-grounding task and
its terminal report (W=1, B=1). Downloaded frames, settlement and scores passed
independent local verification. The response contains native separated reasoning;
normalized coordinates are adapted to pixels before execution. This is one task,
not a full benchmark result.

The initial 16-worker Linux capacity attempt exposed one simulator timeout
during `TeleportFull`, before a model request. That task passes an isolated
reset on the second rendering GPU. This does not prove a single cause for the
timeout. The first attempt is retained as infrastructure evidence and cannot
qualify the full run. `--render-devices 0,1` allows eight renderer slots per GPU
at 16 total, but this Linux GPU configuration remains unvalidated at that scale.

On 2026-11-05, the new Qwen3.6-27B run completed all 1,000 corrected tasks with
eight local macOS simulator workers calling an existing model endpoint. It used
a fresh output directory under the reconciled runtime; the previous interrupted
run remains separate. W is 42.4% and B is 36.0%, with no unresolved infrastructure
errors. Uncached settlement, per-episode scores and aggregate scores agree.
All 14,714 RGB frames decode and match the recorded model inputs; all 4,686
recorded normalized-coordinate conversions match execution.
See [results, historical differences and exact request settings](../reference/METRIC_ALIGNMENT.md#2026-11-05-revised-pack-model-check).
This run does not establish 16-worker Linux GPU capacity. The separate clean
Linux CPU installation checks are described in the [runtime reference](../reference/RUNTIME.md).

The original paper selection is preserved byte-for-byte as
`data/reproduction/paper_v4_pack.json`; its target hashes and historical score
denominators are unchanged. Historical result checkers default to that manifest.
It is a score-audit selection, not a second bundled executable dataset. New
observations require new rollouts: renamed old traces cannot validate these fixes
or reproduce corrected observations. Historical table agreement and new-data
results must be reported separately.

## Compare the corrected release with the original selection

The [input comparison manifest](../../data/provenance/revision_comparison.json)
compares this corrected release with the retained pre-revision input snapshot.
That snapshot's IDs match the frozen paper selection; its presence does not
prove which working-tree bytes were executed for a historical result.

| Comparison group | Tasks |
| --- | ---: |
| Shared IDs | 953 |
| Shared IDs with equal episode and scene JSON | 909 |
| Shared IDs with changed execution inputs | 44 |
| Removed IDs / added IDs | 47 / 47 |

The 44 changed shared tasks reference 24 changed house specifications. Changes
include object asset identifiers and object/child positions. One task,
`procthor_toilet_seed548_T4_hard_toilet_001__mainline`, also changes its initial
pose and setup teleport. It is already counted among those 44. The nine Drawer
repairs have new IDs, so they contribute to the 47 removals/additions.

Of the 909 tasks with equal parsed inputs, 908 also have identical file bytes.
The house for `procthor_sm_reveal_pick_box_keychain_seed461` changes formatting
only. The manifest records both raw and normalized JSON SHA-256 values, each
shared task's classification, and the changed JSON paths. For iTHOR, equality
compares the declared scene configuration; simulator assets are external.

Report all 1,000 tasks for the current benchmark. The 909-task subset can help
diagnose historical score differences, while the 44 changed shared tasks and
47 additions need separate interpretation. Equal parsed inputs do not establish
equal observations, model checkpoints, serving settings or history behavior.
These groups do not establish an exact online reproduction of the paper run.
