"""Keep browsing, credential storage and curated source exports independent."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from vigil.web.app import Workbench
from test_web_app import FakeProcess

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_export_boundaries", ROOT / "scripts/release/export_public_release.py")
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


def test_browsing_examples_does_not_redirect_new_runs_or_credentials(tmp_path, monkeypatch):
    browse = tmp_path / "examples/recorded-runs"
    browse.mkdir(parents=True)
    outputs = tmp_path / "new-evaluations"
    config = tmp_path / "model.json"
    config.write_text(json.dumps({"backend": "openai-compatible", "model": "test", "base_url": "http://example.invalid/v1", "api_key": "dummy-test-key"}))
    app = Workbench(config=config, results=browse, out_dir=outputs)
    process = FakeProcess()
    captured = {}
    monkeypatch.setattr("vigil.web.app.find_spec", lambda _: object())
    def launch(command, **kwargs):
        captured["command"] = command
        return process
    monkeypatch.setattr("vigil.web.app.subprocess.Popen", launch)
    try:
        result = app.start_run({"episode_ids": [app.catalog[0]["episode_id"]]})
        command = captured["command"]
        snapshot = Path(command[command.index("--config") + 1])
        assert app.run_path(result["id"]).is_relative_to(outputs)
        assert any(row["id"] == result["id"] for row in app.discover_runs())
        assert list(browse.iterdir()) == []
        assert not snapshot.is_relative_to(outputs) and not snapshot.is_relative_to(browse)
        assert snapshot.stat().st_mode & 0o777 == 0o600
        assert snapshot.parent.stat().st_mode & 0o777 == 0o700
        assert "dummy-test-key" not in json.dumps(app.run_detail(result["id"]))
    finally:
        process.finish()


def test_export_ignores_unreviewed_runs_and_hidden_snapshots(tmp_path):
    base = tmp_path / "examples/recorded-runs"
    good = base / "reviewed/traces/episode.json"
    good.parent.mkdir(parents=True)
    good.write_text('{"recorded":true}')
    manifest = {"reviewed/traces/episode.json": hashlib.sha256(good.read_bytes()).hexdigest()}
    (base / "manifest.json").write_text(json.dumps(manifest))
    for name in (".ui-configs/run.json", "incidental/model_config.json", "reviewed/private.json"):
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"api_key":"dummy-test-key"}')
    selected = EXPORT.recorded_files(tmp_path)
    assert {str(p) for p in selected} == {"examples/recorded-runs/manifest.json", "examples/recorded-runs/reviewed/traces/episode.json"}
    good.write_text('{"recorded":false}')
    with pytest.raises(ValueError, match="differs"):
        EXPORT.recorded_files(tmp_path)


@pytest.mark.parametrize("name", ["../private.json", "/private/config.json", ".ui-configs/config.json"])
def test_recorded_manifest_rejects_unsafe_paths(tmp_path, name):
    base = tmp_path / "examples/recorded-runs"
    base.mkdir(parents=True)
    (base / "manifest.json").write_text(json.dumps({name: "0" * 64}))
    with pytest.raises(ValueError, match="unsafe"):
        EXPORT.recorded_files(tmp_path)


def test_all_six_homepage_cases_resolve_to_their_own_trace(tmp_path):
    recordings = ROOT / "examples/recorded-runs"
    app = Workbench(config=tmp_path / "missing.json", results=tmp_path / "read",
                    out_dir=tmp_path / "write", recordings=recordings)
    app.discover_runs()
    cases = app.recorded_cases()
    assert len(cases) == 6
    for case in cases:
        replay = app.episode_trace(case["run_id"], case["episode_id"])
        assert len(replay["steps"]) == case["steps"]
        assert all(step["frame"] for step in replay["steps"])
        assert app.run_path(case["run_id"]) == recordings / case["id"]
