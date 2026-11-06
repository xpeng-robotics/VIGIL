from vigil.data.episodes import EpisodeSpec
from vigil.envs.thor import PublicThorEnv, _scale_normalized_1000


class FakeEvent:
    def __init__(self, metadata):
        self.metadata = metadata


def _env(condition, metadata, flags=None):
    env = object.__new__(PublicThorEnv)
    env.episode = EpisodeSpec(
        episode_id="e",
        scene_id="FloorPlan1",
        task_family="test",
        instruction="",
        success_condition=condition,
    )
    env.last_event = FakeEvent(metadata)
    env.flags = dict(flags or {})
    return env


def test_object_state_target_field_value():
    env = _env(
        {"type": "object_state", "target_object_type": "Fridge", "field": "visible", "value": True},
        {"objects": [{"objectId": "f1", "objectType": "Fridge", "visible": True}]},
    )
    assert env.evaluate_success() is True


def test_agent_near_target_uses_distance_threshold():
    env = _env(
        {"type": "agent_near_target", "target_object_type": "Mug", "distance_threshold": 1.5},
        {"objects": [{"objectId": "m1", "objectType": "Mug", "distance": 1.0}]},
    )
    assert env.evaluate_success() is True


def test_object_held_uses_inventory_objects():
    env = _env(
        {"type": "object_held", "target_object_type": "Apple"},
        {"objects": [], "inventoryObjects": [{"objectId": "a1", "objectType": "Apple"}]},
    )
    assert env.evaluate_success() is True


def test_object_at_receptacle_uses_allowed_parent_receptacle():
    env = _env(
        {"type": "object_at_receptacle", "target_object_type": "Knife", "allowed_receptacle_object_ids": ["Sink|1|SinkBasin"]},
        {"objects": [{"objectId": "k1", "objectType": "Knife", "parentReceptacles": ["Sink|1|SinkBasin"]}]},
    )
    assert env.evaluate_success() is True


def test_report_status_requires_report_answer_and_oracle_condition():
    env = _env(
        {
            "type": "report_status",
            "expected": "on",
            "oracle_condition": {"type": "object_state", "target_object_type": "DeskLamp", "field": "is_toggled", "value": True},
        },
        {"objects": [{"objectId": "l1", "objectType": "DeskLamp", "visible": True, "isToggled": True}]},
        flags={"last_report": {"answer": "on"}},
    )
    assert env.evaluate_success() is True




def test_target_grounded_uses_grounding_hits():
    env = _env(
        {"type": "target_grounded", "target_object_type": "Fridge"},
        {"objects": []},
        flags={"grounding_hits": [{"object_id": "f1", "object_type": "Fridge"}]},
    )
    assert env.evaluate_success() is True


def test_report_status_derives_state_label_from_visible_public_evidence():
    env = _env(
        {
            "type": "report_status",
            "oracle_condition": {"type": "object_state", "target_object_type": "DeskLamp", "field": "is_toggled", "value": True},
        },
        {"objects": [{"objectId": "l1", "objectType": "DeskLamp", "visible": True, "isToggled": True}]},
        flags={"last_report": {"status": "on"}},
    )
    result = env.judge()
    assert result.success is True
    assert result.diagnostics["expected_report_status"] == "on"


def test_report_status_uses_fail_when_state_not_publicly_observable():
    env = _env(
        {
            "type": "report_status",
            "oracle_condition": {"type": "object_state", "target_object_type": "DeskLamp", "field": "is_toggled", "value": True},
        },
        {"objects": [{"objectId": "l1", "objectType": "DeskLamp", "visible": False, "isToggled": True}]},
        flags={"last_report": {"status": "fail"}},
    )
    result = env.judge()
    assert result.success is True
    assert result.diagnostics["expected_report_status"] == "fail"

def test_normalized_1000_coordinate_scaling():
    assert _scale_normalized_1000(0, 640) == 0
    assert _scale_normalized_1000(1000, 640) == 639
    assert _scale_normalized_1000(500, 640) == 320
    assert _scale_normalized_1000(1000, 480) == 479
