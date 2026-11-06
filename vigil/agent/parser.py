from __future__ import annotations

import json
import re
from typing import Any

from vigil.actions import ActionCall
from vigil.agent.types import AgentTurnResult, JSONDict

_TOP_LEVEL_RESPONSE_KEYS = frozenset(
    {"skill_name", "arguments", "skill_surface", "thought", "cognitive_state", "diagnostics"}
)
_NESTED_PAYLOAD_KEYS = (
    "output",
    "result",
    "data",
    "decision",
    "response",
    "message",
    "assistant_response",
    "tool_call",
    "tool_calls",
    "choices",
)
_PRIMITIVE_ACTION_ALIASES: dict[str, tuple[str, JSONDict]] = {
    "move_forward": ("navigate", {"mode": "forward", "magnitude": 1}),
    "move_backward": ("navigate", {"mode": "backward", "magnitude": 1}),
    "turn_left": ("navigate", {"mode": "turn_left", "magnitude": 90}),
    "turn_right": ("navigate", {"mode": "turn_right", "magnitude": 90}),
    "look_up": ("look", {"direction": "up", "magnitude": 30}),
    "look_down": ("look", {"direction": "down", "magnitude": 30}),
}


def strip_thinking_tags(text: str) -> str:
    """Keep final content; unfinished reasoning must never supply an action.

    Prefer the server's native reasoning channel. This is a boundary guard for
    text-only gateways, including templates that prefill the opening think token.
    Complete JSON values are skipped so quoted tag literals remain untouched.
    """
    tag = re.compile(r"</?(think|thinking)\s*>", re.IGNORECASE)
    if not tag.search(text):
        return text.strip()
    decoder = json.JSONDecoder()
    visible: list[str] = []
    opened: list[str] = []
    index = 0
    while index < len(text):
        if text[index] in "{[":
            try:
                _, end = decoder.raw_decode(text, index)
            except json.JSONDecodeError:
                pass
            else:
                if not opened:
                    visible.append(text[index:end])
                index = end
                continue
        match = tag.match(text, index)
        if match:
            name = match.group(1).lower()
            if match.group().startswith("</"):
                if opened:
                    if opened.pop() != name:
                        return ""  # Mismatched boundaries do not establish a final answer.
                else:
                    visible.clear()  # The opening token may have been in the template.
            else:
                opened.append(name)
            index = match.end()
            continue
        if not opened:
            visible.append(text[index])
        index += 1
    return "" if opened else "".join(visible).strip()


def repair_json_like_text(text: str) -> JSONDict | None:
    candidate = text.strip()
    if not candidate:
        return None
    candidate = candidate.replace("\u201c", '"').replace("\u201d", '"')
    candidate = candidate.replace("\u2018", "'").replace("\u2019", "'")
    candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_json_dicts_via_raw_decode(text: str) -> list[JSONDict]:
    decoder = json.JSONDecoder()
    found: list[JSONDict] = []
    idx = 0
    length = len(text)
    while idx < length:
        while idx < length and text[idx].isspace():
            idx += 1
        if idx >= length:
            break
        if text[idx] != "{":
            idx += 1
            continue
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx += 1
            continue
        if isinstance(obj, dict):
            found.append(obj)
        idx = end
    return found


def extract_json_block(text: str, *, allow_repair: bool = False) -> JSONDict:
    text = strip_thinking_tags(text.strip())
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if not block:
                continue
            if block.lower().startswith("json"):
                block = block[4:].strip()
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                if allow_repair:
                    repaired = repair_json_like_text(block)
                    if repaired is not None:
                        return repaired
                continue
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if allow_repair:
            repaired = repair_json_like_text(text)
            if repaired is not None:
                return repaired
    decoded = _extract_json_dicts_via_raw_decode(text)
    if decoded:
        with_skill = [d for d in decoded if str(d.get("skill_name") or "").strip()]
        chosen = with_skill[-1] if with_skill else decoded[-1]
        return dict(chosen)
    raise ValueError("Model output did not contain a valid JSON object.")


def promote_nested_agent_payload(payload: JSONDict) -> JSONDict:
    if str(payload.get("skill_name") or "").strip():
        return payload
    nested_candidates: list[JSONDict] = []
    seen_ids: set[int] = set()
    for key in _NESTED_PAYLOAD_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            nested_candidates.append(value)
            seen_ids.add(id(value))
        elif key == "choices" and isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, dict):
                        nested_candidates.append(content)
                        seen_ids.add(id(content))
                    elif isinstance(content, str) and content.strip():
                        try:
                            extracted = extract_json_block(content, allow_repair=True)
                        except ValueError:
                            extracted = None
                        if isinstance(extracted, dict):
                            nested_candidates.append(extracted)
                            seen_ids.add(id(extracted))
    for value in payload.values():
        if isinstance(value, dict) and id(value) not in seen_ids:
            nested_candidates.append(value)
            seen_ids.add(id(value))
    for inner in nested_candidates:
        if not str(inner.get("skill_name") or "").strip():
            continue
        merged = dict(inner)
        for key in ("thought", "cognitive_state", "diagnostics"):
            if key in payload and key not in merged:
                merged[key] = payload[key]
        return merged
    return payload


def extract_agent_payload(payload: str | JSONDict, *, allow_json_repair: bool = True) -> JSONDict:
    data = extract_json_block(payload, allow_repair=allow_json_repair) if isinstance(payload, str) else dict(payload)
    if not isinstance(data, dict):
        raise ValueError("Agent response must decode to one JSON object.")
    return promote_nested_agent_payload(data)


def looks_like_observation_echo(payload: JSONDict) -> bool:
    if str(payload.get("skill_name") or "").strip():
        return False
    keys = set(payload.keys())
    return (
        ({"observation_id", "image_size"}.issubset(keys) or {"frame_id", "image_size"}.issubset(keys))
        or {"error_message", "is_holding"}.issubset(keys)
    )


def coerce_action_alias(skill_name: str, arguments: Any) -> tuple[str, JSONDict, str | None]:
    normalized_name = str(skill_name or "").strip()
    normalized_args = dict(arguments or {}) if isinstance(arguments, dict) else {}
    alias = _PRIMITIVE_ACTION_ALIASES.get(normalized_name)
    if alias is None:
        return normalized_name, normalized_args, None
    canonical_name, alias_arguments = alias
    merged_arguments = dict(alias_arguments)
    merged_arguments.update(normalized_args)
    return canonical_name, merged_arguments, normalized_name


def parse_agent_response(
    payload: str | JSONDict,
    *,
    raw_output: str | None = None,
    reasoning: str | None = None,
    allow_json_repair: bool = True,
) -> AgentTurnResult:
    try:
        data = extract_agent_payload(payload, allow_json_repair=allow_json_repair)
        skill_name = str(data.get("skill_name") or "").strip()
        if not skill_name:
            raise ValueError("Missing skill_name in agent response.")
        arguments = data.get("arguments")
        if not isinstance(arguments, dict):
            raise ValueError("Agent response must include an object-valued `arguments` field.")
        skill_name, arguments, coerced_alias = coerce_action_alias(skill_name, arguments)
        raw_surface = str(data.get("skill_surface") or "action").strip().lower() or "action"
        surface = "action" if raw_surface == "primitive" else raw_surface
        if surface not in {"action", "strategy", "construct"}:
            raise ValueError(f"Unsupported skill_surface: {surface!r}")
        thought = str(reasoning).strip() if reasoning else None
        if not thought and data.get("thought") is not None:
            thought = str(data.get("thought")).strip() or None
        diagnostics: JSONDict = {}
        model_supplied_diagnostics = data.get("diagnostics")
        if isinstance(model_supplied_diagnostics, dict) and model_supplied_diagnostics:
            diagnostics["_model_supplied"] = dict(model_supplied_diagnostics)
        if raw_surface == "primitive":
            diagnostics.setdefault("skill_surface_coerced_from", "primitive")
        if coerced_alias is not None:
            diagnostics.setdefault("skill_name_coerced_from", coerced_alias)
        if isinstance(payload, dict):
            diagnostics.setdefault("unparsed_extra_keys", sorted(key for key in data.keys() if key not in _TOP_LEVEL_RESPONSE_KEYS))
        if thought:
            diagnostics.setdefault("thought", thought)
        if isinstance(data.get("cognitive_state"), dict):
            diagnostics.setdefault("cognitive_state", dict(data["cognitive_state"]))
        if surface != "action":
            diagnostics.setdefault("skill_surface", surface)
        return AgentTurnResult(
            action=ActionCall(skill_name=skill_name, arguments=arguments),
            raw_response=raw_output if raw_output is not None else (payload if isinstance(payload, str) else json.dumps(data, ensure_ascii=False)),
            metadata=diagnostics or None,
        )
    except Exception as exc:  # noqa: BLE001 - parser errors are trace diagnostics.
        return AgentTurnResult(
            action=None,
            raw_response=raw_output if raw_output is not None else (payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)),
            parse_error=str(exc),
        )
