from vigil.agent.prompts import (
    LEGACY_PROMPT_POLICY_VERSION,
    NEUTRAL_REPORT_PROMPT_POLICY_NAME,
    PROMPT_POLICY_NAME,
    build_agent_system_prompt,
    build_task_block,
    get_prompt_policy_metadata,
    with_prompt_policy,
)
from vigil.agent.profiles import get_profile
from vigil.agent.types import AgentObservation
from vigil.agent.prompts import build_frame_text_payload
from vigil.agent.backends.base import ChatResult
from test_protocol_retries import make_agent
import json
import pytest


@pytest.mark.parametrize("state", ["open", "closed", "on", "off"])
def test_observation_labels_do_not_expose_dataset_state_or_custom_ids(state):
    task_id = f"hidden_scene_microwave_{state}_verify_001"
    observation = AgentObservation(
        episode_id=task_id, step_index=3, instruction="Inspect the microwave.",
        metadata={"frame_id": task_id, "expected_report_status": state,
                  "scene_id": "hidden_scene", "image_size": {"width": 640, "height": 480}},
    )
    frame = build_frame_text_payload(observation)
    assert frame == {"frame_id": "step_3", "temporal_tag": "t", "role": "current",
                     "image_size": {"width": 640, "height": 480}}
    assert observation.episode_id == task_id


def test_model_requests_retries_and_history_keep_dataset_ids_private(monkeypatch):
    valid = '{"skill_name":"look","arguments":{"direction":"left","degrees":30}}'
    agent, calls = make_agent(monkeypatch, [ChatResult("not JSON"), ChatResult(valid), ChatResult(valid)],
                              protocol_retry_limit=1)
    for step in [0, 1]:
        turn = agent.act(AgentObservation(
            episode_id="hidden_scene_microwave_closed_verify_open_001", step_index=step,
            instruction="Check whether the microwave is open or closed.",
            metadata={"history_turns": 2, "frame_id": "hidden_scene_answer_closed"},
        ))
        assert turn.action is not None
    assert len(calls) == 3
    assert "hidden_scene" not in json.dumps(calls)
    assert "step_0" in json.dumps(calls[2]) and "step_1" in json.dumps(calls[2])


def test_prompt_policy_metadata_matches_reference_hash():
    metadata = get_prompt_policy_metadata()

    assert metadata["policy_name"] == "native_embodied_public_evidence"
    assert metadata["policy_version"] == "2026-04-27-state-report-labels"
    assert metadata["policy_sha256"] == "48d4f53635ba365008df0da40c2314d46221f4be676b258e3c145c2bee4141a9"


def test_task_block_uses_reference_spacing_and_state_report_rule():
    block = build_task_block("Task X")

    assert "view.\n\nEach step" in block
    assert "For state-recognition tasks, report the observed state label" in block
    assert block.endswith("Task: Task X")


def test_neutral_report_prompt_policy_is_supported():
    profile = with_prompt_policy(get_profile(), NEUTRAL_REPORT_PROMPT_POLICY_NAME)
    prompt = build_agent_system_prompt(task_instruction="Task X", profile=profile, action_schema=[])

    assert "Decide when to report based on the task instruction" in prompt
    assert "Mere visibility, proximity" not in prompt


def test_legacy_prompt_policy_version_is_selectable():
    profile = with_prompt_policy(get_profile(), PROMPT_POLICY_NAME, LEGACY_PROMPT_POLICY_VERSION)
    prompt = build_agent_system_prompt(task_instruction="Task X", profile=profile, action_schema=[])
    metadata = get_prompt_policy_metadata(profile=profile)

    assert metadata["policy_name"] == "native_embodied_public_evidence"
    assert metadata["policy_version"] == "2026-04-18"
    assert metadata["historical_reference_policy_sha256"] == "b450374f4bcc13a58a782c10522e8bc97f46d92d4b49039ee8f00a4889df1d38"
    assert len(metadata["policy_sha256"]) == 64
    assert "single-target completion task" in prompt
    assert prompt.endswith("\n")


def test_public_profile_exposes_reference_modality_api():
    profile = get_profile()

    assert profile.uses_modality("rgb") is True
    assert profile.uses_modality("depth") is False


def test_legacy_policy_fingerprint_changes_with_actual_policy_text(monkeypatch):
    from vigil.agent import prompts

    profile = with_prompt_policy(get_profile(), PROMPT_POLICY_NAME, LEGACY_PROMPT_POLICY_VERSION)
    before = get_prompt_policy_metadata(profile=profile)
    key = (PROMPT_POLICY_NAME, LEGACY_PROMPT_POLICY_VERSION)
    monkeypatch.setitem(prompts._REPORT_INSTRUCTION_RULES, key, prompts._REPORT_INSTRUCTION_RULES[key] + ("Changed policy text.",))
    after = get_prompt_policy_metadata(profile=profile)
    assert before["policy_sha256"] != after["policy_sha256"]
    assert before["rendered_prompt_sha256"] != after["rendered_prompt_sha256"]
    assert before["historical_reference_policy_sha256"] == after["historical_reference_policy_sha256"]
