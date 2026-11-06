from __future__ import annotations

import json
import urllib.request
from typing import Any

from vigil.agent.backends.base import ChatResult, JSONDict, ModelBackendConfig, safe_error_detail
from vigil.agent.backends.transport import request_json
from vigil.agent.backends.images import data_image


class AnthropicClient:
    """Native Anthropic Messages API adapter using only the standard library."""

    def __init__(self, config: ModelBackendConfig):
        self.config = config

    def chat(self, messages: list[JSONDict], *, json_mode: bool = True) -> ChatResult:
        if not self.config.api_key:
            raise ValueError("Anthropic backend requires VIGIL_API_KEY or ANTHROPIC_API_KEY.")
        system, formatted = _messages_to_anthropic(messages)
        body: JSONDict = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "messages": formatted,
            **dict(self.config.extra_body),
        }
        if system:
            body["system"] = system
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        if self.config.top_p is not None:
            body["top_p"] = self.config.top_p
        if self.config.top_k is not None:
            body["top_k"] = self.config.top_k
        endpoint = self.config.base_url.strip() or "https://api.anthropic.com/v1/messages"
        key_header = "x-api-key" if self.config.api_key_header.lower() == "authorization" else self.config.api_key_header
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                key_header: self.config.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )
        payload, attempts = request_json(request, self.config)
        if payload.get("error") or not _valid_response(payload):
            detail = safe_error_detail(json.dumps(payload, ensure_ascii=False), self.config.api_key)
            raise RuntimeError(f"Anthropic request failed: invalid API response: {detail}")
        return ChatResult(
            content=_extract_anthropic_text(payload),
            raw_response=payload,
            usage=_extract_anthropic_usage(payload),
            request_attempts=attempts,
            reasoning=_extract_anthropic_reasoning(payload),
        )


def _valid_response(payload: JSONDict) -> bool:
    content = payload.get("content")
    if not isinstance(content, list):
        return False
    if not content:
        return isinstance(payload.get("stop_reason"), str) and bool(payload["stop_reason"])
    for part in content:
        if not isinstance(part, dict) or not isinstance(part.get("type"), str) or not part["type"]:
            return False
        field = {"text": "text", "thinking": "thinking", "redacted_thinking": "data"}.get(part["type"])
        if field and not isinstance(part.get(field), str):
            return False
    return True


def _messages_to_anthropic(messages: list[JSONDict]) -> tuple[str, list[JSONDict]]:
    system_texts: list[str] = []
    formatted: list[JSONDict] = []
    for message in messages:
        role = str(message.get("role") or "user").lower()
        if role == "system":
            text = _content_text(message.get("content"))
            if text:
                system_texts.append(text)
            continue
        parts = _content_to_anthropic_parts(message.get("content"))
        if parts:
            formatted.append({"role": "assistant" if role == "assistant" else "user", "content": parts})
    return "\n".join(system_texts), formatted


def _content_to_anthropic_parts(content: Any) -> list[JSONDict]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        text = _content_text(content)
        return [{"type": "text", "text": text}] if text else []
    parts: list[JSONDict] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append({"type": "text", "text": item["text"]})
            continue
        if item.get("type") == "image_url":
            url = item.get("image_url", {}).get("url") if isinstance(item.get("image_url"), dict) else None
            image = _data_url_to_anthropic_image(url)
            if image is not None:
                parts.append(image)
    return parts


def _data_url_to_anthropic_image(url: Any) -> JSONDict | None:
    media_type, data = data_image(url)
    return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text")) for item in content if isinstance(item, dict) and item.get("type") == "text")
    return str(content or "")


def _extract_anthropic_text(payload: JSONDict) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return ""
    return "\n".join(str(item.get("text")) for item in content if isinstance(item, dict) and item.get("type") == "text").strip()


def _extract_anthropic_usage(payload: JSONDict) -> JSONDict | None:
    usage = payload.get("usage")
    return dict(usage) if isinstance(usage, dict) else None


def _extract_anthropic_reasoning(payload: JSONDict) -> str | None:
    parts = [item["thinking"] for item in payload["content"]
             if isinstance(item, dict) and item.get("type") == "thinking"
             and isinstance(item.get("thinking"), str)]
    return "\n".join(parts) or None
