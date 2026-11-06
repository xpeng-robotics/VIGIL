from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from vigil.actions import ActionCall

JSONDict = dict[str, Any]


def _boolean(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a JSON boolean, not {type(value).__name__}.")
    return value


def validate_step_evidence(step: "StepTrace") -> None:
    for name in ("action_valid", "judge_success", "terminal"):
        _boolean(getattr(step, name), name)
    judge = step.metadata.get("judge_result")
    if judge is None:
        return
    if not isinstance(judge, dict):
        raise ValueError("judge_result must be an object.")
    nullable = {"strict_world_success", "report_matches_world"}
    for name in {"world_success", "semantic_world_success", "strict_world_success", "report_submitted",
                 "report_matches_world", "invalid_action", "protocol_failure", "recoverable"}:
        if name in judge and not (name in nullable and judge[name] is None):
            _boolean(judge[name], f"judge_result.{name}")


@dataclass(frozen=True)
class StepTrace:
    step_index: int
    action: ActionCall | None = None
    action_valid: bool = True
    env_status: str = "unknown"
    judge_success: bool = False
    progress: float = 0.0
    terminal: bool = False
    error_type: str | None = None
    metadata: JSONDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: JSONDict) -> "StepTrace":
        if not isinstance(payload, dict):
            raise ValueError("Each trace step must be a JSON object.")
        index = payload.get("step_index", payload.get("step", 0))
        if type(index) is not int or index < 0:
            raise ValueError("Step index must be a non-negative integer.")
        action_payload = payload.get("action")
        action = ActionCall.from_dict(action_payload) if isinstance(action_payload, dict) else None
        progress = float(payload.get("progress", 0.0))
        if not math.isfinite(progress) or progress < 0.0 or progress > 1.0:
            raise ValueError(f"Step progress must be in [0, 1], got {progress}.")
        result = cls(
            step_index=index,
            action=action,
            action_valid=_boolean(payload.get("action_valid", action is not None), "action_valid"),
            env_status=str(payload.get("env_status", "unknown")),
            judge_success=_boolean(payload.get("judge_success", False), "judge_success"),
            progress=progress,
            terminal=_boolean(payload.get("terminal", False), "terminal"),
            error_type=payload.get("error_type"),
            metadata=dict(payload.get("metadata") or {}),
        )
        validate_step_evidence(result)
        return result

    def to_dict(self) -> JSONDict:
        payload = asdict(self)
        payload["action"] = self.action.to_dict() if self.action is not None else None
        return payload


@dataclass(frozen=True)
class EpisodeTrace:
    episode_id: str
    profile: str
    max_steps: int
    steps: tuple[StepTrace, ...]
    terminal_status: str = "unknown"
    metadata: JSONDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: JSONDict) -> "EpisodeTrace":
        if not payload.get("episode_id"):
            raise ValueError("Trace is missing required field 'episode_id'.")
        raw_steps = payload.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("Trace must contain a 'steps' list.")
        max_steps = int(payload.get("max_steps", max(len(raw_steps), 1)))
        if max_steps <= 0:
            raise ValueError("Trace max_steps must be positive.")
        return cls(
            episode_id=str(payload["episode_id"]),
            profile=str(payload.get("profile", "unknown")),
            max_steps=max_steps,
            steps=tuple(StepTrace.from_dict(step) for step in raw_steps),
            terminal_status=str(payload.get("terminal_status", "unknown")),
            metadata=dict(payload.get("metadata") or {}),
        )

    def to_dict(self) -> JSONDict:
        return {
            "episode_id": self.episode_id,
            "profile": self.profile,
            "max_steps": self.max_steps,
            "terminal_status": self.terminal_status,
            "steps": [step.to_dict() for step in self.steps],
            "metadata": dict(self.metadata),
        }


def load_trace(path: str | Path) -> EpisodeTrace:
    trace_path = Path(path)
    payload = json.loads(trace_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Trace file must contain a JSON object: {trace_path}")
    return EpisodeTrace.from_dict(payload)


def has_infrastructure_error(trace: EpisodeTrace) -> bool:
    failures = {"simulator_error", "model_request_error", "model_api_error", "model_timeout"}
    labels = [trace.terminal_status]
    for step in trace.steps:
        judge = step.metadata.get("judge_result") or {}
        labels.extend((step.env_status, step.error_type))
        labels.extend(judge.get(key) for key in ("status", "failure_label", "failure_type", "terminal_reason"))
    return any(str(label or "").split(":", 1)[0] in failures for label in labels)


def validate_completed_trace(trace: EpisodeTrace) -> None:
    """Shared structural checks for offline scoring, verification and resume."""
    if not trace.steps or trace.terminal_status in {"", "unknown", "ongoing", "running"}:
        raise ValueError("trace is empty or unfinished")
    if [step.step_index for step in trace.steps] != list(range(len(trace.steps))):
        raise ValueError("step indices must be consecutive and start at zero")
    if any(step.terminal for step in trace.steps[:-1]):
        raise ValueError("trace contains steps after a terminal step")
    if len(trace.steps) > trace.max_steps:
        raise ValueError("trace exceeds its step budget")
    if has_infrastructure_error(trace):
        raise ValueError("trace contains an infrastructure error")
