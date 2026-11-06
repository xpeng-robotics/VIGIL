---
name: vigil-onboarding
description: Improve or verify VIGIL installation, launchers, README instructions and the first recorded replay or single-episode workflow.
---

Read [README](../../../README.md), [installation](../../../docs/guides/INSTALLATION.md)
and [workbench](../../../docs/guides/WORKBENCH.md). Work from the release root.

Check the user path in order: `bash start.sh`, recorded RGB replay, model setup,
one explicitly requested real episode, then result inspection. Source replay
needs Python 3.10+ only; a wheel must serve its bundled demo outside the checkout.
No API key, simulator, Git checkout or frontend build is needed to view recordings.

Keep the source and installed paths distinct. `--results-dir` selects existing
results to read; `--out-dir` selects where new evaluations are saved. Neither
opening the UI nor a code review authorizes starting an evaluation.

For launcher changes run `tests/test_launcher.py`; for UI/CLI changes run their
corresponding suites. Check the launch button and replay at desktop and narrow
viewport sizes. Use empty configuration for captures. Update both README languages
when changing the first-use path, and put advanced details in the topic guides.
