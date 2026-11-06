# Third-Party Notices

Original VIGIL code, task definitions and benchmark annotations are licensed
under [Apache-2.0](../LICENSE). This file identifies upstream components and data
sources used by VIGIL. Redistributed third-party materials retain their upstream
copyright and license; the project license does not replace those terms.

## Scene specifications

VIGIL scene preparation uses ProcTHOR-compatible house specifications and
imports from the ProcTHOR-10K dataset, projects maintained by the Allen Institute
for AI. This source distribution contains 456 selected `house.json` scene
specifications under `data/scenes/`, alongside VIGIL task and scene-setup
configurations under `data/episodes/`.

Retain the relevant upstream attribution and license files with redistributed
scene material. File-specific provenance and adaptation history belong in the
release review record; the license snapshots below are not dataset revision
identifiers.

- [ProcTHOR-10K dataset](https://github.com/allenai/procthor-10k)
- [ProcTHOR generator](https://github.com/allenai/procthor)
- ProcTHOR: Large-Scale Embodied AI Using Procedural Generation, Deitke et al.,
  NeurIPS 2022.

## External runtime

VIGIL optionally uses the [AI2-THOR](https://github.com/allenai/ai2thor) Python
client. The Python client, Unity players and Unity asset bundles are installed
separately and are not included in this source archive. Their respective license
and attribution files remain applicable to those installations.

Direct Python dependencies are declared in `pyproject.toml`. The exact resolved
versions and transitive dependencies must be recorded for the environment being
reviewed. Model endpoints and checkpoints are configured externally; this
archive contains no model weights.

## Preserved upstream license copies

These files are unmodified snapshots of the upstream Apache License 2.0 texts,
retrieved from the following fixed repository commits:

| Upstream project | Included license | Source snapshot |
| --- | --- | --- |
| ProcTHOR-10K | [License](procthor-10k-LICENSE.txt) | [439193522244720b86d8c81cde2e51e3a4d150cf](https://github.com/allenai/procthor-10k/blob/439193522244720b86d8c81cde2e51e3a4d150cf/LICENSE) |
| ProcTHOR | [License](procthor-LICENSE.txt) | [53d5bd4c8c96a699e6a615dc390abb670cc9d353](https://github.com/allenai/procthor/blob/53d5bd4c8c96a699e6a615dc390abb670cc9d353/LICENSE) |
| AI2-THOR | [License](ai2thor-LICENSE.txt) | [24f79883b4889e3f0e6f4ae301808b9025872dfc](https://github.com/allenai/ai2thor/blob/24f79883b4889e3f0e6f4ae301808b9025872dfc/LICENSE) |

The AI2-THOR license text includes the upstream copyright notice:
Copyright 2021 Allen Institute for AI.
