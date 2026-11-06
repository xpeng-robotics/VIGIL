from dataclasses import replace
import json

import pytest

from vigil.actions import ActionCall
from vigil.data.episodes import EpisodeSpec
from vigil.envs.thor import PublicThorEnv


class _FakeEvent:
    def __init__(self, *, success=True, error=None):
        self.frame = None
        self.metadata = {
            "lastActionSuccess": success,
            "errorMessage": error,
            "objects": [],
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


def _episode():
    return EpisodeSpec(
        episode_id="e",
        scene_id="FloorPlan1",
        task_family="S2_distance_approach",
        instruction="approach the target",
        success_condition={"type": "object_state", "target_object_type": "Mug", "field": "visible", "value": True},
    )


def _env(controller):
    env = PublicThorEnv(_episode())
    env.controller = controller
    env.last_event = _FakeEvent()
    return env


def test_navigate_forward_magnitude_executes_discrete_step_count(monkeypatch):
    monkeypatch.setattr("vigil.envs.thor.Controller", object)
    controller = _FakeController([(True, None), (True, None), (True, None)])
    env = _env(controller)

    result = env.step(ActionCall("navigate", {"mode": "forward", "magnitude": 3}))

    assert controller.actions == [{"action": "MoveAhead"}] * 3
    assert result.action_success is True
    assert result.env_result is not None
    assert result.env_result.executed_arguments["magnitude"] == 3
    assert result.env_result.action_adapter["executed_step_count"] == 3
    assert result.env_result.action_adapter["thor_actions"] == [{"action": "MoveAhead"}] * 3


def test_navigate_backward_stops_on_first_low_level_failure(monkeypatch):
    monkeypatch.setattr("vigil.envs.thor.Controller", object)
    controller = _FakeController([(True, None), (False, "path_blocked"), (True, None)])
    env = _env(controller)

    result = env.step(ActionCall("navigate", {"mode": "backward", "magnitude": 3}))

    assert controller.actions == [{"action": "MoveBack"}, {"action": "MoveBack"}]
    assert result.action_success is False
    assert result.env_status == "action_failed"
    assert result.error_message == "path_blocked"
    assert result.env_result is not None
    assert result.env_result.executed_arguments["magnitude"] == 2
    assert result.env_result.action_adapter["requested_step_count"] == 3
    assert result.env_result.action_adapter["executed_step_count"] == 2


@pytest.mark.parametrize("phase", ["CreateHouse", "TeleportFull", "Pass", "OpenObject"])
@pytest.mark.parametrize("success", [False, None, "true"])
def test_reset_refuses_failed_or_unconfirmed_initialization(monkeypatch, phase, success):
    episode = replace(_episode(), scene_setup=({"action": "OpenObject", "objectId": "target"},
                                               {"action": "Pass"}))
    if phase == "CreateHouse":
        episode = replace(episode, scene={"platform": "procthor", "house": {}})
    elif phase == "TeleportFull":
        episode = replace(episode, agent_init={"position": {"x": 0, "y": 1, "z": 0}})
    outcomes = [(True, None)] if phase == "OpenObject" else []
    controller = _FakeController([*outcomes, (success, "injected setup failure")])
    monkeypatch.setattr("vigil.envs.thor.Controller", lambda **kwargs: controller)
    env = PublicThorEnv(episode)
    with pytest.raises(RuntimeError, match=phase):
        env.reset()
    assert controller.actions[-1]["action"] == phase
    assert len(controller.actions) == len(outcomes) + 1


def test_reset_keeps_successful_setup_order(monkeypatch):
    setup = ({"action": "OpenObject", "objectId": "target"}, {"action": "Pass"})
    episode = replace(_episode(), scene={"platform": "procthor", "house": {"rooms": []}},
                      agent_init={"position": {"x": 0, "y": 1, "z": 0}}, scene_setup=setup)
    controller = _FakeController([])
    monkeypatch.setattr("vigil.envs.thor.Controller", lambda **kwargs: controller)
    observation = PublicThorEnv(episode).reset()
    assert [a["action"] for a in controller.actions] == ["CreateHouse", "TeleportFull", "OpenObject", "Pass"]
    assert controller.actions[-2:] == list(setup)
    assert observation.metadata["lastActionSuccess"] is True


@pytest.mark.parametrize("action,field,desired", [("ToggleObjectOn", "isToggled", True),
                                                ("ToggleObjectOff", "isToggled", False),
                                                ("OpenObject", "isOpen", True),
                                                ("CloseObject", "isOpen", False)])
@pytest.mark.parametrize("already_satisfied", [True, False])
def test_setup_state_setters_require_confirmed_target_state(monkeypatch, action, field, desired, already_satisfied):
    observed = desired if already_satisfied else not desired
    class StateController(_FakeController):
        def step(self, **kwargs):
            event = super().step(**kwargs)
            event.metadata["objects"] = [{"objectId": "target", "toggleable": True, "openable": True,
                                          field: observed, "openness": float(observed)}]
            return event
    controller = StateController([(True, None), (False, "already in requested state")])
    monkeypatch.setattr("vigil.envs.thor.Controller", lambda **kwargs: controller)
    episode = replace(_episode(), scene_setup=({"action": action, "objectId": "target"},))
    env = PublicThorEnv(episode)
    if already_satisfied:
        env.reset()
        assert env.initialization_checks[-1]["confirmed_existing_state"][field] is desired
        assert env.initialization_checks[-1]["simulator_success"] is False
    else:
        with pytest.raises(RuntimeError, match=action):
            env.reset()


@pytest.mark.parametrize("change", [{"objectId": "another"}, {"toggleable": False}, {"isToggled": 1}])
def test_already_set_state_requires_exact_object_and_boolean_evidence(change):
    from vigil.envs.thor import _confirmed_setup_state
    target = {"objectId": "target", "toggleable": True, "isToggled": True, **change}
    assert _confirmed_setup_state({"action": "ToggleObjectOn", "objectId": "target"}, {"objects": [target]}) is None


def test_partly_open_object_does_not_confirm_a_fully_open_setup():
    from vigil.envs.thor import _confirmed_setup_state
    target = {"objectId": "target", "openable": True, "isOpen": True, "openness": 0.5}
    assert _confirmed_setup_state({"action": "OpenObject", "objectId": "target"}, {"objects": [target]}) is None


def test_setup_failure_stops_before_model_call_and_is_not_scored(tmp_path, monkeypatch):
    from vigil.eval.runner import run_episode
    from vigil.eval.offline import evaluate_trace_files

    class NeverCalledAgent:
        def act(self, observation):
            pytest.fail("The model must not be called after failed scene initialization")

    controller = _FakeController([(False, "invalid initial pose")])
    stopped = []
    controller.stop = lambda: stopped.append(True)
    monkeypatch.setattr("vigil.envs.thor.Controller", lambda **kwargs: controller)
    path = tmp_path / "episode.json"
    path.write_text(json.dumps({"episode_id": "initialization-failure", "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                               "agent_init": {"position": {"x": 0, "y": 1, "z": 0}},
                               "task": {"task_family": "test", "instruction": "finish"},
                               "budget": {"max_steps": 3}, "success_condition": {"type": "report_only"}}))
    result = run_episode(episode_path=path, agent=NeverCalledAgent(), out_dir=tmp_path / "out", save_frames=False)
    assert result.trace.steps[0].env_status == "simulator_error"
    assert "TeleportFull" in result.trace.steps[0].error_type
    assert result.trace.metadata["initialization_checks"][0]["simulator_success"] is False
    assert stopped == [True]
    with pytest.raises(ValueError, match="infrastructure error"):
        evaluate_trace_files([result.trace_path])
