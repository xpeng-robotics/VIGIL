from __future__ import annotations

from typing import Any

from vigil.eval.traces import EpisodeTrace, StepTrace, validate_step_evidence
from vigil.eval.types import EpisodeSettlement
from vigil.eval.judge import RECOVERABLE_FAILURE_LABELS, settle_report_outcome

JSONDict = dict[str, Any]

_REPORT_STATUSES = {"success", "fail", "unsafe", "invalid", "on", "off", "open", "closed"}
_SUCCESS_TERMINALS = {"success", "completed", "done"}
_FAILURE_TERMINALS = {"failure", "failed", "timeout", "invalid_action", "protocol_error", "stopped"}


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_report_status(status: Any) -> str | None:
    normalized = str(status or "").strip().lower()
    if normalized in _REPORT_STATUSES:
        return normalized
    return None


def _last_report_step(trace: EpisodeTrace) -> StepTrace | None:
    for step in reversed(trace.steps):
        judge = step.metadata.get("judge_result") or {}
        if (step.action is not None and step.action.skill_name in {"report", "ReportDone"}
                and not _step_is_protocol_failure(step) and judge.get("report_submitted") is not False):
            return step
    return None


def _report_status(step: StepTrace | None) -> str | None:
    if step is None or step.action is None:
        return None
    args = dict(step.action.arguments or {})
    for key in ("status", "answer", "state", "value", "result"):
        if args.get(key) is not None:
            return _normalize_report_status(args.get(key)) or str(args.get(key) or "").strip().lower() or None
    return None


def _report_expected_status(step: StepTrace | None) -> str | None:
    if step is None:
        return None
    metadata = dict(step.metadata or {})
    candidates: list[Any] = []
    candidates.append(metadata.get("expected_report_status"))
    env_result = metadata.get("env_result")
    if isinstance(env_result, dict):
        diagnostics = env_result.get("diagnostics")
        if isinstance(diagnostics, dict):
            candidates.extend([diagnostics.get("expected_report_status"), diagnostics.get("expected_status")])
    for candidate in candidates:
        if candidate is None:
            continue
        return _normalize_report_status(candidate) or str(candidate or "").strip().lower() or None
    return None


def _step_is_protocol_failure(step: StepTrace) -> bool:
    label = str(step.error_type or "").strip().lower()
    return bool((step.metadata.get("judge_result") or {}).get("protocol_failure")) or step.env_status == "protocol_error" or label in {"parse_error", "model_protocol_error"}


def _step_is_recoverable_failure(step: StepTrace) -> bool:
    label = str(step.error_type or "").strip().lower()
    judge = step.metadata.get("judge_result") or {}
    return bool(judge["recoverable"]) if "recoverable" in judge else label in RECOVERABLE_FAILURE_LABELS


def _step_invalid(step: StepTrace) -> bool:
    return bool(not step.action_valid and not _step_is_recoverable_failure(step))


def _trace_terminal_status(trace: EpisodeTrace, *, world_success: bool, report_step: StepTrace | None) -> tuple[str, str, str | None, bool | None, bool]:
    raw_terminal = str(trace.terminal_status or "").strip().lower()
    report_status = _report_status(report_step)
    expected_status = _report_expected_status(report_step)
    if report_step is not None:
        report_info = settle_report_outcome(str(report_status or ""), world_success=world_success, expected_status=expected_status)
        return (
            str(report_info["terminal_status"]),
            str(report_info["terminal_reason"]),
            report_status,
            bool(report_info["report_matches_world"]),
            bool(not report_info["report_matches_world"]),
        )
    final_judge = (trace.steps[-1].metadata.get("judge_result") or {}) if trace.steps else {}
    if final_judge.get("status") not in {None, "", "ongoing"}:
        status = str(final_judge["status"])
        return status, str(final_judge.get("terminal_reason") or status), None, None, False
    if trace.steps and trace.steps[-1].env_status == "simulator_error":
        return "failure", "simulator_error", None, None, False
    if not final_judge and any(_step_is_protocol_failure(step) for step in trace.steps):
        return "invalid", "model_protocol_error", None, None, False
    if raw_terminal in _SUCCESS_TERMINALS:
        return "failure", "fail_no_report", None, None, False
    if raw_terminal in _FAILURE_TERMINALS or not raw_terminal:
        return "failure", "fail_no_report", None, None, False
    return raw_terminal, raw_terminal, None, None, False


def _settlement_from_metadata(trace: EpisodeTrace) -> EpisodeSettlement | None:
    payload = dict((trace.metadata or {}).get("settlement") or {})
    if not payload:
        return None
    try:
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
            steps_used=int(payload.get("steps_used", len(trace.steps)) or len(trace.steps)),
            step_budget=int(payload.get("step_budget", trace.max_steps) or trace.max_steps),
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
    except Exception:
        return None


def settle_trace(trace: EpisodeTrace) -> EpisodeSettlement:
    for step in trace.steps:
        validate_step_evidence(step)
    for step in trace.steps[:-1]:
        if step.terminal:
            raise ValueError(f"Trace continues after a terminal step: {trace.episode_id}")
    cached = _settlement_from_metadata(trace)
    steps_used = len(trace.steps)
    step_budget = int(trace.max_steps or max(steps_used, 1))
    report_step = _last_report_step(trace)
    if report_step is not None and report_step is not trace.steps[-1]:
        raise ValueError(f"Trace continues after a report: {trace.episode_id}")
    # Paper W is the final state, not a goal reached earlier or a terminal label.
    last_step = trace.steps[-1] if trace.steps else None
    judge = dict((last_step.metadata or {}).get("judge_result") or {}) if last_step else {}
    world_success = bool(judge.get("world_success", last_step.judge_success if last_step else False))
    semantic_world_success = bool(judge.get("semantic_world_success", world_success))
    strict_world_success = judge.get("strict_world_success")
    final_progress = float(judge.get("progress", last_step.progress if last_step else 0.0) or 0.0)
    terminal_status, terminal_reason, agent_report_status, report_matches_world, false_report = _trace_terminal_status(
        trace,
        world_success=world_success,
        report_step=report_step,
    )
    invalid_actions = sum(1 for step in trace.steps if _step_invalid(step) and not _step_is_protocol_failure(step))
    protocol_failures = sum(1 for step in trace.steps if _step_is_protocol_failure(step))
    recoverable_failures = sum(1 for step in trace.steps if _step_is_recoverable_failure(step))
    protocol_failure = protocol_failures > 0
    budget_exhausted = terminal_status == "failure" and terminal_reason == "fail_no_report" and steps_used >= step_budget
    inferred = EpisodeSettlement(
        terminal_status=terminal_status,
        terminal_reason=terminal_reason,
        world_success=world_success,
        semantic_world_success=semantic_world_success,
        strict_world_success=bool(strict_world_success) if strict_world_success is not None else None,
        final_progress=_clamp01(final_progress),
        semantic_final_progress=_clamp01(float(judge.get("semantic_progress", final_progress) or 0.0)),
        strict_final_progress=_clamp01(float(judge["strict_progress"])) if judge.get("strict_progress") is not None else None,
        steps_used=steps_used,
        step_budget=step_budget,
        report_submitted=report_step is not None,
        agent_report_status=agent_report_status,
        report_matches_world=report_matches_world,
        invalid_actions=invalid_actions,
        protocol_failures=protocol_failures,
        recoverable_failures=recoverable_failures,
        protocol_failure=protocol_failure,
        false_report=false_report,
        budget_exhausted=budget_exhausted,
        violations=[],
    )

    # A cached settlement is a runtime record, not independent scoring evidence.
    # Cross-check every field supported by the trace before using the record.
    expected = inferred.to_dict()
    fields = {
        "world_success", "semantic_world_success", "strict_world_success",
        "steps_used", "step_budget", "report_submitted", "agent_report_status",
        "report_matches_world", "terminal_status", "terminal_reason",
        "protocol_failure", "protocol_failures", "false_report", "budget_exhausted",
    }
    judges = [step.metadata.get("judge_result") or {} for step in trace.steps]
    if judges and all("invalid_action" in judge for judge in judges):
        expected["invalid_actions"] = sum(bool(j["invalid_action"]) and not bool(j.get("protocol_failure")) for j in judges)
        fields.add("invalid_actions")
    if judges and all("recoverable" in judge for judge in judges):
        fields.add("recoverable_failures")
    if judges and all("violations" in judge for judge in judges):
        violations = []
        for judge in judges:
            if judge.get("terminal_reason") == "invalid_action_limit_exceeded":
                violations = list(judge["violations"])
            else:
                violations.extend(judge["violations"])
        expected["violations"] = violations
        fields.add("violations")
    for field, source in (("final_progress", "progress"), ("semantic_final_progress", "semantic_progress"), ("strict_final_progress", "strict_progress")):
        if judges and all(source in j for j in judges):
            values = [j[source] for j in judges if j[source] is not None]
            expected[field] = max(values) if values else None
            fields.add(field)
    if cached is None:
        if (trace.metadata or {}).get("settlement"):
            raise ValueError(f"Malformed cached settlement for {trace.episode_id}.")
        return EpisodeSettlement(**expected)
    payload = trace.metadata["settlement"]
    mismatches = sorted(key for key in fields if key not in payload or payload[key] != expected[key]
                        or (isinstance(expected[key], bool) and type(payload[key]) is not bool))
    if mismatches:
        raise ValueError(f"Settlement disagrees with step evidence for {trace.episode_id}: {', '.join(mismatches)}")
    return cached
