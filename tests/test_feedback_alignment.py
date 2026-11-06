"""A missing aggregate must never substitute a failure proxy for retry."""
import json

import pytest

from vigil.eval.feedback_alignment import audit_feedback, count_episode_events, measure_source
from test_paper_alignment import result


def step(action, label=None):
    return {"runtime_action": {"executed_invocation": action}, "judge_result": {"failure_label": label}}


def test_retry_is_nonadjacent_executed_signature_not_failure_count():
    click = {"skill_name": "interact_pixel", "arguments": {"intent": "ground", "x": 320, "y": 240}}
    turn = {"skill_name": "navigate", "arguments": {"mode": "turn_left", "magnitude": 30}}
    other = {"skill_name": "interact_pixel", "arguments": {"intent": "pick", "x": 320, "y": 240}}
    row = {"trace": [step(click), step(turn, "path_blocked"), step(click), step(other, "interaction_no_effect"),
                     step(click, "too_far"), step(other, "interaction_not_available")]}
    assert count_episode_events(row) == {"retry": 3, "too_far": 1, "path_blocked": 1, "legacy_failure_proxy": 2}


def episode(profile="pure_rgb_dialogue_history_baseline"):
    row = result()
    row["profile"] = {"name": profile}
    row["settlement"]["false_report"] = False
    return row


def test_directory_and_aggregate_reconstruction_agree_with_stale_cached_metrics(tmp_path):
    row = episode()
    (tmp_path / "e.json").write_text(json.dumps(row))
    aggregate = tmp_path / "aggregate.json"
    aggregate.write_text(json.dumps({"results": [row], "episode_count": 1,
                                     "behavior_metrics_summary": {"same_interact_retry_count": 999}}))
    opts = {"families": {"e": "S1_pixel_grounding"}, "profile": row["profile"]["name"]}
    a = measure_source(aggregate, **opts)
    b = measure_source(aggregate, episode_files=True, **opts)
    assert a["counts"] == b["counts"] and a["counts"]["retry"] == 0
    aggregate.write_text('{"truncated":')
    with pytest.raises(ValueError):
        measure_source(aggregate, **opts)
    assert measure_source(aggregate, episode_files=True, **opts)["counts"] == a["counts"]


@pytest.mark.parametrize("mutation", ["missing", "profile", "id", "family", "steps", "infrastructure", "error_file"])
def test_feedback_audit_rejects_changed_denominator_or_experiment(tmp_path, mutation):
    row = episode()
    if mutation == "profile": row["profile"] = "another-experiment"
    if mutation == "id": row["episode_id"] = "wrong"
    if mutation == "family": row["task_family"] = "T1_grounded_interaction"
    if mutation == "steps": row["settlement"]["steps_used"] = 2
    if mutation == "infrastructure": row["trace"][0]["failure_label"] = "model_request_error"
    if mutation != "missing": (tmp_path / "e.json").write_text(json.dumps(row))
    if mutation == "error_file": (tmp_path / "e.error.json").write_text('{}')
    with pytest.raises((ValueError, FileNotFoundError)):
        measure_source(tmp_path, {"e": "S1_pixel_grounding"}, profile="pure_rgb_dialogue_history_baseline", episode_files=True)


def test_corrected_reference_does_not_turn_published_mismatch_into_a_pass(tmp_path):
    maps = []
    for arm, profile in [("base", "pure_rgb_dialogue_history_baseline"), ("feedback", "pure_rgb_dialogue_history_proprio_minimal")]:
        folder = tmp_path / arm; folder.mkdir()
        (folder / "e.json").write_text(json.dumps(episode(profile)))
        maps.append({"test": str(folder)})
    target = {"model_id": "test", "published": {"base": {"too_far": 0, "path_blocked": 0, "retry": 0},
              "feedback": {"too_far": 0, "path_blocked": 0, "retry": 1}, "deltas": {"W": 0, "B": 0, "FR": 0, "NR": 0}},
              "corrected_counts": {arm: {"W": 1, "B": 1, "FR": 0, "NR": 0, "too_far": 0, "path_blocked": 0, "retry": 0} for arm in ("base", "feedback")}}
    args = ({"models": [target]}, {"e": "S1_pixel_grounding"}, *maps)
    assert not audit_feedback(*args, episode_files=True)["all_passed"]
    corrected = audit_feedback(*args, episode_files=True, reference="corrected")
    assert corrected["all_passed"] and corrected["models"][0]["published_mismatches"]


def test_empty_targets_cannot_pass_a_feedback_gate():
    with pytest.raises(ValueError, match="nonempty"):
        audit_feedback({"models": []}, {"e": "S1_pixel_grounding"}, {}, {})
