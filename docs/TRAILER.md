[Documentation](README.md) / [Films](DEMOS.md) / Hardware walkthrough sources

# Hardware walkthrough: sources and editing

The 68-second film introduces VIGIL, then explains two complete robot-view
replays. It contains no simulation footage. The [research overview](VIDEO.md)
remains a separate 152-second film about the benchmark and its simulated tasks.

| Time | Content and source |
| --- | --- |
| 00:00–00:08 | Introduce world outcome and final reporting, then the observe–act–report sequence. The preview image is from the redacted Gemini recording. |
| 00:08–00:12 | Introduce the task and Doubao-Seed-1.6 episode. |
| 00:12–00:30 | All eight frames of `robot-3.mp4`, including five model decisions, the report, and the source closure annotation. Original two-second frame holds plus an extra two-second terminal hold. |
| 00:30–00:34 | Introduce the separate Gemini-3.1-Pro-preview episode. |
| 00:34–01:00 | All twelve frames of `robot-4.mp4`, including nine model decisions, the report, and the source closure annotation. Original two-second frame holds plus an extra two-second terminal hold. |
| 01:00–01:08 | Explain the scope of the recorded labels and close with the paper title. |

Both source replays explicitly use a controlled intervention and end with
`terminal_reason=false_success_report`, `report_status=success`, and
`score_validity=trace_only`. The film reproduces those annotations; it does not
independently certify physical task outcomes. These are separate qualitative
episodes, not a controlled model comparison, a hardware success-rate estimate,
or quantitative evidence of transfer from simulation.

Action labels and explanations follow the source Model Reply fields. They
express the model's requested action or stated intent, not a causal diagnosis.
The fixed action transcription, source hashes and timing are in the
[edit manifest](media/trailer-manifest.json). The chapter bar measures playback
position. The numbered tiles index model decisions, with R for the report;
neither display is a world-goal completion percentage.

## Face redaction and visual fidelity

Human head regions are obscured in all four full hardware videos and their
posters before any film compositing. The first-person replays use reviewed,
padded masks on every distinct observation. The external recording uses an
interpolated head track; the portrait recording also masks partial faces entering
the right edge. Existing display redaction is retained and extended where the
laptop rises into view. The [recording manifest](media/demos/manifest.json)
records the source and redacted-file hashes and the edits applied.

The film crops the RGB region at `(320, 120, 960, 600)` from each replay and
shows its 640 × 480 observations at 960 × 720, or 800 × 600 on introduction
cards. Enlarging the image does not add detail. Every source observation remains
in order, with no synthesized intermediate states. Full task and model-reply
panels remain in the redacted original recordings. Playback is sampled observations, not elapsed
robot execution time. Music is original synthesized audio, not scene sound.

## Rebuild

```bash
python -m pip install -e ".[media]"
python scripts/media/build_trailer.py --preview-only --out-dir outputs/hardware-preview
python scripts/media/build_trailer.py
```

The builder verifies hashes and requires the reviewed, face-redacted source
recordings. It writes H.264/AAC video with progressive-playback metadata at the
start of the file, its poster and an edit manifest. No model or simulator runs.
The original unredacted inputs are not part of this release.
