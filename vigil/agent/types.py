from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from vigil.actions import ActionCall

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class AgentObservation:
    episode_id: str
    step_index: int
    instruction: str
    text: str = ""
    image_path: str | None = None
    metadata: JSONDict | None = None


@dataclass(frozen=True)
class AgentTurnResult:
    action: ActionCall | None
    raw_response: str
    parse_error: str | None = None
    metadata: JSONDict | None = None


class AgentProtocol(Protocol):
    def act(self, observation: AgentObservation) -> AgentTurnResult:
        ...
