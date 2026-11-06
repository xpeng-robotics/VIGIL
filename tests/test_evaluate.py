import json
from pathlib import Path

import pytest

from vigil.cli import main
from vigil.eval.offline import collect_trace_files, evaluate_trace_files, load_traces


def _write_trace(path: Path, *, episode_id: str, success: bool) -> Path:
    path.write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "profile": "pure_rgb_dialogue_history_baseline",
                "max_steps": 5,
                "terminal_status": "success" if success else "timeout",
                "steps": [
                    {
                        "step_index": 0,
                        "action": {"skill_name": "MoveAhead", "arguments": {}},
                        "action_valid": True,
                        "env_status": "success",
                        "judge_success": success,
                        "progress": 1.0 if success else 0.5,
                        "terminal": success,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_collect_trace_files_from_explicit_paths(tmp_path):
    success = _write_trace(tmp_path / "success.json", episode_id="ok", success=True)
    failed = _write_trace(tmp_path / "failed.json", episode_id="fail", success=False)
    files = collect_trace_files([success, failed])
    assert len(files) == 2


def test_evaluate_trace_files_aggregate(tmp_path):
    success = _write_trace(tmp_path / "success.json", episode_id="ok", success=True)
    failed = _write_trace(tmp_path / "failed.json", episode_id="fail", success=False)
    aggregate = evaluate_trace_files([success, failed])
    assert aggregate.episode_count == 2
    assert aggregate.success_rate == 0.0
    assert aggregate.mean_episode_score == 0.1
    assert aggregate.mean_primary_score == 0.1
    assert aggregate.mean_progress_score == 0.75


def test_load_traces_from_directory_ignores_non_trace_json(tmp_path):
    _write_trace(tmp_path / "success.json", episode_id="ok", success=True)
    (tmp_path / "manifest.json").write_text('{"episodes": []}', encoding="utf-8")
    traces = load_traces([tmp_path])
    assert len(traces) == 1
    assert traces[0].episode_id == "ok"


def test_cli_score_traces_json(tmp_path, capsys):
    success = _write_trace(tmp_path / "success.json", episode_id="ok", success=True)
    failed = _write_trace(tmp_path / "failed.json", episode_id="fail", success=False)
    assert main(["score-traces", str(success), str(failed)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["episode_count"] == 2
    assert payload["success_rate"] == 0.0


def test_cli_score_traces_out(tmp_path):
    success = _write_trace(tmp_path / "success.json", episode_id="ok", success=True)
    failed = _write_trace(tmp_path / "failed.json", episode_id="fail", success=False)
    out = tmp_path / "aggregate.json"
    assert main(["score-traces", str(success), str(failed), "--out", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["episode_count"] == 2


def _reference_result_payload(*, episode_id: str = "ref_ok") -> dict:
    return {
        "episode_id": episode_id,
        "task_family": "S1_pixel_grounding",
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
            "step_budget": 5,
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


def _write_reference_result(path: Path, *, episode_id: str = "ref_ok") -> Path:
    path.write_text(json.dumps(_reference_result_payload(episode_id=episode_id)), encoding="utf-8")
    return path


def test_evaluate_trace_files_accepts_reference_result_json(tmp_path):
    result_path = _write_reference_result(tmp_path / "ref_result.json")
    aggregate = evaluate_trace_files([result_path])
    payload = aggregate.to_dict()

    assert aggregate.episode_count == 1
    assert payload["results"][0]["episode_id"] == "ref_ok"
    assert payload["results"][0]["score_summary"]["diagnostics"]["world_success"] is True
    assert payload["results"][0]["score_summary"]["primary_score"] == 0.1


def test_evaluate_trace_files_accepts_reference_aggregate_json(tmp_path):
    aggregate_path = tmp_path / "aggregate_score.json"
    aggregate_path.write_text(
        json.dumps(
            {
                "episode_count": 2,
                "results": [
                    _reference_result_payload(episode_id="ref_a"),
                    _reference_result_payload(episode_id="ref_b"),
                ],
            }
        ),
        encoding="utf-8",
    )

    aggregate = evaluate_trace_files([aggregate_path])
    payload = aggregate.to_dict()

    assert aggregate.episode_count == 2
    assert [item["episode_id"] for item in payload["results"]] == ["ref_a", "ref_b"]
    assert payload["overall_world_success_rate"] == 1.0


def test_collect_trace_files_recurses_for_reference_results(tmp_path):
    nested = tmp_path / "run" / "episodes"
    nested.mkdir(parents=True)
    _write_reference_result(nested / "ref_result.json")
    (tmp_path / "aggregate_score.json").write_text('{"episode_count": 1, "results": []}', encoding="utf-8")

    files = collect_trace_files([tmp_path])

    assert len(files) == 1
    assert files[0].name == "ref_result.json"


def test_evaluate_rejects_duplicate_episode_ids(tmp_path):
    import pytest

    a = _write_trace(tmp_path / "a.json", episode_id="same", success=True)
    b = _write_trace(tmp_path / "b.json", episode_id="same", success=False)
    with pytest.raises(ValueError, match="Duplicate episode_id"):
        evaluate_trace_files([a, b])
    with pytest.raises(ValueError, match="Duplicate episode_id"):
        evaluate_trace_files([tmp_path, a])


@pytest.mark.parametrize("command", ["score-trace", "score-traces"])
@pytest.mark.parametrize("target", ["input", "other", "symlink"])
def test_offline_scoring_never_overwrites_existing_evidence(tmp_path, command, target, capsys):
    source = _write_trace(tmp_path / "trace.json", episode_id="example", success=True)
    output = source if target == "input" else tmp_path / "result.json"
    if target == "symlink":
        output.symlink_to(source)
    elif target == "other":
        output.write_text("existing experiment evidence")
    original = {source: source.read_bytes(), output: output.read_bytes()}
    with pytest.raises(SystemExit) as error:
        main([command, str(source), "--out", str(output)])
    assert error.value.code == 2
    assert "new --out path" in capsys.readouterr().err
    assert all(path.read_bytes() == contents for path, contents in original.items())


@pytest.mark.parametrize("change", [
    lambda p: p["steps"][0].update(step_index=5),
    lambda p: p["steps"][0].update(step_index=0.5),
    lambda p: p["steps"][0].update(step_index=True),
    lambda p: p["steps"].append({**p["steps"][0], "step_index": 1}),
    lambda p: p.update(steps=[None]),
])
def test_offline_scoring_rejects_broken_step_order_and_structure(tmp_path, change, capsys):
    source = _write_trace(tmp_path / "trace.json", episode_id="example", success=True)
    payload = json.loads(source.read_text())
    change(payload)
    source.write_text(json.dumps(payload))
    output = tmp_path / "new-score.json"
    with pytest.raises(SystemExit) as error:
        main(["score-traces", str(source), "--out", str(output)])
    assert error.value.code == 2 and not output.exists()
    assert "Traceback" not in capsys.readouterr().err


def test_recorded_rollout_rescores_without_model_config_or_simulator(tmp_path, monkeypatch):
    import importlib.abc
    import sys
    demo = Path(__file__).resolve().parents[1] / "vigil/web/demo"
    class BlockSimulation(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname.startswith(("ai2thor", "vigil.envs")):
                raise AssertionError("offline scoring imported a simulator")
    monkeypatch.setattr(sys, "meta_path", [BlockSimulation(), *sys.meta_path])
    monkeypatch.chdir(tmp_path)
    (tmp_path / "vigil.json").write_text("malformed configuration must not be loaded")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("offline scoring called an API"))
    output = tmp_path / "rescored.json"
    assert main(["score-traces", str(demo), "--out", str(output)]) == 0
    assert json.loads(output.read_text()) == json.loads((demo / "aggregate_score.json").read_text())
