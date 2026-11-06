from __future__ import annotations

import json
import hashlib
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from vigil.data.paths import CANONICAL_PACK as PACK_NAME

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PACK = ROOT / "data" / "benchmark" / "packs" / PACK_NAME
PROVENANCE_TOP_LEVEL_KEYS = {
    "source_review_states",
    "source_benchmark_pack",
    "source_reviewer_dir",
    "selection_policy",
    "selection_diagnostics",
}
PROVENANCE_SUMMARY_KEYS = {"source_counts", "family_source_counts", "selection_notes"}
PROVENANCE_TEXT_TERMS = ("source_tag", "review_accept", "reviewer_episodes", "review_pending", "selection_")
SCAN_TARGETS = [
    ROOT / "vigil",
    ROOT / ".agent/skills",
    ROOT / "scripts",
    ROOT / "docs",
    ROOT / "README.md",
    ROOT / ".github",
    ROOT / "docs/README.zh-CN.md",
    ROOT / ".agent/AGENTS.md",
    ROOT / "docs/development/CHANGELOG.md",
    ROOT / "start.sh",
    ROOT / "start.command",
    ROOT / "licenses/THIRD_PARTY_NOTICES.md",
    ROOT / "licenses",
    ROOT / "examples/recorded-runs",
    ROOT / "pyproject.toml",
    ROOT / "scripts/deploy/environment.yml",
    ROOT / "data" / "README.md",
    ROOT / "data" / "reproduction",
    ROOT / "data" / "provenance",
    ROOT / "data" / "benchmark" / "packs",
    ROOT / "data" / "episodes",
    ROOT / "data" / "scenes",
]
SKIP_PARTS = {".git", ".pytest_cache", "__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".png", ".jpg", ".jpeg", ".pdf", ".webp", ".gif", ".mp4"}
FORBIDDEN_TERMS = [
    "/dataset" + "_rc",
    "dataset" + "_rc_",
    "xiao" + "peng",
    "fu" + "yao",
    "infra" + "-registry",
    "rc-" + "llmrl",
    "rc-" + "embodied",
    "che" + "ny",
    "public" + "data",
    "bif" + "rost",
    "auth" + "_user",
    "lu" + "ban",
    "inference-" + "fu" + "yao",
    "ai-" + "hub",
    "model" + "_serve",
    "model" + "-serve",
    "chen" + "jiehku",
    "/work" + "space/",
    "serve" + "_only",
    "to" + "do",
    "fix" + "me",
    "ha" + "ck",
    "de" + "bug",
    "note" + "book",
    "cur" + "sor",
    "vs" + "code",
]


def _iter_files(path: Path):
    if path.is_file():
        yield path
        return
    if not path.exists():
        return
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        if any(part in SKIP_PARTS for part in child.parts):
            continue
        if child.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield child


def _release_scan_text(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    if path.suffix.lower() == ".css":
        # A standard CSS pointer declaration is not an editor artifact.
        text = re.sub(r"(?<=[{;])\s*cursor\s*:\s*(?:pointer|default|auto)\s*(?=[;}])", "", text)
    return text


def test_css_pointer_is_allowed_but_editor_artifacts_remain_detectable(tmp_path):
    stylesheet = tmp_path / "style.css"
    stylesheet.write_text("button { cursor: pointer; } /* .cursor/rules */")
    scanned = _release_scan_text(stylesheet)
    assert "cursor: pointer" not in scanned
    assert ".cursor/rules" in scanned


def test_release_tree_has_no_internal_paths_or_cluster_terms():
    hits: list[str] = []
    for target in SCAN_TARGETS:
        for path in _iter_files(target):
            text = _release_scan_text(path)
            for term in FORBIDDEN_TERMS:
                if term in text:
                    hits.append(f"{path.relative_to(ROOT)}: {term}")
    assert not hits, "internal release artifacts found:\n" + "\n".join(hits[:50])


def test_scene_provenance_matches_the_exact_bundled_houses():
    provenance = json.loads((ROOT / "data/provenance/scenes.json").read_text())
    records = provenance["scenes"]
    houses = {p.parent.name: p for p in (ROOT / "data/scenes").glob("*/house.json")}
    assert len(records) == len(houses)
    assert {row["scene_ref"] for row in records} == houses.keys()
    for row in records:
        assert hashlib.sha256(houses[row["scene_ref"]].read_bytes()).hexdigest() == row["house_sha256"]
        if row["source_kind"] == "procthor-10k":
            assert row["dataset_revision"] == provenance["dataset_sources"]["procthor-10k"]["revision"]
            assert type(row["source_index"]) is int and row["source_index"] >= 0
            assert row["source_split"] == "train"


def test_revision_comparison_partitions_selections_and_pins_current_inputs():
    comparison = json.loads((ROOT / "data/provenance/revision_comparison.json").read_text())
    current_ids = {r["episode_id"] for r in _load_canonical_pack()["episodes"]}
    frozen_ids = {r["episode_id"] for r in json.loads(
        (ROOT / "data/reproduction/paper_v4_pack.json").read_text())["episodes"]}
    rows = comparison["shared_inputs"]
    shared_ids = {r["episode_id"] for r in rows}
    assert len(rows) == len(shared_ids) == 953
    assert shared_ids == current_ids & frozen_ids
    assert set(comparison["added_ids"]) == current_ids - frozen_ids
    assert set(comparison["removed_ids"]) == frozen_ids - current_ids
    for key in ("current_pack", "historical_selection"):
        selection = comparison[key]
        assert hashlib.sha256((ROOT / selection["path"]).read_bytes()).hexdigest() == selection["sha256"]
        assert selection["count"] == 1000

    def check_current(path, expected):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected["sha256"]
        normalized = json.dumps(json.loads(path.read_text()), sort_keys=True,
                                separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        assert hashlib.sha256(normalized).hexdigest() == expected["json_sha256"]

    changed_scenes = set()
    for row in rows:
        episode_path = ROOT / "data/episodes" / row["episode_id"] / "episode.json"
        episode = json.loads(episode_path.read_text())
        check_current(episode_path, row["current_episode"])
        assert episode["scene_ref"] == row["current_scene_ref"]
        assert episode["scene"]["platform"] == row["scene_platform"]
        same_episode = row["previous_episode"]["json_sha256"] == row["current_episode"]["json_sha256"]
        assert row["episode_json_equal"] is same_episode
        same_house, same_house_bytes = True, True
        if row["scene_platform"] == "procthor":
            check_current(ROOT / "data/scenes" / row["current_scene_ref"] / "house.json", row["current_house"])
            same_house = row["previous_house"]["json_sha256"] == row["current_house"]["json_sha256"]
            same_house_bytes = row["previous_house"]["sha256"] == row["current_house"]["sha256"]
            if not same_house:
                changed_scenes.add((row["previous_scene_ref"], row["current_scene_ref"]))
        else:
            assert row["scene_platform"] == "ithor" and same_episode
            assert "previous_house" not in row and "current_house" not in row
        assert row["scene_json_equal"] is same_house
        assert row["input_json_equal"] is (same_episode and same_house)
        assert row["input_bytes_equal"] is (
            row["previous_episode"]["sha256"] == row["current_episode"]["sha256"] and same_house_bytes)
    assert comparison["summary"] == {
        "shared_ids": len(rows), "equal_input_json": sum(r["input_json_equal"] for r in rows),
        "equal_input_bytes": sum(r["input_bytes_equal"] for r in rows),
        "changed_shared_inputs": sum(not r["input_json_equal"] for r in rows),
        "changed_shared_scenes": len(changed_scenes),
        "added_ids": len(comparison["added_ids"]), "removed_ids": len(comparison["removed_ids"]),
    } == {"shared_ids": 953, "equal_input_json": 909, "equal_input_bytes": 908,
          "changed_shared_inputs": 44, "changed_shared_scenes": 24, "added_ids": 47, "removed_ids": 47}
    assert {(r["old_scene_ref"], r["new_scene_ref"]) for r in comparison["changed_scenes"]} == changed_scenes
    assert comparison["formatting_only_ids"] == [
        r["episode_id"] for r in rows if r["input_json_equal"] and not r["input_bytes_equal"]]
    assert {r["episode_id"] for r in comparison["changed_episode_definitions"]} == {
        r["episode_id"] for r in rows if not r["episode_json_equal"]}


def test_export_contains_linked_guides_and_inspection_commands(tmp_path):
    destination = tmp_path / "release"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/release/export_public_release.py"), str(destination)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    manifest = json.loads((destination / "docs/development/release_manifest.json").read_text())
    required = {".agent/AGENTS.md", "docs/README.zh-CN.md", "docs/development/CHANGELOG.md", "start.sh", "start.command", "docs/README.md", "scripts/README.md",
                "LICENSE", "NOTICE", "licenses/THIRD_PARTY_NOTICES.md", "licenses/procthor-10k-LICENSE.txt",
                "scripts/release/check_public_release.py", "scripts/__init__.py", "vigil/security.py", "docs/development/SECURITY.md",
                "docs/guides/INSTALLATION.md", "docs/guides/DEPLOYMENT.md", "docs/guides/EVALUATION.md",
                "docs/guides/TRACE_ANALYSIS.md", "vigil/eval/inspection.py", "docs/VIDEO.md",
                "scripts/media/build_overview_video.py", "docs/media/overview.mp4",
                "docs/media/overview-preview.gif", "docs/media/overview-poster.jpg",
                "docs/media/overview.en.vtt", "docs/media/index.html", "docs/media/source/manifest.json",
                "docs/media/player.css", "docs/media/player.js", "scripts/media/preview.py",
                "docs/media/source/benchmark.pdf", "docs/media/source/pipeline.pdf",
                "docs/media/source/failure_distribution_models.pdf", "docs/media/source/belief_closure_figure.pdf",
                "scripts/release/export_recorded_example.py", "examples/recorded-runs/catalog.json",
                "examples/recorded-runs/README.md", "examples/recorded-runs/manifest.json",
                "docs/development/ARCHITECTURE.md", "docs/development/CONTRIBUTING.md", "vigil/agent/model.py",
                ".agent/skills/vigil-onboarding/SKILL.md", ".agent/skills/vigil-evaluation/SKILL.md",
                ".agent/skills/vigil-trace-review/SKILL.md", ".agent/skills/vigil-release/SKILL.md"}
    required.update({"examples/config/.env.example", "examples/config/vigil.json.example", "scripts/deploy/environment.yml"})
    required.update({".github/SUPPORT.md", ".github/CONTRIBUTING.md", ".github/PULL_REQUEST_TEMPLATE.md",
                     ".github/workflows/ci.yml",
                     ".github/ISSUE_TEMPLATE/bug_report.md", ".github/ISSUE_TEMPLATE/feature_request.md",
                     "docs/guides/TROUBLESHOOTING.md"})
    required.add("data/provenance/scenes.json")
    required.add("data/provenance/revision_comparison.json")
    required.update({"data/provenance/task_corrections.json", "data/reproduction/paper_v4_pack.json"})
    required.update({"docs/reference/RUNTIME.md", "scripts/deploy/constraints-macos-x86_64.txt"})
    assert required <= manifest.keys()
    assert "AGENTS.md" not in manifest and "AGENT.md" not in manifest
    assert "vigil.json" not in manifest
    for name, digest in manifest.items():
        assert hashlib.sha256((destination / name).read_bytes()).hexdigest() == digest
    for name in manifest:
        if not name.endswith(".md"):
            continue
        document = destination / name
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", document.read_text()):
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            target = unquote(urlsplit(target).path)
            if not target:
                continue
            assert (document.parent / target).exists(), f"{name}: broken link {target}"

    # A real candidate with accidental credentials must fail before any copy.
    key = "sk-" + "synthetic0123456789" * 2
    with (destination / "README.md").open("a") as handle:
        handle.write("\n" + key + "\n")
    rejected = tmp_path / "rejected"
    result = subprocess.run([sys.executable, str(destination / "scripts/release/export_public_release.py"), str(rejected)],
                            capture_output=True, text=True)
    assert result.returncode != 0 and not rejected.exists()
    assert "public content scan failed" in result.stderr
    assert key not in result.stdout + result.stderr



def _load_canonical_pack():
    return json.loads(CANONICAL_PACK.read_text(encoding="utf-8"))


def test_release_contains_only_canonical_pack():
    pack_files = sorted((ROOT / "data" / "benchmark" / "packs").glob("*.json"))
    assert pack_files == [CANONICAL_PACK]


def test_canonical_pack_has_no_build_provenance():
    payload = _load_canonical_pack()
    assert not (PROVENANCE_TOP_LEVEL_KEYS & set(payload))
    summary = payload.get("summary") or {}
    assert not (PROVENANCE_SUMMARY_KEYS & set(summary))
    text = json.dumps(payload, ensure_ascii=False).lower()
    hits = [term for term in PROVENANCE_TEXT_TERMS if term in text]
    assert not hits


def test_episode_directories_match_canonical_pack_manifest():
    payload = _load_canonical_pack()
    episode_ids = {item["episode_id"] for item in payload["episodes"]}
    episode_dirs = {path.name for path in (ROOT / "data" / "episodes").iterdir() if path.is_dir()}
    assert len(episode_ids) == 1000
    assert episode_dirs == episode_ids
    missing_files = [episode_id for episode_id in episode_ids if not (ROOT / "data" / "episodes" / episode_id / "episode.json").is_file()]
    assert not missing_files
