from vigil.actions import ActionCall
from vigil.data.episodes import EpisodeSpec
from vigil.eval.scoring import aggregate_scores, score_episode
from vigil.eval.traces import EpisodeTrace
from vigil.envs.thor import PublicThorEnv


class _FakeEvent:
    def __init__(self, *, success=True, error=None, objects=None, detections=None):
        self.frame = None
        self.instance_detections2D = dict(detections or {})
        self.instance_segmentation_frame = None
        self.color_to_object_id = {}
        self.metadata = {
            "lastActionSuccess": success,
            "errorMessage": error,
            "objects": [dict(item) for item in list(objects or [])],
            "inventoryObjects": [],
            "inventory": {},
            "agent": {},
        }


class _FakeController:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.actions = []

    def step(self, **kwargs):
        self.actions.append(dict(kwargs))
        if self.outcomes:
            success, error = self.outcomes.pop(0)
        else:
            success, error = True, None
        return _FakeEvent(success=success, error=error)


def _interaction_episode():
    return EpisodeSpec(
        episode_id="interact",
        scene_id="FloorPlan1",
        task_family="T1_grounded_interaction",
        instruction="open the mug",
        success_condition={
            "type": "object_state",
            "target_object_type": "Mug",
            "field": "is_open",
            "value": True,
        },
        scene={"platform": "ithor", "scene_id": "FloorPlan1", "controller": {"interaction_distance_limit": 1.5}},
        generation_hints={
            "interactables": [
                {
                    "interactable_id": "mug_open",
                    "target_object_type": "Mug",
                    "intent": "open",
                    "distance_limit": 1.5,
                    "visibility_required": True,
                    "thor_action": {"action": "OpenObject"},
                }
            ]
        },
    )


def _interaction_env(controller, *, objects, detections):
    env = PublicThorEnv(_interaction_episode())
    env.controller = controller
    env.last_event = _FakeEvent(objects=objects, detections=detections)
    return env


def test_interact_pixel_rejects_too_far_candidate_before_thor_action(monkeypatch):
    monkeypatch.setattr("vigil.envs.thor.Controller", object)
    controller = _FakeController([(True, None)])
    env = _interaction_env(
        controller,
        objects=[
            {
                "objectId": "Mug|1",
                "objectType": "Mug",
                "visible": True,
                "distance": 4.0,
                "openable": True,
                "isOpen": False,
            }
        ],
        detections={"Mug|1": [0, 0, 20, 20]},
    )

    result = env.step(ActionCall("interact_pixel", {"intent": "open_access", "x": 10, "y": 10}))

    assert controller.actions == []
    assert result.action_success is False
    assert result.error_message == "too_far"
    assert result.env_result is not None
    assert result.env_result.target_resolved is True
    assert result.env_result.resolved_target == {"object_id": "Mug|1", "object_type": "Mug"}
    assert result.env_result.action_adapter["validation_error"] == "too_far"


def test_interact_pixel_rejects_unsupported_intent_before_thor_action(monkeypatch):
    monkeypatch.setattr("vigil.envs.thor.Controller", object)
    controller = _FakeController([(True, None)])
    env = _interaction_env(
        controller,
        objects=[
            {
                "objectId": "Mug|1",
                "objectType": "Mug",
                "visible": True,
                "distance": 1.0,
                "openable": True,
                "isOpen": False,
            }
        ],
        detections={"Mug|1": [0, 0, 20, 20]},
    )

    result = env.step(ActionCall("interact_pixel", {"intent": "activate", "x": 10, "y": 10}))

    assert controller.actions == []
    assert result.action_success is False
    assert result.error_message == "intent_not_supported"
    assert result.env_result is not None
    assert result.env_result.action_adapter["candidate"]["supported_intents"] == ["ground", "open_access"]


def test_release_trace_populates_behavior_metrics_for_live_aggregates():
    trace = EpisodeTrace.from_dict(
        {
            "episode_id": "live_trace_001",
            "profile": "pure_rgb_dialogue_history_baseline",
            "max_steps": 5,
            "terminal_status": "failure",
            "metadata": {"task_family": "T1_grounded_interaction"},
            "steps": [
                {
                    "step_index": 0,
                    "action": {"skill_name": "interact_pixel", "arguments": {"intent": "pick", "x": 10, "y": 10}},
                    "action_valid": True,
                    "progress": 0.0,
                    "metadata": {
                        "judge_result": {
                            "failure_label": "too_far",
                            "recoverable": True,
                            "invalid_action": False,
                            "protocol_failure": False,
                            "world_success": False,
                        }
                    },
                },
                {
                    "step_index": 1,
                    "action": {"skill_name": "navigate", "arguments": {"mode": "forward", "magnitude": 1}},
                    "action_valid": True,
                    "progress": 0.0,
                    "metadata": {
                        "judge_result": {
                            "recoverable": False,
                            "invalid_action": False,
                            "protocol_failure": False,
                            "world_success": False,
                        }
                    },
                },
                {
                    "step_index": 2,
                    "action": {"skill_name": "report", "arguments": {"status": "fail", "summary": "not done"}},
                    "action_valid": True,
                    "progress": 0.0,
                    "terminal": True,
                    "metadata": {
                        "judge_result": {
                            "report_status": "fail",
                            "report_matches_world": True,
                            "recoverable": False,
                            "invalid_action": False,
                            "protocol_failure": False,
                            "world_success": False,
                        }
                    },
                },
            ],
        }
    )

    aggregate = aggregate_scores([score_episode(trace)]).to_dict()
    behavior = aggregate["behavior_metrics_summary"]

    assert behavior["first_interact_step"] == 1.0
    assert behavior["first_report_step"] == 3.0
    assert behavior["too_far_count"] == 1.0
    assert behavior["reposition_after_too_far_rate"] == 1.0
