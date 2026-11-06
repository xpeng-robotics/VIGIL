[Documentation](../README.md) / [Review archive](README.md)

# Revised pack comparison — 2026-11-03

**Follow-up:** the revised selection and nine Drawer repairs are now the default;
see [the adoption record](REVISED_DATA_ADOPTION.md). Counts and unchanged-data
statements below describe the earlier review snapshot.

The requested upstream baseline is
[`mixed_mainline_manual_revised_1000.json`](https://github.com/XPeng-RL/vigil/blob/342aff69e15c0d6fa2ca969b7105d91c329cdbad/data/benchmark/packs/mixed_mainline_manual_revised_1000.json)
at commit `342aff69e15c0d6fa2ca969b7105d91c329cdbad`. This review downloaded only the
selected definitions, houses and revision reports. It did not overwrite the
current release's default `mixed_mainline_manual_first_balanced_1000_v1.json`.

## Exact differences

| Item | Current release data | Requested revised data |
| --- | ---: | ---: |
| Tasks | 1,000 | 1,000 |
| Tasks per family | 125 | 125 |
| iTHOR / ProcTHOR tasks | 265 / 735 | 258 / 742 |
| Referenced ProcTHOR houses | 465 | 456 |
| Episode JSON size, decimal MB | 3.6254 | 3.631858 |
| House JSON size, decimal MB | 39.824466 | 38.606812 |

The selections share **962 task IDs**, with 38 removals and 38 additions. Among
the shared IDs, **961 executable episode files are byte-identical**. Only
`procthor_toilet_seed548_T4_hard_toilet_001__mainline` changes its initial pose and
corresponding setup teleport. All shared pack rows match after excluding the
upstream `source_tag` construction annotation; that annotation is absent from the
current public manifest.

There are 444 shared house references. Of these, 28 files differ byte for byte:
27 contain actual JSON-value changes, including asset substitutions and object
placement/state changes; one changes formatting only
(`procthor_sm_reveal_pick_box_keychain_seed461`). The revised selection adds 12
house references and removes 21.

The changes affect **82 revised tasks' execution inputs**: 38 added tasks plus
44 shared tasks with changed scenes and/or definitions. The toilet pose change
is already in those 44. This set exactly matches the upstream
`mixed_mainline_manual_revised_1000_data_fixes.json` list. Including the
formatting-only house change, 83 tasks have different input-file hashes.

| Family | Replaced tasks |
| --- | ---: |
| PG | 0 |
| DA | 2 |
| VS | 0 |
| SV | 2 |
| AI | 10 |
| SI | 4 |
| SM | 10 |
| CR | 10 |

Two added SM tasks have explicit budgets that differ from the old family-wide
30-step value: `procthor_sm_pick_place_egg_plate_seed355` has 35 steps, and
`procthor_sm_pick_place_box_dining_table_seed343` has 45. Preserve these source
budgets when adopting the revised data.

## Remaining defects and misleading metadata

The revised selection removes the open-state Dresser seed297 task. The other
**nine known Dresser failures retain identical episode and house files**;
switching packs does not repair them. Closed-state seed314 also retains the
incorrect initial pose described in the [runtime audit](../reference/RUNTIME.md).
The inspected upstream adapter still records failed setup actions and continues;
it has no Dresser-to-Drawer target repair.

The upstream revision report's headline counts describe 36 replacements. The
actual pinned pack has 38: the additional DA replacements remove the iTHOR
FloorPlan307 tennis-racket and FloorPlan312 mirror tasks and add
`procthor_da_boots_seed682` and `procthor_da_house_plant_seed209`.
The pack's internal ID is still
`mixed_mainline_manual_first_balanced_1000_v1_assetfix14`, despite its revised
filename. Use the pinned commit and file hashes to identify the data precisely.

## Validation and adoption boundary

All 1,000 revised executable definitions load with the current public loader;
all 456 referenced houses are present. The public `validate-pack`, complete
catalog and a three-task `run --dry-run` pass against the revised paths.
The generic public-content scan reports no findings in the 1,462 selected source
files; this does not replace the final exact-export/privacy review. These are
static checks, not fresh model rollouts or full simulator validation.

The historical main-paper check intentionally rejects the revised pack with
`Canonical pack checksum mismatch`. Earlier 20/20 historical alignment therefore
applies to the old frozen pack. Do not edit the expected checksum or relabel old
scores to present them as revised-pack results.

Adoption must synchronize the pack, executable definitions and houses together,
update the canonical selectors and coverage/provenance documents, and use a new
experiment identity. Correct the nine remaining Dresser definitions on that
baseline and finish simulator acceptance before claiming release readiness.

Local comparison artifacts are retained under `outputs/revised-pack-review/`,
excluded from the public export: `data-comparison.json`, `execution-impact.json`,
`episode-diff.csv`, the pinned upstream subset and CLI/checker logs.
