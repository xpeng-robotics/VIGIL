#!/usr/bin/env python3
"""Copy the canonical public release into a new, history-free directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.release.check_public_release import known_private_values, scan_files
from vigil.data.paths import CANONICAL_PACK
PACK = Path("data/benchmark/packs") / CANONICAL_PACK
PUBLIC_SCRIPTS = (
    "__init__.py", "README.md",
    "release/check_public_release.py", "release/export_public_release.py", "release/export_recorded_example.py",
    "reproduce/check_reference_results.py", "reproduce/check_paper_results.py", "reproduce/compare_aggregates.py",
    "reproduce/check_feedback_results.py", "reproduce/run_metric_alignment.sh", "reproduce/run_historical_reference.sh",
    "reproduce/audit_terminal_reports.py",
    "deploy/run_eval.sh", "deploy/run_vllm_local.sh", "deploy/setup_conda_env.sh", "deploy/quickstart.sh",
    "deploy/constraints-macos-x86_64.txt", "deploy/constraints-linux-x86_64.txt", "deploy/environment.yml",
    "media/build_overview_video.py", "media/build_trailer.py", "media/preview.py",
)
PUBLIC_SKILLS = ("vigil-onboarding", "vigil-evaluation", "vigil-trace-review", "vigil-release")


def recorded_files(root: Path) -> list[Path]:
    """Export only reviewed bytes, even if an evaluation ran in the example tree."""
    base = root / "examples/recorded-runs"
    manifest = json.loads((base / "manifest.json").read_text())
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError("recorded example manifest must be a nonempty file-to-SHA256 map")
    files = [Path("examples/recorded-runs/manifest.json")]
    for name, digest in manifest.items():
        relative = Path(name)
        if relative.is_absolute() or any(part.startswith(".") for part in relative.parts):
            raise ValueError("unsafe recorded example manifest path")
        source = base / relative
        if (not source.resolve().is_relative_to(base.resolve()) or
                any(parent.is_symlink() for parent in (source, *source.parents)) or
                not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest):
            raise ValueError(f"recorded example differs from reviewed manifest: {name}")
        files.append(Path("examples/recorded-runs") / relative)
    return files


def export_release(destination: Path, *, private_configs=()) -> int:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("destination already exists; choose a new directory")
    pack = json.loads((ROOT / PACK).read_text())
    ids = [row["episode_id"] for row in pack["episodes"]]
    if len(ids) != 1000 or len(set(ids)) != 1000:
        raise ValueError("canonical pack must contain 1000 unique episodes")
    files = [Path(name) for name in ("README.md", "CITATION.cff", ".agent/AGENTS.md", "start.sh", "start.command", "pyproject.toml", ".gitignore", "examples/config/.env.example", "examples/config/vigil.json.example", "LICENSE", "NOTICE", "licenses/THIRD_PARTY_NOTICES.md")]
    files += [Path(".github") / name for name in (
        "SUPPORT.md", "CONTRIBUTING.md", "PULL_REQUEST_TEMPLATE.md",
        "ISSUE_TEMPLATE/bug_report.md", "ISSUE_TEMPLATE/feature_request.md",
        "workflows/ci.yml",
    )]
    files += [Path("scripts") / name for name in PUBLIC_SCRIPTS]
    files += [Path(".agent/skills") / name / "SKILL.md" for name in PUBLIC_SKILLS]
    for folder, pattern in (("vigil", "*.py"), ("tests", "*.py"), ("docs", "*.md")):
        files += [p.relative_to(ROOT) for p in (ROOT / folder).rglob(pattern) if "__pycache__" not in p.parts]
    for folder in ("static", "demo"):
        files += [p.relative_to(ROOT) for p in (ROOT / "vigil/web" / folder).rglob("*") if p.is_file() and p.suffix in {".html", ".css", ".js", ".json", ".png"}]
    # Presentation assets are source-distribution files, not runtime dependencies.
    files += [p.relative_to(ROOT) for p in (ROOT / "docs/media").rglob("*")
              if p.is_file() and p.suffix in {".mp4", ".gif", ".jpg", ".webp", ".pdf", ".json", ".vtt", ".html", ".svg"}]
    files += [Path("docs/media/player.css"), Path("docs/media/player.js")]
    files += recorded_files(ROOT)
    files += [PACK, Path("data/README.md"), Path("data/reproduction/paper_v4_targets.json"), Path("data/reproduction/paper_v4_neutral_targets.json")]
    files += [Path("data/provenance/scenes.json"), Path("data/provenance/task_corrections.json")]
    files += [Path("data/provenance/revision_comparison.json")]
    files += [Path("data/reproduction/paper_v4_pack.json")]
    files += [Path("data/reproduction/paper_v4_feedback_targets.json")]
    files += [Path("data/reproduction") / name for name in (
        "paper_sv_exclusions.json", "paper_prompt.txt", "paper_prompt_provenance.json",
        "paper_neutral_prompt.txt", "paper_neutral_prompt_provenance.json",
    )]
    files += [Path("data/reproduction/terminal-audit") / name for name in (
        "archive_metrics.json", "sv_summary_audit.csv", "sv_unmapped_examples.csv",
        "report_confusions.csv", "sv_exclusion_sensitivity.csv",
        "history_memory_provenance.json", "memory_feedback_audit.json",
    )]
    files += [Path("data/episodes") / episode_id / "episode.json" for episode_id in ids]
    files += [p.relative_to(ROOT) for p in (ROOT / "data/scenes").rglob("house.json")]
    files += [Path(name) for name in ("LICENSE", "LICENSE.md", "NOTICE") if (ROOT / name).is_file()]
    files += [p.relative_to(ROOT) for p in (ROOT / "licenses").rglob("*.txt")]
    files = sorted(set(files))
    for relative in files:
        source = ROOT / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"missing file or unexpected symlink: {relative}")
    findings = scan_files(ROOT, files, known_values=known_private_values(private_configs))
    if findings:
        locations = "; ".join(f"{row['path']}:{row['line']} ({row['category']})" for row in findings[:20])
        raise ValueError(f"public content scan failed; inspect locally: {locations}")
    destination.mkdir(parents=True)
    manifest = {}
    for relative in files:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
        manifest[relative.as_posix()] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / "docs/development/release_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"Exported {len(files)} files and 1000 episodes to {destination}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--private-config", action="append", type=Path, default=[])
    args = parser.parse_args()
    try:
        return export_release(args.destination, private_configs=args.private_config)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"export failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
