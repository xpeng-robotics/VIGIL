from vigil.data.episodes import EpisodeSpec
from vigil.eval.judge import (
    JudgeState,
    evaluate_condition,
    evaluate_episode,
    estimate_progress,
    finalize_settlement_with_budget,
    judge_step,
    target_object_matches,
)
from vigil.eval.types import EnvActionResult


def test_judge_object_state_and_progress():
    metadata = {"objects": [{"objectId": "f1", "objectType": "Fridge", "visible": True, "isOpen": True}]}
    condition = {"type": "object_state", "target_object_type": "Fridge", "field": "is_open", "value": True}

    assert evaluate_condition(condition, metadata) is True
    assert estimate_progress(condition, metadata) == 0.5


def test_judge_report_status_with_oracle_condition():
    metadata = {"objects": [{"objectId": "l1", "objectType": "DeskLamp", "visible": True, "isToggled": True}]}
    condition = {
        "type": "report_status",
        "expected": "on",
        "oracle_condition": {"type": "object_state", "target_object_type": "DeskLamp", "field": "is_toggled", "value": True},
    }

    assert evaluate_condition(condition, metadata, {"last_report": {"answer": "on"}}) is True
    assert evaluate_condition(condition, metadata, {"last_report": {"answer": "off"}}) is False


def test_evaluate_episode_returns_judge_result():
    episode = EpisodeSpec(
        episode_id="e",
        scene_id="FloorPlan1",
        task_family="test",
        instruction="",
        success_condition={"type": "object_state", "target_object_type": "Mug", "field": "visible", "value": True},
    )
    result = evaluate_episode(episode, {"objects": [{"objectType": "Mug", "visible": True}]})

    assert result.success is True
    assert result.progress == 1.0
    assert result.condition_type == "object_state"


def test_target_object_matches_id_or_type():
    item = {"objectId": "mug|1", "objectType": "Mug"}

    assert target_object_matches(item, {"target_object_id": "mug|1"}) is True
    assert target_object_matches(item, {"target_object_type": "Mug"}) is True
    assert target_object_matches(item, {"target_object_type": "Apple"}) is False


def _episode(success_condition, *, task_family="test", max_steps=4, generation_hints=None):
    return EpisodeSpec(
        episode_id="e",
        scene_id="FloorPlan1",
        task_family=task_family,
        instruction="",
        max_steps=max_steps,
        success_condition=success_condition,
        budget={"max_steps": max_steps, "max_invalid_actions": 0},
        generation_hints=dict(generation_hints or {}),
        constraint_spec={"invalid_action_limit": 0, "hazards": [], "report_required": True},
        trace_hints={"task_family": task_family},
    )


def _env_result(skill_name="navigate", *, executed=None, success=True, post_state=None, resolved_target=None, error=None):
    return EnvActionResult(
        skill_name=skill_name,
        requested_arguments=dict(executed or {}),
        executed_arguments=dict(executed or {}),
        simulator_success=success,
        error_message=error,
        resolved_target=dict(resolved_target) if resolved_target else None,
        target_resolved=resolved_target is not None,
        pre_state={"objects": [], "inventory": {}, "flags": {}},
        post_state=dict(post_state or {"objects": [], "inventory": {}, "flags": {}}),
    )


def test_judge_step_s1_ground_requires_report_closure():
    spec = _episode({"type": "target_grounded", "target_object_type": "Fridge"}, task_family="S1_pixel_grounding")
    state = JudgeState()

    ground = judge_step(
        spec=spec,
        state=state,
        env_result=_env_result(
            "interact_pixel",
            executed={"intent": "ground", "x": 10, "y": 20},
            resolved_target={"object_id": "Fridge|1", "object_type": "Fridge"},
        ),
    )
    assert ground.status == "ongoing"
    assert ground.world_success is True

    settlement = finalize_settlement_with_budget(spec, state, step_budget_override=4)
    assert settlement.terminal_status == "failure"
    assert settlement.terminal_reason == "fail_no_report"
    assert settlement.world_success is True

    state.steps_used += 1
    report = judge_step(
        spec=spec,
        state=state,
        env_result=_env_result("report", executed={"status": "success"}),
    )
    assert report.status == "success"
    assert report.report_matches_world is True


def test_judge_step_s4_hidden_public_evidence_accepts_fail_report():
    spec = _episode(
        {
            "type": "report_status",
            "expected": "success",
            "oracle_condition": {
                "type": "object_state",
                "target_object_type": "Safe",
                "field": "is_open",
                "value": True,
            },
        },
        task_family="S4_state_recognition",
    )
    state = JudgeState(steps_used=1)
    result = judge_step(
        spec=spec,
        state=state,
        env_result=_env_result(
            "report",
            executed={"status": "fail"},
            post_state={
                "inventory": {},
                "flags": {},
                "objects": [{"objectId": "Safe|1", "objectType": "Safe", "isOpen": True, "visible": False}],
            },
        ),
    )

    assert result.status == "success"
    assert result.world_success is False
    assert result.report_matches_world is True
    assert result.oracle_facts["expected_report_status"] == "fail"


def test_judge_step_t3_semantic_success_can_fail_strict_destination_group():
    spec = _episode(
        {
            "type": "object_at_receptacle",
            "target_object_id": "Book|1",
            "target_object_type": "Book",
            "receptacle_type": "Shelf",
            "allowed_receptacle_object_ids": ["Shelf|1", "Shelf|2"],
            "evaluation": {"primary": "semantic", "secondary": "strict"},
            "semantic_spec": {
                "type": "object_at_receptacle",
                "target_object_id": "Book|1",
                "target_object_type": "Book",
                "receptacle_type": "Shelf",
            },
            "strict_spec": {
                "type": "object_at_receptacle",
                "target_object_id": "Book|1",
                "target_object_type": "Book",
                "receptacle_type": "Shelf",
                "allowed_receptacle_object_ids": ["Shelf|1", "Shelf|2"],
            },
        },
        task_family="T3_sequential_manipulation",
    )
    state = JudgeState(steps_used=1)
    result = judge_step(
        spec=spec,
        state=state,
        env_result=_env_result(
            "interact_pixel",
            executed={"intent": "place", "x": 10, "y": 20},
            resolved_target={"object_id": "Shelf|3", "object_type": "Shelf"},
            post_state={
                "inventory": {},
                "flags": {},
                "objects": [
                    {"objectId": "Book|1", "objectType": "Book", "parentReceptacles": ["Shelf|3"]},
                    {"objectId": "Shelf|1", "objectType": "Shelf"},
                    {"objectId": "Shelf|2", "objectType": "Shelf"},
                    {"objectId": "Shelf|3", "objectType": "Shelf"},
                ],
            },
        ),
    )

    assert result.world_success is True
    assert result.semantic_world_success is True
    assert result.strict_world_success is False
