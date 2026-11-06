"""Saved-run auditing must detect inconsistent evidence without live services."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from vigil.cli import main
from vigil.eval.inspection import inspect_progress, verify_run

DEMO = Path(__file__).resolve().parents[1] / "vigil/web/demo"


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "recorded"
    shutil.copytree(DEMO, root)
    return root


def update(path, mutate):
    payload = json.loads(path.read_text())
    mutate(payload)
    path.write_text(json.dumps(payload))


def first_trace(run):
    episode = json.loads((run / "run_status.json").read_text())["episode_ids"][0]
    return run / "traces" / f"{episode}.json"


def test_real_recording_verifies_without_config_data_or_simulator(run, monkeypatch, capsys):
    monkeypatch.chdir(run.parent)
    monkeypatch.setenv("VIGIL_DATA_ROOT", str(run / "missing-data"))
    (run / "model_config.json").unlink()
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    assert main(["verify-run", str(run), "--require-frames", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["episode_count"] == 2
    assert report["agent_steps"] == 5
    assert report["world_success_count"] == report["benchmark_success_count"] == 1
    assert report["frame_headers_checked"]
    assert before == {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}


@pytest.mark.parametrize("state", ["running", "infrastructure_error", "cancelled"])
def test_incomplete_run_cannot_pass_even_with_an_old_aggregate(run, state):
    update(run / "run_status.json", lambda p: p.update(state=state))
    with pytest.raises(ValueError, match="incomplete"):
        verify_run(run)
    assert inspect_progress(run)["metrics_verified"] is False


@pytest.mark.parametrize("ids", [[], ["same", "same"], ["../elsewhere"], [3], "episode"])
def test_invalid_selection_fails_cleanly(run, ids, capsys):
    update(run / "run_status.json", lambda p: p.update(episode_ids=ids))
    with pytest.raises(SystemExit) as exc:
        main(["verify-run", str(run)])
    assert exc.value.code == 2
    assert "Traceback" not in capsys.readouterr().err


@pytest.mark.parametrize("mutation,match", [
    (lambda p: p.update(episode_id="another-episode"), "episode ID"),
    (lambda p: p.update(steps=[]), "empty or unfinished"),
    (lambda p: p["steps"][0].update(step_index=4), "step indices"),
    (lambda p: p["steps"][0].update(terminal=True), "after a terminal"),
    (lambda p: p["steps"][0].update(env_status="simulator_error"), "infrastructure error"),
    (lambda p: p["steps"][0].update(error_type="model_request_error"), "infrastructure error"),
    (lambda p: p["metadata"]["settlement"].update(world_success=False), "settlement"),
])
def test_inconsistent_trace_is_rejected(run, mutation, match):
    update(first_trace(run), mutation)
    with pytest.raises(ValueError, match=match):
        verify_run(run)


def test_score_and_aggregate_must_both_match(run):
    score = next((run / "scores").glob("*.json"))
    original = score.read_text()
    update(score, lambda p: p.update(steps_used=900))
    with pytest.raises(ValueError, match="saved score"):
        verify_run(run)
    score.write_text(original)
    update(run / "aggregate_score.json", lambda p: p.update(success_rate=0.0))
    with pytest.raises(ValueError, match="aggregate differs"):
        verify_run(run)


def test_rescore_resume_and_verification_agree_on_invalid_sequence(run):
    from vigil.eval.batch import _existing_episode_outputs
    from vigil.eval.offline import evaluate_trace_files
    from vigil.eval.scoring import score_episode
    from vigil.eval.traces import load_trace
    path = first_trace(run)
    update(path, lambda p: p["steps"][0].update(step_index=99))
    trace = load_trace(path)
    score = run / "scores" / f"{trace.episode_id}.score.json"
    score.write_text(json.dumps(score_episode(trace).to_dict()))
    assert _existing_episode_outputs(run, trace.episode_id) is None
    with pytest.raises(ValueError, match="step indices"):
        evaluate_trace_files([path])
    with pytest.raises(ValueError, match="step indices"):
        verify_run(run)


def test_missing_evidence_fails_and_frames_are_optional(run):
    frame = next((run / "frames").rglob("*.png"))
    frame.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="invalid PNG"):
        verify_run(run, require_frames=True)
    shutil.rmtree(run / "frames")
    assert verify_run(run)["verified"]
    with pytest.raises(ValueError, match="Verification failed"):
        verify_run(run, require_frames=True)
    first_trace(run).unlink()
    with pytest.raises(ValueError, match="Verification failed"):
        verify_run(run)


def test_selection_controls_progress_and_verification(run, capsys):
    (run / "traces/old-unselected.json").write_text("{}")
    (run / "scores/old-unselected.score.json").write_text("{}")
    assert main(["progress", str(run), "--json"]) == 0
    progress = json.loads(capsys.readouterr().out)
    assert progress["saved_traces"] == progress["selected_episodes"] == 2
    assert progress["saved_scores"] == 2
    assert verify_run(run)["episode_count"] == 2


def test_progress_cli_works_outside_release(run, tmp_path):
    import os
    result = subprocess.run([sys.executable, "-m", "vigil", "progress", str(run)], cwd=tmp_path,
                            env={**os.environ, "PYTHONPATH": str(DEMO.parents[2])},
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "saved traces: 2/2" in result.stdout


def test_untracked_and_malformed_progress(tmp_path):
    assert inspect_progress(tmp_path)["state"] == "untracked"
    (tmp_path / "run_status.json").write_text("[]")
    with pytest.raises(ValueError, match="JSON object"):
        inspect_progress(tmp_path)


@pytest.mark.parametrize("as_file", [False, True])
def test_report_missing_status_never_downgrades_a_run_to_a_summary(run, capsys, as_file):
    (run / "run_status.json").unlink()
    with pytest.raises(SystemExit) as error:
        main(["report", str(run / "aggregate_score.json" if as_file else run)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "run_status.json" in output.err and "World completion" not in output.out


def test_standalone_aggregate_is_explicitly_unverified(run, tmp_path, capsys):
    path = tmp_path / "combined.json"
    shutil.copyfile(run / "aggregate_score.json", path)
    assert main(["report", str(path)]) == 0
    output = capsys.readouterr().out
    assert output.startswith("UNVERIFIED stored summary")
    assert "World completion W: 50.0%" in output and "Benchmark success B: 50.0%" in output


@pytest.mark.parametrize("changes", [
    {"episode_count": True}, {"episode_count": 0}, {"success_rate": float("nan")},
    {"world_success_rate": float("inf")}, {"success_rate": 1.1}, {"success_rate": "1"},
    {"results": []}, {"results": [{"episode_id": "same"}, {"episode_id": "same"}]},
    {"scores": [{"episode_id": "different"}, {"episode_id": "selection"}]},
    {"infrastructure_errors": ["failed request"]}, {"skipped_missing": 1},
    {"overall_episode_count": 1}, {"diagnostic_rates": []},
    {"diagnostic_rates": {"false_report": -1}}, {"terminal_status_histogram": {"success": 3}},
])
def test_standalone_report_rejects_invalid_counts_rates_and_selections(run, tmp_path, capsys, changes):
    payload = json.loads((run / "aggregate_score.json").read_text())
    payload.update(changes)
    path = tmp_path / "invalid-summary.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(SystemExit) as error:
        main(["report", str(path)])
    assert error.value.code == 2
    assert not capsys.readouterr().out
