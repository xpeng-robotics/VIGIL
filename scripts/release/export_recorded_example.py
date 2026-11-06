#!/usr/bin/env python3
"""Export one historical VIGIL result as a verified, portable replay.

Usage: python scripts/release/export_recorded_example.py RESULT --frames SCREENSHOTS
       --model MODEL --out NEW_DIRECTORY
No model or simulator is started. Original archives are never modified.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vigil.agent.parser import parse_agent_response
from vigil.eval.scoring import aggregate_scores, score_episode
from vigil.eval.settlement import settle_trace
from vigil.eval.traces import EpisodeTrace
from vigil.eval.inspection import verify_run
from vigil.security import secret_field
from scripts.release.check_public_release import scan_bytes, text_findings


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_public(value):
    """Fail on suspected private content; do not silently rewrite evidence."""
    blocked_keys = {"api_key", "authorization", "access_token", "refresh_token",
                    "password", "secret", "cookie", "base_url", "endpoint",
                    "thoughtsignature", "responseid", "raw_response"}
    def visit(item):
        if isinstance(item, dict):
            for key, child in item.items():
                normalized = re.sub(r"[^a-z0-9]", "", key.lower())
                if (secret_field(key) or normalized in
                        {re.sub(r"[^a-z0-9]", "", name) for name in blocked_keys | {"base_urls"}}):
                    raise ValueError("Private transport field in selected evidence; inspect locally.")
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)
        elif isinstance(item, str):
            if text_findings(item) or re.search(r"https?://|/private/|Bearer\s+\S+", item, re.I):
                raise ValueError("Possible private address or credential in evidence; inspect locally.")
    visit(value)


def export_example(source: Path, frames: Path, model: str, destination: Path):
    if destination.exists():
        raise ValueError("Output already exists; choose a new directory.")
    raw = json.loads(source.read_text())
    episode_id = raw["episode_id"]
    if Path(episode_id).name != episode_id or episode_id in {".", ".."}:
        raise ValueError("Invalid episode ID.")
    rows = raw["trace"]
    if not rows or [r["step"] for r in rows] != list(range(1, len(rows)+1)):
        raise ValueError("Expected complete, consecutive, one-based archived steps.")
    files = []
    for i in range(len(rows)+1):
        matches = sorted(frames.glob(f"step_{i:03d}_*.png"))
        if len(matches) != 1 or matches[0].is_symlink():
            raise ValueError(f"Missing or ambiguous observation {i}.")
        header = matches[0].read_bytes()[:24]
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Expected PNG observation.")
        files.append(matches[0])
    steps = []
    for i, row in enumerate(rows):
        output = {k: row["model_output"][k] for k in ("raw_text", "parsed_invocation")}
        turn = parse_agent_response(output["raw_text"], allow_json_repair=False)
        runtime = row["runtime_action"]
        action = runtime["validated_invocation"]
        if turn.action is None or turn.action.to_dict() != action:
            raise ValueError(f"Raw model action disagrees with recorded action at step {i+1}.")
        parsed = output["parsed_invocation"]
        if {k: parsed[k] for k in ("skill_name", "arguments")} != action:
            raise ValueError("Recorded parsed invocation disagrees with validated action.")
        executed = runtime["executed_invocation"]
        adapter = runtime.get("adapter")
        if adapter:
            if adapter.get("adapter") != "normalized_1000_to_pixel":
                raise ValueError("Unrecognized coordinate adapter; review before exporting.")
            for key in ("x", "y"):
                if adapter["input"][key] != action["arguments"][key] or adapter["output"][key] != executed["arguments"][key]:
                    raise ValueError("Coordinate adapter disagrees with recorded action.")
            width, height = struct.unpack(">II", files[i].read_bytes()[16:24])
            if adapter["image_size"] != {"width": width, "height": height}:
                raise ValueError("Coordinate adapter image size does not match observation.")
        elif executed != action:
            raise ValueError("Executed action changed without a recorded adapter.")
        env, judge = row["env_result"], row["judge_result"]
        if row["ok"] != env["simulator_success"]:
            raise ValueError("Execution success flag disagrees with environment evidence.")
        if judge["status"] != "ongoing" and i != len(rows)-1:
            raise ValueError("Archive contains steps after termination.")
        env = dict(env, executed_arguments=executed["arguments"], diagnostics=judge.get("oracle_facts", {}))
        steps.append({"step_index": i, "action": action,
                      "action_valid": not (judge["invalid_action"] or judge["protocol_failure"]),
                      "env_status": "ok" if row["ok"] else "action_failed",
                      "judge_success": judge["world_success"], "progress": judge["progress"],
                      "terminal": judge["status"] != "ongoing", "error_type": judge.get("failure_label"),
                      "metadata": {"model_output": output, "runtime_action": runtime,
                                   "env_result": env, "judge_result": judge}})
    meta = {k: raw[k] for k in ("task_family", "difficulty", "profile", "contract_version", "settlement") if k in raw}
    trace = EpisodeTrace.from_dict({"episode_id": episode_id, "profile": raw["profile"]["name"],
                                   "max_steps": raw["settlement"]["step_budget"], "steps": steps,
                                   "terminal_status": raw["terminal_status"], "metadata": meta})
    check_public({"trace": trace.to_dict(), "model": model})
    uncached = replace(trace, metadata={k: v for k, v in meta.items() if k != "settlement"})
    if settle_trace(uncached).to_dict() != raw["settlement"]:
        raise ValueError("Archived settlement disagrees with independent recomputation.")
    score = score_episode(trace)
    if score.success != raw["score_summary"]["success"]:
        raise ValueError("Recomputed benchmark success differs from archived result.")
    summary = score.to_dict()["score_summary"]
    for key in ("success", "semantic_success", "strict_success", "progress", "semantic_progress",
                "strict_progress", "efficiency", "safety", "compliance", "primary_score", "strict_score"):
        if key in raw["score_summary"] and raw["score_summary"][key] != summary[key]:
            raise ValueError(f"Archived score field differs after recomputation: {key}")
    check_public(raw["score_summary"])
    check_public({"source_filename": source.name, "started_at": raw.get("started_at"),
                  "frame_filenames": [path.name for path in files]})
    for path in files:
        if scan_bytes(path.name, path.read_bytes()):
            raise ValueError("Possible private frame metadata; inspect locally before exporting.")
    # Preserve source evidence and its provenance separately from derived scores.
    destination.mkdir(parents=True)
    def write(name, value):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, indent=2, sort_keys=True)+"\n")
    write(f"traces/{episode_id}.json", trace.to_dict())
    write(f"scores/{episode_id}.score.json", score.to_dict())
    write("aggregate_score.json", aggregate_scores([score]).to_dict())
    write("run_status.json", {"episode_ids": [episode_id], "state": "complete", "infrastructure_errors": []})
    write("model_config.json", {"model": model, "recorded_only": True})
    frame_manifest = []
    for i, path in enumerate(files):
        name = f"frames/{episode_id}/" + (f"step_{i:03d}.png" if i < len(rows) else "terminal.png")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        frame_manifest.append({"file": name, "source_file": path.name, "sha256": digest(target),
                               "observation_index": i})
    write("provenance.json", {"source_result_sha256": digest(source), "source_filename": source.name,
          "model": model, "started_at": raw.get("started_at"), "profile": raw["profile"],
          "archived_score_summary": raw["score_summary"],
          "selection": "Editorial case selection, not a representative evaluation or ranking.",
          "conversion": "Lossless frame copies. Zero-based steps. Step images precede actions; terminal.png follows the last action. Scores rebuilt by the public scorer; original settlement preserved and independently checked.",
          "omitted": "Transport responses, service configuration, worker identifiers, and duplicated top-level reasoning fields. Raw action text and structured execution evidence retained.",
          "frames": frame_manifest})
    write("verification.json", verify_run(destination, require_frames=True))
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result", type=Path)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    export_example(args.result, args.frames, args.model, args.out)
    print(f"Exported and verified one recorded episode to {args.out}")


if __name__ == "__main__":
    main()
