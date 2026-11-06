[Documentation](../README.md) / Development

# Release Checklist

Before publishing VIGIL:

- At publication time, confirm `README.md` points to the final paper, project page,
  and dataset. Destination URLs can remain unset during local acceptance.
- Preserve the approved Apache-2.0 project `LICENSE`, `NOTICE` and package license metadata in both source and wheel. Original code, task definitions and benchmark annotations use this license; third-party materials retain their upstream terms.
- Retain `licenses/THIRD_PARTY_NOTICES.md` and the unmodified upstream license texts in `licenses/` in source exports and built distributions.
- Scan the exact exported candidate and record its SHA-256 manifest with the resulting license/component reports. A declared dependency list is not a scan-generated SBOM.
- Keep raw construction data, reviewer state, intermediate candidate packs, and internal result folders out of git.
- Run `python scripts/release/check_public_release.py /path/to/exported-release` and
  repeat it on the final ZIP and built wheel, including known private configuration
  matches when available. Follow [the security guide](SECURITY.md) for media,
  PDF and Git-history checks; current-file scanning does not clean old commits.
- Preserve a public per-scene provenance record with available source identifiers
  and final house hashes. The
  [public scene manifest](../../data/provenance/scenes.json) pins the 47 imported
  houses to a verified dataset revision and records all 456 house hashes. The
  409 generated scenes are frozen evaluation inputs; rebuilding their generation
  pipeline is outside the release reproduction contract.
- Publish a tested simulator environment specification, including the AI2-THOR
  package version, Unity build, platform and dependencies. The
  [runtime references](../reference/RUNTIME.md) record clean macOS and Linux
  Python installations and three scripted scene checks on each platform. macOS
  also passed an empty-cache Unity download. Linux used a verified archive
  prepared on another machine and a CPU software renderer. Record GPU capacity
  checks separately; the optional dependency range alone is not a reproducibility lock.
- Validate scene creation, initial poses, setup actions and task targets on that
  runtime. Review the retained unreachable-point warnings in
  `procthor_faucet_seed123` and `procthor_vacuumcleaner_seed366`. The two prescribed
  initializations and target-grounding actions now pass on both runtime references;
  this does not validate all navigation points or the full pack. Static JSON
  resolution alone does not establish task solvability; see [data scope](../reference/DATA.md).
- Preserve the nine versioned Drawer corrections and their 18 real-simulator
  scripted report checks. All 1,000 initializations pass on the macOS reference
  (527 new, 473 matching prior checks). The completed eight-worker macOS
  Qwen3.6-27B run covers all 1,000 corrected tasks with matching settlement and
  scores. Recheck live behavior when changing the runtime or execution inputs.
  See the [adoption record](../reviews/REVISED_DATA_ADOPTION.md).
  Offline scoring passes do not establish live completion. Keep the frozen
  historical selection and targets separate from the corrected default.
- Keep one canonical executable pack and its referenced definitions; retain
  `data/reproduction/paper_v4_pack.json` solely for historical score checks:

```text
data/benchmark/packs/mixed_mainline_manual_revised_1000_v2.json
data/episodes/<episode_id>/episode.json
```


- Apply the five documented [feedback retry corrections](../reference/FEEDBACK_CORRECTION.md) to the manuscript before publishing updated paper tables.
- Run the metric-code alignment gate against at least one full frozen reference result directory. Prefer two runs with different model behaviors before a release candidate:

```bash
scripts/reproduce/run_metric_alignment.sh \
  --reference-path /path/to/reference_results_or_traces \
  --expected-aggregate /path/to/reference_aggregate_score.json
```

- If only original per-episode result JSONs are available, run the auxiliary scorer-drift check while the full aggregate is being recovered:

```bash
PYTHONPATH=. python scripts/reproduce/check_reference_results.py \
  --reference-path /path/to/reference_result_jsons
```

This is not a release-ready substitute for the full aggregate gate.

- Run tests:

```bash
PYTHONPATH=. python -m pytest
```

- Run CLI checks:

```bash
PYTHONPATH=. python -m vigil.cli validate-pack data/benchmark/packs/mixed_mainline_manual_revised_1000_v2.json
PYTHONPATH=. python -m vigil.cli verify-run vigil/web/demo --require-frames
```

- Confirm `.agent/AGENTS.md`, `docs/README.zh-CN.md`, `docs/development/CHANGELOG.md` and all linked guides are
  included in the exact export. Validate its SHA-256 manifest after copying.
- Check `vigil progress` from outside the checkout on a saved run, including macOS.
  Check that `verify-run` rejects incomplete runs and inconsistent evidence.
- From the extracted source, check `bash start.sh --no-open` without package
  installation. Check interpreter discovery and automatic port selection.
- Confirm final UI and run-directory reports reject changed aggregates and malformed
  boolean evidence. Check that evaluator child arguments contain no configured key.

- Install the exact exported candidate in a clean environment and run `vigil ui`.
  Verify that the recorded demo works without a key or simulator, both example
  frames and failed outcomes are visible, and the wheel includes all UI assets.
- Check configuration save, task filtering, result replay, run cancellation and
  incomplete-run handling. Opening the interface must not start a model call.
- Confirm private keys are absent from HTTP responses, trace downloads and the
  public export; generated model snapshots must remain owner-readable only.

- Confirm the aggregate comparator checks recursive reference fields, including no-report analysis, behavior metrics, harness assistance, and capability/template/target-group buckets.
- Scan for private organization names, internal platform names, private domains, and secret-like literals before publishing.
- Confirm no generated files are staged:

```bash
find . -name '__pycache__' -o -name '.pytest_cache' -o -path './results'
```
