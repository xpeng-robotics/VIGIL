from __future__ import annotations

import base64
import json
import mimetypes
import threading
import urllib.request
from pathlib import Path
from typing import Any

from vigil.agent.backends.base import ChatResult, JSONDict, ModelBackendConfig, safe_error_detail
from vigil.agent.backends.transport import request_json


class OpenAICompatibleClient:
    """Small OpenAI-compatible chat client used by vLLM and public gateways."""

    _endpoint_lock = threading.Lock()
    _endpoint_index = 0

    def __init__(self, config: ModelBackendConfig):
        self.config = config
        self.base_urls = tuple(config.base_urls or ((config.base_url,) if config.base_url else ()))

    def chat(self, messages: list[JSONDict], *, json_mode: bool = True) -> ChatResult:
        body: JSONDict = {
            "model": self.config.model,
            "messages": messages,
            self.config.max_tokens_field: self.config.max_tokens,
            "stream": False,
            **dict(self.config.extra_body),
        }
        if self.config.temperature is not None:
            body["temperature"] = self.config.temperature
        if self.config.top_p is not None:
            body["top_p"] = self.config.top_p
        if self.config.top_k is not None:
            body["top_k"] = self.config.top_k
        if json_mode and self.config.supports_json_mode:
            body["response_format"] = {"type": "json_object"}

        request = urllib.request.Request(
            self._next_base_url(), data=json.dumps(body).encode("utf-8"),
            headers=self._headers(), method="POST",
        )
        payload, attempts = request_json(request, self.config)
        if payload.get("error") or not _valid_response(payload):
            detail = safe_error_detail(json.dumps(payload, ensure_ascii=False), self.config.api_key)
            raise RuntimeError(f"Model request failed: invalid API response: {detail}")
        return ChatResult(
            content=extract_chat_text(payload),
            reasoning=extract_reasoning_text(payload),
            raw_response=payload,
            usage=extract_usage(payload),
            request_attempts=attempts,
        )

    def _next_base_url(self) -> str:
        if not self.base_urls:
            return self.config.base_url
        if len(self.base_urls) == 1:
            return self.base_urls[0]
        with self._endpoint_lock:
            index = type(self)._endpoint_index
            type(self)._endpoint_index += 1
        return self.base_urls[index % len(self.base_urls)]

    def _headers(self) -> JSONDict:
        headers: JSONDict = {"Content-Type": "application/json"}
        if self.config.api_key:
            if self.config.api_key_header.lower() == "authorization":
                headers["Authorization"] = f"Bearer {self.config.api_key}"
            else:
                headers[self.config.api_key_header] = self.config.api_key
        return headers


def _valid_response(payload: JSONDict) -> bool:
    if "choices" not in payload:
        return isinstance(payload.get("text"), str)  # Legacy text gateways.
    choices = payload["choices"]
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return False
    choice = choices[0]
    if "message" not in choice:
        return isinstance(choice.get("text"), str)
    message = choice["message"]
    if not isinstance(message, dict):
        return False
    content = message.get("content")
    if isinstance(content, str):
        return True  # An empty model answer is still a model response.
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict) or not part:
                return False
            kind = part.get("type", "text")
            if not isinstance(kind, str) or not kind:
                return False
            if kind in {"text", "output_text"} and not isinstance(part.get("text"), str):
                return False
        return True
    if isinstance(content, dict):
        return any(isinstance(content.get(key), str) for key in ("text", "content"))
    if content is not None:
        return False
    # Refusal, truncation and tool-only output must not become transport errors.
    reason = choice.get("finish_reason")
    if isinstance(reason, str) and reason and ("content" in message or reason in {"length", "content_filter"}):
        return True
    if any(isinstance(message.get(key), str) for key in ("refusal", "reasoning_content", "reasoning", "thinking")):
        return True
    calls = message.get("tool_calls")
    if isinstance(calls, list) and calls and all(isinstance(call, dict) and call for call in calls):
        return True
    return isinstance(message.get("function_call"), dict) and bool(message["function_call"])


def image_file_to_data_url(path: str | Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    with open(path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_multimodal_user_message(text: str, image_path: str | Path | None = None, *, image_detail: str = "default") -> JSONDict:
    if image_path:
        image = {"url": image_file_to_data_url(image_path)}
        if image_detail != "default":
            image["detail"] = image_detail
        return {
            "role": "user",
            "content": [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": image},
            ],
        }
    return {"role": "user", "content": text}


def extract_chat_text(response: JSONDict) -> str:
    choices = response.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else None
        if isinstance(message, dict):
            # A present chat message owns the final answer, including an empty
            # or truncated answer. Envelope text may contain a draft.
            return _extract_text_from_content(message.get("content"))
        text = first.get("text") if isinstance(first, dict) else None
        if isinstance(text, str):
            return text
    if isinstance(response.get("text"), str):
        return str(response["text"])
    return ""


def extract_reasoning_text(response: JSONDict) -> str | None:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return None
    empty_reasoning = False
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = message.get(key)
        if isinstance(value, str):
            if value.strip():
                return value.strip()
            empty_reasoning = True
    reasoning = _extract_reasoning_from_content(message.get("content"))
    return reasoning if reasoning is not None else ("" if empty_reasoning else None)


def extract_usage(response: JSONDict) -> JSONDict | None:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    return {key: value for key, value in usage.items() if isinstance(key, str)}


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type", "text") in {"text", "output_text"} and item.get("thought") is not True and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    if isinstance(content, dict):
        for key in ("text", "content"):
            value = content.get(key)
            if isinstance(value, str):
                return value
    return ""


def _extract_reasoning_from_content(content: Any) -> str | None:
    if not isinstance(content, list):
        return None
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        part_type = str(item.get("type") or "").lower()
        if (part_type in {"reasoning", "thinking", "reasoning_content"} or item.get("thought") is True) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    joined = "\n".join(part.strip() for part in parts if part.strip())
    return joined if parts else None
