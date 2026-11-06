#!/usr/bin/env python3
"""Compare current scoring of archived traces against the published paper tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from vigil.eval.paper_alignment import PaperAlignmentError, audit_paper, read_object


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-map",
        type=Path,
        required=True,
        help="Private JSON mapping paper model IDs to reference aggregate files.",
    )
    parser.add_argument(
        "--targets", type=Path, default=ROOT / "data/reproduction/paper_v4_targets.json"
    )
    parser.add_argument(
        "--pack-file",
        type=Path,
        default=ROOT
        / "data/reproduction/paper_v4_pack.json",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        sources = read_object(args.source_map)
        inputs = [
            args.source_map,
            args.targets,
            args.pack_file,
            *map(Path, sources.values()),
        ]
        if args.out.resolve() in {path.resolve() for path in inputs}:
            raise PaperAlignmentError("Audit output must not overwrite an input.")
        report = audit_paper(args.targets, args.pack_file, sources)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[paper-alignment] {report['models_passed']}/{report['models_expected']} models match paper and per-step W/B evidence"
    )
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
