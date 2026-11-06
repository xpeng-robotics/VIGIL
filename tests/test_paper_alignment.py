import json
from pathlib import Path

import pytest

from vigil.eval.paper_alignment import PaperAlignmentError, audit_model, trace_outcome


def result(episode_id="e", *, world=True, report=True):
    return {
        "episode_id": episode_id,
        "task_family": "S1_pixel_grounding",
        "trace": [
            {
                "judge_result": {
                    "world_success": world,
                    "semantic_world_success": world,
                    "report_submitted": report,
                    "report_matches_world": True if report else None,
                },
                "runtime_action": {
                    "executed_invocation": {
                        "skill_name": "report" if report else "look",
                        "arguments": {"status": "success" if world else "fail"} if report else {},
                    }
                },
            }
        ],
        "settlement": {
            "terminal_status": "success" if world and report else "failure",
            "world_success": world,
            "semantic_world_success": world,
            "report_submitted": report,
            "report_matches_world": True if report else None,
            "steps_used": 1,
            "step_budget": 5,
        },
    }


def run_audit(tmp_path, rows, *, expected_world=1, expected_benchmark=1):
    source = tmp_path / "aggregate.json"
    source.write_text(json.dumps({"episode_count": len(rows), "results": rows}))
    counts = {
        "world_success_count": expected_world,
        "benchmark_success_count": expected_benchmark,
    }
    target = {
        "model_id": "test",
        "expected": {**counts, "by_task_family": {"S1_pixel_grounding": counts}},
    }
    return audit_model(source, target, {"e": "S1_pixel_grounding"})


def test_paper_audit_recomputes_instead_of_trusting_saved_score(tmp_path):
    row = result()
    row["score_summary"] = {"success": False}
    audit = run_audit(tmp_path, [row])
    assert audit["passed"]
    assert audit["actual"]["benchmark_success_count"] == 1


def test_paper_audit_rejects_settlement_disagreeing_with_step_evidence(tmp_path):
    row = result()
    row["settlement"]["world_success"] = False
    row["settlement"]["semantic_world_success"] = False
    audit = run_audit(tmp_path, [row])
    assert not audit["passed"]
    assert audit["scorer_trace_disagreement_count"] == 1


def test_paper_audit_requires_exact_counts_not_a_rounded_nearby_score(tmp_path):
    audit = run_audit(tmp_path, [result()], expected_benchmark=0)
    assert not audit["passed"]
    assert audit["paper_mismatches"]


@pytest.mark.parametrize(
    "rows,error",
    [
        ([result(), result()], "Duplicate"),
        ([result("other")], "canonical"),
        ([], "nonempty"),
    ],
)
def test_paper_audit_rejects_ambiguous_coverage(tmp_path, rows, error):
    with pytest.raises(PaperAlignmentError, match=error):
        run_audit(tmp_path, rows)


def test_trace_outcome_uses_final_world_and_requires_report():
    row = result(world=False)
    row["trace"].insert(0, {"judge_result": {"world_success": True}})
    assert trace_outcome(row) == (False, False)
    assert trace_outcome(result(report=False)) == (True, False)
    with pytest.raises(PaperAlignmentError, match="complete step trace"):
        trace_outcome({"trace": []})


def test_published_v4_targets_include_the_actual_anchor_rows():
    path = (
        Path(__file__).resolve().parents[1] / "data/reproduction/paper_v4_targets.json"
    )
    targets = json.loads(path.read_text())
    rows = {row["model_id"]: row["expected"] for row in targets["models"]}
    assert len(rows) == 20
    assert (
        rows["qwen3.6-27b"]["world_success_count"],
        rows["qwen3.6-27b"]["benchmark_success_count"],
    ) == (467, 378)
    assert (
        rows["qwen3.5-27b"]["world_success_count"],
        rows["qwen3.5-27b"]["benchmark_success_count"],
    ) == (420, 362)
    for row in rows.values():
        assert len(row["by_task_family"]) == 8
        for metric in ("world_success_count", "benchmark_success_count"):
            assert (
                sum(cell[metric] for cell in row["by_task_family"].values())
                == row[metric]
            )
