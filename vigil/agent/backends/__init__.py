from vigil.agent.backends.anthropic import AnthropicClient
from vigil.agent.backends.base import ChatResult, ModelBackendConfig, ModelClient
from vigil.agent.backends.factory import create_model_client
from vigil.agent.backends.gemini import GeminiClient
from vigil.agent.backends.openai_compatible import (
    OpenAICompatibleClient,
    build_multimodal_user_message,
    extract_chat_text,
    image_file_to_data_url,
)

__all__ = [
    "AnthropicClient",
    "ChatResult",
    "GeminiClient",
    "ModelBackendConfig",
    "ModelClient",
    "OpenAICompatibleClient",
    "build_multimodal_user_message",
    "create_model_client",
    "extract_chat_text",
    "image_file_to_data_url",
]
