"""Local readiness checks, with optional live simulator and model probes."""
from __future__ import annotations

from importlib.util import find_spec
import json
import os
import platform
import sys
from pathlib import Path
import tempfile

from vigil.data.episodes import EpisodeSpec, load_pack
from vigil.agent.backends import create_model_client
from vigil.data.paths import resolve_episode_path


def check_environment(args, config_loader) -> list[dict]:
    checks = []

    def record(name, status, message):
        checks.append({"check": name, "status": status, "message": message})

    record("python", "ok" if sys.version_info >= (3, 10) else "error", f"Python {platform.python_version()}; requires 3.10+.")
    available = find_spec("ai2thor") is not None
    record("ai2thor", "ok" if available else "error", "Installed." if available else 'Install the simulator: python -m pip install -e ".[thor]"')
    if platform.system() == "Linux" and not os.getenv("DISPLAY") and os.getenv("VIGIL_THOR_PLATFORM", "").lower() != "cloud":
        record("rendering", "warning", "No DISPLAY. For headless GPU rendering set VIGIL_THOR_PLATFORM=cloud and configure a Vulkan driver.")
    elif platform.system() == "Darwin" and platform.machine() == "arm64":
        record("rendering", "warning", "Apple Silicon runtime compatibility depends on the AI2-THOR build. Run doctor --check-simulator to verify.")
    else:
        record("rendering", "info", "Static checks cannot verify rendering. Use --check-simulator.")
    first_episode = None
    try:
        pack = load_pack(args.pack_file)
        scenes = set()
        for row in pack.episodes:
            episode = EpisodeSpec.from_path(resolve_episode_path(row.episode_id, args.episode_root, allow_path=False))
            if first_episode is None:
                first_episode = episode
            if episode.scene.get("platform") == "procthor":
                scene = Path(args.scene_root) / str(episode.scene_ref) / "house.json"
                if scene not in scenes:
                    payload = json.loads(scene.read_text(encoding="utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError(f"Invalid scene: {scene}")
                    scenes.add(scene)
        record("data", "ok", f"{len(pack.episodes)} executable episodes and {len(scenes)} scene files checked.")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        record("data", "error", str(exc))
    try:
        Path(args.out_dir).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=args.out_dir):
            pass
        record("output", "ok", f"Writable: {args.out_dir}")
    except OSError as exc:
        record("output", "error", str(exc))
    try:
        config = config_loader(args)
        if config.backend.replace("_", "-").lower() in {"gemini", "anthropic", "claude", "openai"} and not config.api_key:
            raise ValueError("The selected provider requires an API key. Set VIGIL_API_KEY or the provider's key variable.")
        record("model_config", "ok", f"Backend {config.backend}; model {config.model}; API key {'set' if config.api_key else 'not set'}.")
        if args.check_model:
            response = create_model_client(config).chat([{"role": "user", "content": 'Reply with JSON: {"ok": true}'}], json_mode=True)
            if not response.content.strip():
                raise ValueError("Model returned empty text.")
            record("model_request", "ok", "Text request succeeded. Use smoke to verify the complete RGB action loop.")
    except Exception as exc:
        configured = args.check_model or hasattr(args, "model") or bool(os.getenv("VIGIL_MODEL_NAME"))
        record("model_config" if not args.check_model else "model_request", "error" if configured else "warning", str(exc))
    if args.check_simulator:
        from vigil.eval.runner import _validate_model_frame
        from vigil.envs.thor import PublicThorEnv
        if first_episode is None or not available:
            record("simulator", "error", "Fix the data and AI2-THOR checks before starting the simulator.")
        else:
            env = None
            try:
                env = PublicThorEnv(first_episode, scene_root=args.scene_root)
                env.reset()
                with tempfile.TemporaryDirectory(prefix="vigil-doctor-") as folder:
                    image = env.save_frame(Path(folder) / "frame.png")
                    if not image or not Path(image).is_file():
                        raise RuntimeError("Simulator did not produce an RGB frame.")
                    _validate_model_frame(env, episode_id=first_episode.episode_id, step_index=0, image_path=str(image))
                record("simulator", "ok", "Scene reset and RGB rendering succeeded.")
            except Exception as exc:
                record("simulator", "error", str(exc))
            finally:
                if env is not None:
                    try:
                        env.close()
                    except Exception as exc:
                        record("simulator_cleanup", "error", str(exc))
    return checks
