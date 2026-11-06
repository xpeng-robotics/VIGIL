from vigil.agent import parse_agent_response
from vigil.eval.scoring import score_episode, score_episodes
from vigil.eval.traces import EpisodeTrace
from vigil.eval.scoring import aggregate_scores, score_episode as benchmark_score_episode, score_result_payload, summarize_trace
from vigil.eval.traces import EpisodeTrace as BenchmarkEpisodeTrace


def _success_trace() -> EpisodeTrace:
    return EpisodeTrace.from_dict(
        {
            "episode_id": "success_001",
            "profile": "pure_rgb_dialogue_history_baseline",
            "max_steps": 8,
            "terminal_status": "success",
            "steps": [
                {"step_index": 0, "action": {"skill_name": "RotateRight", "arguments": {}}, "progress": 0.25},
                {
                    "step_index": 1,
                    "action": {"skill_name": "OpenObject", "arguments": {"object_type": "Fridge"}},
                    "judge_success": True,
                    "progress": 1.0,
                    "terminal": True,
                },
            ],
        }
    )


def test_parse_agent_response_action_contract():
    result = parse_agent_response('{"skill_name": "Stop", "arguments": {}}')
    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "Stop"


def test_parse_agent_response_reports_protocol_error():
    result = parse_agent_response('not json')
    assert result.action is None
    assert result.parse_error


def test_world_complete_without_report_is_not_benchmark_success():
    score = score_episode(_success_trace())
    assert score.success is False
    assert score.episode_score == 0.1
    assert score.primary_score == 0.1
    assert score.progress_score == 1.0
    assert score.score_summary["diagnostics"]["report_submitted"] is False
    assert score.action_validity == 1.0
    assert score.efficiency > 0.0


def test_score_failed_trace_with_progress():
    trace = EpisodeTrace.from_dict(
        {
            "episode_id": "failed_001",
            "profile": "pure_rgb_dialogue_history_baseline",
            "max_steps": 4,
            "terminal_status": "timeout",
            "steps": [
                {"step_index": 0, "action": {"skill_name": "MoveAhead", "arguments": {}}, "progress": 0.25},
                {"step_index": 1, "action": None, "action_valid": False, "progress": 0.5},
            ],
        }
    )
    score = score_episode(trace)
    assert score.success is False
    assert score.episode_score == 0.1
    assert score.primary_score == 0.1
    assert score.progress_score == 0.5
    assert score.action_validity == 0.5


def test_aggregate_scores():
    aggregate = score_episodes([_success_trace()])
    assert aggregate.episode_count == 1
    assert aggregate.success_rate == 0.0


def test_benchmark_modules_are_canonical_imports():
    trace = BenchmarkEpisodeTrace.from_dict(_success_trace().to_dict())
    assert benchmark_score_episode(trace).success is False
    assert EpisodeTrace is BenchmarkEpisodeTrace

def test_reference_legacy_fail_no_report_step_is_not_counted():
    summary = summarize_trace(
        trace=[
            {"ok": True, "goal_progress": 1.0, "report_matches_world": True},
            {"ok": False, "failure_label": "fail_no_report", "goal_progress": 1.0},
        ],
        terminal_status="failure",
        step_budget=5,
        task_family="S1_pixel_grounding",
    )

    assert summary.diagnostics["steps_used"] == 1
    assert summary.diagnostics["world_success"] is True
    assert summary.diagnostics["semantic_world_success"] is True
    assert summary.primary_score == 0.1


def test_reference_legacy_recoverable_failure_count_matches_reference():
    summary = summarize_trace(
        trace=[
            {"ok": False, "failure_label": "too_far", "goal_progress": 0.0},
            {"ok": False, "failure_label": "interaction_no_effect", "goal_progress": 0.0},
        ],
        terminal_status="timeout",
        step_budget=2,
        task_family="T1_grounded_interaction",
    )

    assert summary.diagnostics["recoverable_failures"] == 2
    assert summary.diagnostics["invalid_actions"] == 0

def test_reference_result_rescore_preserves_public_metadata_and_extra_buckets():
    result = {
        "episode_id": "state_001",
        "status": "failure",
        "trace": [
            {
                "runtime_action": {"executed_invocation": {"skill_name": "report", "arguments": {}}},
                "agent_diagnostics": {"sanitation": {"sanitized": True, "protocol_retry_count": 1}},
            }
        ],
        "task_family": "S4_state_verification",
        "difficulty": "na",
        "functional_template": "verify_open_state",
        "target_group": "container_access",
        "primary_capabilities": ["state_verification"],
        "score_summary": {"task_family": "S4_state_recognition"},
        "settlement": {
            "terminal_status": "failure",
            "terminal_reason": "fail_no_report",
            "world_success": True,
            "semantic_world_success": True,
            "strict_world_success": None,
            "final_progress": 1.0,
            "semantic_final_progress": 1.0,
            "strict_final_progress": None,
            "steps_used": 1,
            "step_budget": 10,
            "report_submitted": False,
            "agent_report_status": None,
            "report_matches_world": None,
            "invalid_actions": 0,
            "protocol_failures": 0,
            "recoverable_failures": 0,
            "protocol_failure": False,
            "false_report": False,
            "budget_exhausted": False,
            "violations": [],
        },
    }

    score = score_result_payload(result)
    aggregate = aggregate_scores([score]).to_dict()
    output = aggregate["results"][0]

    assert output["functional_template"] == "verify_open_state"
    assert output["target_group"] == "container_access"
    assert output["score_summary"]["task_family"] == "S4_state_recognition"
    assert "verify_open_state" in aggregate["by_functional_template"]
    assert "container_access" in aggregate["by_target_group"]
    assert aggregate["by_capability_bucket"]["state_verification"]["episode_count"] == 1
    assert aggregate["no_report_analysis"]["fail_no_report_count"] == 1
    assert aggregate["harness_assistance_summary"]["protocol_retry_episode_rate"] == 1.0
