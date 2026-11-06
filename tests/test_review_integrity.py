"""Adversarial checks for cached results, API settings and interrupted runs."""
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from vigil.actions import ActionCall
from vigil.agent.backends.base import ModelBackendConfig
from vigil.agent.backends.anthropic import AnthropicClient
from vigil.agent.backends.gemini import GeminiClient
from vigil.eval.judge import JudgeState, finalize_settlement_with_budget, judge_step
from vigil.eval.scoring import aggregate_scores, score_episode, score_result_payload
from vigil.eval.settlement import settle_trace
from vigil.eval.traces import EpisodeTrace, StepTrace
from vigil.cli import main
from vigil.eval.paper_alignment import PaperAlignmentError, trace_outcome
from vigil.eval.runner import _judge_result_payload, _env_result_payload
from test_backends import FakeResponse
from test_judge import _episode, _env_result
from test_paper_alignment import result as paper_result


def judged_trace(events, *, limit=0, budget=5, spec=None):
    if spec is None:
        spec = _episode({"type": "target_grounded", "target_object_type": "Fridge"},
                        task_family="S1_pixel_grounding", max_steps=budget)
        spec.constraint_spec["invalid_action_limit"] = limit
    else:
        budget = spec.max_steps
    state = JudgeState()
    steps = []
    for index, event in enumerate(events):
        protocol = event.skill_name == "model_protocol_error"
        state.steps_used += 1
        judged = judge_step(spec=spec, state=state, env_result=event, protocol_failure=protocol)
        metadata = {"judge_result": _judge_result_payload(judged), "env_result": _env_result_payload(event)}
        if judged.oracle_facts.get("expected_report_status") is not None:
            metadata["expected_report_status"] = judged.oracle_facts["expected_report_status"]
        steps.append(StepTrace(
            step_index=index, action=None if protocol else ActionCall(event.skill_name, event.executed_arguments),
            action_valid=not (judged.invalid_action or judged.protocol_failure),
            env_status="protocol_error" if protocol else "success", progress=judged.progress,
            judge_success=judged.world_success, error_type=judged.failure_label,
            terminal=judged.status != "ongoing", metadata=metadata,
        ))
    settlement = finalize_settlement_with_budget(spec, state)
    return EpisodeTrace(spec.episode_id, "test", budget, tuple(steps), settlement.terminal_status,
                        {"settlement": settlement.to_dict(), "task_family": spec.task_family})


def ground():
    return _env_result("interact_pixel", executed={"intent": "ground", "x": 10, "y": 20},
                       resolved_target={"object_id": "Fridge|1", "object_type": "Fridge"})


@pytest.mark.parametrize("events,limit,budget", [
    ([ground(), _env_result("report", executed={"status": "success"})], 0, 5),
    ([_env_result("report", executed={"status": "success"})], 0, 5),
    ([ground(), _env_result("report", executed={"status": "fail"})], 0, 5),
    ([ground()], 0, 1),
    ([_env_result("model_protocol_error", success=False)], 0, 1),
    ([_env_result("model_protocol_error", success=False)] * 2, 1, 5),
    ([_env_result(error="path_blocked", success=False)], 0, 1),
    ([_env_result("model_protocol_error", success=False), ground(),
      _env_result("report", executed={"status": "success"})], 0, 5),
])
def test_runtime_settlement_matches_uncached_trace_and_aggregate(events, limit, budget):
    trace = judged_trace(events, limit=limit, budget=budget)
    uncached = replace(trace, metadata={"task_family": "S1_pixel_grounding"})
    assert settle_trace(uncached).to_dict() == trace.metadata["settlement"]
    score = score_episode(trace)
    reloaded = score_result_payload(score.to_result_dict())
    assert score.to_result_dict() == reloaded.to_result_dict()
    before, after = (aggregate_scores([item]).to_dict() for item in (score, reloaded))
    # Internal result_metadata can contain compatibility aliases after import.
    before.pop("scores")
    after.pop("scores")
    assert before == after


@pytest.mark.parametrize("field,value", [
    ("world_success", True), ("semantic_world_success", True),
    ("report_matches_world", True), ("steps_used", 200),
    ("step_budget", 900), ("terminal_status", "success"),
    ("protocol_failures", 9), ("final_progress", 1),
])
def test_rescore_rejects_cached_settlement_contradicting_evidence(field, value):
    trace = judged_trace([_env_result("report", executed={"status": "success"})])
    trace.metadata["settlement"][field] = value
    with pytest.raises(ValueError, match="disagrees with step evidence"):
        score_episode(trace)


@pytest.mark.parametrize("mutation", ["missing_final", "early_report", "string_boolean", "bad_count"])
def test_paper_gate_rejects_incomplete_or_impossible_evidence(mutation, tmp_path):
    row = paper_result()
    if mutation == "missing_final":
        row = paper_result(report=False)
        row["trace"].append({"runtime_action": {"executed_invocation": {"skill_name": "look"}}})
    elif mutation == "early_report":
        row["trace"].append({"judge_result": {"world_success": True}})
    elif mutation == "string_boolean":
        row["trace"][0]["judge_result"]["world_success"] = "false"
    else:
        from test_paper_alignment import run_audit
        row["settlement"]["steps_used"] = 2
        with pytest.raises(PaperAlignmentError, match="step count"):
            run_audit(tmp_path, [row])
        return
    with pytest.raises(PaperAlignmentError):
        trace_outcome(row)


def test_reference_rescore_retains_failed_action_validity():
    trace = EpisodeTrace("e", "p", 1, (StepTrace(0, action=None, action_valid=False),), "failure")
    score = score_episode(trace)
    assert score.action_validity == 0
    assert score_result_payload(score.to_result_dict()).action_validity == 0


def test_legacy_simulator_failure_is_not_automatically_an_invalid_action():
    row = paper_result(report=False)
    row["trace"][0].update(ok=False)
    row["trace"][0]["judge_result"].update(invalid_action=False, protocol_failure=False, recoverable=True)
    assert score_result_payload(row).action_validity == 1


@pytest.mark.parametrize("visible,status", [(True, "on"), (True, "off"), (True, "success"), (False, "fail")])
def test_state_verification_report_matches_live_judgment(visible, status):
    spec = _episode({"type": "report_status", "oracle_condition": {
        "type": "object_state", "target_object_type": "DeskLamp", "field": "is_toggled", "value": True,
    }}, task_family="S4_state_recognition")
    event = _env_result("report", executed={"status": status}, post_state={"objects": [
        {"objectId": "lamp", "objectType": "DeskLamp", "visible": visible, "isToggled": True},
    ]})
    trace = judged_trace([event], spec=spec)
    assert settle_trace(replace(trace, metadata={})).to_dict() == trace.metadata["settlement"]
    assert score_episode(trace).success is (visible and status == "on")


def test_world_regression_preserves_legacy_peak_progress_but_not_world_success():
    spec = _episode({"type": "object_state", "target_object_type": "DeskLamp", "field": "is_toggled", "value": True})
    def event(skill, toggled, args=None):
        return _env_result(skill, executed=args, post_state={"objects": [
            {"objectId": "lamp", "objectType": "DeskLamp", "visible": True, "isToggled": toggled},
        ]})
    trace = judged_trace([event("look", True), event("report", False, {"status": "success"})], spec=spec)
    inferred = settle_trace(replace(trace, metadata={}))
    assert inferred.to_dict() == trace.metadata["settlement"]
    assert not inferred.world_success and inferred.semantic_final_progress == 1


@pytest.mark.parametrize("extra", [{"model": "other"}, {"messages": []}, {"max_tokens": 9999},
                                    {"contents": []}, {"generationConfig": {"topK": 9}}])
def test_extra_body_cannot_silently_replace_recorded_experiment(extra):
    with pytest.raises(ValueError, match="cannot override"):
        ModelBackendConfig(base_url="http://example.invalid/v1", model="expected", extra_body=extra)


def test_native_requests_honor_settings_and_keep_thoughts_out_of_actions(monkeypatch):
    bodies = []
    def request(req, timeout):
        bodies.append(json.loads(req.data))
        if req.full_url.endswith("/v1/messages"):
            return FakeResponse({"content": [{"type": "text", "text": "{}"}]})
        return FakeResponse({"candidates": [{"content": {"parts": [
            {"thought": True, "text": '{"skill_name":"report","arguments":{"status":"success"}}'},
            {"text": '{"skill_name":"look","arguments":{"direction":"up","magnitude":1}}'},
        ]}}]})
    monkeypatch.setattr("urllib.request.urlopen", request)
    config = ModelBackendConfig(base_url="", model="test", backend="gemini", api_key="test-key",
                                top_k=17, supports_json_mode=False,
                                extra_body={"generationConfig": {"thinkingConfig": {"includeThoughts": True}}})
    response = GeminiClient(config).chat([{"role": "user", "content": "test"}])
    generation = bodies[-1]["generationConfig"]
    assert generation["topK"] == 17 and generation["thinkingConfig"]["includeThoughts"] is True
    assert "responseMimeType" not in generation
    assert json.loads(response.content)["skill_name"] == "look"
    assert json.loads(response.reasoning)["skill_name"] == "report"
    AnthropicClient(replace(config, backend="anthropic", extra_body={})).chat([{"role": "user", "content": "test"}])
    assert bodies[-1]["top_k"] == 17
    assert "system" not in bodies[-1]


def test_run_directory_lock_prevents_a_second_process(tmp_path):
    from vigil.eval.state import run_lock
    script = "from pathlib import Path; from vigil.eval.state import run_lock; import sys\nwith run_lock(Path(sys.argv[1])): pass"
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    with run_lock(tmp_path):
        process = subprocess.run([sys.executable, "-c", script, str(tmp_path)], env=env, capture_output=True, text=True)
        assert process.returncode != 0 and "Another evaluation" in process.stderr
    with run_lock(tmp_path):
        pass


@pytest.mark.parametrize("state", ["running", "infrastructure_error"])
def test_report_never_presents_stale_aggregate_as_current(tmp_path, state):
    (tmp_path / "aggregate_score.json").write_text(json.dumps({"episode_count": 1000, "success_rate": 1}))
    (tmp_path / "run_status.json").write_text(json.dumps({"state": state}))
    with pytest.raises(SystemExit) as error:
        main(["report", str(tmp_path)])
    assert error.value.code == 2


def test_single_episode_returns_nonzero_on_simulator_error(tmp_path, monkeypatch):
    from test_cli import _write_episode
    from test_sim_runner import _ResetFailEnv
    _write_episode(tmp_path, "sample")
    monkeypatch.setattr("vigil.eval.runner.PublicThorEnv", _ResetFailEnv)
    assert main(["--no-config", "run-episode", str(tmp_path / "sample/episode.json"),
                 "--script-actions", '[]', "--out-dir", str(tmp_path / "out"), "--no-frames"]) == 1


@pytest.mark.parametrize("progress", [float("nan"), float("inf")])
def test_trace_rejects_nonfinite_progress(progress):
    with pytest.raises(ValueError):
        StepTrace.from_dict({"step_index": 0, "progress": progress})


def test_all_canonical_contracts_have_runtime_and_trace_settlement_parity():
    from vigil.data.episodes import EpisodeSpec
    root = Path(__file__).resolve().parents[1]
    paths = sorted((root / "data/episodes").glob("*/episode.json"))
    assert len(paths) == 1000
    for path in paths:
        spec = EpisodeSpec.from_path(path)
        protocol = _env_result("model_protocol_error", success=False)
        invalid_limit = int(spec.constraint_spec.get("invalid_action_limit", 0))
        scenarios = [
            [_env_result("look")],
            [_env_result("report", executed={"status": "success"})],
            [_env_result("report", executed={"status": "fail"})],
            [protocol] * min(spec.max_steps, invalid_limit + 1 if invalid_limit else spec.max_steps),
        ]
        for events in scenarios:
            trace = judged_trace(events, spec=spec)
            uncached = replace(trace, metadata={"task_family": spec.task_family})
            assert settle_trace(uncached).to_dict() == trace.metadata["settlement"], spec.episode_id
            score = score_episode(trace)
            assert score.to_result_dict() == score_result_payload(score.to_result_dict()).to_result_dict()
