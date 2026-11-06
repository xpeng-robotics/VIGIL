"""VIGIL public API. Importing the package does not load evaluation or simulation."""
from importlib import import_module

_EXPORTS = {
    'ActionCall': ('vigil.actions', 'ActionCall'),
    'AgentObservation': ('vigil.agent', 'AgentObservation'),
    'AgentProfile': ('vigil.agent.profiles', 'AgentProfile'),
    'AgentProtocol': ('vigil.agent', 'AgentProtocol'),
    'AgentTurnResult': ('vigil.agent', 'AgentTurnResult'),
    'AggregateScore': ('vigil.eval.scoring', 'AggregateScore'),
    'DEFAULT_PROFILE_NAME': ('vigil.agent.profiles', 'DEFAULT_PROFILE_NAME'),
    'EpisodeScore': ('vigil.eval.scoring', 'EpisodeScore'),
    'EpisodeSpec': ('vigil.data.episodes', 'EpisodeSpec'),
    'EpisodeTrace': ('vigil.eval.traces', 'EpisodeTrace'),
    'OpenAIModelAgent': ('vigil.agent.model', 'OpenAIModelAgent'),
    'Pack': ('vigil.data.episodes', 'Pack'),
    'ScriptedAgent': ('vigil.agent.scripted', 'ScriptedAgent'),
    'StaticAgent': ('vigil.agent', 'StaticAgent'),
    'StepTrace': ('vigil.eval.traces', 'StepTrace'),
    'collect_trace_files': ('vigil.eval.offline', 'collect_trace_files'),
    'evaluate_trace_files': ('vigil.eval.offline', 'evaluate_trace_files'),
    'get_profile': ('vigil.agent.profiles', 'get_profile'),
    'list_profiles': ('vigil.agent.profiles', 'list_profiles'),
    'load_pack': ('vigil.data.episodes', 'load_pack'),
    'load_trace': ('vigil.eval.traces', 'load_trace'),
    'load_traces': ('vigil.eval.offline', 'load_traces'),
    'parse_agent_response': ('vigil.agent', 'parse_agent_response'),
    'resolve_episode_path': ('vigil.data.paths', 'resolve_episode_path'),
    'run_episode': ('vigil.eval.runner', 'run_episode'),
    'score_episode': ('vigil.eval.scoring', 'score_episode'),
    'score_episodes': ('vigil.eval.scoring', 'score_episodes'),
    'validate_action': ('vigil.actions', 'validate_action'),
    'validate_pack': ('vigil.data.episodes', 'validate_pack'),
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module), attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
