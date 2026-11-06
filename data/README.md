# VIGIL Data

This release contains the canonical benchmark artifacts for 1,000 tasks across
eight families (125 tasks each):

```text
benchmark/packs/mixed_mainline_manual_revised_1000_v2.json
episodes/<episode_id>/episode.json
scenes/<scene_ref>/house.json
```

The pack contains 258 iTHOR tasks referencing 67 built-in scene names and 742
ProcTHOR tasks referencing 456 included house specifications. The scene JSONs
contain layouts and asset identifiers; AI2-THOR runtime binaries and 3D assets
are installed separately. The complete source archive bundles this data, while
the wheel includes only code, UI and the recorded example.

See [data coverage, size and validation limits](../docs/reference/DATA.md) and
[installation](../docs/guides/INSTALLATION.md). Original task definitions and
annotations use [Apache-2.0](../LICENSE); third-party material retains its upstream
terms. Per-scene source revision records remain a publication requirement.

The frozen `reproduction/paper_v4_pack.json` identifies historical score-check selections; it is not the current executable pack. Task corrections and hashes are recorded in `provenance/task_corrections.json`.

[Revision comparison](provenance/revision_comparison.json) records retained
pre-revision and current input hashes: 953 shared IDs, with 909 equal parsed
inputs and 44 changed inputs, plus 47 additions/removals. This metadata supports
diagnostic comparisons; it does not define a second executable pack or establish
which inputs a historical model run used.

Do not add raw construction data, review queues, other archived packs, or intermediate repair outputs to the public release tree.
