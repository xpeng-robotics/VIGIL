import pytest

from vigil.agent.types import AgentObservation
from vigil.agent.backends.base import ChatResult, ModelBackendConfig
from vigil.eval.runner import OpenAIModelAgent, build_turn_trace_metadata
from vigil.eval.scoring import aggregate_scores, score_episode
from vigil.eval.traces import EpisodeTrace

VALID = '{"skill_name":"report","arguments":{"status":"fail","summary":"not done"}}'


def make_agent(monkeypatch, responses, **settings):
    calls = []

    class Client:
        def chat(self, messages, **kwargs):
            calls.append(messages)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setattr("vigil.agent.model.create_model_client", lambda config: Client())
    return OpenAIModelAgent(
        ModelBackendConfig(base_url="http://example.invalid", model="test", **settings)
    ), calls


def observation():
    return AgentObservation(
        episode_id="e",
        step_index=0,
        instruction="Select the cup.",
        metadata={"history_turns": 1},
    )


def test_release_default_keeps_truncation_visible_without_extra_calls(monkeypatch):
    agent, calls = make_agent(
        monkeypatch,
        [ChatResult("", reasoning="unfinished", usage={"completion_tokens": 2048})],
    )
    turn = agent.act(observation())
    assert turn.action is None and turn.parse_error
    assert len(calls) == 1
    assert turn.metadata["sanitation"]["protocol_retry_count"] == 0


def test_reference_retry_retains_attempts_tokens_and_harness_accounting(monkeypatch):
    first = ChatResult(
        "",
        reasoning="unfinished",
        raw_response={"choices": [{"finish_reason": "length"}]},
        usage={"completion_tokens": 4096, "prompt_tokens": 100, "total_tokens": 4196},
    )
    last = ChatResult(
        VALID,
        usage={"completion_tokens": 30, "prompt_tokens": 120, "total_tokens": 150},
    )
    agent, calls = make_agent(monkeypatch, [first, last], protocol_retry_limit=1)
    turn = agent.act(observation())
    assert turn.action.skill_name == "report"
    assert len(calls) == 2 and calls[1][-1]["role"] == "user"
    assert "not valid for the benchmark protocol" in calls[1][-1]["content"]
    assert turn.metadata["usage"]["completion_tokens"] == 4126
    assert (
        turn.metadata["model_attempts"][0]["raw_response"]["choices"][0][
            "finish_reason"
        ]
        == "length"
    )
    assert turn.metadata["sanitation"]["total_retry_count"] == 1
    assert agent._conversation_history[-1]["content"] == VALID
    trace = EpisodeTrace.from_dict(
        {
            "episode_id": "e",
            "profile": "pure_rgb_dialogue_history_baseline",
            "max_steps": 1,
            "terminal_status": "failure",
            "steps": [
                {
                    "step_index": 0,
                    "action": turn.action.to_dict(),
                    "metadata": build_turn_trace_metadata(turn),
                }
            ],
        }
    )
    summary = aggregate_scores([score_episode(trace)]).to_dict()[
        "harness_assistance_summary"
    ]
    assert summary["mean_protocol_retry_count"] == 1
    assert summary["harness_assisted_rate"] == 1


def test_reference_retry_is_bounded_and_does_not_convert_reasoning_to_action(
    monkeypatch,
):
    agent, calls = make_agent(
        monkeypatch,
        [ChatResult("", reasoning=VALID), ChatResult("", reasoning=VALID)],
        protocol_retry_limit=1,
    )
    turn = agent.act(observation())
    assert turn.action is None and turn.parse_error
    assert len(calls) == 2
    assert turn.metadata["sanitation"]["protocol_retry_count"] == 1


def test_observation_echo_retry_is_explicit_and_recorded(monkeypatch):
    echo = ChatResult('{"frame_id":"x","image_size":{"width":640,"height":480}}')
    agent, calls = make_agent(
        monkeypatch, [echo, ChatResult(VALID)], observation_echo_retry_limit=2
    )
    turn = agent.act(observation())
    assert turn.action.skill_name == "report"
    assert len(calls) == 2 and "echoed the observation" in calls[1][-1]["content"]
    assert turn.metadata["sanitation"]["observation_echo_retry_count"] == 1


def test_request_failure_during_retry_is_not_silenced(monkeypatch):
    agent, calls = make_agent(
        monkeypatch, [ChatResult(""), RuntimeError("HTTP 500")], protocol_retry_limit=1
    )
    turn = agent.act(observation())
    assert turn.action is None
    assert turn.parse_error.startswith("model_request_error:")
    assert turn.metadata["exception_type"] == "RuntimeError"
    assert len(calls) == 2


def test_retry_settings_validate_and_load_from_environment(monkeypatch):
    monkeypatch.setenv("VIGIL_MODEL_BASE_URL", "http://example.invalid")
    monkeypatch.setenv("VIGIL_MODEL_NAME", "test")
    monkeypatch.setenv("VIGIL_PROTOCOL_RETRY_LIMIT", "1")
    monkeypatch.setenv("VIGIL_OBSERVATION_ECHO_RETRY_LIMIT", "2")
    config = ModelBackendConfig.from_env()
    assert (config.protocol_retry_limit, config.observation_echo_retry_limit) == (1, 2)
    with pytest.raises(ValueError, match="protocol_retry_limit"):
        ModelBackendConfig(base_url="x", model="x", protocol_retry_limit=20)
