from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vigil.actions import ActionCall
from vigil.actions import coerce_discrete_step_count, normalize_interaction_intent
from vigil.data.episodes import EpisodeSpec
from vigil.data.conditions import evaluate_episode, estimate_progress, target_object_matches
from vigil.envs.types import EnvActionResult
from vigil.coordinates import adapt_pixel_arguments, coordinate_mode, scale_normalized_1000 as _scale_normalized_1000

# Resolved only when a caller explicitly constructs a simulator adapter.
Controller = None


def _load_controller():
    global Controller
    if Controller is not None:
        return Controller
    try:
        from ai2thor.controller import Controller as AI2ThorController
    except ImportError as exc:
        raise RuntimeError('ai2thor is not installed. Install with `python -m pip install -e ".[thor]"`.') from exc

    class WorkspaceController(AI2ThorController):
        @property
        def base_dir(self):
            override = os.environ.get("VIGIL_AI2THOR_BASE", "").strip()
            if override:
                return str(Path(override).expanduser())
            return super().base_dir

    Controller = WorkspaceController
    return Controller


JSONDict = dict[str, Any]
DIRECT_THOR_SKILLS = {
    "MoveAhead",
    "MoveBack",
    "RotateLeft",
    "RotateRight",
    "LookUp",
    "LookDown",
}
THOR_ACTION_TO_INTENT = {
    "OpenObject": "open_access",
    "CloseObject": "close_access",
    "ToggleObjectOn": "activate",
    "ToggleObjectOff": "deactivate",
    "PickupObject": "pick",
    "PutObject": "place",
}
EXTRA_INTENT_ALIASES = {
    "pick_up": "pick",
    "place_object": "place",
    "turn_on": "activate",
    "turn_off": "deactivate",
}


def _normalize_coord_mode(coord_mode: str | None) -> str | None:
    return coordinate_mode(coord_mode)


def _normalize_runner_intent(intent: Any) -> str:
    normalized = normalize_interaction_intent(str(intent or ""))
    return EXTRA_INTENT_ALIASES.get(normalized, normalized)


def _link_ai2thor_release_cache() -> None:
    raw_source = (
        os.environ.get("VIGIL_THOR_RELEASES_DIR", "").strip()
        or os.environ.get("VIGIL_AI2THOR_RELEASES_DIR", "").strip()
    )
    if not raw_source:
        return
    source = Path(raw_source).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"AI2-THOR releases cache does not exist: {source}")
    target_base = os.environ.get("VIGIL_AI2THOR_BASE", "").strip()
    target = (Path(target_base).expanduser() if target_base else Path.home() / ".ai2thor") / "releases"
    try:
        if source.resolve() == target.resolve():
            return
    except OSError:
        pass
    target.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        destination = target / child.name
        if destination.exists() or destination.is_symlink():
            continue
        destination.symlink_to(child, target_is_directory=child.is_dir())


def _confirmed_setup_state(action: JSONDict, metadata: JSONDict) -> JSONDict | None:
    """THOR rejects repeated state setters; require independent state evidence."""
    kind = action.get("action")
    if kind not in {"ToggleObjectOn", "ToggleObjectOff", "OpenObject", "CloseObject"}:
        return None
    target_id = action.get("objectId")
    if not isinstance(target_id, str) or not target_id:
        return None
    target = next((obj for obj in metadata.get("objects", [])
                   if isinstance(obj, dict) and obj.get("objectId") == target_id), {})
    if kind in {"ToggleObjectOn", "ToggleObjectOff"}:
        desired = kind == "ToggleObjectOn"
        if target.get("toggleable") is True and target.get("isToggled") is desired:
            return {"isToggled": desired}
    else:
        desired = action.get("openness", 1.0) if kind == "OpenObject" else 0.0
        actual = target.get("openness")
        if (type(desired) in (int, float) and 0 <= desired <= 1
                and type(actual) in (int, float) and target.get("openable") is True
                and target.get("isOpen") is (desired > 0)
                and math.isclose(actual, desired, rel_tol=0, abs_tol=1e-6)):
            return {"isOpen": desired > 0, "openness": actual}
    return None


@dataclass(frozen=True)
class ThorObservation:
    frame: Any
    metadata: JSONDict


@dataclass(frozen=True)
class ThorStepResult:
    observation: ThorObservation
    env_status: str
    action_success: bool
    error_message: str | None
    progress: float
    judge_success: bool
    terminal: bool = False
    diagnostics: JSONDict = field(default_factory=dict)
    env_result: EnvActionResult | None = None


class PublicThorEnv:
    """Small public AI2-THOR adapter for VIGIL release runs.

    This intentionally supports the common iTHOR path first and keeps the
    public execution contract easy to inspect and extend. ProcTHOR controller
    pooling, recovery policies, and alternate interaction adapters can be
    layered on without changing the trace/scoring contract.
    """

    def __init__(
        self,
        episode: EpisodeSpec,
        *,
        width: int = 640,
        height: int = 480,
        render_depth: bool = False,
        scene_root: str | Path = "data/scenes",
        coord_mode: str | None = None,
    ):
        _load_controller()
        self.episode = episode
        self.platform = str(episode.scene.get("platform") or "ithor").lower()
        self.width = int(width)
        self.height = int(height)
        self.render_depth = bool(render_depth)
        self.scene_root = Path(scene_root)
        self.coord_mode = _normalize_coord_mode(coord_mode)
        self.controller: Any | None = None
        self.last_event: Any | None = None
        self.flags: JSONDict = {}
        self.initialization_checks: list[JSONDict] = []
        self._interactables = [
            dict(item)
            for item in list((episode.generation_hints or {}).get("interactables") or [])
            if isinstance(item, dict)
        ]

    def reset(self) -> ThorObservation:
        self.initialization_checks.clear()
        _link_ai2thor_release_cache()
        controller_kwargs = dict(self.episode.scene.get("controller") or {})
        if self.platform == "procthor":
            controller_kwargs["scene"] = "Procedural"
        else:
            controller_kwargs.setdefault("scene", self.episode.scene_id)
        controller_kwargs.setdefault("width", self.width)
        controller_kwargs.setdefault("height", self.height)
        controller_kwargs.setdefault("renderDepthImage", self.render_depth)
        controller_kwargs.setdefault("snapToGrid", False)
        controller_kwargs.setdefault("timeout", 600)
        controller_kwargs.setdefault("server_timeout", 600)
        controller_kwargs.setdefault("server_start_timeout", 1200)

        thor_platform = os.environ.get("VIGIL_THOR_PLATFORM", "").strip().lower()
        if thor_platform == "cloud" and "platform" not in controller_kwargs:
            try:
                from ai2thor.platform import CloudRendering

                controller_kwargs["platform"] = CloudRendering
            except ImportError as exc:
                raise RuntimeError(
                    "VIGIL_THOR_PLATFORM=cloud was requested, but ai2thor.platform.CloudRendering "
                    "is unavailable in this environment."
                ) from exc

        gpu_device = os.environ.get("VIGIL_GPU_DEVICE", "").strip()
        if gpu_device and "gpu_device" not in controller_kwargs:
            try:
                controller_kwargs["gpu_device"] = int(gpu_device)
            except ValueError:
                pass

        self.controller = Controller(**controller_kwargs)
        if self.platform == "procthor":
            house = self._load_procthor_house()
            self._reset_step({"action": "CreateHouse", "house": house, "renderImage": False})
        init = dict(self.episode.agent_init or self.episode.start_pose or {})
        if init:
            action = {
                "action": "TeleportFull",
                "position": dict(init.get("position") or {}),
                "rotation": dict(init.get("rotation") or {}),
                "horizon": init.get("horizon", 0.0),
            }
            if "standing" in init:
                action["standing"] = bool(init.get("standing"))
            self._reset_step(action)
        else:
            self._reset_step({"action": "Pass"})
        for setup_action in self.episode.scene_setup:
            self._reset_step(dict(setup_action))
        return self.get_observation()

    def _reset_step(self, action: JSONDict) -> None:
        self.last_event = self.controller.step(**action)
        metadata = getattr(self.last_event, "metadata", None)
        success = isinstance(metadata, dict) and metadata.get("lastActionSuccess") is True
        existing = (_confirmed_setup_state(action, metadata)
                    if isinstance(metadata, dict) and metadata.get("lastActionSuccess") is False else None)
        self.initialization_checks.append({"action": action.get("action"), "object_id": action.get("objectId"),
                                           "simulator_success": success, "confirmed_existing_state": existing})
        if not success and existing is None:
            detail = metadata.get("errorMessage") if isinstance(metadata, dict) else None
            raise RuntimeError(
                f"Scene initialization failed for {action.get('action', 'unknown')}: "
                f"{detail or 'simulator did not confirm success'}"
            )

    def _load_procthor_house(self) -> JSONDict:
        scene_payload = dict(self.episode.scene or {})
        if isinstance(scene_payload.get("house"), dict):
            return dict(scene_payload["house"])
        if isinstance(scene_payload.get("house_json"), dict):
            return dict(scene_payload["house_json"])
        refs = [
            self.episode.scene_ref,
            scene_payload.get("scene_ref"),
            scene_payload.get("scene_id") if str(scene_payload.get("scene_id") or "") != "Procedural" else None,
        ]
        for ref in refs:
            if not ref:
                continue
            scene_dir = self.scene_root / str(ref)
            house_path = scene_dir / "house.json"
            if house_path.exists():
                return json.loads(house_path.read_text(encoding="utf-8"))
            scene_json = scene_dir / "scene.json"
            if scene_json.exists():
                catalog = json.loads(scene_json.read_text(encoding="utf-8"))
                if catalog.get("house_path"):
                    candidate = scene_dir / str(catalog["house_path"])
                    if candidate.exists():
                        return json.loads(candidate.read_text(encoding="utf-8"))
        searched = ", ".join(str(item) for item in refs if item) or "<none>"
        raise FileNotFoundError(f"Could not find ProcTHOR house.json under {self.scene_root} for scene_ref(s): {searched}")

    def get_observation(self) -> ThorObservation:
        event = self.last_event
        if event is None:
            return ThorObservation(frame=None, metadata={})
        return ThorObservation(frame=getattr(event, "frame", None), metadata=dict(event.metadata or {}))

    def get_world_state(self) -> JSONDict:
        metadata = dict((self.last_event.metadata if self.last_event is not None else {}) or {})
        inventory_objects = [dict(item) for item in list(metadata.get("inventoryObjects") or [])]
        held = inventory_objects[0] if inventory_objects else {}
        inventory = dict(metadata.get("inventory") or {})
        inventory.setdefault("held_object_id", held.get("objectId") or held.get("object_id"))
        inventory.setdefault("held_object_type", held.get("objectType") or held.get("object_type"))
        return {
            "objects": [dict(item) for item in list(metadata.get("objects") or [])],
            "inventory": inventory,
            "flags": dict(self.flags),
            "agent": dict(metadata.get("agent") or {}),
        }

    def _target_payload(self, target: JSONDict | None) -> JSONDict | None:
        if not target:
            return None
        return {
            "object_id": target.get("object_id") or target.get("objectId"),
            "object_type": target.get("object_type") or target.get("objectType"),
        }

    def _make_step_result(
        self,
        *,
        skill_name: str,
        requested_arguments: JSONDict,
        executed_arguments: JSONDict,
        pre_state: JSONDict,
        simulator_success: bool,
        error_message: str | None,
        env_status: str,
        terminal: bool = False,
        resolved_target: JSONDict | None = None,
        target_resolved: bool | None = None,
        action_adapter: JSONDict | None = None,
    ) -> ThorStepResult:
        observation = self.get_observation()
        post_state = self.get_world_state()
        env_result = EnvActionResult(
            skill_name=skill_name,
            requested_arguments=dict(requested_arguments),
            executed_arguments=dict(executed_arguments),
            observation=observation,
            simulator_success=bool(simulator_success),
            error_message=error_message,
            resolved_target=resolved_target,
            target_resolved=bool(resolved_target is not None) if target_resolved is None else bool(target_resolved),
            action_adapter=action_adapter,
            pre_state=dict(pre_state),
            post_state=post_state,
        )
        judge = self.judge()
        return ThorStepResult(
            observation=observation,
            env_status=env_status,
            action_success=bool(simulator_success),
            error_message=error_message,
            progress=judge.progress,
            judge_success=judge.success,
            terminal=terminal,
            diagnostics=judge.diagnostics,
            env_result=env_result,
        )

    def step(self, action: ActionCall) -> ThorStepResult:
        pre_state = self.get_world_state()
        requested_arguments = dict(action.arguments or {})
        if action.skill_name in {"Stop", "ReportDone", "report"}:
            if action.skill_name in {"ReportDone", "report"}:
                self.flags["last_report"] = requested_arguments
            return self._make_step_result(
                skill_name="report" if action.skill_name in {"ReportDone", "report"} else action.skill_name,
                requested_arguments=requested_arguments,
                executed_arguments=requested_arguments,
                pre_state=pre_state,
                simulator_success=True,
                error_message=None,
                env_status="stopped",
                terminal=True,
            )
        try:
            if action.skill_name == "interact_pixel":
                return self._handle_interact_pixel(action, pre_state=pre_state)
            if action.skill_name == "navigate" and str(requested_arguments.get("mode") or "").lower() in {
                "forward",
                "backward",
            }:
                return self._handle_discrete_navigation(action, pre_state=pre_state)
            thor_action = self._to_thor_action(action)
            self.last_event = self.controller.step(**thor_action)  # type: ignore[union-attr]
            metadata = dict(self.last_event.metadata or {})
            action_success = bool(metadata.get("lastActionSuccess", False))
            error = metadata.get("errorMessage") or None
            return self._make_step_result(
                skill_name=action.skill_name,
                requested_arguments=requested_arguments,
                executed_arguments=requested_arguments,
                pre_state=pre_state,
                simulator_success=action_success,
                error_message=str(error) if error else None,
                env_status="success" if action_success else "action_failed",
                terminal=False,
                action_adapter={"thor_action": thor_action},
            )
        except Exception as exc:  # noqa: BLE001 - errors become trace diagnostics.
            error = f"{type(exc).__name__}: {exc}"
            env_result = EnvActionResult(
                skill_name=action.skill_name,
                requested_arguments=requested_arguments,
                executed_arguments={},
                observation=self.get_observation(),
                simulator_success=False,
                error_message=error,
                pre_state=pre_state,
                post_state=self.get_world_state(),
            )
            return ThorStepResult(
                observation=self.get_observation(),
                env_status="protocol_error",
                action_success=False,
                error_message=error,
                progress=self.estimate_progress(),
                judge_success=False,
                terminal=False,
                env_result=env_result,
            )

    def _handle_discrete_navigation(self, action: ActionCall, *, pre_state: JSONDict) -> ThorStepResult:
        args = dict(action.arguments or {})
        mode = str(args.get("mode") or "").lower()
        step_count = coerce_discrete_step_count(args.get("magnitude", 1))
        thor_action = {"action": "MoveAhead" if mode == "forward" else "MoveBack"}
        thor_actions = []
        action_success = True
        error: str | None = None
        for _ in range(step_count):
            self.last_event = self.controller.step(**thor_action)  # type: ignore[union-attr]
            thor_actions.append(dict(thor_action))
            metadata = dict(self.last_event.metadata or {})
            if not bool(metadata.get("lastActionSuccess", False)):
                action_success = False
                error = metadata.get("errorMessage") or None
                break
        executed_arguments = dict(args)
        executed_arguments.update({"mode": mode, "magnitude": len(thor_actions)})
        action_adapter: JSONDict = {
            "thor_action": dict(thor_action),
            "thor_actions": thor_actions,
            "requested_step_count": step_count,
            "executed_step_count": len(thor_actions),
        }
        return self._make_step_result(
            skill_name=action.skill_name,
            requested_arguments=args,
            executed_arguments=executed_arguments,
            pre_state=pre_state,
            simulator_success=action_success,
            error_message=str(error) if error else None,
            env_status="success" if action_success else "action_failed",
            terminal=False,
            action_adapter=action_adapter,
        )

    def _to_thor_action(self, action: ActionCall) -> JSONDict:
        args = dict(action.arguments)
        if action.skill_name == "navigate":
            mode = str(args.get("mode") or "").lower()
            magnitude = float(args.get("magnitude", 1))
            if mode == "forward":
                return {"action": "MoveAhead"}
            if mode == "backward":
                return {"action": "MoveBack"}
            if mode == "turn_left":
                return {"action": "RotateLeft", "degrees": magnitude}
            if mode == "turn_right":
                return {"action": "RotateRight", "degrees": magnitude}
            raise ValueError(f"Unsupported navigate.mode: {mode}")
        if action.skill_name == "look":
            direction = str(args.get("direction") or "").lower()
            magnitude = float(args.get("magnitude", 30))
            if direction == "up":
                return {"action": "LookUp", "degrees": magnitude}
            if direction == "down":
                return {"action": "LookDown", "degrees": magnitude}
            raise ValueError(f"Unsupported look.direction: {direction}")
        if action.skill_name in DIRECT_THOR_SKILLS:
            payload: JSONDict = {"action": action.skill_name}
            if "degrees" in args:
                payload["degrees"] = float(args["degrees"])
            return payload
        if action.skill_name == "Interact":
            return {"action": str(args.get("thor_action") or "Pass"), **dict(args.get("thor_args") or {})}
        if action.skill_name in {"PickupObject", "OpenObject", "CloseObject", "ToggleObjectOn", "ToggleObjectOff", "PutObject"}:
            object_id = self._resolve_object_id(args)
            if not object_id:
                raise ValueError("Could not resolve target object. Provide object_id or visible object_type.")
            payload = {"action": action.skill_name, "objectId": object_id}
            if action.skill_name == "PutObject":
                payload.setdefault("forceAction", bool(args.get("forceAction", True)))
                payload.setdefault("placeStationary", bool(args.get("placeStationary", True)))
            elif "forceAction" in args:
                payload["forceAction"] = bool(args["forceAction"])
            return payload
        raise ValueError(f"Unsupported THOR runner skill: {action.skill_name}")

    def _resolve_object_id(self, args: JSONDict) -> str | None:
        if args.get("object_id"):
            return str(args["object_id"])
        object_type = str(args.get("object_type") or "").strip().lower()
        if not object_type or self.last_event is None:
            return None
        objects = list((self.last_event.metadata or {}).get("objects", []) or [])
        visible = [item for item in objects if bool(item.get("visible")) and str(item.get("objectType") or "").lower() == object_type]
        if visible:
            visible.sort(key=lambda item: float(item.get("distance") or 1e9))
            return str(visible[0].get("objectId"))
        return None

    def _interaction_distance_limit(self, spec: JSONDict | None = None) -> float:
        raw = None
        if isinstance(spec, dict):
            raw = spec.get("distance_limit")
        if raw is None:
            raw = (self.episode.generation_hints or {}).get("interaction_distance_limit")
        if raw is None:
            raw = (self.episode.scene.get("controller") or {}).get("interaction_distance_limit")
        try:
            return float(raw if raw is not None else 1.5)
        except (TypeError, ValueError):
            return 1.5

    def _object_bool(self, target: JSONDict, *keys: str, default: bool = False) -> bool:
        for key in keys:
            if key in target:
                return bool(target.get(key))
        return default

    def _object_value(self, target: JSONDict, *keys: str) -> Any:
        for key in keys:
            if key in target:
                return target.get(key)
        return None

    def _target_matches_spec(self, target: JSONDict, spec: JSONDict) -> bool:
        target_id = str(target.get("objectId") or target.get("object_id") or "").strip()
        target_type = str(target.get("objectType") or target.get("object_type") or "").strip()
        spec_id = str(spec.get("target_object_id") or spec.get("object_id") or spec.get("objectId") or "").strip()
        spec_type = str(
            spec.get("target_object_type")
            or spec.get("object_type")
            or spec.get("objectType")
            or ""
        ).strip()
        matched_key = False
        if spec_id:
            matched_key = True
            if target_id != spec_id:
                return False
        if spec_type:
            matched_key = True
            if target_type.lower() != spec_type.lower():
                return False
        return matched_key

    def _matching_interactable_specs(self, target: JSONDict, *, intent: str | None = None) -> list[JSONDict]:
        matched = [spec for spec in self._interactables if self._target_matches_spec(target, spec)]
        if intent is None:
            return matched
        intent = _normalize_runner_intent(intent)
        filtered = []
        for spec in matched:
            spec_intent = _normalize_runner_intent(spec.get("intent") or "")
            thor_action = dict(spec.get("thor_action") or {})
            action_intent = THOR_ACTION_TO_INTENT.get(str(thor_action.get("action") or ""))
            if spec_intent == intent or action_intent == intent:
                filtered.append(spec)
        return filtered

    def _candidate_supported_intents(self, target: JSONDict) -> set[str]:
        supported: set[str] = set()
        if self._object_bool(target, "visible", default=True):
            supported.add("ground")
        matched_specs = self._matching_interactable_specs(target)
        for spec in matched_specs:
            spec_intent = _normalize_runner_intent(spec.get("intent") or "")
            if spec_intent:
                supported.add(spec_intent)
            thor_action = dict(spec.get("thor_action") or {})
            action_intent = THOR_ACTION_TO_INTENT.get(str(thor_action.get("action") or ""))
            if action_intent:
                supported.add(action_intent)
        if matched_specs:
            return supported
        if self._object_bool(target, "openable", default=False):
            supported.update({"open_access", "close_access"})
        if self._object_bool(target, "toggleable", default=False):
            supported.update({"activate", "deactivate"})
        if self._object_bool(target, "pickupable", default=False):
            supported.add("pick")
        if self._object_bool(target, "receptacle", default=False):
            supported.add("place")
        return supported

    def _candidate_issues(self, target: JSONDict, intent: str) -> list[str]:
        intent = _normalize_runner_intent(intent)
        issues: list[str] = []
        matched_specs = self._matching_interactable_specs(target, intent=intent)
        visible = self._object_bool(target, "visible", default=True)
        visibility_required = True
        if matched_specs:
            visibility_required = any(bool(spec.get("visibility_required", True)) for spec in matched_specs)
        if visibility_required and not visible:
            issues.append("not_visible")

        if intent != "ground":
            raw_distance = self._object_value(target, "distance")
            try:
                distance = None if raw_distance is None else float(raw_distance)
            except (TypeError, ValueError):
                distance = None
            if matched_specs:
                distance_limit = min(self._interaction_distance_limit(spec) for spec in matched_specs)
            else:
                distance_limit = self._interaction_distance_limit()
            if distance is not None and distance > distance_limit:
                issues.append("too_far")

        inventory = dict(self.get_world_state().get("inventory") or {})
        held_object_id = str(inventory.get("held_object_id") or "").strip()
        if intent == "pick" and held_object_id:
            issues.append("hand_full")
        if intent in {"place", "drop"} and not held_object_id:
            issues.append("no_held_object")
        if intent == "open_access" and self._object_bool(target, "isOpen", "is_open", default=False):
            issues.append("already_in_target_state")
        if intent == "close_access" and not self._object_bool(target, "isOpen", "is_open", default=True):
            issues.append("already_in_target_state")
        if intent == "activate" and self._object_bool(target, "isToggled", "is_toggled", default=False):
            issues.append("already_in_target_state")
        if intent == "deactivate" and not self._object_bool(target, "isToggled", "is_toggled", default=True):
            issues.append("already_in_target_state")
        return issues

    def _candidate_from_object(self, target: JSONDict, *, intent: str | None = None) -> JSONDict:
        candidate = dict(self._target_payload(target) or {})
        candidate["visible"] = self._object_bool(target, "visible", default=True)
        if "distance" in target:
            candidate["distance"] = target.get("distance")
        matched_specs = self._matching_interactable_specs(target)
        if matched_specs:
            candidate["interactable_ids"] = [
                str(spec.get("interactable_id") or spec.get("id") or "").strip()
                for spec in matched_specs
                if str(spec.get("interactable_id") or spec.get("id") or "").strip()
            ]
        candidate["supported_intents"] = sorted(self._candidate_supported_intents(target))
        if intent is not None:
            candidate["issues"] = self._candidate_issues(target, intent)
        return candidate

    def _validate_interaction_candidate(self, target: JSONDict, intent: str) -> str | None:
        intent = _normalize_runner_intent(intent)
        supported_intents = self._candidate_supported_intents(target)
        if intent not in supported_intents:
            return "intent_not_supported"
        issues = self._candidate_issues(target, intent)
        for issue in ("too_far", "not_visible", "hand_full"):
            if issue in issues:
                return issue
        if "no_held_object" in issues:
            return "interaction_not_available"
        if "already_in_target_state" in issues:
            return "already_in_target_state"
        if issues:
            return "interaction_not_available"
        return None

    def _handle_interact_pixel(self, action: ActionCall, *, pre_state: JSONDict) -> ThorStepResult:
        args = dict(action.arguments or {})
        intent = _normalize_runner_intent(args.get("intent") or "ground")
        if intent == "drop":
            thor_action = {"action": "DropHandObject", "forceAction": False}
            self.last_event = self.controller.step(**thor_action)
            metadata = dict(self.last_event.metadata or {})
            success = bool(metadata.get("lastActionSuccess", False))
            return self._make_step_result(
                skill_name="interact_pixel", requested_arguments=args,
                executed_arguments={**args, "intent": intent}, pre_state=pre_state,
                simulator_success=success, error_message=metadata.get("errorMessage") or None,
                env_status="success" if success else "action_failed", target_resolved=False,
                action_adapter={"thor_action": thor_action},
            )
        executed_arguments, coordinate_adapter = adapt_pixel_arguments(
            {**args, "intent": intent}, mode=self.coord_mode, width=self.width, height=self.height,
        )
        x, y = executed_arguments["x"], executed_arguments["y"]
        adapter = dict(coordinate_adapter or {})
        if not (0 <= x < self.width and 0 <= y < self.height):
            # Preserve raw and mapped coordinates even when the action is invalid.
            return self._make_step_result(
                skill_name="interact_pixel", requested_arguments=args, executed_arguments=executed_arguments,
                pre_state=pre_state, simulator_success=False,
                error_message=f"interact_pixel coordinates out of bounds: ({x}, {y}) for image size {self.width}x{self.height}.",
                env_status="protocol_error", target_resolved=False, action_adapter=adapter or None,
            )
        target = self._resolve_pixel_object(x, y)
        resolved_target = self._target_payload(target)
        if not target:
            return self._make_step_result(
                skill_name="interact_pixel",
                requested_arguments=args,
                executed_arguments=executed_arguments,
                pre_state=pre_state,
                simulator_success=False,
                error_message="interaction_no_effect",
                env_status="action_failed",
                terminal=False,
                resolved_target=None,
                target_resolved=False,
                action_adapter=adapter or None,
            )
        candidate = self._candidate_from_object(target, intent=intent)
        validation_error = self._validate_interaction_candidate(target, intent)
        if validation_error:
            return self._make_step_result(
                skill_name="interact_pixel",
                requested_arguments=args,
                executed_arguments=executed_arguments,
                pre_state=pre_state,
                simulator_success=False,
                error_message=validation_error,
                env_status="action_failed",
                terminal=False,
                resolved_target=resolved_target,
                target_resolved=True,
                action_adapter={**adapter, "candidate": candidate, "validation_error": validation_error},
            )
        if intent == "ground":
            grounding_hits = list(self.flags.get("grounding_hits") or [])
            grounding_hits.append(dict(resolved_target or {}))
            self.flags["grounding_hits"] = grounding_hits
            grounded = target_object_matches(target, dict(self.episode.success_condition or {}))
            self.flags["target_grounded"] = bool(grounded)
            return self._make_step_result(
                skill_name="interact_pixel",
                requested_arguments=args,
                executed_arguments=executed_arguments,
                pre_state=pre_state,
                simulator_success=True,
                error_message=None,
                env_status="success",
                terminal=False,
                resolved_target=resolved_target,
                target_resolved=True,
                action_adapter={**adapter, "candidate": candidate},
            )
        mapped = {
            "open_access": "OpenObject",
            "close_access": "CloseObject",
            "activate": "ToggleObjectOn",
            "deactivate": "ToggleObjectOff",
            "pick": "PickupObject",
            "place": "PutObject",
        }.get(intent)
        if mapped is None:
            raise ValueError(f"Unsupported interact_pixel intent: {intent}")
        object_id = target.get("objectId") or target.get("object_id")
        thor_action: JSONDict = {"action": mapped, "objectId": object_id, "forceAction": False}
        if mapped == "PutObject":
            thor_action["placeStationary"] = True
        self.last_event = self.controller.step(**thor_action)  # type: ignore[union-attr]
        metadata = dict(self.last_event.metadata or {})
        action_success = bool(metadata.get("lastActionSuccess", False))
        error = metadata.get("errorMessage") or None
        if action_success and mapped == "PutObject":
            held_id = str((pre_state.get("inventory") or {}).get("held_object_id") or "").strip()
            if held_id and object_id:
                placed_objects = dict(self.flags.get("placed_objects") or {})
                placed_objects[held_id] = str(object_id)
                self.flags["placed_objects"] = placed_objects
        return self._make_step_result(
            skill_name="interact_pixel",
            requested_arguments=args,
            executed_arguments=executed_arguments,
            pre_state=pre_state,
            simulator_success=action_success,
            error_message=str(error) if error else None,
            env_status="success" if action_success else "action_failed",
            terminal=False,
            resolved_target=resolved_target,
            target_resolved=True,
            action_adapter={**adapter, "thor_action": thor_action, "candidate": candidate},
        )

    def _resolve_pixel_object(self, x: int, y: int) -> JSONDict | None:
        event = self.last_event
        if event is None or x < 0 or y < 0:
            return None
        object_id = None
        frame = getattr(event, "instance_segmentation_frame", None)
        color_to_object_id = getattr(event, "color_to_object_id", None)
        if frame is not None and color_to_object_id is not None:
            try:
                height = len(frame)
                width = len(frame[0]) if height else 0
                if 0 <= y < height and 0 <= x < width:
                    color = tuple(int(v) for v in frame[y][x][:3])
                    object_id = color_to_object_id.get(color)
            except Exception:
                object_id = None
        objects = list((event.metadata or {}).get("objects", []) or [])
        if object_id:
            for item in objects:
                if item.get("objectId") == object_id:
                    return dict(item)
        detections = getattr(event, "instance_detections2D", None)
        if detections is not None:
            try:
                for oid, bbox in detections.items():
                    if bbox is None or len(bbox) != 4:
                        continue
                    x1, y1, x2, y2 = [int(v) for v in bbox]
                    if x1 <= x <= x2 and y1 <= y <= y2:
                        for item in objects:
                            if item.get("objectId") == oid:
                                return dict(item)
            except Exception:
                return None
        return None

    def judge(self):
        metadata = (self.last_event.metadata if self.last_event is not None else {}) or {}
        return evaluate_episode(self.episode, dict(metadata), self.flags)

    def evaluate_success(self) -> bool:
        return self.judge().success

    def estimate_progress(self) -> float:
        metadata = (self.last_event.metadata if self.last_event is not None else {}) or {}
        return estimate_progress(dict(self.episode.success_condition or {}), dict(metadata))

    def save_frame(self, path: str | Path) -> Path | None:
        frame = getattr(self.last_event, "frame", None) if self.last_event is not None else None
        if frame is None:
            return None
        try:
            from PIL import Image
            out = Path(path)
            out.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(frame).save(out)
            return out
        except Exception:
            return None

    def close(self) -> None:
        controller = self.controller
        self.controller = None
        self.last_event = None
        if controller is not None:
            try:
                controller.stop()
            except Exception:
                pass
