from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ObservationModality = Literal["rgb", "depth"]
FeedbackPolicy = Literal["none"]
PosePolicy = Literal["none", "relative_odometry"]
VisualContextPolicy = Literal["current_only", "short_window", "dialogue_history"]
MemoryPolicy = Literal["none"]

DEFAULT_PROFILE_NAME = "pure_rgb_dialogue_history_baseline"


@dataclass(frozen=True)
class AgentProfile:
    name: str
    observation_modalities: tuple[ObservationModality, ...] = ("rgb",)
    visual_context_policy: VisualContextPolicy = "current_only"
    feedback_policy: FeedbackPolicy = "none"
    pose_policy: PosePolicy = "none"
    memory_policy: MemoryPolicy = "none"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def uses_modality(self, modality: str) -> bool:
        return str(modality).strip().lower() in set(self.observation_modalities)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["observation_modalities"] = list(self.observation_modalities)
        return payload


_PROFILES: dict[str, AgentProfile] = {
    DEFAULT_PROFILE_NAME: AgentProfile(
        name=DEFAULT_PROFILE_NAME,
        description=(
            "Single-frame RGB with episode-local dialogue/action history. "
            "No model-visible feedback, agent-side memory, or pose is used."
        ),
        metadata={
            "prompt_policy_name": "native_embodied_public_evidence_neutral_report",
            "prompt_policy_version": "2026-05-02-neutral-report",
            "benchmark_mode": "pure_rgb_dialogue_history_baseline",
            "observation_axis": "rgb",
            "visual_context_axis": "current_only",
            "feedback_axis": "none",
            "pose_axis": "none",
            "memory_axis": "none",
            "conversation_history_turns": 20,
            "mainline": True,
            "mainline_comparable": True,
            "memory_bucket": "none",
            "diagnostic_reason": None,
            "hypothesis": (
                "Single-frame RGB with 20-turn dialogue history only: no model-visible "
                "feedback, no agent-side memory, and no pose."
            ),
            "analysis_parent": "pure_rgb_baseline",
            "structured_memory": False,
        },
    ),
}


def get_profile(name: str | None = None) -> AgentProfile:
    key = (name or DEFAULT_PROFILE_NAME).strip()
    try:
        return _PROFILES[key]
    except KeyError as exc:
        choices = ", ".join(sorted(_PROFILES))
        raise KeyError(f"Unknown VIGIL profile {key!r}. Available profiles: {choices}") from exc


def list_profiles() -> list[dict[str, Any]]:
    return [profile.to_dict() for profile in sorted(_PROFILES.values(), key=lambda item: item.name)]


def resolve_benchmark_mode(profile: AgentProfile) -> str:
    return str(profile.metadata.get("benchmark_mode") or profile.name)
