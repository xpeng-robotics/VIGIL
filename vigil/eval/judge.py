from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from vigil.data.episodes import EpisodeSpec
from vigil.data.conditions import (
    JudgeResult,
    _clamp01,
    _normalize_report_status,
    _complement_report_status,
    _agent_in_region,
    _normalize_receptacle_ids,
    _strip_dual_success_metadata,
    _resolve_explicit_dual_success_contract,
    _build_dual_success_eval,
    _state_report_label_from_oracle,
    _evaluate_success_single,
    evaluate_success,
    evaluate_condition,
    evaluate_episode,
    estimate_progress,
    target_object_matches,
)
from vigil.eval.types import EnvActionResult, EpisodeSettlement, StepJudgeResult

JSONDict = dict[str, Any]


RECOVERABLE_FAILURE_LABELS: frozenset[str] = frozenset(
    {
        "too_far",
        "interaction_no_effect",
        "not_visible",
        "hand_full",
        "path_blocked",
        "already_holding_target",
        "already_in_target_state",
    }
)


def _sanitize_error_message(message: Any) -> str | None:
    text = str(message or "").strip()
    if not text:
        return None
    lowered = text.lower()
    known_categories = {
        "invalid_format",
        "invalid_action_schema",
        "invalid_arguments",
        "model_timeout",
        "model_api_error",
        "too_far",
        "not_visible",
        "path_blocked",
        "hand_full",
        "already_holding_target",
        "out_of_bounds",
        "interaction_not_available",
        "interaction_no_effect",
        "intent_not_supported",
        "already_in_target_state",
        "action_failed",
    }
    if lowered in known_categories:
        return lowered
    if "invalid json" in lowered or "not valid json" in lowered:
        return "invalid_format"
    if "missing skill_name" in lowered or "unknown skill" in lowered:
        return "invalid_action_schema"
    if "missing required arguments" in lowered or "must be one of" in lowered:
        return "invalid_arguments"
    if "arguments must be an object" in lowered or "must be numeric" in lowered:
        return "invalid_arguments"
    if "timed out" in lowered or "timeout" in lowered:
        return "model_timeout"
    if "connection error" in lowered or "api error" in lowered or "http error" in lowered:
        return "model_api_error"
    if "too far" in lowered or "too_far" in lowered:
        return "too_far"
    if "not visible" in lowered or "not_visible" in lowered:
        return "not_visible"
    if "blocked" in lowered or "blocking" in lowered or "path_blocked" in lowered:
        return "path_blocked"
    if "hand_full" in lowered or "hand has something in it already" in lowered:
        return "hand_full"
    if "already_holding_target" in lowered or "already holding target" in lowered:
        return "already_holding_target"
    if "receptacle_closed" in lowered or "place_not_whitelisted" in lowered:
        return "interaction_not_available"
    if "intent_not_supported" in lowered or "no_supported_action" in lowered:
        return "intent_not_supported"
    if "already_in_target_state" in lowered or "already in target state" in lowered:
        return "already_in_target_state"
    if "no clickable object has been selected" in lowered or "interaction_miss" in lowered:
        return "interaction_no_effect"
    if "interaction_no_effect" in lowered or "no_effect" in lowered:
        return "interaction_no_effect"
    if "out of bounds" in lowered:
        return "out_of_bounds"
    return "action_failed"


def classify_failure_label(message: Any) -> str | None:
    normalized = _sanitize_error_message(message)
    if normalized is None:
        return None
    if normalized in {
        "too_far",
        "interaction_no_effect",
        "out_of_bounds",
        "not_visible",
        "hand_full",
        "path_blocked",
        "already_holding_target",
        "intent_not_supported",
        "interaction_not_available",
        "already_in_target_state",
    }:
        return normalized
    if normalized in {"invalid_format", "invalid_action_schema", "invalid_arguments"}:
        return "invalid_arguments"
    return "runtime_error"


def _spec_max_steps(spec: EpisodeSpec) -> int:
    raw_budget = getattr(spec, "budget", {})
    if isinstance(raw_budget, dict):
        value = raw_budget.get("max_steps")
    else:
        value = getattr(raw_budget, "max_steps", None)
    return int(value or getattr(spec, "max_steps", 1) or 1)


@dataclass
class JudgeState:
    steps_used: int = 0
    invalid_actions: int = 0
    protocol_failures: int = 0
    recoverable_failures: int = 0
    latest_progress: float = 0.0
    world_success: bool = False
    semantic_latest_progress: float = 0.0
    strict_latest_progress: float | None = None
    semantic_world_success: bool = False
    strict_world_success: bool | None = None
    report_submitted: bool = False
    agent_report_status: str | None = None
    report_matches_world: bool | None = None
    protocol_failure: bool = False
    false_report: bool = False
    bound_success_object_id: str | None = None
    success_target_interacted: bool = False
    visibility_latched: bool = False
    grounding_hits: list[JSONDict] = field(default_factory=list)
    violations: list[JSONDict] = field(default_factory=list)
    terminal_status: str | None = None
    terminal_reason: str | None = None


def _expected_report_status(success_spec: JSONDict, *, world_success: bool) -> str | None:
    condition_type = str(success_spec.get("type") or "").strip().lower()
    if condition_type != "report_status":
        return None
    expected_when_true = _normalize_report_status(success_spec.get("expected")) or "success"
    return expected_when_true if world_success else _complement_report_status(expected_when_true)


def _lookup_region(spec: EpisodeSpec, region_id: str) -> JSONDict | None:
    for region in list(spec.constraint_spec.get("regions") or []):
        if str(region.get("region_id") or "").strip() == region_id:
            return dict(region)
    return None


def _resolve_dual_success_contract_for_judging(spec: EpisodeSpec, success_spec: JSONDict) -> JSONDict:
    explicit = _resolve_explicit_dual_success_contract(success_spec)
    if explicit is not None:
        contract = dict(explicit)
        contract["semantic_spec"] = _normalize_effective_success_spec_for_judging(
            spec, dict(contract.get("semantic_spec") or {})
        )
        strict_spec = dict(contract.get("strict_spec") or {})
        contract["strict_spec"] = (
            _normalize_effective_success_spec_for_judging(spec, strict_spec)
            if strict_spec
            else None
        )
        return contract

    base_spec = _strip_dual_success_metadata(success_spec)
    semantic_spec = _normalize_effective_success_spec_for_judging(spec, base_spec)
    strict_spec: JSONDict | None = None
    strict_unavailable_reason: str | None = None
    condition_type = str(base_spec.get("type") or "").strip().lower()

    if (
        spec.task_family == "T3_sequential_manipulation"
        and condition_type == "object_at_receptacle"
    ):
        allowed_receptacle_ids = _normalize_receptacle_ids(base_spec.get("allowed_receptacle_object_ids"))
        if allowed_receptacle_ids:
            strict_spec = dict(base_spec)
        else:
            strict_unavailable_reason = "no_public_receptacle_group"
    else:
        strict_spec = dict(semantic_spec)

    return {
        "primary_metric": "semantic",
        "secondary_metric": "strict",
        "semantic_spec": semantic_spec,
        "strict_spec": strict_spec,
        "strict_unavailable_reason": strict_unavailable_reason,
    }


def _is_synthetic_target_id(value: Any) -> bool:
    target_id = str(value or "").strip()
    return bool(target_id) and "synthetic-bootstrap" in target_id


def _resolve_bound_success_target_id(
    *,
    spec: EpisodeSpec,
    state: JudgeState,
    env_result: EnvActionResult,
) -> str | None:
    success_spec = dict(spec.success_spec or {})
    if str(success_spec.get("type") or "").strip().lower() != "object_state":
        return None
    target_type = str(success_spec.get("target_object_type") or "").strip()
    if not target_type:
        return None
    if state.bound_success_object_id:
        return state.bound_success_object_id
    resolved_target = dict(env_result.resolved_target or {})
    resolved_type = str(
        resolved_target.get("object_type")
        or resolved_target.get("objectType")
        or ""
    ).strip()
    resolved_id = str(
        resolved_target.get("object_id")
        or resolved_target.get("objectId")
        or ""
    ).strip()
    if resolved_id and resolved_type == target_type:
        return resolved_id
    return None


def _requires_explicit_target_binding(spec: EpisodeSpec, success_spec: JSONDict) -> bool:
    if str(success_spec.get("type") or "").strip().lower() != "object_state":
        return False
    target_object_id = str(success_spec.get("target_object_id") or "").strip()
    if not target_object_id:
        target_object_id = str((spec.trace_hints or {}).get("target_object_id") or "").strip()
    if _is_synthetic_target_id(target_object_id):
        return True
    return False


def _requires_success_target_interaction(spec: EpisodeSpec, success_spec: JSONDict) -> bool:
    if str(success_spec.get("type") or "").strip().lower() != "object_state":
        return False
    interactables = list(spec.generation_hints.get("interactables") or [])
    return bool(interactables)


def _normalize_s4_state_report_spec(spec: EpisodeSpec, success_spec: JSONDict) -> JSONDict:
    if spec.task_family != "S4_state_recognition":
        return success_spec
    if str(success_spec.get("type") or "").strip().lower() != "report_status":
        return success_spec
    expected = _state_report_label_from_oracle(dict(success_spec.get("oracle_condition") or {}))
    if expected is None:
        return success_spec
    normalized = dict(success_spec)
    normalized["expected"] = expected
    return normalized


def _normalize_effective_success_spec_for_judging(spec: EpisodeSpec, success_spec: JSONDict) -> JSONDict:
    normalized = dict(success_spec or {})
    condition_type = str(normalized.get("type") or "").strip().lower()
    if (
        spec.task_family == "T3_sequential_manipulation"
        and condition_type == "object_at_receptacle"
        and str(normalized.get("receptacle_type") or normalized.get("target_place_type") or "").strip()
    ):
        # T3 place prompts should never rely on a hidden singleton instance. When a
        # reviewer authored an explicit group, keep that group; otherwise fall back
        # to legacy type-level semantics for backward compatibility.
        normalized.pop("receptacle_object_id", None)
        normalized.pop("target_place_id", None)
    normalized = _normalize_s4_state_report_spec(spec, normalized)
    return normalized


def _resolved_target_matches_success_spec(resolved_target: JSONDict | None, success_spec: JSONDict) -> bool:
    target = dict(resolved_target or {})
    resolved_id = str(target.get("object_id") or target.get("objectId") or "").strip()
    resolved_type = str(target.get("object_type") or target.get("objectType") or "").strip()
    target_id = str(success_spec.get("target_object_id") or "").strip()
    target_type = str(success_spec.get("target_object_type") or "").strip()
    if target_id:
        return bool(resolved_id) and resolved_id == target_id
    if target_type:
        return bool(resolved_type) and resolved_type == target_type
    return False


def _evaluate_action_constraints(spec: EpisodeSpec, env_result: EnvActionResult) -> list[JSONDict]:
    violations: list[JSONDict] = []
    for constraint in list(spec.constraint_spec.get("action_constraints") or []):
        ctype = str(constraint.get("type") or "").strip().lower()
        if ctype == "must_resolve_target_for_interact":
            skill = str(constraint.get("skill") or "interact_pixel").strip()
            if env_result.skill_name == skill and not env_result.target_resolved:
                violations.append(
                    {
                        "type": "must_resolve_target_for_interact",
                        "skill": skill,
                        "severity": "invalid",
                    }
                )
    return violations


def _hazard_active(spec: EpisodeSpec, world_state: JSONDict, hazard: JSONDict) -> bool:
    if not bool(hazard.get("active", True)):
        return False
    trigger = dict(hazard.get("trigger") or {})
    trigger_type = str(trigger.get("type") or "").strip().lower()
    region_id = str(trigger.get("region_id") or trigger.get("volume_id") or "")
    region = _lookup_region(spec, region_id) if region_id else None
    region_match = True if not region_id else _agent_in_region(world_state, region)
    if trigger_type == "forbidden_when_flag_false":
        flags = dict(world_state.get("flags") or {})
        flag_key = str(trigger.get("flag_key") or "")
        expected = trigger.get("flag_value")
        return region_match and flags.get(flag_key) == expected
    if trigger_type in {"navigation_volume", "always"}:
        return region_match
    return False


def _evaluate_hazards(spec: EpisodeSpec, world_state: JSONDict) -> list[JSONDict]:
    violations: list[JSONDict] = []
    for hazard in list(spec.constraint_spec.get("hazards") or []):
        if not isinstance(hazard, dict) or not _hazard_active(spec, world_state, hazard):
            continue
        violations.append(
            {
                "type": "hazard_triggered",
                "hazard_id": hazard.get("hazard_id"),
                "hazard_type": hazard.get("hazard_type"),
                "severity": "unsafe" if bool(hazard.get("fatal_if_crossed")) else "invalid",
            }
        )
    return violations


def settle_report_outcome(
    report_status: str,
    *,
    world_success: bool,
    expected_status: str | None = None,
) -> JSONDict:
    normalized_status = _normalize_report_status(report_status) or str(report_status or "").strip().lower()
    normalized_expected = _normalize_report_status(expected_status)
    if normalized_expected is not None:
        report_matches_world = normalized_status == normalized_expected
        terminal_status = "success" if report_matches_world else "failure"
        terminal_reason = (
            "report_success"
            if terminal_status == "success"
            else "false_success_report"
            if normalized_status == "success"
            else "false_negative_report"
            if normalized_expected == "success"
            else "report_mismatch"
        )
    else:
        report_matches_world = (
            (normalized_status == "success" and world_success)
            or (normalized_status in {"fail", "unsafe", "invalid"} and not world_success)
        )
        if normalized_status == "success" and world_success:
            terminal_status = "success"
        elif not report_matches_world:
            terminal_status = "failure"
        elif normalized_status == "unsafe":
            terminal_status = "unsafe"
        elif normalized_status == "invalid":
            terminal_status = "invalid"
        else:
            terminal_status = "failure"
        terminal_reason = (
            "report_success"
            if terminal_status == "success"
            else "false_success_report"
            if normalized_status == "success" and not world_success
            else "false_negative_report"
            if normalized_status in {"fail", "unsafe", "invalid"} and world_success
            else f"report_{normalized_status or 'invalid'}"
        )
    return {
        "report_status": normalized_status or None,
        "expected_status": normalized_expected,
        "report_matches_world": report_matches_world,
        "terminal_status": terminal_status,
        "terminal_reason": terminal_reason,
        "failure_label": terminal_reason if terminal_status != "success" else None,
    }


def judge_step(
    *,
    spec: EpisodeSpec,
    state: JudgeState,
    env_result: EnvActionResult,
    protocol_failure: bool = False,
) -> StepJudgeResult:
    success_contract = _resolve_dual_success_contract_for_judging(spec, spec.success_spec or {})
    effective_success_spec = dict(success_contract.get("semantic_spec") or {})
    strict_success_spec = dict(success_contract.get("strict_spec") or {})
    strict_unavailable_reason = success_contract.get("strict_unavailable_reason")
    if (
        str(effective_success_spec.get("type") or "").strip().lower() == "object_state"
        and not effective_success_spec.get("target_object_id")
    ):
        bound_target_id = _resolve_bound_success_target_id(
            spec=spec,
            state=state,
            env_result=env_result,
        )
        if bound_target_id:
            effective_success_spec["target_object_id"] = bound_target_id
            state.bound_success_object_id = bound_target_id
        else:
            target_type = str(effective_success_spec.get("target_object_type") or "").strip()
            object_count = sum(
                1
                for item in list(env_result.post_state.get("objects") or [])
                if str(item.get("objectType") or "").strip() == target_type
            )
            if target_type and object_count > 1:
                effective_success_spec["_require_unique_match"] = True
    interact_intent = str((env_result.executed_arguments or {}).get("intent") or "").strip().lower()
    if (
        env_result.skill_name == "interact_pixel"
        and interact_intent == "ground"
        and env_result.target_resolved
        and env_result.simulator_success
    ):
        resolved = dict(env_result.resolved_target or {})
        state.grounding_hits.append({
            "object_id": resolved.get("object_id") or resolved.get("objectId"),
            "object_type": resolved.get("object_type") or resolved.get("objectType"),
        })

    augmented_post_state = dict(env_result.post_state)
    aug_flags = dict(augmented_post_state.get("flags") or {})
    aug_flags["grounding_hits"] = list(state.grounding_hits)
    augmented_post_state["flags"] = aug_flags

    require_explicit_binding = _requires_explicit_target_binding(spec, effective_success_spec)
    if require_explicit_binding and not state.bound_success_object_id:
        success_eval = {
            "resolved": False,
            "success": False,
            "progress": 0.0,
            "message": "synthetic bootstrap target requires explicit target binding before success can be credited",
        }
    else:
        if (
            _requires_success_target_interaction(spec, effective_success_spec)
            and env_result.skill_name == "interact_pixel"
            and env_result.target_resolved
            and _resolved_target_matches_success_spec(env_result.resolved_target, effective_success_spec)
            and (
                env_result.simulator_success
                or str(env_result.error_message or "").strip().lower() == "already_in_target_state"
            )
        ):
            state.success_target_interacted = True
        if _requires_success_target_interaction(spec, effective_success_spec) and not state.success_target_interacted:
            success_eval = {
                "resolved": False,
                "success": False,
                "progress": 0.0,
                "message": "interactive object_state tasks require a successful target interaction before success can be credited",
            }
        else:
            success_eval = evaluate_success(augmented_post_state, effective_success_spec)
    semantic_eval = dict(success_eval.get("semantic_eval") or success_eval)
    strict_eval: JSONDict | None = None
    if strict_success_spec:
        strict_eval = _evaluate_success_single(augmented_post_state, strict_success_spec)
    success_eval = _build_dual_success_eval(
        semantic_eval=semantic_eval,
        strict_eval=strict_eval,
        primary_metric=str(success_contract.get("primary_metric") or "semantic"),
        secondary_metric=str(success_contract.get("secondary_metric") or "strict"),
        strict_unavailable_reason=(strict_unavailable_reason if isinstance(strict_unavailable_reason, str) else None),
    )
    world_success = bool(success_eval.get("success"))
    semantic_world_success = bool(semantic_eval.get("success"))
    strict_world_success = bool(strict_eval.get("success")) if strict_eval is not None else None
    if (
        str(effective_success_spec.get("type") or "").strip().lower() == "object_state"
        and str(effective_success_spec.get("field") or "").strip().lower() == "visible"
    ):
        if world_success:
            state.visibility_latched = True
        elif state.visibility_latched:
            world_success = True
            semantic_world_success = True
            success_eval = dict(success_eval, success=True, progress=1.0, message="visibility latched from earlier step")
            semantic_eval = dict(semantic_eval, success=True, progress=1.0, message="visibility latched from earlier step")
    progress = _clamp01(success_eval.get("progress", state.latest_progress))
    semantic_progress = _clamp01(semantic_eval.get("progress", progress))
    strict_progress = _clamp01(strict_eval.get("progress", progress)) if strict_eval is not None else None
    state.latest_progress = max(state.latest_progress, progress)
    state.world_success = world_success
    state.semantic_world_success = semantic_world_success
    state.strict_world_success = strict_world_success
    state.semantic_latest_progress = max(getattr(state, "semantic_latest_progress", 0.0), semantic_progress)
    current_strict_progress = getattr(state, "strict_latest_progress", None)
    if strict_progress is not None:
        baseline = current_strict_progress if current_strict_progress is not None else 0.0
        state.strict_latest_progress = max(baseline, strict_progress)
    else:
        state.strict_latest_progress = current_strict_progress

    if protocol_failure:
        state.protocol_failure = True
        state.protocol_failures += 1
        invalid_limit = int(spec.constraint_spec.get("invalid_action_limit", 0) or 0)
        combined_invalid = state.invalid_actions + state.protocol_failures
        if invalid_limit > 0 and combined_invalid > invalid_limit:
            state.terminal_status = "invalid"
            state.terminal_reason = "invalid_action_limit_exceeded"
            state.violations.append(
                {"type": "invalid_action_limit_exceeded", "limit": invalid_limit, "count": combined_invalid}
            )
            return StepJudgeResult(
                status="invalid",
                progress=state.latest_progress,
                recoverable=False,
                invalid_action=True,
                protocol_failure=True,
                failure_label="invalid_action_limit_exceeded",
                terminal_reason=state.terminal_reason,
                world_success=world_success,
                semantic_world_success=semantic_world_success,
                strict_world_success=strict_world_success,
                semantic_progress=semantic_progress,
                strict_progress=strict_progress,
                primary_metric=str(success_contract.get("primary_metric") or "semantic"),
                violations=list(state.violations),
                oracle_facts=success_eval,
            )
        return StepJudgeResult(
            status="ongoing",
            progress=state.latest_progress,
            recoverable=False,
            invalid_action=True,
            protocol_failure=True,
            failure_label="model_protocol_error",
            world_success=world_success,
            semantic_world_success=semantic_world_success,
            strict_world_success=strict_world_success,
            semantic_progress=semantic_progress,
            strict_progress=strict_progress,
            primary_metric=str(success_contract.get("primary_metric") or "semantic"),
            oracle_facts=success_eval,
        )

    violations: list[JSONDict] = []
    violations.extend(_evaluate_action_constraints(spec, env_result))
    violations.extend(_evaluate_hazards(spec, env_result.post_state))

    failure_label = classify_failure_label(env_result.error_message)
    recoverable = bool(failure_label in RECOVERABLE_FAILURE_LABELS)
    invalid_action = bool((not env_result.simulator_success) and not recoverable and env_result.skill_name != "report")
    if any(str(item.get("severity") or "") == "invalid" for item in violations):
        invalid_action = True
        if failure_label is None:
            failure_label = str(violations[0].get("type") or "constraint_violation")
    if recoverable:
        state.recoverable_failures += 1
    if invalid_action:
        state.invalid_actions += 1
    if violations:
        state.violations.extend(violations)

    if any(str(item.get("severity") or "") == "unsafe" for item in violations):
        state.terminal_status = "unsafe"
        state.terminal_reason = "hazard_triggered"
        return StepJudgeResult(
            status="unsafe",
            progress=state.latest_progress,
            recoverable=False,
            invalid_action=False,
            protocol_failure=False,
            failure_label="hazard_triggered",
            terminal_reason=state.terminal_reason,
            world_success=world_success,
            semantic_world_success=semantic_world_success,
            strict_world_success=strict_world_success,
            semantic_progress=semantic_progress,
            strict_progress=strict_progress,
            primary_metric=str(success_contract.get("primary_metric") or "semantic"),
            violations=list(violations),
            oracle_facts=success_eval,
        )

    if env_result.skill_name == "report":
        state.report_submitted = True
        expected_status = _expected_report_status(effective_success_spec, world_success=world_success)
        eval_expected = success_eval.get("expected_report_status")
        if eval_expected is not None:
            expected_status = _normalize_report_status(eval_expected)
        report_info = settle_report_outcome(
            str(env_result.executed_arguments.get("status") or ""),
            world_success=semantic_world_success,
            expected_status=expected_status,
        )
        report_status = report_info["report_status"]
        report_matches_world = bool(report_info["report_matches_world"])
        state.agent_report_status = report_status
        state.report_matches_world = report_matches_world
        if not report_matches_world:
            state.false_report = True
        terminal_status = str(report_info["terminal_status"])
        terminal_reason = str(report_info["terminal_reason"])
        state.terminal_status = terminal_status
        state.terminal_reason = terminal_reason
        return StepJudgeResult(
            status=terminal_status,
            progress=state.latest_progress,
            recoverable=False,
            invalid_action=False,
            protocol_failure=False,
            failure_label=report_info["failure_label"],
            terminal_reason=terminal_reason,
            world_success=world_success,
            semantic_world_success=semantic_world_success,
            strict_world_success=strict_world_success,
            semantic_progress=semantic_progress,
            strict_progress=strict_progress,
            primary_metric=str(success_contract.get("primary_metric") or "semantic"),
            report_submitted=True,
            report_status=report_status,
            report_matches_world=report_matches_world,
            oracle_facts=success_eval,
        )

    invalid_limit = int(spec.constraint_spec.get("invalid_action_limit", 0) or 0)
    combined_invalid = state.invalid_actions + state.protocol_failures
    if invalid_limit > 0 and combined_invalid > invalid_limit:
        state.terminal_status = "invalid"
        state.terminal_reason = "invalid_action_limit_exceeded"
        state.violations.append(
            {"type": "invalid_action_limit_exceeded", "limit": invalid_limit, "count": combined_invalid}
        )
        return StepJudgeResult(
            status="invalid",
            progress=state.latest_progress,
            recoverable=False,
            invalid_action=True,
            protocol_failure=False,
            failure_label="invalid_action_limit_exceeded",
            terminal_reason=state.terminal_reason,
            world_success=world_success,
            semantic_world_success=semantic_world_success,
            strict_world_success=strict_world_success,
            semantic_progress=semantic_progress,
            strict_progress=strict_progress,
            primary_metric=str(success_contract.get("primary_metric") or "semantic"),
            violations=list(state.violations),
            oracle_facts=success_eval,
        )

    return StepJudgeResult(
        status="ongoing",
        progress=state.latest_progress,
        recoverable=recoverable,
        invalid_action=invalid_action,
        protocol_failure=False,
        failure_label=failure_label,
        world_success=world_success,
        semantic_world_success=semantic_world_success,
        strict_world_success=strict_world_success,
        semantic_progress=semantic_progress,
        strict_progress=strict_progress,
        primary_metric=str(success_contract.get("primary_metric") or "semantic"),
        violations=list(violations),
        oracle_facts=success_eval,
    )


def finalize_settlement(spec: EpisodeSpec, state: JudgeState) -> EpisodeSettlement:
    return finalize_settlement_with_budget(spec, state)


def finalize_settlement_with_budget(
    spec: EpisodeSpec,
    state: JudgeState,
    *,
    step_budget_override: int | None = None,
) -> EpisodeSettlement:
    terminal_status = state.terminal_status or "failure"
    terminal_reason = state.terminal_reason or ("fail_no_report" if not state.report_submitted else "terminal_without_reason")
    resolved_step_budget = int(step_budget_override or _spec_max_steps(spec))
    budget_exhausted = (
        state.steps_used >= resolved_step_budget
        and terminal_status == "failure"
        and terminal_reason == "fail_no_report"
    )
    return EpisodeSettlement(
        terminal_status=terminal_status,
        terminal_reason=terminal_reason,
        world_success=state.world_success,
        semantic_world_success=state.semantic_world_success,
        strict_world_success=state.strict_world_success,
        final_progress=state.latest_progress,
        semantic_final_progress=state.semantic_latest_progress,
        strict_final_progress=state.strict_latest_progress,
        steps_used=state.steps_used,
        step_budget=resolved_step_budget,
        report_submitted=state.report_submitted,
        agent_report_status=state.agent_report_status,
        report_matches_world=state.report_matches_world,
        invalid_actions=state.invalid_actions,
        protocol_failures=state.protocol_failures,
        recoverable_failures=state.recoverable_failures,
        protocol_failure=state.protocol_failure,
        false_report=state.false_report,
        budget_exhausted=budget_exhausted,
        violations=list(state.violations),
    )

# ---------------------------------------------------------------------------
# Release compatibility helpers
# ---------------------------------------------------------------------------
