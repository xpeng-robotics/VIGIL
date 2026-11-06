"""Provider wire contracts, native RGB bytes and historical coordinate semantics."""
import base64
import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from vigil.actions import ActionCall
from vigil.agent.backends import AnthropicClient, GeminiClient, ModelBackendConfig, OpenAICompatibleClient
from vigil.agent.backends.openai_compatible import extract_chat_text
from vigil.agent.model import OpenAIModelAgent
from vigil.agent.prompts import build_interact_pixel_system_hint
from vigil.agent.types import AgentObservation
from vigil.cli import build_parser
from vigil.config import _model_config_from_args, _model_config_metadata, apply_model_config
from vigil.coordinates import adapt_pixel_arguments
from test_backends import FakeResponse
from test_thor import _env, _FakeController

ROOT = Path(__file__).resolve().parents[1]
ANSWER = '{"skill_name":"interact_pixel","arguments":{"intent":"ground","x":495,"y":790}}'
PROVIDERS = [
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"content": ANSWER}}]}),
    ("gemini", GeminiClient, {"candidates": [{"content": {"parts": [{"text": ANSWER}]}}]}),
    ("anthropic", AnthropicClient, {"content": [{"type": "text", "text": ANSWER}]}),
]


@pytest.mark.parametrize("backend,client_type,response", PROVIDERS)
@pytest.mark.parametrize("sampling,temperature", [({}, 0.6), ({"temperature": 0.2, "max_tokens": 4096}, 0.2)])
def test_agent_wire_preserves_system_history_and_current_rgb(monkeypatch, backend, client_type, response, sampling, temperature):
    frame = next((ROOT / "vigil/web/demo/frames").rglob("step_000.png"))
    requests = []
    monkeypatch.setattr("urllib.request.urlopen", lambda request, **kw: requests.append(request) or FakeResponse(response))
    config = ModelBackendConfig(base_url="https://gateway.example/api", model="test-model", backend=backend,
                                api_key="test-key", coord_mode="normalized_1000",
                                coord_prompt_mode="explicit", supports_json_mode=False, **sampling)
    agent = OpenAIModelAgent(config)
    obs = AgentObservation(episode_id="e", step_index=0, instruction="Select the cup.", image_path=str(frame),
                           metadata={"history_turns": 20, "image_size": {"width": 640, "height": 480}})
    agent.act(obs)
    turn = agent.act(obs)
    body = json.loads(requests[-1].data)
    prompt = agent._build_system_prompt(obs)
    encoded = base64.b64encode(frame.read_bytes()).decode()
    if backend == "gemini":
        assert body["systemInstruction"] == {"parts": [{"text": prompt}]}
        assert [m["role"] for m in body["contents"]] == ["user", "model", "user"]
        assert body["contents"][-1]["parts"][-1] == {"inlineData": {"mimeType": "image/png", "data": encoded}}
        assert body["generationConfig"] == {"maxOutputTokens": 4096, "temperature": temperature, "topP": 0.9}
        assert requests[-1].get_header("X-goog-api-key") == "test-key"
    elif backend == "anthropic":
        assert body["system"] == prompt
        assert [m["role"] for m in body["messages"]] == ["user", "assistant", "user"]
        assert body["messages"][-1]["content"][-1]["source"] == {"type": "base64", "media_type": "image/png", "data": encoded}
        assert (body["max_tokens"], body["temperature"], body["top_p"]) == (4096, temperature, 0.9)
    else:
        assert body["messages"][0] == {"role": "system", "content": prompt}
        assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "user"]
        assert body["messages"][-1]["content"][-1]["image_url"] == {"url": "data:image/png;base64," + encoded}
        assert (body["max_tokens"], body["temperature"], body["top_p"], body["stream"]) == (4096, temperature, 0.9, False)
    assert json.dumps(body).count(encoded) == 1
    assert "test-key" not in requests[-1].full_url
    evidence = turn.metadata["image_input"]
    assert evidence["sha256"] == hashlib.sha256(frame.read_bytes()).hexdigest()
    assert (evidence["width"], evidence["height"], evidence["transform"]) == (640, 480, "none")
    assert turn.action.arguments == {"intent": "ground", "x": 495, "y": 790}
    assert turn.metadata["request_attempt_count"] == 1


@pytest.mark.parametrize("backend,client_type,response", PROVIDERS)
def test_transport_retries_preserve_payload_and_do_not_correct_model_output(monkeypatch, backend, client_type, response):
    requests = []
    def send(request, **kwargs):
        requests.append(request.data)
        if len(requests) == 1:
            raise HTTPError(request.full_url, 503, "unavailable", {}, None)
        return FakeResponse(response)
    monkeypatch.setattr("urllib.request.urlopen", send)
    client = client_type(ModelBackendConfig(base_url="https://gateway.example/api", model="m", backend=backend,
                                            api_key="test-key", request_max_retries=1, request_retry_delay_s=0))
    result = client.chat([{"role": "user", "content": "instruction"}])
    assert requests[0] == requests[1] and result.request_attempts == 2 and result.content == ANSWER


@pytest.mark.parametrize("client_type", [GeminiClient, AnthropicClient])
@pytest.mark.parametrize("url", ["https://example.com/image.png", "data:image/png,abc", "data:image/png;base64,!"])
def test_native_adapters_fail_instead_of_silently_dropping_images(monkeypatch, client_type, url):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: pytest.fail("Invalid image must fail before request"))
    client = client_type(ModelBackendConfig(base_url="https://gateway.example/api", model="m", api_key="test-key"))
    with pytest.raises(ValueError, match="image"):
        client.chat([{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}}]}])


def test_response_thinking_blocks_cannot_become_an_executed_action():
    response = {"choices": [{"message": {"content": [
        {"type": "thinking", "text": '{"skill_name":"report","arguments":{"status":"success"}}'},
        {"type": "text", "thought": True, "text": "discard this draft"},
        {"type": "text", "text": ANSWER},
    ]}}]}
    assert extract_chat_text(response) == ANSWER


def test_completion_budget_field_and_extra_template_options(monkeypatch):
    captured = []
    monkeypatch.setattr("urllib.request.urlopen", lambda r, **kw: captured.append(json.loads(r.data)) or FakeResponse())
    config = ModelBackendConfig(base_url="https://gateway.example/api", model="m", max_tokens=4096,
                                max_tokens_field="max_completion_tokens", temperature=None, top_p=None,
                                supports_json_mode=False, extra_body={"reasoning_effort": "medium"})
    OpenAICompatibleClient(config).chat([{"role": "user", "content": "instruction"}])
    assert captured == [{"model": "m", "messages": [{"role": "user", "content": "instruction"}],
                         "max_completion_tokens": 4096, "stream": False, "reasoning_effort": "medium"}]


def test_anthropic_gateway_header_and_thinking_remain_separate(monkeypatch):
    captured = []
    monkeypatch.setattr("urllib.request.urlopen", lambda r, **kw: captured.append(r) or FakeResponse({"content": [
        {"type": "thinking", "thinking": "A draft action."}, {"type": "text", "text": ANSWER}]}))
    client = AnthropicClient(ModelBackendConfig(base_url="https://gateway.example/api", model="m",
                                                backend="anthropic", api_key="test-key", api_key_header="API-KEY"))
    response = client.chat([{"role": "user", "content": "instruction"}])
    assert captured[0].get_header("Api-key") == "test-key"
    assert not captured[0].has_header("X-api-key")
    assert response.content == ANSWER and response.reasoning == "A draft action."


def test_alignment_options_resolve_and_enter_resume_metadata(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    values = {"base_url": "https://gateway.example/v1", "model": "m", "image_detail": "high",
              "max_tokens_field": "max_completion_tokens", "request_max_retries": 5, "request_retry_delay_s": 2,
              "protocol_retry_limit": 1, "observation_echo_retry_limit": 2,
              "coord_mode": "normalized_1000", "coord_prompt_mode": "none"}
    path.write_text(json.dumps(values))
    monkeypatch.setenv("VIGIL_MODEL_REQUEST_MAX_RETRIES", "9")
    args = build_parser().parse_args(["smoke", "--config", str(path), "--request-max-retries", "3"])
    apply_model_config(args)
    config = _model_config_from_args(args)
    metadata = _model_config_metadata(config)
    for key in values:
        if key not in {"base_url", "request_max_retries"}:
            assert metadata[key] == values[key]
    assert config.request_max_retries == metadata["request_max_retries"] == 3


@pytest.mark.parametrize("options", [{"coord_mode": "normalized_100"}, {"coord_prompt_mode": "explict"},
                                     {"image_detail": "large"}, {"max_tokens_field": "maxTokens"}])
def test_invalid_alignment_settings_do_not_silently_use_defaults(options):
    with pytest.raises(ValueError):
        ModelBackendConfig(base_url="https://gateway.example/api", model="m", **options)


def test_explicit_pixel_prompt_matches_pixel_execution():
    hint = build_interact_pixel_system_hint("pixel", coord_prompt_mode="explicit")
    assert "normalized_1000" not in hint and "width-1" in hint
    args, adapter = adapt_pixel_arguments({"x": 495, "y": 390, "intent": "ground"}, mode="pixel", width=640, height=480)
    assert (args["x"], args["y"], adapter) == (495, 390, None)
    assert build_interact_pixel_system_hint("normalized_1000", coord_prompt_mode="none") == ""


@pytest.mark.parametrize("xy,expected", [((0, 0), (0, 0)), ((1000, 1000), (639, 479)),
                                         ((495, 790), (316, 378)), ((500, 500), (320, 240)),
                                         ((499.5, 500.5), (320, 240)), ((-10, 1010), (-6, 484))])
def test_historical_coordinate_scaling_and_no_clamping(xy, expected):
    args, adapter = adapt_pixel_arguments({"x": xy[0], "y": xy[1], "intent": "ground"},
                                          mode="normalized_1000", width=640, height=480)
    assert (args["x"], args["y"]) == expected
    assert adapter["output"] == {"x": expected[0], "y": expected[1]}


def test_runtime_keeps_coordinate_evidence_and_target_out_of_action_signature(monkeypatch):
    monkeypatch.setattr("vigil.envs.thor.Controller", object)
    env = _env(_FakeController([])); env.coord_mode = "normalized_1000"
    target = {"objectId": "cup", "objectType": "Cup", "visible": True, "distance": 0.7}
    pixels = []
    monkeypatch.setattr(env, "_resolve_pixel_object", lambda x, y: pixels.append((x, y)) or target)
    result = env.step(ActionCall("interact_pixel", {"intent": "ground", "x": 495, "y": 790}))
    assert result.action_success and pixels == [(316, 378)]
    assert result.env_result.executed_arguments == {"intent": "ground", "x": 316, "y": 378}
    assert result.env_result.resolved_target == {"object_id": "cup", "object_type": "Cup"}
    assert result.env_result.action_adapter["input"] == {"x": 495, "y": 790}
    invalid = env.step(ActionCall("interact_pixel", {"intent": "ground", "x": 1010, "y": -10}))
    assert invalid.env_status == "protocol_error" and len(pixels) == 1
    assert invalid.env_result.action_adapter["output"] == {"x": 645, "y": -5}


def test_drop_never_requires_or_normalizes_a_pixel(monkeypatch):
    monkeypatch.setattr("vigil.envs.thor.Controller", object)
    controller = _FakeController([(True, None)]); env = _env(controller); env.coord_mode = "normalized_1000"
    result = env.step(ActionCall("interact_pixel", {"intent": "drop"}))
    assert result.action_success
    assert controller.actions == [{"action": "DropHandObject", "forceAction": False}]
    assert result.env_result.executed_arguments == {"intent": "drop"}


@pytest.mark.parametrize("backend,client_type,payload", [
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {}, "finish_reason": "stop"}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [None]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"content": 17}}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"content": [None]}}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"content": [{"type": "text", "text": None}]}}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"content": [{"type": []}]}}]}),
    ("gemini", GeminiClient, {"candidates": [{}]}),
    ("gemini", GeminiClient, {"candidates": [None]}),
    ("gemini", GeminiClient, {"candidates": [{"content": {"parts": ["broken"]}}]}),
    ("gemini", GeminiClient, {"candidates": [{"content": {"parts": [{"text": None}]}}]}),
    ("gemini", GeminiClient, {"candidates": [{"content": {"parts": [{"text": "draft", "thought": "false"}]}}]}),
    ("gemini", GeminiClient, {"candidates": [], "promptFeedback": {"blockReason": 17}}),
    ("anthropic", AnthropicClient, {"content": [None]}),
    ("anthropic", AnthropicClient, {"content": [{}]}),
    ("anthropic", AnthropicClient, {"content": [{"type": "text", "text": None}]}),
    ("anthropic", AnthropicClient, {"content": [{"type": "thinking", "thinking": {}}]}),
    ("anthropic", AnthropicClient, {"content": []}),
])
def test_malformed_response_is_infrastructure_failure_not_model_protocol_error(monkeypatch, backend, client_type, payload):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResponse(payload))
    config = ModelBackendConfig(base_url="https://gateway.example/api", model="test-model", backend=backend, api_key="test-key")
    with pytest.raises(RuntimeError, match="invalid API response"):
        client_type(config).chat([{"role": "user", "content": "test"}])
    turn = OpenAIModelAgent(config).act(AgentObservation("example", 0, "Select the cup."))
    assert "model_request_error" in turn.parse_error


@pytest.mark.parametrize("backend,client_type,payload", [
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"content": ""}}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"finish_reason": "length", "message": {"content": None}}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"refusal": "Cannot comply."}}]}),
    ("openai-compatible", OpenAICompatibleClient, {"choices": [{"message": {"tool_calls": [{"type": "function", "function": {"name": "test", "arguments": "{}"}}]}}]}),
    ("gemini", GeminiClient, {"candidates": [{"finishReason": "MAX_TOKENS"}]}),
    ("gemini", GeminiClient, {"candidates": [{"finishReason": "SAFETY"}]}),
    ("gemini", GeminiClient, {"promptFeedback": {"blockReason": "SAFETY"}}),
    ("gemini", GeminiClient, {"candidates": [{"content": {"parts": [{"text": ""}]}}]}),
    ("anthropic", AnthropicClient, {"content": [], "stop_reason": "end_turn"}),
    ("anthropic", AnthropicClient, {"content": [], "stop_reason": "max_tokens"}),
    ("anthropic", AnthropicClient, {"content": [], "stop_reason": "refusal"}),
])
def test_valid_empty_truncated_and_refused_responses_remain_model_outcomes(monkeypatch, backend, client_type, payload):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: FakeResponse(payload))
    config = ModelBackendConfig(base_url="https://gateway.example/api", model="test-model", backend=backend, api_key="test-key")
    assert client_type(config).chat([{"role": "user", "content": "test"}]).raw_response == payload
    turn = OpenAIModelAgent(config).act(AgentObservation("example", 0, "Select the cup."))
    assert "model_request_error" not in (turn.parse_error or "")
