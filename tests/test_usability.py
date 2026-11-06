import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from vigil.cli import _model_config_from_args, build_parser, main as cli_main
from vigil.eval.batch import _existing_episode_outputs
from vigil.agent.backends.base import ChatResult, ModelBackendConfig
from vigil.eval.runner import OpenAIModelAgent, run_episode
from test_cli import _write_episode, _write_finished_trace
from test_sim_runner import _NonTerminalSuccessEnv

ROOT = Path(__file__).resolve().parents[1]


def main(argv):
    return cli_main(["--no-config", *argv])


@pytest.fixture
def clean_model_env(monkeypatch):
    for name in list(os.environ):
        if name.startswith("VIGIL_") or name in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}:
            monkeypatch.delenv(name)
    monkeypatch.setenv("VIGIL_MODEL_NAME", "environment-model")
    monkeypatch.setenv("VIGIL_BACKEND", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-only-key")
    monkeypatch.setenv("VIGIL_TEMPERATURE", "0.2")


def config(*flags):
    return _model_config_from_args(build_parser().parse_args(["run-episode", "sample", *flags]))


def test_cli_overrides_one_field_and_preserves_provider_credentials(clean_model_env):
    resolved = config("--model", "another-model", "--temperature", "0.7")
    assert (resolved.model, resolved.temperature) == ("another-model", 0.7)
    assert resolved.backend == "anthropic"
    assert resolved.api_key == "test-only-key"
    assert config("--temperature", "0").temperature == 0


def test_explicit_nullable_values_and_extra_body_override_env(clean_model_env, monkeypatch):
    monkeypatch.setenv("VIGIL_EXTRA_BODY_JSON", '{"old":true}')
    monkeypatch.setenv("VIGIL_TOP_K", "8")
    resolved = config("--temperature", "none", "--top-k", "none", "--request-extra-body-json", "{}")
    assert resolved.temperature is None and resolved.top_k is None and resolved.extra_body == {}


def test_explicit_url_replaces_environment_endpoint_pool(clean_model_env, monkeypatch):
    monkeypatch.setenv("VIGIL_MODEL_BASE_URLS", "http://old.invalid/one,http://old.invalid/two")
    resolved = config("--base-url", "http://new.invalid/v1/chat/completions")
    assert resolved.base_urls == (resolved.base_url,)
    assert resolved.base_url.startswith("http://new.invalid/")


@pytest.mark.parametrize("url, expected", [
    ("https://gateway.invalid/inference/service/v1/", "https://gateway.invalid/inference/service/v1/chat/completions"),
    ("https://gateway.invalid/proxy/192.0.2.10:8000/v1?route=test", "https://gateway.invalid/proxy/192.0.2.10:8000/v1/chat/completions?route=test"),
    ("https://gateway.invalid/custom/chat", "https://gateway.invalid/custom/chat"),
    ("https://gateway.invalid/inference/v1/chat/completions", "https://gateway.invalid/inference/v1/chat/completions"),
])
def test_openai_gateway_base_url_with_path_prefix(clean_model_env, url, expected):
    resolved = config("--backend", "openai-compatible", "--base-url", url)
    assert resolved.base_url == expected
    assert resolved.base_urls == (expected,)


def test_explicit_backend_selects_its_provider_key(clean_model_env, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    assert config("--backend", "gemini").api_key == "gemini-test-key"
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test-key")
    assert config("--backend", "openai").base_url == "https://api.openai.com/v1/chat/completions"


def test_no_frames_keeps_rgb_and_removes_temporary_images(tmp_path, monkeypatch):
    paths = []
    captured = []
    pixels = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aNQkAAAAASUVORK5CYII=")

    class FrameEnv(_NonTerminalSuccessEnv):
        def save_frame(self, path):
            paths.append(Path(path))
            Path(path).write_bytes(pixels)
            return path

    class Client:
        def chat(self, messages, **kwargs):
            captured.append(messages[-1]["content"])
            return ChatResult('{"skill_name":"look","arguments":{"direction":"up","magnitude":10}}')

    _write_episode(tmp_path, "sample")
    monkeypatch.setattr("vigil.eval.runner.PublicThorEnv", FrameEnv)
    agent = OpenAIModelAgent(ModelBackendConfig(base_url="http://unused.invalid", model="test"))
    agent.client = Client()
    result = run_episode(episode_path=tmp_path / "sample/episode.json", agent=agent,
                         out_dir=tmp_path / "out", save_frames=False, max_steps=2)
    assert len(captured) == 2
    for content in captured:
        assert any(part.get("type") == "image_url" and part["image_url"]["url"].startswith("data:image/png;base64,") for part in content)
    assert paths and all(not path.exists() for path in paths)
    assert not (tmp_path / "out/frames").exists()
    assert result.trace_path.is_file()


def test_no_frames_cleans_up_on_render_failure(tmp_path, monkeypatch):
    from vigil.eval.runner import BlackFrameError
    paths = []

    class BrokenEnv(_NonTerminalSuccessEnv):
        def save_frame(self, path):
            paths.append(Path(path))
            return None

    _write_episode(tmp_path, "sample")
    monkeypatch.setattr("vigil.eval.runner.PublicThorEnv", BrokenEnv)
    agent = OpenAIModelAgent(ModelBackendConfig(base_url="http://unused.invalid", model="test"))
    with pytest.raises(BlackFrameError):
        run_episode(episode_path=tmp_path / "sample/episode.json", agent=agent,
                    out_dir=tmp_path / "out", save_frames=False)
    assert paths and not paths[0].parent.exists()
    assert not (tmp_path / "out/traces/sample.json").exists()


def test_resume_rejects_empty_and_inconsistent_scores(tmp_path):
    for folder, name in (("traces", "sample.json"), ("scores", "sample.score.json")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / name).write_text("{}")
    assert _existing_episode_outputs(tmp_path, "sample") is None
    _write_finished_trace(tmp_path, "sample")
    assert _existing_episode_outputs(tmp_path, "sample") is not None
    score_path = tmp_path / "scores/sample.score.json"
    payload = json.loads(score_path.read_text())
    payload["success"] = not payload["success"]
    score_path.write_text(json.dumps(payload))
    assert _existing_episode_outputs(tmp_path, "sample") is None


def test_resume_rejects_trace_without_steps_even_with_matching_score(tmp_path):
    from vigil.eval.traces import load_trace
    from vigil.eval.scoring import score_episode
    trace_path = _write_finished_trace(tmp_path, "sample")
    payload = json.loads(trace_path.read_text())
    payload["steps"] = []
    trace_path.write_text(json.dumps(payload))
    score = score_episode(load_trace(trace_path)).to_dict()
    (tmp_path / "scores/sample.score.json").write_text(json.dumps(score))
    assert _existing_episode_outputs(tmp_path, "sample") is None


def test_resume_rejects_trace_from_another_profile(tmp_path):
    _write_finished_trace(tmp_path, "sample")
    assert _existing_episode_outputs(tmp_path, "sample", profile="different-profile") is None


@pytest.fixture
def mini_run(tmp_path, monkeypatch):
    episodes = tmp_path / "episodes"
    _write_episode(episodes, "sample")
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"pack_id": "mini", "episodes": [{"path": "episodes/sample/episode.json"}]}))
    out = tmp_path / "out"
    calls = []

    def fake_run(*, episode_path, out_dir, **kwargs):
        calls.append(kwargs)
        path = _write_finished_trace(Path(out_dir), Path(episode_path).parent.name)
        # Model the complete runtime artifact, including the recorded settlement.
        from vigil.eval.settlement import settle_trace
        from vigil.eval.traces import load_trace
        from vigil.eval.scoring import score_episode
        trace = load_trace(path)
        trace.metadata["settlement"] = settle_trace(trace).to_dict()
        path.write_text(json.dumps(trace.to_dict()))
        (Path(out_dir) / "scores" / f"{trace.episode_id}.score.json").write_text(json.dumps(score_episode(trace).to_dict()))
        return SimpleNamespace(trace_path=path, score=SimpleNamespace(terminal_status="timeout", episode_score=0))

    monkeypatch.setattr("vigil.eval.runner.run_episode", fake_run)
    args = ["run-pack", "--pack-file", str(pack), "--episode-root", str(episodes), "--out-dir", str(out), "--episode-timeout-s", "0"]
    return args, out, calls


@pytest.mark.parametrize("change", [["--model", "changed"], ["--temperature", "0.8"], ["--max-steps", "2"], ["--width", "320"]])
def test_resume_refuses_experiment_changes_without_overwriting_metadata(mini_run, clean_model_env, change):
    args, out, calls = mini_run
    assert main(args) == 0
    original = (out / "model_config.json").read_bytes()
    with pytest.raises(SystemExit) as error:
        main([*args, "--resume-existing", *change])
    assert error.value.code == 2
    assert len(calls) == 1
    assert (out / "model_config.json").read_bytes() == original
    assert "test-only-key" not in (out / "run_config.json").read_text()


def test_resume_rejects_changed_episode_assets(mini_run, clean_model_env):
    args, out, calls = mini_run
    assert main(args) == 0
    path = Path(args[args.index("--episode-root") + 1]) / "sample/episode.json"
    payload = json.loads(path.read_text())
    payload["task"]["instruction"] = "a changed task"
    path.write_text(json.dumps(payload))
    with pytest.raises(SystemExit):
        main([*args, "--resume-existing"])
    assert len(calls) == 1


def test_existing_run_requires_explicit_resume_and_rejects_missing_manifest(mini_run, clean_model_env):
    args, out, calls = mini_run
    assert main(args) == 0
    with pytest.raises(SystemExit):
        main(args)
    assert main([*args, "--resume-existing"]) == 0
    assert len(calls) == 1
    (out / "run_config.json").unlink()
    with pytest.raises(SystemExit):
        main([*args, "--resume-existing"])


def test_subprocess_receives_same_effective_model_config(mini_run, clean_model_env, monkeypatch):
    args, out, _ = mini_run
    expected = config("--model", "changed", "--temperature", "none", "--supports-json-mode", "0")

    def fake_process(cmd, **kwargs):
        child_args = build_parser().parse_args(cmd[3:])
        assert _model_config_from_args(child_args) == expected
        _write_finished_trace(out, "sample")
        return 0

    monkeypatch.setattr("vigil.eval.batch.run_episode_process", fake_process)
    assert main([*args, "--episode-timeout-s", "5", "--model", "changed", "--temperature", "none", "--supports-json-mode", "0"]) == 0


def test_configured_key_is_not_copied_into_child_arguments(mini_run, clean_model_env, monkeypatch):
    args, out, _ = mini_run
    key = "test-only-subprocess-secret"
    settings = out.parent / "model-settings.json"
    settings.write_text(json.dumps({"api_key": key}))
    def fake_process(cmd, **kwargs):
        assert key not in repr(cmd)
        assert "--api-key" not in cmd
        assert kwargs["env"]["VIGIL_API_KEY"] == key
        assert "ANTHROPIC_API_KEY" not in kwargs["env"]
        _write_finished_trace(out, "sample")
        return 0
    monkeypatch.setattr("vigil.eval.batch.run_episode_process", fake_process)
    assert cli_main([*args, "--config", str(settings), "--episode-timeout-s", "5"]) == 0
    assert os.environ.get("ANTHROPIC_API_KEY") == "test-only-key"
    assert key not in (out / "run_config.json").read_text()


def test_canonical_alias_works_outside_checkout_and_dry_run_respects_limit(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["list-episodes", "--max-episodes", "1", "--json"]) == 0
    row = json.loads(capsys.readouterr().out)[0]
    assert main(["run-pack", "--dry-run", "--task-family", row["task_family"], "--max-episodes", "1", "--out-dir", str(tmp_path / "dry")]) == 0
    payload = json.loads(next((tmp_path / "dry").glob("*.json")).read_text())
    assert payload["summary"]["episode_count"] == 1
    assert payload["episodes"][0]["task_family"] == row["task_family"]


@pytest.mark.parametrize("flags", [["--max-episodes", "0"], ["--workers", "-1"], ["--episode-timeout-s", "nan"], ["--start-index", "-1"], ["--request-extra-body-json", "oops"]])
def test_invalid_cli_values_fail_before_execution(flags):
    with pytest.raises(SystemExit) as error:
        build_parser().parse_args(["run-pack", *flags])
    assert error.value.code == 2


def test_doctor_checks_assets_and_keeps_credentials_private(mini_run, clean_model_env, monkeypatch, capsys):
    args, out, _ = mini_run
    monkeypatch.setattr("vigil.diagnostics.find_spec", lambda name: object())
    doctor_args = ["doctor", "--pack-file", args[2], "--episode-root", args[4], "--out-dir", str(out), "--json"]
    assert main(doctor_args) == 0
    text = capsys.readouterr().out
    assert "test-only-key" not in text
    checks = json.loads(text)
    assert next(c for c in checks if c["check"] == "data")["status"] == "ok"
    (Path(args[4]) / "sample/episode.json").unlink()
    assert main(doctor_args) == 1


def test_report_uses_world_and_benchmark_success(mini_run, clean_model_env, capsys):
    args, out, _ = mini_run
    assert main(args) == 0
    capsys.readouterr()
    assert main(["report", str(out)]) == 0
    text = capsys.readouterr().out
    assert "World completion W:" in text and "Benchmark success B:" in text
    assert (out / "summary.txt").read_text().strip() == text.strip()


def test_smoke_reports_model_request_failures_and_retries_them_on_resume(mini_run, clean_model_env, monkeypatch):
    from vigil.eval.traces import load_trace
    from vigil.eval.scoring import score_episode
    args, out, _ = mini_run
    count = []

    def failed_run(*, out_dir, **kwargs):
        count.append(1)
        trace_path = _write_finished_trace(Path(out_dir), "sample")
        payload = json.loads(trace_path.read_text())
        payload["steps"][0]["error_type"] = "model_request_error: HTTP 401"
        trace_path.write_text(json.dumps(payload))
        score = score_episode(load_trace(trace_path))
        (out / "scores/sample.score.json").write_text(json.dumps(score.to_dict()))
        return SimpleNamespace(trace_path=trace_path, score=score)

    monkeypatch.setattr("vigil.eval.runner.run_episode", failed_run)
    assert main(["smoke", *args[1:]]) == 1
    assert not (out / "aggregate_score.json").exists()
    status = json.loads((out / "run_status.json").read_text())
    assert status["state"] == "infrastructure_error"
    assert status["infrastructure_errors"] == ["sample"]
    assert main(["smoke", *args[1:], "--resume-existing"]) == 1
    assert len(count) == 2


def test_doctor_provider_without_key_fails_static_check(mini_run, clean_model_env, monkeypatch, capsys):
    args, out, _ = mini_run
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr("vigil.diagnostics.find_spec", lambda name: object())
    assert main(["doctor", "--pack-file", args[2], "--episode-root", args[4], "--out-dir", str(out)]) == 1
    assert "requires an API key" in capsys.readouterr().out


def test_source_launcher_rejects_old_python_with_actionable_message(tmp_path):
    import subprocess
    old_python = tmp_path / "old-python"
    old_python.write_text("#!/bin/sh\nexit 1\n")
    old_python.chmod(0o755)
    env = {**os.environ, "PYTHON_BIN": str(old_python)}
    result = subprocess.run(["bash", str(ROOT / "start.sh"), "--help"], env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert "Python 3.10+" in result.stderr and "PYTHON_BIN" in result.stderr
