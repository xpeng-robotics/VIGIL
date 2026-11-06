"""Inspect saved runs without starting a simulator or making model requests."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from vigil.eval.scoring import aggregate_scores, score_episode
from vigil.eval.settlement import settle_trace
from vigil.eval.traces import load_trace, validate_completed_trace


def _object(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def selected_episode_ids(status: dict) -> list[str]:
    ids = status.get("episode_ids")
    if not isinstance(ids, list) or not ids:
        raise ValueError("run_status.json must select at least one episode.")
    if any(not isinstance(item, str) or not item or item in {".", ".."}
           or "/" in item or "\\" in item for item in ids):
        raise ValueError("run_status.json contains an invalid episode ID.")
    if len(set(ids)) != len(ids):
        raise ValueError("run_status.json contains duplicate episode IDs.")
    return ids


def inspect_progress(directory: str | Path) -> dict:
    root = Path(directory)
    if not root.is_dir():
        raise ValueError(f"Run directory does not exist: {root}")
    status_path = root / "run_status.json"
    status = _object(status_path) if status_path.is_file() else {}
    ids = selected_episode_ids(status) if status else None
    traces = list((root / "traces").glob("*.json"))
    scores = list((root / "scores").glob("*.score.json"))
    selected = set(ids) if ids else None
    if selected is not None:
        traces = [p for p in traces if p.stem in selected]
        scores = [p for p in scores if p.name.removesuffix(".score.json") in selected]
    return {
        "state": status.get("state", "untracked"),
        "selected_episodes": len(ids) if ids else None,
        "saved_traces": len(traces),
        "saved_scores": len(scores),
        "infrastructure_errors": status.get("infrastructure_errors", []),
        "latest_traces": [p.name for p in sorted(traces, key=lambda p: p.stat().st_mtime)[-5:]],
        "metrics_verified": False,
    }


def verify_run(directory: str | Path, *, require_frames: bool = False) -> dict:
    """Rebuild settlements and scores from step evidence for the selected episodes.

    This checks artifact consistency, not simulator authenticity or paper parity.
    It deliberately does not read model configuration, credentials or live APIs.
    """
    root = Path(directory)
    status = _object(root / "run_status.json")
    if status.get("state") != "complete" or status.get("infrastructure_errors"):
        raise ValueError("Run is incomplete or contains infrastructure errors; resume it before verification.")
    ids = selected_episode_ids(status)
    scores = []
    rows = []
    for episode_id in ids:
        try:
            trace = load_trace(root / "traces" / f"{episode_id}.json")
            if trace.episode_id != episode_id:
                raise ValueError("trace episode ID differs from run_status.json")
            validate_completed_trace(trace)
            uncached = replace(trace, metadata={k: v for k, v in trace.metadata.items() if k != "settlement"})
            rebuilt = settle_trace(uncached).to_dict()
            if rebuilt != trace.metadata.get("settlement"):
                raise ValueError("cached settlement differs from step evidence")
            # The public scorer validates the cache and preserves its result metadata.
            score = score_episode(trace)
            saved = _object(root / "scores" / f"{episode_id}.score.json")
            if score.to_dict() != saved:
                raise ValueError("saved score differs from rescored trace")
            if require_frames:
                for step in trace.steps:
                    frame = root / "frames" / episode_id / f"step_{step.step_index:03d}.png"
                    with frame.open("rb") as handle:
                        if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                            raise ValueError(f"invalid PNG header: {frame.name}")
            scores.append(score)
            rows.append({"episode_id": episode_id, "steps": len(trace.steps),
                         "world_success": rebuilt["world_success"], "benchmark_success": score.success,
                         "terminal_reason": rebuilt["terminal_reason"]})
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise ValueError(f"Verification failed for {episode_id}: {exc}") from exc
    aggregate = aggregate_scores(scores).to_dict()
    if aggregate != _object(root / "aggregate_score.json"):
        raise ValueError("Saved aggregate differs from selected, rescored episodes.")
    return {
        "verified": True,
        "scope": "selected episodes in run_status.json; artifact consistency only",
        "episode_count": len(ids),
        "agent_steps": sum(row["steps"] for row in rows),
        "world_success_count": sum(row["world_success"] for row in rows),
        "benchmark_success_count": sum(row["benchmark_success"] for row in rows),
        "uncached_settlement_parity": True,
        "per_episode_score_parity": True,
        "aggregate_parity": True,
        "frame_headers_checked": require_frames,
        "episodes": rows,
    }
