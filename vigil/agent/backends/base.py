from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import quote, quote_plus, urlsplit, urlunsplit

from vigil.security import validate_auth_placement
from vigil.coordinates import coordinate_mode, coordinate_prompt_mode

JSONDict = dict[str, Any]


def safe_error_detail(value: Any, api_key: str | None, *, limit: int = 1000) -> str:
    """Redact provider-echoed credentials before errors reach logs or traces."""
    text = str(value)
    if api_key:
        forms = {api_key, quote(api_key, safe=""), quote_plus(api_key), json.dumps(api_key)[1:-1]}
        for form in sorted(forms, key=len, reverse=True):
            text = text.replace(form, "[REDACTED]")
    return text[:limit]


@dataclass(frozen=True)
class ChatResult:
    content: str
    reasoning: str | None = None
    raw_response: JSONDict | None = None
    usage: JSONDict | None = None
    request_attempts: int = 1


@dataclass(frozen=True)
class ModelBackendConfig:
    base_url: str
    model: str
    base_urls: tuple[str, ...] = ()
    backend: str = "openai-compatible"
    api_key: str | None = field(default=None, repr=False)
    api_key_header: str = "Authorization"
    timeout_s: int = 120
    temperature: float | None = 0.6
    top_p: float | None = 0.9
    top_k: int | None = None
    max_tokens: int = 4096
    max_tokens_field: str = "max_tokens"
    image_detail: str = "default"
    coord_mode: str | None = None
    coord_prompt_mode: str | None = None
    supports_json_mode: bool = True
    extra_body: JSONDict = field(default_factory=dict)
    protocol_retry_limit: int = 0
    observation_echo_retry_limit: int = 0
    request_max_retries: int = field(default_factory=lambda: int(os.getenv("VIGIL_MODEL_REQUEST_MAX_RETRIES", "2")))
    request_retry_delay_s: float = field(default_factory=lambda: float(os.getenv("VIGIL_MODEL_REQUEST_RETRY_DELAY_S", "1")))

    def __post_init__(self) -> None:
        validate_auth_placement((self.base_url, *self.base_urls), self.extra_body)
        coordinate_mode(self.coord_mode)
        coordinate_prompt_mode(self.coord_prompt_mode)
        if self.max_tokens_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("max_tokens_field must be max_tokens or max_completion_tokens.")
        if self.image_detail not in {"default", "auto", "low", "high"}:
            raise ValueError("image_detail must be default, auto, low or high.")
        if self.backend in {"gemini", "anthropic", "claude"} and (
            self.max_tokens_field != "max_tokens" or self.image_detail != "default"
        ):
            raise ValueError("max_tokens_field and image_detail overrides apply only to OpenAI-compatible backends.")
        if type(self.request_max_retries) is not int or not 0 <= self.request_max_retries <= 20:
            raise ValueError("request_max_retries must be an integer between 0 and 20.")
        if not math.isfinite(self.request_retry_delay_s) or self.request_retry_delay_s < 0:
            raise ValueError("request_retry_delay_s must be finite and non-negative.")
        tool_fields = {"tools", "tool_choice", "parallel_tool_calls", "functions", "function_call"}
        if tool_fields.intersection(self.extra_body):
            raise ValueError(
                "Native tool calling is not supported by the text-action client. "
                "Remove tool/function settings from extra_body and return the benchmark "
                "skill_name/arguments JSON in message content."
            )
        reserved = {"model", "messages", "system", "systemInstruction", "contents",
                    "max_tokens", "max_completion_tokens", "temperature", "top_p",
                    "top_k", "response_format", "stream"}
        conflicts = reserved.intersection(self.extra_body)
        if conflicts:
            raise ValueError(f"extra_body cannot override benchmark request fields: {', '.join(sorted(conflicts))}. Use the dedicated model settings.")
        generation = self.extra_body.get("generationConfig", {})
        if not isinstance(generation, dict):
            raise ValueError("extra_body.generationConfig must be a JSON object.")
        conflicts = {"maxOutputTokens", "temperature", "topP", "topK", "responseMimeType"}.intersection(generation)
        if conflicts:
            raise ValueError(f"extra_body.generationConfig cannot override configured generation fields: {', '.join(sorted(conflicts))}.")
        if self.timeout_s <= 0 or self.max_tokens <= 0:
            raise ValueError("timeout_s and max_tokens must be positive")
        if self.temperature is not None and (not math.isfinite(self.temperature) or self.temperature < 0):
            raise ValueError("temperature must be finite and non-negative, or none")
        if self.top_p is not None and (not math.isfinite(self.top_p) or not 0 <= self.top_p <= 1):
            raise ValueError("top_p must be between 0 and 1, or none")
        if self.top_k is not None and self.top_k <= 0:
            raise ValueError("top_k must be positive, or none")
        if not 0 <= self.protocol_retry_limit <= 4:
            raise ValueError("protocol_retry_limit must be between 0 and 4")
        if not 0 <= self.observation_echo_retry_limit <= 8:
            raise ValueError("observation_echo_retry_limit must be between 0 and 8")

    @classmethod
    def from_env(cls, **overrides: Any) -> "ModelBackendConfig":
        """Resolve each field independently: explicit value, environment, default."""
        def value(name: str, fallback: Any) -> Any:
            return overrides[name] if name in overrides else fallback()

        backend = value("backend", lambda: os.getenv("VIGIL_BACKEND", "openai-compatible").strip() or "openai-compatible")
        backend_key = backend.replace("_", "-").lower()
        if backend_key not in {"openai", "openai-compatible", "vllm", "gemini", "anthropic", "claude"}:
            raise ValueError(f"Unsupported model backend: {backend!r}.")
        base_urls = () if "base_url" in overrides else _env_url_tuple("VIGIL_MODEL_BASE_URLS")
        base_url = value("base_url", lambda: os.getenv("VIGIL_MODEL_BASE_URL", "").strip() or (base_urls[0] if base_urls else ""))
        if backend_key == "openai" and not base_url:
            base_url = "https://api.openai.com/v1/chat/completions"
        if backend_key in {"openai", "openai-compatible", "vllm"}:
            base_url = _chat_completions_url(base_url) if base_url else ""
            base_urls = tuple(_chat_completions_url(url) for url in base_urls)
        if base_url and not base_urls:
            base_urls = (base_url,)
        model = value("model", lambda: os.getenv("VIGIL_MODEL_NAME", "").strip())
        if backend_key not in {"gemini", "anthropic", "claude"} and not base_url:
            raise ValueError("Set --base-url or VIGIL_MODEL_BASE_URL for an OpenAI-compatible endpoint.")
        if not model:
            raise ValueError("Set model in vigil.json, --model or VIGIL_MODEL_NAME. Use vigil init to create a configuration file.")
        return cls(
            base_url=base_url,
            base_urls=base_urls,
            model=model,
            backend=backend,
            api_key=value("api_key", lambda: _api_key_from_env(backend_key)),
            api_key_header=value("api_key_header", lambda: os.getenv("VIGIL_API_KEY_HEADER", "Authorization")),
            timeout_s=value("timeout_s", lambda: int(os.getenv("VIGIL_TIMEOUT_S", "120"))),
            temperature=value("temperature", lambda: _env_float("VIGIL_TEMPERATURE", 0.6)),
            top_p=value("top_p", lambda: _env_float("VIGIL_TOP_P", 0.9)),
            top_k=value("top_k", lambda: _env_int_optional("VIGIL_TOP_K")),
            max_tokens=value("max_tokens", lambda: int(os.getenv("VIGIL_MAX_TOKENS", "4096"))),
            max_tokens_field=value("max_tokens_field", lambda: os.getenv("VIGIL_MAX_TOKENS_FIELD", "max_tokens")),
            image_detail=value("image_detail", lambda: os.getenv("VIGIL_IMAGE_DETAIL", "default")),
            coord_mode=value("coord_mode", lambda: os.getenv("VIGIL_COORD_MODE", "").strip() or None),
            coord_prompt_mode=value("coord_prompt_mode", lambda: os.getenv("VIGIL_COORD_PROMPT_MODE", "").strip() or None),
            supports_json_mode=value("supports_json_mode", lambda: _env_bool("VIGIL_SUPPORTS_JSON_MODE", True)),
            extra_body=value("extra_body", lambda: _env_json_object("VIGIL_EXTRA_BODY_JSON")),
            protocol_retry_limit=value("protocol_retry_limit", lambda: int(os.getenv("VIGIL_PROTOCOL_RETRY_LIMIT", "0"))),
            observation_echo_retry_limit=value("observation_echo_retry_limit", lambda: int(os.getenv("VIGIL_OBSERVATION_ECHO_RETRY_LIMIT", "0"))),
            request_max_retries=value("request_max_retries", lambda: int(os.getenv("VIGIL_MODEL_REQUEST_MAX_RETRIES", "2"))),
            request_retry_delay_s=value("request_retry_delay_s", lambda: float(os.getenv("VIGIL_MODEL_REQUEST_RETRY_DELAY_S", "1"))),
        )


class ModelClient(Protocol):
    def chat(self, messages: list[JSONDict], *, json_mode: bool = True) -> ChatResult:
        ...


def _chat_completions_url(url: str) -> str:
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("Model endpoint must be an http:// or https:// URL. Set base_url in vigil.json or --base-url.")
    path = parts.path.rstrip("/")
    if not path:
        path = "/v1/chat/completions"
    elif path.endswith("/v1"):
        path += "/chat/completions"
    else:
        return url.strip()
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _api_key_from_env(backend: str) -> str | None:
    if os.getenv("VIGIL_API_KEY"):
        return os.getenv("VIGIL_API_KEY")
    if backend == "gemini":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if backend in {"anthropic", "claude"}:
        return os.getenv("ANTHROPIC_API_KEY")
    return os.getenv("OPENAI_API_KEY")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_float(name: str, default: float | None) -> float | None:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"none", "null"}:
        return None
    return float(raw)


def _env_int_optional(name: str) -> int | None:
    raw = os.getenv(name, "").strip().lower()
    if not raw or raw in {"none", "null"}:
        return None
    return int(raw)


def _env_json_object(name: str) -> JSONDict:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must decode to a JSON object.")
    return payload


def _env_url_tuple(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return ()
    urls = tuple(item.strip() for item in raw.split(",") if item.strip())
    return urls
