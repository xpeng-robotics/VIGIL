from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from vigil.envs.types import EnvActionResult

JSONDict = dict[str, Any]


@dataclass
class StepJudgeResult:
    status: str
    progress: float
    recoverable: bool
    invalid_action: bool
    protocol_failure: bool
    failure_label: str | None = None
    terminal_reason: str | None = None
    world_success: bool = False
    semantic_world_success: bool = False
    strict_world_success: bool | None = None
    semantic_progress: float | None = None
    strict_progress: float | None = None
    primary_metric: str = "semantic"
    report_submitted: bool = False
    report_status: str | None = None
    report_matches_world: bool | None = None
    violations: list[JSONDict] = field(default_factory=list)
    oracle_facts: JSONDict = field(default_factory=dict)


@dataclass
class EpisodeSettlement:
    terminal_status: str
    terminal_reason: str
    world_success: bool
    semantic_world_success: bool
    strict_world_success: bool | None
    final_progress: float
    semantic_final_progress: float
    strict_final_progress: float | None
    steps_used: int
    step_budget: int
    report_submitted: bool
    agent_report_status: str | None
    report_matches_world: bool | None
    invalid_actions: int
    protocol_failures: int
    recoverable_failures: int
    protocol_failure: bool
    false_report: bool
    budget_exhausted: bool
    violations: list[JSONDict] = field(default_factory=list)

    def to_dict(self) -> JSONDict:
        return {
            "terminal_status": self.terminal_status,
            "terminal_reason": self.terminal_reason,
            "world_success": self.world_success,
            "semantic_world_success": self.semantic_world_success,
            "strict_world_success": self.strict_world_success,
            "final_progress": self.final_progress,
            "semantic_final_progress": self.semantic_final_progress,
            "strict_final_progress": self.strict_final_progress,
            "steps_used": self.steps_used,
            "step_budget": self.step_budget,
            "report_submitted": self.report_submitted,
            "agent_report_status": self.agent_report_status,
            "report_matches_world": self.report_matches_world,
            "invalid_actions": self.invalid_actions,
            "protocol_failures": self.protocol_failures,
            "recoverable_failures": self.recoverable_failures,
            "protocol_failure": self.protocol_failure,
            "false_report": self.false_report,
            "budget_exhausted": self.budget_exhausted,
            "violations": list(self.violations),
        }
