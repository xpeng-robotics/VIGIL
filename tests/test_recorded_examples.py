from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from vigil.eval.inspection import verify_run
from vigil.web.app import Workbench

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples/recorded-runs"
SPEC = importlib.util.spec_from_file_location("recorded_export", ROOT / "scripts/release/export_recorded_example.py")
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


@pytest.mark.parametrize("name,steps,world,benchmark", [
    ("verified-fridge", 5, 1, 1), ("sequential-apple", 6, 1, 1),
    ("false-report-fridge", 5, 0, 0), ("post-goal-kettle", 25, 1, 0),
    ("verified-microwave", 1, 1, 1), ("mismatch-microwave", 1, 1, 0),
])
def test_recorded_example_evidence_and_frames(name, steps, world, benchmark):
    folder = EXAMPLES / name
    result = verify_run(folder, require_frames=True)
    assert (result["agent_steps"], result["world_success_count"], result["benchmark_success_count"]) == (steps, world, benchmark)
    provenance = json.loads((folder / "provenance.json").read_text())
    assert len(provenance["frames"]) == steps + 1
    for frame in provenance["frames"]:
        assert EXPORT.digest(folder / frame["file"]) == frame["sha256"]
    for path in folder.rglob("*.json"):
        EXPORT.check_public(json.loads(path.read_text()))


def test_workbench_displays_archived_model_action_text(tmp_path):
    app = Workbench(config=tmp_path / "empty.json", results=EXAMPLES)
    runs = app.discover_runs()
    selected = next(r for r in runs if r["name"] == "verified-fridge")
    detail = app.run_detail(selected["id"])
    assert detail["recording"]["feedback"] == "none"
    assert "not a representative" in detail["recording"]["scope"]
    intervention = next(r for r in runs if r["name"] == "sequential-apple")
    assert app.run_detail(intervention["id"])["recording"]["feedback"] == "proprio_minimal"
    episode = detail["episodes"][0]["episode_id"]
    replay = app.episode_trace(selected["id"], episode)
    assert '"navigate"' in replay["steps"][0]["response"]
    assert replay["steps"][3]["executed"]["x"] == 300
    assert replay["steps"][3]["action"]["arguments"]["x"] == 470


def test_state_verification_pair_has_identical_input_and_opposite_reports():
    inputs, reports = [], []
    for name in ("verified-microwave", "mismatch-microwave"):
        folder = EXAMPLES / name
        provenance = json.loads((folder / "provenance.json").read_text())
        inputs.append(EXPORT.digest(folder / provenance["frames"][0]["file"]))
        trace = json.loads(next((folder / "traces").glob("*.json")).read_text())
        assert trace["profile"] == "pure_rgb_dialogue_history_baseline"
        assert provenance["profile"]["feedback_policy"] == "none"
        reports.append(trace["steps"][0]["action"]["arguments"]["status"])
    assert inputs[0] == inputs[1]
    assert reports == ["closed", "open"]


def test_archive_export_rejects_changed_evidence_before_writing(tmp_path):
    folder = EXAMPLES / "verified-fridge"
    trace = json.loads(next((folder / "traces").glob("*.json")).read_text())
    provenance = json.loads((folder / "provenance.json").read_text())
    raw = {**trace["metadata"], "episode_id": trace["episode_id"],
           "terminal_status": trace["terminal_status"], "score_summary": provenance["archived_score_summary"]}
    raw["trace"] = [{"step": i+1, "ok": s["metadata"]["env_result"]["simulator_success"],
                     **{k: s["metadata"][k] for k in ("model_output", "runtime_action", "env_result", "judge_result")}}
                    for i, s in enumerate(trace["steps"])]
    frames = tmp_path / "frames"
    frames.mkdir()
    for item in provenance["frames"]:
        shutil.copy2(folder / item["file"], frames / item["source_file"])
    source = tmp_path / "source.json"
    source.write_text(json.dumps(raw))
    valid = tmp_path / "valid"
    EXPORT.export_example(source, frames, "recorded-model", valid)
    assert verify_run(valid, require_frames=True)["world_success_count"] == 1
    raw["settlement"]["world_success"] = False
    source.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="settlement disagrees"):
        EXPORT.export_example(source, frames, "recorded-model", tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_public_export_refuses_transport_credentials():
    with pytest.raises(ValueError, match="Private transport field"):
        EXPORT.check_public({"authorization": "sample-private-value"})
