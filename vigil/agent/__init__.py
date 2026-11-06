from __future__ import annotations

import json

from vigil.actions import ActionCall
from vigil.agent.parser import parse_agent_response
from vigil.agent.prompts import (
    build_agent_observation_text,
    build_agent_prompt,
    build_agent_system_prompt,
    build_interact_pixel_system_hint,
    get_prompt_policy_metadata,
)
from vigil.agent.types import AgentObservation, AgentProtocol, AgentTurnResult


class StaticAgent:
    """Tiny deterministic agent used for smoke tests and examples."""

    def __init__(self, action: ActionCall | None = None):
        self.action = action or ActionCall(skill_name="Stop", arguments={})

    def act(self, observation: AgentObservation) -> AgentTurnResult:
        return AgentTurnResult(action=self.action, raw_response=json.dumps(self.action.to_dict()))


__all__ = [
    "AgentObservation",
    "AgentProtocol",
    "AgentTurnResult",
    "StaticAgent",
    "build_agent_observation_text",
    "build_agent_prompt",
    "build_agent_system_prompt",
    "build_interact_pixel_system_hint",
    "get_prompt_policy_metadata",
    "parse_agent_response",
]
