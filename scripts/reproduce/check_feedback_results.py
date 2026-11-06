#!/usr/bin/env python3
"""Audit the paired feedback table with one exact trace-based retry definition."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vigil.eval.feedback_alignment import audit_feedback
from vigil.eval.paper_alignment import file_hash, normalize_family, read_object


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-map", type=Path, required=True)
    parser.add_argument("--feedback-map", type=Path, required=True)
    parser.add_argument("--targets", type=Path, default=ROOT / "data/reproduction/paper_v4_feedback_targets.json")
    parser.add_argument("--pack-file", type=Path, default=ROOT / "data/reproduction/paper_v4_pack.json")
    parser.add_argument("--episode-files", action="store_true", help="Read all canonical per-episode files beside each mapped aggregate; do not parse aggregates.")
    parser.add_argument("--reference", choices=("published", "corrected"), default="published")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        baseline, feedback = read_object(args.baseline_map), read_object(args.feedback_map)
        inputs = [args.baseline_map, args.feedback_map, args.targets, args.pack_file]
        sources = list(map(Path, [*baseline.values(), *feedback.values()]))
        output = args.out.resolve()
        if output in {p.resolve() for p in inputs} or any(output == p.resolve() or output.is_relative_to(p.resolve() if p.is_dir() else p.parent.resolve()) for p in sources):
            raise ValueError("Audit output must be outside reference source directories and must not overwrite inputs.")
        entries = read_object(args.pack_file)["episodes"]
        families = {r["episode_id"]: normalize_family(r["task_family"]) for r in entries}
        if len(families) != len(entries) or not families:
            raise ValueError("Pack needs unique, nonempty episode IDs.")
        targets = read_object(args.targets)
        if targets.get("pack_sha256") and targets["pack_sha256"] != file_hash(args.pack_file):
            raise ValueError("Pack hash differs from the frozen feedback targets.")
        report = audit_feedback(targets, families, baseline, feedback,
                                episode_files=args.episode_files, reference=args.reference)
        report["targets_sha256"] = file_hash(args.targets)
        report["pack_sha256"] = file_hash(args.pack_file)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(f"[feedback-alignment] {report['models_passed']}/{report['models_expected']} match the {args.reference} reference")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
