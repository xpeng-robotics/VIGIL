import json
from pathlib import Path

import pytest

from vigil.actions import ActionCall, PUBLIC_SKILLS
from vigil.data.paths import CANONICAL_PACK
from vigil.agent import AgentObservation, AgentTurnResult
from vigil.agent.backends import ModelBackendConfig, build_multimodal_user_message, extract_chat_text
from vigil.agent.profiles import get_profile
from vigil.eval.traces import StepTrace
from vigil.agent.model import OpenAIModelAgent
from vigil.agent.scripted import ScriptedAgent, load_scripted_agent
from vigil.agent.prompts import build_agent_prompt
from vigil.data.paths import resolve_episode_path
from vigil.eval.runner import format_dialogue_history

ROOT = Path(__file__).resolve().parents[1]


def test_all_canonical_episode_jsons_present():
    pack = json.loads((ROOT / "data/benchmark/packs" / CANONICAL_PACK).read_text())
    missing = [
        row["episode_id"]
        for row in pack["episodes"]
        if not (ROOT / "data/episodes" / row["episode_id"] / "episode.json").exists()
    ]
    assert len(pack["episodes"]) == 1000
    assert missing == []


def test_resolve_episode_path_by_id():
    path = resolve_episode_path(
        "ithor_fp1_s1_pixel_grounding_easy_fridge_ground_001",
        ROOT / "data/episodes",
    )
    assert path.name == "episode.json"
    assert path.exists()


def test_scripted_agent_returns_actions():
    agent = ScriptedAgent([ActionCall("Stop", {})])
    result = agent.act(type("Obs", (), {"episode_id": "e", "step_index": 0, "instruction": "", "image_path": None})())
    assert result.action is not None
    assert result.action.skill_name == "Stop"


def test_load_scripted_agent_from_json():
    agent = load_scripted_agent('[{"skill_name":"Stop","arguments":{}}]', None)
    assert agent is not None
    assert agent.act(type("Obs", (), {"episode_id": "e", "step_index": 0, "instruction": "", "image_path": None})()).action.skill_name == "Stop"


def test_multimodal_message_without_image():
    message = build_multimodal_user_message("hello", None)
    assert message == {"role": "user", "content": "hello"}


def test_extract_chat_text_openai_shape():
    payload = {"choices": [{"message": {"content": "{\"skill_name\":\"Stop\",\"arguments\":{}}"}}]}
    assert "Stop" in extract_chat_text(payload)


def test_public_skills_include_vigil_native_contract():
    assert {"navigate", "look", "interact_pixel", "report"}.issubset(PUBLIC_SKILLS)


def test_canonical_procthor_scene_assets_present():
    pack = json.loads((ROOT / "data/benchmark/packs" / CANONICAL_PACK).read_text())
    refs = set()
    for row in pack["episodes"]:
        episode_path = ROOT / "data/episodes" / row["episode_id"] / "episode.json"
        episode = json.loads(episode_path.read_text())
        if episode.get("scene", {}).get("platform") == "procthor":
            refs.add(episode.get("scene_ref") or episode["scene"].get("scene_id"))
    missing = [ref for ref in refs if not (ROOT / "data/scenes" / ref / "house.json").exists()]
    assert len(refs) == 456
    assert missing == []


def test_prompt_uses_native_system_and_observation_contract():
    history = format_dialogue_history([StepTrace(step_index=0, action=ActionCall("navigate", {"mode": "forward", "magnitude": 1}), env_status="success", progress=0.25)])
    obs = type("Obs", (), {"episode_id": "e", "step_index": 0, "instruction": "Find the mug.", "text": history, "image_path": None})()
    prompt = build_agent_prompt(obs)
    assert "## Allowed actions" in prompt
    assert "Use only public evidence from this episode" in prompt
    assert "## Output format" in prompt
    assert "frame_id" in prompt


class _FakeThorResult:
    action_success = True
    env_status = "success"
    error_message = None
    progress = 1.0
    judge_success = True
    terminal = True
    diagnostics = {}


class _FakeThorEnv:
    def __init__(self, episode, **kwargs):
        self.episode = episode

    def reset(self):
        return None

    def save_frame(self, path):
        return None

    def estimate_progress(self):
        return 0.25

    def step(self, action):
        return _FakeThorResult()

    def close(self):
        return None


class _BlackFrameEvent:
    frame = [[[0, 0, 0], [0, 0, 0]], [[0, 0, 0], [0, 0, 0]]]
    metadata = {}


class _BlackFrameEnv(_FakeThorEnv):
    def __init__(self, episode, **kwargs):
        super().__init__(episode, **kwargs)
        self.last_event = _BlackFrameEvent()

    def save_frame(self, path):
        return Path(path)




class _NonTerminalSuccessResult:
    action_success = True
    env_status = "success"
    error_message = None
    progress = 1.0
    judge_success = True
    terminal = False
    diagnostics = {"expected_report_status": "success"}


class _NonTerminalSuccessEnv(_FakeThorEnv):
    def step(self, action):
        return _NonTerminalSuccessResult()


class _OneActionAgent:
    def __init__(self):
        self.calls = 0

    def act(self, observation: AgentObservation) -> AgentTurnResult:
        self.calls += 1
        return AgentTurnResult(
            action=ActionCall("interact_pixel", {"intent": "ground", "x": 10, "y": 20}),
            raw_response='{"skill_name":"interact_pixel","arguments":{"intent":"ground","x":10,"y":20}}',
        )

class _MetadataAgent:
    def act(self, observation: AgentObservation) -> AgentTurnResult:
        return AgentTurnResult(
            action=ActionCall("report", {"status": "success", "summary": "done"}),
            raw_response='{"skill_name":"report","arguments":{"status":"success","summary":"done"}}',
            metadata={"usage": {"total_tokens": 3}, "skill_name_coerced_from": "done"},
        )


def test_run_episode_preserves_profile_and_turn_metadata(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner

    episode_dir = tmp_path / "episodes" / "episode_001"
    episode_dir.mkdir(parents=True)
    episode_path = episode_dir / "episode.json"
    episode_path.write_text(
        json.dumps(
            {
                "episode_id": "episode_001",
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "test", "instruction": "finish"},
                "budget": {"max_steps": 3},
                "success_condition": {"type": "report_only"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sim_runner, "PublicThorEnv", _FakeThorEnv)

    result = sim_runner.run_episode(
        episode_path=episode_path,
        agent=_MetadataAgent(),
        out_dir=tmp_path / "out",
        save_frames=False,
        profile="custom_profile",
    )

    assert result.trace.profile == "custom_profile"
    step_metadata = result.trace.steps[0].metadata
    assert step_metadata["raw_response"].startswith('{"skill_name"')
    assert step_metadata["agent_turn"]["usage"] == {"total_tokens": 3}
    assert step_metadata["agent_turn"]["skill_name_coerced_from"] == "done"


def test_run_episode_serializes_agent_profile_to_trace_json(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner

    episode_dir = tmp_path / "episodes" / "episode_profile_object"
    episode_dir.mkdir(parents=True)
    episode_path = episode_dir / "episode.json"
    episode_path.write_text(
        json.dumps(
            {
                "episode_id": "episode_profile_object",
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "test", "instruction": "finish"},
                "budget": {"max_steps": 3},
                "success_condition": {"type": "report_only"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sim_runner, "PublicThorEnv", _FakeThorEnv)

    profile = get_profile()
    result = sim_runner.run_episode(
        episode_path=episode_path,
        agent=_MetadataAgent(),
        out_dir=tmp_path / "out",
        save_frames=False,
        profile=profile,
    )

    payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
    assert payload["profile"] == profile.name
    assert payload["metadata"]["profile"]["name"] == profile.name
    assert payload["metadata"]["profile"]["metadata"]["conversation_history_turns"] == 20


def test_run_episode_fails_fast_on_black_model_frame(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner

    episode_dir = tmp_path / "episodes" / "episode_black_frame"
    episode_dir.mkdir(parents=True)
    episode_path = episode_dir / "episode.json"
    episode_path.write_text(
        json.dumps(
            {
                "episode_id": "episode_black_frame",
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "test", "instruction": "finish"},
                "budget": {"max_steps": 3},
                "success_condition": {"type": "report_only"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sim_runner, "PublicThorEnv", _BlackFrameEnv)

    with pytest.raises(sim_runner.BlackFrameError, match="black rendered frame"):
        sim_runner.run_episode(
            episode_path=episode_path,
            agent=_MetadataAgent(),
            out_dir=tmp_path / "out",
        )

    assert not (tmp_path / "out" / "traces" / "episode_black_frame.json").exists()
    assert not (tmp_path / "out" / "scores" / "episode_black_frame.score.json").exists()


def test_run_episode_trace_metadata_preserves_public_buckets(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner

    episode_dir = tmp_path / "episodes" / "episode_metadata"
    episode_dir.mkdir(parents=True)
    episode_path = episode_dir / "episode.json"
    episode_path.write_text(
        json.dumps(
            {
                "episode_id": "episode_metadata",
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "S4_state_recognition", "instruction": "finish"},
                "budget": {"max_steps": 3},
                "success_condition": {"type": "report_only"},
                "trace_hints": {
                    "difficulty": "na",
                    "functional_template": "verify_open_state",
                    "target_object_type": "Fridge",
                    "target_group": "container_access",
                    "primary_capabilities": ["SR", "TM"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sim_runner, "PublicThorEnv", _FakeThorEnv)

    result = sim_runner.run_episode(
        episode_path=episode_path,
        agent=_MetadataAgent(),
        out_dir=tmp_path / "out",
        save_frames=False,
        pack_id="mixed_mainline_manual_first_balanced_1000_v1",
        pack_platform="mixed",
    )

    metadata = result.trace.metadata
    assert metadata["benchmark_mode"] == "pure_model"
    assert metadata["contract_version"] == "vigil_native_v1"
    assert metadata["pack_id"] == "mixed_mainline_manual_first_balanced_1000_v1"
    assert metadata["platform"] == "mixed"
    assert metadata["scene_platform"] == "ithor"
    assert metadata["difficulty"] == "na"
    assert metadata["functional_template"] == "verify_open_state"
    assert metadata["target_object_type"] == "Fridge"
    assert metadata["target_group"] == "container_access"
    assert metadata["primary_capabilities"] == ["SR", "TM"]
    result_payload = result.score.to_result_dict()
    assert result_payload["functional_template"] == "verify_open_state"
    assert result_payload["target_group"] == "container_access"



def test_run_episode_does_not_stop_on_world_success_without_report(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner

    episode_dir = tmp_path / "episodes" / "episode_no_report"
    episode_dir.mkdir(parents=True)
    episode_path = episode_dir / "episode.json"
    episode_path.write_text(
        json.dumps(
            {
                "episode_id": "episode_no_report",
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "S1_pixel_grounding", "instruction": "ground fridge"},
                "budget": {"max_steps": 2},
                "success_condition": {"type": "target_grounded", "target_object_type": "Fridge"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sim_runner, "PublicThorEnv", _NonTerminalSuccessEnv)
    agent = _OneActionAgent()

    result = sim_runner.run_episode(
        episode_path=episode_path,
        agent=agent,
        out_dir=tmp_path / "out",
        save_frames=False,
    )

    assert agent.calls == 2
    assert len(result.trace.steps) == 2
    assert result.trace.terminal_status == "timeout"
    assert result.score.terminal_status == "failure"
    assert result.score.score_summary["diagnostics"]["report_submitted"] is False
    assert result.score.primary_score == 0.1
    assert result.trace.steps[0].metadata["env_result"]["diagnostics"]["expected_report_status"] == "success"

class _StrategySurfaceAgent:
    def act(self, observation: AgentObservation) -> AgentTurnResult:
        return AgentTurnResult(
            action=ActionCall("navigate", {"mode": "forward", "magnitude": 1}),
            raw_response='{"skill_surface":"strategy","skill_name":"navigate","arguments":{"mode":"forward","magnitude":1}}',
            metadata={"skill_surface": "strategy"},
        )


class _NoStepEnv(_FakeThorEnv):
    def step(self, action):
        raise AssertionError("strategy surface should not be executed as an environment action")


def test_run_episode_rejects_non_action_skill_surface(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner

    episode_dir = tmp_path / "episodes" / "episode_surface"
    episode_dir.mkdir(parents=True)
    episode_path = episode_dir / "episode.json"
    episode_path.write_text(
        json.dumps(
            {
                "episode_id": "episode_surface",
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "test", "instruction": "finish"},
                "budget": {"max_steps": 3},
                "success_condition": {"type": "report_only"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sim_runner, "PublicThorEnv", _NoStepEnv)

    result = sim_runner.run_episode(
        episode_path=episode_path,
        agent=_StrategySurfaceAgent(),
        out_dir=tmp_path / "out",
        save_frames=False,
    )

    step = result.trace.steps[0]
    assert step.env_status == "protocol_error"
    assert step.action is not None
    assert step.action.skill_name == "navigate"
    assert "Runtime engine only executes action skills" in step.error_type
    assert step.metadata["judge_result"]["protocol_failure"] is True


class _ResetFailEnv(_FakeThorEnv):
    def reset(self):
        raise TimeoutError("Reading from AI2-THOR backend timed out")


def test_run_episode_records_simulator_reset_failure(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner

    episode_dir = tmp_path / "episodes" / "episode_reset_fail"
    episode_dir.mkdir(parents=True)
    episode_path = episode_dir / "episode.json"
    episode_path.write_text(
        json.dumps(
            {
                "episode_id": "episode_reset_fail",
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "test", "instruction": "finish"},
                "budget": {"max_steps": 3},
                "success_condition": {"type": "report_only"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sim_runner, "PublicThorEnv", _ResetFailEnv)

    result = sim_runner.run_episode(
        episode_path=episode_path,
        agent=_MetadataAgent(),
        out_dir=tmp_path / "out",
        save_frames=False,
    )

    assert result.trace_path.exists()
    assert result.score_path.exists()
    assert result.trace.terminal_status == "failure"
    assert result.score.terminal_status == "failure"
    assert result.score.terminal_reason == "simulator_error"
    assert result.score.settlement["steps_used"] == 1
    step = result.trace.steps[0]
    assert step.env_status == "simulator_error"
    assert step.action_valid is False
    assert "AI2-THOR backend timed out" in step.error_type


def test_openai_model_agent_records_model_request_error(monkeypatch):
    class BrokenClient:
        def chat(self, messages, *, json_mode=True):
            raise RuntimeError("HTTP 400: context too long")

    monkeypatch.setattr("vigil.agent.model.create_model_client", lambda config: BrokenClient())
    agent = OpenAIModelAgent(ModelBackendConfig(base_url="http://x", model="m"))

    result = agent.act(AgentObservation(episode_id="e", step_index=0, instruction="do it"))

    assert result.action is None
    assert result.parse_error is not None
    assert "model_request_error" in result.parse_error
    assert "context too long" in result.parse_error

def test_dialogue_history_excludes_evaluator_feedback_and_limits_turns():
    long_error = "InvalidOperationException: target failed. trace: " + "stack " * 200
    steps = [
        StepTrace(
            step_index=i,
            action=ActionCall("interact_pixel", {"intent": "pick", "x": 10, "y": 20}),
            env_status="action_failed",
            action_valid=False,
            progress=0.5,
            error_type=long_error,
        )
        for i in range(5)
    ]

    history = format_dialogue_history(steps, max_turns=2)

    assert '"step":3' in history
    assert '"step":2' not in history
    assert "trace:" not in history
    assert "stack" not in history
    assert len(history) < 1000



def test_prompt_includes_normalized_1000_coordinate_policy():
    obs = AgentObservation(episode_id="e", step_index=0, instruction="point to the mug")
    prompt = build_agent_prompt(obs, coord_mode="normalized_1000", coord_prompt_mode="explicit")

    assert "normalized_1000" in prompt
    assert "[0, 1000]" in prompt
    assert "top-left" in prompt


def test_openai_model_agent_uses_native_system_user_history_messages(monkeypatch):
    captured = []

    class CapturingClient:
        def chat(self, messages, *, json_mode=True):
            captured.append((messages, json_mode))
            return type(
                "Response",
                (),
                {
                    "content": '{"skill_name":"report","arguments":{"status":"fail","summary":"not done"}}',
                    "raw_response": {"ok": True},
                    "reasoning": None,
                    "usage": {"request_count": 1},
                },
            )()

    monkeypatch.setattr("vigil.agent.model.create_model_client", lambda config: CapturingClient())
    agent = OpenAIModelAgent(ModelBackendConfig(base_url="http://x", model="m"))
    obs = AgentObservation(
        episode_id="episode_1",
        step_index=0,
        instruction="Select the mug.",
        metadata={"history_turns": 1, "image_size": {"width": 640, "height": 480}},
    )

    agent.act(obs)
    agent.act(AgentObservation(episode_id="episode_1", step_index=1, instruction="Select the mug.", metadata={"history_turns": 1}))

    first_messages, first_json_mode = captured[0]
    second_messages, _ = captured[1]
    assert first_json_mode is True
    assert [message["role"] for message in first_messages] == ["system", "user"]
    assert "## Allowed actions" in first_messages[0]["content"]
    assert [message["role"] for message in second_messages] == ["system", "user", "assistant", "user"]


def test_startup_notification_follows_reset_and_precedes_model_action(tmp_path, monkeypatch):
    from vigil.eval import runner as sim_runner
    events=[]
    class ReadyEnv(_FakeThorEnv):
        def reset(self):
            events.append('reset')
    class ReadyAgent(_MetadataAgent):
        def act(self, observation):
            events.append('act')
            return super().act(observation)
    episode_path=tmp_path/'episode.json'
    episode_path.write_text(json.dumps({'episode_id':'startup','scene':{'platform':'ithor','scene_id':'FloorPlan1'},'agent_init':{},'task':{'task_family':'test','instruction':'finish'},'budget':{'max_steps':1},'success_condition':{'type':'report_only'}}))
    monkeypatch.setattr(sim_runner,'PublicThorEnv',ReadyEnv)
    sim_runner.run_episode(episode_path=episode_path,agent=ReadyAgent(),out_dir=tmp_path/'out',save_frames=False,startup_ready_callback=lambda:events.append('ready'))
    assert events[:3]==['reset','ready','act']


def test_public_agent_history_contains_only_own_actions():
    steps = [StepTrace(
        step_index=0, action=ActionCall("navigate", {"mode": "forward", "magnitude": 1}),
        env_status="blocked", action_valid=False, progress=0.75, judge_success=True,
        error_type="hidden evaluator detail", metadata={"judge_result": {"world_success": True}},
    )]
    payload = json.loads(format_dialogue_history(steps))
    assert set(payload) == {"step", "action"}
    assert payload["action"]["skill_name"] == "navigate"
    assert format_dialogue_history(steps, max_turns=0) == ""
    assert format_dialogue_history(steps, max_turns=-1) == ""
