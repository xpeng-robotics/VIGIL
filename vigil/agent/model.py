from __future__ import annotations

import hashlib
import json
from typing import Any
from vigil.agent.types import AgentObservation, AgentTurnResult
from vigil.agent.parser import extract_agent_payload, looks_like_observation_echo, parse_agent_response
from vigil.agent.prompts import build_agent_observation_text, build_agent_system_prompt, build_interact_pixel_system_hint
from vigil.agent.backends import ModelBackendConfig, build_multimodal_user_message, create_model_client
from vigil.agent.profiles import AgentProfile, get_profile
from vigil.agent.backends.images import image_evidence

JSONDict = dict[str, Any]
_OMITTED_INVALID_RESPONSE = "[invalid or truncated response omitted]"
_HISTORY_PAYLOAD_KEYS = (
    "skill_name",
    "arguments",
    "skill_surface",
    "thought",
    "cognitive_state",
)


def _canonical_payload_text(payload: JSONDict) -> str:
    """Serialize only the parsed protocol payload for retry/history prompts."""
    safe_payload = {key: payload[key] for key in _HISTORY_PAYLOAD_KEYS if key in payload}
    return json.dumps(safe_payload, ensure_ascii=False, separators=(",", ":"))


class OpenAIModelAgent:
    def __init__(self, config: ModelBackendConfig, *, profile: AgentProfile | str | None = None):
        self.config = config
        self.coord_mode = str(config.coord_mode or "").strip().lower() or None
        self.coord_prompt_mode = str(config.coord_prompt_mode or "").strip().lower() or None
        self.profile = profile if isinstance(profile, AgentProfile) else get_profile(profile)
        self.client = create_model_client(config)
        self._conversation_history: list[JSONDict] = []

    def act(self, observation: AgentObservation) -> AgentTurnResult:
        system_prompt = self._build_system_prompt(observation)
        user_text = build_agent_observation_text(
            observation,
            coord_mode=self.coord_mode,
            include_tail=True,
            multimodal=bool(observation.image_path),
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self._conversation_history_messages(observation))
        messages.append(build_multimodal_user_message(user_text, observation.image_path, image_detail=self.config.image_detail))
        input_image = image_evidence(messages)
        responses = []
        protocol_retries = echo_retries = 0

        def request(current_messages):
            response = self.client.chat(current_messages, json_mode=True)
            responses.append(response)
            return response

        def diagnostics():
            final = responses[-1] if responses else None
            usage = final.usage if final else None
            if len(responses) > 1 and any(r.usage is not None for r in responses):
                usage = {"request_count": len(responses)}
                for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens"):
                    values = [(r.usage or {}).get(key) for r in responses]
                    numeric = [v for v in values if isinstance(v, (int, float))]
                    if numeric:
                        usage[key] = sum(numeric)
            result = {
                "system_prompt_sha256": hashlib.sha256(system_prompt.encode("utf-8")).hexdigest(),
                "system_prompt_chars": len(system_prompt),
                "image_input": input_image,
                "assistant_history_policy": "canonical_payload_v1",
                "request_attempt_count": sum(getattr(r, "request_attempts", 1) for r in responses),
                "raw_response": final.raw_response if final else None,
                "reasoning": final.reasoning if final else None,
                "usage": usage,
                "sanitation": {
                    "protocol_retry_count": protocol_retries,
                    "observation_echo_retry_count": echo_retries,
                    "total_retry_count": protocol_retries + echo_retries,
                    "sanitized": bool(protocol_retries or echo_retries),
                },
            }
            if len(responses) > 1:
                result["model_attempts"] = [
                    {"content": r.content, "reasoning": r.reasoning, "usage": r.usage, "raw_response": r.raw_response}
                    for r in responses
                ]
            return result

        try:
            response = request(messages)
            payload = None
            assistant_history_content = None
            for attempt in range(self.config.protocol_retry_limit + 1):
                try:
                    payload = extract_agent_payload(
                        response.content,
                    )
                    assistant_history_content = _canonical_payload_text(payload)
                    break
                except (ValueError, TypeError):
                    payload = None
                    assistant_history_content = None
                    if attempt == self.config.protocol_retry_limit:
                        break
                    nudge = (
                        "Your previous reply was not valid for the benchmark protocol. Return exactly one top-level JSON object with required keys skill_name and arguments. No prose, no markdown, no code fences."
                        if attempt == 0 else
                        "The benchmark could not parse your last reply. Output one compact JSON object only. Keep thought short if present."
                    )
                    protocol_retries += 1
                    response = request([
                        *messages,
                        {"role": "assistant", "content": _OMITTED_INVALID_RESPONSE},
                        {"role": "user", "content": nudge},
                    ])
            for attempt in range(self.config.observation_echo_retry_limit):
                if payload is None or not looks_like_observation_echo(payload):
                    break
                nudge = (
                    "Your previous reply echoed the observation. Return only one top-level JSON object with required keys skill_name and arguments; cognitive_state is optional."
                    if attempt == 0 else
                    "Do not return the observation or feedback as your answer. Output exactly one top-level skill invocation JSON object and no prose; cognitive_state is optional."
                )
                echo_retries += 1
                response = request([
                    *messages,
                    {"role": "assistant", "content": assistant_history_content or _OMITTED_INVALID_RESPONSE},
                    {"role": "user", "content": nudge},
                ])
                payload = None
                assistant_history_content = None
                try:
                    payload = extract_agent_payload(
                        response.content,
                    )
                    assistant_history_content = _canonical_payload_text(payload)
                except (ValueError, TypeError):
                    break
        except Exception as exc:  # noqa: BLE001 - request failures remain explicit trace errors.
            return AgentTurnResult(
                action=None,
                raw_response=responses[-1].content if responses else "",
                parse_error=f"model_request_error: {type(exc).__name__}: {exc}",
                metadata={**diagnostics(), "exception_type": type(exc).__name__},
            )
        text = response.content
        result = parse_agent_response(text, raw_output=text, reasoning=response.reasoning)
        if result.action is not None and assistant_history_content is not None:
            self._record_conversation_turn(observation, assistant_history_content)
        return AgentTurnResult(
            action=result.action, raw_response=text, parse_error=result.parse_error,
            metadata={**diagnostics(), **(result.metadata or {})},
        )

    def _build_system_prompt(self, observation: AgentObservation) -> str:
        coord_hint = build_interact_pixel_system_hint(self.coord_mode, coord_prompt_mode=self.coord_prompt_mode)
        return build_agent_system_prompt(
            task_instruction=observation.instruction,
            profile=self.profile,
            grounding_rules=[coord_hint] if coord_hint.strip() else [],
        )

    def _conversation_history_turn_limit(self, observation: AgentObservation) -> int:
        metadata = dict(observation.metadata or {})
        raw = metadata.get("history_turns", 0)
        try:
            return max(0, min(64, int(raw)))
        except (TypeError, ValueError):
            return 0

    def _conversation_history_messages(self, observation: AgentObservation) -> list[JSONDict]:
        turn_limit = self._conversation_history_turn_limit(observation)
        if turn_limit <= 0:
            return []
        return list(self._conversation_history[-(turn_limit * 2) :])

    def _record_conversation_turn(self, observation: AgentObservation, assistant_content: str) -> None:
        turn_limit = self._conversation_history_turn_limit(observation)
        if turn_limit <= 0:
            return
        normalized_assistant = str(assistant_content or "").strip()
        if not normalized_assistant:
            return
        user_content = build_agent_observation_text(
            observation,
            coord_mode=self.coord_mode,
            include_tail=False,
            multimodal=False,
        ).strip()
        if not user_content:
            return
        self._conversation_history.extend(
            [
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": normalized_assistant},
            ]
        )
        self._conversation_history = self._conversation_history[-(turn_limit * 2) :]
