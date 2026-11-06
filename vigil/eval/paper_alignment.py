"""Audit frozen paper outcomes with the current scorer and per-step evidence."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from vigil.eval.scoring import score_result_payload


class PaperAlignmentError(ValueError):
    """An input is incomplete, ambiguous, or inconsistent with the frozen pack."""


def normalize_family(value: str) -> str:
    return "S4_state_recognition" if value == "S4_state_verification" else value


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PaperAlignmentError(f"Expected a JSON object: {path}")
    return value


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def trace_outcome(result: dict[str, Any]) -> tuple[bool, bool]:
    """Derive W/B without trusting a saved score or settlement success flag."""
    trace = result.get("trace")
    if not isinstance(trace, list) or not trace:
        raise PaperAlignmentError(
            "Each reference result needs its complete step trace."
        )
    if any(not isinstance(step, dict) for step in trace):
        raise PaperAlignmentError("Every trace step must be a JSON object.")
    judges = [step.get("judge_result") or {} for step in trace]
    if any(not isinstance(judge, dict) or type(judge.get("world_success")) is not bool for judge in judges):
        raise PaperAlignmentError("Every step, including the final step, needs boolean world_success evidence.")
    final = judges[-1]
    world = final["world_success"]
    semantic_world = final.get("semantic_world_success", world)
    if type(semantic_world) is not bool:
        raise PaperAlignmentError("semantic_world_success must be boolean.")
    if semantic_world != world:
        raise PaperAlignmentError(
            "Paper W requires the primary semantic world predicate."
        )
    submitted = False
    matched = None
    for index, (step, judge) in enumerate(zip(trace, judges)):
        invocation = (
            (step.get("runtime_action") or {}).get("executed_invocation")
            or step.get("invocation")
            or {}
        )
        is_report = (
            bool(judge.get("report_submitted"))
            or invocation.get("skill_name") == "report"
            or step.get("agent_report_status") is not None
        )
        if is_report:
            if index != len(trace) - 1:
                raise PaperAlignmentError("Trace continues after a terminal report.")
            if invocation.get("skill_name") != "report" or judge.get("protocol_failure"):
                raise PaperAlignmentError("Terminal report evidence needs a valid report invocation.")
            submitted = True
            matched = judge.get("report_matches_world")
            if matched is None:
                matched = step.get("report_matches_world")
        if index != len(trace) - 1 and judge.get("status") not in {None, "", "ongoing"}:
            raise PaperAlignmentError("Trace continues after a terminal judgment.")
    if submitted and type(matched) is not bool:
        raise PaperAlignmentError("A terminal report is missing report-match evidence.")
    if submitted:
        status = (invocation.get("arguments") or {}).get("status")
        statuses = {"success", "fail", "unsafe", "invalid", "on", "off", "open", "closed"}
        if status not in statuses:
            raise PaperAlignmentError("Terminal report invocation needs a valid status.")
        expected = (final.get("oracle_facts") or {}).get("expected_report_status")
        if expected is not None and expected not in statuses:
            raise PaperAlignmentError("Invalid expected report status in oracle evidence.")
        derived_match = (status == expected) if expected is not None else (
            (status == "success" and world) or (status in {"fail", "unsafe", "invalid"} and not world)
        )
        if matched != derived_match:
            raise PaperAlignmentError("Terminal report-match evidence disagrees with the actual report.")
        matched = derived_match
    return world, bool(world and submitted and matched)


def audit_model(
    source: Path, target: dict[str, Any], family_by_id: dict[str, str]
) -> dict[str, Any]:
    aggregate = read_object(source)
    if aggregate.get("error_count") or aggregate.get("errors") or aggregate.get("infrastructure_errors"):
        raise PaperAlignmentError("Reference aggregate contains infrastructure errors.")
    if aggregate.get("skipped_missing"):
        raise PaperAlignmentError("Reference aggregate has missing selected episodes.")
    results = aggregate.get("results")
    if not isinstance(results, list) or not results:
        raise PaperAlignmentError("Reference aggregate needs a nonempty results list.")
    if any(not isinstance(row, dict) for row in results):
        raise PaperAlignmentError("Every result must be a JSON object.")
    ids = [str(row.get("episode_id") or "") for row in results]
    if len(set(ids)) != len(ids):
        raise PaperAlignmentError("Duplicate episode IDs in reference results.")
    if set(ids) != set(family_by_id):
        raise PaperAlignmentError(
            "Reference episode IDs differ from the canonical pack."
        )
    for key in ("episode_count", "overall_episode_count"):
        if key in aggregate and aggregate[key] != len(ids):
            raise PaperAlignmentError(f"{key} disagrees with the result count.")
    declared_model = aggregate.get("model_name")
    if declared_model and declared_model not in target.get(
        "source_model_names", [target["model_id"]]
    ):
        raise PaperAlignmentError(
            "Source model name does not match the selected paper row."
        )
    profile = aggregate.get("profile") or {}
    profile_name = profile.get("name") if isinstance(profile, dict) else profile
    if profile_name and profile_name != "pure_rgb_dialogue_history_baseline":
        raise PaperAlignmentError("Source is not the baseline paper profile.")

    totals = Counter(world_success_count=0, benchmark_success_count=0)
    families = {
        family: Counter(world_success_count=0, benchmark_success_count=0)
        for family in set(family_by_id.values())
    }
    disagreements = []
    digest_rows = []
    for result in results:
        episode_id = result["episode_id"]
        family = normalize_family(
            str(
                result.get("task_family")
                or (result.get("score_summary") or {}).get("task_family")
                or ""
            )
        )
        if family != family_by_id[episode_id]:
            raise PaperAlignmentError(f"Task family differs from pack: {episode_id}")
        if (result.get("settlement") or {}).get("steps_used") != len(result.get("trace") or []):
            raise PaperAlignmentError(f"Settlement step count differs from trace: {episode_id}")
        world, benchmark = trace_outcome(result)
        score = score_result_payload(result)
        actual_world = score.score_summary["diagnostics"]["world_success"]
        if (bool(actual_world), bool(score.success)) != (world, benchmark):
            disagreements.append(
                {
                    "episode_id": episode_id,
                    "trace_W": world,
                    "trace_B": benchmark,
                    "scorer_W": bool(actual_world),
                    "scorer_B": bool(score.success),
                }
            )
        for key, flag in (
            ("world_success_count", world),
            ("benchmark_success_count", benchmark),
        ):
            totals[key] += int(flag)
            families[family][key] += int(flag)
        digest_rows.append(
            {
                "episode_id": episode_id,
                "task_family": family,
                "W": world,
                "B": benchmark,
            }
        )
    actual = {
        **dict(totals),
        "by_task_family": {k: dict(v) for k, v in sorted(families.items())},
    }
    expected = target["expected"]
    mismatches = []
    for key in ("world_success_count", "benchmark_success_count"):
        if actual[key] != expected[key]:
            mismatches.append(
                {"field": key, "expected": expected[key], "actual": actual[key]}
            )
        for family, counts in expected["by_task_family"].items():
            if actual["by_task_family"].get(family, {}).get(key) != counts[key]:
                mismatches.append(
                    {
                        "field": f"by_task_family.{family}.{key}",
                        "expected": counts[key],
                        "actual": actual["by_task_family"].get(family, {}).get(key),
                    }
                )
    encoded = json.dumps(
        sorted(digest_rows, key=lambda row: row["episode_id"]),
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "model_id": target["model_id"],
        "episode_count": len(ids),
        "source_sha256": file_hash(source),
        "outcome_sha256": hashlib.sha256(encoded).hexdigest(),
        "actual": actual,
        "paper_mismatches": mismatches,
        "scorer_trace_disagreement_count": len(disagreements),
        "scorer_trace_disagreement_examples": disagreements[:20],
        "passed": not mismatches and not disagreements,
    }


def audit_paper(
    targets_path: Path, pack_path: Path, sources: dict[str, str]
) -> dict[str, Any]:
    targets = read_object(targets_path)
    if targets.get("schema_version") != "vigil_paper_alignment_v1":
        raise PaperAlignmentError("Unsupported target schema.")
    if file_hash(pack_path) != targets["release_pack_sha256"]:
        raise PaperAlignmentError("Canonical pack checksum mismatch.")
    pack = read_object(pack_path)
    entries = pack["episodes"]
    family_by_id = {
        row["episode_id"]: normalize_family(row["task_family"]) for row in entries
    }
    if len(family_by_id) != len(entries) or len(entries) != targets["episode_count"]:
        raise PaperAlignmentError("Canonical pack count or uniqueness mismatch.")
    counts = Counter(family_by_id.values())
    if len(counts) != 8 or set(counts.values()) != {targets["family_episode_count"]}:
        raise PaperAlignmentError("Canonical family counts differ from paper.")
    models = targets["models"]
    model_ids = [row["model_id"] for row in models]
    if len(set(model_ids)) != len(model_ids):
        raise PaperAlignmentError("Duplicate model IDs in target table.")
    if set(sources) - set(model_ids):
        raise PaperAlignmentError("Unknown model ID in source map.")
    rows = []
    for model in models:
        model_id = model["model_id"]
        if model_id not in sources:
            rows.append(
                {"model_id": model_id, "passed": False, "error": "missing_source"}
            )
            continue
        try:
            row = audit_model(Path(sources[model_id]), model, family_by_id)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row = {
                "model_id": model_id,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)
        print(
            f"[paper-alignment] {model_id}: {'PASS' if row['passed'] else 'FAIL'}",
            flush=True,
        )
    return {
        "schema_version": "vigil_paper_alignment_report_v1",
        "paper": targets["paper"],
        "targets_sha256": file_hash(targets_path),
        "pack_sha256": file_hash(pack_path),
        "models_passed": sum(row["passed"] for row in rows),
        "models_expected": len(models),
        "all_passed": bool(rows) and all(row["passed"] for row in rows),
        "fresh_rollout_parity_verified": False,
        "rows": rows,
    }
