import json
import os
import subprocess
import sys
from pathlib import Path

from vigil.eval.scoring import score_result_payload

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/reproduce/compare_aggregates.py"
CHECK_REFERENCE_SCRIPT = ROOT / "scripts/reproduce/check_reference_results.py"


def _aggregate(success_rate=0.5, episode_score=0.5):
    return {
        "episode_count": 2,
        "success_rate": success_rate,
        "mean_episode_score": episode_score,
        "mean_progress_score": 0.75,
        "mean_action_validity": 1.0,
        "mean_efficiency": 0.5,
        "scores": [
            {
                "episode_id": "ok",
                "success": True,
                "episode_score": 1.0,
                "progress_score": 1.0,
                "action_validity": 1.0,
                "efficiency": 1.0,
                "steps_taken": 1,
                "max_steps": 5,
                "terminal_status": "success",
            },
            {
                "episode_id": "fail",
                "success": False,
                "episode_score": 0.0,
                "progress_score": 0.5,
                "action_validity": 1.0,
                "efficiency": 0.0,
                "steps_taken": 1,
                "max_steps": 5,
                "terminal_status": "timeout",
            },
        ],
    }


def _write(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_compare_aggregates_accepts_matching_payloads(tmp_path):
    expected = _write(tmp_path / "expected.json", _aggregate())
    actual = _write(tmp_path / "actual.json", _aggregate())
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "OK" in result.stdout


def test_compare_aggregates_reports_episode_diffs(tmp_path):
    expected_payload = _aggregate()
    actual_payload = _aggregate()
    actual_payload["scores"][1]["terminal_status"] = "stopped"
    expected = _write(tmp_path / "expected.json", expected_payload)
    actual = _write(tmp_path / "actual.json", actual_payload)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "episode.fail.terminal_status" in result.stderr



def _internal_aggregate(primary_score=0.5, terminal_status="failure"):
    return {
        "episode_count": 1,
        "mean_primary_score": primary_score,
        "success_rate": 0.0,
        "semantic_success_rate": 0.0,
        "strict_success_rate": None,
        "closure_success_rate": 0.0,
        "world_success_rate": 0.0,
        "primary_world_success_rate": 0.0,
        "semantic_world_success_rate": 0.0,
        "strict_world_success_rate": None,
        "closure_given_world_rate": None,
        "mean_steps_used": 1.0,
        "terminal_status_histogram": {terminal_status: 1},
        "diagnostic_rates": {},
        "by_task_family": {},
        "by_difficulty": {},
        "results": [
            {
                "episode_id": "state_001",
                "status": terminal_status,
                "steps_used": 1,
                "task_family": "S4_state_recognition",
                "score_summary": {
                    "task_family": "S4_state_recognition",
                    "success": False,
                    "semantic_success": False,
                    "strict_success": None,
                    "progress": 0.0,
                    "semantic_progress": 0.0,
                    "strict_progress": None,
                    "efficiency": 0.9,
                    "compliance": 0.6,
                    "primary_score": primary_score,
                    "strict_score": None,
                    "terminal_status": terminal_status,
                    "terminal_reason": "false_success_report",
                    "diagnostics": {
                        "terminal_status": terminal_status,
                        "terminal_reason": "false_success_report",
                        "world_success": False,
                        "primary_world_success": False,
                        "semantic_world_success": False,
                        "strict_world_success": None,
                        "report_submitted": True,
                        "agent_report_status": "success",
                        "report_matches_world": False,
                        "protocol_failure": False,
                        "false_report": True,
                        "budget_exhausted": False,
                        "steps_used": 1,
                        "step_budget": 10,
                        "invalid_actions": 0,
                        "protocol_failures": 0,
                        "recoverable_failures": 0,
                    },
                },
            }
        ],
    }


def test_compare_aggregates_accepts_internal_vigil_schema(tmp_path):
    expected = _write(tmp_path / "expected_internal.json", _internal_aggregate())
    actual = _write(tmp_path / "actual_internal.json", _internal_aggregate())
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "internal aggregate" in result.stdout


def test_compare_aggregates_reports_internal_score_summary_diffs(tmp_path):
    expected = _write(tmp_path / "expected_internal.json", _internal_aggregate(primary_score=0.08))
    actual = _write(tmp_path / "actual_internal.json", _internal_aggregate(primary_score=0.5))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "top.mean_primary_score" in result.stderr
    assert "episode.state_001.score_summary.primary_score" in result.stderr

def test_compare_aggregates_reports_reference_recursive_bucket_fields(tmp_path):
    expected_payload = _internal_aggregate()
    actual_payload = _internal_aggregate()
    expected_payload["diagnostic_rates"] = {"false_report": 1.0, "reference_only_detail": 7.0}
    actual_payload["diagnostic_rates"] = {"false_report": 1.0}
    expected_payload["by_task_family"] = {
        "S4_state_recognition": {
            "episode_count": 1,
            "mean_primary_score": 0.5,
            "success_rate": 0.0,
            "behavior_metrics_summary": {"reference_only": True},
        }
    }
    actual_payload["by_task_family"] = {
        "S4_state_recognition": {
            "episode_count": 1,
            "mean_primary_score": 0.5,
            "success_rate": 0.0,
        }
    }
    expected = _write(tmp_path / "expected_internal.json", expected_payload)
    actual = _write(tmp_path / "actual_internal.json", actual_payload)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "top.diagnostic_rates.reference_only_detail" in result.stderr
    assert "top.by_task_family.S4_state_recognition.behavior_metrics_summary" in result.stderr


def test_compare_aggregates_reports_diagnostic_rate_diffs(tmp_path):
    expected_payload = _internal_aggregate()
    actual_payload = _internal_aggregate()
    expected_payload["diagnostic_rates"] = {"false_report": 1.0}
    actual_payload["diagnostic_rates"] = {"false_report": 0.0}
    expected = _write(tmp_path / "expected_internal.json", expected_payload)
    actual = _write(tmp_path / "actual_internal.json", actual_payload)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "top.diagnostic_rates.false_report" in result.stderr

def _reference_result_payload():
    payload = {
        "episode_id": "state_001",
        "task_family": "S4_state_recognition",
        "difficulty": "easy",
        "trace": [
            {
                "step": 1,
                "judge_result": {
                    "invalid_action": False,
                    "protocol_failure": False,
                },
            }
        ],
        "settlement": {
            "terminal_status": "failure",
            "terminal_reason": "fail_no_report",
            "world_success": True,
            "semantic_world_success": True,
            "strict_world_success": None,
            "final_progress": 1.0,
            "semantic_final_progress": 1.0,
            "strict_final_progress": None,
            "steps_used": 1,
            "step_budget": 10,
            "report_submitted": False,
            "agent_report_status": None,
            "report_matches_world": None,
            "invalid_actions": 0,
            "protocol_failures": 0,
            "recoverable_failures": 0,
            "protocol_failure": False,
            "false_report": False,
            "budget_exhausted": False,
            "violations": [],
        },
    }
    payload["score_summary"] = score_result_payload(payload).to_dict()["score_summary"]
    return payload


def _run_check_reference(path: Path):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        [sys.executable, str(CHECK_REFERENCE_SCRIPT), "--reference-path", str(path)],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_check_reference_results_accepts_matching_score_summary(tmp_path):
    result_path = _write(tmp_path / "reference_result.json", _reference_result_payload())

    result = _run_check_reference(result_path)

    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "1 reference result file(s)" in result.stdout


def test_check_reference_results_reports_score_summary_diffs(tmp_path):
    payload = _reference_result_payload()
    payload["score_summary"]["primary_score"] = 0.99
    result_path = _write(tmp_path / "reference_result.json", payload)

    result = _run_check_reference(result_path)

    assert result.returncode == 1
    assert "episode.state_001.score_summary.primary_score" in result.stderr



def test_compare_aggregates_rejects_incomplete_pack_coverage(tmp_path):
    expected = _write(tmp_path / "expected.json", _aggregate())
    actual = _write(tmp_path / "actual.json", _aggregate())
    pack = _write(tmp_path / "pack.json", {"episodes": [
        {"episode_id": "ok"}, {"episode_id": "fail"}, {"episode_id": "missing"},
    ]})
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual),
         "--pack-file", str(pack)], text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "1 missing" in result.stderr


def test_compare_aggregates_rejects_empty_and_miscounted_results(tmp_path):
    for payload in ({"episode_count": 0, "results": []}, {**_aggregate(), "episode_count": 1000}):
        expected = _write(tmp_path / "expected.json", payload)
        actual = _write(tmp_path / "actual.json", payload)
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
            text=True, capture_output=True, check=False,
        )
        assert result.returncode == 2


def test_compare_aggregates_checks_behavior_and_full_episode_summary(tmp_path):
    expected_payload, actual_payload = _internal_aggregate(), _internal_aggregate()
    expected_payload["overall_behavior_success_rate"] = 1.0
    actual_payload["overall_behavior_success_rate"] = 0.0
    expected_payload["results"][0]["score_summary"]["behavior_success"] = True
    actual_payload["results"][0]["score_summary"]["behavior_success"] = False
    expected = _write(tmp_path / "expected.json", expected_payload)
    actual = _write(tmp_path / "actual.json", actual_payload)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--expected", str(expected), "--actual", str(actual)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 1
    assert "top.overall_behavior_success_rate" in result.stderr
    assert "episode.state_001.score_summary.behavior_success" in result.stderr
