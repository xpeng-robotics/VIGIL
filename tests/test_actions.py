import pytest

from vigil.actions import (
    ActionCall,
    get_serialized_action_registry,
    normalize_action_invocation,
    validate_action,
)


def test_action_registry_exposes_public_schema():
    names = {item["name"] for item in get_serialized_action_registry()}

    assert {"navigate", "look", "interact_pixel", "report"}.issubset(names)


def test_interact_pixel_intent_alias_normalizes():
    name, arguments = normalize_action_invocation("interact_pixel", {"intent": "open", "x": 10, "y": 20})

    assert name == "interact_pixel"
    assert arguments["intent"] == "open_access"


def test_validate_action_rejects_missing_pixel_coordinates():
    with pytest.raises(ValueError, match="missing required"):
        validate_action(ActionCall("interact_pixel", {"intent": "ground"}))


def test_validate_action_rejects_completion_report_without_status_and_summary():
    with pytest.raises(ValueError, match="missing required"):
        validate_action(ActionCall("report", {}))


def test_action_schema_describes_ground_intent_for_visual_selection():
    registry = {item["name"]: item for item in get_serialized_action_registry()}
    intent_arg = [arg for arg in registry["interact_pixel"]["arguments"] if arg["name"] == "intent"][0]

    assert "Use `ground`" in intent_arg["description"]
