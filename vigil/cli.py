from __future__ import annotations

import argparse
import os
import json
import platform
import shlex
import signal
import sys
import threading
from collections import Counter
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from vigil.data.episodes import EpisodeSpec, load_pack
from vigil.data.families import FAMILY_ALIASES
from vigil.eval.offline import evaluate_trace_files, write_json
from vigil.agent.prompts import with_prompt_policy
from vigil.agent.profiles import DEFAULT_PROFILE_NAME, get_profile, list_profiles
from vigil.data.paths import resolve_data_args, resolve_episode_path
from vigil.data.selection import select_episodes
from vigil.eval.reporting import format_report, validate_stored_summary
from vigil.config import DEFAULT_CONFIG, apply_model_config, create_config, _model_config_from_args


def _json_object_arg(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise argparse.ArgumentTypeError("value must decode to a JSON object")
    return payload


def _cmd_init(args: argparse.Namespace) -> int:
    path = create_config(args.path, args.backend, model=args.model, base_url=args.base_url)
    print(f"Created {path}")
    if not args.model:
        print("Set model in the file, or configure it in vigil ui.")
    print("If authentication is required, set VIGIL_API_KEY or your provider's key environment variable.")
    suffix = "" if path == Path.cwd() / DEFAULT_CONFIG else f" --config {shlex.quote(str(path))}"
    print(f"Check setup: vigil doctor{suffix}\nRun one episode: vigil smoke{suffix} --out-dir outputs/first-run")
    print(f"Inspect: vigil ui{suffix} --results-dir outputs/first-run")
    return 0


def _cmd_print_env(_: argparse.Namespace) -> int:
    payload = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "ai2thor_available": find_spec("ai2thor") is not None,
        "pytest_available": find_spec("pytest") is not None,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_list_profiles(args: argparse.Namespace) -> int:
    profiles = list_profiles()
    if args.json:
        print(json.dumps(profiles, indent=2, sort_keys=True))
    else:
        for profile in profiles:
            print(f"{profile['name']}	{profile['description']}")
    return 0


def _cmd_validate_pack(args: argparse.Namespace) -> int:
    pack = load_pack(args.pack_file)
    print(f"valid pack: {pack.pack_id} ({len(pack.episodes)} episodes)")
    return 0


def _cmd_list_episodes(args: argparse.Namespace) -> int:
    episodes = select_episodes(load_pack(args.pack_file), args)
    rows = [{"episode_id": e.episode_id, "task_family": e.task_family,
             "difficulty": e.metadata.get("difficulty") or e.metadata.get("aux_difficulty") or e.trace_hints.get("difficulty") or "unknown",
             "scene_id": e.scene_id} for e in episodes]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("episode_id\ttask_family\tdifficulty\tscene_id")
        for row in rows:
            print("\t".join(str(value) for value in row.values()))
    return 0


def _cmd_catalog(args: argparse.Namespace) -> int:
    """Summarize executable tasks, without inferring platforms from pack stubs."""
    pack = load_pack(args.pack_file)
    selected = select_episodes(pack, args)
    episodes = []
    for entry in selected:
        path = resolve_episode_path(entry.episode_id, args.episode_root, allow_path=False)
        episode = EpisodeSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if episode.episode_id != entry.episode_id or episode.task_family != entry.task_family:
            raise ValueError("Executable episode identity differs from the selected pack.")
        episodes.append(episode)
    platforms = Counter(str(e.scene.get("platform") or "unknown") for e in episodes)
    scenes = {platform: len({e.scene_ref or e.scene_id for e in episodes
                            if str(e.scene.get("platform") or "unknown") == platform})
              for platform in platforms}
    codes = {value: key for key, value in FAMILY_ALIASES.items()}
    families = []
    for family in dict.fromkeys(e.task_family for e in episodes):
        tasks = [e for e in episodes if e.task_family == family]
        families.append({"code": codes.get(family, family), "task_family": family,
                         "episodes": len(tasks), "step_budgets": sorted({e.max_steps for e in tasks}),
                         "example": {"episode_id": tasks[0].episode_id, "instruction": tasks[0].instruction}})
    result = {"pack_id": pack.pack_id, "episode_count": len(episodes),
              "platform_episodes": dict(platforms), "scene_references": scenes, "families": families}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"VIGIL task catalog — {len(episodes):,} selected episodes / {len(families)} task families")
        print("Selection: " + ", ".join(f"{count} {name} tasks" for name, count in platforms.items()))
        print("Scene references: " + ", ".join(f"{count} {name}" for name, count in scenes.items()))
        for family in families:
            print(f"\n{family['code']}  {family['episodes']} tasks | step budgets: {', '.join(map(str, family['step_budgets']))}")
            print(f"  {family['example']['instruction']}")
        print("\nCatalog inspection only; no model or simulator was started.")
        print("Choose tasks: vigil list-episodes --task-family PG --max-episodes 5")
        print("Try an episode: vigil smoke --task-family PG --out-dir outputs/first-run")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    from vigil.diagnostics import check_environment
    checks = check_environment(args, _model_config_from_args)
    if args.json:
        print(json.dumps(checks, indent=2))
    else:
        for check in checks:
            print(f"[{check['status']}] {check['check']}: {check['message']}")
    return int(any(check["status"] == "error" for check in checks))


def _cmd_report(args: argparse.Namespace) -> int:
    path = args.path / "aggregate_score.json" if args.path.is_dir() else args.path
    status_path = path.parent / "run_status.json"
    tracked = status_path.exists() or args.path.is_dir() or any(
        (path.parent / name).exists() for name in ("run_config.json", "traces", "scores")
    )
    if tracked:
        if not status_path.is_file():
            raise ValueError("Run directory is missing run_status.json; final metrics cannot be verified. "
                             "Use vigil progress to inspect saved files, or score-traces to rescore an explicit subset.")
        from vigil.eval.inspection import verify_run
        verify_run(path.parent)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if tracked and payload != json.loads((path.parent / "aggregate_score.json").read_text(encoding="utf-8")):
        raise ValueError("Requested aggregate does not match the verified run aggregate.")
    if not tracked:
        validate_stored_summary(payload)
        print("UNVERIFIED stored summary — no run selection or trace evidence was checked.")
    print(format_report(payload))
    return 0


def _cmd_progress(args: argparse.Namespace) -> int:
    from vigil.eval.inspection import inspect_progress
    payload = inspect_progress(args.path)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        total = payload["selected_episodes"] if payload["selected_episodes"] is not None else "unknown"
        print(f"State: {payload['state']} | saved traces: {payload['saved_traces']}/{total} | saved scores: {payload['saved_scores']}/{total}")
        print("File counts are progress only. Use vigil verify-run after completion to check results.")
        for name in payload["latest_traces"]:
            print(f"  {name}")
    return 0


def _cmd_verify_run(args: argparse.Namespace) -> int:
    from vigil.eval.inspection import verify_run
    payload = verify_run(args.path, require_frames=args.require_frames)
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        total = payload["episode_count"]
        print(f"Verified {total} selected episodes, {payload['agent_steps']} steps: settlements, scores and aggregate agree.")
        print(f"W: {payload['world_success_count']}/{total} | B: {payload['benchmark_success_count']}/{total}")
        print("Checks saved evidence consistency; does not establish full benchmark coverage or paper reproduction.")
    return 0


def _cmd_run_pack(args: argparse.Namespace) -> int:
    from vigil.eval.batch import run_pack
    return run_pack(args)


def _cmd_score_trace(args: argparse.Namespace) -> int:
    aggregate = evaluate_trace_files([args.trace_file])
    if aggregate.episode_count != 1:
        raise ValueError("score-trace requires exactly one episode; use score-traces for multiple episodes.")
    score = aggregate.scores[0].to_dict()
    if args.out:
        write_json(args.out, score)
        print(f"wrote score: {args.out}")
    else:
        print(json.dumps(score, indent=2, sort_keys=True))
    return 0


def _cmd_score_traces(args: argparse.Namespace) -> int:
    aggregate = evaluate_trace_files([str(path) for path in args.trace_paths])
    payload = aggregate.to_dict()
    if args.out:
        write_json(args.out, aggregate)
        print(f"wrote aggregate score: {args.out}")
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _cmd_run_episode(args: argparse.Namespace) -> int:
    from vigil.eval.state import run_lock
    if args.startup_ready_file:
        # Pack workers are protected by their parent's output lock/fingerprint.
        return _run_episode(args)
    with run_lock(Path(args.out_dir)):
        out = Path(args.out_dir)
        if (out / "run_config.json").exists() or any(
            path.is_file() for folder in ("traces", "scores", "frames") for path in (out / folder).rglob("*")
        ):
            raise ValueError("Output directory already contains rollout evidence. Use a new --out-dir for run-episode; "
                             "use run --resume-existing only for a matching pack run.")
        return _run_episode(args)


def _run_episode(args: argparse.Namespace) -> int:
    from vigil.agent.model import OpenAIModelAgent
    from vigil.agent.scripted import load_scripted_agent
    from vigil.eval.runner import run_episode
    from vigil.eval.batch import _has_infrastructure_error
    episode_path = resolve_episode_path(args.episode, args.episode_root)
    if not args.startup_ready_file and (Path(args.out_dir) / "run_config.json").exists():
        raise ValueError("This output directory belongs to a pack run. Use a new --out-dir for run-episode.")
    scripted = load_scripted_agent(args.script_actions, args.script_file)
    profile = get_profile(args.profile)
    if args.prompt_policy_name or args.prompt_policy_version:
        profile = with_prompt_policy(profile, args.prompt_policy_name, args.prompt_policy_version)
    if scripted is not None:
        agent = scripted
    else:
        config = _model_config_from_args(args)
        agent = OpenAIModelAgent(config, profile=profile)
    result = run_episode(
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
        pack_id=args.pack_id,
        pack_platform=args.pack_platform,
        startup_ready_callback=args.startup_ready_file.touch if args.startup_ready_file else None,
    )
    print(json.dumps({
        "episode_id": result.trace.episode_id,
        "trace_path": str(result.trace_path),
        "score_path": str(result.score_path),
        "success": result.score.success,
        "episode_score": result.score.episode_score,
        "terminal_status": result.score.terminal_status,
    }, indent=2, sort_keys=True))
    return int(_has_infrastructure_error(result.trace))


def _render_devices_arg(raw: str) -> list[int]:
    values = raw.split(",")
    if not values or any(not value.strip().isdecimal() for value in values):
        raise argparse.ArgumentTypeError("Use comma-separated nonnegative renderer device IDs, for example 0,1.")
    devices = [int(value) for value in values]
    if len(devices) != len(set(devices)):
        raise argparse.ArgumentTypeError("Renderer device IDs must be unique.")
    return devices


def _nonnegative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return value


def _positive_int(raw: str) -> int:
    value = _nonnegative_int(raw)
    if value == 0:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def _timeout_arg(raw: str) -> float:
    import math
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return value


def _optional_float(raw: str) -> float | None:
    return None if raw.lower() in {"none", "null"} else float(raw)


def _optional_int(raw: str) -> int | None:
    return None if raw.lower() in {"none", "null"} else _positive_int(raw)


def _add_model_args(parser):
    _add_config_args(parser)
    group = parser.add_argument_group("model configuration", "Priority: CLI > vigil.json > environment > defaults.")
    fields = (
        ("backend", str, "openai-compatible, openai, vllm, gemini, anthropic, or claude; VIGIL_BACKEND"),
        ("base-url", str, "Endpoint URL (root, /v1 or full path); VIGIL_MODEL_BASE_URL"),
        ("model", str, "Model name; VIGIL_MODEL_NAME"),
        ("api-key", str, "API key; VIGIL_API_KEY or provider key"),
        ("api-key-header", str, "API key header; VIGIL_API_KEY_HEADER"),
        ("timeout", _positive_int, "Model request timeout in seconds; VIGIL_TIMEOUT_S, default 120"),
        ("temperature", _optional_float, "Sampling temperature or none; VIGIL_TEMPERATURE, default 0.6"),
        ("top-p", _optional_float, "Nucleus sampling or none; VIGIL_TOP_P, default 0.9"),
        ("top-k", _optional_int, "Top-k or none; VIGIL_TOP_K, default omitted"),
        ("max-tokens", _positive_int, "Generation budget; VIGIL_MAX_TOKENS, default 4096"),
        ("coord-mode", str, "Coordinate adapter; VIGIL_COORD_MODE"),
        ("coord-prompt-mode", str, "Coordinate prompt hint; VIGIL_COORD_PROMPT_MODE"),
        ("max-tokens-field", str, "OpenAI token field: max_tokens or max_completion_tokens; VIGIL_MAX_TOKENS_FIELD"),
        ("image-detail", str, "OpenAI image detail: default, auto, high, low; VIGIL_IMAGE_DETAIL"),
        ("request-max-retries", int, "Transport retries after the first attempt; VIGIL_MODEL_REQUEST_MAX_RETRIES, default 2"),
        ("request-retry-delay-s", float, "Delay between transport retries; VIGIL_MODEL_REQUEST_RETRY_DELAY_S, default 1"),
        ("protocol-retry-limit", int, "Model protocol correction attempts; VIGIL_PROTOCOL_RETRY_LIMIT, default 0"),
        ("observation-echo-retry-limit", int, "Observation echo correction attempts; VIGIL_OBSERVATION_ECHO_RETRY_LIMIT, default 0"),
        ("request-extra-body-json", _json_object_arg, "Extra request body; VIGIL_EXTRA_BODY_JSON"),
    )
    for name, kind, help_text in fields:
        group.add_argument("--" + name, type=kind, default=argparse.SUPPRESS, help=help_text)
    group.add_argument("--supports-json-mode", type=int, choices=(0, 1), default=argparse.SUPPRESS, help="Request JSON response format; VIGIL_SUPPORTS_JSON_MODE, default 1.")


def _add_config_args(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--config", type=Path, default=argparse.SUPPRESS, help="Model settings file; defaults to ./vigil.json when present.")
    group.add_argument("--no-config", action="store_true", default=argparse.SUPPRESS, help="Use only CLI and environment settings.")


def _add_data_args(parser, *, pack=False):
    if pack:
        parser.add_argument("--pack-file", default="canonical", help="Pack path or canonical (default).")
    parser.add_argument("--episode-root", type=Path, default=None, help="Executable episodes; default located from release data.")
    parser.add_argument("--scene-root", type=Path, default=None, help="Scene assets; default located from release data.")


def _add_selection_args(parser, *, limit=None):
    parser.add_argument("--task-family", action="append", help="PG, DA, VS, SV, AI, SI, SM, CR or a stored family ID; repeat to include several.")
    parser.add_argument("--difficulty", action="append", help="Keep a difficulty; repeat to include several.")
    parser.add_argument("--start-index", type=_nonnegative_int, default=0, help="Start index within the filtered tasks.")
    parser.add_argument("--max-episodes", type=_positive_int, default=limit)


def _add_execution_args(parser):
    _add_model_args(parser)
    parser.add_argument("--profile", default=DEFAULT_PROFILE_NAME)
    parser.add_argument("--prompt-policy-name", default=None)
    parser.add_argument("--prompt-policy-version", default=None)
    parser.add_argument("--out-dir", type=Path, default=Path("outputs/eval"))
    scripts = parser.add_mutually_exclusive_group()
    scripts.add_argument("--script-actions", default=None, help="JSON actions for a simulator run without a model.")
    scripts.add_argument("--script-file", type=Path, default=None)
    parser.add_argument("--max-steps", type=_nonnegative_int, default=0, help="Episode step limit; 0 uses the episode budget.")
    parser.add_argument("--width", type=_positive_int, default=640)
    parser.add_argument("--height", type=_positive_int, default=480)
    parser.add_argument("--render-depth", action="store_true")
    parser.add_argument("--no-frames", action="store_true", help="Discard PNG files after execution; RGB still reaches the model.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VIGIL — embodied model evaluation and RGB replay",
        usage="%(prog)s COMMAND [options]", prog="vigil",
        epilog="Start: vigil ui | Inspect tasks: vigil catalog | Evaluate: vigil init, vigil doctor, vigil smoke.\nUse vigil COMMAND --help for options.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_config_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True, title="commands", metavar="COMMAND")

    initialize = subparsers.add_parser("init", help="Create a model configuration file.")
    initialize.add_argument("path", type=Path, nargs="?", default=Path(DEFAULT_CONFIG))
    initialize.add_argument("--backend", choices=("openai-compatible", "vllm", "openai", "gemini", "anthropic", "claude"), default="openai-compatible")
    initialize.add_argument("--model", help="Provider model identifier; leave out to edit it later.")
    initialize.add_argument("--base-url", help="Local or hosted endpoint; native providers have built-in defaults.")
    initialize.set_defaults(func=_cmd_init)

    ui = subparsers.add_parser("ui", help="Open the local workbench: setup, task selection, progress and RGB replay.")
    ui.add_argument("--port", type=int, default=0, help="Local port; 0 chooses an available port (default). Set a fixed port for SSH forwarding.")
    ui.add_argument("--config", type=Path, default=argparse.SUPPRESS, help="Model settings to edit; default vigil.json.")
    ui.add_argument("--results-dir", type=Path, default=Path("outputs"), help="Browse existing results here; does not change where new evaluations are saved.")
    ui.add_argument("--out-dir", type=Path, default=Path("outputs"), help="Save new UI evaluations here (default: outputs).")
    ui.add_argument("--no-open", action="store_true", help="Print the URL without opening a browser.")
    def launch_ui(args):
        if getattr(args, "no_config", False):
            raise ValueError("The workbench edits a settings file; --no-config is for evaluation commands. "
                             "Use vigil ui --config PATH to select a separate file.")
        from vigil.web.app import serve
        return serve(port=args.port, config=getattr(args, "config", Path(DEFAULT_CONFIG)), results=args.results_dir, out_dir=args.out_dir, open_browser=not args.no_open)
    ui.set_defaults(func=launch_ui)

    print_env = subparsers.add_parser("print-env", help="Print local environment information.")
    print_env.set_defaults(func=_cmd_print_env)
    profiles = subparsers.add_parser("list-profiles", help="List benchmark profiles.")
    profiles.add_argument("--json", action="store_true")
    profiles.set_defaults(func=_cmd_list_profiles)
    validate = subparsers.add_parser("validate-pack", help="Validate a pack manifest.")
    validate.add_argument("pack_file", nargs="?", default="canonical")
    validate.set_defaults(func=_cmd_validate_pack)

    catalog = subparsers.add_parser("catalog", help="Inspect task families, examples and data coverage without a simulator or key.")
    catalog.add_argument("--pack-file", default="canonical")
    catalog.add_argument("--episode-root", type=Path, default=None)
    _add_selection_args(catalog)
    catalog.add_argument("--json", action="store_true")
    catalog.set_defaults(func=_cmd_catalog)

    listing = subparsers.add_parser("list-episodes", help="List and filter benchmark tasks.")
    listing.add_argument("--pack-file", default="canonical")
    _add_selection_args(listing)
    listing.add_argument("--json", action="store_true")
    listing.set_defaults(func=_cmd_list_episodes)

    doctor = subparsers.add_parser("doctor", help="Check installation, data, output access and model configuration.")
    _add_data_args(doctor, pack=True)
    _add_model_args(doctor)
    doctor.add_argument("--out-dir", type=Path, default=Path("outputs/doctor"))
    doctor.add_argument("--check-simulator", action="store_true", help="Start AI2-THOR and verify an RGB frame (may download runtime assets).")
    doctor.add_argument("--check-model", action="store_true", help="Send a small text request to the configured model (uses API quota).")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=_cmd_doctor)

    for command in ("run", "smoke"):
        run = subparsers.add_parser(command, aliases=["run-pack"] if command == "run" else [], help="Run one real episode." if command == "smoke" else "Run the benchmark with selection, concurrency and resume.")
        _add_data_args(run, pack=True)
        _add_execution_args(run)
        _add_selection_args(run, limit=1 if command == "smoke" else None)
        run.add_argument("--dry-run", action="store_true", help="Validate selection and write a manifest; no simulation or model calls.")
        run.add_argument("--workers", "--parallel-workers", dest="workers", type=_nonnegative_int, default=1, help="Concurrent episodes; default 1. 0 chooses up to the auto cap and CPU count.")
        run.add_argument("--max-auto-workers", type=_positive_int, default=4)
        run.add_argument("--boot-concurrency", type=_nonnegative_int, default=0, help="Simultaneous controller launches; 0 uses min(8, workers).")
        run.add_argument("--render-concurrency", type=_nonnegative_int, default=0, help="Live render processes; 0 uses min(4, workers).")
        run.add_argument("--render-devices", type=_render_devices_arg, default=None, help="Distribute renderer slots across device IDs, e.g. 0,1; requires episode subprocesses. Does not allocate GPUs.")
        run.add_argument("--resume-existing", action="store_true", help="Reuse verified results from the same experiment.")
        run.add_argument("--episode-timeout-s", type=_timeout_arg, default=1800.0, help="Episode subprocess wall-time limit, default 1800; 0 runs in process without this limit.")
        run.set_defaults(func=_cmd_run_pack)
        if command == "smoke":
            run.set_defaults(out_dir=Path("outputs/smoke"))

    episode = subparsers.add_parser("run-episode", help="Run an episode id or episode.json path.")
    episode.add_argument("episode")
    _add_data_args(episode)
    _add_execution_args(episode)
    episode.add_argument("--pack-id", default=None, help=argparse.SUPPRESS)
    episode.add_argument("--pack-platform", default=None, help=argparse.SUPPRESS)
    episode.add_argument("--startup-ready-file", type=Path, default=None, help=argparse.SUPPRESS)
    episode.set_defaults(func=_cmd_run_episode)

    score = subparsers.add_parser("score-trace", help="Score one episode trace.")
    score.add_argument("trace_file", type=Path)
    score.add_argument("--out", type=Path, help="Write a new score file; existing files are never overwritten.")
    score.set_defaults(func=_cmd_score_trace)
    scores = subparsers.add_parser("score-traces", help="Score trace files or directories.")
    scores.add_argument("trace_paths", nargs="+", type=Path)
    scores.add_argument("--out", type=Path, help="Write a new aggregate file; existing files are never overwritten.")
    scores.set_defaults(func=_cmd_score_traces)
    report = subparsers.add_parser("report", help="Show W/B metrics and failure diagnostics from an aggregate.")
    report.add_argument("path", type=Path, help="Run directory or aggregate_score.json")
    report.set_defaults(func=_cmd_report)
    progress = subparsers.add_parser("progress", help="Inspect saved progress without model or simulator calls.")
    progress.add_argument("path", type=Path, help="Run directory")
    progress.add_argument("--json", action="store_true")
    progress.set_defaults(func=_cmd_progress)
    verify = subparsers.add_parser("verify-run", help="Rebuild settlements and verify scores against saved step evidence.")
    verify.add_argument("path", type=Path, help="Completed release-format run directory")
    verify.add_argument("--require-frames", action="store_true", help="Also require a PNG header for every step's RGB file.")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=_cmd_verify_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(argv) if argv is not None else sys.argv[1:]
    if not argv:
        print("VIGIL — start here:\n  vigil ui       Explore recorded RGB trajectories.\n  vigil catalog  Inspect tasks and examples without a model or simulator.\n  vigil init     Configure your model; --model and --base-url are optional.\n  vigil doctor   Check your setup.\n  vigil smoke    Run one real episode.\n  vigil run      Scale up with task selection, workers and resume.\n\nInspect results: vigil ui --results-dir outputs/first-run\nUse vigil --help for all commands.")
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    handlers = {}
    if args.command in {"run", "run-pack", "smoke"} and args.episode_timeout_s and threading.current_thread() is threading.main_thread():
        args.cancel_event = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda *_: args.cancel_event.set())
    try:
        if args.command in {"doctor", "run", "run-pack", "smoke", "run-episode"}:
            apply_model_config(args)
        resolve_data_args(args)
        return int(args.func(args))
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(2, f"vigil: {exc}\n")
    except KeyboardInterrupt:
        parser.exit(130, "vigil: interrupted. Completed pack episodes can be reused with --resume-existing.\n")
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
