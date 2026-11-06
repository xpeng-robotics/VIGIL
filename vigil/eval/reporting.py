"""Readable summaries of the existing trace scorer's output."""
from __future__ import annotations

import math


def validate_stored_summary(payload: dict) -> None:
    """Check display fields only; a standalone summary cannot verify its evidence."""
    if not isinstance(payload, dict):
        raise ValueError("Expected an aggregate JSON object.")
    count = payload.get("episode_count")
    if type(count) is not int or count <= 0:
        raise ValueError("Stored summary must have a positive integer episode_count.")
    if any(payload.get(key) for key in ("error_count", "errors", "infrastructure_errors", "skipped_missing")):
        raise ValueError("Stored summary contains infrastructure errors or missing episodes.")
    if "overall_episode_count" in payload and (
        type(payload["overall_episode_count"]) is not int or payload["overall_episode_count"] != count
    ):
        raise ValueError("Stored summary episode counts disagree.")

    def check_rate(value):
        if type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value):
            raise ValueError("Stored summary rates must be finite numbers between 0 and 1.")

    for key in ("world_success_rate", "success_rate"):
        check_rate(payload.get(key))
    rates = payload.get("diagnostic_rates", {})
    if not isinstance(rates, dict):
        raise ValueError("Stored summary diagnostic_rates must be an object.")
    for value in rates.values():
        if value is not None:
            check_rate(value)
    histogram = payload.get("terminal_status_histogram", {})
    if not isinstance(histogram, dict) or any(type(n) is not int or n < 0 for n in histogram.values()):
        raise ValueError("Stored summary terminal counts must be nonnegative integers.")
    if histogram and sum(histogram.values()) != count:
        raise ValueError("Stored summary terminal counts differ from episode_count.")
    selections = []
    for key in ("results", "scores"):
        if key not in payload:
            continue
        rows = payload[key]
        if not isinstance(rows, list) or len(rows) != count:
            raise ValueError(f"Stored summary {key} count differs from episode_count.")
        ids = [row.get("episode_id") if isinstance(row, dict) else None for row in rows]
        if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != count:
            raise ValueError(f"Stored summary {key} contains invalid or duplicate episode IDs.")
        selections.append(set(ids))
    if len(selections) == 2 and selections[0] != selections[1]:
        raise ValueError("Stored summary results and scores select different episodes.")


def format_report(payload: dict) -> str:
    def percent(value):
        return "n/a" if value is None else f"{100 * value:.1f}%"

    lines = [
        f"Episodes: {payload['episode_count']}",
        f"World completion W: {percent(payload.get('world_success_rate'))}",
        f"Benchmark success B: {percent(payload.get('success_rate'))}",
        "W is final world completion; B also requires a matching terminal report.",
    ]
    histogram = payload.get("terminal_status_histogram") or {}
    if histogram:
        lines.append("Terminal status: " + ", ".join(f"{key}={count}" for key, count in sorted(histogram.items())))
    rates = payload.get("diagnostic_rates") or {}
    if rates:
        lines.append("Diagnostics: " + ", ".join(f"{key}={percent(value)}" for key, value in sorted(rates.items()) if isinstance(value, (int, float))))
    return "\n".join(lines)
