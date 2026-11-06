from __future__ import annotations

from typing import Any

JSONDict = dict[str, Any]


def _score_summary(item: JSONDict) -> JSONDict:
    return dict(item.get("score_summary") or {})


def _diagnostics(item: JSONDict) -> JSONDict:
    return dict(_score_summary(item).get("diagnostics") or {})


def _settlement(item: JSONDict) -> JSONDict:
    return dict(item.get("settlement") or {})


def resolved_terminal_status(item: JSONDict) -> str | None:
    settlement = _settlement(item)
    if settlement.get("terminal_status") is not None:
        return str(settlement.get("terminal_status") or "").strip() or None
    score_summary = _score_summary(item)
    if score_summary.get("terminal_status") is not None:
        return str(score_summary.get("terminal_status") or "").strip() or None
    diagnostics = _diagnostics(item)
    if diagnostics.get("terminal_status") is not None:
        return str(diagnostics.get("terminal_status") or "").strip() or None
    if item.get("terminal_status") is not None:
        return str(item.get("terminal_status") or "").strip() or None
    if item.get("status") is not None:
        return str(item.get("status") or "").strip() or None
    return None


def resolved_terminal_reason(item: JSONDict) -> str | None:
    settlement = _settlement(item)
    if settlement.get("terminal_reason") is not None:
        return str(settlement.get("terminal_reason") or "").strip() or None
    score_summary = _score_summary(item)
    if score_summary.get("terminal_reason") is not None:
        return str(score_summary.get("terminal_reason") or "").strip() or None
    diagnostics = _diagnostics(item)
    if diagnostics.get("terminal_reason") is not None:
        return str(diagnostics.get("terminal_reason") or "").strip() or None
    if item.get("terminal_reason") is not None:
        return str(item.get("terminal_reason") or "").strip() or None
    return None


def resolved_failure_label(item: JSONDict) -> str | None:
    if item.get("failure_label") is not None:
        return str(item.get("failure_label") or "").strip() or None
    if item.get("failure_type") is not None:
        return str(item.get("failure_type") or "").strip() or None
    judge_result = dict(item.get("judge_result") or {})
    if judge_result.get("failure_label") is not None:
        return str(judge_result.get("failure_label") or "").strip() or None
    if judge_result.get("failure_type") is not None:
        return str(judge_result.get("failure_type") or "").strip() or None
    settlement = _settlement(item)
    if settlement.get("terminal_reason") is not None:
        return str(settlement.get("terminal_reason") or "").strip() or None
    diagnostics = _diagnostics(item)
    if diagnostics.get("terminal_reason") is not None:
        return str(diagnostics.get("terminal_reason") or "").strip() or None
    for trace_item in reversed(list(item.get("trace") or [])):
        label = resolved_failure_label(dict(trace_item or {}))
        if label is not None:
            return label
    return None


def score_summary_with_contract(score_summary: JSONDict, settlement: JSONDict | None = None) -> JSONDict:
    payload = dict(score_summary or {})
    diagnostics = dict(payload.get("diagnostics") or {})
    settlement_payload = dict(settlement or {})
    terminal_status = (
        settlement_payload.get("terminal_status")
        if settlement_payload.get("terminal_status") is not None
        else diagnostics.get("terminal_status")
    )
    terminal_reason = (
        settlement_payload.get("terminal_reason")
        if settlement_payload.get("terminal_reason") is not None
        else diagnostics.get("terminal_reason")
    )
    payload["diagnostics"] = diagnostics
    payload["terminal_status"] = terminal_status
    payload["terminal_reason"] = terminal_reason
    return payload
