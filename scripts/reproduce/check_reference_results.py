#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vigil.eval.scoring import score_result_payload

JSONDict = dict[str, Any]


def load_json(path: Path) -> JSONDict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def collect_reference_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            files.extend(sorted(path.rglob("*.json")))
        elif path.exists():
            files.append(path)
        else:
            raise FileNotFoundError(f"reference path does not exist: {path}")
    supported: list[Path] = []
    for path in files:
        try:
            payload = load_json(path)
        except Exception:  # noqa: BLE001 - non-result JSONs are ignored in directory mode.
            if path in paths:
                raise
            continue
        if is_reference_result(payload):
            supported.append(path)
    if not supported:
        raise ValueError("No reference result JSON files found.")
    return supported


def is_reference_result(payload: JSONDict) -> bool:
    return (
        bool(payload.get("episode_id"))
        and isinstance(payload.get("settlement"), dict)
        and isinstance(payload.get("score_summary"), dict)
    )


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def values_match(expected: Any, actual: Any, *, tolerance: float) -> bool:
    expected_number = as_number(expected)
    actual_number = as_number(actual)
    if expected_number is not None or actual_number is not None:
        if expected_number is None or actual_number is None:
            return False
        return math.isclose(expected_number, actual_number, rel_tol=0.0, abs_tol=tolerance)
    return expected == actual


def compare_subset(prefix: str, expected: Any, actual: Any, *, tolerance: float) -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{prefix}: expected object actual={type(actual).__name__}"]
        diffs: list[str] = []
        for key, expected_value in sorted(expected.items()):
            if key not in actual:
                diffs.append(f"{prefix}.{key}: missing from actual")
                continue
            diffs.extend(compare_subset(f"{prefix}.{key}", expected_value, actual.get(key), tolerance=tolerance))
        return diffs
    if isinstance(expected, list):
        if expected != actual:
            return [f"{prefix}: expected={expected!r} actual={actual!r}"]
        return []
    if not values_match(expected, actual, tolerance=tolerance):
        return [f"{prefix}: expected={expected!r} actual={actual!r}"]
    return []


def check_reference_results(paths: list[Path], *, tolerance: float, max_diffs: int) -> tuple[int, int, list[str]]:
    files = collect_reference_files(paths)
    episode_ids: set[str] = set()
    diffs: list[str] = []
    for path in files:
        payload = load_json(path)
        episode_id = str(payload.get("episode_id") or path.stem)
        episode_ids.add(episode_id)
        expected_summary = dict(payload.get("score_summary") or {})
        actual_summary = dict(score_result_payload(payload).to_dict().get("score_summary") or {})
        file_diffs = compare_subset(
            f"episode.{episode_id}.score_summary",
            expected_summary,
            actual_summary,
            tolerance=tolerance,
        )
        diffs.extend(file_diffs)
        if len(diffs) >= max_diffs:
            return len(files), len(episode_ids), diffs[:max_diffs]
    return len(files), len(episode_ids), diffs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Check that release scoring reproduces per-episode score_summary fields "
            "embedded in reference result JSON files. This is useful when no full "
            "reference aggregate is available; use run_metric_alignment.sh for the "
            "final aggregate parity gate."
        )
    )
    parser.add_argument("--reference-path", action="append", type=Path, required=True, help="Reference result JSON file or directory. Repeatable.")
    parser.add_argument("--tolerance", type=float, default=1e-9, help="Absolute tolerance for numeric comparison.")
    parser.add_argument("--max-diffs", type=int, default=50, help="Maximum number of diffs to print.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        file_count, unique_count, diffs = check_reference_results(
            list(args.reference_path),
            tolerance=float(args.tolerance),
            max_diffs=max(1, int(args.max_diffs)),
        )
    except Exception as exc:  # noqa: BLE001 - CLI should surface validation errors cleanly.
        print(f"[check_reference_results] ERROR: {exc}", file=sys.stderr)
        return 2
    if diffs:
        print(f"[check_reference_results] FAILED: {len(diffs)} mismatch(es) shown", file=sys.stderr)
        for diff in diffs:
            print(diff, file=sys.stderr)
        return 1
    print(
        "[check_reference_results] OK: "
        f"{file_count} reference result file(s), {unique_count} unique episode(s), "
        f"score_summary fields match within tolerance {float(args.tolerance):g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
