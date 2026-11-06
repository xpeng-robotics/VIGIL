<div align="center">

<p><strong>VIGIL · NeurIPS 2026 · Poster</strong></p>
<h1>Done, But Not Sure</h1>
<p>Disentangling World Completion from Self-Termination in Embodied Agents</p>

<p>
  <a href="https://arxiv.org/abs/2605.08747">Paper</a> &nbsp;·&nbsp;
  <a href="https://xpeng-robotics.github.io/vigil/">Project</a> &nbsp;·&nbsp;
  <a href="docs/README.md">Docs</a> &nbsp;·&nbsp;
  <a href="docs/README.zh-CN.md">中文</a>
</p>

</div>

https://github.com/user-attachments/assets/1bd9f83d-87c9-466e-b1d6-88cdfeb50ef2

<p align="center"><sub>2:32 · Benchmark overview</sub></p>

VIGIL is a benchmark for task completion and self-termination in embodied agents.
It tracks the world state and the agent's final report separately, revealing
premature success claims and tasks completed without a report.

The benchmark spans 1,000 episodes across eight task families in AI2-THOR, with
agents navigating and interacting through first-person RGB observations. This
repository includes the task pack, evaluation tools and a local replay workbench.

[Watch the real-robot demos →](docs/DEMOS.md)

## Try the recorded demo

With **Python 3.10+**, clone the repository and open the workbench:

```bash
git clone https://github.com/xpeng-robotics/VIGIL.git
cd VIGIL
bash start.sh
```

Choose **Explore a recorded run**, select an episode, then open **Replay** to
step through camera images, model actions and outcomes. This uses recordings
included in the repository; no package installation, model key or simulator is
needed. On macOS, `start.command` opens the same workbench.

Press **Ctrl+C** in the terminal to close the workbench before continuing.

## Run your own evaluation

You need a vision-capable model API and a Linux or macOS host that can run
AI2-THOR. Inference can run on a separate machine or through a hosted provider.
The commands below run from the cloned repository root.

### 1. Install evaluation support

Use a Python 3.10+ interpreter for `python3` below; substitute `python3.10` or
another supported interpreter if needed.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[thor]"
```

The task pack and scene files are included. The first simulator start may
download Unity runtime assets into `~/.ai2thor`.

On a headless Linux host with a working Vulkan renderer, select cloud rendering:

```bash
export VIGIL_THOR_PLATFORM=cloud
```

For driver requirements and Apple Silicon/Rosetta setup, follow the
[installation guide](docs/guides/INSTALLATION.md#rendering-platforms).

### 2. Connect your model

For an OpenAI-compatible vision endpoint, create a configuration:

```bash
vigil init --backend openai-compatible \
  --model YOUR_VISION_MODEL \
  --base-url http://127.0.0.1:8000/v1
```

Replace the model identifier and URL with those of your running model service.
The endpoint must accept images as well as text. If it requires authentication,
set the key in the same terminal:

```bash
export VIGIL_API_KEY="YOUR_API_KEY"
```

Settings are saved in `vigil.json`. If that file already exists, edit it or run
`vigil ui` and use **Run an evaluation → Save configuration**. The CLI and
workbench share these settings. Native Gemini/Anthropic APIs and local model
serving are covered in [model setup](docs/guides/MODEL_EVAL.md).

### 3. Run one episode

Check the configuration and renderer, then run one complete task:

```bash
vigil doctor
vigil doctor --check-simulator
vigil smoke --out-dir outputs/first-run
```

`doctor` checks local readiness; `--check-simulator` starts Unity and checks an
RGB frame. `smoke` runs the model, actions and scoring together on one task.
It uses your model API and saves the result under `outputs/first-run`.

For a browser workflow, run `vigil ui`, open **Run an evaluation**, choose
**Check setup**, then **Run 1 episode**. New UI runs get their own timestamped
directories under `outputs/`.

### 4. Inspect the result

For the command-line run above:

```bash
vigil verify-run outputs/first-run --require-frames
vigil report outputs/first-run
vigil ui --results-dir outputs/first-run
```

The workbench lets you replay observations and actions and inspect the final
report. Each run saves RGB images in `frames/`, episode records in `traces/`,
per-episode results in `scores/`, and an aggregate in `aggregate_score.json`.

| Result | What it measures |
| --- | --- |
| World completion (W) | Whether the task's world-state condition holds at episode closure. |
| Benchmark success (B) | Whether that condition holds and the required terminal report is correct. |

`verify-run` checks that saved evidence, scores and the aggregate agree. A task
failure can still be a valid evaluation result; an API or simulator error needs
to be resolved before the run has final benchmark metrics.

## Run a larger evaluation

After the first episode works, try a small batch:

```bash
vigil run --max-episodes 10 --workers 1 --out-dir outputs/my-model-10
```

For all 1,000 episodes, omit the episode limit:

```bash
vigil run --workers 1 --out-dir outputs/my-model-full
```

Both commands keep the original per-task step budgets and save frames for
replay. Increase `--workers` after checking renderer capacity and your API quota;
see the [evaluation guide](docs/guides/EVALUATION.md#understand-the-concurrency-controls)
for the corresponding renderer limits.

In another terminal with the same environment activated, check progress:

```bash
vigil progress outputs/my-model-full
```

To continue an interrupted run with the same model, code, data and settings:

```bash
vigil run --workers 1 --out-dir outputs/my-model-full --resume-existing
```

Completed, verified episodes are reused. Use a fresh output directory for a new
model or changed settings. Once the run finishes, use the same `verify-run`,
`report` and `ui --results-dir` commands with `outputs/my-model-full`.

These commands use the current benchmark release, including task and input-protocol
corrections made after the paper. The defaults are not an exact paper-reproduction
preset; see [benchmark versions and paper comparisons](docs/reference/PAPER_ALIGNMENT.md)
for the differences and the original archives needed for historical checks.

## Citation

<details>
<summary>BibTeX</summary>

```bibtex
@inproceedings{chen2026done,
  title     = {Done, But Not Sure: Disentangling World Completion from Self-Termination in Embodied Agents},
  author    = {Chen, Ying and Fang, Lihuang and Jiang, Rui and Wang, Mingxu and Gu, Zhifeng and Yi, Lei and Chen, Jie},
  booktitle = {Advances in Neural Information Processing Systems},
  year      = {2026},
  url       = {https://arxiv.org/abs/2605.08747}
}
```

</details>

## License

Original code, task definitions and annotations use [Apache-2.0](LICENSE).
Simulator, scene and model assets retain their upstream terms; see the
[third-party notices](licenses/THIRD_PARTY_NOTICES.md).
