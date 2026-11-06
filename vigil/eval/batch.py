"""Batch evaluation workflow shared by command-line and workbench entry points."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import argparse
import json
import os
import queue
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any
from vigil.agent.model import OpenAIModelAgent
from vigil.agent.scripted import load_scripted_agent
from vigil.agent.backends import ModelBackendConfig
from vigil.agent.profiles import get_profile
from vigil.agent.prompts import with_prompt_policy
from vigil.data.episodes import load_pack
from vigil.data.paths import resolve_episode_path
from vigil.data.selection import select_episodes
from vigil.config import _model_config_from_args, _model_config_metadata
from vigil.eval.process import run_episode_process
from vigil.eval.dry_run import run_pack_dry
from vigil.eval.offline import evaluate_trace_files
from vigil.eval.traces import load_trace, validate_completed_trace, has_infrastructure_error
from vigil.eval.scoring import score_episode
from vigil.eval.state import atomic_json, experiment_config, prepare_run, run_lock
from vigil.eval.reporting import format_report


def _trace_path_for_episode(out_dir: str | Path, episode_id: str) -> Path:
    return Path(out_dir) / "traces" / f"{episode_id}.json"


def _score_path_for_episode(out_dir: str | Path, episode_id: str) -> Path:
    return Path(out_dir) / "scores" / f"{episode_id}.score.json"


def _pack_platform(pack: Any) -> str:
    return str((getattr(pack, "metadata", {}) or {}).get("platform") or "").strip()


def _load_json_if_valid(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _existing_episode_outputs(out_dir: str | Path, episode_id: str, *, profile: str | None = None) -> tuple[Path, Path] | None:
    trace_path = _trace_path_for_episode(out_dir, episode_id)
    score_path = _score_path_for_episode(out_dir, episode_id)
    score = _load_json_if_valid(score_path)
    if score is None:
        return None
    try:
        trace = load_trace(trace_path)
        if trace.episode_id != episode_id:
            return None
        if profile is not None and trace.profile != profile:
            return None
        validate_completed_trace(trace)
        if score != score_episode(trace).to_dict():
            return None
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None
    return trace_path, score_path


def _has_infrastructure_error(trace) -> bool:
    return has_infrastructure_error(trace)


def _score_status_message(index: int, total: int, episode_id: str, score_path: Path, *, prefix: str = "") -> str:
    payload = _load_json_if_valid(score_path) or {}
    terminal_status = str(payload.get("terminal_status") or payload.get("status") or "unknown")
    episode_score = payload.get("episode_score", payload.get("primary_score", "unknown"))
    label = f"{prefix} " if prefix else ""
    return f"{label}[{index + 1}/{total}] {episode_id}: {terminal_status} score={episode_score}"


def run_pack(args: argparse.Namespace) -> int:
    if args.dry_run:
        return _run_pack(args)
    with run_lock(Path(args.out_dir)):
        return _run_pack(args)


def _run_pack(args: argparse.Namespace) -> int:
    if getattr(args, "render_devices", None) and float(args.episode_timeout_s or 0) <= 0:
        raise ValueError("--render-devices requires --episode-timeout-s greater than zero for isolated child environments.")
    pack = load_pack(args.pack_file)
    profile = get_profile(args.profile)
    if args.prompt_policy_name or args.prompt_policy_version:
        profile = with_prompt_policy(profile, args.prompt_policy_name, args.prompt_policy_version)
    selected = select_episodes(pack, args)
    if args.dry_run:
        result = run_pack_dry(replace(pack, episodes=tuple(selected)), profile, args.out_dir)
        print(f"wrote aggregate: {result.aggregate_path}")
        return 0

    model_config: ModelBackendConfig | None = None
    if not args.script_actions and not args.script_file:
        model_config = _model_config_from_args(args)
    config_metadata = _model_config_metadata(model_config) if model_config else None
    prepare_run(Path(args.out_dir), experiment_config(args, pack, profile, config_metadata), resume=args.resume_existing)
    run_status = {"state": "running", "episode_ids": [e.episode_id for e in selected]}
    atomic_json(Path(args.out_dir) / "run_status.json", run_status)
    (Path(args.out_dir) / "summary.txt").write_text("Run incomplete. Use vigil report after completion.\n", encoding="utf-8")
    if config_metadata is not None:
        atomic_json(Path(args.out_dir) / "model_config.json", config_metadata)
    label = f"{model_config.backend}/{model_config.model}" if model_config else "scripted actions"
    print(f"Running {len(selected)} episode(s) with {label}. Output: {Path(args.out_dir).resolve()}", flush=True)
    if getattr(args, "cancel_event", None) is None:
        args.cancel_event = threading.Event()
    try:
        return _execute_pack(args, pack, profile, selected, model_config, run_status)
    except BaseException as exc:
        args.cancel_event.set()
        state = "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
        atomic_json(Path(args.out_dir) / "run_status.json", {**run_status, "state": state})
        (Path(args.out_dir) / "summary.txt").write_text(
            f"Run {state}. Inspect episode logs and use --resume-existing after resolving the cause.\n",
            encoding="utf-8",
        )
        raise


def _execute_pack(args, pack, profile, selected, model_config, run_status) -> int:
    from vigil.eval import runner
    pack_platform = _pack_platform(pack)
    cancel_event = args.cancel_event
    if cancel_event.is_set():
        raise KeyboardInterrupt("Evaluation cancelled.")

    def run_one(index: int, episode: Any) -> tuple[int, Path, str]:
        episode_path = resolve_episode_path(episode.episode_id, args.episode_root, allow_path=False)
        agent = (
            load_scripted_agent(args.script_actions, args.script_file)
            if args.script_actions or args.script_file
            else OpenAIModelAgent(model_config, profile=profile)
        )
        result = runner.run_episode(
            episode_path=episode_path,
            agent=agent,
            out_dir=args.out_dir,
            width=args.width,
            height=args.height,
            render_depth=args.render_depth,
            max_steps=args.max_steps,
            save_frames=not args.no_frames,
            scene_root=args.scene_root,
            profile=profile,
            controller_boot_gate=controller_boot_gate,
            render_gate=render_gate,
            pack_id=pack.pack_id,
            pack_platform=pack_platform or None,
        )
        return index, result.trace_path, (
            f"[{index + 1}/{len(selected)}] {episode.episode_id}: "
            f"{result.score.terminal_status} score={result.score.episode_score}"
        )

    def run_one_subprocess(index: int, episode: Any) -> tuple[int, Path, str]:
        episode_id = str(episode.episode_id)
        episode_path = resolve_episode_path(episode_id, args.episode_root, allow_path=False).resolve()
        trace_path = _trace_path_for_episode(args.out_dir, episode_id)
        score_path = _score_path_for_episode(args.out_dir, episode_id)
        log_dir = Path(args.out_dir) / "episode_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            "-m",
            "vigil.cli",
            "run-episode",
            str(episode_path),
            "--no-config",
            "--profile",
            str(args.profile),
            "--episode-root",
            str(args.episode_root),
            "--scene-root",
            str(args.scene_root),
            "--out-dir",
            str(args.out_dir),
            "--width",
            str(args.width),
            "--height",
            str(args.height),
        ]
        # Forward only explicit overrides; the child inherits the same environment.
        for name in ("backend", "base_url", "model", "api_key_header", "timeout",
                     "temperature", "top_p", "top_k", "max_tokens", "coord_mode", "coord_prompt_mode",
                     "request_extra_body_json", "supports_json_mode", "max_tokens_field", "image_detail",
                     "request_max_retries", "request_retry_delay_s", "protocol_retry_limit", "observation_echo_retry_limit"):
            if hasattr(args, name):
                value = getattr(args, name)
                if name == "request_extra_body_json":
                    value = json.dumps(value, sort_keys=True)
                if name == "supports_json_mode":
                    value = int(value)
                cmd.extend(["--" + name.replace("_", "-"), "none" if value is None else str(value)])
        child_env = os.environ.copy()
        if model_config is not None:
            # Each isolated worker starts its round-robin counter at zero. Offset
            # the same replica pool per episode so short rollouts use all replicas.
            if len(model_config.base_urls) > 1:
                offset = index % len(model_config.base_urls)
                urls = model_config.base_urls[offset:] + model_config.base_urls[:offset]
                child_env["VIGIL_MODEL_BASE_URLS"] = ",".join(urls)
            # Keep the effective credential out of process arguments and errors.
            for name in ("VIGIL_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
                child_env.pop(name, None)
            if model_config.api_key:
                child_env["VIGIL_API_KEY"] = model_config.api_key
            elif model_config.api_key == "":
                cmd.extend(["--api-key", ""])
        if args.prompt_policy_name:
            cmd.extend(["--prompt-policy-name", str(args.prompt_policy_name)])
        if args.prompt_policy_version:
            cmd.extend(["--prompt-policy-version", str(args.prompt_policy_version)])
        cmd.extend(["--pack-id", str(pack.pack_id)])
        if pack_platform:
            cmd.extend(["--pack-platform", pack_platform])
        if args.script_actions:
            cmd.extend(["--script-actions", str(args.script_actions)])
        if args.script_file:
            cmd.extend(["--script-file", str(args.script_file)])
        if args.max_steps is not None:
            cmd.extend(["--max-steps", str(args.max_steps)])
        if args.no_frames:
            cmd.append("--no-frames")
        if args.render_depth:
            cmd.append("--render-depth")

        stdout_path = log_dir / f"{episode_id}.stdout.log"
        stderr_path = log_dir / f"{episode_id}.stderr.log"
        timeout_s = float(args.episode_timeout_s or 0)
        try:
            returncode = run_episode_process(
                cmd, stdout_path=stdout_path, stderr_path=stderr_path,
                timeout_s=timeout_s, boot_gate=controller_boot_gate,
                render_gate=render_gate,
                device_pool=device_pool,
                cancel_event=getattr(args, "cancel_event", None),
                env=child_env,
            )
        except subprocess.TimeoutExpired as exc:
            with stderr_path.open("a", encoding="utf-8") as stderr:
                stderr.write(f"\n[run-pack] episode timeout after {timeout_s:.0f}s\n")
            raise TimeoutError(
                f"episode timed out after {timeout_s:.0f}s: {episode_id}; "
                f"logs: {stdout_path}, {stderr_path}"
            ) from exc
        trace = load_trace(trace_path) if trace_path.is_file() else None
        valid_outputs = (trace is not None and trace.episode_id == episode_id
                         and _load_json_if_valid(score_path) == score_episode(trace).to_dict())
        if returncode != 0 and not (valid_outputs and _has_infrastructure_error(trace)):
            raise RuntimeError(
                f"episode subprocess failed rc={returncode}: {episode_id}; "
                f"logs: {stdout_path}, {stderr_path}"
            )
        if not valid_outputs:
            raise RuntimeError(f"episode subprocess did not write valid trace/score: {episode_id}")
        return index, trace_path, _score_status_message(index, len(selected), episode_id, score_path)

    indexed_trace_paths: dict[int, Path] = {}
    indexed_episodes = list(enumerate(selected))
    episodes_to_run: list[tuple[int, Any]] = []
    if args.resume_existing:
        for index, episode in indexed_episodes:
            existing = _existing_episode_outputs(args.out_dir, str(episode.episode_id), profile=profile.name)
            if existing is None:
                episodes_to_run.append((index, episode))
                continue
            trace_path, score_path = existing
            indexed_trace_paths[index] = trace_path
            print(_score_status_message(index, len(selected), str(episode.episode_id), score_path, prefix="[resume-skip]"), flush=True)
    else:
        episodes_to_run = indexed_episodes
    requested_workers = int(args.workers if args.workers is not None else 1)
    if requested_workers <= 0:
        max_auto_workers = max(1, int(args.max_auto_workers or 1))
        worker_count = min(len(episodes_to_run), max_auto_workers, os.cpu_count() or 1)
        print(
            f"[auto-workers] selected={len(episodes_to_run)} workers={worker_count} "
            f"cap={max_auto_workers}",
            flush=True,
        )
    else:
        worker_count = max(1, requested_workers)
    worker_count = min(worker_count, len(episodes_to_run)) if episodes_to_run else 0
    boot_concurrency = int(args.boot_concurrency or 0)
    if boot_concurrency <= 0:
        boot_concurrency = max(1, min(8, worker_count))
    render_concurrency = int(args.render_concurrency or 0)
    if render_concurrency <= 0:
        render_concurrency = max(1, min(4, worker_count))
    boot_concurrency = max(1, min(boot_concurrency, worker_count))
    render_concurrency = max(1, min(render_concurrency, worker_count))
    controller_boot_gate = threading.Semaphore(boot_concurrency) if worker_count > 1 else None
    render_gate = threading.Semaphore(render_concurrency) if worker_count > 1 else None
    devices = getattr(args, "render_devices", None)
    device_pool = None
    if devices:
        device_pool = queue.Queue()
        for slot in range(render_concurrency):
            device_pool.put(devices[slot % len(devices)])
    use_subprocess = float(args.episode_timeout_s or 0) > 0
    run_episode_fn = run_one_subprocess if use_subprocess else run_one
    worker_errors = []
    error_lock = threading.Lock()

    def guarded_run_one(index, episode):
        if cancel_event.is_set():
            raise KeyboardInterrupt("Evaluation cancelled.")
        try:
            return run_episode_fn(index, episode)
        except BaseException as exc:
            # Set cancellation before this worker can pick up another queued task.
            with error_lock:
                if not worker_errors:
                    worker_errors.append(exc)
                cancel_event.set()
            raise

    if not episodes_to_run:
        print("[resume] all selected episodes already have valid trace/score files", flush=True)
    elif worker_count == 1:
        for index, episode in episodes_to_run:
            print(f"[{index + 1}/{len(selected)}] starting {episode.episode_id}", flush=True)
            result_index, trace_path, message = guarded_run_one(index, episode)
            indexed_trace_paths[result_index] = trace_path
            print(message, flush=True)
    else:
        print(
            f"running {len(episodes_to_run)} episodes with {worker_count} workers "
            f"(boot_concurrency={boot_concurrency}, render_concurrency={render_concurrency}, "
            f"episode_subprocess={int(use_subprocess)}, episode_timeout_s={float(args.episode_timeout_s or 0):.0f})",
            flush=True,
        )
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(guarded_run_one, index, episode): (index, episode.episode_id)
                for index, episode in episodes_to_run
            }
            try:
                for future in as_completed(futures):
                    result_index, trace_path, message = future.result()
                    indexed_trace_paths[result_index] = trace_path
                    print(message, flush=True)
            except BaseException:
                cancel_event.set()
                for future in futures:
                    future.cancel()
                if worker_errors:
                    raise worker_errors[0]
                raise

    if cancel_event.is_set():
        raise KeyboardInterrupt("Evaluation cancelled.")

    missing = [episode.episode_id for index, episode in indexed_episodes if index not in indexed_trace_paths]
    if missing:
        preview = ", ".join(str(item) for item in missing[:20])
        suffix = "" if len(missing) <= 20 else f", ... (+{len(missing) - 20} more)"
        raise SystemExit(f"Missing traces for {len(missing)} selected episodes: {preview}{suffix}")
    trace_paths = [indexed_trace_paths[index] for index, _ in indexed_episodes]
    failed = [path.stem for path in trace_paths if _has_infrastructure_error(load_trace(path))]
    if failed:
        report = (
            f"INCOMPLETE: infrastructure/model request errors in {len(failed)} episodes. "
            "Final aggregate metrics were not generated. Inspect traces, fix the cause, "
            "then use --resume-existing."
        )
        atomic_json(Path(args.out_dir) / "run_status.json", {
            **run_status, "state": "infrastructure_error", "infrastructure_errors": failed,
        })
        (Path(args.out_dir) / "summary.txt").write_text(report + "\n", encoding="utf-8")
        print(report, file=sys.stderr)
        return 1
    aggregate = evaluate_trace_files([str(path) for path in trace_paths])
    aggregate_path = Path(args.out_dir) / "aggregate_score.json"
    atomic_json(aggregate_path, aggregate.to_dict())
    print(f"wrote aggregate score: {aggregate_path}", flush=True)
    report = format_report(aggregate.to_dict())
    (Path(args.out_dir) / "summary.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    atomic_json(Path(args.out_dir) / "run_status.json", {
        **run_status, "state": "complete", "infrastructure_errors": [],
    })
    return 0
