from vigil.agent.profiles import DEFAULT_PROFILE_NAME, get_profile, list_profiles, resolve_benchmark_mode


def test_default_profile_is_pure_rgb_dialogue_history_baseline():
    profile = get_profile()
    assert profile.name == DEFAULT_PROFILE_NAME
    assert profile.observation_modalities == ("rgb",)
    assert profile.visual_context_policy == "current_only"
    assert profile.memory_policy == "none"
    assert profile.metadata["conversation_history_turns"] == 20
    assert profile.metadata["visual_context_axis"] == "current_only"
    assert profile.metadata["mainline_comparable"] is True
    assert profile.metadata["analysis_parent"] == "pure_rgb_baseline"
    assert profile.metadata["structured_memory"] is False
    assert profile.feedback_policy == "none"
    assert profile.pose_policy == "none"


def test_default_profile_resolves_to_main_benchmark_mode():
    profile = get_profile("pure_rgb_dialogue_history_baseline")
    assert resolve_benchmark_mode(profile) == "pure_rgb_dialogue_history_baseline"


def test_public_release_has_one_profile():
    profiles = list_profiles()
    assert [item["name"] for item in profiles] == ["pure_rgb_dialogue_history_baseline"]
