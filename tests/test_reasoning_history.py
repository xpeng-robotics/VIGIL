"""Reasoning is trace evidence, never a hidden action or a later prompt."""
import json

import pytest

from vigil.agent.backends.base import ChatResult
from vigil.agent.backends.base import ModelBackendConfig
from vigil.agent.model import OpenAIModelAgent
from vigil.agent.parser import parse_agent_response, strip_thinking_tags
from vigil.agent.backends.openai_compatible import extract_chat_text, extract_reasoning_text
from test_backends import FakeResponse
from test_protocol_retries import VALID, make_agent, observation

MARKER = "reasoning-only-marker"


@pytest.mark.parametrize("text", [
    f"<think>{MARKER}</think>{VALID}",
    f"<thinking>{MARKER}</thinking>{VALID}",
    f"{MARKER}</think>{VALID}",  # Opening token may belong to the chat template.
    f"<think>{MARKER}<think>nested draft</think>more draft</think>{VALID}",
])
def test_next_turn_receives_only_visible_answer_but_trace_keeps_original(monkeypatch, text):
    agent, calls = make_agent(monkeypatch, [ChatResult(text), ChatResult(VALID)])
    first = agent.act(observation())
    agent.act(observation())
    assert first.action is not None and first.raw_response == text
    assistants = [m['content'] for m in calls[1] if m['role'] == 'assistant']
    assert assistants == [VALID]
    assert MARKER not in json.dumps(calls[1])


@pytest.mark.parametrize("text", [
    f"<think>{MARKER} {VALID}",
    f"<thinking>{MARKER} {VALID}",
    f"{MARKER} {VALID}</think>",
    f"<think>{MARKER} {VALID}</thinking>",
])
def test_reasoning_without_final_answer_cannot_execute_or_enter_history(monkeypatch, text):
    agent, calls = make_agent(monkeypatch, [ChatResult(text), ChatResult(VALID)])
    first = agent.act(observation())
    assert first.action is None and first.parse_error
    assert first.raw_response == text
    agent.act(observation())
    assert MARKER not in json.dumps(calls[1])
    assert not any(m['role'] == 'assistant' for m in calls[1])


@pytest.mark.parametrize("unfinished", [False, True])
def test_protocol_retry_cannot_copy_reasoning_into_the_request(monkeypatch, unfinished):
    text = f"<think>{MARKER}" if unfinished else f"<think>{MARKER}</think>not JSON"
    agent, calls = make_agent(monkeypatch, [ChatResult(text), ChatResult(VALID)], protocol_retry_limit=1)
    turn = agent.act(observation())
    assert turn.action is not None and len(calls) == 2
    assert MARKER not in json.dumps(calls[1])
    assert turn.metadata['model_attempts'][0]['content'] == text


def test_echo_retry_cannot_copy_reasoning_into_the_request(monkeypatch):
    echo = '{"frame_id":"x","image_size":{"width":640,"height":480}}'
    agent, calls = make_agent(monkeypatch, [ChatResult(f"<think>{MARKER}</think>{echo}"), ChatResult(VALID)],
                              observation_echo_retry_limit=1)
    assert agent.act(observation()).action is not None
    assert MARKER not in json.dumps(calls[1])


@pytest.mark.parametrize("fenced", [False, True])
def test_tag_literals_inside_json_strings_are_not_reasoning_blocks(fenced):
    payload = json.dumps({'skill_name': 'report', 'arguments': {'status': 'fail',
                         'summary': 'literal <think>quoted text</think>'}})
    text = f"```json\n{payload}\n```" if fenced else payload
    assert strip_thinking_tags(text) == text
    assert parse_agent_response(text).action.arguments['summary'] == 'literal <think>quoted text</think>'


@pytest.mark.parametrize("field", ['reasoning', 'reasoning_content'])
@pytest.mark.parametrize("content", [VALID, None])
def test_server_separated_reasoning_stays_out_of_next_wire_request(monkeypatch, field, content):
    requests = []
    payload = {'choices': [{'message': {'content': content, field: MARKER + VALID},
                            'finish_reason': 'stop' if content else 'length'}]}
    def send(request, **kwargs):
        requests.append(json.loads(request.data))
        return FakeResponse(payload)
    monkeypatch.setattr('urllib.request.urlopen', send)
    agent = OpenAIModelAgent(ModelBackendConfig(base_url='https://gateway.example/v1/chat/completions', model='test'))
    first = agent.act(observation())
    agent.act(observation())
    assert first.metadata['reasoning'] == MARKER + VALID
    assert (first.action is not None) is bool(content)
    assert not str(first.parse_error).startswith('model_request_error:')
    assert MARKER not in json.dumps(requests[1])
    assert first.metadata['raw_response'] == payload


@pytest.mark.parametrize('reasoning', [None, '', 'server reasoning'])
@pytest.mark.parametrize('content', [
    '<think>unfinished ' + VALID,
    '<think >unfinished ' + VALID,
    '<think>outer<think>inner</think>' + VALID,
    '<think>draft</thinking>' + VALID,
])
def test_native_reasoning_never_bypasses_inline_boundaries(monkeypatch, reasoning, content):
    agent, calls = make_agent(monkeypatch, [ChatResult(content, reasoning=reasoning), ChatResult(VALID)])
    first = agent.act(observation())
    assert first.action is None and first.parse_error
    assert first.raw_response == content
    agent.act(observation())
    assert not any(message['role'] == 'assistant' for message in calls[1])


@pytest.mark.parametrize('reasoning', [None, '', 'server reasoning'])
def test_nonreasoning_prefix_is_accepted_without_entering_history(monkeypatch, reasoning):
    content = 'Here is the next action: ' + VALID
    agent, calls = make_agent(monkeypatch, [ChatResult(content, reasoning=reasoning), ChatResult(VALID)])
    first = agent.act(observation())
    assert first.action is not None
    agent.act(observation())
    assert [m['content'] for m in calls[1] if m['role'] == 'assistant'] == [VALID]
    assert first.metadata['assistant_history_policy'] == 'canonical_payload_v1'


@pytest.mark.parametrize('content', [None, ''])
def test_empty_chat_message_never_falls_back_to_envelope_draft(monkeypatch, content):
    payload = {'choices': [{'message': {'content': content, 'reasoning_content': MARKER},
                            'text': VALID, 'finish_reason': 'length'}], 'text': VALID}
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **kw: FakeResponse(payload))
    agent = OpenAIModelAgent(ModelBackendConfig(base_url='https://gateway.example/v1', model='test'))
    turn = agent.act(observation())
    assert turn.action is None and turn.parse_error
    assert not turn.parse_error.startswith('model_request_error:')
    assert turn.metadata['raw_response'] == payload
    assert not agent._conversation_history


def test_structured_thought_parts_are_evidence_and_never_final_text():
    envelope = {'choices': [{'message': {'content': [
        {'type': 'text', 'thought': True, 'text': MARKER},
        {'type': 'text', 'text': VALID},
    ]}}]}
    assert extract_reasoning_text(envelope) == MARKER
    assert extract_chat_text(envelope) == VALID


def test_protocol_thought_survives_but_private_reasoning_and_extra_keys_do_not(monkeypatch):
    protocol = {'skill_name': 'report', 'arguments': {'status': 'fail'}, 'thought': 'visible explanation'}
    content = '<think>' + MARKER + '</think>' + json.dumps({**protocol, 'private_draft': MARKER})
    agent, calls = make_agent(monkeypatch, [ChatResult(content), ChatResult(VALID)])
    first = agent.act(observation())
    assert first.action is not None
    agent.act(observation())
    prior = next(m['content'] for m in calls[1] if m['role'] == 'assistant')
    assert json.loads(prior) == protocol
    assert MARKER not in json.dumps(calls[1])
    assert first.raw_response == content
