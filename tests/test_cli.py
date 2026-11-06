import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from vigil.cli import main as cli_main
from vigil.eval.scoring import score_episode
from vigil.eval.traces import EpisodeTrace, StepTrace
from vigil.data.paths import CANONICAL_PACK

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data/benchmark/packs" / CANONICAL_PACK


def main(argv):
    # Repository tests must not inherit a user's local model configuration.
    return cli_main(["--no-config", *argv])


def _write_episode(root: Path, episode_id: str) -> None:
    episode_dir = root / episode_id
    episode_dir.mkdir(parents=True)
    (episode_dir / "episode.json").write_text(
        json.dumps(
            {
                "episode_id": episode_id,
                "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
                "agent_init": {},
                "task": {"task_family": "test", "instruction": "finish"},
                "budget": {"max_steps": 1},
                "success_condition": {"type": "report_only"},
            }
        ),
        encoding="utf-8",
    )


def _write_finished_trace(out_dir: Path, episode_id: str) -> Path:
    trace = EpisodeTrace(
        episode_id=episode_id,
        profile="pure_rgb_dialogue_history_baseline",
        max_steps=1,
        steps=(StepTrace(step_index=0, terminal=True, env_status="stopped"),),
        terminal_status="timeout",
        metadata={"task_family": "test", "scene_id": "FloorPlan1"},
    )
    score = score_episode(trace)
    trace_dir = out_dir / "traces"
    score_dir = out_dir / "scores"
    trace_dir.mkdir(parents=True, exist_ok=True)
    score_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{episode_id}.json"
    score_path = score_dir / f"{episode_id}.score.json"
    trace_path.write_text(json.dumps(trace.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    score_path.write_text(json.dumps(score.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return trace_path


def test_cli_list_profiles_json(capsys):
    assert main(["list-profiles", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item["name"] == "pure_rgb_dialogue_history_baseline" for item in payload)


@pytest.mark.parametrize("artifact", ["traces/old.json", "scores/old.score.json", "frames/old/step_000.png"])
def test_standalone_rollout_refuses_existing_evidence_before_starting_simulator(tmp_path, monkeypatch, artifact):
    _write_episode(tmp_path, "sample")
    out = tmp_path / "out"
    evidence = out / artifact
    evidence.parent.mkdir(parents=True)
    evidence.write_bytes(b"original evidence")
    monkeypatch.setattr("vigil.eval.runner.run_episode", lambda **kw: pytest.fail("must fail before simulation"))
    with pytest.raises(SystemExit) as error:
        main(["run-episode", str(tmp_path / "sample/episode.json"), "--out-dir", str(out), "--script-actions", "[]"])
    assert error.value.code == 2 and evidence.read_bytes() == b"original evidence"


def test_cli_validate_canonical_pack(capsys):
    assert main(["validate-pack", str(PACK)]) == 0
    out = capsys.readouterr().out
    assert "valid pack" in out
    assert "1000 episodes" in out


def test_cli_run_pack_dry(tmp_path):
    assert main(
        [
            "run-pack",
            "--pack-file",
            str(PACK),
            "--profile",
            "pure_rgb_dialogue_history_baseline",
            "--dry-run",
            "--workers",
            "4",
            "--out-dir",
            str(tmp_path),
        ]
    ) == 0
    aggregates = list(tmp_path.glob("*.aggregate.json"))
    assert len(aggregates) == 1
    payload = json.loads(aggregates[0].read_text(encoding="utf-8"))
    assert payload["summary"]["episode_count"] == 1000


def test_cli_run_pack_resume_existing_skips_completed(tmp_path, monkeypatch):
    episode_root = tmp_path / "episodes"
    out_dir = tmp_path / "out"
    for episode_id in ("episode_done", "episode_missing"):
        _write_episode(episode_root, episode_id)
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "pack_id": "mini",
                "episodes": [
                    {"path": "episodes/episode_done/episode.json"},
                    {"path": "episodes/episode_missing/episode.json"},
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run_episode(*, episode_path, out_dir, **kwargs):
        episode_id = Path(episode_path).parent.name
        calls.append(episode_id)
        trace_path = _write_finished_trace(Path(out_dir), episode_id)
        return SimpleNamespace(
            trace_path=trace_path,
            score_path=Path(out_dir) / "scores" / f"{episode_id}.score.json",
            score=SimpleNamespace(terminal_status="timeout", episode_score=0.0),
        )

    monkeypatch.setattr("vigil.eval.runner.run_episode", fake_run_episode)
    assert main([
        "run-pack", "--pack-file", str(pack_path), "--episode-root", str(episode_root),
        "--out-dir", str(out_dir), "--script-actions", '[{"skill_name":"report","arguments":{"status":"fail"}}]',
        "--max-episodes", "1", "--episode-timeout-s", "0",
    ]) == 0
    calls.clear()

    assert main(
        [
            "run-pack",
            "--pack-file",
            str(pack_path),
            "--episode-root",
            str(episode_root),
            "--out-dir",
            str(out_dir),
            "--script-actions",
            '[{"skill_name":"report","arguments":{"status":"fail"}}]',
            "--resume-existing",
            "--episode-timeout-s",
            "0",
            "--workers",
            "1",
        ]
    ) == 0

    assert calls == ["episode_missing"]
    aggregate = json.loads((out_dir / "aggregate_score.json").read_text(encoding="utf-8"))
    assert aggregate["episode_count"] == 2


def test_run_eval_wrapper_preserves_cli_overrides(tmp_path):
    import os
    import subprocess
    import sys
    output = tmp_path / "output"
    env = {**os.environ, "PYTHON_BIN": sys.executable, "VIGIL_WORKERS": "8", "VIGIL_MAX_EPISODES": "3"}
    result = subprocess.run(["bash", str(ROOT / "scripts/deploy/run_eval.sh"), "--no-config", "--dry-run",
                             "--max-episodes", "1", "--out-dir", str(output)],
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    aggregate = json.loads(next(output.glob("*.aggregate.json")).read_text())
    assert aggregate["summary"]["episode_count"] == 1


def test_release_defaults_match_across_public_entrypoints(monkeypatch):
    from vigil.cli import build_parser, _model_config_from_args
    from vigil.agent.backends import ModelBackendConfig
    from vigil.agent.prompts import get_prompt_policy_metadata, with_prompt_policy
    from vigil.agent.profiles import get_profile

    for name in ("VIGIL_MAX_TOKENS", "VIGIL_TEMPERATURE", "VIGIL_TOP_P", "VIGIL_TOP_K"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("VIGIL_MODEL_BASE_URL", "http://localhost:8000/v1/chat/completions")
    monkeypatch.setenv("VIGIL_MODEL_NAME", "test-model")
    configs = [ModelBackendConfig.from_env()]
    for command in (["run-pack", "--pack-file", str(PACK)], ["run-episode", "sample"]):
        args = build_parser().parse_args(command + ["--model", "test-model", "--base-url", "http://localhost:8000/v1/chat/completions"])
        configs.append(_model_config_from_args(args))
        assert args.max_steps == 0
        if args.command == "run-pack":
            assert args.workers == 1
            assert args.max_auto_workers == 4
    for config in configs:
        assert (config.temperature, config.top_p, config.top_k, config.max_tokens) == (0.6, 0.9, None, 4096)
        assert not config.coord_mode and not config.coord_prompt_mode
    metadata = get_prompt_policy_metadata(profile=get_profile())
    assert metadata["policy_name"] == "native_embodied_public_evidence_neutral_report"
    assert metadata["policy_version"] == "2026-05-02-neutral-report"
    legacy = with_prompt_policy(get_profile(), "native_embodied_public_evidence", "2026-04-18")
    assert get_prompt_policy_metadata(profile=legacy)["historical_reference_policy_sha256"] == "b450374f4bcc13a58a782c10522e8bc97f46d92d4b49039ee8f00a4889df1d38"


@pytest.mark.parametrize("limit,devices", [(1, None), (2, "0,1")])
def test_cli_subprocess_mode_enforces_render_limit(tmp_path, monkeypatch, limit, devices):
    import os
    import sys
    from vigil import cli
    from vigil.eval.process import run_episode_process
    episode_root=tmp_path/'episodes';out=tmp_path/'out';events=tmp_path/'events'
    ids=[f'limited_{i}' for i in range(4)]
    for episode_id in ids:_write_episode(episode_root,episode_id)
    pack=tmp_path/'pack.json'
    pack.write_text(json.dumps({'pack_id':'limited','episodes':[{'path':f'episodes/{e}/episode.json'} for e in ids]}))
    child=tmp_path/'child.py'
    child.write_text("import sys\nsys.path.insert(0, " + repr(str(ROOT)) + ")\n" + '''import argparse,json,os,time
from pathlib import Path
from vigil.eval.traces import EpisodeTrace, StepTrace
from vigil.eval.scoring import score_episode
p=argparse.ArgumentParser();p.add_argument('--episode');p.add_argument('--out',type=Path);p.add_argument('--events',type=Path);p.add_argument('--limit',type=int);p.add_argument('--startup-ready-file',type=Path);a=p.parse_args()
def record(kind):
 fd=os.open(a.events,os.O_CREAT|os.O_WRONLY|os.O_APPEND,0o600);os.write(fd,(kind+' '+os.environ.get('VIGIL_GPU_DEVICE','unset')+'\\n').encode());os.close(fd)
record('start')
started=a.events.with_suffix('.started');started.mkdir(exist_ok=True)
(started/a.episode).touch();a.startup_ready_file.touch()
# Keep the first wave alive until every allowed slot has started. A fixed sleep
# could finish before the next interpreter starts on a busy host.
while len(list(started.iterdir())) < a.limit: time.sleep(.01)
(a.out/'traces').mkdir(parents=True,exist_ok=True);(a.out/'scores').mkdir(parents=True,exist_ok=True)
trace=EpisodeTrace(a.episode,'pure_rgb_dialogue_history_baseline',1,(StepTrace(0,terminal=True),),'failure')
(a.out/'traces'/f'{a.episode}.json').write_text(json.dumps(trace.to_dict()))
(a.out/'scores'/f'{a.episode}.score.json').write_text(json.dumps(score_episode(trace).to_dict()))
record('end')
''')
    def launch(cmd,**kwargs):
        episode_id=json.loads(Path(cmd[cmd.index('run-episode')+1]).read_text())["episode_id"]
        return run_episode_process([sys.executable,str(child),'--episode',episode_id,'--out',str(out),'--events',str(events),'--limit',str(limit)],**kwargs)
    monkeypatch.setattr("vigil.eval.batch.run_episode_process", launch)
    gpu_args = ['--render-devices', devices] if devices else []
    assert main(['run-pack','--pack-file',str(pack),'--episode-root',str(episode_root),'--out-dir',str(out),'--script-actions','[{"skill_name":"report","arguments":{"status":"fail"}}]','--workers','4','--boot-concurrency','1','--render-concurrency',str(limit),'--episode-timeout-s','5',*gpu_args])==0
    active=peak=0
    by_device = {}
    for event in events.read_text().splitlines():
        kind, device = event.split()
        delta = 1 if kind == 'start' else -1
        active += delta
        by_device[device] = by_device.get(device, 0) + delta
        if devices:
            assert device in {'0', '1'}
            assert 0 <= by_device[device] <= 1
        peak=max(active,peak)
    assert peak == limit
    assert active==0
    assert all(value == 0 for value in by_device.values())
    if devices:
        assert set(by_device) == {'0', '1'}


@pytest.mark.parametrize('devices', ['', '0,', '-1', '0,0', 'a', '0;1'])
def test_cli_rejects_invalid_renderer_devices(devices):
    from vigil.cli import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(['run', '--render-devices', devices])


def test_renderer_devices_require_process_isolation(tmp_path):
    with pytest.raises(SystemExit) as failure:
        main(['run', '--render-devices', '0,1', '--episode-timeout-s', '0',
              '--dry-run', '--out-dir', str(tmp_path / 'out')])
    assert failure.value.code == 2
    assert not (tmp_path / 'out' / 'run_config.json').exists()
