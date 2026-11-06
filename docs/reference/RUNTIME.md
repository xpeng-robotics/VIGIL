[Documentation](../README.md) / Reference

# Simulator reference environments

The 2026-11-04 acceptance checks installed the release wheel in clean Python
environments on macOS and Linux, outside the source checkout. Both passed three
scripted scene checks: initialization, nonblank 640 × 480 RGB, target visibility
and a pixel-grounding action. Each used AI2-THOR **5.0.0** and Unity build
`f0825767cd50d69f666c7f282e54abfe58f1e917`.

| Reference | Python / architecture | Renderer | Runtime preparation |
| --- | --- | --- | --- |
| macOS 26.6.2 | CPython 3.11.15 / x86_64 | `OSXIntel64` | Public-package installation and an empty Unity cache; official download completed on this host |
| Linux, glibc 2.39 | CPython 3.12.3 / x86_64 | `Linux64`, Xvfb, Mesa llvmpipe | Public wheels and official Unity archive downloaded on another machine, SHA-256 verified, then installed in the isolated environment |

The Linux check used two CPU cores, llvmpipe with LLVM 20.1.2 and Mesa 25.2.8
(OpenGL 4.5). No rendering GPU was used. Its settings included
`LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvmpipe`,
`__GLX_VENDOR_LIBRARY_NAME=mesa`, `OMP_NUM_THREADS=2` and `LP_NUM_THREADS=2`,
with `DISPLAY` set to the owned Xvfb display and `VIGIL_THOR_PLATFORM` unset.
All simulator and display processes started by the check exited afterward.

These are three-scene runtime checks, with **zero model requests**. They do not
establish full-pack Linux execution, GPU rendering capacity or model scores.
For an actual model check, configure your API and run `vigil smoke`, then
`vigil verify-run RUN_DIR --require-frames`. A separate eight-worker macOS run
completed all 1,000 revised tasks with Qwen3.6-27B on 2026-11-05, with W 42.4%
and B 36.0%. All saved settlements/scores agree, and all 14,714 RGB inputs and
4,686 normalized-coordinate conversions pass the complete evidence audit.
See [request settings and comparison limits](METRIC_ALIGNMENT.md#2026-11-05-revised-pack-model-check)
and the [release checklist](../development/RELEASE_CHECKLIST.md).

## Install matching Python packages

From the source release, in a matching Python environment:

```bash
# macOS x86_64, Python 3.11.15
python -m pip install -c scripts/deploy/constraints-macos-x86_64.txt -e ".[thor]"

# Linux x86_64, Python 3.12.3
python -m pip install -c scripts/deploy/constraints-linux-x86_64.txt -e ".[thor]"
```

Choose the constraint file for your platform. The
[macOS constraints](../../scripts/deploy/constraints-macos-x86_64.txt) and
[Linux constraints](../../scripts/deploy/constraints-linux-x86_64.txt) record
the installed simulator dependency versions. They do not provision Python,
Rosetta, Xvfb, graphics drivers or Unity, and are not wheel-hash lockfiles.
The core installation and recorded replay need none of these simulator packages.

After preparing the renderer, run `vigil doctor --check-simulator` in that
environment. For Linux GPU rendering, use the separate
[deployment guide](../guides/DEPLOYMENT.md); the CPU reference does not validate
CloudRendering or a multi-GPU configuration.

## Runtime identity and downloads

The executable hashes below identify the Unity player, not its complete asset
directory:

| Unity platform | Executable SHA-256 |
| --- | --- |
| `OSXIntel64` | `d8bbfbee47581f4aa4f5df71e095f0a1c00888bed7b493eaffcc0f37d6364df3` |
| `Linux64` | `95aa60b3bead39f7f6e86d1189664d420d8323243c63a45766601cd8fadeba88` |

The macOS first download took about 14 minutes on the tested connection. Finish
runtime download before timing model evaluation. The Linux archive SHA-256 is
`4712a43a510d1f4e50a388958d046acd31a87f1c9d8d5ed116f73dc4b17265ad`,
verified against the official checksum before and after transfer. The test did
not complete the large download directly inside the Linux container because
that connection was slow.

An offline host needs a prepared cache for its own platform and build. Set
`VIGIL_THOR_RELEASES_DIR` to an existing AI2-THOR `releases/` directory, or use
`VIGIL_AI2THOR_BASE` to select a writable cache base. Do not copy a macOS Unity
player to Linux or include simulator binaries in the public benchmark archive.

## What the scene checks establish

| Scene | Canonical episode |
| --- | --- |
| iTHOR `FloorPlan1` | `ithor_fp1_s1_pixel_grounding_easy_fridge_ground_001` |
| `procthor_faucet_seed123` | `procthor_faucet_seed123_S1_medium_faucet_001__mainline` |
| `procthor_vacuumcleaner_seed366` | `procthor_vacuumcleaner_seed366_S1_easy_vacuumcleaner_001__mainline` |

The two ProcTHOR houses retain historical unreachable-point warnings. Their
prescribed initialization and target-grounding action pass on both references;
the checks do not validate every navigation point. RGB frames were saved and
inspected. The diagnostic selected pixels using evaluator-only instance masks;
no model received those masks or hidden state.

Initialization requires simulator success or independent metadata confirming
that the exact target is already in the requested on/off/open/closed state.
Other setup failures stop before a model call. Saved initialization evidence
never becomes model input. The runtime does not silently change initial poses,
setup actions, task budgets or score formulas when a setup step fails.

## Revised pack status

The default includes the revised 1,000-task selection and nine versioned Drawer
corrections. All nine pass reset and correct/incorrect scripted report checks
(18 scored traces), including uncached settlement and score comparison. The
dropped open-state seed297 task is absent; closed-state seed314 has an explicitly
corrected initial pose. See the [adoption record](../reviews/REVISED_DATA_ADOPTION.md).

The macOS initialization audit covers all 1,000 tasks: 527 fresh checks and
473 prior successful checks with identical inputs, initializer code and build.
This validates reset, nonblank RGB and declared target presence. Full task
execution and scoring remain separate gates. Historical paper score checks
continue to use the frozen selection and archived evidence.

The original Dresser failures and repair analysis are preserved in the
[original initialization audit](../reviews/ORIGINAL_RUNTIME_AUDIT.md).
