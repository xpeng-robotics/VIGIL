from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from vigil.agent.backends.base import ChatResult, JSONDict, ModelBackendConfig, safe_error_detail
from vigil.agent.backends.transport import request_json
from vigil.agent.backends.images import data_image


class GeminiClient:
    """Native Gemini generateContent adapter using only the standard library."""

    def __init__(self, config: ModelBackendConfig):
        self.config = config

    def chat(self, messages: list[JSONDict], *, json_mode: bool = True) -> ChatResult:
        if not self.config.api_key:
            raise ValueError("Gemini backend requires VIGIL_API_KEY or GEMINI_API_KEY.")
        system = "\n".join(_content_text(m.get("content")) for m in messages if m.get("role") == "system")
        body: JSONDict = {
            **dict(self.config.extra_body),
            "contents": _messages_to_gemini_contents(messages),
            "generationConfig": {
                **dict(self.config.extra_body.get("generationConfig", {})),
                "maxOutputTokens": self.config.max_tokens,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if self.config.temperature is not None:
            body["generationConfig"]["temperature"] = self.config.temperature
        if self.config.top_p is not None:
            body["generationConfig"]["topP"] = self.config.top_p
        if self.config.top_k is not None:
            body["generationConfig"]["topK"] = self.config.top_k
        if json_mode and self.config.supports_json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        endpoint = self.config.base_url.strip() or _default_gemini_endpoint(self.config.model)
        headers = {"Content-Type": "application/json"}
        header = "x-goog-api-key" if self.config.api_key_header.lower() == "authorization" else self.config.api_key_header
        headers[header] = self.config.api_key
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        payload, attempts = request_json(request, self.config)
        if payload.get("error") or not _valid_response(payload):
            detail = safe_error_detail(json.dumps(payload, ensure_ascii=False), self.config.api_key)
            raise RuntimeError(f"Gemini request failed: invalid API response: {detail}")
        return ChatResult(
            content=_extract_gemini_text(payload),
            reasoning=_extract_gemini_text(payload, thought=True) or None,
            raw_response=payload,
            usage=_extract_gemini_usage(payload),
            request_attempts=attempts,
        )


def _valid_response(payload: JSONDict) -> bool:
    candidates = payload.get("candidates")
    if candidates is None or candidates == []:
        feedback = payload.get("promptFeedback")
        reason = feedback.get("blockReason") if isinstance(feedback, dict) else None
        return isinstance(reason, str) and reason not in {"", "BLOCK_REASON_UNSPECIFIED"}
    if not isinstance(candidates, list) or not isinstance(candidates[0], dict):
        return False
    candidate = candidates[0]
    content = candidate.get("content")
    finished = isinstance(candidate.get("finishReason"), str) and candidate["finishReason"] not in {"", "FINISH_REASON_UNSPECIFIED"}
    if content is None:
        return finished  # Safety/truncation can have no content.
    if not isinstance(content, dict):
        return False
    parts = content.get("parts")
    if parts is None:
        return finished
    return isinstance(parts, list) and all(
        isinstance(part, dict) and bool(part) and not part.get("error")
        and ("text" not in part or isinstance(part["text"], str))
        and ("thought" not in part or type(part["thought"]) is bool)
        for part in parts
    )


def _default_gemini_endpoint(model: str) -> str:
    quoted_model = urllib.parse.quote(model, safe="-_.")
    return f"https://generativelanguage.googleapis.com/v1beta/models/{quoted_model}:generateContent"


def _messages_to_gemini_contents(messages: list[JSONDict]) -> list[JSONDict]:
    contents: list[JSONDict] = []
    for message in messages:
        role = str(message.get("role") or "user")
        if role == "system":
            continue
        parts = _content_to_gemini_parts(message.get("content"))
        if not parts:
            continue
        contents.append({"role": "model" if role == "assistant" else "user", "parts": parts})
    return contents


def _content_to_gemini_parts(content: Any) -> list[JSONDict]:
    if isinstance(content, str):
        return [{"text": content}]
    if not isinstance(content, list):
        text = _content_text(content)
        return [{"text": text}] if text else []
    parts: list[JSONDict] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            parts.append({"text": item["text"]})
            continue
        if item.get("type") == "image_url":
            url = item.get("image_url", {}).get("url") if isinstance(item.get("image_url"), dict) else None
            inline = _data_url_to_inline_data(url)
            if inline is not None:
                parts.append({"inlineData": inline})
    return parts


def _data_url_to_inline_data(url: Any) -> JSONDict | None:
    mime_type, data = data_image(url)
    return {"mimeType": mime_type, "data": data}


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text")) for item in content if isinstance(item, dict) and item.get("type") == "text")
    return str(content or "")


def _extract_gemini_text(payload: JSONDict, *, thought: bool = False) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    content = candidates[0].get("content") if isinstance(candidates[0], dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return ""
    return "\n".join(part["text"] for part in parts if isinstance(part, dict)
                     and isinstance(part.get("text"), str) and bool(part.get("thought")) == thought).strip()


def _extract_gemini_usage(payload: JSONDict) -> JSONDict | None:
    usage = payload.get("usageMetadata")
    if not isinstance(usage, dict):
        return None
    return dict(usage)
