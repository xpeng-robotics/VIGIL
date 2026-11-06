from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

JSONDict = dict[str, Any]

CANONICAL_INTENTS = (
    "ground",
    "open_access",
    "close_access",
    "pick",
    "place",
    "activate",
    "deactivate",
    "drop",
)
_INTENT_ALIASES = {
    "open": "open_access",
    "close": "close_access",
    "toggle_on": "activate",
    "toggle_off": "deactivate",
    "pickup": "pick",
    "put": "place",
    "put_down": "place",
    "point": "ground",
    "locate": "ground",
    "tap": "ground",
}
_NAVIGATE_MODES: frozenset[str] = frozenset({"forward", "backward", "turn_left", "turn_right"})
_LOOK_DIRECTIONS: frozenset[str] = frozenset({"up", "down"})
_REPORT_STATUSES: frozenset[str] = frozenset({"success", "fail", "unsafe", "invalid", "on", "off", "open", "closed"})


@dataclass(frozen=True)
class ArgumentSpec:
    name: str
    type: str
    description: str

    def to_dict(self) -> JSONDict:
        return asdict(self)


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    required_arguments: tuple[str, ...]
    arguments: tuple[ArgumentSpec, ...]

    def to_dict(self) -> JSONDict:
        return {
            "name": self.name,
            "description": self.description,
            "required_arguments": list(self.required_arguments),
            "arguments": [argument.to_dict() for argument in self.arguments],
        }


ACTION_REGISTRY: dict[str, ActionSpec] = {
    "navigate": ActionSpec(
        name="navigate",
        description=(
            "Translation along the agent forward/backward axis or rotation about the vertical axis, "
            "in the current egocentric frame."
        ),
        required_arguments=("mode", "magnitude"),
        arguments=(
            ArgumentSpec("mode", "enum", "One of: forward, backward, turn_left, turn_right."),
            ArgumentSpec(
                "magnitude",
                "number",
                "For forward/backward, a positive integer step count. For turn_left/turn_right, rotation in degrees.",
            ),
        ),
    ),
    "look": ActionSpec(
        name="look",
        description="Change camera pitch without changing agent position.",
        required_arguments=("direction", "magnitude"),
        arguments=(
            ArgumentSpec("direction", "enum", "One of: up, down."),
            ArgumentSpec("magnitude", "number", "How far to look up or down, in degrees."),
        ),
    ),
    "interact_pixel": ActionSpec(
        name="interact_pixel",
        description=(
            "Issue a local embodied interaction at image coordinates (x, y) with the given intent. "
            "The agent must be within 1.5 m of the target object for the interaction to succeed; "
            "navigate closer first if the object appears far away. "
            "Provide x and y for all intents except `drop`, which operates on the currently held object. "
            "After state-changing attempts such as open/close/toggle, inspect the next frame before repeating the same interaction."
        ),
        required_arguments=("intent",),
        arguments=(
            ArgumentSpec("x", "int_px", "Horizontal coordinate; required unless intent is `drop`."),
            ArgumentSpec("y", "int_px", "Vertical coordinate; required unless intent is `drop`."),
            ArgumentSpec(
                "intent",
                "enum",
                "Canonical values: "
                f"{', '.join(CANONICAL_INTENTS)}. "
                "Use `ground` to select or point to a target in the image without changing world state. "
                "Use `pick` to physically pick up and hold an object, not merely select it in the image.",
            ),
        ),
    ),
    "report": ActionSpec(
        name="report",
        description="Terminal self-report signal with a short summary.",
        required_arguments=("status", "summary"),
        arguments=(
            ArgumentSpec("status", "enum", "One of: success, fail, unsafe, invalid, on, off, open, closed."),
            ArgumentSpec("summary", "string", "Brief justification for the status."),
        ),
    ),
}
PUBLIC_SKILLS = set(ACTION_REGISTRY)


@dataclass(frozen=True)
class ActionCall:
    skill_name: str
    arguments: JSONDict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: JSONDict) -> "ActionCall":
        skill_name = payload.get("skill_name")
        arguments = payload.get("arguments", {})
        if not isinstance(skill_name, str) or not skill_name.strip():
            raise ValueError("Action must contain a non-empty string 'skill_name'.")
        if not isinstance(arguments, dict):
            raise ValueError("Action 'arguments' must be an object.")
        return cls(skill_name=skill_name.strip(), arguments=dict(arguments))

    def to_dict(self) -> JSONDict:
        return asdict(self)


def get_action_registry() -> dict[str, ActionSpec]:
    return ACTION_REGISTRY


def get_serialized_action_registry() -> list[JSONDict]:
    return [spec.to_dict() for spec in ACTION_REGISTRY.values()]


def normalize_interaction_intent(intent: str) -> str:
    normalized = str(intent or "").strip().lower()
    return _INTENT_ALIASES.get(normalized, normalized)


def normalize_action_invocation(
    action_name: str,
    arguments: JSONDict,
    *,
    strict: bool = False,
) -> tuple[str, JSONDict]:
    name = str(action_name or "").strip()
    args = dict(arguments or {})

    if name == "interact_pixel":
        intent = args.get("intent")
        if intent is not None and not strict:
            args["intent"] = normalize_interaction_intent(str(intent))
        for xy in ("x", "y"):
            if xy in args and isinstance(args[xy], (list, tuple)) and len(args[xy]) > 0:
                args[xy] = args[xy][0]

    if not strict and name == "report":
        for key in list(args.keys()):
            if key.lower() == "status" and key != "status":
                args["status"] = args.pop(key)
        if "status" in args:
            args["status"] = str(args["status"]).strip().lower()

    return name, args


def validate_action(action: ActionCall, *, strict_skill_set: bool = False) -> None:
    if not action.skill_name:
        raise ValueError("Action skill_name cannot be empty.")
    if strict_skill_set and action.skill_name not in PUBLIC_SKILLS:
        choices = ", ".join(sorted(PUBLIC_SKILLS))
        raise ValueError(f"Unsupported public skill {action.skill_name!r}. Available skills: {choices}")
    if action.skill_name in ACTION_REGISTRY:
        validate_action_invocation(action.skill_name, action.arguments)


def validate_action_invocation(action_name: str, arguments: JSONDict, *, strict: bool = False) -> None:
    name, args = normalize_action_invocation(action_name, arguments, strict=strict)
    spec = ACTION_REGISTRY.get(name)
    if spec is None:
        known = ", ".join(sorted(ACTION_REGISTRY.keys()))
        raise ValueError(f"Unknown action '{name}'. Available: {known}")
    required_arguments = list(spec.required_arguments)
    if name == "interact_pixel":
        raw_intent = args.get("intent")
        resolved_intent = str(raw_intent or "").strip() if strict else normalize_interaction_intent(str(raw_intent or ""))
        if resolved_intent != "drop":
            required_arguments.extend(["x", "y"])
    missing = [arg for arg in required_arguments if arg not in args]
    if missing:
        raise ValueError(f"Action '{name}' missing required arguments: {missing}")
    missing_values = [arg for arg in required_arguments if args.get(arg) is None]
    if missing_values:
        raise ValueError(f"Action '{name}' required arguments must not be null: {missing_values}")
    arg_specs = {a.name: a for a in spec.arguments}
    for key, value in args.items():
        arg_spec = arg_specs.get(key)
        if arg_spec is None:
            continue
        if arg_spec.type in ("number", "int_px") and value is not None:
            try:
                coerce_numeric_argument(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Action '{name}' argument '{key}' must be numeric, got: {value!r}") from exc

    if name == "navigate":
        mode = str(args.get("mode", "")).strip().lower()
        if mode not in _NAVIGATE_MODES:
            raise ValueError(f"Action 'navigate' argument 'mode' must be one of {sorted(_NAVIGATE_MODES)!r}")
        if mode in {"forward", "backward"}:
            try:
                coerce_discrete_step_count(args.get("magnitude"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Action 'navigate' argument 'magnitude' must be a positive integer when mode is "
                    f"{mode!r}."
                ) from exc
    elif name == "look":
        direction = str(args.get("direction", "")).strip().lower()
        if direction not in _LOOK_DIRECTIONS:
            raise ValueError(f"Action 'look' argument 'direction' must be one of {sorted(_LOOK_DIRECTIONS)!r}")
    elif name == "interact_pixel":
        raw_intent = args.get("intent")
        intent = str(raw_intent or "").strip() if strict else normalize_interaction_intent(str(raw_intent or ""))
        if intent not in CANONICAL_INTENTS:
            raise ValueError(
                "Action 'interact_pixel' argument 'intent' must be one of "
                f"{list(CANONICAL_INTENTS)!r}, got {raw_intent!r}"
            )
    elif name == "report":
        status = str(args.get("status", "")).strip().lower()
        if status not in _REPORT_STATUSES:
            raise ValueError(f"Action 'report' argument 'status' must be one of {sorted(_REPORT_STATUSES)!r}")


def coerce_numeric_argument(value: Any) -> float:
    if isinstance(value, (list, tuple)):
        for item in value:
            try:
                return coerce_numeric_argument(item)
            except (TypeError, ValueError):
                continue
        raise ValueError(f"must be numeric, got sequence: {value!r}")
    return float(value)


def coerce_discrete_step_count(value: Any) -> int:
    numeric = coerce_numeric_argument(value)
    rounded = int(round(numeric))
    if rounded < 1 or abs(float(numeric) - float(rounded)) > 1e-6:
        raise ValueError(f"must be a positive integer step count, got: {value!r}")
    return rounded
