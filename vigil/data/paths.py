"""Locate release data independently of the shell's working directory."""
from __future__ import annotations

import os
from pathlib import Path
from vigil.paths import source_root

CANONICAL_PACK = "mixed_mainline_manual_revised_1000_v2.json"


def data_root() -> Path:
    override = os.getenv("VIGIL_DATA_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    cwd = Path.cwd()
    roots = [cwd, *cwd.parents]
    release = source_root()
    if release is not None:
        roots.append(release)
    for root in roots:
        candidate = root / "data"
        if (candidate / "benchmark" / "packs" / CANONICAL_PACK).is_file():
            return candidate
    raise FileNotFoundError(
        "Cannot locate VIGIL data. Set VIGIL_DATA_ROOT to the release's data directory, "
        "or supply --pack-file, --episode-root and --scene-root."
    )


def resolve_data_args(args) -> None:
    if hasattr(args, "pack_file"):
        if str(args.pack_file) == "canonical":
            args.pack_file = data_root() / "benchmark" / "packs" / CANONICAL_PACK
        else:
            args.pack_file = Path(args.pack_file).expanduser().resolve()
    for name, folder in (("episode_root", "episodes"), ("scene_root", "scenes")):
        if hasattr(args, name):
            value = getattr(args, name)
            setattr(args, name, Path(value).expanduser().resolve() if value else data_root() / folder)


def resolve_episode_path(episode_or_path: str | Path, episode_root: str | Path = "data/episodes", *, allow_path: bool = True) -> Path:
    """Resolve task IDs under the chosen root; pack callers must disable file fallback."""
    raw = Path(episode_or_path)
    value = str(episode_or_path)
    is_id = bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value
    if is_id:
        candidate = Path(episode_root) / value / "episode.json"
        if candidate.is_file():
            return candidate
    elif not allow_path:
        raise ValueError("Pack episode IDs must be single directory names, not file paths.")
    if allow_path and raw.is_file():
        return raw
    raise FileNotFoundError(f"Could not resolve episode path for {episode_or_path!r} under {episode_root}.")
