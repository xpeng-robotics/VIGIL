from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

JSONDict = dict[str, Any]


@dataclass
class EnvActionResult:
    skill_name: str
    requested_arguments: JSONDict
    executed_arguments: JSONDict
    observation: Any = None
    simulator_success: bool = False
    error_message: str | None = None
    resolved_target: JSONDict | None = None
    target_resolved: bool = False
    action_adapter: JSONDict | None = None
    pre_state: JSONDict = field(default_factory=dict)
    post_state: JSONDict = field(default_factory=dict)
    info: JSONDict = field(default_factory=dict)
