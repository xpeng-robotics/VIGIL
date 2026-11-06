# Maintainer tools

For normal use, run **`vigil ui`**, **`vigil catalog`**, **`vigil smoke`** and
**`vigil run`**. From an extracted source archive, start with **`bash start.sh`**.
The tools below support maintenance and explicit deployment workflows.

| Directory | Purpose | Entry |
| --- | --- | --- |
| [release/](release/) | Check disclosures, export source and curated recordings | `python scripts/release/export_public_release.py /path/to/new-release` |
| [reproduce/](reproduce/) | Compare archived results with paper/reference metrics | [Alignment guide](../docs/reference/METRIC_ALIGNMENT.md) |
| [deploy/](deploy/) | Optional Conda setup, logged batch execution and self-hosted inference | [Deployment guide](../docs/guides/DEPLOYMENT.md) |
| [media/](media/) | Rebuild the research film from attributed source material | [Video sources](../docs/VIDEO.md) |

Run Python helpers with `--help` for arguments. Do not invoke model-serving or
historical-reference shell scripts to inspect the repository: those scripts can
start real evaluation or serving processes.

The optional `scripts/deploy/quickstart.sh --smoke` installs evaluation support
and runs one real episode against your configured model API; it does not run
developer tests. On headless Linux it defaults to CloudRendering unless you
explicitly choose another renderer. `--check` installs development support and
runs offline tests plus a dry run. Set `VIGIL_SKIP_INSTALL=1` for a prepared
environment. The [installation guide](../docs/guides/INSTALLATION.md) and public
CLI remain the primary entry points.
`show_eval_progress.sh` is replaced by `vigil progress RUN_DIR`. The optional
logged batch wrapper is now `scripts/deploy/run_eval.sh`; it forwards to the same
CLI and evaluator. Existing `vigil` commands, including `run-pack`, remain valid.

## Preview the films

Run `python3 scripts/media/preview.py` from the source root to open the 68-second hardware walkthrough, research film and hardware gallery. It uses only the Python standard library, supports video seeking, and serves the presentation assets on loopback. Use `--no-open` to print the URL without opening a browser.
