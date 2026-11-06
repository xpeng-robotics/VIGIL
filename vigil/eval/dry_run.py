from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil.data.episodes import Pack
from vigil.agent.profiles import AgentProfile, resolve_benchmark_mode

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class DryRunResult:
    aggregate_path: Path
    payload: JSONDict


def build_dry_run_aggregate(pack: Pack, profile: AgentProfile) -> JSONDict:
    return {
        "schema_version": "vigil.release.aggregate.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pack_id": pack.pack_id,
        "profile": profile.to_dict(),
        "benchmark_mode": resolve_benchmark_mode(profile),
        "summary": {
            "episode_count": len(pack.episodes),
            "status": "dry_run",
        },
        "score_summary": {
            "status": "not_executed",
            "success_rate": None,
            "mean_episode_score": None,
            "note": "Dry-run validates pack/profile wiring only. Score real traces with `vigil score-trace`.",
        },
        "episodes": [
            {
                "episode_id": episode.episode_id,
                "scene_id": episode.scene_id,
                "task_family": episode.task_family,
                "max_steps": episode.max_steps,
                "status": "not_executed",
                "episode_score": None,
            }
            for episode in pack.episodes
        ],
    }


def run_pack_dry(pack: Pack, profile: AgentProfile, out_dir: str | Path) -> DryRunResult:
    output_dir = Path(out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_dry_run_aggregate(pack, profile)
    aggregate_path = output_dir / f"{pack.pack_id}.{profile.name}.aggregate.json"
    aggregate_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return DryRunResult(aggregate_path=aggregate_path, payload=payload)
