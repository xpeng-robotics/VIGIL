"""Failure injection for batch orchestration, directory scoring and API errors."""
import io
import json
from pathlib import Path
import shutil
import threading
import traceback
from urllib.error import HTTPError, URLError
from urllib.parse import quote

import pytest

from vigil import cli
from vigil.agent.types import AgentObservation
from vigil.agent.backends import AnthropicClient, GeminiClient, ModelBackendConfig, OpenAICompatibleClient
from vigil.eval.offline import evaluate_trace_files
from vigil.eval.runner import OpenAIModelAgent
from test_backends import FakeResponse
from test_cli import _write_episode, _write_finished_trace

DEMO = Path(__file__).resolve().parents[1] / "vigil/web/demo"
CLIENTS = [OpenAICompatibleClient, GeminiClient, AnthropicClient]
TEST_KEY = "test-credential-with+reserved?characters"


@pytest.mark.parametrize("broken", ['{"episode_id":', '{}', '{"episode_id":"failed","steps":null}'])
def test_directory_scoring_never_drops_a_broken_trace(tmp_path, broken):
    traces = tmp_path / "traces"
    traces.mkdir()
    good = next((DEMO / "traces").glob("*fridge*.json"))
    shutil.copyfile(good, traces / "success.json")
    (traces / "failed.json").write_text(broken)
    with pytest.raises(ValueError, match="failed.json"):
        evaluate_trace_files([traces])


@pytest.mark.parametrize("input_name", [".", "traces"])
def test_directory_scoring_requires_all_selected_traces(tmp_path, input_name):
    root = tmp_path / "run"
    shutil.copytree(DEMO, root)
    next((root / "traces").glob("*toaster*.json")).unlink()
    with pytest.raises(ValueError, match="[Mm]issing.*trace|[Tt]race.*missing"):
        evaluate_trace_files([root / input_name])


def test_directory_scoring_uses_the_run_selection(tmp_path):
    root = tmp_path / "run"
    shutil.copytree(DEMO, root)
    status = json.loads((root / "run_status.json").read_text())
    status["episode_ids"] = [episode for episode in status["episode_ids"] if "toaster" in episode]
    (root / "run_status.json").write_text(json.dumps(status))
    for directory in (root, root / "traces", tmp_path):
        aggregate = evaluate_trace_files([directory])
        assert aggregate.episode_count == 1
        assert aggregate.success_rate == 0.0


@pytest.mark.parametrize("state", ["running", "failed", "cancelled", "infrastructure_error"])
def test_parent_directory_cannot_bypass_nested_run_completion(tmp_path, state):
    root = tmp_path / "group/run"
    shutil.copytree(DEMO, root)
    status = json.loads((root / "run_status.json").read_text())
    status["state"] = state
    (root / "run_status.json").write_text(json.dumps(status))
    with pytest.raises(ValueError, match="incomplete"):
        evaluate_trace_files([tmp_path])


def test_nested_run_requires_missing_selected_evidence(tmp_path):
    root = tmp_path / "group/run"
    shutil.copytree(DEMO, root)
    next((root / "traces").glob("*toaster*.json")).unlink()
    with pytest.raises(ValueError, match="Missing selected trace"):
        evaluate_trace_files([tmp_path])


@pytest.mark.parametrize("form", ["parent", "directories", "files"])
def test_rescoring_refuses_known_mixed_experiments_but_allows_matching_shards(tmp_path, form):
    paths = []
    for index, trace in enumerate(sorted((DEMO / "traces").glob("*.json"))):
        run = tmp_path / f"shard-{index}"
        target = run / "traces" / trace.name
        target.parent.mkdir(parents=True)
        shutil.copyfile(trace, target)
        (run / "run_status.json").write_text(json.dumps({"state": "complete", "episode_ids": [trace.stem]}))
        (run / "run_config.json").write_text(json.dumps({"schema_version": 1, "model": {"model": "model-a"}}))
        paths.append(target)
    inputs = {"parent": [tmp_path], "directories": [p.parent for p in paths], "files": paths}[form]
    assert evaluate_trace_files(inputs).episode_count == 2
    config = paths[1].parent.parent / "run_config.json"
    config.write_text(json.dumps({"schema_version": 1, "model": {"model": "model-b"}}))
    with pytest.raises(ValueError, match="different run_config.json experiments"):
        evaluate_trace_files(inputs)


@pytest.mark.parametrize("payload", [[], {}, None])
def test_malformed_experiment_identity_is_not_treated_as_untracked(tmp_path, payload):
    shutil.copytree(DEMO, tmp_path / "run")
    (tmp_path / "run/run_config.json").write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Invalid run_config"):
        evaluate_trace_files([tmp_path])


def test_untracked_run_directory_ignores_its_valid_score_files(tmp_path):
    _write_finished_trace(tmp_path, "sample")
    assert evaluate_trace_files([tmp_path]).episode_count == 1


def test_selected_trace_must_match_its_declared_episode(tmp_path):
    shutil.copytree(DEMO, tmp_path / "run")
    trace = next((tmp_path / "run/traces").glob("*.json"))
    payload = json.loads(trace.read_text())
    payload["episode_id"] = "different-episode"
    trace.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="episode ID"):
        evaluate_trace_files([tmp_path / "run"])


@pytest.mark.parametrize("client_type", CLIENTS)
@pytest.mark.parametrize("failure", ["http", "transport"])
def test_request_errors_redact_keys_even_in_formatted_tracebacks(monkeypatch, client_type, failure):
    def fail(request, **kwargs):
        detail = f"Invalid credential: {TEST_KEY}; URL token: {quote(TEST_KEY, safe='')}"
        if failure == "http":
            raise HTTPError(request.full_url, 401, detail, {}, io.BytesIO(detail.encode()))
        raise URLError(detail)

    monkeypatch.setattr("urllib.request.urlopen", fail)
    monkeypatch.setenv("VIGIL_MODEL_REQUEST_MAX_RETRIES", "0")
    client = client_type(ModelBackendConfig(base_url="https://example.invalid/chat", model="test", api_key=TEST_KEY))
    with pytest.raises(RuntimeError) as error:
        client.chat([{"role": "user", "content": "hello"}])
    rendered = "".join(traceback.format_exception(type(error.value), error.value, error.value.__traceback__))
    assert TEST_KEY not in rendered
    assert quote(TEST_KEY, safe="") not in rendered
    assert "[REDACTED]" in str(error.value)


@pytest.mark.parametrize("payload", [
    {"error": {"message": "test-key denied"}},
    {"code": 401, "message": "test-key denied"},
    {"content": "wrong response shape"},
])
def test_anthropic_gateway_error_is_not_a_model_answer(monkeypatch, payload):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse(payload))
    client = AnthropicClient(ModelBackendConfig(base_url="https://example.invalid/messages", model="test", api_key="test-key"))
    with pytest.raises(RuntimeError, match="invalid API response") as error:
        client.chat([{"role": "user", "content": "hello"}])
    assert "test-key" not in str(error.value)


def test_anthropic_error_reaches_agent_as_infrastructure_failure(monkeypatch):
    payload = {"error": {"message": "test-key denied"}}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse(payload))
    agent = OpenAIModelAgent(ModelBackendConfig(base_url="https://example.invalid/messages", model="test",
                                               backend="anthropic", api_key="test-key"))
    turn = agent.act(AgentObservation("sample", 0, "Find the target."))
    assert "model_request_error" in turn.parse_error
    assert "test-key" not in json.dumps(turn.metadata)
    assert "test-key" not in turn.parse_error


@pytest.mark.parametrize("content,reason", [([], "max_tokens"), ([{"type": "text", "text": "I cannot do that."}], "refusal")])
def test_anthropic_empty_or_refused_model_output_remains_a_response(monkeypatch, content, reason):
    payload = {"content": content, "stop_reason": reason}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse(payload))
    client = AnthropicClient(ModelBackendConfig(base_url="https://example.invalid/messages", model="test", api_key="test-key"))
    assert client.chat([{"role": "user", "content": "hello"}]).raw_response == payload


@pytest.mark.parametrize("failure,exit_code,state", [(RuntimeError, 2, "failed"), (KeyboardInterrupt, 130, "cancelled")])
def test_fatal_worker_stops_siblings_and_marks_run(tmp_path, monkeypatch, failure, exit_code, state):
    episodes = tmp_path / "episodes"
    ids = [f"sample_{i}" for i in range(6)]
    for episode in ids:
        _write_episode(episodes, episode)
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"pack_id": "batch", "episodes": [{"path": f"episodes/{episode}/episode.json"} for episode in ids]}))
    out = tmp_path / "out"
    peer_started = threading.Event()
    cancellation_observed = threading.Event()
    started = []

    def fake_process(cmd, *, cancel_event, **kwargs):
        episode = json.loads(Path(cmd[cmd.index("run-episode") + 1]).read_text())["episode_id"]
        if cancel_event is not None and cancel_event.is_set():
            raise KeyboardInterrupt
        started.append(episode)
        if episode == ids[0]:
            assert peer_started.wait(2)
            raise failure("injected worker failure")
        peer_started.set()
        # Bounded wait makes the old broken implementation fail without hanging.
        if cancel_event is not None and cancel_event.wait(0.8):
            cancellation_observed.set()
            raise KeyboardInterrupt
        _write_finished_trace(out, episode)
        return 0

    monkeypatch.setattr("vigil.eval.batch.run_episode_process", fake_process)
    with pytest.raises(SystemExit) as error:
        cli.main(["--no-config", "run", "--pack-file", str(pack), "--episode-root", str(episodes),
                  "--out-dir", str(out), "--workers", "2", "--script-actions", '[{"skill_name":"report","arguments":{"status":"fail"}}]'])
    assert error.value.code == exit_code
    assert cancellation_observed.is_set()
    assert len(started) < len(ids)
    assert json.loads((out / "run_status.json").read_text())["state"] == state
    assert not (out / "aggregate_score.json").exists()
