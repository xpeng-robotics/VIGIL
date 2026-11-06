from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from vigil.eval.result_contract import score_summary_with_contract
from vigil.eval.settlement import settle_trace
from vigil.eval.traces import EpisodeTrace
from vigil.eval.types import EpisodeSettlement

JSONDict = dict[str, Any]
SUCCESS_TERMINAL_STATUSES = {"success", "completed", "done"}
FAILURE_TERMINAL_STATUSES = {"failure", "failed", "timeout", "invalid_action", "protocol_error", "stopped"}


@dataclass(frozen=True)
class EpisodeScoreSummary:
    task_family: str
    success: bool
    semantic_success: bool
    behavior_success: bool
    clean_success: bool
    strict_success: bool | None
    progress: float
    semantic_progress: float
    strict_progress: float | None
    efficiency: float
    compliance: float
    primary_score: float
    strict_score: float | None
    diagnostics: JSONDict

    def to_dict(self) -> JSONDict:
        return score_summary_with_contract({
            "task_family": self.task_family,
            "success": self.success,
            "semantic_success": self.semantic_success,
            "behavior_success": self.behavior_success,
            "clean_success": self.clean_success,
            "strict_success": self.strict_success,
            "progress": self.progress,
            "semantic_progress": self.semantic_progress,
            "strict_progress": self.strict_progress,
            "efficiency": self.efficiency,
            "safety": self.compliance,
            "compliance": self.compliance,
            "primary_score": self.primary_score,
            "strict_score": self.strict_score,
            "diagnostics": dict(self.diagnostics),
        })


@dataclass(frozen=True)
class EpisodeScore:
    episode_id: str
    success: bool
    episode_score: float
    progress_score: float
    action_validity: float
    efficiency: float
    steps_taken: int
    max_steps: int
    terminal_status: str
    primary_score: float
    task_family: str = "unknown"
    semantic_success: bool = False
    behavior_success: bool = False
    clean_success: bool = False
    strict_success: bool | None = None
    compliance: float = 0.0
    terminal_reason: str = ""
    difficulty: str = "unknown"
    score_summary: JSONDict = field(default_factory=dict)
    settlement: JSONDict = field(default_factory=dict)
    result_metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        payload = asdict(self)
        payload["status"] = self.terminal_status
        payload["steps_used"] = self.steps_taken
        return payload

    def to_result_dict(self) -> JSONDict:
        payload = dict(self.result_metadata)
        payload.update({
            "episode_id": self.episode_id,
            "status": self.terminal_status,
            "terminal_status": self.terminal_status,
            "terminal_reason": self.terminal_reason,
            "steps_used": self.steps_taken,
            "task_family": self.task_family,
            "difficulty": self.difficulty,
            "score_summary": dict(self.score_summary),
            "settlement": dict(self.settlement),
            # Compatibility aliases for older release tooling.
            "success": self.success,
            "behavior_success": self.behavior_success,
            "clean_success": self.clean_success,
            "episode_score": self.episode_score,
            "progress_score": self.progress_score,
            "action_validity": self.action_validity,
            "efficiency": self.efficiency,
            "primary_score": self.primary_score,
        })
        return payload


@dataclass(frozen=True)
class AggregateScore:
    episode_count: int
    success_rate: float
    behavior_success_rate: float
    clean_success_rate: float
    mean_episode_score: float
    mean_progress_score: float
    mean_action_validity: float
    mean_efficiency: float
    scores: tuple[EpisodeScore, ...]
    mean_primary_score: float
    semantic_success_rate: float
    strict_success_rate: float | None
    closure_success_rate: float
    world_success_rate: float
    primary_world_success_rate: float
    semantic_world_success_rate: float
    strict_world_success_rate: float | None
    closure_given_world_rate: float | None
    mean_steps_used: float
    terminal_status_histogram: JSONDict
    diagnostic_rates: JSONDict
    by_task_family: JSONDict
    by_difficulty: JSONDict

    def to_dict(self) -> JSONDict:
        results = [score.to_result_dict() for score in self.scores]
        payload = {
            "episode_count": self.episode_count,
            "mean_primary_score": self.mean_primary_score,
            "success_rate": self.success_rate,
            "behavior_success_rate": self.behavior_success_rate,
            "clean_success_rate": self.clean_success_rate,
            "semantic_success_rate": self.semantic_success_rate,
            "strict_success_rate": self.strict_success_rate,
            "closure_success_rate": self.closure_success_rate,
            "world_success_rate": self.world_success_rate,
            "primary_world_success_rate": self.primary_world_success_rate,
            "semantic_world_success_rate": self.semantic_world_success_rate,
            "strict_world_success_rate": self.strict_world_success_rate,
            "closure_given_world_rate": self.closure_given_world_rate,
            "mean_steps_used": self.mean_steps_used,
            "terminal_status_histogram": dict(self.terminal_status_histogram),
            "diagnostic_rates": dict(self.diagnostic_rates),
            "by_task_family": dict(self.by_task_family),
            "by_difficulty": dict(self.by_difficulty),
            "results": results,
            # Compatibility aliases used by the initial public scaffold.
            "mean_episode_score": self.mean_episode_score,
            "mean_progress_score": self.mean_progress_score,
            "mean_action_validity": self.mean_action_validity,
            "mean_efficiency": self.mean_efficiency,
            "scores": [score.to_dict() for score in self.scores],
        }
        payload.update(_aggregate_result_dict_fields(results))
        payload.update(_overall_aliases(payload))
        return payload


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_mean(values: list[float] | tuple[float, ...]) -> float:
    return mean(values) if values else 0.0


def _safe_mean_optional(values: list[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    return mean(filtered) if filtered else None


LEGACY_FAMILY_ALIASES = {
    "S4_state_recognition": "S4_state_verification",
}


def _safe_rate(count: int, total: int) -> float:
    return float(count) / float(total) if total else 0.0


def _normalize_family_name(family: str) -> str:
    normalized = str(family or "").strip()
    return LEGACY_FAMILY_ALIASES.get(normalized, normalized)


def _result_score_summary(result: JSONDict) -> JSONDict:
    return dict(result.get("score_summary") or {})


def _result_score_diagnostics(result: JSONDict) -> JSONDict:
    return dict(_result_score_summary(result).get("diagnostics") or {})


def _result_primary_world_success_flag(result: JSONDict) -> float:
    diagnostics = _result_score_diagnostics(result)
    return 1.0 if diagnostics.get("primary_world_success", diagnostics.get("world_success")) else 0.0


def _result_semantic_world_success_flag(result: JSONDict) -> float:
    return 1.0 if _result_score_diagnostics(result).get("semantic_world_success") else 0.0


def _result_strict_world_success_flag(result: JSONDict) -> float | None:
    value = _result_score_diagnostics(result).get("strict_world_success")
    if value is None:
        return None
    return 1.0 if value else 0.0


def _result_semantic_success_flag(result: JSONDict) -> float:
    summary = _result_score_summary(result)
    return 1.0 if bool(summary.get("semantic_success", summary.get("success"))) else 0.0


def _result_behavior_success_flag(result: JSONDict) -> float:
    summary = _result_score_summary(result)
    value = summary.get("behavior_success")
    if value is not None:
        return 1.0 if bool(value) else 0.0
    diagnostics = _result_score_diagnostics(result)
    return 1.0 if _result_semantic_success_flag(result) > 0.0 and not bool(diagnostics.get("protocol_failure")) else 0.0


def _result_clean_success_flag(result: JSONDict) -> float:
    summary = _result_score_summary(result)
    value = summary.get("clean_success")
    if value is not None:
        return 1.0 if bool(value) else 0.0
    diagnostics = _result_score_diagnostics(result)
    return 1.0 if _result_behavior_success_flag(result) > 0.0 and int(diagnostics.get("invalid_actions") or 0) == 0 else 0.0


def _result_strict_success_flag(result: JSONDict) -> float | None:
    value = _result_score_summary(result).get("strict_success")
    if value is None:
        return None
    return 1.0 if bool(value) else 0.0


def _result_closure_success_flag(result: JSONDict) -> float:
    diagnostics = _result_score_diagnostics(result)
    return 1.0 if bool(diagnostics.get("closure_success", diagnostics.get("terminal_status") == "success")) else 0.0


def _result_honest_fail_report_flag(result: JSONDict) -> float:
    diagnostics = _result_score_diagnostics(result)
    return 1.0 if (
        bool(diagnostics.get("report_submitted"))
        and str(diagnostics.get("agent_report_status") or "").strip().lower() == "fail"
        and diagnostics.get("report_matches_world") is True
    ) else 0.0


def _result_false_negative_report_flag(result: JSONDict) -> float:
    reason = str(_result_score_diagnostics(result).get("terminal_reason") or "").strip().lower()
    return 1.0 if reason == "false_negative_report" else 0.0


def _task_family_to_capability_bucket(task_family: str, primary_capabilities: list[str] | None = None) -> str:
    family = _normalize_family_name(task_family)
    capabilities = [str(item).strip().lower() for item in (primary_capabilities or []) if str(item).strip()]
    if family.startswith("S1"):
        return "pixel_grounding"
    if family.startswith("S2"):
        return "distance_approach"
    if family.startswith("S3"):
        return "view_search"
    if family.startswith("S4"):
        return "state_verification"
    if "report" in capabilities or "closure" in capabilities:
        return "closure/reporting"
    if family.startswith("T1") or family.startswith("T2"):
        return "closure/reporting"
    return "other"


def _normalize_episode_terminal_status(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "fail":
        return "failure"
    return normalized or "unknown"


def _result_pack_diagnostic_rates(results: list[JSONDict]) -> JSONDict:
    total = len(results)
    if not total:
        return {}
    fail_no_report = invalid_limit = world_success_no_report = protocol = false_report = honest_fail = false_negative = 0
    for result in results:
        diagnostics = _result_score_diagnostics(result)
        terminal_reason = str(diagnostics.get("terminal_reason") or "")
        if terminal_reason == "fail_no_report":
            fail_no_report += 1
        if terminal_reason == "invalid_action_limit_exceeded":
            invalid_limit += 1
        if diagnostics.get("primary_world_success", diagnostics.get("world_success")) and not diagnostics.get("report_submitted"):
            world_success_no_report += 1
        if diagnostics.get("protocol_failure"):
            protocol += 1
        if diagnostics.get("false_report"):
            false_report += 1
        if _result_honest_fail_report_flag(result):
            honest_fail += 1
        if _result_false_negative_report_flag(result):
            false_negative += 1
    inv = 1.0 / total
    return {
        "fail_no_report": fail_no_report * inv,
        "invalid_action_limit_exceeded": invalid_limit * inv,
        "world_success_without_report": world_success_no_report * inv,
        "protocol_failure": protocol * inv,
        "false_report": false_report * inv,
        "honest_fail_report": honest_fail * inv,
        "false_negative_report": false_negative * inv,
    }


def _summarize_requirement_attribution_distribution(results: list[JSONDict]) -> JSONDict:
    if not results:
        return {"episode_count": 0, "dominant_requirement_failure": {}, "secondary_requirement_failures": {}}
    dominant_counts: dict[str, int] = defaultdict(int)
    secondary_counts: dict[str, int] = defaultdict(int)
    for result in results:
        attribution = dict(result.get("requirement_attribution") or {})
        dominant_counts[str(attribution.get("dominant_requirement_failure") or "none")] += 1
        for item in attribution.get("secondary_requirement_failures") or []:
            secondary_counts[str(item or "unknown")] += 1
    total = len(results)
    return {
        "episode_count": total,
        "dominant_requirement_failure": {
            key: {"count": value, "rate": _safe_rate(value, total)}
            for key, value in sorted(dominant_counts.items())
        },
        "secondary_requirement_failures": {
            key: {"count": value, "rate": _safe_rate(value, total)}
            for key, value in sorted(secondary_counts.items())
        },
    }


def _episode_sanitation(result: JSONDict) -> JSONDict:
    protocol_retry_total = 0
    observation_echo_retry_total = 0
    assisted = False
    for item in list(result.get("trace") or []):
        diagnostics = dict(item.get("agent_diagnostics") or {})
        sanitation = dict(diagnostics.get("sanitation") or {})
        if not sanitation:
            continue
        protocol_retry_total += int(sanitation.get("protocol_retry_count") or 0)
        observation_echo_retry_total += int(sanitation.get("observation_echo_retry_count") or 0)
        assisted = assisted or bool(sanitation.get("sanitized"))
    return {
        "sanitized": assisted,
        "protocol_retry_total": protocol_retry_total,
        "observation_echo_retry_total": observation_echo_retry_total,
    }


def _harness_assistance_summary(results: list[JSONDict]) -> JSONDict:
    if not results:
        return {}
    per_episode = [_episode_sanitation(result) for result in results]
    return {
        "harness_assisted_rate": _safe_mean([1.0 if item.get("sanitized") else 0.0 for item in per_episode]),
        "protocol_retry_episode_rate": _safe_mean([1.0 if int(item.get("protocol_retry_total") or 0) > 0 else 0.0 for item in per_episode]),
        "observation_echo_retry_episode_rate": _safe_mean([1.0 if int(item.get("observation_echo_retry_total") or 0) > 0 else 0.0 for item in per_episode]),
        "mean_protocol_retry_count": _safe_mean([float(item.get("protocol_retry_total") or 0.0) for item in per_episode]),
        "mean_observation_echo_retry_count": _safe_mean([float(item.get("observation_echo_retry_total") or 0.0) for item in per_episode]),
    }


def _no_report_analysis(results: list[JSONDict]) -> JSONDict:
    total = len(results)
    if not total:
        return {}

    def primary(result: JSONDict) -> float:
        return float(_result_score_summary(result).get("primary_score") or 0.0)

    def progress(result: JSONDict) -> float:
        return float(_result_score_summary(result).get("progress") or 0.0)

    no_report: list[JSONDict] = []
    reported: list[JSONDict] = []
    world_ok_no_report: list[JSONDict] = []
    fail_no_report: list[JSONDict] = []
    for result in results:
        diagnostics = _result_score_diagnostics(result)
        submitted = bool(diagnostics.get("report_submitted"))
        world_ok = bool(diagnostics.get("world_success"))
        terminal_reason = str(diagnostics.get("terminal_reason") or "")
        if submitted:
            reported.append(result)
        else:
            no_report.append(result)
        if world_ok and not submitted:
            world_ok_no_report.append(result)
        if terminal_reason == "fail_no_report":
            fail_no_report.append(result)
    return {
        "episode_count": total,
        "report_submitted_count": len(reported),
        "no_report_count": len(no_report),
        "no_report_rate": len(no_report) / total,
        "mean_primary_score_no_report": _safe_mean([primary(result) for result in no_report]) if no_report else 0.0,
        "mean_progress_no_report": _safe_mean([progress(result) for result in no_report]) if no_report else 0.0,
        "mean_steps_no_report": _safe_mean([float(result.get("steps_used") or 0) for result in no_report]) if no_report else 0.0,
        "mean_primary_score_reported": _safe_mean([primary(result) for result in reported]) if reported else 0.0,
        "world_success_without_report_count": len(world_ok_no_report),
        "world_success_without_report_rate": len(world_ok_no_report) / total,
        "mean_primary_score_world_ok_no_report": _safe_mean([primary(result) for result in world_ok_no_report]) if world_ok_no_report else 0.0,
        "mean_progress_world_ok_no_report": _safe_mean([progress(result) for result in world_ok_no_report]) if world_ok_no_report else 0.0,
        "mean_steps_world_ok_no_report": _safe_mean([float(result.get("steps_used") or 0) for result in world_ok_no_report]) if world_ok_no_report else 0.0,
        "fail_no_report_count": len(fail_no_report),
        "mean_primary_score_fail_no_report": _safe_mean([primary(result) for result in fail_no_report]) if fail_no_report else 0.0,
        "mean_progress_fail_no_report": _safe_mean([progress(result) for result in fail_no_report]) if fail_no_report else 0.0,
    }


def _extract_runtime_invocation(step: JSONDict) -> JSONDict:
    runtime_action = dict(step.get("runtime_action") or {})
    invocation = dict(runtime_action.get("executed_invocation") or runtime_action.get("validated_invocation") or {})
    if invocation:
        return invocation
    if runtime_action.get("skill_name") or runtime_action.get("action_type"):
        return runtime_action
    return {}


def _extract_runtime_action_signature(step: JSONDict) -> str | None:
    invocation = _extract_runtime_invocation(step)
    skill_name = str(invocation.get("skill_name") or invocation.get("action_type") or "").strip()
    if not skill_name:
        return None
    arguments = dict(invocation.get("arguments") or {})
    import json
    return f"{skill_name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


def _extract_behavior_metrics(result: JSONDict) -> JSONDict:
    trace = list(result.get("trace") or [])
    first_interact_step: int | None = None
    first_report_step: int | None = None
    first_candidate_step: int | None = None
    repeated_action_streak_max = 0
    same_interact_retry_count = 0
    too_far_count = 0
    interaction_no_effect_count = 0
    reposition_after_too_far_hits = 0
    reposition_after_interaction_no_effect_hits = 0
    reposition_after_too_far_total = 0
    reposition_after_interaction_no_effect_total = 0
    report_without_interaction = False
    search_modes: list[str] = []
    previous_signature: str | None = None
    current_streak = 0
    interact_signature_counts: dict[str, int] = defaultdict(int)

    def is_reposition_step(step: JSONDict) -> bool:
        invocation = _extract_runtime_invocation(step)
        skill_name = str(invocation.get("skill_name") or "").strip()
        if skill_name in {"navigate", "look"}:
            return True
        search_mode = str(((step.get("agent_diagnostics") or {}).get("search_decision") or {}).get("mode") or "")
        return search_mode in {"approach_candidate", "reposition_after_failure", "scan"}

    for index, step in enumerate(trace, start=1):
        invocation = _extract_runtime_invocation(step)
        skill_name = str(invocation.get("skill_name") or "").strip()
        failure_label = str((step.get("judge_result") or {}).get("failure_label") or step.get("failure_label") or "")
        candidate_status = dict((step.get("agent_diagnostics") or {}).get("candidate_status") or {})
        search_mode = str(((step.get("agent_diagnostics") or {}).get("search_decision") or {}).get("mode") or "").strip()
        if search_mode:
            search_modes.append(search_mode)
        if candidate_status and first_candidate_step is None:
            first_candidate_step = index
        if skill_name == "interact_pixel" and first_interact_step is None:
            first_interact_step = index
        if skill_name == "report" and first_report_step is None:
            first_report_step = index
        if skill_name == "report" and first_interact_step is None:
            report_without_interaction = True
        signature = _extract_runtime_action_signature(step)
        if signature and signature == previous_signature:
            current_streak += 1
        elif signature:
            current_streak = 1
        else:
            current_streak = 0
        previous_signature = signature
        repeated_action_streak_max = max(repeated_action_streak_max, current_streak)
        if skill_name == "interact_pixel" and signature:
            interact_signature_counts[signature] += 1
            if interact_signature_counts[signature] > 1:
                same_interact_retry_count += 1
        if failure_label == "too_far":
            too_far_count += 1
            reposition_after_too_far_total += 1
            next_step = trace[index] if index < len(trace) else None
            if next_step and is_reposition_step(next_step):
                reposition_after_too_far_hits += 1
        if failure_label == "interaction_no_effect":
            interaction_no_effect_count += 1
            reposition_after_interaction_no_effect_total += 1
            next_step = trace[index] if index < len(trace) else None
            if next_step and is_reposition_step(next_step):
                reposition_after_interaction_no_effect_hits += 1
    search_mode_switch_count = 0
    last_mode = ""
    for mode in search_modes:
        if not mode:
            continue
        if last_mode and mode != last_mode:
            search_mode_switch_count += 1
        last_mode = mode
    return {
        "first_interact_step": first_interact_step,
        "first_report_step": first_report_step,
        "repeated_action_streak_max": repeated_action_streak_max,
        "same_interact_retry_count": same_interact_retry_count,
        "too_far_count": too_far_count,
        "interaction_no_effect_count": interaction_no_effect_count,
        "reposition_after_too_far_rate": reposition_after_too_far_hits / reposition_after_too_far_total if reposition_after_too_far_total else None,
        "reposition_after_interaction_no_effect_rate": reposition_after_interaction_no_effect_hits / reposition_after_interaction_no_effect_total if reposition_after_interaction_no_effect_total else None,
        "search_mode_switch_count": search_mode_switch_count,
        "report_without_interaction": report_without_interaction,
        "steps_before_first_candidate": first_candidate_step,
    }


def _summarize_behavior_metrics(results: list[JSONDict]) -> JSONDict:
    per_episode = [_extract_behavior_metrics(result) for result in results]
    if not per_episode:
        return {}
    numeric_fields = [
        "first_interact_step",
        "first_report_step",
        "repeated_action_streak_max",
        "same_interact_retry_count",
        "too_far_count",
        "interaction_no_effect_count",
        "reposition_after_too_far_rate",
        "reposition_after_interaction_no_effect_rate",
        "search_mode_switch_count",
        "steps_before_first_candidate",
    ]
    summary: JSONDict = {}
    for field in numeric_fields:
        values = [float(metrics[field]) for metrics in per_episode if metrics.get(field) is not None]
        summary[field] = _safe_mean(values) if values else None
    summary["report_without_interaction_rate"] = _safe_mean([1.0 if metrics.get("report_without_interaction") else 0.0 for metrics in per_episode])
    summary["episode_count"] = len(per_episode)
    return summary


def _result_bucket_summary(bucket_results: list[JSONDict]) -> JSONDict:
    if not bucket_results:
        return {}
    scores = [float(_result_score_summary(result).get("primary_score") or 0.0) for result in bucket_results]
    progress = [float(_result_score_summary(result).get("progress") or 0.0) for result in bucket_results]
    success = [1.0 if bool(_result_score_summary(result).get("success")) else 0.0 for result in bucket_results]
    semantic_success = [_result_semantic_success_flag(result) for result in bucket_results]
    behavior_success = [_result_behavior_success_flag(result) for result in bucket_results]
    clean_success = [_result_clean_success_flag(result) for result in bucket_results]
    strict_success_values = [_result_strict_success_flag(result) for result in bucket_results]
    world_success = [_result_primary_world_success_flag(result) for result in bucket_results]
    semantic_world_success = [_result_semantic_world_success_flag(result) for result in bucket_results]
    strict_world_success_values = [_result_strict_world_success_flag(result) for result in bucket_results]
    closure_success = [_result_closure_success_flag(result) for result in bucket_results]
    steps = [float(result.get("steps_used") or 0) for result in bucket_results]
    diagnostics = [_result_score_diagnostics(result) for result in bucket_results]
    primary_world_ok_count = sum(1 for value in world_success if value > 0.0)
    summary = {
        "episode_count": len(bucket_results),
        "mean_primary_score": _safe_mean(scores),
        "mean_progress": _safe_mean(progress),
        "success_rate": _safe_mean(success),
        "semantic_success_rate": _safe_mean(semantic_success),
        "behavior_success_rate": _safe_mean(behavior_success),
        "clean_success_rate": _safe_mean(clean_success),
        "strict_success_rate": _safe_mean_optional(strict_success_values),
        "closure_success_rate": _safe_mean(closure_success),
        "world_success_rate": _safe_mean(world_success),
        "primary_world_success_rate": _safe_mean(world_success),
        "semantic_world_success_rate": _safe_mean(semantic_world_success),
        "strict_world_success_rate": _safe_mean_optional(strict_world_success_values),
        "closure_given_world_rate": sum(closure_success) / primary_world_ok_count if primary_world_ok_count else None,
        "report_rate": _safe_mean([1.0 if bool(diagnostics_item.get("report_submitted")) else 0.0 for diagnostics_item in diagnostics]),
        "false_report_rate": _safe_mean([1.0 if bool(diagnostics_item.get("false_report")) else 0.0 for diagnostics_item in diagnostics]),
        "honest_fail_report_rate": _safe_mean([_result_honest_fail_report_flag(result) for result in bucket_results]),
        "false_negative_report_rate": _safe_mean([_result_false_negative_report_flag(result) for result in bucket_results]),
        "fail_no_report_rate": _safe_mean([1.0 if str(diagnostics_item.get("terminal_reason") or "") == "fail_no_report" else 0.0 for diagnostics_item in diagnostics]),
        "invalid_action_limit_rate": _safe_mean([1.0 if str(diagnostics_item.get("terminal_reason") or "") == "invalid_action_limit_exceeded" else 0.0 for diagnostics_item in diagnostics]),
        "world_success_without_report_rate": _safe_mean([1.0 if (_result_primary_world_success_flag(result) > 0.0 and not bool(_result_score_diagnostics(result).get("report_submitted"))) else 0.0 for result in bucket_results]),
        "mean_steps_used": _safe_mean(steps),
        "behavior_metrics_summary": _summarize_behavior_metrics(bucket_results),
        "requirement_attribution_distribution": _summarize_requirement_attribution_distribution(bucket_results),
    }
    summary["harness_assistance_summary"] = _harness_assistance_summary(bucket_results)
    return summary


def _result_difficulty_summary(results: list[JSONDict]) -> JSONDict:
    by_difficulty: dict[str, list[JSONDict]] = defaultdict(list)
    for result in results:
        by_difficulty[str(result.get("difficulty") or "unknown")].append(result)
    summaries: JSONDict = {}
    for difficulty, bucket in sorted(by_difficulty.items()):
        strict_world_success = [_result_strict_world_success_flag(result) for result in bucket]
        strict_world_success_present = [value for value in strict_world_success if value is not None]
        summaries[difficulty] = {
            "episode_count": len(bucket),
            "mean_primary_score": _safe_mean([float(_result_score_summary(result).get("primary_score") or 0.0) for result in bucket]),
            "success_rate": _safe_mean([1.0 if bool(_result_score_summary(result).get("success")) else 0.0 for result in bucket]),
            "behavior_success_rate": _safe_mean([_result_behavior_success_flag(result) for result in bucket]),
            "clean_success_rate": _safe_mean([_result_clean_success_flag(result) for result in bucket]),
            "closure_success_rate": _safe_mean([_result_closure_success_flag(result) for result in bucket]),
            "world_success_rate": _safe_mean([_result_primary_world_success_flag(result) for result in bucket]),
            "primary_world_success_rate": _safe_mean([_result_primary_world_success_flag(result) for result in bucket]),
            "strict_world_success_rate": _safe_mean(strict_world_success_present) if strict_world_success_present else None,
        }
    return summaries


def _aggregate_result_dict_fields(results: list[JSONDict]) -> JSONDict:
    by_family: dict[str, list[JSONDict]] = defaultdict(list)
    by_capability: dict[str, list[JSONDict]] = defaultdict(list)
    by_template: dict[str, list[JSONDict]] = defaultdict(list)
    by_target_group: dict[str, list[JSONDict]] = defaultdict(list)
    statuses: dict[str, int] = defaultdict(int)
    for result in results:
        summary = _result_score_summary(result)
        diagnostics = _result_score_diagnostics(result)
        family = _normalize_family_name(str(summary.get("task_family") or result.get("task_family") or "unknown"))
        capability = _task_family_to_capability_bucket(family, list(result.get("primary_capabilities") or []))
        template = str(result.get("functional_template") or "unknown")
        target_group = str(result.get("target_group") or "unknown")
        terminal_status = str(diagnostics.get("terminal_status") or result.get("status") or "unknown")
        by_family[family].append(result)
        by_capability[capability].append(result)
        by_template[template].append(result)
        by_target_group[target_group].append(result)
        statuses[_normalize_episode_terminal_status(terminal_status)] += 1
    return {
        "diagnostic_rates": _result_pack_diagnostic_rates(results),
        "requirement_attribution_distribution": _summarize_requirement_attribution_distribution(results),
        "no_report_analysis": _no_report_analysis(results),
        "behavior_metrics_summary": _summarize_behavior_metrics(results),
        "harness_assistance_summary": _harness_assistance_summary(results),
        "terminal_status_histogram": dict(sorted(statuses.items())),
        "by_task_family": {family: _result_bucket_summary(bucket) for family, bucket in sorted(by_family.items())},
        "by_capability_bucket": {capability: _result_bucket_summary(bucket) for capability, bucket in sorted(by_capability.items())},
        "by_functional_template": {template: _result_bucket_summary(bucket) for template, bucket in sorted(by_template.items())},
        "by_target_group": {group: _result_bucket_summary(bucket) for group, bucket in sorted(by_target_group.items())},
        "by_difficulty": _result_difficulty_summary(results),
    }


def _overall_aliases(payload: JSONDict) -> JSONDict:
    return {
        "overall_episode_count": payload.get("episode_count"),
        "overall_mean_primary_score": payload.get("mean_primary_score"),
        "overall_success_rate": payload.get("success_rate"),
        "overall_behavior_success_rate": payload.get("behavior_success_rate"),
        "overall_clean_success_rate": payload.get("clean_success_rate"),
        "overall_world_success_rate": payload.get("world_success_rate"),
        "overall_semantic_success_rate": payload.get("semantic_success_rate"),
        "overall_strict_success_rate": payload.get("strict_success_rate"),
        "overall_closure_success_rate": payload.get("closure_success_rate"),
        "overall_primary_world_success_rate": payload.get("primary_world_success_rate"),
        "overall_semantic_world_success_rate": payload.get("semantic_world_success_rate"),
        "overall_strict_world_success_rate": payload.get("strict_world_success_rate"),
        "overall_closure_given_world_rate": payload.get("closure_given_world_rate"),
        "overall_diagnostic_rates": dict(payload.get("diagnostic_rates") or {}),
        "overall_attribution_distribution": dict(payload.get("requirement_attribution_distribution") or {}),
        "overall_no_report_analysis": dict(payload.get("no_report_analysis") or {}),
        "overall_harness_assistance_summary": dict(payload.get("harness_assistance_summary") or {}),
    }


def _legacy_trace_item(trace_item: JSONDict) -> bool:
    return "judge_result" not in trace_item


def _legacy_steps_used(trace: list[JSONDict], terminal_status: str | None) -> int:
    resolved_terminal = str(terminal_status or "").strip().lower()
    if not trace:
        return 0
    if resolved_terminal and trace[-1].get("failure_label") == "fail_no_report":
        return max(0, len(trace) - 1)
    return len(trace)


def summarize_episode(*, settlement: EpisodeSettlement, task_family: str) -> EpisodeScoreSummary:
    closure_success = (
        settlement.terminal_status == "success"
        and settlement.report_submitted
        and settlement.report_matches_world is True
    )
    semantic_success = closure_success and settlement.semantic_world_success
    behavior_success = semantic_success and not settlement.protocol_failure
    clean_success = behavior_success and settlement.invalid_actions == 0
    strict_success = (
        closure_success and settlement.strict_world_success
        if settlement.strict_world_success is not None
        else None
    )
    success = semantic_success
    is_terminal = settlement.terminal_status not in {"ongoing", ""}
    progress = _clamp01(settlement.final_progress)
    semantic_progress = _clamp01(settlement.semantic_final_progress)
    strict_progress = _clamp01(settlement.strict_final_progress) if settlement.strict_final_progress is not None else None
    efficiency = _clamp01(1.0 - (settlement.steps_used / settlement.step_budget)) if settlement.step_budget > 0 else 0.0

    compliance_penalty = 0.0
    if settlement.protocol_failure:
        compliance_penalty += 0.7
    if settlement.false_report:
        compliance_penalty += 0.4
    if settlement.terminal_status == "unsafe":
        compliance_penalty += 0.6
    if settlement.step_budget > 0:
        compliance_penalty += min(0.3, settlement.invalid_actions / settlement.step_budget)
    compliance = _clamp01(1.0 - compliance_penalty)

    primary_score = (
        0.60 * (1.0 if success else 0.0)
        + 0.15 * progress
        + 0.15 * efficiency
        + 0.10 * compliance
    )
    if settlement.protocol_failure:
        primary_score = min(primary_score, 0.02)
    elif settlement.false_report:
        primary_score = min(primary_score, 0.08)
    elif is_terminal and not settlement.report_submitted:
        primary_score = min(primary_score, 0.10)

    diagnostics = {
        "terminal_status": settlement.terminal_status,
        "terminal_reason": settlement.terminal_reason,
        "world_success": settlement.world_success,
        "primary_world_success": settlement.world_success,
        "semantic_world_success": settlement.semantic_world_success,
        "strict_world_success": settlement.strict_world_success,
        "closure_success": closure_success,
        "semantic_success": semantic_success,
        "behavior_success": behavior_success,
        "clean_success": clean_success,
        "strict_success": strict_success,
        "report_submitted": settlement.report_submitted,
        "agent_report_status": settlement.agent_report_status,
        "report_matches_world": settlement.report_matches_world,
        "protocol_failure": settlement.protocol_failure,
        "false_report": settlement.false_report,
        "budget_exhausted": settlement.budget_exhausted,
        "steps_used": settlement.steps_used,
        "step_budget": settlement.step_budget,
        "semantic_progress": semantic_progress,
        "strict_progress": strict_progress,
        "invalid_actions": settlement.invalid_actions,
        "protocol_failures": settlement.protocol_failures,
        "recoverable_failures": settlement.recoverable_failures,
        "violations": list(settlement.violations),
    }
    return EpisodeScoreSummary(
        task_family=task_family,
        success=success,
        semantic_success=semantic_success,
        behavior_success=behavior_success,
        clean_success=clean_success,
        strict_success=strict_success,
        progress=progress,
        semantic_progress=semantic_progress,
        strict_progress=strict_progress,
        efficiency=efficiency,
        compliance=compliance,
        primary_score=primary_score,
        strict_score=(1.0 if strict_success else 0.0) if strict_success is not None else None,
        diagnostics=diagnostics,
    )


def _trace_protocol_failure(trace_item: JSONDict, *, legacy: bool) -> bool:
    if legacy:
        return str(trace_item.get("failure_label") or "") == "model_protocol_error"
    judge_result = trace_item.get("judge_result")
    if isinstance(judge_result, dict):
        return bool(judge_result.get("protocol_failure"))
    return str(trace_item.get("failure_label") or "") == "model_protocol_error"


def _trace_false_report(trace_item: JSONDict) -> bool:
    report_matches_world = trace_item.get("report_matches_world")
    judge_result = trace_item.get("judge_result")
    if isinstance(judge_result, dict) and report_matches_world is None:
        report_matches_world = judge_result.get("report_matches_world")
    if report_matches_world is False:
        return True
    labels = {
        str(trace_item.get("failure_label") or "").strip().lower(),
        str(trace_item.get("terminal_reason") or "").strip().lower(),
    }
    if isinstance(judge_result, dict):
        labels.add(str(judge_result.get("failure_label") or "").strip().lower())
        labels.add(str(judge_result.get("terminal_reason") or "").strip().lower())
    return bool(labels & {"false_success_report", "false_negative_report", "report_mismatch"})


def _trace_counts_as_settlement_invalid(item: JSONDict, *, legacy: bool) -> bool:
    if legacy:
        return item.get("ok") is False and str(item.get("failure_label") or "") not in {
            "too_far",
            "interaction_no_effect",
            "out_of_bounds",
            "not_visible",
            "hand_full",
        }
    judge_result = item.get("judge_result")
    if not isinstance(judge_result, dict) or not judge_result.get("invalid_action"):
        return False
    return True


def _dual_metric_eval_value(judge_result: JSONDict, metric: str, field: str) -> Any:
    oracle_facts = judge_result.get("oracle_facts")
    if not isinstance(oracle_facts, dict):
        return None
    metric_eval = oracle_facts.get(f"{metric}_eval")
    if not isinstance(metric_eval, dict):
        return None
    return metric_eval.get(field)


def summarize_trace(*, trace: list[JSONDict], terminal_status: str | None, step_budget: int, task_family: str) -> EpisodeScoreSummary:
    resolved_terminal = str(terminal_status or "ongoing")
    legacy = bool(trace and _legacy_trace_item(trace[0]))
    judge_tail = (trace[-1].get("judge_result") or {}) if trace and not legacy else {}
    steps_used = _legacy_steps_used(trace, terminal_status) if legacy else len(trace)
    terminal_reason = None
    if resolved_terminal != "ongoing":
        terminal_reason = str(
            judge_tail.get("terminal_reason")
            or next((str(item.get("failure_label") or "") for item in reversed(trace) if item.get("failure_label")), "")
            or resolved_terminal
        )
    raw_progress = judge_tail.get("progress", 0.0) if not legacy else next((item.get("goal_progress") for item in reversed(trace) if item.get("goal_progress") is not None), 0.0)
    strict_world_success_raw = None
    strict_progress_raw = None
    if not legacy:
        strict_world_success_raw = judge_tail.get("strict_world_success")
        if strict_world_success_raw is None:
            strict_world_success_raw = _dual_metric_eval_value(judge_tail, "strict", "success")
        strict_progress_raw = judge_tail.get("strict_progress")
        if strict_progress_raw is None:
            strict_progress_raw = _dual_metric_eval_value(judge_tail, "strict", "progress")
    settlement = EpisodeSettlement(
        terminal_status=resolved_terminal,
        terminal_reason=terminal_reason or "",
        world_success=bool(
            judge_tail.get(
                "world_success",
                next(
                    (item.get("report_matches_world") for item in reversed(trace) if item.get("report_matches_world") is not None),
                    resolved_terminal == "success",
                ),
            )
        ) if legacy else bool(judge_tail.get("world_success", resolved_terminal == "success")),
        semantic_world_success=bool(
            judge_tail.get(
                "semantic_world_success",
                judge_tail.get(
                    "world_success",
                    next(
                        (item.get("report_matches_world") for item in reversed(trace) if item.get("report_matches_world") is not None),
                        resolved_terminal == "success",
                    ),
                ),
            )
        ) if legacy else bool(judge_tail.get("semantic_world_success", judge_tail.get("world_success", resolved_terminal == "success"))),
        strict_world_success=None if legacy else (bool(strict_world_success_raw) if strict_world_success_raw is not None else None),
        final_progress=float(raw_progress or 0.0),
        semantic_final_progress=float(judge_tail.get("semantic_progress", raw_progress or 0.0)) if not legacy else float(raw_progress or 0.0),
        strict_final_progress=float(strict_progress_raw) if (not legacy and strict_progress_raw is not None) else None,
        steps_used=steps_used,
        step_budget=int(step_budget or len(trace) or 1),
        report_submitted=any(
            ((item.get("runtime_action") or {}).get("executed_invocation") or {}).get("skill_name") == "report"
            or ((item.get("invocation") or {}).get("skill_name") == "report")
            or item.get("agent_report_status") is not None
            for item in trace
        ),
        agent_report_status=next((item.get("agent_report_status") for item in reversed(trace) if item.get("agent_report_status") is not None), None),
        report_matches_world=next((item.get("report_matches_world") for item in reversed(trace) if item.get("report_matches_world") is not None), None),
        invalid_actions=sum(1 for item in trace if _trace_counts_as_settlement_invalid(item, legacy=legacy) and not _trace_protocol_failure(item, legacy=legacy)),
        protocol_failures=sum(1 for item in trace if _trace_protocol_failure(item, legacy=legacy)),
        recoverable_failures=sum(
            1
            for item in trace
            if (
                (item.get("judge_result") or {}).get("recoverable")
                if not legacy
                else str(item.get("failure_label") or "") in {"too_far", "interaction_no_effect", "out_of_bounds", "not_visible", "hand_full"}
            )
        ),
        protocol_failure=any(_trace_protocol_failure(item, legacy=legacy) for item in trace),
        false_report=any(_trace_false_report(item) for item in trace),
        budget_exhausted=resolved_terminal not in {"success", "unsafe", "invalid", "ongoing"} and steps_used >= int(step_budget or 0),
        violations=[violation for item in trace for violation in list((item.get("judge_result") or {}).get("violations") or [])],
    )
    return summarize_episode(settlement=settlement, task_family=task_family)


def _task_family(trace: EpisodeTrace) -> str:
    metadata = dict(trace.metadata or {})
    return str(metadata.get("task_family") or metadata.get("family") or "unknown")


def _reference_trace_from_release_trace(trace: EpisodeTrace) -> list[JSONDict]:
    reference_trace: list[JSONDict] = []
    for step in trace.steps:
        metadata = dict(step.metadata or {})
        judge_result = dict(metadata.get("judge_result") or {})
        env_result = dict(metadata.get("env_result") or {})
        action_payload = step.action.to_dict() if step.action is not None else None
        runtime_action: JSONDict = {}
        if action_payload is not None:
            runtime_action["executed_invocation"] = action_payload
        agent_turn = dict(metadata.get("agent_turn") or {})
        agent_diagnostics: JSONDict = {}
        if agent_turn.get("usage") is not None:
            agent_diagnostics["model_usage"] = agent_turn.get("usage")
        if agent_turn.get("sanitation") is not None:
            agent_diagnostics["sanitation"] = agent_turn.get("sanitation")

        report_status = metadata.get("agent_report_status")
        if report_status is None:
            report_status = judge_result.get("report_status")
        report_matches_world = metadata.get("report_matches_world")
        if report_matches_world is None:
            report_matches_world = judge_result.get("report_matches_world")

        item: JSONDict = {
            "step": int(step.step_index) + 1,
            "ok": bool(step.action_valid),
            "action_valid": bool(step.action_valid and step.action is not None),
            "runtime_action": runtime_action,
            "env_result": env_result,
            "judge_result": judge_result,
            "goal_progress": float(step.progress or 0.0),
            "terminal_status": trace.terminal_status if step.terminal else None,
            "failure_label": judge_result.get("failure_label") or step.error_type,
            "failure_type": judge_result.get("failure_type") or judge_result.get("failure_label") or step.error_type,
            "agent_report_status": report_status,
            "reported_status": report_status,
            "report_matches_world": report_matches_world,
            "oracle_terminal_status": "success" if bool(judge_result.get("world_success", step.judge_success)) else "fail",
        }
        if agent_diagnostics:
            item["agent_diagnostics"] = agent_diagnostics
        reference_trace.append(item)
    return reference_trace


def score_episode(trace: EpisodeTrace) -> EpisodeScore:
    settlement = settle_trace(trace)
    task_family = _task_family(trace)
    summary = summarize_episode(settlement=settlement, task_family=task_family)
    summary_dict = summary.to_dict()
    steps_taken = len(trace.steps)
    valid_steps = sum(1 for step in trace.steps if step.action_valid and step.action is not None)
    action_validity = valid_steps / steps_taken if steps_taken else 0.0
    return EpisodeScore(
        episode_id=trace.episode_id,
        success=summary.success,
        episode_score=summary.primary_score,
        progress_score=summary.progress,
        action_validity=action_validity,
        efficiency=summary.efficiency,
        steps_taken=settlement.steps_used,
        max_steps=settlement.step_budget,
        terminal_status=settlement.terminal_status,
        primary_score=summary.primary_score,
        task_family=task_family,
        difficulty=str((trace.metadata or {}).get("difficulty") or "unknown"),
        semantic_success=summary.semantic_success,
        behavior_success=summary.behavior_success,
        clean_success=summary.clean_success,
        strict_success=summary.strict_success,
        compliance=summary.compliance,
        terminal_reason=settlement.terminal_reason,
        score_summary=summary_dict,
        settlement=settlement.to_dict(),
        result_metadata={
            key: value
            for key, value in dict(trace.metadata or {}).items()
            if key != "settlement"
        } | {"trace": _reference_trace_from_release_trace(trace)},
    )


def settlement_from_dict(payload: JSONDict) -> EpisodeSettlement:
    return EpisodeSettlement(
        terminal_status=str(payload.get("terminal_status") or "failure"),
        terminal_reason=str(payload.get("terminal_reason") or "terminal_without_reason"),
        world_success=bool(payload.get("world_success")),
        semantic_world_success=bool(payload.get("semantic_world_success")),
        strict_world_success=payload.get("strict_world_success"),
        final_progress=_clamp01(float(payload.get("final_progress", 0.0) or 0.0)),
        semantic_final_progress=_clamp01(float(payload.get("semantic_final_progress", payload.get("final_progress", 0.0)) or 0.0)),
        strict_final_progress=(
            None
            if payload.get("strict_final_progress") is None
            else _clamp01(float(payload.get("strict_final_progress") or 0.0))
        ),
        steps_used=int(payload.get("steps_used", 0) or 0),
        step_budget=int(payload.get("step_budget", payload.get("max_steps", 1)) or 1),
        report_submitted=bool(payload.get("report_submitted")),
        agent_report_status=payload.get("agent_report_status"),
        report_matches_world=payload.get("report_matches_world"),
        invalid_actions=int(payload.get("invalid_actions", 0) or 0),
        protocol_failures=int(payload.get("protocol_failures", 0) or 0),
        recoverable_failures=int(payload.get("recoverable_failures", 0) or 0),
        protocol_failure=bool(payload.get("protocol_failure")),
        false_report=bool(payload.get("false_report")),
        budget_exhausted=bool(payload.get("budget_exhausted")),
        violations=[dict(item) for item in list(payload.get("violations") or []) if isinstance(item, dict)],
    )


def _reference_action_validity(result: JSONDict, settlement: EpisodeSettlement) -> float:
    trace = list(result.get("trace") or [])
    if trace:
        invalid = 0
        for item in trace:
            judge = dict((item or {}).get("judge_result") or {})
            if item.get("action_valid") is False or bool(judge.get("invalid_action")) or bool(judge.get("protocol_failure")):
                invalid += 1
        return max(0.0, min(1.0, (len(trace) - invalid) / len(trace)))
    steps = max(1, int(settlement.steps_used or 1))
    invalid = settlement.invalid_actions + settlement.protocol_failures
    return max(0.0, min(1.0, (steps - invalid) / steps))


def score_result_payload(result: JSONDict) -> EpisodeScore:
    settlement_payload = dict(result.get("settlement") or {})
    if not settlement_payload:
        raise ValueError("Reference result must contain a settlement object for rescoring.")
    settlement = settlement_from_dict(settlement_payload)
    task_family = str(result.get("task_family") or (result.get("score_summary") or {}).get("task_family") or "unknown")
    summary = summarize_episode(settlement=settlement, task_family=task_family)
    summary_dict = summary.to_dict()
    reference_summary = result.get("score_summary")
    if isinstance(reference_summary, dict) and reference_summary.get("task_family"):
        summary_dict["task_family"] = str(reference_summary["task_family"])
    return EpisodeScore(
        episode_id=str(result.get("episode_id") or ""),
        success=summary.success,
        episode_score=summary.primary_score,
        progress_score=summary.progress,
        action_validity=_reference_action_validity(result, settlement),
        efficiency=summary.efficiency,
        steps_taken=settlement.steps_used,
        max_steps=settlement.step_budget,
        terminal_status=settlement.terminal_status,
        primary_score=summary.primary_score,
        task_family=task_family,
        difficulty=str(result.get("difficulty") or "unknown"),
        semantic_success=summary.semantic_success,
        behavior_success=summary.behavior_success,
        clean_success=summary.clean_success,
        strict_success=summary.strict_success,
        compliance=summary.compliance,
        terminal_reason=settlement.terminal_reason,
        score_summary=summary_dict,
        settlement=settlement.to_dict(),
        result_metadata={
            key: value
            for key, value in result.items()
            if key
            not in {
                "episode_id",
                "status",
                "terminal_status",
                "terminal_reason",
                "steps_used",
                "task_family",
                "difficulty",
                "score_summary",
                "settlement",
            }
        },
    )


def _diagnostics(score: EpisodeScore) -> JSONDict:
    return dict((score.score_summary or {}).get("diagnostics") or {})


def _score_world_success(score: EpisodeScore) -> bool:
    diagnostics = _diagnostics(score)
    return bool(diagnostics.get("primary_world_success", diagnostics.get("world_success")))


def _score_semantic_world_success(score: EpisodeScore) -> bool:
    return bool(_diagnostics(score).get("semantic_world_success"))


def _score_behavior_success(score: EpisodeScore) -> bool:
    summary = dict(score.score_summary or {})
    if summary.get("behavior_success") is not None:
        return bool(summary.get("behavior_success"))
    return bool(score.semantic_success and not _diagnostics(score).get("protocol_failure"))


def _score_clean_success(score: EpisodeScore) -> bool:
    summary = dict(score.score_summary or {})
    if summary.get("clean_success") is not None:
        return bool(summary.get("clean_success"))
    return bool(_score_behavior_success(score) and int(_diagnostics(score).get("invalid_actions") or 0) == 0)


def _score_strict_world_success(score: EpisodeScore) -> bool | None:
    value = _diagnostics(score).get("strict_world_success")
    return None if value is None else bool(value)


def _score_closure_success(score: EpisodeScore) -> bool:
    diagnostics = _diagnostics(score)
    return bool(diagnostics.get("closure_success", diagnostics.get("terminal_status") == "success"))


def _score_honest_fail_report(score: EpisodeScore) -> bool:
    diagnostics = _diagnostics(score)
    return bool(
        diagnostics.get("report_submitted")
        and str(diagnostics.get("agent_report_status") or "").strip().lower() == "fail"
        and diagnostics.get("report_matches_world") is True
    )


def _score_false_negative_report(score: EpisodeScore) -> bool:
    return str(_diagnostics(score).get("terminal_reason") or "").strip().lower() == "false_negative_report"


def _bucket_summary(scores: list[EpisodeScore]) -> JSONDict:
    if not scores:
        return {}
    strict_success_values = [None if score.strict_success is None else (1.0 if score.strict_success else 0.0) for score in scores]
    strict_world_values = [_score_strict_world_success(score) for score in scores]
    primary_world_ok_count = sum(1 for score in scores if _score_world_success(score))
    closure_success = [1.0 if _score_closure_success(score) else 0.0 for score in scores]
    return {
        "episode_count": len(scores),
        "mean_primary_score": _safe_mean([score.primary_score for score in scores]),
        "mean_progress": _safe_mean([score.progress_score for score in scores]),
        "success_rate": _safe_mean([1.0 if score.success else 0.0 for score in scores]),
        "semantic_success_rate": _safe_mean([1.0 if score.semantic_success else 0.0 for score in scores]),
        "behavior_success_rate": _safe_mean([1.0 if _score_behavior_success(score) else 0.0 for score in scores]),
        "clean_success_rate": _safe_mean([1.0 if _score_clean_success(score) else 0.0 for score in scores]),
        "strict_success_rate": _safe_mean_optional(strict_success_values),
        "closure_success_rate": _safe_mean(closure_success),
        "world_success_rate": _safe_mean([1.0 if _score_world_success(score) else 0.0 for score in scores]),
        "primary_world_success_rate": _safe_mean([1.0 if _score_world_success(score) else 0.0 for score in scores]),
        "semantic_world_success_rate": _safe_mean([1.0 if _score_semantic_world_success(score) else 0.0 for score in scores]),
        "strict_world_success_rate": _safe_mean_optional([None if value is None else (1.0 if value else 0.0) for value in strict_world_values]),
        "closure_given_world_rate": (sum(closure_success) / primary_world_ok_count if primary_world_ok_count else None),
        "report_rate": _safe_mean([1.0 if bool(_diagnostics(score).get("report_submitted")) else 0.0 for score in scores]),
        "false_report_rate": _safe_mean([1.0 if bool(_diagnostics(score).get("false_report")) else 0.0 for score in scores]),
        "honest_fail_report_rate": _safe_mean([1.0 if _score_honest_fail_report(score) else 0.0 for score in scores]),
        "false_negative_report_rate": _safe_mean([1.0 if _score_false_negative_report(score) else 0.0 for score in scores]),
        "fail_no_report_rate": _safe_mean([1.0 if str(_diagnostics(score).get("terminal_reason") or "") == "fail_no_report" else 0.0 for score in scores]),
        "invalid_action_limit_rate": _safe_mean([1.0 if str(_diagnostics(score).get("terminal_reason") or "") == "invalid_action_limit_exceeded" else 0.0 for score in scores]),
        "world_success_without_report_rate": _safe_mean([1.0 if (_score_world_success(score) and not bool(_diagnostics(score).get("report_submitted"))) else 0.0 for score in scores]),
        "mean_steps_used": _safe_mean([float(score.steps_taken) for score in scores]),
    }


def _diagnostic_rates(scores: tuple[EpisodeScore, ...]) -> JSONDict:
    if not scores:
        return {}
    return {
        "fail_no_report": _safe_mean([1.0 if str(_diagnostics(score).get("terminal_reason") or "") == "fail_no_report" else 0.0 for score in scores]),
        "invalid_action_limit_exceeded": _safe_mean([1.0 if str(_diagnostics(score).get("terminal_reason") or "") == "invalid_action_limit_exceeded" else 0.0 for score in scores]),
        "world_success_without_report": _safe_mean([1.0 if (_score_world_success(score) and not bool(_diagnostics(score).get("report_submitted"))) else 0.0 for score in scores]),
        "protocol_failure": _safe_mean([1.0 if bool(_diagnostics(score).get("protocol_failure")) else 0.0 for score in scores]),
        "false_report": _safe_mean([1.0 if bool(_diagnostics(score).get("false_report")) else 0.0 for score in scores]),
        "honest_fail_report": _safe_mean([1.0 if _score_honest_fail_report(score) else 0.0 for score in scores]),
        "false_negative_report": _safe_mean([1.0 if _score_false_negative_report(score) else 0.0 for score in scores]),
    }


def aggregate_scores(scores: list[EpisodeScore] | tuple[EpisodeScore, ...]) -> AggregateScore:
    if not scores:
        raise ValueError("Cannot score an empty collection.")
    scores = tuple(scores)
    strict_success_values = [None if score.strict_success is None else (1.0 if score.strict_success else 0.0) for score in scores]
    strict_world_values = []
    terminal_histogram: dict[str, int] = {}
    by_family: dict[str, list[EpisodeScore]] = {}
    by_difficulty: dict[str, list[EpisodeScore]] = {}
    for score in scores:
        terminal_histogram[score.terminal_status] = terminal_histogram.get(score.terminal_status, 0) + 1
        by_family.setdefault(score.task_family, []).append(score)
        by_difficulty.setdefault(score.difficulty or "unknown", []).append(score)
        strict_world = _score_strict_world_success(score)
        if strict_world is not None:
            strict_world_values.append(1.0 if bool(strict_world) else 0.0)
    primary_world_ok_count = sum(1 for score in scores if _score_world_success(score))
    closure_success_values = [1.0 if _score_closure_success(score) else 0.0 for score in scores]
    return AggregateScore(
        episode_count=len(scores),
        success_rate=_safe_mean([1.0 if score.success else 0.0 for score in scores]),
        behavior_success_rate=_safe_mean([1.0 if _score_behavior_success(score) else 0.0 for score in scores]),
        clean_success_rate=_safe_mean([1.0 if _score_clean_success(score) else 0.0 for score in scores]),
        mean_episode_score=_safe_mean([score.episode_score for score in scores]),
        mean_progress_score=_safe_mean([score.progress_score for score in scores]),
        mean_action_validity=_safe_mean([score.action_validity for score in scores]),
        mean_efficiency=_safe_mean([score.efficiency for score in scores]),
        scores=scores,
        mean_primary_score=_safe_mean([score.primary_score for score in scores]),
        semantic_success_rate=_safe_mean([1.0 if score.semantic_success else 0.0 for score in scores]),
        strict_success_rate=_safe_mean_optional(strict_success_values),
        closure_success_rate=_safe_mean(closure_success_values),
        world_success_rate=_safe_mean([1.0 if _score_world_success(score) else 0.0 for score in scores]),
        primary_world_success_rate=_safe_mean([1.0 if _score_world_success(score) else 0.0 for score in scores]),
        semantic_world_success_rate=_safe_mean([1.0 if _score_semantic_world_success(score) else 0.0 for score in scores]),
        strict_world_success_rate=_safe_mean(strict_world_values) if strict_world_values else None,
        closure_given_world_rate=(sum(closure_success_values) / primary_world_ok_count if primary_world_ok_count else None),
        mean_steps_used=_safe_mean([float(score.steps_taken) for score in scores]),
        terminal_status_histogram=dict(sorted(terminal_histogram.items())),
        diagnostic_rates=_diagnostic_rates(scores),
        by_task_family={family: _bucket_summary(items) for family, items in sorted(by_family.items())},
        by_difficulty={difficulty: _bucket_summary(items) for difficulty, items in sorted(by_difficulty.items())},
    )


def score_episodes(traces: list[EpisodeTrace] | tuple[EpisodeTrace, ...]) -> AggregateScore:
    if not traces:
        raise ValueError("Cannot score an empty trace collection.")
    return aggregate_scores([score_episode(trace) for trace in traces])


def score_result_payloads(results: list[JSONDict] | tuple[JSONDict, ...]) -> AggregateScore:
    if not results:
        raise ValueError("Cannot score an empty result collection.")
    return aggregate_scores([score_result_payload(result) for result in results])
