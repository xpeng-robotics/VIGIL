"""Pure task-condition evaluation shared by environment evidence and the judge."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any
from vigil.data.episodes import EpisodeSpec

JSONDict = dict[str, Any]


@dataclass(frozen=True)
class JudgeResult:
    success: bool
    progress: float
    condition_type: str
    terminal_reason: str = ""
    diagnostics: JSONDict = field(default_factory=dict)

    def to_dict(self) -> JSONDict:
        return asdict(self)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_report_status(status: Any) -> str | None:
    normalized = str(status or "").strip().lower()
    if normalized in {"success", "fail", "unsafe", "invalid", "on", "off", "open", "closed"}:
        return normalized
    return None


def _complement_report_status(expected_status: str | None) -> str:
    normalized = _normalize_report_status(expected_status)
    complements = {
        "success": "fail",
        "fail": "success",
        "on": "off",
        "off": "on",
        "open": "closed",
        "closed": "open",
    }
    if normalized in complements:
        return complements[normalized]
    return "fail"


def _agent_in_region(world_state: JSONDict, region: JSONDict | None) -> bool:
    if not isinstance(region, dict):
        return False
    agent = dict(world_state.get("agent") or {})
    position = dict(agent.get("position") or {})
    x = position.get("x")
    z = position.get("z")
    if x is None or z is None:
        return False
    min_x = region.get("min_x")
    max_x = region.get("max_x")
    min_z = region.get("min_z")
    max_z = region.get("max_z")
    if None in {min_x, max_x, min_z, max_z}:
        return False
    return float(min_x) <= float(x) <= float(max_x) and float(min_z) <= float(z) <= float(max_z)


def _read_simulator_object_field(item: JSONDict, field_name: str) -> Any:
    fn = str(field_name or "").strip()
    if fn in item:
        return item.get(fn)
    if fn == "is_open":
        return item.get("isOpen")
    if fn == "is_toggled":
        return item.get("isToggled")
    return item.get(fn)


def _normalize_receptacle_ids(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw_items = value
    else:
        raw_items = [value]
    normalized: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _strip_dual_success_metadata(success_spec: JSONDict | None) -> JSONDict:
    cleaned = dict(success_spec or {})
    for key in (
        "evaluation",
        "semantic_spec",
        "strict_spec",
        "strict_unavailable_reason",
        "task_binding_mode",
    ):
        cleaned.pop(key, None)
    return cleaned


def _resolve_explicit_dual_success_contract(success_spec: JSONDict) -> JSONDict | None:
    semantic_spec = dict(success_spec.get("semantic_spec") or {})
    strict_spec = dict(success_spec.get("strict_spec") or {})
    evaluation = dict(success_spec.get("evaluation") or {})
    if not semantic_spec and not strict_spec and not evaluation:
        return None
    base_spec = _strip_dual_success_metadata(success_spec)
    primary_metric = str(evaluation.get("primary") or "semantic").strip().lower() or "semantic"
    if primary_metric not in {"semantic", "strict"}:
        primary_metric = "semantic"
    secondary_metric = str(evaluation.get("secondary") or "strict").strip().lower() or "strict"
    if secondary_metric not in {"semantic", "strict", "none"}:
        secondary_metric = "strict"
    resolved_semantic = semantic_spec or base_spec
    resolved_strict = strict_spec or (base_spec if secondary_metric == "strict" else {})
    strict_unavailable_reason = str(success_spec.get("strict_unavailable_reason") or "").strip() or None
    return {
        "primary_metric": primary_metric,
        "secondary_metric": secondary_metric,
        "semantic_spec": resolved_semantic,
        "strict_spec": resolved_strict or None,
        "strict_unavailable_reason": strict_unavailable_reason,
    }


def _build_dual_success_eval(
    *,
    semantic_eval: JSONDict,
    strict_eval: JSONDict | None,
    primary_metric: str,
    secondary_metric: str,
    strict_unavailable_reason: str | None = None,
) -> JSONDict:
    primary_eval = strict_eval if primary_metric == "strict" and strict_eval is not None else semantic_eval
    payload = dict(primary_eval)
    payload["primary_metric"] = primary_metric
    payload["secondary_metric"] = secondary_metric
    payload["primary_eval"] = dict(primary_eval)
    payload["semantic_eval"] = dict(semantic_eval)
    payload["strict_eval"] = dict(strict_eval) if strict_eval is not None else None
    payload["strict_available"] = strict_eval is not None
    if strict_unavailable_reason:
        payload["strict_unavailable_reason"] = strict_unavailable_reason
    return payload


def _matches_receptacle_reference(
    *,
    item: JSONDict,
    success_spec: JSONDict,
    objects: list[JSONDict],
    flags: JSONDict,
) -> bool:
    allowed_receptacle_ids = _normalize_receptacle_ids(success_spec.get("allowed_receptacle_object_ids"))
    target_place_id = str(
        success_spec.get("receptacle_object_id")
        or success_spec.get("target_place_id")
        or ""
    ).strip()
    target_place_type = str(
        success_spec.get("receptacle_type")
        or success_spec.get("target_place_type")
        or ""
    ).strip()
    parent_ids = _normalize_receptacle_ids(item.get("parentReceptacles"))
    placed_objects = dict(flags.get("placed_objects", {}) or {})
    placed_id = str(placed_objects.get(str(item.get("objectId") or "")) or "").strip()
    if placed_id:
        parent_ids.append(placed_id)
    if allowed_receptacle_ids:
        return any(parent_id in set(allowed_receptacle_ids) for parent_id in parent_ids)
    if target_place_id:
        return target_place_id in parent_ids
    if not target_place_type:
        return False
    receptacle_ids = set(parent_ids)
    return any(
        str(obj.get("objectId") or "").strip() in receptacle_ids
        and str(obj.get("objectType") or "").strip() == target_place_type
        for obj in objects
    )


def _state_report_label_from_oracle(oracle: JSONDict) -> str | None:
    field = str(oracle.get("field") or "").strip()
    value = bool(oracle.get("value"))
    if field == "is_toggled":
        return "on" if value else "off"
    if field == "is_open":
        return "open" if value else "closed"
    return None


def _evaluate_agent_near_target(world_state: JSONDict, success_spec: JSONDict) -> JSONDict:
    """S2 diagnostic: agent within interaction range of target (XZ plane)."""
    threshold = float(success_spec.get("distance_threshold", 1.5))
    target_type = str(success_spec.get("target_object_type") or "").strip()
    target_id = str(success_spec.get("target_object_id") or "").strip()
    objects = list(world_state.get("objects") or [])
    if target_id:
        matched = [o for o in objects if str(o.get("objectId") or "") == target_id]
    else:
        matched = [o for o in objects if target_type and str(o.get("objectType") or "") == target_type]
    if not matched:
        return {"resolved": False, "success": False, "progress": 0.0,
                "message": f"target object {target_type or target_id} not found in world state"}
    best_distance = min(float(o.get("distance", 999.0)) for o in matched)
    success = best_distance <= threshold
    progress = _clamp01(1.0 - best_distance / max(threshold * 3, 1.0)) if not success else 1.0
    return {
        "resolved": True, "success": success,
        "progress": progress,
        "message": f"agent {'within' if success else 'outside'} {threshold:.1f}m of target (dist={best_distance:.2f}m)",
    }


def _evaluate_target_grounded(world_state: JSONDict, success_spec: JSONDict) -> JSONDict:
    """S1 diagnostic: target resolved by interact_pixel (checked via grounding_hits in flags)."""
    flags = dict(world_state.get("flags") or {})
    target_type = str(success_spec.get("target_object_type") or "").strip()
    target_id = str(success_spec.get("target_object_id") or "").strip()
    grounding_hits = list(flags.get("grounding_hits") or [])
    success = any(
        (target_id and str(hit.get("object_id") or "") == target_id)
        or (target_type and str(hit.get("object_type") or "") == target_type)
        for hit in grounding_hits
    )
    return {
        "resolved": True, "success": success,
        "progress": 1.0 if success else 0.0,
        "message": "target grounded by interact_pixel" if success else "target not yet grounded",
    }


def _evaluate_report_status_public_evidence(world_state: JSONDict, oracle_spec: JSONDict) -> JSONDict:
    condition_type = str(oracle_spec.get("type") or "").strip().lower()
    if condition_type != "object_state":
        return _evaluate_success_single(world_state, oracle_spec)
    target_object_type = oracle_spec.get("target_object_type")
    target_object_id = oracle_spec.get("target_object_id")
    objects = list(world_state.get("objects") or [])
    if target_object_id:
        matched = [item for item in objects if item.get("objectId") == target_object_id]
    else:
        matched = [item for item in objects if target_object_type and item.get("objectType") == target_object_type]
    if not matched:
        return {
            "resolved": False,
            "success": False,
            "progress": 0.0,
            "message": "report_status target not found in current public state",
        }
    visible_matched = [item for item in matched if bool(_read_simulator_object_field(item, "visible"))]
    if not visible_matched:
        return {
            "resolved": False,
            "success": False,
            "progress": 0.0,
            "message": "report_status target state not publicly observable in current frame",
        }
    public_world_state = dict(world_state)
    public_world_state["objects"] = visible_matched
    public_eval = _evaluate_success_single(public_world_state, oracle_spec)
    if public_eval.get("success"):
        return dict(public_eval, message="report_status public evidence supports oracle")
    return dict(public_eval, message="report_status public evidence does not support oracle")


def _evaluate_success_single(world_state: JSONDict, success_spec: JSONDict) -> JSONDict:
    condition_type = str(success_spec.get("type") or "").strip().lower()
    if condition_type == "all_of":
        children = [_evaluate_success_single(world_state, dict(item)) for item in success_spec.get("conditions", [])]
        success = bool(children) and all(child.get("success") for child in children)
        progress = min((child.get("progress", 0.0) for child in children), default=0.0)
        return {
            "resolved": all(child.get("resolved") for child in children),
            "success": success,
            "progress": _clamp01(progress if children else 0.0),
            "children": children,
            "message": "all_of satisfied" if success else "all_of not yet satisfied",
        }
    if condition_type == "any_of":
        children = [_evaluate_success_single(world_state, dict(item)) for item in success_spec.get("conditions", [])]
        success = any(child.get("success") for child in children)
        progress = max((child.get("progress", 0.0) for child in children), default=0.0)
        return {
            "resolved": any(child.get("resolved") for child in children),
            "success": success,
            "progress": _clamp01(progress),
            "children": children,
            "message": "any_of satisfied" if success else "any_of not yet satisfied",
        }
    if condition_type == "flag_equals":
        flags = dict(world_state.get("flags") or {})
        key = str(success_spec.get("key") or "")
        expected = success_spec.get("value")
        success = flags.get(key) == expected
        return {
            "resolved": True,
            "success": success,
            "progress": 1.0 if success else 0.0,
            "message": f"flag {key} {'matched' if success else 'did not match'}",
        }
    if condition_type == "report_status":
        # report_status tasks (e.g., S4 per task_family.md) still need an oracle
        # world-truth condition that is hidden from the model.
        oracle = dict(success_spec.get("oracle_condition") or {})
        if not oracle:
            return {
                "resolved": False,
                "success": False,
                "progress": 0.0,
                "message": "report_status requires oracle_condition",
            }
        oracle_eval = _evaluate_success_single(world_state, oracle)
        expected_when_true = _normalize_report_status(success_spec.get("expected")) or "success"
        if expected_when_true in {"success", "fail"}:
            expected_when_true = _state_report_label_from_oracle(oracle) or expected_when_true
        public_eval = _evaluate_report_status_public_evidence(world_state, oracle)
        if bool(public_eval.get("success")):
            expected_report_status = expected_when_true
        elif bool(public_eval.get("resolved")):
            expected_report_status = _complement_report_status(expected_when_true)
        else:
            # For verification questions, absent public evidence should not force a
            # hidden-state success claim; conservative `fail` matches the agent contract.
            expected_report_status = "fail"
        return {
            "resolved": bool(public_eval.get("resolved")),
            "success": bool(public_eval.get("success")),
            "progress": float(public_eval.get("progress", 0.0)),
            "expected_report_status": expected_report_status,
            "oracle_eval": oracle_eval,
            "public_eval": public_eval,
            "message": str(public_eval.get("message") or "report_status public evidence unavailable"),
        }
    if condition_type == "agent_in_region":
        region_id = str(success_spec.get("region_id") or "")
        region = dict(success_spec.get("region") or {})
        success = _agent_in_region(world_state, region if region else None)
        return {
            "resolved": bool(region),
            "success": success,
            "progress": 1.0 if success else 0.0,
            "message": f"agent {'inside' if success else 'outside'} region {region_id or 'unknown'}",
        }
    if condition_type == "agent_near_target":
        return _evaluate_agent_near_target(world_state, success_spec)
    if condition_type == "target_grounded":
        return _evaluate_target_grounded(world_state, success_spec)
    inventory = dict(world_state.get("inventory") or {})
    objects = list(world_state.get("objects") or [])
    flags = dict(world_state.get("flags") or {})
    target_object_type = success_spec.get("target_object_type")
    target_object_id = success_spec.get("target_object_id")
    if condition_type == "object_held":
        held_id = inventory.get("held_object_id")
        held_type = inventory.get("held_object_type")
        success = bool(
            (target_object_id and held_id == target_object_id)
            or (target_object_type and held_type == target_object_type)
        )
        return {
            "resolved": True,
            "success": success,
            "progress": 1.0 if success else 0.0,
            "message": "required object held" if success else "required object not held",
        }
    if condition_type == "object_state":
        field_name = str(success_spec.get("field") or "")
        expected = success_spec.get("value")
        if target_object_id:
            matched = [item for item in objects if item.get("objectId") == target_object_id]
        else:
            matched = [item for item in objects if target_object_type and item.get("objectType") == target_object_type]
        require_unique_match = bool(success_spec.get("_require_unique_match"))
        if not target_object_id and require_unique_match and len(matched) != 1:
            return {
                "resolved": False,
                "success": False,
                "progress": 0.0,
                "message": "ambiguous object_state target; concrete object_id required",
            }
        success = any(_read_simulator_object_field(item, field_name) == expected for item in matched)
        return {
            "resolved": bool(matched),
            "success": success,
            "progress": 1.0 if success else 0.0,
            "message": "required object state reached" if success else "required object state not reached",
        }
    if condition_type == "object_at_receptacle":
        if target_object_id:
            matched = [item for item in objects if item.get("objectId") == target_object_id]
        else:
            matched = [item for item in objects if target_object_type and item.get("objectType") == target_object_type]
        success = any(
            _matches_receptacle_reference(
                item=item,
                success_spec=success_spec,
                objects=objects,
                flags=flags,
            )
            for item in matched
        )
        target_place_id = str(
            success_spec.get("receptacle_object_id")
            or success_spec.get("target_place_id")
            or ""
        ).strip()
        target_place_type = str(
            success_spec.get("receptacle_type")
            or success_spec.get("target_place_type")
            or ""
        ).strip()
        allowed_receptacle_ids = _normalize_receptacle_ids(success_spec.get("allowed_receptacle_object_ids"))
        if allowed_receptacle_ids:
            target_label = (
                f"{target_place_type} group ({len(allowed_receptacle_ids)} instances)"
                if target_place_type
                else f"receptacle group ({len(allowed_receptacle_ids)} instances)"
            )
        else:
            target_label = target_place_id or target_place_type or "required receptacle"
        return {
            "resolved": bool(matched) and bool(target_label),
            "success": success,
            "progress": 1.0 if success else 0.0,
            "message": (
                f"required object at receptacle {target_label}"
                if success
                else f"required object not at receptacle {target_label}"
            ),
        }
    if condition_type == "object_placed":
        placed_objects = dict(flags.get("placed_objects", {}) or {})
        target_place_id = success_spec.get("target_place_id")
        success = bool(target_object_id and placed_objects.get(target_object_id) == target_place_id)
        return {
            "resolved": True,
            "success": success,
            "progress": 1.0 if success else 0.0,
            "message": "required object placed correctly" if success else "required object not placed correctly",
        }
    return {
        "resolved": False,
        "success": False,
        "progress": 0.0,
        "message": f"unsupported success spec type: {condition_type or 'unknown'}",
    }


def evaluate_success(world_state: JSONDict, success_spec: JSONDict) -> JSONDict:
    explicit_contract = _resolve_explicit_dual_success_contract(dict(success_spec or {}))
    if explicit_contract is None:
        return _evaluate_success_single(world_state, success_spec)
    semantic_eval = _evaluate_success_single(world_state, dict(explicit_contract["semantic_spec"]))
    strict_spec = dict(explicit_contract.get("strict_spec") or {})
    strict_eval = _evaluate_success_single(world_state, strict_spec) if strict_spec else None
    return _build_dual_success_eval(
        semantic_eval=semantic_eval,
        strict_eval=strict_eval,
        primary_metric=str(explicit_contract.get("primary_metric") or "semantic"),
        secondary_metric=str(explicit_contract.get("secondary_metric") or "strict"),
        strict_unavailable_reason=explicit_contract.get("strict_unavailable_reason"),
    )


def _metadata_inventory(metadata: JSONDict) -> JSONDict:
    existing = metadata.get("inventory")
    if isinstance(existing, dict):
        return dict(existing)
    inventory_objects = list(metadata.get("inventoryObjects") or [])
    if not inventory_objects:
        return {"held_object_id": None, "held_object_type": None}
    held = dict(inventory_objects[0] or {})
    return {
        "held_object_id": held.get("objectId") or held.get("object_id"),
        "held_object_type": held.get("objectType") or held.get("object_type"),
    }


def world_state_from_metadata(metadata: JSONDict, flags: JSONDict | None = None) -> JSONDict:
    payload = dict(metadata or {})
    return {
        "objects": [dict(item) for item in list(payload.get("objects") or [])],
        "inventory": _metadata_inventory(payload),
        "flags": dict(flags or payload.get("flags") or {}),
        "agent": dict(payload.get("agent") or {}),
    }


def _report_value(report: JSONDict) -> str | None:
    for key in ("answer", "status", "state", "value", "result"):
        if report.get(key) is not None:
            return str(report[key]).strip().lower()
    return None


def evaluate_condition(condition: JSONDict, metadata: JSONDict, flags: JSONDict | None = None) -> bool:
    flags = dict(flags or {})
    condition = dict(condition or {})
    world_state = world_state_from_metadata(metadata, flags)
    if str(condition.get("type") or "").strip().lower() == "report_status":
        report = dict(flags.get("last_report") or {})
        reported = _normalize_report_status(_report_value(report)) or (_report_value(report) or "")
        eval_result = evaluate_success(world_state, condition)
        expected = _normalize_report_status(eval_result.get("expected_report_status"))
        if expected is None:
            expected = _normalize_report_status(condition.get("expected") or condition.get("value"))
        return bool(reported) if expected is None else reported == expected
    return bool(evaluate_success(world_state, condition).get("success"))


def evaluate_episode(episode: EpisodeSpec, metadata: JSONDict, flags: JSONDict | None = None) -> JudgeResult:
    condition = dict(getattr(episode, "success_spec", None) or getattr(episode, "success_condition", None) or {})
    flags = dict(flags or {})
    world_state = world_state_from_metadata(metadata, flags)
    eval_result = evaluate_success(world_state, condition)
    if str(condition.get("type") or "").strip().lower() == "report_status":
        success = evaluate_condition(condition, metadata, flags)
    else:
        success = bool(eval_result.get("success"))
    progress = float(eval_result.get("progress", 1.0 if success else estimate_progress(condition, metadata)))
    return JudgeResult(
        success=success,
        progress=progress,
        condition_type=str(condition.get("type") or "").strip().lower(),
        terminal_reason="success" if success else "ongoing",
        diagnostics={"condition": condition, **dict(eval_result)},
    )


def _objects_from_metadata(metadata: JSONDict) -> list[JSONDict]:
    return [dict(item) for item in list((metadata or {}).get("objects", []) or [])]


def estimate_progress(condition: JSONDict, metadata: JSONDict) -> float:
    object_type = str(condition.get("object_type") or condition.get("target_object_type") or "").lower()
    if not object_type:
        return 0.0
    if any(
        str(item.get("objectType") or "").lower() == object_type and item.get("visible")
        for item in _objects_from_metadata(metadata)
    ):
        return 0.5
    return 0.0


def target_object_matches(item: JSONDict | None, condition: JSONDict) -> bool:
    if not item:
        return False
    target_id = str(condition.get("target_object_id") or condition.get("object_id") or "")
    target_type = str(condition.get("target_object_type") or condition.get("object_type") or "").lower()
    if target_id and item.get("objectId") == target_id:
        return True
    if target_type and str(item.get("objectType") or "").lower() == target_type:
        return True
    return False
