from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from typing import Any

from vigil.actions import get_serialized_action_registry
from vigil.agent.types import AgentObservation
from vigil.agent.profiles import AgentProfile, get_profile

JSONDict = dict[str, Any]
PROMPT_POLICY_NAME = "native_embodied_public_evidence"
NEUTRAL_REPORT_PROMPT_POLICY_NAME = "native_embodied_public_evidence_neutral_report"
PROMPT_POLICY_VERSION = "2026-04-27-state-report-labels"
LEGACY_PROMPT_POLICY_VERSION = "2026-04-18"
# Official 2026-05-02 legacy reference manifest hash.
LEGACY_PROMPT_POLICY_SHA256 = "b450374f4bcc13a58a782c10522e8bc97f46d92d4b49039ee8f00a4889df1d38"

_DEFAULT_PROMPT_POLICY_VERSIONS: dict[str, str] = {
    PROMPT_POLICY_NAME: PROMPT_POLICY_VERSION,
    NEUTRAL_REPORT_PROMPT_POLICY_NAME: "2026-05-02-neutral-report",
}

_PROMPT_POLICY_VERSION_ALIASES: dict[str, str] = {
    "2026-04-18-contract-aligned": LEGACY_PROMPT_POLICY_VERSION,
}

_REPORT_INSTRUCTION_RULES: dict[tuple[str, str], tuple[str, ...]] = {
    (PROMPT_POLICY_NAME, PROMPT_POLICY_VERSION): (
        "Mere visibility, proximity, or an attempted action is not enough; do not report success from visual plausibility alone.",
        "Do not claim completion from visual plausibility alone when the task requires changing world state.",
    ),
    (PROMPT_POLICY_NAME, LEGACY_PROMPT_POLICY_VERSION): (
        "Mere visibility, proximity, or an attempted action is not enough; do not report success from visual plausibility alone.",
        "Do not claim completion from visual plausibility alone when the task requires changing world state.",
        "If the task is a single-target completion task and your last action already completed the requested interaction, default to `report` or a brief verification move instead of another blind retry.",
    ),
    (NEUTRAL_REPORT_PROMPT_POLICY_NAME, _DEFAULT_PROMPT_POLICY_VERSIONS[NEUTRAL_REPORT_PROMPT_POLICY_NAME]): (
        "Decide when to report based on the task instruction, the current observation, and the action history available in this episode.",
        "For tasks that require changing world state, use the observations available after your actions when deciding whether the requested condition has been achieved.",
    ),
}

_DEFAULT_GROUNDING_RULES: tuple[str, ...] = (
    "Use only the frame whose `role` is `current` for visibility judgments and `interact_pixel` targeting.",
    "`interact_pixel` acts on the object currently under the specified location in the current RGB frame.",
    "Do not assume hidden success state; rely on subsequent public observations and allowed feedback fields from this episode.",
)

_DEFAULT_DEPTH_MIN_METERS = 0.1
_DEFAULT_DEPTH_MAX_METERS = 5.0
_DEFAULT_DEPTH_RENDER_MODE = "grayscale"


def _read_depth_meter_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip() or os.environ.get(name.replace("VIGIL_", "VEVAL_"), "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value != value or value in {float("inf"), float("-inf")}:
        return default
    return value


def resolve_depth_range_meters() -> tuple[float, float]:
    min_depth = _read_depth_meter_env("VIGIL_DEPTH_MIN_METERS", _DEFAULT_DEPTH_MIN_METERS)
    max_depth = _read_depth_meter_env("VIGIL_DEPTH_MAX_METERS", _DEFAULT_DEPTH_MAX_METERS)
    if max_depth <= min_depth:
        return _DEFAULT_DEPTH_MIN_METERS, _DEFAULT_DEPTH_MAX_METERS
    return min_depth, max_depth


def resolve_depth_render_mode() -> str:
    raw = os.environ.get("VIGIL_DEPTH_RENDER_MODE", "").strip().lower() or os.environ.get("VEVAL_DEPTH_RENDER_MODE", "").strip().lower()
    if raw in {"grayscale", "pseudo_color"}:
        return raw
    return _DEFAULT_DEPTH_RENDER_MODE


def describe_depth_prompt_encoding() -> str:
    min_depth, max_depth = resolve_depth_range_meters()
    mode = resolve_depth_render_mode()
    if mode == "pseudo_color":
        return (
            f"aligned to the RGB frame and rendered from metric depth clipped to [{min_depth:g}, {max_depth:g}] meters "
            "as a pseudo-color image; red/orange = nearest, yellow = mid-range, cyan = mid-far, blue = farthest"
        )
    return (
        f"aligned to the RGB frame and rendered from metric depth clipped to [{min_depth:g}, {max_depth:g}] meters "
        "as a grayscale image; brighter = nearer, darker = farther"
    )


def normalize_prompt_policy_name(raw: str | None) -> str:
    policy_name = str(raw or "").strip() or PROMPT_POLICY_NAME
    if policy_name not in _DEFAULT_PROMPT_POLICY_VERSIONS:
        supported = ", ".join(sorted(_DEFAULT_PROMPT_POLICY_VERSIONS))
        raise ValueError(f"Unsupported prompt policy: {policy_name}. Supported values: {supported}")
    return policy_name


def normalize_prompt_policy_version(raw: str | None, prompt_policy_name: str | None = None) -> str:
    policy_name = normalize_prompt_policy_name(prompt_policy_name)
    policy_version = _PROMPT_POLICY_VERSION_ALIASES.get(str(raw or "").strip(), str(raw or "").strip())
    if not policy_version:
        policy_version = _DEFAULT_PROMPT_POLICY_VERSIONS[policy_name]
    if (policy_name, policy_version) not in _REPORT_INSTRUCTION_RULES:
        supported = ", ".join(
            version
            for name, version in sorted(_REPORT_INSTRUCTION_RULES)
            if name == policy_name
        )
        raise ValueError(
            f"Unsupported prompt policy version for {policy_name}: {policy_version}. "
            f"Supported versions: {supported}"
        )
    return policy_version


def profile_prompt_policy_name(profile: AgentProfile | None) -> str:
    if profile is None:
        return PROMPT_POLICY_NAME
    return normalize_prompt_policy_name((profile.metadata or {}).get("prompt_policy_name"))


def profile_prompt_policy_version(profile: AgentProfile | None) -> str:
    policy_name = profile_prompt_policy_name(profile)
    if profile is None:
        return normalize_prompt_policy_version(None, policy_name)
    return normalize_prompt_policy_version((profile.metadata or {}).get("prompt_policy_version"), policy_name)


def with_prompt_policy(
    profile: AgentProfile,
    prompt_policy_name: str | None,
    prompt_policy_version: str | None = None,
) -> AgentProfile:
    resolved = normalize_prompt_policy_name(prompt_policy_name)
    resolved_version = normalize_prompt_policy_version(prompt_policy_version, resolved)
    metadata = dict(profile.metadata or {})
    metadata["prompt_policy_name"] = resolved
    metadata["prompt_policy_version"] = resolved_version
    return replace(profile, metadata=metadata)


def build_interact_pixel_system_hint(
    coord_mode: str | None,
    *,
    coord_prompt_mode: str | None = None,
) -> str:
    mode = str(coord_prompt_mode or "").strip().lower()
    normalized = str(coord_mode or "").strip().lower()
    if mode in {"none", "off", "disabled"}:
        return ""
    if normalized == "normalized_1000":
        return (
            "For interact_pixel, output x and y in normalized_1000 coordinates: integers in [0, 1000], "
            "where (0,0) is the top-left corner and (1000,1000) is the bottom-right corner of the current RGB frame."
        )
    if mode == "explicit":
        return (
            "For interact_pixel, output x and y in pixel coordinates of the current RGB frame: "
            "x in [0, width-1] and y in [0, height-1], with (0,0) at the top-left corner. "
            "Use the image_size metadata for width and height."
        )
    return ""


def build_modality_guidance_block(profile: AgentProfile) -> str | None:
    has_depth = profile.uses_modality("depth")
    has_pose = profile.pose_policy == "relative_odometry"
    if not has_depth and not has_pose:
        return None
    lines = ["## Modality guidance"]
    if has_depth:
        lines.extend([
            f"- A paired rendered depth image follows for the same frame ({describe_depth_prompt_encoding()}).",
            "- Use depth for coarse geometry, relative distance, occlusion, and reachability judgment.",
            "- Use RGB for object identity, visibility checks, and all `interact_pixel` coordinates.",
        ])
    if has_pose:
        lines.extend([
            "- `relative_pose` reports odometry in the start heading's local frame:",
            "  - `dx_meters`: lateral displacement (positive = right of start heading).",
            "  - `dz_meters`: forward/backward displacement (positive = forward from start heading).",
            "  - `dyaw_degrees`: accumulated heading change (positive = clockwise).",
            "  - `pitch_degrees`: camera tilt change (positive = looking down).",
            "  - `distance_from_start_meters`: straight-line distance from episode start.",
            "- Use pose for coarse self-localization and loop/revisit detection; it does not replace visual evidence for object targeting.",
        ])
    return "\n".join(lines)


def build_visual_context_guidance_block(profile: AgentProfile) -> str | None:
    if profile.visual_context_policy != "short_window":
        return None
    oldest_history_tag = f"t-{max(1, int((profile.metadata or {}).get('visual_context_window_size') or 1) - 1)}"
    return "\n".join(
        [
            "## Visual context guidance",
            (
                "- Observation frames are ordered oldest to newest via `temporal_tag` "
                f"(`{oldest_history_tag}`, ..., `t-1`, `t`) and each frame carries a stable `frame_id`."
            ),
            "- Use history frames and `previous_action` only as temporal context from this same episode.",
            "- Only the `current` frame (`t`) should be used for visibility judgments and `interact_pixel` targeting.",
        ]
    )


def build_task_block(
    task_instruction: str,
    *,
    prompt_policy_name: str | None = None,
    prompt_policy_version: str | None = None,
) -> str:
    policy_name = normalize_prompt_policy_name(prompt_policy_name)
    policy_version = normalize_prompt_policy_version(prompt_policy_version, policy_name)
    return "\n\n".join(
        [
            "You are an embodied agent in a simulated 3D environment with an egocentric (first-person) view.",
            "Each step you only see local observations; plan and act under partial observability.",
            "Ground decisions in the task, the current observation, recent observation history when available, and the allowed actions schema.",
            "Actions are embodied attempts in the scene, not symbolic shortcuts.",
            "Use only public evidence from this episode. Do not assume hidden simulator state or hidden success signals.",
            "For state-recognition tasks, report the observed state label (for example: on/off or open/closed) rather than mapping the state to task success/fail.",
            *_REPORT_INSTRUCTION_RULES[(policy_name, policy_version)],
            f"Task: {task_instruction}",
        ]
    )


def build_compact_action_schema_block(action_schema: list[JSONDict]) -> str:
    def _arg_descriptor(argument: JSONDict) -> str:
        name = str(argument.get("name") or "").strip()
        arg_type = str(argument.get("type") or "").strip()
        description = " ".join(str(argument.get("description") or "").strip().split())
        if not name:
            return ""
        if description:
            return f"{name}:{arg_type} ({description})" if arg_type else f"{name}:{description}"
        return f"{name}:{arg_type}" if arg_type else name

    lines = ["## Allowed actions"]
    for action in action_schema:
        name = str(action.get("name") or "").strip()
        if not name:
            continue
        desc = " ".join(str(action.get("description") or "").strip().split())
        required = ", ".join(str(item) for item in (action.get("required_arguments") or []))
        arguments = list(action.get("arguments") or [])
        arg_summary = ", ".join(
            descriptor
            for descriptor in (_arg_descriptor(arg) for arg in arguments)
            if descriptor
        )
        summary = f"- {name}"
        if desc:
            summary += f": {desc}"
        if required:
            summary += f" | required: {required}"
        if arg_summary:
            summary += f" | args: {arg_summary}"
        lines.append(summary)
    return "\n".join(lines)


def build_grounding_rules_block(rules: list[str]) -> str | None:
    if not rules:
        return None
    return "\n\n".join(["## Grounding Rules", "\n".join(f"- {rule}" for rule in rules)])


def build_output_constraints_block() -> str:
    return "\n\n".join(
        [
            "## Output format",
            "Return exactly one JSON object and nothing else.",
            "Required keys: `skill_name`, `arguments`.",
            "Optional keys: `thought`, `cognitive_state`.",
            "Use the exact action names from the allowed-actions schema above; do not invent aliases or synonyms.",
            "Do not output prose, markdown, code fences, or multiple JSON objects.",
            "If you include `thought`, keep it to one short sentence.",
        ]
    )


def build_agent_system_prompt(
    *,
    task_instruction: str,
    profile: AgentProfile | None = None,
    action_schema: list[JSONDict] | None = None,
    grounding_rules: list[str] | None = None,
    memory_block: str | None = None,
) -> str:
    resolved_profile = profile or get_profile()
    prompt_policy_name = profile_prompt_policy_name(resolved_profile)
    prompt_policy_version = profile_prompt_policy_version(resolved_profile)
    action_payload = action_schema if action_schema is not None else get_serialized_action_registry()
    resolved_grounding_rules = [
        rule
        for rule in [
            *_DEFAULT_GROUNDING_RULES,
            *[str(block).strip() for block in (grounding_rules or []) if str(block).strip()],
        ]
        if str(rule).strip()
    ]
    sections = [
        build_task_block(
            task_instruction,
            prompt_policy_name=prompt_policy_name,
            prompt_policy_version=prompt_policy_version,
        ),
        build_compact_action_schema_block(action_payload),
    ]
    for block in (
        build_modality_guidance_block(resolved_profile),
        build_visual_context_guidance_block(resolved_profile),
        build_grounding_rules_block(resolved_grounding_rules),
        memory_block,
    ):
        if block:
            sections.append(block)
    sections.append(build_output_constraints_block())
    prompt = "\n\n".join(section for section in sections if section)
    if (prompt_policy_name, prompt_policy_version) == (PROMPT_POLICY_NAME, LEGACY_PROMPT_POLICY_VERSION):
        # Match the system prompt surface recorded by the 2026-05-02 reference traces.
        return prompt + "\n"
    return prompt


def get_prompt_policy_metadata(*, profile: AgentProfile | None = None) -> JSONDict:
    policy_name = profile_prompt_policy_name(profile)
    policy_version = profile_prompt_policy_version(profile)
    canonical_payload: JSONDict = {
        "policy_name": policy_name,
        "policy_version": policy_version,
        "task_routing": "none",
        "report_basis": "public_evidence_only",
        "stop_rule": "stop_after_public_completion_evidence",
        "grounding_rules": list(_DEFAULT_GROUNDING_RULES),
        "task_block": build_task_block(
            "__PROMPT_POLICY_SENTINEL__",
            prompt_policy_name=policy_name,
            prompt_policy_version=policy_version,
        ),
        "output_constraints": build_output_constraints_block(),
    }
    canonical_text = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True)
    policy_sha256 = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()
    metadata: JSONDict = {
        "policy_name": policy_name,
        "policy_version": policy_version,
        "task_routing": "none",
        "report_basis": "public_evidence_only",
        "policy_sha256": policy_sha256,
    }
    if (policy_name, policy_version) == (PROMPT_POLICY_NAME, LEGACY_PROMPT_POLICY_VERSION):
        metadata["historical_reference_policy_sha256"] = LEGACY_PROMPT_POLICY_SHA256
    if profile is not None:
        rendered_prompt = build_agent_system_prompt(
            task_instruction="__PROMPT_POLICY_SENTINEL__",
            profile=profile,
            action_schema=get_serialized_action_registry(),
        )
        metadata["render_profile_name"] = str(profile.name or "")
        metadata["rendered_prompt_sha256"] = hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()
    return metadata


def build_frame_text_payload(
    observation: AgentObservation,
    *,
    coord_mode: str | None = None,
    include_segmentation: bool = False,
    include_pose: bool = False,
) -> JSONDict:
    metadata = dict(getattr(observation, "metadata", None) or {})
    step_index = int(getattr(observation, "step_index", 0) or 0)
    payload: JSONDict = {
        # Dataset IDs can encode hidden initial states (for example, "closed").
        # Frame labels need only distinguish steps within the current episode.
        "frame_id": f"step_{step_index}",
        "temporal_tag": str(metadata.get("temporal_tag") or "t"),
        "role": str(metadata.get("role") or "current"),
    }
    feedback = metadata.get("feedback")
    if isinstance(feedback, dict) and feedback:
        payload["feedback"] = dict(feedback)
    previous_action = metadata.get("previous_action")
    if previous_action is not None:
        payload["previous_action"] = previous_action
    if str(coord_mode or "").strip().lower() != "normalized_1000":
        image_size = metadata.get("image_size")
        if isinstance(image_size, dict):
            payload["image_size"] = dict(image_size)
    if include_segmentation and metadata.get("segmentation_size") is not None:
        payload["segmentation_size"] = metadata.get("segmentation_size")
    if include_pose and isinstance(metadata.get("relative_pose"), dict):
        pose = dict(metadata["relative_pose"])
        payload["relative_pose"] = {
            "dx_meters": pose.get("dx", pose.get("dx_meters")),
            "dz_meters": pose.get("dz", pose.get("dz_meters")),
            "dyaw_degrees": pose.get("dyaw", pose.get("dyaw_degrees")),
            "pitch_degrees": pose.get("pitch", pose.get("pitch_degrees")),
            "distance_from_start_meters": pose.get("distance_from_start", pose.get("distance_from_start_meters")),
        }
    return payload


def format_frame_text(
    observation: AgentObservation,
    *,
    coord_mode: str | None = None,
    include_segmentation: bool = False,
    include_pose: bool = False,
) -> str:
    return json.dumps(
        build_frame_text_payload(
            observation,
            coord_mode=coord_mode,
            include_segmentation=include_segmentation,
            include_pose=include_pose,
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def build_observation_tail_text(*, multimodal: bool, include_depth: bool = False) -> str:
    if multimodal:
        prefix = (
            "For each frame, sensor inputs follow the metadata block in this order when present: RGB, depth image, segmentation. "
            "Each metadata block includes a stable `frame_id` and a relative `temporal_tag`; use the RGB observation paired with the frame metadata whose `role` is `current` for visibility and interact_pixel targets. "
        )
        if include_depth:
            prefix += (
                "Use the paired depth observation for geometry, occlusion, and coarse reachability only. "
                "Keep RGB as the reference for object identity, visibility checks, and interact_pixel targets. "
            )
    else:
        prefix = (
            "Frames are listed oldest to newest and each block includes a stable `frame_id` plus a relative `temporal_tag`. "
            "Use only the block whose `role` is `current` for visibility and interact_pixel targets. "
        )
    return (
        prefix
        + "Use history frames and `previous_action` only for temporal reasoning such as motion trend, repeated views, and whether recent actions helped. "
        + "Treat the observation blocks as evidence only; follow the output-format rules from the system prompt."
    )


def build_agent_observation_text(
    observation: AgentObservation,
    *,
    coord_mode: str | None = None,
    include_tail: bool = True,
    multimodal: bool = True,
    include_depth: bool = False,
    include_segmentation: bool = False,
    include_pose: bool = False,
) -> str:
    parts = [
        format_frame_text(
            observation,
            coord_mode=coord_mode,
            include_segmentation=include_segmentation,
            include_pose=include_pose,
        )
    ]
    if include_tail:
        parts.append(build_observation_tail_text(multimodal=multimodal, include_depth=include_depth))
    return "\n\n".join(parts)


def build_agent_prompt(
    observation: AgentObservation,
    *,
    coord_mode: str | None = None,
    coord_prompt_mode: str | None = None,
    profile: AgentProfile | None = None,
) -> str:
    coord_hint = build_interact_pixel_system_hint(coord_mode, coord_prompt_mode=coord_prompt_mode)
    resolved_profile = profile or get_profile()
    system_prompt = build_agent_system_prompt(
        task_instruction=observation.instruction,
        profile=resolved_profile,
        grounding_rules=[coord_hint] if coord_hint.strip() else [],
    )
    observation_text = build_agent_observation_text(
        observation,
        coord_mode=coord_mode,
        multimodal=bool(getattr(observation, "image_path", None)),
        include_depth=resolved_profile.uses_modality("depth"),
        include_pose=resolved_profile.pose_policy == "relative_odometry",
    )
    return "\n\n".join([system_prompt, observation_text])
