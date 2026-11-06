"""Regression boundaries for the layered public package and portable entry points."""
import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from vigil.cli import select_episodes, build_parser
from vigil.data.episodes import load_pack
from vigil.data.families import FAMILY_ALIASES
from vigil.data.paths import CANONICAL_PACK, data_root, resolve_episode_path
from vigil.agent.profiles import get_profile
from vigil.eval import state

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("shadow", ["file", "directory"])
def test_task_root_wins_over_same_named_working_directory_entry(tmp_path, monkeypatch, shadow):
    monkeypatch.chdir(tmp_path)
    task = tmp_path / "episodes/sample/episode.json"
    task.parent.mkdir(parents=True)
    task.write_text('{}')
    local = tmp_path / "sample"
    local.write_text('{}') if shadow == "file" else local.mkdir()
    assert resolve_episode_path("sample", task.parents[1]) == task
    assert resolve_episode_path("sample", task.parents[1], allow_path=False) == task
    task.unlink()
    with pytest.raises(FileNotFoundError):
        resolve_episode_path("sample", task.parents[1], allow_path=False)


def test_explicit_episode_file_is_supported_but_pack_ids_cannot_be_paths(tmp_path):
    task = tmp_path / "custom.json"
    task.write_text('{}')
    assert resolve_episode_path(task) == task
    for value in (str(task), "../custom", "nested/task", "..", "."):
        with pytest.raises(ValueError, match="Pack episode IDs"):
            resolve_episode_path(value, tmp_path, allow_path=False)


@pytest.mark.parametrize("timeout", ["0", "5"])
def test_pack_fingerprint_and_workers_use_the_selected_task_root(tmp_path, monkeypatch, timeout):
    import json
    from vigil.cli import main
    from test_cli import _write_episode, _write_finished_trace
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "episodes"
    _write_episode(root, "sample")
    pack = tmp_path / "pack.json"
    pack.write_text(json.dumps({"pack_id": "mini", "episodes": [{"path": "episodes/sample/episode.json"}]}))
    # Invalid JSON here used to break fingerprinting or replace the task in workers.
    (tmp_path / "sample").write_text("unrelated local file")
    out = tmp_path / "out"
    seen = []
    def run_episode(**kwargs):
        seen.append(Path(kwargs["episode_path"]))
        return SimpleNamespace(trace_path=_write_finished_trace(out, "sample"),
                               score=SimpleNamespace(terminal_status="timeout", episode_score=0))
    def subprocess(cmd, **kwargs):
        seen.append(Path(cmd[cmd.index("run-episode") + 1]))
        _write_finished_trace(out, "sample")
        return 0
    monkeypatch.setattr("vigil.eval.runner.run_episode", run_episode)
    monkeypatch.setattr("vigil.eval.batch.run_episode_process", subprocess)
    assert main(["run", "--no-config", "--pack-file", str(pack), "--episode-root", str(root),
                 "--out-dir", str(out), "--script-actions", "[]", "--episode-timeout-s", timeout]) == 0
    assert seen == [root / "sample/episode.json"]


@pytest.mark.parametrize("public,module", [
    ("ActionCall", "vigil.actions"),
    ("AgentObservation", "vigil.agent.types"),
    ("OpenAIModelAgent", "vigil.agent.model"),
    ("ScriptedAgent", "vigil.agent.scripted"),
    ("run_episode", "vigil.eval.runner"),
    ("resolve_episode_path", "vigil.data.paths"),
    ("score_episode", "vigil.eval.scoring"),
])
def test_public_root_api_resolves_to_its_owner(public, module):
    import vigil
    assert getattr(vigil, public) is getattr(importlib.import_module(module), public)


def test_agent_implementation_does_not_import_world_or_judge():
    from vigil import OpenAIModelAgent, ScriptedAgent
    assert OpenAIModelAgent.__module__ == "vigil.agent.model"
    assert ScriptedAgent.__module__ == "vigil.agent.scripted"
    for source in (ROOT / "vigil/agent").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(("vigil.eval", "vigil.envs", "vigil.benchmark", "vigil.thor")), source


def test_data_discovery_from_an_unrelated_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("VIGIL_DATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    assert data_root() == ROOT / "data"


@pytest.mark.parametrize("alias,stored", FAMILY_ALIASES.items())
def test_public_family_alias_selects_identical_episode_ids(alias, stored):
    pack = load_pack(ROOT / "data/benchmark/packs" / CANONICAL_PACK)
    parser = build_parser()
    public = select_episodes(pack, parser.parse_args(["list-episodes", "--task-family", alias.lower()]))
    original = select_episodes(pack, parser.parse_args(["list-episodes", "--task-family", stored]))
    assert len(public) == 125
    assert [e.episode_id for e in public] == [e.episode_id for e in original]


def test_runtime_fingerprint_still_covers_all_layers(tmp_path, monkeypatch):
    package = tmp_path / "vigil"
    (package / "eval").mkdir(parents=True)
    monkeypatch.setattr(state, "__file__", str(package / "eval/state.py"))
    pack = tmp_path / "pack.json"
    pack.write_text('{}')
    args = build_parser().parse_args(["run", "--pack-file", str(pack)])
    def digest():
        return state.experiment_config(args, SimpleNamespace(episodes=[]), get_profile(), None)["runtime_sha256"]
    previous = digest()
    for name in ("agent/model.py", "agent/backends/base.py", "data/episodes.py", "envs/thor.py", "eval/judge.py"):
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('VERSION = 1\n')
        current = digest()
        assert current != previous, name
        previous = current


@pytest.mark.parametrize("field,changed", [("system", "OtherOS"), ("machine", "OtherArchitecture")])
def test_resume_refuses_another_operating_system_or_architecture(tmp_path, monkeypatch, field, changed):
    pack = tmp_path / "pack.json"
    pack.write_text('{}')
    args = build_parser().parse_args(["run", "--pack-file", str(pack)])
    def config():
        return state.experiment_config(args, SimpleNamespace(episodes=[]), get_profile(), None)
    original = config()
    out = tmp_path / "run"
    out.mkdir()
    state.prepare_run(out, original, resume=False)
    state.prepare_run(out, original, resume=True)
    monkeypatch.setattr(state.platform, field, lambda: changed)
    with pytest.raises(ValueError, match="runtime_versions"):
        state.prepare_run(out, config(), resume=True)


@pytest.mark.parametrize("artifact", ["frames/task/step_000.png", "aggregate_score.json", "run_status.json", "model_config.json"])
@pytest.mark.parametrize("tracked,resume", [(False, False), (False, True), (True, False), (True, True)])
def test_partial_evidence_requires_matching_explicit_recovery(tmp_path, artifact, tracked, resume):
    import json
    output = tmp_path / "run"
    evidence = output / artifact
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"original evidence")
    config = {"schema_version": 1, "model": {"model": "sample"}}
    config_path = output / "run_config.json"
    if tracked:
        config_path.write_text(json.dumps(config))
    if tracked and resume:
        state.prepare_run(output, config, resume=True)
    else:
        with pytest.raises(ValueError, match="Output directory|no run_config.json"):
            state.prepare_run(output, config, resume=resume)
    assert evidence.read_bytes() == b"original evidence"
    assert config_path.exists() == tracked
