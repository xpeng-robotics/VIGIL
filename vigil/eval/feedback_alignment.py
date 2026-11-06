"""Recompute paired feedback tables from complete archived episode evidence."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from vigil.eval.offline import _validate_completed_payload
from vigil.eval.paper_alignment import PaperAlignmentError, normalize_family, read_object, trace_outcome
from vigil.eval.scoring import _extract_behavior_metrics, score_result_payload


def count_episode_events(result: dict) -> dict:
    """Count executed interaction signatures, including non-adjacent repeats."""
    counts = Counter(retry=0, too_far=0, path_blocked=0, legacy_failure_proxy=0)
    seen = set()
    for step in result["trace"]:
        label = (step.get("judge_result") or {}).get("failure_label") or step.get("failure_label")
        if label in {"too_far", "path_blocked"}:
            counts[label] += 1
        if label in {"interaction_no_effect", "interaction_not_available"}:
            counts["legacy_failure_proxy"] += 1
        runtime = step.get("runtime_action") or {}
        invocation = runtime.get("executed_invocation") or runtime.get("validated_invocation") or runtime
        if invocation.get("skill_name") == "interact_pixel":
            signature = json.dumps(invocation.get("arguments") or {}, sort_keys=True, ensure_ascii=False)
            counts["retry"] += signature in seen
            seen.add(signature)
    if counts["retry"] != _extract_behavior_metrics(result)["same_interact_retry_count"]:
        raise PaperAlignmentError("Independent retry count disagrees with the shared scorer.")
    return dict(counts)


def measure_source(source: Path, families: dict[str, str], *, profile: str, episode_files: bool = False,
                   model_id: str | None = None) -> dict:
    """Episode-file mode is explicit: a broken aggregate never changes the metric."""
    source = Path(source)
    if episode_files:
        directory = source if source.is_dir() else source.parent
        errors = [directory / f"{eid}.error.json" for eid in families]
        if any(path.exists() for path in errors):
            raise PaperAlignmentError("Selected episodes have infrastructure error files.")

        def rows():
            for eid in sorted(families):
                path = directory / f"{eid}.json"
                raw = path.read_bytes()
                row = json.loads(raw)
                if row.get("episode_id") != eid:
                    raise PaperAlignmentError("Episode filename disagrees with its ID.")
                yield row, hashlib.sha256(raw).hexdigest()
        records = rows()
    else:
        aggregate = read_object(source)
        if any(aggregate.get(key) for key in ("error_count", "errors", "infrastructure_errors", "skipped_missing")):
            raise PaperAlignmentError("Source aggregate contains infrastructure failures or missing episodes.")
        results = aggregate.get("results")
        if not isinstance(results, list) or len(results) != len(families):
            raise PaperAlignmentError("Source aggregate must contain the complete canonical selection.")
        for key in ("episode_count", "overall_episode_count"):
            if key in aggregate and aggregate[key] != len(results):
                raise PaperAlignmentError("Aggregate episode count differs from its results.")
        if model_id and aggregate.get("model_name") not in {None, model_id}:
            raise PaperAlignmentError("Aggregate model differs from the selected source map entry.")
        records = ((r, hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()) for r in results)
    totals = Counter(W=0, B=0, FR=0, NR=0, retry=0, too_far=0, path_blocked=0, legacy_failure_proxy=0)
    seen = set()
    hashes = []
    for row, digest in records:
        eid = row.get("episode_id")
        if eid not in families or eid in seen:
            raise PaperAlignmentError("Unknown or duplicate episode ID in source.")
        seen.add(eid)
        _validate_completed_payload(row, Path(str(eid)))
        family = normalize_family(row.get("task_family") or "")
        if family != families[eid]:
            raise PaperAlignmentError("Source task family differs from canonical pack.")
        saved_profile = row.get("profile") or {}
        if (saved_profile.get("name") if isinstance(saved_profile, dict) else saved_profile) != profile:
            raise PaperAlignmentError("Source profile differs from the selected experiment arm.")
        if row.get("model_name") not in {None, model_id}:
            raise PaperAlignmentError("Episode model differs from source map entry.")
        settlement = row.get("settlement") or {}
        if settlement.get("steps_used") != len(row["trace"]):
            raise PaperAlignmentError("Settlement step count differs from trace.")
        world, benchmark = trace_outcome(row)
        score = score_result_payload(row)
        if (world, benchmark) != (score.score_summary["diagnostics"]["world_success"], score.success):
            raise PaperAlignmentError("Settlement/current scorer disagrees with per-step W/B evidence.")
        final = row["trace"][-1]
        invocation = (final.get("runtime_action") or {}).get("executed_invocation") or {}
        submitted = invocation.get("skill_name") == "report"
        matched = final["judge_result"].get("report_matches_world", final.get("report_matches_world"))
        false_report = submitted and matched is False
        no_report = not submitted and settlement.get("terminal_reason") == "fail_no_report"
        if bool(settlement.get("false_report")) != false_report:
            raise PaperAlignmentError("Settlement false report disagrees with terminal report evidence.")
        totals.update(W=int(world), B=int(benchmark), FR=int(false_report), NR=int(no_report))
        totals.update(count_episode_events(row))
        hashes.append((eid, digest))
    if seen != set(families):
        raise PaperAlignmentError("Source episode IDs differ from the canonical pack.")
    return {
        "episode_count": len(seen), "counts": dict(totals),
        "source_kind": "episode_files" if episode_files else "aggregate",
        "evidence_sha256": hashlib.sha256(json.dumps(sorted(hashes)).encode()).hexdigest(),
        "profile": profile,
        "model_identity": "source map assertion; checked where recorded",
    }


def audit_feedback(targets: dict, families: dict[str, str], baseline: dict, feedback: dict, *,
                   episode_files: bool = False, reference: str = "published") -> dict:
    if reference not in {"published", "corrected"}:
        raise PaperAlignmentError("reference must be published or corrected.")
    models = targets.get("models")
    if not families or not isinstance(models, list) or not models:
        raise PaperAlignmentError("Audit requires nonempty model targets and canonical episode IDs.")
    if targets.get("episode_count", len(families)) != len(families):
        raise PaperAlignmentError("Pack episode count differs from the frozen targets.")
    model_ids = [row["model_id"] for row in models]
    if len(set(model_ids)) != len(model_ids):
        raise PaperAlignmentError("Duplicate model IDs in targets.")
    required = {"W", "B", "FR", "NR", "retry", "too_far", "path_blocked"}
    for row in models:
        for arm in ("base", "feedback"):
            counts = row.get("corrected_counts", {}).get(arm, {})
            if set(counts) != required or any(type(v) is not int or v < 0 for v in counts.values()):
                raise PaperAlignmentError("Corrected targets require all seven non-negative integer counts per arm.")
    reports = []
    for target in targets["models"]:
        model = target["model_id"]
        measurements = {}
        for arm, sources, profile in (
            ("base", baseline, "pure_rgb_dialogue_history_baseline"),
            ("feedback", feedback, "pure_rgb_dialogue_history_proprio_minimal"),
        ):
            if model not in sources:
                raise PaperAlignmentError(f"Missing {arm} source for {model}.")
            measurements[arm] = measure_source(Path(sources[model]), families, profile=profile,
                                               episode_files=episode_files, model_id=model)
        n = len(families)
        published_mismatches = []
        corrected_mismatches = []
        for arm in ("base", "feedback"):
            counts = measurements[arm]["counts"]
            for metric in ("retry", "too_far", "path_blocked"):
                expected = target["published"][arm][metric]
                actual = counts[metric] / n
                if abs(expected - actual) > 0.005001:
                    published_mismatches.append({"arm": arm, "metric": metric, "published": expected, "actual": actual})
            for metric, expected in target["corrected_counts"][arm].items():
                if counts[metric] != expected:
                    corrected_mismatches.append({"arm": arm, "metric": metric, "expected": expected, "actual": counts[metric]})
        deltas = {k: 100 * (measurements["feedback"]["counts"][k] - measurements["base"]["counts"][k]) / n
                  for k in ("W", "B", "FR", "NR")}
        for metric, actual in deltas.items():
            expected = target["published"]["deltas"][metric]
            if abs(expected - actual) > 1e-9:
                published_mismatches.append({"metric": "delta_" + metric, "published": expected, "actual": actual})
        reports.append({"model_id": model, **measurements, "deltas": deltas,
                        "published_mismatches": published_mismatches, "corrected_mismatches": corrected_mismatches,
                        "passed": not (published_mismatches if reference == "published" else corrected_mismatches)})
    return {"reference": reference, "all_passed": all(r["passed"] for r in reports),
            "models_passed": sum(r["passed"] for r in reports), "models_expected": len(reports), "models": reports,
            "metric": "Repeated executed interact_pixel signatures after their first occurrence, over all selected episodes.",
            "scope": "Offline archived evidence; corrected reference does not rewrite the published paper."}
