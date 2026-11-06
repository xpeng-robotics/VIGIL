import json
import os
from pathlib import Path

import pytest

from vigil.cli import _model_config_from_args, build_parser, main
from vigil.config import apply_model_config
from test_cli import _write_episode, _write_finished_trace


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in list(os.environ):
        if name.startswith("VIGIL_") or name in {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"}:
            monkeypatch.delenv(name)


def settings(tmp_path, **values):
    path = tmp_path / "vigil.json"
    path.write_text(json.dumps({"backend": "openai-compatible", "base_url": "http://localhost:8000/v1", "model": "file-model", **values}))
    return path


def resolved(*flags):
    args = build_parser().parse_args(["smoke", *flags])
    apply_model_config(args)
    return _model_config_from_args(args)


def test_init_creates_editable_config_and_does_not_overwrite(tmp_path, capsys):
    assert main(["init"]) == 0
    path = tmp_path / "vigil.json"
    assert json.loads(path.read_text())["model"] == ""
    assert "vigil smoke" in capsys.readouterr().out
    original = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        main(["init"])
    assert error.value.code == 2 and path.read_bytes() == original
    if os.name == "posix":
        assert path.stat().st_mode & 0o077 == 0


def test_no_arguments_shows_starting_commands(capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert all(command in output for command in ("vigil init", "vigil smoke", "vigil run"))


@pytest.mark.parametrize("backend", ["openai-compatible", "openai", "gemini", "anthropic"])
def test_init_model_and_endpoint_create_runnable_private_configuration(tmp_path, backend, monkeypatch):
    monkeypatch.setenv("VIGIL_API_KEY", "sample-private-value")
    assert main(["init", "--backend", backend, "--model", "vision-model", "--base-url", "https://gateway.example/v1"]) == 0
    path = tmp_path / "vigil.json"
    payload = json.loads(path.read_text())
    assert payload["model"] == "vision-model" and payload["api_key"] == ""
    assert "sample-private-value" not in path.read_text()
    config = resolved()
    assert config.backend == backend and config.model == "vision-model"
    assert config.api_key == "sample-private-value"
    assert config.base_url.startswith("https://gateway.example/v1")


def test_init_rejects_credential_url_before_creating_file(tmp_path, capsys):
    key = "sk-" + "synthetic0123456789" * 2
    with pytest.raises(SystemExit) as error:
        main(["init", "--model", "vision", "--base-url", "https://gateway.example/v1?key=" + key])
    assert error.value.code == 2 and not (tmp_path / "vigil.json").exists()
    assert key not in capsys.readouterr().err


def test_catalog_reads_executable_scene_platforms_without_loading_model_config(tmp_path, capsys):
    (tmp_path / "vigil.json").write_text("invalid model configuration")
    assert main(["catalog", "--json"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["episode_count"] == 1000
    assert catalog["platform_episodes"] == {"ithor": 258, "procthor": 742}
    assert catalog["scene_references"] == {"ithor": 67, "procthor": 456}
    assert len(catalog["families"]) == 8
    assert all(family["episodes"] == 125 and family["example"]["instruction"] for family in catalog["families"])


def test_catalog_honors_selection_and_rejects_missing_executable_data(tmp_path, capsys):
    assert main(["catalog", "--task-family", "SI", "--max-episodes", "3", "--json"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog["episode_count"] == 3 and len(catalog["families"]) == 1
    assert catalog["families"][0]["code"] == "SI"
    assert catalog["families"][0]["step_budgets"] == [35]
    with pytest.raises(SystemExit) as error:
        main(["catalog", "--episode-root", str(tmp_path / "missing")])
    assert error.value.code == 2
    assert "Could not resolve episode path" in capsys.readouterr().err


def test_priority_cli_then_file_then_environment(tmp_path, monkeypatch):
    settings(tmp_path, temperature=0.4, api_key="file-test-key")
    monkeypatch.setenv("VIGIL_MODEL_NAME", "environment-model")
    monkeypatch.setenv("VIGIL_TEMPERATURE", "0.8")
    monkeypatch.setenv("VIGIL_API_KEY", "environment-test-key")
    monkeypatch.setenv("VIGIL_MAX_TOKENS", "1234")
    cfg = resolved("--temperature", "0.6")
    assert (cfg.model, cfg.temperature, cfg.max_tokens) == ("file-model", 0.6, 1234)
    assert cfg.api_key == "file-test-key"
    assert resolved("--model", "cli-model").model == "cli-model"


def test_empty_file_key_uses_environment_and_explicit_empty_key_disables_it(tmp_path, monkeypatch):
    settings(tmp_path, api_key="")
    monkeypatch.setenv("VIGIL_API_KEY", "environment-test-key")
    assert resolved().api_key == "environment-test-key"
    assert resolved("--api-key", "").api_key == ""


def test_no_config_ignores_malformed_default_file(tmp_path, monkeypatch):
    (tmp_path / "vigil.json").write_text("not JSON")
    monkeypatch.setenv("VIGIL_MODEL_NAME", "env-model")
    monkeypatch.setenv("VIGIL_MODEL_BASE_URL", "http://localhost:9000")
    assert resolved("--no-config").model == "env-model"


@pytest.mark.parametrize("content,expected", [
    ('{"model":}', "line 1"),
    ('[]', "JSON object"),
    ('{"max_token":12}', "Unknown setting"),
    ('{"temperature":"high"}', "number or null"),
    ('{"max_tokens":true}', "integer"),
    ('{"supports_json_mode":2}', "true or false"),
    ('{"api_key":123456}', "api_key must be a string"),
])
def test_invalid_config_has_clear_error_without_echoing_values(tmp_path, capsys, content, expected):
    (tmp_path / "vigil.json").write_text(content)
    with pytest.raises(SystemExit) as error:
        main(["smoke", "--dry-run"])
    assert error.value.code == 2
    message = capsys.readouterr().err
    assert expected in message
    assert "Traceback" not in message and "123456" not in message


def test_explicit_missing_config_is_not_silently_ignored():
    with pytest.raises(ValueError, match="Configuration file not found"):
        resolved("--config", "missing.json")


@pytest.mark.parametrize("backend", ["openai", "anthropic", "gemini"])
def test_native_provider_config_does_not_inherit_old_endpoint(tmp_path, monkeypatch, backend):
    assert main(["init", "--backend", backend]) == 0
    path = tmp_path / "vigil.json"
    payload = json.loads(path.read_text())
    payload["model"] = "provider-model"
    path.write_text(json.dumps(payload))
    monkeypatch.setenv("VIGIL_MODEL_BASE_URL", "http://old-provider.invalid/v1")
    monkeypatch.setenv("VIGIL_MODEL_BASE_URLS", "http://old-provider.invalid/v1")
    cfg = resolved()
    assert "old-provider" not in cfg.base_url
    assert not any("old-provider" in url for url in cfg.base_urls)


@pytest.mark.parametrize("url,expected", [
    ("http://localhost:8000", "http://localhost:8000/v1/chat/completions"),
    ("http://localhost:8000/v1/", "http://localhost:8000/v1/chat/completions"),
    ("https://example.com/v1?route=fast", "https://example.com/v1/chat/completions?route=fast"),
    ("https://example.com/custom/chat", "https://example.com/custom/chat"),
])
def test_endpoint_accepts_common_base_urls(tmp_path, url, expected):
    settings(tmp_path, base_url=url)
    cfg = resolved()
    assert cfg.base_url == expected and cfg.base_urls == (expected,)


def test_config_flags_can_precede_or_follow_command(tmp_path):
    path = settings(tmp_path)
    for flags in (["--config", str(path), "smoke"], ["smoke", "--config", str(path)]):
        args = build_parser().parse_args(flags)
        apply_model_config(args)
        assert _model_config_from_args(args).model == "file-model"


@pytest.mark.parametrize("placement", ["before", "after", "both", "default"])
def test_ui_receives_explicit_config_regardless_of_flag_placement(tmp_path, monkeypatch, placement):
    selected = tmp_path / "selected.json"
    calls = []
    monkeypatch.setattr("vigil.web.app.serve", lambda **kwargs: calls.append(kwargs) or 0)
    flags = {"before": ["--config", str(selected), "ui"],
             "after": ["ui", "--config", str(selected)],
             "both": ["--config", "ignored.json", "ui", "--config", str(selected)],
             "default": ["ui"]}[placement]
    assert main([*flags, "--no-open"]) == 0
    assert calls[0]["config"] == (Path("vigil.json") if placement == "default" else selected)


def test_ui_does_not_silently_ignore_no_config(monkeypatch, capsys):
    monkeypatch.setattr("vigil.web.app.serve", lambda **_: pytest.fail("UI must not load ignored settings"))
    with pytest.raises(SystemExit) as error:
        main(["--no-config", "ui"])
    assert error.value.code == 2
    assert "vigil ui --config PATH" in capsys.readouterr().err


def test_init_next_steps_preserve_custom_config_path(tmp_path, capsys):
    import shlex
    path = tmp_path / "model settings.json"
    assert main(["init", str(path), "--model", "vision"]) == 0
    command = capsys.readouterr().out.split("Inspect: ", 1)[1].strip()
    args = build_parser().parse_args(shlex.split(command)[1:])
    assert args.config == path


def test_run_alias_uses_the_same_runner_and_dry_run_selection(tmp_path):
    parser = build_parser()
    assert parser.parse_args(["run"]).func is parser.parse_args(["run-pack"]).func
    out = tmp_path / "out"
    assert main(["run", "--dry-run", "--max-episodes", "1", "--out-dir", str(out)]) == 0
    assert json.loads(next(out.glob("*.json")).read_text())["summary"]["episode_count"] == 1


def test_subprocess_uses_selected_file_and_never_reloads_default(tmp_path, monkeypatch):
    episode_root = tmp_path / "episodes"
    _write_episode(episode_root, "sample")
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"pack_id": "mini", "episodes": [{"path": "episodes/sample/episode.json"}]}))
    selected = tmp_path / "selected.json"
    selected.write_text(json.dumps({"backend": "anthropic", "model": "selected-model", "api_key": "test-file-key", "temperature": None}))
    settings(tmp_path, model="wrong-default-model")
    out = tmp_path / "out"

    def launch(cmd, **kwargs):
        args = build_parser().parse_args(cmd[3:])
        assert Path(args.episode) == episode_root / "sample/episode.json"
        apply_model_config(args)
        assert "test-file-key" not in repr(cmd)
        with monkeypatch.context() as child:
            for name in ("VIGIL_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
                if name in kwargs["env"]:
                    child.setenv(name, kwargs["env"][name])
                else:
                    child.delenv(name, raising=False)
            cfg = _model_config_from_args(args)
        assert args.no_config
        assert (cfg.backend, cfg.model, cfg.api_key, cfg.temperature) == ("anthropic", "selected-model", "test-file-key", None)
        _write_finished_trace(out, "sample")
        return 0

    monkeypatch.setattr("vigil.eval.batch.run_episode_process", launch)
    assert main(["run", "--config", str(selected), "--pack-file", str(pack), "--episode-root", str(episode_root), "--out-dir", str(out)]) == 0
    assert "test-file-key" not in (out / "run_config.json").read_text()
    assert "test-file-key" not in (out / "model_config.json").read_text()


def test_isolated_workers_distribute_first_requests_across_replica_pool(tmp_path, monkeypatch):
    import subprocess
    import sys
    episode_root = tmp_path / "episodes"
    ids = [f"sample_{index}" for index in range(4)]
    for episode_id in ids:
        _write_episode(episode_root, episode_id)
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"pack_id": "mini", "episodes": [{"path": f"episodes/{i}/episode.json"} for i in ids]}))
    monkeypatch.setenv("VIGIL_MODEL_BASE_URLS", "http://replica-a.example/v1,http://replica-b.example/v1")
    monkeypatch.setenv("VIGIL_MODEL_NAME", "same-model")
    out = tmp_path / "out"
    first_urls = []
    def launch(cmd, **kwargs):
        # A real fresh Python interpreter reproduces the per-process counter reset.
        script = "from vigil.agent.backends import ModelBackendConfig, OpenAICompatibleClient; print(OpenAICompatibleClient(ModelBackendConfig.from_env())._next_base_url())"
        env = {**kwargs["env"], "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True)
        first_urls.append(result.stdout.strip())
        args = build_parser().parse_args(cmd[3:])
        episode_id = json.loads(Path(args.episode).read_text())["episode_id"]
        _write_finished_trace(out, episode_id)
        return 0
    monkeypatch.setattr("vigil.eval.batch.run_episode_process", launch)
    assert main(["run", "--no-config", "--pack-file", str(pack), "--episode-root", str(episode_root),
                 "--out-dir", str(out)]) == 0
    assert first_urls == ["http://replica-a.example/v1/chat/completions", "http://replica-b.example/v1/chat/completions"] * 2
    assert json.loads((out / "model_config.json").read_text())["base_urls"] == first_urls[:2]
