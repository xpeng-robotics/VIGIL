"""Keep resumed results tied to the same experiment and executable assets."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import platform
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version

from vigil.data.paths import resolve_episode_path


@contextmanager
def run_lock(out_dir: Path):
    """One pack writer per directory; the OS releases the lock after a crash."""
    try:
        import fcntl
    except ImportError as exc:
        raise RuntimeError("Live pack execution requires Linux or macOS file locking.") from exc
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / ".run.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another evaluation is writing this --out-dir. Use a separate directory.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def experiment_config(args, pack, profile, model_metadata: dict | None) -> dict:
    assets = {}
    for episode in pack.episodes:
        path = resolve_episode_path(episode.episode_id, args.episode_root, allow_path=False)
        assets[f"episode:{episode.episode_id}"] = file_digest(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        scene = payload.get("scene") or {}
        if scene.get("platform") == "procthor":
            ref = payload.get("scene_ref") or scene.get("scene_id")
            key = f"scene:{ref}"
            if key not in assets:
                assets[key] = file_digest(Path(args.scene_root) / str(ref) / "house.json")
    package = Path(__file__).resolve().parents[1]
    runtime = {str(p.relative_to(package)): file_digest(p) for p in sorted(package.rglob("*.py"))}
    versions = {"python": platform.python_version(), "system": platform.system(),
                "architecture": platform.machine()}
    try:
        versions["ai2thor"] = version("ai2thor")
    except PackageNotFoundError:
        versions["ai2thor"] = "not-installed"
    script = args.script_actions
    if args.script_file:
        script = Path(args.script_file).read_text(encoding="utf-8")
    return {
        "schema_version": 1,
        "pack_sha256": file_digest(Path(args.pack_file)),
        "assets_sha256": hashlib.sha256(json.dumps(assets, sort_keys=True).encode()).hexdigest(),
        "runtime_sha256": hashlib.sha256(json.dumps(runtime, sort_keys=True).encode()).hexdigest(),
        "runtime_versions": versions,
        "thor_platform": os.getenv("VIGIL_THOR_PLATFORM", "").strip().lower(),
        "render_devices": getattr(args, "render_devices", None),
        "profile": profile.to_dict(),
        "model": model_metadata,
        "script_sha256": hashlib.sha256(json.dumps(json.loads(script), sort_keys=True).encode()).hexdigest() if script else None,
        "width": args.width,
        "height": args.height,
        "render_depth": args.render_depth,
        "max_steps": args.max_steps,
        "episode_timeout_s": args.episode_timeout_s,
        "save_frames": not args.no_frames,
    }


def prepare_run(out_dir: Path, config: dict, *, resume: bool) -> None:
    path = out_dir / "run_config.json"
    has_outputs = any((out_dir / name).exists() for name in (
        "run_status.json", "aggregate_score.json", "model_config.json"
    )) or any(p.is_file() for folder in ("traces", "scores", "frames")
             for p in (out_dir / folder).rglob("*"))
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError("Unreadable run_config.json; use a new --out-dir.") from exc
        if previous != config:
            keys = sorted(key for key in config if previous.get(key) != config[key]) if isinstance(previous, dict) else ["schema"]
            raise ValueError(f"Experiment differs from existing results ({', '.join(keys)}). Use a new --out-dir.")
        if has_outputs and not resume:
            raise ValueError("Output directory already contains results. Use --resume-existing or a new --out-dir.")
    elif has_outputs:
        raise ValueError("Existing results have no run_config.json; their experiment cannot be verified. Use a new --out-dir.")
    else:
        atomic_json(path, config)
