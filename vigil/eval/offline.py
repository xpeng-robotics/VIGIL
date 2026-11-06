from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vigil.eval.scoring import AggregateScore
from vigil.eval.scoring import aggregate_scores, score_episode, score_result_payload
from vigil.eval.traces import EpisodeTrace, load_trace, validate_completed_trace
from vigil.eval.inspection import selected_episode_ids


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _looks_like_release_trace_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(payload.get("episode_id")) and isinstance(payload.get("steps"), list)


def _looks_like_reference_result_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and bool(payload.get("episode_id"))
        and isinstance(payload.get("trace"), list)
        and isinstance(payload.get("settlement"), dict)
    )


def _looks_like_reference_aggregate_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and isinstance(payload.get("results"), list)


def _looks_like_trace(path: Path, *, required: bool = False) -> bool:
    try:
        payload: Any = _read_json(path)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Cannot read trace input {path}: {exc}") from exc
    if isinstance(payload, dict) and payload.get("episode_id") and (
        path.name.endswith(".error.json") or payload.get("error_type")
    ):
        raise ValueError(f"Unresolved infrastructure error record: {path}")
    if _looks_like_release_trace_payload(payload) or _looks_like_reference_result_payload(payload):
        return True
    resembles_trace = isinstance(payload, dict) and (
        bool({"steps", "trace"}.intersection(payload)) or ("profile" in payload and "episode_id" in payload)
    )
    if required or resembles_trace:
        raise ValueError(f"Invalid trace JSON: {path}")
    return False


def _directory_trace_files(path: Path) -> list[Path]:
    # Recorded selections take precedence over stale files from earlier subsets.
    root = path.parent if path.name == "traces" else path
    status_path = root / "run_status.json"
    if status_path.exists() or status_path.is_symlink():
        if not status_path.is_file():
            raise ValueError(f"Run status must be a JSON file: {status_path}")
        status = _read_json(status_path)
        if not isinstance(status, dict):
            raise ValueError(f"Expected a JSON object: {status_path}")
        if status.get("state") != "complete" or status.get("infrastructure_errors"):
            raise ValueError(f"Run is incomplete or contains infrastructure errors: {root}")
        files = []
        for episode_id in selected_episode_ids(status):
            trace = root / "traces" / f"{episode_id}.json"
            if not trace.is_file():
                raise ValueError(f"Missing selected trace: {trace}")
            _looks_like_trace(trace, required=True)
            if _read_json(trace)["episode_id"] != episode_id:
                raise ValueError(f"Trace episode ID differs from run_status.json: {trace}")
            files.append(trace)
        return files
    files = []

    def unreadable(error: OSError) -> None:
        raise error

    for directory, folders, names in os.walk(path, onerror=unreadable):
        folders.sort()
        directory = Path(directory)
        if directory != path and ("run_status.json" in names or "run_status.json" in folders):
            # Nested runs must keep the same selection and completion rules as
            # direct inputs, rather than rediscovering stale or partial traces.
            files.extend(_directory_trace_files(directory))
            folders.clear()
            continue
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            candidate = directory / name
            required = path.name == "traces" or "traces" in candidate.relative_to(path).parts[:-1]
            if _looks_like_trace(candidate, required=required):
                files.append(candidate)
    return files


def collect_trace_files(paths: list[str | Path]) -> list[Path]:
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            files.extend(_directory_trace_files(path))
        elif path.exists():
            if not _looks_like_trace(path):
                raise ValueError(f"Trace path is not a supported release trace or reference result JSON: {path}")
            files.append(path)
        else:
            raise FileNotFoundError(f"Trace path does not exist: {path}")
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in files:
        resolved = path.resolve()
        if resolved not in seen:
            deduped.append(resolved)
            seen.add(resolved)
    if not deduped:
        raise ValueError("No trace JSON files found.")
    return deduped


def _iter_trace_payloads(paths: list[str | Path]):
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            for trace_path in collect_trace_files([path]):
                yield trace_path, _read_json(trace_path)
            continue
        if not path.exists():
            raise FileNotFoundError(f"Trace path does not exist: {path}")

        payload = _read_json(path)
        if _looks_like_release_trace_payload(payload) or _looks_like_reference_result_payload(payload):
            yield path, payload
            continue
        if _looks_like_reference_aggregate_payload(payload):
            results = payload.get("results") or []
            if not results:
                raise ValueError(f"Reference aggregate JSON has no results: {path}")
            if payload.get("error_count") or payload.get("errors") or payload.get("infrastructure_errors"):
                raise ValueError(f"Reference aggregate contains infrastructure errors: {path}")
            if payload.get("skipped_missing"):
                raise ValueError(f"Reference aggregate has missing selected episodes: {path}")
            for key in ("episode_count", "overall_episode_count"):
                if key in payload and (type(payload[key]) is not int or payload[key] != len(results)):
                    raise ValueError(f"Reference aggregate {key} differs from result count: {path}")
            for index, result in enumerate(results):
                if not _looks_like_reference_result_payload(result):
                    raise ValueError(f"Unsupported result payload in aggregate {path} at results[{index}]")
                yield path, result
            continue
        raise ValueError(f"Trace path is not a supported release trace, reference result, or reference aggregate JSON: {path}")


def load_traces(paths: list[str | Path]) -> list[EpisodeTrace]:
    traces: list[EpisodeTrace] = []
    unsupported: list[Path] = []
    for path in collect_trace_files(paths):
        payload = _read_json(path)
        if _looks_like_release_trace_payload(payload):
            traces.append(load_trace(path))
        else:
            unsupported.append(path)
    if unsupported:
        sample = ", ".join(str(path) for path in unsupported[:3])
        raise ValueError(
            "load_traces only returns release EpisodeTrace files; "
            f"reference result JSONs require evaluate_trace_files. Unsupported: {sample}"
        )
    return traces


def evaluate_trace_files(paths: list[str | Path]) -> AggregateScore:
    scores = []
    seen_ids: set[str] = set()
    configs: dict[Path, dict] = {}
    for path, payload in _iter_trace_payloads(paths):
        root = path.parent.parent if path.parent.name == "traces" else path.parent
        config_path = root / "run_config.json"
        if (config_path.exists() or config_path.is_symlink()) and config_path not in configs:
            config = _read_json(config_path)
            if not isinstance(config, dict) or not config:
                raise ValueError(f"Invalid run_config.json: {config_path}")
            if configs and config != next(iter(configs.values())):
                raise ValueError("Cannot combine different run_config.json experiments. "
                                 "Score each model/configuration separately.")
            configs[config_path] = config
        _validate_completed_payload(payload, path)
        episode_id = payload["episode_id"]
        if episode_id in seen_ids:
            raise ValueError(f"Duplicate episode_id {episode_id!r} in trace inputs: {path}")
        seen_ids.add(episode_id)
        if _looks_like_release_trace_payload(payload):
            trace = EpisodeTrace.from_dict(payload)
            try:
                validate_completed_trace(trace)
            except ValueError as exc:
                raise ValueError(f"Cannot score {path}: {exc}") from exc
            scores.append(score_episode(trace))
        elif _looks_like_reference_result_payload(payload):
            scores.append(score_result_payload(payload))
        else:
            raise ValueError(f"Unsupported trace/result JSON: {path}")
    return aggregate_scores(scores)


def _validate_completed_payload(payload: dict, path: Path) -> None:
    """Do not turn a saved partial rollout or infrastructure failure into a score."""
    release = "steps" in payload
    steps = payload.get("steps" if release else "trace")
    terminal = payload.get("terminal_status") or (payload.get("settlement") or {}).get("terminal_status")
    if not steps or terminal in {None, "", "unknown", "ongoing", "running"}:
        raise ValueError(f"Cannot score an empty or unfinished trace: {path}")
    failures = {"simulator_error", "model_request_error", "model_api_error", "model_timeout"}
    if terminal in failures or payload.get("error_type"):
        raise ValueError(f"Trace contains an infrastructure error: {path}")
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError(f"Trace steps must be JSON objects: {path}")
        judge = step.get("judge_result") or (step.get("metadata") or {}).get("judge_result") or {}
        labels = [step.get(k) for k in ("env_status", "error_type", "failure_label", "failure_type")]
        labels.extend(judge.get(k) for k in ("status", "failure_label", "failure_type", "terminal_reason"))
        if any(str(label or "").split(":", 1)[0] in failures for label in labels):
            raise ValueError(f"Trace contains an infrastructure error: {path}")


def write_json(path: str | Path, payload: object) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(payload, "to_dict"):
        data = payload.to_dict()  # type: ignore[assignment]
    else:
        data = payload
    content = json.dumps(data, indent=2, sort_keys=True) + "\n"
    try:
        with out.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        raise ValueError("Refusing to replace an existing score output; choose a new --out path. "
                         "Original traces and scores must be preserved.") from None
    return out
