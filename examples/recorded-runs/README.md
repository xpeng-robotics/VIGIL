# Selected recorded trajectories

Six complete, curated episodes from historical VIGIL experiments, with **43
model actions and 49 original RGB observations**. They illustrate the reporting
contract and provide offline examples. They are not a random sample, a model
ranking, a new evaluation, or a reproduction of the paper's aggregate results.

From the extracted source release:

```bash
bash start.sh --results-dir examples/recorded-runs
```

The source workbench home page also has a direct card for each case.
Alternatively, open **Results & replay** and select a named recording. Playback needs neither a model API
key nor a simulator. With the installed CLI and this source bundle, use
`vigil ui --results-dir examples/recorded-runs`.

| Recording | Model | Task | Profile | Steps | W / B |
| --- | --- | --- | --- | ---: | --- |
| `verified-fridge` | Gemini 3.1 Pro | AI: open the fridge | RGB + dialogue history, no action feedback | 5 | 1 / 1 |
| `sequential-apple` | Gemini 3.1 Pro | SM: pick up an apple and place it in the sink | Action-feedback intervention | 6 | 1 / 1 |
| `false-report-fridge` | Claude Sonnet 4 | AI: open the fridge | RGB + dialogue history, no action feedback | 5 | 0 / 0 |
| `post-goal-kettle` | Qwen3.6-27B | AI: open the kettle | Action-feedback intervention | 25 | 1 / 0 |
| `verified-microwave` | Gemini 3.1 Pro | SV: report the microwave state | RGB + dialogue history, no action feedback | 1 | 1 / 1 |
| `mismatch-microwave` | Doubao Seed 1.8 | SV: report the microwave state | RGB + dialogue history, no action feedback | 1 | 1 / 0 |

The two intervention cases expose `too_far` and `path_blocked` feedback. They
must not be treated as baseline no-feedback results. Each case has its own model,
profile, trace, score and one-episode aggregate. No combined cross-profile score
is supplied. Exact archival model identifiers are retained in `model_config.json`
and `provenance.json`; display names are in [catalog.json](catalog.json).

The kettle's world condition first becomes true after action 9 and remains true
through action 25. The final outcome is budget exhaustion without a report.
The two fridge cases share the same episode ID. One opens the fridge and reports
correctly; the other reports success after unsuccessful interactions. These are
selected behaviors, not estimates of model-level reliability or internal beliefs.

The microwave pair starts from byte-identical reset PNGs. The models report
`closed` and `open`, respectively; the recorded world state is closed. Both
single-action traces preserve the original report text. Their contrasting B
outcomes illustrate semantic report verification, without changing the task or
the scoring rules.

## What is retained

Each recording includes:

- `traces/`: original model action text, parsed invocation, validated and executed
  actions, coordinate adapters, environment evidence, judge evidence and settlement.
- `frames/`: lossless copies of the archived PNGs. `step_000.png` is the reset
  observation **before** action 1; `step_001.png` is before action 2. The extra
  `terminal.png` is the observation after the last action. The workbench pairs
  each pre-action frame with that action and its resulting evaluator evidence.
- `scores/` and `aggregate_score.json`: rebuilt by the public scorer; W/B and all
  archived scalar score-summary fields checked against the source result.
- `provenance.json`: source-result hash, original frame names and hashes, profile,
  archived score summary, timestamp, editorial selection and conversion scope.
- `verification.json`: independent settlement, score and aggregate consistency
  check. This validates stored evidence, not a new simulator run.

Private endpoints, credentials, transport payloads, worker identifiers and
provider response signatures are excluded. Evaluator evidence remains available
for inspection and is **not** an extra model observation.

```bash
vigil verify-run examples/recorded-runs/verified-fridge --require-frames
vigil verify-run examples/recorded-runs/sequential-apple --require-frames
vigil verify-run examples/recorded-runs/false-report-fridge --require-frames
vigil verify-run examples/recorded-runs/post-goal-kettle --require-frames
vigil verify-run examples/recorded-runs/verified-microwave --require-frames
vigil verify-run examples/recorded-runs/mismatch-microwave --require-frames
```

## Export another historical case

The helper accepts the archived, one-based `trace` result format and its
`step_000_reset.png`, `step_001_*.png`, … screenshots. It requires complete
observations and matching action, adapter, settlement and score evidence.
Choose a new output directory; existing directories are not overwritten.

```bash
python scripts/release/export_recorded_example.py /path/to/episode.json \
  --frames /path/to/episode-screenshots \
  --model model-identifier \
  --out outputs/recorded-example
vigil ui --results-dir outputs/recorded-example
```

The helper copies only selected evidence fields and refuses suspected private
content instead of silently rewriting it. Review free text and images before
sharing a new case. It does not establish a license for a third-party archive.
Use the release's [third-party notices](../../licenses/THIRD_PARTY_NOTICES.md) and
[publication checklist](../../docs/development/RELEASE_CHECKLIST.md) for these bundled cases.

Keep the main repository small by publishing a few inspectable examples. A full
experiment archive belongs in a versioned dataset or release asset, with a
manifest, checksums, exact profiles, coverage and reproducibility documentation.
These examples are included in the source distribution; the runtime wheel keeps
its smaller built-in demo.

The source exporter includes only files listed with matching SHA256 hashes in
[manifest.json](manifest.json). Incidental evaluations and hidden configuration
files are not included. Reviewed additions require an explicit manifest update.
