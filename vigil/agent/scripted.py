from __future__ import annotations

import json
from pathlib import Path
from vigil.actions import ActionCall
from vigil.agent.types import AgentObservation, AgentTurnResult


class ScriptedAgent:
    def __init__(self, actions: list[ActionCall]):
        self.actions = list(actions)
        self.index = 0

    @classmethod
    def from_json(cls, raw: str) -> "ScriptedAgent":
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("Scripted actions must be a JSON list.")
        return cls([ActionCall.from_dict(item) for item in payload])

    def act(self, observation: AgentObservation) -> AgentTurnResult:
        if self.index < len(self.actions):
            action = self.actions[self.index]
            self.index += 1
        else:
            action = ActionCall("Stop", {})
        return AgentTurnResult(action=action, raw_response=json.dumps(action.to_dict()))


def load_scripted_agent(script_actions: str | None, script_file: str | Path | None) -> ScriptedAgent | None:
    if script_file:
        return ScriptedAgent.from_json(Path(script_file).read_text(encoding="utf-8"))
    if script_actions:
        return ScriptedAgent.from_json(script_actions)
    return None
