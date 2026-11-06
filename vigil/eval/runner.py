from __future__ import annotations

from collections.abc import Callable

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from vigil.actions import ActionCall, validate_action
from vigil.agent.types import AgentObservation, AgentProtocol, AgentTurnResult
from vigil.data.episodes import EpisodeSpec
from vigil.agent.model import OpenAIModelAgent
from vigil.agent.profiles import AgentProfile, DEFAULT_PROFILE_NAME, get_profile
from vigil.eval.judge import JudgeState, finalize_settlement_with_budget, judge_step
from vigil.eval.scoring import EpisodeScore, score_episode
from vigil.eval.settlement import settle_trace
from vigil.eval.traces import EpisodeTrace, StepTrace
from vigil.eval.types import EnvActionResult, StepJudgeResult
from vigil.envs.thor import PublicThorEnv
from vigil.utils.image_validation import black_frame_stats, is_black_frame

JSONDict = dict[str, Any]
CONTRACT_VERSION = "vigil_native_v1"
DEFAULT_BENCHMARK_MODE = "pure_model"
PUBLIC_TRACE_METADATA_KEYS = (
    "benchmark_mode",
    "contract_version",
    "pack_id",
    "platform",
    "episode_family_id",
    "family_anchor_key",
    "difficulty",
    "aux_difficulty",
    "functional_template",
    "target_object_type",
    "target_group",
    "primary_capabilities",
)


class BlackFrameError(RuntimeError):
    """Raised when AI2-THOR returns a near-black frame for a model observation."""


@dataclass(frozen=True)
class SimRunResult:
    trace_path: Path
    score_path: Path
    trace: EpisodeTrace
    score: EpisodeScore


def build_turn_trace_metadata(turn: AgentTurnResult) -> JSONDict:
    metadata: JSONDict = {"raw_response": turn.raw_response}
    if turn.parse_error:
        metadata["parse_error"] = turn.parse_error
    if turn.metadata:
        metadata["agent_turn"] = dict(turn.metadata)
    return metadata


def compact_error_text(error: str | None, *, max_chars: int = 180) -> str | None:
    if not error:
        return None
    text = str(error).replace("\n", " ").strip()
    for marker in (" trace:", " Traceback", " at "):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    if len(text) > max_chars:
        text = text[: max_chars - 3].rstrip() + "..."
    return text or None


def format_dialogue_history(steps: list[StepTrace], *, max_turns: int = 20) -> str:
    if not steps:
        return ""
    limit = max(int(max_turns), 0)
    selected = steps[-limit:] if limit else []
    lines = []
    for step in selected:
        action = step.action.to_dict() if step.action is not None else None
        payload: JSONDict = {
            "step": step.step_index,
            "action": action,
        }
        lines.append(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines)


def _profile_history_turns(profile: str | AgentProfile) -> int:
    resolved_profile = profile
    if isinstance(profile, str):
        try:
            resolved_profile = get_profile(profile)
        except Exception:
            return 20
    value = resolved_profile.metadata.get("conversation_history_turns", 20)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 20


def _trace_profile_name(profile: str | AgentProfile) -> str:
    if isinstance(profile, AgentProfile):
        return profile.name
    return str(profile)


def _trace_profile_metadata(profile: str | AgentProfile) -> JSONDict:
    if not isinstance(profile, AgentProfile):
        return {}
    return profile.to_dict()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _validate_model_frame(env: Any, *, episode_id: str, step_index: int, image_path: str | None) -> None:
    if not _env_bool("VIGIL_FAIL_ON_BLACK_FRAME", True):
        return
    event = getattr(env, "last_event", None)
    frame = getattr(event, "frame", None) if event is not None else None
    if not is_black_frame(frame):
        return
    stats = black_frame_stats(frame) or {}
    mean_pixel = float(stats.get("mean_pixel") or 0.0)
    black_ratio = float(stats.get("black_pixel_ratio") or 0.0)
    shape = str(stats.get("shape") or "unknown")
    raise BlackFrameError(
        "black rendered frame before model call: "
        f"episode_id={episode_id} step={step_index} mean_pixel={mean_pixel:.2f} "
        f"black_pixel_ratio={black_ratio:.4f} shape={shape} frame_path={image_path or '<none>'}"
    )


def _copy_public_trace_fields(target: JSONDict, source: JSONDict) -> None:
    for key in PUBLIC_TRACE_METADATA_KEYS:
        if key not in source:
            continue
        value = source.get(key)
        if value is None:
            continue
        if key == "aux_difficulty":
            target.setdefault("difficulty", value)
            continue
        target.setdefault(key, value)


def _build_trace_metadata(
    *,
    episode: EpisodeSpec,
    settlement: Any,
    profile: str | AgentProfile,
    pack_id: str | None,
    pack_platform: str | None,
) -> JSONDict:
    trace_metadata: JSONDict = {
        "scene_id": episode.scene_id,
        "task_family": episode.task_family,
        "benchmark_mode": os.getenv("VIGIL_BENCHMARK_MODE", "").strip() or DEFAULT_BENCHMARK_MODE,
        "contract_version": os.getenv("VIGIL_CONTRACT_VERSION", "").strip() or CONTRACT_VERSION,
        "settlement": settlement.to_dict(),
    }
    if pack_id:
        trace_metadata["pack_id"] = str(pack_id)
    if pack_platform:
        trace_metadata["platform"] = str(pack_platform)
    _copy_public_trace_fields(trace_metadata, dict(episode.metadata or {}))
    _copy_public_trace_fields(trace_metadata, dict(episode.trace_hints or {}))
    if "platform" not in trace_metadata:
        trace_metadata["platform"] = str((episode.scene or {}).get("platform") or "unknown")
    trace_metadata["scene_platform"] = str((episode.scene or {}).get("platform") or "unknown")
    if trace_metadata.get("primary_capabilities") is not None:
        trace_metadata["primary_capabilities"] = [
            str(item) for item in list(trace_metadata.get("primary_capabilities") or []) if str(item).strip()
        ]
    profile_metadata = _trace_profile_metadata(profile)
    if profile_metadata:
        trace_metadata["profile"] = profile_metadata
    return trace_metadata


def _build_observation_metadata(
    *,
    episode: EpisodeSpec,
    steps: list[StepTrace],
    history_turns: int,
    width: int,
    height: int,
) -> JSONDict:
    metadata: JSONDict = {
        "scene_id": episode.scene_id,
        "task_family": episode.task_family,
        "history_turns": history_turns,
        "image_size": {"width": int(width), "height": int(height)},
    }
    if steps and steps[-1].action is not None:
        metadata["previous_action"] = json.dumps(
            steps[-1].action.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    return metadata


def _env_world_state(env: Any) -> JSONDict:
    getter = getattr(env, "get_world_state", None)
    if callable(getter):
        try:
            return dict(getter())
        except Exception:
            return {}
    return {}


def _env_result_payload(env_result: EnvActionResult, diagnostics: JSONDict | None = None) -> JSONDict:
    payload: JSONDict = {
        "skill_name": env_result.skill_name,
        "requested_arguments": dict(env_result.requested_arguments),
        "executed_arguments": dict(env_result.executed_arguments),
        "simulator_success": env_result.simulator_success,
        "error_message": env_result.error_message,
        "resolved_target": dict(env_result.resolved_target) if env_result.resolved_target else None,
        "target_resolved": env_result.target_resolved,
        "action_adapter": dict(env_result.action_adapter) if env_result.action_adapter else None,
    }
    if diagnostics:
        payload["diagnostics"] = dict(diagnostics)
    return payload


def _judge_result_payload(judge_result: StepJudgeResult) -> JSONDict:
    return {
        "status": judge_result.status,
        "progress": judge_result.progress,
        "recoverable": judge_result.recoverable,
        "invalid_action": judge_result.invalid_action,
        "protocol_failure": judge_result.protocol_failure,
        "failure_label": judge_result.failure_label,
        "terminal_reason": judge_result.terminal_reason,
        "world_success": judge_result.world_success,
        "semantic_world_success": judge_result.semantic_world_success,
        "strict_world_success": judge_result.strict_world_success,
        "semantic_progress": judge_result.semantic_progress,
        "strict_progress": judge_result.strict_progress,
        "report_submitted": judge_result.report_submitted,
        "report_status": judge_result.report_status,
        "report_matches_world": judge_result.report_matches_world,
        "violations": list(judge_result.violations),
        "oracle_facts": dict(judge_result.oracle_facts),
    }


def run_episode(
    *,
    episode_path: str | Path,
    agent: AgentProtocol,
    out_dir: str | Path,
    width: int = 640,
    height: int = 480,
    render_depth: bool = False,
    max_steps: int | None = None,
    save_frames: bool = True,
    scene_root: str | Path = "data/scenes",
    profile: str | AgentProfile = DEFAULT_PROFILE_NAME,
    controller_boot_gate: Any | None = None,
    render_gate: Any | None = None,
    startup_ready_callback: Callable[[], None] | None = None,
    pack_id: str | None = None,
    pack_platform: str | None = None,
) -> SimRunResult:
    episode = EpisodeSpec.from_path(episode_path)
    step_budget = int(max_steps or episode.max_steps)
    history_turns = _profile_history_turns(profile)
    out_root = Path(out_dir)
    trace_dir = out_root / "traces"
    score_dir = out_root / "scores"
    frame_dir = out_root / "frames" / episode.episode_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    score_dir.mkdir(parents=True, exist_ok=True)
    if save_frames:
        frame_dir.mkdir(parents=True, exist_ok=True)

    env = PublicThorEnv(
        episode,
        width=width,
        height=height,
        render_depth=render_depth,
        scene_root=scene_root,
        coord_mode=getattr(agent, "coord_mode", None),
    )
    steps: list[StepTrace] = []
    judge_state = JudgeState()
    terminal_status = "timeout"
    render_gate_acquired = False
    temporary_frames = None
    try:
        if not save_frames:
            temporary_frames = tempfile.TemporaryDirectory(prefix="vigil-frames-")
            frame_dir = Path(temporary_frames.name)
        if render_gate is not None:
            render_gate.acquire()
            render_gate_acquired = True
        if controller_boot_gate is not None:
            with controller_boot_gate:
                env.reset()
        else:
            env.reset()
        if startup_ready_callback is not None:
            startup_ready_callback()
        for step_index in range(step_budget):
            # Frame retention must never change the model's observation modality.
            frame_path = frame_dir / (f"step_{step_index:03d}.png" if save_frames else "current.png")
            saved = env.save_frame(frame_path)
            image_path = str(saved) if saved is not None else None
            if isinstance(agent, OpenAIModelAgent) and (not image_path or not Path(image_path).is_file()):
                raise BlackFrameError(f"Missing rendered RGB frame for {episode.episode_id} at step {step_index}.")
            _validate_model_frame(
                env,
                episode_id=episode.episode_id,
                step_index=step_index,
                image_path=image_path,
            )
            observation = AgentObservation(
                episode_id=episode.episode_id,
                step_index=step_index,
                instruction=episode.instruction,
                text=format_dialogue_history(steps, max_turns=history_turns),
                image_path=image_path,
                metadata=_build_observation_metadata(
                    episode=episode,
                    steps=steps,
                    history_turns=history_turns,
                    width=width,
                    height=height,
                ),
            )
            turn = agent.act(observation)
            turn_metadata = build_turn_trace_metadata(turn)
            agent_turn_metadata = dict(turn.metadata or {})
            skill_surface = str(agent_turn_metadata.get("skill_surface") or "action").strip().lower() or "action"
            unsupported_surface = turn.action is not None and skill_surface != "action"
            schema_error = None
            if turn.action is not None and not unsupported_surface:
                try:
                    validate_action(turn.action, strict_skill_set=True)
                except (TypeError, ValueError, OverflowError) as exc:
                    schema_error = str(exc)
            if turn.action is None or unsupported_surface or schema_error:
                raw_error = (
                    f"Runtime engine only executes action skills, got: {skill_surface}"
                    if unsupported_surface
                    else (schema_error or turn.parse_error or "parse_error")
                )
                error_message = compact_error_text(raw_error, max_chars=500) or "parse_error"
                world_state = _env_world_state(env)
                env_result = EnvActionResult(
                    skill_name="model_protocol_error",
                    requested_arguments=turn.action.to_dict() if turn.action is not None else {},
                    executed_arguments={},
                    simulator_success=False,
                    error_message=error_message,
                    pre_state=world_state,
                    post_state=world_state,
                )
                judge_state.steps_used += 1
                judge_result = judge_step(
                    spec=episode,
                    state=judge_state,
                    env_result=env_result,
                    protocol_failure=True,
                )
                step_metadata = dict(turn_metadata)
                step_metadata["env_result"] = _env_result_payload(env_result)
                step_metadata["judge_result"] = _judge_result_payload(judge_result)
                terminal = judge_result.status != "ongoing"
                steps.append(
                    StepTrace(
                        step_index=step_index,
                        action=turn.action,
                        action_valid=False,
                        env_status="protocol_error",
                        error_type=error_message,
                        progress=judge_result.progress,
                        judge_success=judge_result.world_success,
                        terminal=terminal,
                        metadata=step_metadata,
                    )
                )
                if terminal:
                    terminal_status = judge_result.status
                    break
                continue
            result = env.step(turn.action)
            step_metadata = dict(turn_metadata)
            diagnostics = getattr(result, "diagnostics", None)
            env_result = getattr(result, "env_result", None)
            if isinstance(env_result, EnvActionResult):
                judge_state.steps_used += 1
                judge_result = judge_step(
                    spec=episode,
                    state=judge_state,
                    env_result=env_result,
                    protocol_failure=result.env_status == "protocol_error",
                )
                step_metadata["env_result"] = _env_result_payload(env_result, diagnostics if isinstance(diagnostics, dict) else None)
                step_metadata["judge_result"] = _judge_result_payload(judge_result)
                if judge_result.report_status is not None:
                    step_metadata["agent_report_status"] = judge_result.report_status
                if judge_result.report_matches_world is not None:
                    step_metadata["report_matches_world"] = judge_result.report_matches_world
                oracle_facts = dict(judge_result.oracle_facts or {})
                if oracle_facts.get("expected_report_status") is not None:
                    step_metadata["expected_report_status"] = oracle_facts.get("expected_report_status")
                terminal = judge_result.status != "ongoing"
                action_valid = not (judge_result.invalid_action or judge_result.protocol_failure)
                steps.append(
                    StepTrace(
                        step_index=step_index,
                        action=turn.action,
                        action_valid=action_valid,
                        env_status=result.env_status,
                        judge_success=judge_result.world_success,
                        progress=judge_result.progress,
                        terminal=terminal,
                        error_type=compact_error_text(judge_result.failure_label or result.error_message, max_chars=500),
                        metadata=step_metadata,
                    )
                )
                if terminal:
                    terminal_status = judge_result.status
                    break
                continue
            if diagnostics:
                step_metadata["env_result"] = {"diagnostics": dict(diagnostics)}
            steps.append(
                StepTrace(
                    step_index=step_index,
                    action=turn.action,
                    action_valid=result.action_success,
                    env_status=result.env_status,
                    judge_success=result.judge_success,
                    progress=result.progress,
                    terminal=result.terminal,
                    error_type=compact_error_text(result.error_message, max_chars=500),
                    metadata=step_metadata,
                )
            )
            if result.terminal:
                terminal_status = "success" if result.judge_success else "stopped"
                break
    except BlackFrameError:
        raise
    except Exception as exc:  # noqa: BLE001 - simulator failures are recorded per episode.
        error_message = compact_error_text(f"{type(exc).__name__}: {exc}", max_chars=500) or type(exc).__name__
        world_state = _env_world_state(env)
        env_result = EnvActionResult(
            skill_name="simulator_error",
            requested_arguments={},
            executed_arguments={},
            simulator_success=False,
            error_message=error_message,
            pre_state=world_state,
            post_state=world_state,
        )
        judge_state.steps_used += 1
        judge_state.terminal_status = "failure"
        judge_state.terminal_reason = "simulator_error"
        steps.append(
            StepTrace(
                step_index=len(steps),
                action=None,
                action_valid=False,
                env_status="simulator_error",
                error_type=error_message,
                progress=judge_state.latest_progress,
                judge_success=False,
                terminal=True,
                metadata={
                    "exception_type": type(exc).__name__,
                    "env_result": _env_result_payload(env_result),
                    "judge_result": _judge_result_payload(StepJudgeResult(
                        status="failure", terminal_reason="simulator_error",
                        progress=judge_state.latest_progress, recoverable=False,
                        invalid_action=False, protocol_failure=False,
                        world_success=judge_state.world_success,
                        semantic_world_success=judge_state.semantic_world_success,
                        strict_world_success=judge_state.strict_world_success,
                        semantic_progress=judge_state.semantic_latest_progress,
                        strict_progress=judge_state.strict_latest_progress,
                    )),
                },
            )
        )
        terminal_status = "failure"
    finally:
        try:
            env.close()
        finally:
            if render_gate_acquired and render_gate is not None:
                render_gate.release()
            if temporary_frames is not None:
                temporary_frames.cleanup()

    settlement = finalize_settlement_with_budget(episode, judge_state, step_budget_override=step_budget)
    if steps and judge_state.steps_used == 0:
        settlement = settle_trace(EpisodeTrace(
            episode_id=episode.episode_id, profile=_trace_profile_name(profile),
            max_steps=step_budget, steps=tuple(steps), terminal_status=terminal_status,
        ))
    trace_metadata = _build_trace_metadata(
        episode=episode,
        settlement=settlement,
        profile=profile,
        pack_id=pack_id,
        pack_platform=pack_platform,
    )
    trace_metadata["action_validation_policy"] = "public_registry_v1"
    if os.environ.get("VIGIL_GPU_DEVICE", "").strip():
        trace_metadata["renderer_device"] = os.environ["VIGIL_GPU_DEVICE"].strip()
    initialization = getattr(env, "initialization_checks", None)
    if initialization:
        trace_metadata["initialization_checks"] = list(initialization)
    trace = EpisodeTrace(
        episode_id=episode.episode_id,
        profile=_trace_profile_name(profile),
        max_steps=step_budget,
        steps=tuple(steps),
        terminal_status=terminal_status,
        metadata=trace_metadata,
    )
    score = score_episode(trace)
    trace_path = trace_dir / f"{episode.episode_id}.json"
    score_path = score_dir / f"{episode.episode_id}.score.json"
    trace_path.write_text(json.dumps(trace.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    score_path.write_text(json.dumps(score.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return SimRunResult(trace_path=trace_path, score_path=score_path, trace=trace, score=score)
