[VIGIL](../README.md) / Documentation

# Use VIGIL

Start with a recording, then run an evaluation or examine the paper's evidence.

### Explore

[Open the workbench](guides/WORKBENCH.md) to inspect recorded RGB, actions and
outcomes. Python 3.10+ is enough; the examples need no model or simulator.

### Evaluate

[Run your first episode](guides/EVALUATION.md), verify its evidence, then scale
up. The guide leads through environment setup, model connection and recovery.

### Paper results

[Review the paper results and evidence](reference/PAPER_ALIGNMENT.md).
Counts, audit summaries and checking scripts are included. Rerunning historical
score checks requires the original trajectory archives, which are not bundled.

<details>
<summary><strong>Setup and playback</strong></summary>

- [Installation](guides/INSTALLATION.md) — choose the environment for your workflow.
- [Model connection](guides/MODEL_EVAL.md) — configure a local or hosted vision model.
- [Deployment](guides/DEPLOYMENT.md) — use a separate simulation or inference host.
- [Saved results](guides/TRACE_ANALYSIS.md) — replay, verify and rescore trajectories.
- [Film and hardware recordings](DEMOS.md) — video playback and the chaptered player.
- [Troubleshooting](guides/TROUBLESHOOTING.md) — start from the symptom.

</details>

<details>
<summary><strong>Benchmark reference</strong></summary>

| Reference | Covers |
| --- | --- |
| [Task data](reference/DATA.md) | Current tasks, scene coverage and revisions |
| [Scoring](reference/SCORING.md) | W, B, reports and failure outcomes |
| [Commands](reference/USAGE.md) | CLI options, settings and outputs |
| [API contracts](reference/API_ALIGNMENT.md) | Images, coordinates, parsing and retries |
| [Simulator environments](reference/RUNTIME.md) | Tested platforms and runtime scope |
| [Historical metrics](reference/METRIC_ALIGNMENT.md) | Archived scoring checks and their limits |
| [Camera-ready evidence](reference/CAMERA_READY_AUDIT.md) | Companion analyses and provenance |
| [Feedback corrections](reference/FEEDBACK_CORRECTION.md) | Revised retry counts |

</details>

<details>
<summary><strong>Contribute and maintain</strong></summary>

Start with [Contributing](development/CONTRIBUTING.md) and the
[architecture map](development/ARCHITECTURE.md). The [release checklist](development/RELEASE_CHECKLIST.md)
and [security guide](development/SECURITY.md) cover publication checks.

The [maintainer tools](../scripts/README.md), [assistant instructions](../.agent/AGENTS.md)
and [changelog](development/CHANGELOG.md) support development. The
[review archive](reviews/README.md) preserves historical findings; the
[film evidence map](VIDEO.md) and [recording catalog](../examples/recorded-runs/README.md)
identify the sources and conditions of each demonstration.

</details>

[中文入门](README.zh-CN.md) · [Get help](../.github/SUPPORT.md)
