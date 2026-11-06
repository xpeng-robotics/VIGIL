"""Select tasks consistently for listing, dry runs and execution."""
import argparse
from typing import Any
from vigil.data.families import normalize_family


def select_episodes(pack: Any, args: argparse.Namespace) -> list:
    episodes = list(pack.episodes)
    if args.task_family:
        families = {normalize_family(value) for value in args.task_family}
        episodes = [episode for episode in episodes if normalize_family(episode.task_family) in families]
    if args.difficulty:
        episodes = [episode for episode in episodes if str(episode.metadata.get("difficulty") or episode.metadata.get("aux_difficulty") or episode.trace_hints.get("difficulty") or "unknown") in args.difficulty]
    episodes = episodes[args.start_index:]
    if args.max_episodes is not None:
        episodes = episodes[:args.max_episodes]
    if not episodes:
        raise ValueError("No episodes match the selection. Use list-episodes to inspect the pack.")
    return episodes
