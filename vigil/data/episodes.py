from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class EpisodeSpec:
    episode_id: str
    scene_id: str
    task_family: str
    instruction: str
    max_steps: int = 20
    start_pose: JSONDict | None = None
    success_condition: JSONDict | None = None
    scene_ref: str | None = None
    metadata: JSONDict = field(default_factory=dict)
    scene: JSONDict = field(default_factory=dict)
    agent_init: JSONDict = field(default_factory=dict)
    scene_setup: tuple[JSONDict, ...] = field(default_factory=tuple)
    budget: JSONDict = field(default_factory=dict)
    constraint_spec: JSONDict = field(default_factory=dict)
    trace_hints: JSONDict = field(default_factory=dict)
    generation_hints: JSONDict = field(default_factory=dict)

    @property
    def success_spec(self) -> JSONDict:
        return dict(self.success_condition or {})

    @property
    def task_instruction(self) -> str:
        return str(self.instruction or "")

    @classmethod
    def from_dict(cls, payload: JSONDict) -> "EpisodeSpec":
        if "scene" in payload or "task" in payload or "budget" in payload:
            return cls._from_vigil_style_dict(payload)
        return cls._from_manifest_row(payload)

    @classmethod
    def _from_manifest_row(cls, payload: JSONDict) -> "EpisodeSpec":
        required = ("episode_id", "scene_id", "task_family")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError(f"Episode manifest row is missing required fields: {', '.join(missing)}")
        raw_budget = dict(payload.get("budget") or {}) if isinstance(payload.get("budget"), dict) else {}
        max_steps = int(payload.get("max_steps", raw_budget.get("max_steps", 20)))
        if max_steps <= 0:
            raise ValueError(f"Episode {payload['episode_id']!r} has non-positive max_steps.")
        budget = _normalize_budget(raw_budget, max_steps=max_steps)
        start_pose = payload.get("start_pose") or payload.get("agent_init")
        scene = dict(payload.get("scene") or {"platform": "ithor", "scene_id": payload["scene_id"]})
        trace_hints = dict(payload.get("trace_hints") or {})
        trace_hints.setdefault("task_family", str(payload["task_family"]))
        generation_hints = _normalize_generation_hints(payload)
        return cls(
            episode_id=str(payload["episode_id"]),
            scene_id=str(payload["scene_id"]),
            task_family=str(payload["task_family"]),
            instruction=str(payload.get("instruction") or payload.get("task_instruction") or ""),
            max_steps=max_steps,
            start_pose=dict(start_pose or {}) if isinstance(start_pose, dict) else start_pose,
            success_condition=payload.get("success_condition") or payload.get("success_spec"),
            scene_ref=str(payload.get("scene_ref") or payload.get("scene_id") or "") or None,
            metadata={
                k: v
                for k, v in payload.items()
                if k
                not in {
                    "episode_id",
                    "scene_id",
                    "task_family",
                    "instruction",
                    "task_instruction",
                    "max_steps",
                    "budget",
                    "start_pose",
                    "agent_init",
                    "success_condition",
                    "success_spec",
                    "scene",
                    "scene_setup",
                    "scene_ref",
                    "constraint_spec",
                    "trace_hints",
                    "generation_hints",
                    "interactables",
                    "hazards",
                }
            },
            scene=scene,
            agent_init=dict(start_pose or {}) if isinstance(start_pose, dict) else {},
            scene_setup=tuple(dict(item) for item in payload.get("scene_setup", []) or []),
            budget=budget,
            constraint_spec=_normalize_constraint_spec(payload, budget=budget),
            trace_hints=trace_hints,
            generation_hints=generation_hints,
        )

    @classmethod
    def _from_vigil_style_dict(cls, payload: JSONDict) -> "EpisodeSpec":
        required = ("episode_id", "scene", "agent_init", "task", "budget", "success_condition")
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"VIGIL-style episode config is missing required fields: {missing}")
        scene = dict(payload["scene"])
        task = dict(payload["task"])
        raw_budget = dict(payload["budget"])
        scene_id = str(scene.get("scene_id") or (scene.get("controller") or {}).get("scene") or "")
        if not scene_id:
            raise ValueError("VIGIL-style episode scene must define scene_id or controller.scene.")
        max_steps = int(raw_budget.get("max_steps", 0) or 0)
        if max_steps <= 0:
            raise ValueError("budget.max_steps must be positive.")
        budget = _normalize_budget(raw_budget, max_steps=max_steps)
        trace_hints = dict(payload.get("trace_hints") or {})
        task_family = str(task.get("task_family") or trace_hints.get("task_family") or "unknown")
        trace_hints.setdefault("task_family", task_family)
        generation_hints = _normalize_generation_hints(payload)
        return cls(
            episode_id=str(payload["episode_id"]),
            scene_id=scene_id,
            task_family=task_family,
            instruction=str(task.get("instruction") or ""),
            max_steps=max_steps,
            start_pose=dict(payload.get("agent_init") or {}),
            success_condition=dict(payload.get("success_condition") or payload.get("success_spec") or {}),
            scene_ref=str(payload.get("scene_ref") or scene.get("scene_ref") or scene_id or "") or None,
            metadata=dict(payload.get("metadata") or {}),
            scene=scene,
            agent_init=dict(payload.get("agent_init") or {}),
            scene_setup=tuple(dict(item) for item in payload.get("scene_setup", []) or []),
            budget=budget,
            constraint_spec=_normalize_constraint_spec(payload, budget=budget),
            trace_hints=trace_hints,
            generation_hints=generation_hints,
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "EpisodeSpec":
        payload = _read_json(Path(path))
        return cls.from_dict(payload)

    def to_dict(self) -> JSONDict:
        payload = asdict(self)
        payload["scene_setup"] = [dict(item) for item in self.scene_setup]
        return payload


@dataclass(frozen=True)
class Pack:
    pack_id: str
    episodes: tuple[EpisodeSpec, ...]
    metadata: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return {
            "pack_id": self.pack_id,
            "episodes": [episode.to_dict() for episode in self.episodes],
            "metadata": dict(self.metadata),
        }


def _normalize_budget(raw_budget: JSONDict, *, max_steps: int) -> JSONDict:
    budget = dict(raw_budget)
    budget["max_steps"] = int(max_steps)
    budget["max_invalid_actions"] = int(budget.get("max_invalid_actions", 0) or 0)
    budget.setdefault("timeout_policy", "fail")
    return budget


def _normalize_constraint_spec(payload: JSONDict, *, budget: JSONDict) -> JSONDict:
    constraint_spec = {
        "invalid_action_limit": int(budget.get("max_invalid_actions", 0) or 0),
        "hazards": [dict(item) for item in payload.get("hazards", []) or []],
        "report_required": True,
    }
    if isinstance(payload.get("constraint_spec"), dict):
        constraint_spec.update(dict(payload["constraint_spec"]))
    return constraint_spec


def _normalize_generation_hints(payload: JSONDict) -> JSONDict:
    generation_hints: JSONDict = {}
    interactables = list(payload.get("interactables") or [])
    if interactables:
        generation_hints["interactables"] = [dict(item) for item in interactables]
    if isinstance(payload.get("generation_hints"), dict):
        generation_hints.update(dict(payload["generation_hints"]))
    return generation_hints


def _read_json(path: Path) -> JSONDict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return payload


def _load_episode_entry(entry: Any, *, base_dir: Path) -> EpisodeSpec:
    if isinstance(entry, str):
        return EpisodeSpec.from_dict(_read_json((base_dir / entry).resolve()))
    if not isinstance(entry, dict):
        raise ValueError("Each pack episode entry must be an object or path string.")
    if "path" in entry:
        return EpisodeSpec.from_dict(_read_json((base_dir / str(entry["path"])).resolve()))
    return EpisodeSpec.from_dict(entry)


def load_pack(path: str | Path) -> Pack:
    pack_path = Path(path).resolve()
    payload = _read_json(pack_path)
    raw_episodes = payload.get("episodes")
    if not isinstance(raw_episodes, list):
        raise ValueError("Pack must contain an 'episodes' list.")
    episodes = tuple(_load_episode_entry(entry, base_dir=pack_path.parent) for entry in raw_episodes)
    metadata = dict(payload.get("metadata") or {})
    for key in ("version", "purpose", "asset_role", "platform", "status", "generated_at", "summary"):
        if key in payload:
            metadata.setdefault(key, payload[key])
    pack = Pack(
        pack_id=str(payload.get("pack_id") or pack_path.stem),
        episodes=episodes,
        metadata=metadata,
    )
    validate_pack(pack)
    return pack


def validate_pack(pack: Pack) -> None:
    if not pack.episodes:
        raise ValueError("Pack contains no episodes.")
    seen: set[str] = set()
    for episode in pack.episodes:
        if episode.episode_id in seen:
            raise ValueError(f"Duplicate episode_id in pack: {episode.episode_id}")
        seen.add(episode.episode_id)
