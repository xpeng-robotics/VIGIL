from vigil.actions import ActionCall
from vigil.eval.settlement import settle_trace
from vigil.eval.traces import EpisodeTrace, StepTrace


def test_settle_trace_counts_core_outcomes():
    trace = EpisodeTrace(
        episode_id="e",
        profile="p",
        max_steps=5,
        terminal_status="success",
        steps=(
            StepTrace(step_index=0, action=ActionCall("MoveAhead", {}), action_valid=True, progress=0.5),
            StepTrace(step_index=1, action=ActionCall("report", {"status": "success"}), judge_success=True, progress=1.0, terminal=True),
        ),
    )

    settlement = settle_trace(trace)

    assert settlement.world_success is True
    assert settlement.final_progress == 1.0
    assert settlement.steps_used == 2
    assert settlement.step_budget == 5
    assert settlement.report_submitted is True


def test_settle_trace_counts_invalid_and_protocol_failures():
    trace = EpisodeTrace(
        episode_id="e",
        profile="p",
        max_steps=3,
        terminal_status="protocol_error",
        steps=(
            StepTrace(step_index=0, action=None, action_valid=False, env_status="protocol_error", error_type="parse_error"),
        ),
    )

    settlement = settle_trace(trace)

    assert settlement.world_success is False
    assert settlement.invalid_actions == 0
    assert settlement.protocol_failures == 1
    assert settlement.protocol_failure is True


def test_settle_trace_marks_false_success_report():
    trace = EpisodeTrace(
        episode_id="e",
        profile="p",
        max_steps=5,
        terminal_status="stopped",
        steps=(
            StepTrace(
                step_index=0,
                action=ActionCall("report", {"status": "success", "summary": "looks done"}),
                action_valid=True,
                progress=0.5,
                terminal=True,
            ),
        ),
    )

    settlement = settle_trace(trace)

    assert settlement.terminal_status == "failure"
    assert settlement.terminal_reason == "false_success_report"
    assert settlement.false_report is True
    assert settlement.report_matches_world is False


def test_settle_trace_uses_expected_report_status_from_metadata():
    trace = EpisodeTrace(
        episode_id="state_on",
        profile="test",
        max_steps=2,
        terminal_status="stopped",
        steps=(
            StepTrace(
                step_index=0,
                action=ActionCall("report", {"status": "on"}),
                judge_success=True,
                progress=1.0,
                terminal=True,
                metadata={"env_result": {"diagnostics": {"expected_report_status": "on"}}},
            ),
        ),
    )
    settlement = settle_trace(trace)
    assert settlement.terminal_status == "success"
    assert settlement.agent_report_status == "on"
    assert settlement.report_matches_world is True


def test_attained_then_lost_world_state_is_not_success_at_closure():
    from vigil.eval.scoring import score_episode

    trace = EpisodeTrace(
        episode_id="attained_then_lost", profile="p", max_steps=5, terminal_status="success",
        steps=(
            StepTrace(step_index=0, judge_success=True, progress=1.0),
            StepTrace(step_index=1, action=ActionCall("report", {"status": "success"}),
                      judge_success=False, progress=0.25, terminal=True),
        ),
    )
    settlement = settle_trace(trace)
    assert not settlement.world_success
    assert settlement.final_progress == 0.25
    assert settlement.false_report
    assert not score_episode(trace).success


def test_final_judge_world_evidence_is_distinct_from_report_judgment():
    from vigil.eval.scoring import score_episode

    trace = EpisodeTrace(
        episode_id="false_negative", profile="p", max_steps=5, terminal_status="failure",
        steps=(StepTrace(
            step_index=0, action=ActionCall("report", {"status": "fail"}), judge_success=False,
            metadata={"judge_result": {"world_success": True, "semantic_world_success": True}},
        ),),
    )
    settlement = settle_trace(trace)
    assert settlement.world_success
    assert settlement.false_report
    assert not score_episode(trace).success


def test_success_flag_without_report_cannot_bypass_closure_requirement():
    from vigil.eval.scoring import summarize_episode
    from vigil.eval.types import EpisodeSettlement

    settlement = EpisodeSettlement(
        terminal_status="success", terminal_reason="bad_cached_success",
        world_success=True, semantic_world_success=True, strict_world_success=True,
        final_progress=1.0, semantic_final_progress=1.0, strict_final_progress=1.0,
        steps_used=1, step_budget=5, report_submitted=False,
        agent_report_status=None, report_matches_world=None,
        invalid_actions=0, protocol_failures=0, recoverable_failures=0,
        protocol_failure=False, false_report=False, budget_exhausted=False,
    )
    summary = summarize_episode(settlement=settlement, task_family="S1_pixel_grounding")
    assert not summary.success
    assert not summary.strict_success
    assert not summary.diagnostics["closure_success"]
