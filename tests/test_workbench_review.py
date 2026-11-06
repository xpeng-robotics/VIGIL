"""Adversarial result and launch checks from the workbench review."""
import json
from pathlib import Path
import shutil

import pytest

from vigil.eval.scoring import score_episode
from vigil.cli import main
from vigil.eval.traces import EpisodeTrace
from vigil.web.app import ASSETS, Workbench, make_server


@pytest.fixture
def recorded(tmp_path):
    root = tmp_path / "results/run"
    shutil.copytree(ASSETS / "demo", root)
    return root


def workbench(root):
    return Workbench(config=root.parent / "absent.json", results=root.parent, out_dir=root.parent)


def mutate(path, callback):
    obj = json.loads(path.read_text())
    callback(obj)
    path.write_text(json.dumps(obj))


def success_payload():
    return next(json.loads(p.read_text()) for p in (ASSETS / "demo/traces").glob("*.json")
                if json.loads(p.read_text())["terminal_status"] == "success")


@pytest.mark.parametrize("field", ["judge_success", "action_valid", "terminal"])
def test_trace_booleans_are_not_coerced_from_strings(field):
    payload = success_payload()
    payload["steps"][-1][field] = "false"
    with pytest.raises(ValueError, match="boolean"):
        score_episode(EpisodeTrace.from_dict(payload))


@pytest.mark.parametrize("field", ["world_success", "semantic_world_success", "strict_world_success", "protocol_failure", "recoverable"])
def test_judge_evidence_requires_real_booleans(field):
    payload = success_payload()
    payload["steps"][-1]["metadata"]["judge_result"][field] = "false"
    with pytest.raises(ValueError, match="boolean"):
        score_episode(EpisodeTrace.from_dict(payload))


def test_ui_does_not_present_unverified_aggregate_as_final(recorded):
    app = workbench(recorded)
    run = next(r for r in app.discover_runs() if not r["demo"])
    assert app.run_detail(run["id"])["metrics"]["success_rate"] == 0.5
    mutate(recorded / "aggregate_score.json", lambda p: p.update(success_rate=1.0))
    detail = app.run_detail(run["id"])
    assert detail["metrics"] is None
    assert detail["verification_error"]


def test_ui_revalidates_when_trace_changes(recorded):
    app = workbench(recorded)
    run = next(r for r in app.discover_runs() if not r["demo"])
    assert app.run_detail(run["id"])["metrics"]
    trace = next((recorded / "traces").glob("*.json"))
    mutate(trace, lambda p: p.update(steps=[]))
    assert app.run_detail(run["id"])["metrics"] is None


def test_report_does_not_present_tampered_run_metrics(recorded, capsys):
    mutate(recorded / "aggregate_score.json", lambda p: p.update(success_rate=1.0))
    with pytest.raises(SystemExit) as exc:
        main(["report", str(recorded)])
    assert exc.value.code == 2
    assert "aggregate" in capsys.readouterr().err


def test_one_malformed_run_does_not_break_the_library(recorded):
    bad = recorded.parent / "broken"
    bad.mkdir()
    (bad / "run_status.json").write_text("[]")
    runs = workbench(recorded).discover_runs()
    assert any(r["demo"] for r in runs)
    assert next(r for r in runs if r["name"] == "broken")["state"] == "invalid"


def test_replaced_run_directory_cannot_escape_results(recorded, tmp_path):
    app = workbench(recorded)
    run = next(r for r in app.discover_runs() if not r["demo"])
    outside = tmp_path / "outside"
    recorded.rename(outside)
    recorded.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        app.run_detail(run["id"])


def test_run_metadata_symlinks_cannot_escape_results(recorded, tmp_path):
    app = workbench(recorded)
    run = next(r for r in app.discover_runs() if not r["demo"])
    outside = tmp_path / "outside.json"
    outside.write_text('{"model":"private external metadata"}')
    (recorded / "model_config.json").unlink()
    (recorded / "model_config.json").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        app.run_detail(run["id"])


def test_missing_simulator_is_caught_before_any_run_is_created(tmp_path, monkeypatch):
    app = Workbench(config=tmp_path / "absent.json", results=tmp_path / "outputs")
    monkeypatch.setattr("vigil.web.app.find_spec", lambda _: None)
    with pytest.raises(ValueError, match="Install the simulator"):
        app.start_run({"episode_ids": [app.catalog[0]["episode_id"]]})
    assert app.process is None and not app.results.exists()


@pytest.mark.parametrize("port", [-1, 65536])
def test_invalid_ui_port_has_actionable_error(recorded, port):
    with pytest.raises(ValueError, match="port"):
        make_server(workbench(recorded), port)
