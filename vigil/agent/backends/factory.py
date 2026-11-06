from __future__ import annotations

from vigil.agent.backends.anthropic import AnthropicClient
from vigil.agent.backends.base import ModelBackendConfig, ModelClient
from vigil.agent.backends.gemini import GeminiClient
from vigil.agent.backends.openai_compatible import OpenAICompatibleClient


def create_model_client(config: ModelBackendConfig | None = None) -> ModelClient:
    resolved = config or ModelBackendConfig.from_env()
    backend = resolved.backend.strip().replace("_", "-").lower()
    if backend in {"openai", "openai-compatible", "vllm"}:
        return OpenAICompatibleClient(resolved)
    if backend == "gemini":
        return GeminiClient(resolved)
    if backend in {"anthropic", "claude"}:
        return AnthropicClient(resolved)
    raise ValueError(f"Unsupported VIGIL_BACKEND {resolved.backend!r}.")
