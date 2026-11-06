"""Exercise the public workbench at its HTTP and CLI boundaries; no model calls."""
import json
import os
from pathlib import Path
import shutil
import threading
import urllib.error
import urllib.request

import pytest

from vigil.cli import build_parser
from vigil.eval.offline import evaluate_trace_files
from vigil.web.app import ASSETS, Workbench, make_server

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in list(os.environ):
        if name.startswith("VIGIL_") or name in {"OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"}:
            monkeypatch.delenv(name)
    config = tmp_path / "vigil.json"
    config.write_text(json.dumps({"backend": "openai-compatible", "model": "test-model", "base_url": "http://example.invalid/v1", "api_key": "private-test-key"}))
    workbench = Workbench(config=config, results=tmp_path / "outputs", out_dir=tmp_path / "outputs")
    yield workbench
    if workbench.process is not None and hasattr(workbench.process, "finish"):
        workbench.process.finish()


@pytest.fixture
def http(app):
    server = make_server(app, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, body=None, *, token=True, headers=None):
        h = dict(headers or {})
        if body is not None:
            h["Content-Type"] = "application/json"
            if token:
                h["X-Vigil-Token"] = app.token
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}{path}",
                                     data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    yield request
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_ui_cli_is_separate_from_live_execution():
    args = build_parser().parse_args(["ui", "--no-open", "--port", "0", "--results-dir", "saved"])
    assert args.no_open and args.port == 0 and args.results_dir == Path("saved")


def test_bootstrap_is_read_only_and_hides_the_key(app, http):
    code, body, _ = http("/api/bootstrap")
    assert code == 200 and b"private-test-key" not in body
    data = json.loads(body)
    assert data["config"]["key_configured"]
    assert "api_key" not in data["config"]
    assert len(data["episodes"]) == 1000
    assert {e["difficulty"] for e in data["episodes"]} >= {"easy", "hard"}
    assert data["episodes"][0]["difficulty"] == "easy"
    assert app.process is None and not app.results.exists()


def test_demo_contains_real_rgb_and_matches_the_shared_scorer(app, http):
    result = app.run_detail("demo")
    assert result["demo"] and result["metrics"]["episode_count"] == 2
    paths = [app.demo / "traces" / f"{r['episode_id']}.json" for r in result["episodes"]]
    assert evaluate_trace_files(paths).to_dict() == json.loads((app.demo / "aggregate_score.json").read_text())
    trace = app.episode_trace("demo", result["episodes"][0]["episode_id"])
    code, image, headers = http(trace["steps"][0]["frame"])
    assert code == 200 and image.startswith(b"\x89PNG\r\n\x1a\n")
    assert headers["Content-Type"] == "image/png"
    assert trace["steps"][0]["action"]["arguments"]["x"] != trace["steps"][0]["executed"]["x"]


def test_demo_works_without_data_or_valid_model_config(tmp_path, monkeypatch):
    monkeypatch.setenv("VIGIL_DATA_ROOT", str(tmp_path / "missing"))
    config = tmp_path / "bad.json"
    config.write_text("{broken")
    app = Workbench(config=config, results=tmp_path / "out")
    assert app.data_error and not app.catalog
    result = app.run_detail("demo")
    assert result["episodes"][0]["instruction"]
    assert app.episode_trace("demo", result["episodes"][0]["episode_id"])["steps"]
    with pytest.raises(ValueError):
        app.save_config({"model": "new"})
    assert config.read_text() == "{broken"


@pytest.mark.parametrize("state", ["running", "infrastructure_error", "cancelled", "interrupted"])
def test_incomplete_runs_never_expose_an_old_final_score(app, state):
    target = app.results / "old-run"
    shutil.copytree(app.demo, target)
    status = json.loads((target / "run_status.json").read_text())
    status["state"] = state
    (target / "run_status.json").write_text(json.dumps(status))
    run = next(r for r in app.discover_runs() if not r["demo"])
    assert app.run_detail(run["id"])["metrics"] is None


def test_save_config_preserves_key_and_uses_shared_validation(app, http):
    status, body, _ = http("/api/config", {"model": "updated", "api_key": ""})
    assert status == 200 and b"private-test-key" not in body
    saved = json.loads(app.config_path.read_text())
    assert saved["api_key"] == "private-test-key" and saved["model"] == "updated"
    assert app.config_path.stat().st_mode & 0o777 == 0o600
    before = app.config_path.read_bytes()
    status, _, _ = http("/api/config", {"max_tokens": -1})
    assert status == 400 and app.config_path.read_bytes() == before
    status, _, _ = http("/api/config", {"extra_body": {"messages": []}})
    assert status == 400 and app.config_path.read_bytes() == before
    http("/api/config", {"clear_api_key": True})
    assert json.loads(app.config_path.read_text())["api_key"] == ""


def test_cross_origin_and_missing_token_cannot_save_or_start(app, http):
    before = app.config_path.read_bytes()
    assert http("/api/config", {"model": "bad"}, token=False)[0] == 403
    assert http("/api/config", {"model": "bad"}, headers={"Origin": "https://external.invalid"})[0] == 403
    assert http("/api/runs", {"episode_ids": [app.catalog[0]["episode_id"]]}, token=False)[0] == 403
    assert http("/api/bootstrap", headers={"Host": "external.invalid"})[0] == 403
    assert app.config_path.read_bytes() == before and app.process is None


def test_file_access_is_limited_to_registered_run_assets(app, http, tmp_path):
    assert http("/vigil.json")[0] == 404
    assert http("/static/../app.py")[0] == 404
    assert http("/api/runs/demo/frames/%2E%2E/step_000.png")[0] == 400
    assert http("/api/runs/demo/frames/anything/%2E%2E%2Fvigil.json")[0] == 400
    secret = tmp_path / "secret.json"
    secret.write_text('{"private":"not-a-result"}')
    target = app.results / "linked-run"
    shutil.copytree(app.demo, target)
    (target / "aggregate_score.json").unlink()
    (target / "aggregate_score.json").symlink_to(secret)
    run = next(r for r in app.discover_runs() if not r["demo"])
    code, body, _ = http(f"/api/runs/{run['id']}/download")
    assert code == 400 and b"not-a-result" not in body


@pytest.mark.parametrize("payload", [{"episode_ids": []}, {"episode_ids": ["../../etc/passwd"]}, {"episode_ids": "not-a-list"}])
def test_invalid_selection_cannot_launch_process(app, payload):
    with pytest.raises(ValueError):
        app.start_run(payload)
    assert app.process is None


class FakeProcess:
    pid = 123456789
    def __init__(self):
        self.done = threading.Event()
        self.returncode = None
    def wait(self, timeout=None):
        self.done.wait(timeout)
        return self.returncode
    def poll(self):
        return self.returncode
    def finish(self):
        self.returncode = 1
        self.done.set()


def test_launch_delegates_to_cli_with_private_snapshot_and_no_shell(app, monkeypatch):
    monkeypatch.setattr("vigil.web.app.find_spec", lambda _: object())
    captured = {}
    process = FakeProcess()
    def launch(command, **kwargs):
        captured.update(command=command, **kwargs)
        return process
    monkeypatch.setattr("vigil.web.app.subprocess.Popen", launch)
    episode = app.catalog[0]["episode_id"]
    result = app.start_run({"episode_ids": [episode], "workers": 8, "boot_concurrency": 1, "render_concurrency": 6})
    command = captured["command"]
    assert command[1:5] == ["-u", "-m", "vigil.cli", "run"]
    assert command[command.index("--workers") + 1] == "8"
    assert command[command.index("--boot-concurrency") + 1] == "1"
    assert command[command.index("--render-concurrency") + 1] == "6"
    assert "private-test-key" not in repr(command) and not captured.get("shell")
    snapshot = Path(command[command.index("--config") + 1])
    assert snapshot.stat().st_mode & 0o777 == 0o600
    assert json.loads(snapshot.read_text())["api_key"] == "private-test-key"
    run_path = app.run_path(result["id"])
    assert not snapshot.is_relative_to(run_path)
    assert app.run_detail(result["id"])["metrics"] is None
    assert json.loads((run_path / "selection.json").read_text())["episodes"][0]["episode_id"] == episode
    with pytest.raises(ValueError, match="already active"):
        app.start_run({"episode_ids": [episode]})
    with pytest.raises(ValueError, match="current run"):
        app.save_config({"model": "different"})
    with pytest.raises(ValueError, match="Only a run"):
        app.stop_run("demo")
    process.finish()


@pytest.mark.parametrize("name", ["boot_concurrency", "render_concurrency"])
@pytest.mark.parametrize("value", [-1, 17, True, "4"])
def test_invalid_concurrency_cannot_create_a_ui_run(app, monkeypatch, name, value):
    monkeypatch.setattr("vigil.web.app.find_spec", lambda _: object())
    before = list(app.out_dir.glob("run-*"))
    with pytest.raises(ValueError, match="between 0"):
        app.start_run({"episode_ids": [app.catalog[0]["episode_id"]], name: value})
    assert app.process is None and list(app.out_dir.glob("run-*")) == before


def test_static_ui_is_shipped_and_has_no_remote_frontend_dependencies(http):
    for route in ("/", "/static/style.css", "/static/app.js"):
        assert http(route)[0] == 200
    html = (ASSETS / "static/index.html").read_text()
    assert 'src="https://' not in html and 'href="https://' not in html


def test_frame_requests_do_not_load_all_episode_results(app, http, monkeypatch):
    episode = app.run_detail("demo")["episodes"][0]["episode_id"]
    def unexpected(*args):
        raise AssertionError("A frame request must not load every episode's scores and frames.")
    monkeypatch.setattr(app, "run_detail", unexpected)
    code, body, _ = http(f"/api/runs/demo/frames/{episode}/step_000.png")
    assert code == 200 and body.startswith(b"\x89PNG\r\n\x1a\n")
