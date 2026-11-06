from vigil.eval.scoring import aggregate_scores, score_result_payload


def _reference_settlement(**overrides):
    payload = {
        "terminal_status": "success",
        "terminal_reason": "report_success",
        "world_success": True,
        "semantic_world_success": True,
        "strict_world_success": True,
        "final_progress": 1.0,
        "semantic_final_progress": 1.0,
        "strict_final_progress": 1.0,
        "steps_used": 3,
        "step_budget": 10,
        "report_submitted": True,
        "agent_report_status": "success",
        "report_matches_world": True,
        "invalid_actions": 0,
        "protocol_failures": 0,
        "recoverable_failures": 0,
        "protocol_failure": False,
        "false_report": False,
        "budget_exhausted": False,
        "violations": [],
    }
    payload.update(overrides)
    return payload


def test_behavior_success_rate_excludes_protocol_successes():
    result = {
        "episode_id": "protocol_success",
        "task_family": "T1_grounded_interaction",
        "settlement": _reference_settlement(protocol_failure=True, protocol_failures=1),
    }

    aggregate = aggregate_scores([score_result_payload(result)]).to_dict()

    assert aggregate["success_rate"] == 1.0
    assert aggregate["behavior_success_rate"] == 0.0
    assert aggregate["clean_success_rate"] == 0.0
    assert aggregate["results"][0]["score_summary"]["behavior_success"] is False
    assert aggregate["results"][0]["primary_score"] == 0.02


def test_clean_success_rate_excludes_invalid_action_successes():
    result = {
        "episode_id": "invalid_success",
        "task_family": "T1_grounded_interaction",
        "settlement": _reference_settlement(invalid_actions=1),
    }

    aggregate = aggregate_scores([score_result_payload(result)]).to_dict()

    assert aggregate["success_rate"] == 1.0
    assert aggregate["behavior_success_rate"] == 1.0
    assert aggregate["clean_success_rate"] == 0.0
    assert aggregate["results"][0]["score_summary"]["clean_success"] is False
