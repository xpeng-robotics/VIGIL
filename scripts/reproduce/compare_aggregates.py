#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

JSONDict = dict[str, Any]
INTERNAL_TOP_LEVEL_KEYS = (
    "episode_count",
    "mean_primary_score",
    "success_rate",
    "semantic_success_rate",
    "strict_success_rate",
    "closure_success_rate",
    "world_success_rate",
    "primary_world_success_rate",
    "semantic_world_success_rate",
    "strict_world_success_rate",
    "closure_given_world_rate",
    "mean_steps_used",
    "behavior_success_rate",
    "clean_success_rate",
    "mean_episode_score",
    "mean_progress_score",
    "mean_action_validity",
    "mean_efficiency",
)
LEGACY_TOP_LEVEL_KEYS = (
    "episode_count",
    "success_rate",
    "mean_episode_score",
    "mean_progress_score",
    "mean_action_validity",
    "mean_efficiency",
)
INTERNAL_SCORE_KEYS = (
    "task_family",
    "success",
    "semantic_success",
    "strict_success",
    "progress",
    "semantic_progress",
    "strict_progress",
    "efficiency",
    "compliance",
    "primary_score",
    "strict_score",
    "terminal_status",
    "terminal_reason",
)
INTERNAL_DIAGNOSTIC_KEYS = (
    "terminal_status",
    "terminal_reason",
    "world_success",
    "primary_world_success",
    "semantic_world_success",
    "strict_world_success",
    "closure_success",
    "semantic_success",
    "strict_success",
    "report_submitted",
    "agent_report_status",
    "report_matches_world",
    "protocol_failure",
    "false_report",
    "budget_exhausted",
    "steps_used",
    "step_budget",
    "semantic_progress",
    "strict_progress",
    "invalid_actions",
    "protocol_failures",
    "recoverable_failures",
)
DIAGNOSTIC_RATE_KEYS = (
    "fail_no_report",
    "invalid_action_limit_exceeded",
    "world_success_without_report",
    "protocol_failure",
    "false_report",
    "honest_fail_report",
    "false_negative_report",
)
REFERENCE_RECURSIVE_TOP_KEYS = (
    "diagnostic_rates",
    "requirement_attribution_distribution",
    "no_report_analysis",
    "behavior_metrics_summary",
    "harness_assistance_summary",
    "overall_diagnostic_rates",
    "overall_attribution_distribution",
    "overall_no_report_analysis",
    "overall_harness_assistance_summary",
    "by_task_family",
    "by_capability_bucket",
    "by_functional_template",
    "by_target_group",
    "by_difficulty",
)
BUCKET_SCORE_KEYS = (
    "episode_count",
    "mean_primary_score",
    "mean_progress",
    "success_rate",
    "semantic_success_rate",
    "strict_success_rate",
    "closure_success_rate",
    "world_success_rate",
    "primary_world_success_rate",
    "semantic_world_success_rate",
    "strict_world_success_rate",
    "closure_given_world_rate",
    "report_rate",
    "false_report_rate",
    "honest_fail_report_rate",
    "false_negative_report_rate",
    "fail_no_report_rate",
    "invalid_action_limit_rate",
    "world_success_without_report_rate",
    "mean_steps_used",
)
LEGACY_SCORE_KEYS = (
    "success",
    "episode_score",
    "progress_score",
    "action_validity",
    "efficiency",
    "steps_taken",
    "max_steps",
    "terminal_status",
)


def load_json(path: Path) -> JSONDict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def values_match(expected: Any, actual: Any, *, tolerance: float) -> bool:
    expected_float = as_float(expected)
    actual_float = as_float(actual)
    if expected_float is not None or actual_float is not None:
        if expected_float is None or actual_float is None:
            return False
        return (math.isfinite(expected_float) and math.isfinite(actual_float)
                and math.isclose(expected_float, actual_float, rel_tol=0.0, abs_tol=tolerance))
    return expected == actual


def scalar_dict_diff(prefix: str, expected: JSONDict, actual: JSONDict, keys: tuple[str, ...], *, tolerance: float) -> list[str]:
    diffs: list[str] = []
    for key in keys:
        if key not in expected:
            continue
        if not values_match(expected.get(key), actual.get(key), tolerance=tolerance):
            diffs.append(f"{prefix}.{key}: expected={expected.get(key)!r} actual={actual.get(key)!r}")
    return diffs


def nested_scalar_map_diff(prefix: str, expected: Any, actual: Any, keys: tuple[str, ...], *, tolerance: float) -> list[str]:
    if not isinstance(expected, dict):
        return [f"{prefix}: expected must be an object"]
    if not isinstance(actual, dict):
        return [f"{prefix}: actual must be an object"]

    diffs: list[str] = []
    for bucket_name, expected_bucket in sorted(expected.items()):
        if bucket_name not in actual:
            diffs.append(f"{prefix}.{bucket_name}: missing from actual")
            continue
        actual_bucket = actual.get(bucket_name)
        if not isinstance(expected_bucket, dict) or not isinstance(actual_bucket, dict):
            if expected_bucket != actual_bucket:
                diffs.append(f"{prefix}.{bucket_name}: expected={expected_bucket!r} actual={actual_bucket!r}")
            continue
        diffs.extend(
            scalar_dict_diff(
                f"{prefix}.{bucket_name}",
                expected_bucket,
                actual_bucket,
                keys,
                tolerance=tolerance,
            )
        )
    return diffs


def recursive_reference_diff(prefix: str, expected: Any, actual: Any, *, tolerance: float) -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{prefix}: expected object actual={type(actual).__name__}"]
        diffs: list[str] = []
        for key, expected_value in sorted(expected.items()):
            if key not in actual:
                diffs.append(f"{prefix}.{key}: missing from actual")
                continue
            diffs.extend(
                recursive_reference_diff(
                    f"{prefix}.{key}",
                    expected_value,
                    actual.get(key),
                    tolerance=tolerance,
                )
            )
        return diffs
    if isinstance(expected, list):
        if expected != actual:
            return [f"{prefix}: expected={expected!r} actual={actual!r}"]
        return []
    if not values_match(expected, actual, tolerance=tolerance):
        return [f"{prefix}: expected={expected!r} actual={actual!r}"]
    return []


def aggregate_schema(aggregate: JSONDict) -> str:
    if isinstance(aggregate.get("results"), list):
        return "internal"
    if isinstance(aggregate.get("scores"), list):
        return "legacy"
    raise ValueError("aggregate must contain either an internal 'results' list or a legacy 'scores' list")


def result_map(aggregate: JSONDict) -> dict[str, JSONDict]:
    schema = aggregate_schema(aggregate)
    key = "results" if schema == "internal" else "scores"
    items = aggregate.get(key)
    if not isinstance(items, list):
        raise ValueError(f"aggregate must contain a '{key}' list")
    if not items:
        raise ValueError(f"aggregate must contain non-empty {key}")
    if aggregate.get("episode_count") != len(items):
        raise ValueError(f"episode_count does not match {key} length {len(items)}")
    mapped: dict[str, JSONDict] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{key}[{index}] must be an object")
        episode_id = item.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise ValueError(f"{key}[{index}] must contain a non-empty episode_id")
        if episode_id in mapped:
            raise ValueError(f"duplicate score for episode_id {episode_id!r}")
        mapped[episode_id] = item
    return mapped


def compare_internal_episode(episode_id: str, expected: JSONDict, actual: JSONDict, *, tolerance: float) -> list[str]:
    diffs: list[str] = []
    expected_summary = dict(expected.get("score_summary") or {})
    actual_summary = dict(actual.get("score_summary") or {})
    diffs.extend(recursive_reference_diff(
        f"episode.{episode_id}.score_summary", expected_summary, actual_summary,
        tolerance=tolerance,
    ))
    expected_diag = dict(expected_summary.get("diagnostics") or {})
    actual_diag = dict(actual_summary.get("diagnostics") or {})
    diffs.extend(
        scalar_dict_diff(
            f"episode.{episode_id}.diagnostics",
            expected_diag,
            actual_diag,
            INTERNAL_DIAGNOSTIC_KEYS,
            tolerance=tolerance,
        )
    )
    for key in ("status", "steps_used", "task_family", "difficulty", "functional_template", "target_group"):
        if key in expected and not values_match(expected.get(key), actual.get(key), tolerance=tolerance):
            diffs.append(f"episode.{episode_id}.{key}: expected={expected.get(key)!r} actual={actual.get(key)!r}")
    return diffs


def compare_legacy_episode(episode_id: str, expected: JSONDict, actual: JSONDict, *, tolerance: float) -> list[str]:
    return scalar_dict_diff(f"episode.{episode_id}", expected, actual, LEGACY_SCORE_KEYS, tolerance=tolerance)


def compare_aggregates(expected: JSONDict, actual: JSONDict, *, tolerance: float, max_diffs: int) -> list[str]:
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and non-negative")
    expected_schema = aggregate_schema(expected)
    actual_schema = aggregate_schema(actual)
    if expected_schema != actual_schema:
        return [f"schema: expected={expected_schema!r} actual={actual_schema!r}"]

    diffs: list[str] = []
    top_keys = INTERNAL_TOP_LEVEL_KEYS if expected_schema == "internal" else LEGACY_TOP_LEVEL_KEYS
    if expected_schema == "internal":
        top_keys += tuple(f"overall_{key}" for key in INTERNAL_TOP_LEVEL_KEYS)
    diffs.extend(scalar_dict_diff("top", expected, actual, top_keys, tolerance=tolerance))

    if expected_schema == "internal":
        if "terminal_status_histogram" in expected and expected.get("terminal_status_histogram") != actual.get("terminal_status_histogram"):
            diffs.append("top.terminal_status_histogram: expected and actual differ")
        for key in REFERENCE_RECURSIVE_TOP_KEYS:
            if key in expected:
                diffs.extend(
                    recursive_reference_diff(
                        f"top.{key}",
                        expected.get(key),
                        actual.get(key),
                        tolerance=tolerance,
                    )
                )
    expected_results = result_map(expected)
    actual_results = result_map(actual)
    expected_ids = set(expected_results)
    actual_ids = set(actual_results)
    for episode_id in sorted(expected_ids - actual_ids):
        diffs.append(f"episode.{episode_id}: missing from actual")
    for episode_id in sorted(actual_ids - expected_ids):
        diffs.append(f"episode.{episode_id}: extra in actual")

    for episode_id in sorted(expected_ids & actual_ids):
        if expected_schema == "internal":
            episode_diffs = compare_internal_episode(
                episode_id,
                expected_results[episode_id],
                actual_results[episode_id],
                tolerance=tolerance,
            )
        else:
            episode_diffs = compare_legacy_episode(
                episode_id,
                expected_results[episode_id],
                actual_results[episode_id],
                tolerance=tolerance,
            )
        diffs.extend(episode_diffs)
        if len(diffs) >= max_diffs:
            return diffs[:max_diffs]
    return diffs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two VIGIL aggregate score JSON files.")
    parser.add_argument("--expected", type=Path, required=True, help="Reference aggregate JSON")
    parser.add_argument("--actual", type=Path, required=True, help="Aggregate JSON produced by this release")
    parser.add_argument("--tolerance", type=float, default=1e-9, help="Absolute tolerance for float fields")
    parser.add_argument("--pack-file", type=Path, help="Require exact coverage of this pack manifest.")
    parser.add_argument("--max-diffs", type=int, default=50, help="Maximum number of diffs to print")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        expected = load_json(args.expected)
        actual = load_json(args.actual)
        if args.pack_file:
            pack = load_json(args.pack_file)
            rows = pack.get("episodes") or []
            ids = [row["episode_id"] for row in rows]
            if not ids or len(set(ids)) != len(ids):
                raise ValueError("pack must contain unique episode IDs")
            for label, payload in (("expected", expected), ("actual", actual)):
                observed = set(result_map(payload))
                missing, extra = set(ids) - observed, observed - set(ids)
                if missing or extra:
                    raise ValueError(
                        f"{label} pack coverage: {len(missing)} missing, {len(extra)} extra episodes"
                    )
        diffs = compare_aggregates(expected, actual, tolerance=float(args.tolerance), max_diffs=max(1, int(args.max_diffs)))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"[compare_aggregates] ERROR: {exc}", file=sys.stderr)
        return 2
    if diffs:
        print(f"[compare_aggregates] FAILED: {len(diffs)} mismatch(es) shown", file=sys.stderr)
        for diff in diffs:
            print(diff, file=sys.stderr)
        return 1
    episode_count = expected.get("episode_count", len(result_map(expected)))
    schema = aggregate_schema(expected)
    print(f"[compare_aggregates] OK: {schema} aggregate with {episode_count} episodes matches within tolerance {args.tolerance:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
