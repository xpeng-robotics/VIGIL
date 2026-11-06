from vigil.agent import parse_agent_response


def test_parser_accepts_fenced_json():
    result = parse_agent_response('```json\n{"skill_name":"Stop","arguments":{}}\n```')

    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "Stop"


def test_parser_strips_thinking_tags():
    result = parse_agent_response('<think>hidden</think>{"skill_name":"look","arguments":{"direction":"up"}}')

    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "look"


def test_parser_promotes_openai_nested_payload():
    result = parse_agent_response(
        '{"choices":[{"message":{"content":"{\\"skill_name\\":\\"Stop\\",\\"arguments\\":{}}"}}]}'
    )

    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "Stop"


def test_parser_coerces_primitive_alias():
    result = parse_agent_response('{"skill_name":"move_forward","arguments":{}}')

    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "navigate"
    assert result.action.arguments["mode"] == "forward"

def test_parser_keeps_non_contract_look_direction_for_validator():
    result = parse_agent_response('{"skill_name":"look","arguments":{"direction":"right"}}')

    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "look"
    assert result.action.arguments["direction"] == "right"


def test_parser_does_not_coerce_snake_case_pixel_legacy_alias():
    result = parse_agent_response('{"skill_name":"toggle_object_on","arguments":{"x":190,"y":350}}')

    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "toggle_object_on"
    assert result.action.arguments == {"x": 190, "y": 350}


def test_parser_does_not_coerce_snake_case_object_legacy_alias():
    result = parse_agent_response('{"skill_name":"pickup_object","arguments":{"object_id":"bed"}}')

    assert result.parse_error is None
    assert result.action is not None
    assert result.action.skill_name == "pickup_object"
    assert result.action.arguments == {"object_id": "bed"}


def test_parser_rejects_legacy_alias_fields():
    result = parse_agent_response('{"action":"navigate","params":{"mode":"forward","magnitude":1}}')

    assert result.action is None
    assert result.parse_error
    assert "Missing skill_name" in result.parse_error

def test_parser_matches_reference_for_non_object_fenced_json():
    result = parse_agent_response('```json\n[]\n```\n{"skill_name":"report","arguments":{"status":"success","summary":"done"}}')

    assert result.action is None
    assert result.parse_error
    assert "one JSON object" in result.parse_error

