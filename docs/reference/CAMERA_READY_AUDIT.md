[Documentation](../README.md) / Reference

# Camera-ready companion evidence

These are offline analyses of the original paper archives. The benchmark scorer,
historical W/B tables, prompts and task budgets are not changed by this audit.
The current executable pack remains a separate revised dataset.

## Files and scope

| Evidence | Artifact | Scope |
| --- | --- | --- |
| Summary-state audit | [2,500 episode rows](../../data/reproduction/terminal-audit/sv_summary_audit.csv), [unmapped examples](../../data/reproduction/terminal-audit/sv_unmapped_examples.csv) | All 20 primary models, 125 original SV episodes each |
| Companion metrics | [Integer counts and archive hashes](../../data/reproduction/terminal-audit/archive_metrics.json) | W/B, report coverage/correctness, attainment and loss |
| Report confusions | [Task-split label counts](../../data/reproduction/terminal-audit/report_confusions.csv) | Includes incorrect and missing reports, not only successful tasks |
| Setup sensitivity | [Counts](../../data/reproduction/terminal-audit/sv_exclusion_sensitivity.csv), [ten excluded IDs](../../data/reproduction/paper_sv_exclusions.json) | Uniform exclusion; 990 total / 115 SV episodes remain |
| Historical prompt | [Rendered template](../../data/reproduction/paper_prompt.txt), [provenance](../../data/reproduction/paper_prompt_provenance.json) | Exact template hash matched in 20 primary manifests |
| History and memory | [Paired archive audit](../../data/reproduction/terminal-audit/history_memory_provenance.json), [observed memory feedback](../../data/reproduction/terminal-audit/memory_feedback_audit.json) | Four baselines and seven treatments, 1,000 episodes each |
| Hardware examples | [Four-video gallery](../media/demos/index.html) | Qualitative external recordings and controlled-intervention replays |

## Revised assertion rule

The standard-library-only [audit script](../../scripts/reproduce/audit_terminal_reports.py)
defines `explicit-assertion-v2`. It reads the summary and queried attribute,
without seeing the expected answer. It accepts bare state labels or explicit
present-state assertions. It rejects negation, uncertainty, conditionals,
conflicting assertions, spatial `on the table`, past-only descriptions and
imperatives. It never maps generic success/fail to an object state. Agreement
is then checked against the evaluator's available terminal label.

This corrects the earlier lexical rule, which could misread “no signs of being
powered on” and “no visible open gap.” The rule was refined during camera-ready
review, not preregistered. It deliberately leaves many valid paraphrases
unmapped; unmapped does not mean incorrect. Object-reference resolution and
complete semantic interpretation are outside its scope.

RoboBrain's revised 125-episode audit is **105 agreeing / 17 disagreeing / 3
unmapped**, versus the rebuttal's earlier 104/17/4. This difference is disclosed
in the paper; neither result replaces exact B. The fresh four-model summary
counts in the rebuttal used the earlier rule and have not been re-audited here.

## Task setup and provenance corrections

Ten original Dresser SV definitions requested unsupported open/close setup.
They are task defects, not agent errors. Nine retained targets were repaired
as Drawers in the revised release and one was removed. See the
[runtime investigation](RUNTIME.md) and [data adoption record](../reviews/REVISED_DATA_ADOPTION.md).
Excluding all ten uniformly changes overall W/B by at most 0.230 percentage
points in these archives. The SV-only impact is larger; denominators and counts
are explicit. This is not fresh execution on repaired tasks or validation of
the remaining initializations. The 875 achievement episodes are unchanged.

The primary manifests' `2026-04-18` prompt label was hard-coded by the historical
runner. The actual rendered template from each of three recorded commits has
SHA-256 `b450374f4bcc13a58a782c10522e8bc97f46d92d4b49039ee8f00a4889df1d38`, matching
all 20 manifests. Its source version constant is `2026-04-27-state-report-labels`.
The hash covers the placeholder baseline template, not every per-request
coordinate override. The current legacy preset is a reconstruction and is not
byte-identical to this template.

The original 20-configuration prompt-sensitivity template is also recovered: [full text](../../data/reproduction/paper_neutral_prompt.txt) and [hash provenance](../../data/reproduction/paper_neutral_prompt_provenance.json). Replacing the two primary instructions with the neutral sentences matches all 20 archived template hashes (`57030dba...225da96`). This corrects the earlier description as deletion; it does not identify the fresh four-model rebuttal campaign.

All seven history/memory W/B deltas were recovered from raw saved per-step
judgments. Six-frame history retains the configured 20-turn dialogue history;
memory uses one current frame. The memory intervention also exposes controller
feedback through its structured records, including holding and action-error
information. It is a combined intervention, not a memory-only or RGB-only
ablation. The historical `robot_observable` policy label does not identify the
same surface as the current release. Dirty worktrees limit exact reconstruction
from a commit ID; the released diagnostics record what the archives show.

The fresh neutral-wording, acknowledgement and stop-only numbers come from the
final author response. Their raw archives and complete prompts are not included
here, so this package cannot reproduce those three controls. The numerical
audit files do not contain full historical rollouts or serving credentials.

## Final figure and label corrections

The camera-ready [closure-outcome figure](../media/source/failure_distribution_camera_ready.pdf)
separates correct reports at W=0 from invalid-action-limit terminations. Correct
failure reports remain outside benchmark success; the five plotted categories
are disjoint and exhaustive. The correction leaves W, B, false-report and
no-report counts unchanged. Invalid-action-limit termination can include
well-formed but invalid actions; it is not exclusively a formatting error.

The paper also corrects two qualitative trajectory descriptions and distinguishes
action counts from observations including the initial frame. Historical figures
in the overview film are retained as original-submission illustrations; the
linked camera-ready figure contains the corrected outcome partition.

The [frame-label review](../reviews/FRAME_ID_REVIEW.md) records the separate
archived-input check and the scope of the pre-fix release run.

## Recompute with private original archives

Create a private JSON object mapping the model IDs in `archive_metrics.json`
to complete original aggregate files. With Python 3.10+:

```bash
python scripts/reproduce/audit_terminal_reports.py \
  --source-map /path/to/private-source-map.json \
  --pack data/reproduction/paper_v4_pack.json \
  --exclusions data/reproduction/paper_sv_exclusions.json \
  --out outputs/new-terminal-audit
```

The script checks the 1,000 episode IDs, final report-match evidence, task
denominators and exclusion membership before writing counts and hashes. It
does not launch a simulator or infer that a saved rollout was validly initialized.
The revised executable pack must not be substituted for the historical selection.

The self-contained hardware gallery and benchmark film are included in this
source release and can be hosted as static files. Public release conditions
remain in the [release checklist](../development/RELEASE_CHECKLIST.md).
