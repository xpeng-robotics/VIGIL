[Documentation](../README.md) / [Review archive](README.md)

# Original scene initialization audit

This is the 2026-11-03 audit of the original selection, before the versioned
Drawer corrections and revised default pack. Its counts and unchanged-data
statements describe that snapshot. For current status, read the
[runtime reference](../reference/RUNTIME.md) and
[revised data adoption](REVISED_DATA_ADOPTION.md).


This section records the **original pack audit before the versioned correction**.
Its counts and unchanged-data statements describe that earlier snapshot.

The initial 2026-11-03 review found that the original candidate was **not validated for
a complete 1,000-task live run**. The local initialization audit and targeted
follow-up cover 492 distinct tasks: 482 pass and 10 fail; the remaining 508 have
not completed this audit. Passing means scene/setup initialization, not successful
model execution or solvability.

All ten confirmed failures are SV tasks whose target is a non-openable `Dresser`,
but whose setup requests `OpenObject` or `CloseObject`:

| Requested state | Scene seeds |
| --- | --- |
| Closed | 212, 244, 314, 346, 611 |
| Open | 109, 276, 297, 346, 459 |

Their episode IDs follow
`procthor_sr_check_{closed|open}_dresser_seed<seed>_S4_{hard|easy}_dresser_check_{closed|open}_001__mainline`.
All ten fail on both cached OSXIntel64 builds
`f0825767cd50d69f666c7f282e54abfe58f1e917` and
`4d2e1f1d04051fafcd9794b810f227551121253a`, using the same AI2-THOR 5.0.0 client.
The exact targets report `openable=false`, `isOpen=false`, `openness=0.0`.
The [upstream object-type reference](https://ai2thor.allenai.org/ithor/documentation/objects/object-types/)
also distinguishes Dresser from openable Drawer objects. A separate canonical
Drawer task with object ID `Dresser|4|1___6` passes on both builds; an ID containing
"Dresser" alone does not establish this defect.

The historical adapter recorded failed setup actions and continued. Historical
score agreement therefore does not establish valid scene initialization. In the
two inspected complete references (Gemini 3.1 Pro Preview and InternVL3.5-38B),
four of these ten tasks have saved W=1/B=1. The current guard stops before a model
call instead of accepting an unsupported property's default as a valid setup.

Original task/house files, archived scores and metric denominators remain
unchanged. These task definitions require a versioned correction and renewed
validation before full-pack release readiness can be claimed. Switching between
the two tested builds does not resolve this blocker.

### Repair scope established by local diagnostics

All ten affected Dresser objects contain separate, openable Drawer objects.
In the generated scenes, a parent ID such as `5|1` has child IDs such as
`5|1___0`; the parent itself remains non-openable. Correcting only the object-type
label is insufficient: the setup action, oracle, report target, instruction and
task annotations must all reference the same actual drawer.

Eight scenes have visible child drawers at the recorded pose. The closed-state
seed314 and open-state seed297 tasks have no visible child drawer; their nearest
target drawers are approximately 8.6 m and 5.3 m away. Those two need an explicitly
recorded, reachable initial pose that meets the SV visibility/distance contract.
Do not hide this correction in automatic runtime teleport recovery.

Two isolated candidates demonstrate the binding repair: open-state seed109 uses
`5|1___0`, and closed-state seed244 uses `4|0___1`, each its dresser's top drawer.
Both pass real cached-Unity initialization with their original house and pose.
For each candidate, a scripted correct report yields W=1/B=1, an incorrect report
yields W=1/B=0, and uncached settlement/scoring recomputation agrees. These four
scripted checks are feasibility evidence, not model evaluation or acceptance of
all ten corrections. The canonical tasks and historical results are unchanged.

The recommended correction is a new pack version with explicit old-to-new task
mapping and hashes. Retain 1,000 tasks, 125 per family and the original budgets;
review the exact drawer descriptions against rendered RGB before freezing it.
Finish auditing the remaining original tasks before closing the correction list,
then validate the corrected full pack. Corrected task observations require new
rollouts; relabeling old reports or rescoring old traces cannot reproduce them.
