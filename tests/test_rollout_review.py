"""Regressions motivated by historical rollout auditing, without live services."""
import json
from pathlib import Path

import pytest

from vigil.eval.offline import evaluate_trace_files
from vigil.eval.paper_alignment import PaperAlignmentError, trace_outcome
from vigil.cli import main
from test_evaluate import _reference_result_payload
from test_paper_alignment import result


def write(path, payload):
    path.write_text(json.dumps(payload))
    return path


def test_directory_rescoring_must_not_drop_historical_timeout_records(tmp_path):
    write(tmp_path / "ok.json", _reference_result_payload())
    write(tmp_path / "failed.error.json", {
        "episode_id": "failed", "error_type": "TimeoutError",
        "error_message": "episode process timed out", "elapsed_s": 120,
    })
    with pytest.raises(ValueError, match="infrastructure"):
        evaluate_trace_files([tmp_path])


@pytest.mark.parametrize("extra", [
    {"error_count": 1}, {"errors": [{"episode_id": "failed"}]},
    {"episode_count": 2}, {"overall_episode_count": 2},
    {"skipped_missing": ["missing"]},
])
def test_aggregate_rescoring_requires_consistent_coverage(tmp_path, extra):
    path = write(tmp_path / "aggregate.json", {
        "episode_count": 1, "results": [_reference_result_payload()], **extra,
    })
    with pytest.raises(ValueError, match="infrastructure|count|missing"):
        evaluate_trace_files([path])


def test_rescoring_rejects_incomplete_status_even_with_saved_traces(tmp_path):
    (tmp_path / "traces").mkdir()
    write(tmp_path / "traces/ref_ok.json", _reference_result_payload())
    write(tmp_path / "run_status.json", {"state": "running", "episode_ids": ["ref_ok"]})
    with pytest.raises(ValueError, match="incomplete"):
        evaluate_trace_files([tmp_path])


def test_single_trace_command_never_silently_selects_first_aggregate_result(tmp_path, capsys):
    path = write(tmp_path / "aggregate.json", {
        "episode_count": 2,
        "results": [_reference_result_payload(episode_id="a"), _reference_result_payload(episode_id="b")],
    })
    with pytest.raises(SystemExit) as exc:
        main(["score-trace", str(path)])
    assert exc.value.code == 2
    assert "exactly one episode" in capsys.readouterr().err


@pytest.mark.parametrize("mutation", ["ongoing", "empty", "simulator_error", "model_request_error"])
def test_rescoring_rejects_unfinished_or_infrastructure_trace(tmp_path, mutation):
    demo = Path(__file__).resolve().parents[1] / "vigil/web/demo/traces"
    payload = json.loads(next(demo.glob("*.json")).read_text())
    if mutation == "ongoing":
        payload["terminal_status"] = "ongoing"
    elif mutation == "empty":
        payload["steps"] = []
    else:
        payload["steps"][0]["env_status" if mutation == "simulator_error" else "error_type"] = mutation
    path = write(tmp_path / "trace.json", payload)
    with pytest.raises(ValueError, match="unfinished|infrastructure"):
        evaluate_trace_files([path])


def test_paper_gate_checks_actual_report_instead_of_matching_flags():
    row = result()
    row["trace"][0]["runtime_action"]["executed_invocation"]["arguments"] = {"status": "fail"}
    with pytest.raises(PaperAlignmentError, match="report.*evidence"):
        trace_outcome(row)


def test_paper_gate_requires_an_actual_report_invocation():
    row = result()
    row["trace"][0]["runtime_action"]["executed_invocation"] = {"skill_name": "look", "arguments": {}}
    with pytest.raises(PaperAlignmentError, match="report.*invocation"):
        trace_outcome(row)


@pytest.mark.parametrize("reported,expected,world,benchmark", [
    ("off", "off", True, True), ("on", "off", True, False),
    ("off", "off", False, False), ("fail", None, False, False),
])
def test_paper_report_evidence_handles_state_reports_and_correct_failures(reported, expected, world, benchmark):
    row = result(world=world)
    step = row["trace"][0]
    step["runtime_action"]["executed_invocation"]["arguments"] = {"status": reported}
    step["judge_result"]["oracle_facts"] = {"expected_report_status": expected}
    step["judge_result"]["report_matches_world"] = reported == expected if expected else True
    assert trace_outcome(row) == (world, benchmark)
