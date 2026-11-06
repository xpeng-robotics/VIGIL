[Documentation](../README.md) / Development

# Contributing

Start with [the architecture map](ARCHITECTURE.md). Coding assistants should
explicitly read [.agent/AGENTS.md](../../.agent/AGENTS.md); there is no root
AGENTS.md, and tools that only discover root instructions need that path supplied.
The package lives directly in `vigil/`; no `src/` indirection is used. A downloaded
release has no required Git history. Python 3.10+ is sufficient for
core development; simulator dependencies are optional.

```bash
python -m pip install -e ".[dev]"
python -m pytest
vigil validate-pack
vigil run --dry-run --max-episodes 3 --out-dir outputs/check-selection
vigil verify-run vigil/web/demo --require-frames
```

Offline tests include local HTTP sockets and subprocess cancellation. They do
not need a model key, GPU or simulator service. Use the suite relevant to your
change during development; a release candidate requires the complete suite.
Judging/scoring changes additionally need settlement, integrity and paper-alignment
coverage. Do not describe offline checks as fresh model evaluation.

The [offline CI workflow](../../.github/workflows/ci.yml) runs on pushes and pull
requests. It checks the suite, canonical task pack, bundled replay and public
source export on Linux and macOS. It uses no model keys or simulator installation.

For a quick protocol/API and score-integrity check:

```bash
python -m pytest -o addopts='' -q --durations=8 \
  tests/test_reasoning_history.py tests/test_protocol_retries.py \
  tests/test_api_alignment.py tests/test_action_protocol_boundary.py \
  tests/test_adversarial_review.py
```

Use `--durations=10` on the complete suite to distinguish slow subprocess or
packaging checks from parser/scorer regressions. Neither command starts a live
model evaluation.

Keep the standard library core, original task budgets, RGB-only input and shared
W/B contract. Preserve user configuration and experiment output. Update the
relevant user guide and [CHANGELOG.md](CHANGELOG.md) for public changes.

## Packages and source exports

Build a wheel and install it in a fresh environment outside this checkout:

```bash
python -m pip wheel . --no-deps --wheel-dir dist
```

Create a fresh environment and install that wheel, then change to an unrelated
directory and clear PYTHONPATH before checking it. Running from the checkout can
mask missing wheel files in a flat layout.

Check `vigil --help` and launch `vigil ui --no-open --port 0` there. The wheel must
serve its static UI and two-episode demo without source data. Real tasks require
`VIGIL_DATA_ROOT` pointing to the source release's `data/` directory. The six film
cases are source-release assets, not wheel dependencies.

Export to a **new directory**, then run the tests and verification inside that
exact exported copy:

```bash
python scripts/release/export_public_release.py /path/to/new-release
cd /path/to/new-release
python -m pytest
PYTHONPATH=. python -m vigil validate-pack
PYTHONPATH=. python -m vigil verify-run vigil/web/demo --require-frames
```

The exporter includes root files and helpers from explicit allowlists, Python
source/tests, Markdown guides, selected presentation assets and the canonical
data. Project skill names are also explicitly allowlisted.

Curated recordings use `examples/recorded-runs/manifest.json`, a file-to-SHA256
map. Adding a recording requires evidence/frame verification, checking its public
metadata, and deliberately updating that reviewed map and catalog. Unlisted
files, hidden configuration snapshots and incidental evaluations are excluded;
changed listed bytes fail export. See [recording provenance](../../examples/recorded-runs/README.md).

Do not copy `outputs/`, local model configuration or the entire working directory
into a release. The final export has its own `docs/development/release_manifest.json` covering all
exported bytes. Publication additionally requires the unresolved items in the
[release checklist](RELEASE_CHECKLIST.md); passing tests alone is insufficient.
