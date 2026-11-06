[Documentation](../README.md) / Guides

# Installation and environment checks

## Choose what to install

| Workflow | Python packages | Other requirements |
| --- | --- | --- |
| Source-release recorded replay | None; `bash start.sh` | Python 3.10+, browser |
| Installed UI, scoring and verification | `pip install -e .` | Python 3.10+, browser for the UI |
| Real episodes against an existing API | `pip install -e ".[thor]"` | Compatible Linux/macOS renderer, model with image input, API access |
| Offline contributor tests | `pip install -e ".[dev]"` | Local subprocess and loopback socket support |
| Self-hosted inference | Evaluation environment plus a separate serving environment | Model-specific vLLM, accelerator drivers and weights |

The source release includes the canonical 1,000 tasks and scene JSON. A wheel
includes the UI and two recorded examples, but excludes the full benchmark data,
simulator binaries and model weights. Installation may download Python packages;
the recorded UI itself works offline after installation.

## Standard installation

To explore the extracted source release immediately, run `bash start.sh` from its
root. No package installation is needed. The launcher chooses an available port
and a supported Python interpreter. macOS also has `start.command`. Use
`PYTHON_BIN=/path/to/python bash start.sh` to select an environment explicitly.
For a fixed remote-forwarding port: `bash start.sh --no-open --port 8765`.
Opening the workbench never starts an evaluation.

Extract the source release, enter its root and run:

```bash
python3.10 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
vigil ui
```

Use your available Python 3.10+ in place of `python3.10`. The dedicated environment
is useful for simulator packages and the installed `vigil` command. The source
launcher prefers `PYTHON_BIN`, then an active virtual environment, then the release's
`.venv`, then a supported interpreter on PATH. An explicitly selected unsupported
environment produces an error rather than silently switching it.

Expected: the browser shows an overview and **Explore a recorded run**.
Open the example, choose an episode and move through RGB frames and actions.
No model configuration is needed for this check. No frontend compilation is needed.

To enable real evaluation in the same environment:

```bash
python -m pip install -e ".[thor]"
vigil init
# Edit vigil.json, or configure the model in vigil ui.
vigil doctor
vigil doctor --check-simulator
vigil smoke --out-dir outputs/first-smoke
```

The simulator extra installs AI2-THOR. The bundled house files are loaded directly;
the dataset-download package `prior` is not needed to run this release.

Restart the UI after installing extras. `doctor` performs local checks;
`--check-simulator` starts Unity and can download assets; `--check-model` sends a
small text request using quota. Only a real episode checks image input, action
parsing, rendering and evaluation together. See [deployment](DEPLOYMENT.md) for
cloud rendering and [model configuration](MODEL_EVAL.md) for API formats.

## Conda alternative

```bash
conda env create -f scripts/deploy/environment.yml
conda activate vigil-release
python -m pip install -e ".[thor]"
vigil ui
```

Run these commands from the repository root. Conda provides Python and pip;
the install command adds VIGIL and its simulator support. Use a dedicated
environment when an existing environment has incompatible packages. Contributor
checks are documented separately in [Contributing](../development/CONTRIBUTING.md);
they are not required to open replay or run a configured model.

## Rendering platforms

On a compatible macOS desktop, start with the default platform and run
`vigil doctor --check-simulator`. Apple Silicon may need an x86_64 Python/runtime
environment through Rosetta for the available Unity build. This release has a
successful local x86_64 runtime experiment on Apple Silicon; an ARM Python import
alone does not establish working rendering. A Linux rendering host is an alternative
if the local Unity build cannot launch. Native Windows simulator execution is not
validated by this release; use a supported remote rendering host.

The [reference environments](../reference/RUNTIME.md) record matching Python
constraints and Unity hashes for macOS and Linux. Clean installations passed
three scripted scene checks on each platform, including Xvfb/Mesa software
rendering on Linux. The macOS check included a first Unity-cache download; Linux
used a verified archive prepared on another machine. These checks establish the
recorded runtime configurations, not full-pack Linux or GPU capacity validation.

On a headless Linux machine:

```bash
export VIGIL_THOR_PLATFORM=cloud
vigil doctor --check-simulator
```

AI2-THOR supports `CloudRendering`; its Linux platform checks for a Vulkan loader.
On Debian/Ubuntu that package is `libvulkan1`; a working graphics driver is also
needed. Installation of the Python extra does not install a GPU driver.
See the [upstream headless setup](https://ai2thor.allenai.org/ithor/documentation/)
and [platform validation code](https://github.com/allenai/ai2thor/blob/main/ai2thor/platform.py).

The first simulator start downloads its Unity build into `~/.ai2thor` by default.
Allow network access and writable cache storage. Included `house.json` files are
scene descriptions, not those binaries. An offline rendering host must have the
matching runtime cache prepared in advance. Do not assume a fresh offline host
can run from the source ZIP alone.

## Wheel installation and data location

If you installed a wheel from outside the source release:

```bash
python -m pip install /path/to/vigil_benchmark-0.1.0-py3-none-any.whl
vigil ui
export VIGIL_DATA_ROOT=/path/to/extracted-release/data
vigil validate-pack
```

The environment variable is only required for full task data when it cannot be
located automatically. Existing trace scoring and the bundled example do not need
it. For real evaluation, install `.[thor]` from the extracted source release as
shown above. These instructions use the provided artifacts and do not assume a
public package-index release exists.

## Common installation failures

See [troubleshooting](TROUBLESHOOTING.md) for missing commands, environment
creation errors, data discovery, renderer failures and model connection issues.

For reproducibility, save `python --version` and `python -m pip freeze` with your
experiment notes. Public dependency ranges are not a hardware-specific lockfile.
Record the serving engine, weights revision and chat template separately.
