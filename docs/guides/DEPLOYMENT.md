[Documentation](../README.md) / Guides

# Local and cloud deployment

VIGIL has three pieces: the browser workbench, the simulator/evaluator process,
and the model endpoint. The browser can reach a remote workbench through SSH;
the evaluator can call a local or remote model API. Moving the model to the cloud
does not remove the evaluator's rendering requirement.

| Setup | Evaluator and renderer | Model | Browser access |
| --- | --- | --- | --- |
| Recorded replay | Local Python; no renderer needed | None | Local `vigil ui` |
| Desktop with API | Local compatible Linux/macOS | Existing remote API | Local `vigil ui` |
| Cloud evaluation host | Existing Linux GPU VM or allocated machine | Existing API | SSH tunnel to remote UI |
| Self-hosted model | Local or cloud rendering host | One or more GPU model replicas | Same UI and CLI |

The commands below run on machines you already have. The release does not provision
VMs, submit scheduler jobs, or expose a public multi-user service. The local API
experiment and recorded replay have been exercised. A clean Linux installation
also passed three scripted scenes using Xvfb/Mesa software rendering; see the
[runtime reference](../reference/RUNTIME.md). Cloud GPU and multi-GPU recipes
still require validation on the chosen hardware and serving stack.

## Existing remote API

After [installation](INSTALLATION.md), open `vigil ui`, enter the endpoint, model
and key, and run the initially selected single task. Alternatively:

```bash
vigil init
# Fill in vigil.json with your endpoint, model and key.
vigil doctor
vigil smoke --out-dir outputs/api-smoke
vigil verify-run outputs/api-smoke --require-frames
```

OpenAI-compatible endpoints accept a root, a prefix ending in `/v1`, or the full
`/chat/completions` route. For a native Gemini or Anthropic endpoint choose that
backend explicitly; URL shape alone does not select an API format. A custom
authentication header belongs in `api_key_header`. Configuration priority is
CLI > configuration file > environment > defaults. See [API details](MODEL_EVAL.md).

## Existing headless cloud machine

Copy or extract the release on the host; do not copy a local virtual environment
between operating systems. On a Linux host with Python 3.10+, GPU drivers and Vulkan:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[thor]"
export VIGIL_THOR_PLATFORM=cloud
vigil init
# Configure the model on this host.
vigil doctor --check-simulator
vigil ui --no-open --port 8765
```

From your laptop, in another terminal:

```bash
ssh -N -L 8765:127.0.0.1:8765 user@your-cloud-host
```

Open `http://127.0.0.1:8765` on the laptop. Configuration and results are saved on
the cloud host. The workbench binds to `127.0.0.1`; it has no `--host 0.0.0.0`
option. Keep the server terminal alive, or run it inside an existing terminal
multiplexer. Closing the browser does not stop a run; **Stop run** or Ctrl+C on
the server stops its own child run. Files from completed episodes are retained.

To copy a completed run for local replay:

```bash
rsync -a user@your-cloud-host:/path/to/release/outputs/my-run/ outputs/my-run/
vigil verify-run outputs/my-run --require-frames
vigil ui --results-dir outputs/my-run
```

Copy traces, scores, aggregate, run status and frames together. Review logs and
model metadata before sharing outside your group. Run paths are not required to
match on the laptop; replay locates frames inside the copied run directory.

For 16 concurrent episodes on two already assigned rendering GPUs:

```bash
vigil run --workers 16 --render-concurrency 16 --boot-concurrency 4 \
  --render-devices 0,1 --out-dir outputs/two-render-devices
```

This limits each GPU to eight live renderer processes. Raising workers alone
does not distribute rendering across devices. Validate the chosen renderer load
with a smaller selection before the full pack; a simulator timeout is an
infrastructure failure and cannot be included as a model task failure.

## Self-hosted multi-GPU model

Use a serving environment compatible with the chosen multimodal model and
accelerators. vLLM is deliberately not a mandatory VIGIL dependency. A four-GPU
example in that environment is:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 vllm serve /path/to/vision-language-model \
  --served-model-name my-vlm \
  --tensor-parallel-size 4 \
  --host 127.0.0.1 --port 8000
```

In the evaluation environment, use `openai-compatible`, model `my-vlm`, base URL
`http://127.0.0.1:8000/v1`, and an empty key if this loopback server has no
authentication. For a server on another host, use your existing private routing
or an SSH tunnel. Set `supports_json_mode` to `false` if the server does not
support that response-format option. Test one actual image episode before scaling.

For a temporary server and evaluation in one lifecycle, after vLLM is installed
in the active environment:

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 bash scripts/deploy/run_vllm_local.sh \
  --model-path /path/to/vision-language-model --model-name my-vlm \
  --tensor-parallel-size 4 \
  -- --no-config --max-episodes 1 --out-dir outputs/local-model-smoke
```

The helper waits for readiness, runs the public evaluation command, then stops
its own server process. Arguments before `--` configure serving; arguments after
it configure evaluation. `--no-config` avoids inheriting another model's local
configuration. Serving-specific options can be passed with repeated
`--vllm-arg`, one token at a time. Inspect the installed `vllm serve --help` for
model-specific template and parser options; changing a template is a serving
choice, not a benchmark prompt patch. Do not apply one template to an entire
model family without checking the exact model and server version.

Tensor parallelism splits one model across GPUs. It is independent of VIGIL's
`--workers`, which schedules concurrent episodes. vLLM also supports pipeline
parallelism and multi-node deployments; the upstream guide explains the separate
cluster setup. This release's helper does not initialize a multi-node cluster.
See [vLLM parallelism and scaling](https://docs.vllm.ai/en/stable/serving/parallelism_scaling/).

When a model fits comfortably on fewer GPUs, multiple serving replicas may provide
more independent request capacity. Put equivalent replicas behind an existing
endpoint, or use the compatible backend's comma-separated `VIGIL_MODEL_BASE_URLS` setting with
`--no-config` and no single `base_url` override. Keep weights, template and
generation settings identical. Check your installed backend documentation in
[CLI usage](../reference/USAGE.md) before configuring multiple URLs. The evaluator does not
allocate GPUs or balance renderer placement across machines.

For the pool, configure `VIGIL_MODEL_BASE_URLS` as comma-separated compatible API
URLs and `VIGIL_MODEL_NAME` as the same model on every replica, then use
`vigil run --no-config --workers 8 --render-concurrency 8 --out-dir outputs/replicas`.
Each isolated worker starts at a different offset in the list and rotates its
requests. This is request distribution, not a global load balancer or rate limiter.

## What to record

Save the code/release version, `run_config.json`, selected episode IDs, package
versions, renderer platform, model/weights revision, serving engine version,
template, generation settings, retries and concurrency. Preserve original task
budgets for benchmark comparisons. See [efficient evaluation](EVALUATION.md) for
render limits, recovery and manual distribution across evaluation machines.
