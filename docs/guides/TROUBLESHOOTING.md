[Documentation](../README.md) / Guides

# Troubleshooting

Start with the symptom below. Commands assume the repository root and Python
3.10+; activate your environment if you installed VIGIL in one.

| Symptom | Next step |
| --- | --- |
| A README preview has no progress bar | The old preview is a GIF. Open the MP4 or run `python3 scripts/media/preview.py` for the chaptered player. |
| Video jumps back when seeking | Use the provided preview server, which supports byte-range requests, or open `docs/media/index.html` directly. A plain static server may not implement seeking. |
| `Python 3.10+ is required` | Select an installed interpreter: `PYTHON_BIN=python3.11 bash start.sh`, or follow [installation](INSTALLATION.md). |
| `venv` reports `ensurepip is not available` | Install the OS package that provides `venv` for your Python version, or use the [Conda alternative](INSTALLATION.md#conda-alternative). |
| `vigil: command not found` | Activate `.venv` with `source .venv/bin/activate`. From the source root, `python -m vigil` also works without installing a command on PATH. |
| The browser did not open | Run `bash start.sh --no-open` and open the printed address. The launcher chooses an available local port. |
| `doctor` reports missing model settings or AI2-THOR | For recorded replay, run `bash start.sh`; these are evaluation prerequisites. To evaluate a model, follow [model setup](MODEL_EVAL.md) and install `.[thor]`. |
| Authentication fails or the model is not found | Check the API format, model name and endpoint in `vigil ui`. Set the key in the UI or a provider environment variable. A successful text connection check does not test image support. |
| A wheel install cannot find tasks or scenes | The wheel includes the replay, not the full dataset. Download the source and set `VIGIL_DATA_ROOT=/path/to/VIGIL/data`; see [data discovery](INSTALLATION.md#wheel-installation-and-data-location). |
| Unity cannot start or the first run takes a long time | The first run can download simulator assets. Check [rendering platforms](INSTALLATION.md#rendering-platforms) and the tested [runtime references](../reference/RUNTIME.md) before launching more workers. |
| Unity briefly shows an outdoor street for a ProcTHOR task | This is the startup background before the house and initial pose load. Inspect the saved RGB frames, which are recorded after initialization. |
| Linux reports no valid display | Use a working X/GLX desktop or configure `VIGIL_THOR_PLATFORM=cloud` with Vulkan; follow [rendering setup](INSTALLATION.md#rendering-platforms). |
| Downloads are too slow on the evaluation host | Prepare public wheels and the matching official Unity cache on a connected machine; verify hashes after transfer. See the tested [Linux setup](../reference/RUNTIME.md). |
| A text connection check passes but an episode fails | Check that the model and gateway accept image input and the requested response format; a text-only check cannot establish this. |
| A run refuses to resume or the output directory already exists | Use a new `--out-dir`. Resume requires the same code, model, task inputs and profile; see [evaluation and recovery](EVALUATION.md). |

## Check the problem without running an evaluation

```bash
python -m vigil print-env
python -m vigil validate-pack
```

`print-env` reports Python, platform and whether optional packages are installed.
`validate-pack` checks the source task selection. Neither starts a simulator or
calls a model. For local evaluation readiness, also run `python -m vigil doctor`;
missing model/simulator setup is expected in a replay-only installation.

## Ask for help

[Open an issue](https://github.com/xpeng-robotics/VIGIL/issues/new/choose) with:

- The command or UI action, expected outcome and actual outcome.
- Your operating system, Python version, and whether you used source or a wheel.
- The error message and smallest example that reproduces it.

Include `print-env` output when useful. Remove credentials, private endpoints
and personal paths from excerpts. Keep `vigil.json` and raw model configurations
private. A short, sanitized error excerpt is usually sufficient.
