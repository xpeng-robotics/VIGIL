"""The rollout boundary must enforce the public action protocol before execution."""
import json
from dataclasses import replace

import pytest

from vigil.actions import ActionCall
from vigil.agent.backends.base import ModelBackendConfig
from vigil.agent.parser import parse_agent_response
from vigil.agent.scripted import ScriptedAgent
from vigil.eval import runner
from vigil.eval.judge import JudgeState, judge_step
from vigil.eval.settlement import settle_trace
from test_judge import _episode, _env_result
from test_live_alignment_fixes import _FakeController, _interaction_env
from test_sim_runner import _FakeThorEnv


@pytest.mark.parametrize("field", ["tools", "tool_choice", "parallel_tool_calls", "functions", "function_call"])
def test_native_tool_settings_fail_before_a_rollout(field):
    with pytest.raises(ValueError, match="Native tool calling"):
        ModelBackendConfig(base_url="https://gateway.example/v1", model="test", extra_body={field: []})


@pytest.mark.parametrize("payload", [
    {"skill_name": "pick", "arguments": {"x": 10, "y": 20}},
    {"skill_name": "act", "arguments": {"intent": "pick", "x": 10, "y": 20}},
    {"skill_name": "PickupObject", "arguments": {"object_id": "Mug|1"}},
    {"skill_name": "Interact", "arguments": {"thor_action": "PickupObject", "thor_args": {"objectId": "Mug|1"}}},
    {"skill_name": "interact_pixel", "arguments": {"x": 10, "y": 20}},
    {"skill_name": "interact_pixel", "arguments": {"intent": "act", "x": 10, "y": 20}},
    {"skill_name": "interact_pixel", "arguments": {"intent": "pick"}},
    {"skill_name": "report", "arguments": {"status": "success"}},
])
def test_invalid_public_action_never_reaches_environment_and_rescores_consistently(tmp_path, monkeypatch, payload):
    calls = []
    class GuardedEnv(_FakeThorEnv):
        def step(self, action):
            calls.append(action)
            return super().step(action)

    monkeypatch.setattr(runner, "PublicThorEnv", GuardedEnv)
    episode_path = tmp_path / "episode.json"
    episode_path.write_text(json.dumps({
        "episode_id": "boundary", "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
        "agent_init": {},
        "task": {"task_family": "PG", "instruction": "Select the mug."},
        "budget": {"max_steps": 1},
        "success_condition": {"type": "target_grounded", "target_object_type": "Mug"},
    }))
    parsed = parse_agent_response(json.dumps(payload))
    assert parsed.action is not None  # Parsing preserves the attempted action for review.
    result = runner.run_episode(episode_path=episode_path, agent=ScriptedAgent([parsed.action]),
                                out_dir=tmp_path / "run", save_frames=False)
    assert calls == []
    step = result.trace.steps[0]
    assert step.action == parsed.action
    assert step.env_status == "protocol_error" and not step.action_valid
    assert step.metadata["env_result"]["executed_arguments"] == {}
    settlement = result.trace.metadata["settlement"]
    assert settlement["protocol_failures"] == 1
    assert not settlement["world_success"] and not settlement["report_submitted"]
    uncached = replace(result.trace, metadata={k: v for k, v in result.trace.metadata.items() if k != "settlement"})
    assert settle_trace(uncached).to_dict() == settlement


@pytest.mark.parametrize("intent", ["ground", "pick", "pickup"])
def test_ground_and_pick_have_different_simulator_effects_and_pg_credit(monkeypatch, intent):
    monkeypatch.setattr("vigil.envs.thor.Controller", object)
    controller = _FakeController([])
    env = _interaction_env(controller, objects=[{
        "objectId": "Mug|1", "objectType": "Mug", "visible": True,
        "distance": 1.0, "pickupable": True,
    }], detections={"Mug|1": [0, 0, 20, 20]})
    env._interactables = []  # This fixture's default task only permits opening.
    turn = parse_agent_response(json.dumps({"skill_name": "interact_pixel", "arguments": {
        "intent": intent, "x": 10, "y": 10,
    }}))
    result = env.step(turn.action)
    assert result.action_success
    assert controller.actions == ([] if intent == "ground" else [
        {"action": "PickupObject", "objectId": "Mug|1", "forceAction": False}
    ])
    state = JudgeState(steps_used=1)
    spec = _episode({"type": "target_grounded", "target_object_type": "Mug"}, task_family="S1_pixel_grounding")
    judged = judge_step(spec=spec, state=state, env_result=result.env_result)
    assert judged.world_success is (intent == "ground")
    state.steps_used += 1
    reported = judge_step(spec=spec, state=state, env_result=_env_result("report", executed={"status": "success"}))
    assert (reported.status == "success") is (intent == "ground")
