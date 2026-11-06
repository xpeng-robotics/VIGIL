import json
from urllib.error import HTTPError, URLError

import pytest

from vigil.agent.backends import AnthropicClient, GeminiClient, ModelBackendConfig, OpenAICompatibleClient, build_multimodal_user_message, create_model_client


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {
            "choices": [{"message": {"content": '{"skill_name":"Stop","arguments":{}}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_openai_compatible_client_request_shape(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers.get("Authorization")
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        ModelBackendConfig(
            base_url="http://localhost:8000/v1/chat/completions",
            model="tiny-vlm",
            api_key="secret",
            timeout_s=7,
            temperature=0.2,
            top_p=0.9,
            top_k=20,
            max_tokens=512,
            extra_body={"chat_template_kwargs": {"enable_thinking": True}},
        )
    )

    result = client.chat([{"role": "user", "content": "hello"}], json_mode=True)

    assert captured["url"] == "http://localhost:8000/v1/chat/completions"
    assert captured["timeout"] == 7
    assert captured["authorization"] == "Bearer secret"
    assert captured["body"]["model"] == "tiny-vlm"
    assert captured["body"]["max_tokens"] == 512
    assert captured["body"]["temperature"] == 0.2
    assert captured["body"]["top_p"] == 0.9
    assert captured["body"]["top_k"] == 20
    assert captured["body"]["chat_template_kwargs"] == {"enable_thinking": True}
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert result.content.startswith('{"skill_name"')
    assert result.usage == {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}


def test_openai_compatible_client_skips_response_format_when_json_mode_unsupported(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        ModelBackendConfig(
            base_url="http://localhost:8000/v1/chat/completions",
            model="self-hosted-vlm",
            api_key="secret",
            supports_json_mode=False,
        )
    )

    client.chat([{"role": "user", "content": "hello"}], json_mode=True)

    assert "response_format" not in captured["body"]


def test_openai_compatible_client_round_robins_base_urls(monkeypatch):
    captured = []

    def fake_urlopen(request, timeout):
        captured.append(request.full_url)
        return FakeResponse()

    OpenAICompatibleClient._endpoint_index = 0
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        ModelBackendConfig(
            base_url="http://localhost:8003/v1/chat/completions",
            base_urls=(
                "http://localhost:8003/v1/chat/completions",
                "http://localhost:8004/v1/chat/completions",
            ),
            model="self-hosted-vlm",
        )
    )

    client.chat([{"role": "user", "content": "one"}], json_mode=False)
    client.chat([{"role": "user", "content": "two"}], json_mode=False)
    client.chat([{"role": "user", "content": "three"}], json_mode=False)

    assert captured == [
        "http://localhost:8003/v1/chat/completions",
        "http://localhost:8004/v1/chat/completions",
        "http://localhost:8003/v1/chat/completions",
    ]


def test_openai_compatible_client_retries_transient_http_error(monkeypatch):
    captured = {"calls": 0}

    def fake_urlopen(request, timeout):
        captured["calls"] += 1
        if captured["calls"] == 1:
            raise HTTPError(
                request.full_url,
                503,
                "service unavailable",
                {},
                fp=None,
            )
        return FakeResponse()

    monkeypatch.setenv("VIGIL_MODEL_REQUEST_MAX_RETRIES", "2")
    monkeypatch.setenv("VIGIL_MODEL_REQUEST_RETRY_DELAY_S", "0")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        ModelBackendConfig(
            base_url="http://localhost:8000/v1/chat/completions",
            model="tiny-vlm",
            api_key=None,
            timeout_s=7,
        )
    )

    client.chat([{"role": "user", "content": "hello"}], json_mode=True)

    assert captured["calls"] == 2


def test_openai_compatible_client_raises_after_retry_limit(monkeypatch):
    captured = {"calls": 0}

    def fake_urlopen(request, timeout):
        captured["calls"] += 1
        raise URLError(ConnectionResetError(104, "Connection reset by peer"))

    monkeypatch.setenv("VIGIL_MODEL_REQUEST_MAX_RETRIES", "1")
    monkeypatch.setenv("VIGIL_MODEL_REQUEST_RETRY_DELAY_S", "0")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = OpenAICompatibleClient(
        ModelBackendConfig(
            base_url="http://localhost:8000/v1/chat/completions",
            model="tiny-vlm",
            api_key=None,
            timeout_s=7,
        )
    )

    try:
        client.chat([{"role": "user", "content": "hello"}], json_mode=True)
    except RuntimeError as exc:
        assert "Model request failed" in str(exc)
    else:
        raise AssertionError("Expected model request failure")

    assert captured["calls"] == 2


def test_anthropic_client_request_shape(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["api_key"] = request.headers.get("x-api-key") or request.headers.get("X-api-key") or request.headers.get("X-Api-Key")
        captured["version"] = request.headers.get("anthropic-version") or request.headers.get("Anthropic-version") or request.headers.get("Anthropic-Version")
        return FakeResponse({"content": [{"type": "text", "text": "{}"}], "usage": {"input_tokens": 1, "output_tokens": 1}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = AnthropicClient(ModelBackendConfig(base_url="", model="claude-sonnet-4", backend="anthropic", api_key="secret"))

    result = client.chat([{"role": "system", "content": "system"}, {"role": "user", "content": "hello"}], json_mode=True)

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["api_key"] == "secret"
    assert captured["version"] == "2023-06-01"
    assert captured["body"]["model"] == "claude-sonnet-4"
    assert captured["body"]["messages"] == [{"role": "user", "content": [{"type": "text", "text": "hello"}]}]
    assert captured["body"]["system"] == "system"
    assert result.content == "{}"


def test_factory_accepts_public_backend_aliases():
    assert create_model_client(ModelBackendConfig(base_url="http://x", model="m", backend="vllm")).__class__.__name__ == "OpenAICompatibleClient"
    assert create_model_client(ModelBackendConfig(base_url="", model="m", backend="claude", api_key="k")).__class__.__name__ == "AnthropicClient"


def test_gemini_gateway_uses_configured_header_and_preserves_image(monkeypatch):
    def fake_urlopen(request, timeout):
        assert request.full_url == "https://gateway.example/gemini:generateContent"
        assert request.get_header("Api-key") == "test-key"
        assert "test-key" not in request.full_url
        body = json.loads(request.data)
        parts = body["contents"][0]["parts"]
        assert parts[1]["inlineData"] == {"mimeType": "image/png", "data": "aW1hZ2U="}
        assert body["generationConfig"]["maxOutputTokens"] == 4096
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "{}"}]}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = GeminiClient(ModelBackendConfig(
        base_url="https://gateway.example/gemini:generateContent", model="gemini-test",
        api_key="test-key", api_key_header="API-KEY", max_tokens=4096,
    ))
    result = client.chat([{"role": "user", "content": [
        {"type": "text", "text": "Describe this image."},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}},
    ]}])
    assert result.content == "{}"


@pytest.mark.parametrize("client_type", [OpenAICompatibleClient, GeminiClient])
@pytest.mark.parametrize("payload", [
    {"code": 61200000, "data": "API key test-key is invalid", "desc": "Authentication failed"},
    {"error": {"message": "test-key denied"}},
    {"unexpected": "response", "promptFeedback": None},
])
def test_http_200_api_errors_are_request_failures_not_model_answers(monkeypatch, client_type, payload):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse(payload))
    client = client_type(ModelBackendConfig(base_url="https://gateway.example/chat", model="m", api_key="test-key"))
    with pytest.raises(RuntimeError, match="invalid API response") as error:
        client.chat([{"role": "user", "content": "hello"}])
    assert "test-key" not in str(error.value)


def test_gemini_safety_block_remains_a_model_response(monkeypatch):
    payload = {"promptFeedback": {"blockReason": "SAFETY"}}
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResponse(payload))
    client = GeminiClient(ModelBackendConfig(base_url="", model="m", api_key="test-key"))
    assert client.chat([{"role": "user", "content": "hello"}]).raw_response == payload


def test_multimodal_message_without_image_stays_text_only():
    assert build_multimodal_user_message("hello", None) == {"role": "user", "content": "hello"}


def test_model_backend_config_reads_generation_flags_from_env(monkeypatch):
    monkeypatch.setenv("VIGIL_BACKEND", "openai-compatible")
    monkeypatch.setenv("VIGIL_MODEL_BASE_URL", "http://localhost:8000/v1/chat/completions")
    monkeypatch.setenv("VIGIL_MODEL_NAME", "m")
    monkeypatch.setenv("VIGIL_MAX_TOKENS", "256")
    monkeypatch.setenv("VIGIL_TEMPERATURE", "1.0")
    monkeypatch.setenv("VIGIL_TOP_P", "0.95")
    monkeypatch.setenv("VIGIL_TOP_K", "20")
    monkeypatch.setenv("VIGIL_EXTRA_BODY_JSON", '{"chat_template_kwargs":{"enable_thinking":true}}')
    monkeypatch.setenv("VIGIL_SUPPORTS_JSON_MODE", "0")

    config = ModelBackendConfig.from_env()

    assert config.max_tokens == 256
    assert config.temperature == 1.0
    assert config.top_p == 0.95
    assert config.top_k == 20
    assert config.extra_body == {"chat_template_kwargs": {"enable_thinking": True}}
    assert config.supports_json_mode is False
