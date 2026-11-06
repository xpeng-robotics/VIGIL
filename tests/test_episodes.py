import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from vigil.data.episodes import EpisodeSpec, load_pack
from vigil.data.episodes import EpisodeSpec as BenchmarkEpisodeSpec
from vigil.data.paths import CANONICAL_PACK

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "data/benchmark/packs" / CANONICAL_PACK


def test_load_canonical_1000_pack():
    pack = load_pack(PACK)
    assert pack.pack_id == "mixed_mainline_manual_revised_1000_v2"
    assert len(pack.episodes) == 1000
    first = pack.episodes[0]
    assert first.episode_id == "ithor_fp1_s1_pixel_grounding_easy_fridge_ground_001"
    assert first.scene_id == "FloorPlan1"
    assert first.task_family == "S1_pixel_grounding"


def test_revised_pack_preserves_family_balance_and_explicit_sm_budgets():
    pack = load_pack(PACK)
    assert set(Counter(e.task_family for e in pack.episodes).values()) == {125}
    specs = [EpisodeSpec.from_path(ROOT / "data/episodes" / e.episode_id / "episode.json")
             for e in pack.episodes]
    sm = [e for e in specs if e.task_family.startswith("T3")]
    assert Counter(e.max_steps for e in sm) == {30: 123, 35: 1, 45: 1}


def test_drawer_corrections_keep_setup_oracle_and_report_bound_to_one_target():
    manifest = json.loads((ROOT / "data/provenance/task_corrections.json").read_text())
    assert hashlib.sha256(PACK.read_bytes()).hexdigest() == manifest["pack_sha256"]
    rows = {e["episode_id"]: e for e in json.loads(PACK.read_text())["episodes"]}
    corrections = manifest["corrected_episodes"]
    assert len(corrections) == 9
    assert sum(c["pose_changed"] for c in corrections) == 1
    for correction in corrections:
        episode_id = correction["corrected_episode_id"]
        assert correction["original_episode_id"] not in rows
        assert rows[episode_id]["target_object_type"] == "Drawer"
        path = ROOT / "data/episodes" / episode_id / "episode.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == correction["corrected_episode_sha256"]
        episode = json.loads(path.read_text())
        target = correction["target_object_id"]
        condition = episode["success_condition"]
        assert episode["task"]["target_object_type"] == "Drawer"
        assert condition["target_object_id"] == condition["oracle_condition"]["target_object_id"] == target
        assert condition["target_object_type"] == condition["oracle_condition"]["target_object_type"] == "Drawer"
        assert condition["expected"] == correction["expected_state"]
        assert condition["oracle_condition"]["value"] is (correction["expected_state"] == "open")
        setters = [a for a in episode["scene_setup"] if a["action"] in {"OpenObject", "CloseObject"}]
        assert len(setters) == 1 and setters[0]["objectId"] == target
        assert setters[0]["action"] == ("OpenObject" if correction["expected_state"] == "open" else "CloseObject")
        assert episode["agent_init"] == correction["corrected_pose"]
        assert episode["budget"]["max_steps"] == 5
        assert episode["budget"]["max_invalid_actions"] == 2


def test_historical_score_selection_is_frozen_separately_from_current_data():
    original = ROOT / "data/reproduction/paper_v4_pack.json"
    original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
    assert original_hash == "1ad6913d84364141d62c5662cc17c652d009fe41ffdca05b3c88a9cb26a4c245"
    assert hashlib.sha256(PACK.read_bytes()).hexdigest() != original_hash
    old_ids = {e["episode_id"] for e in json.loads(original.read_text())["episodes"]}
    new_ids = {e["episode_id"] for e in json.loads(PACK.read_text())["episodes"]}
    assert len(old_ids) == len(new_ids) == 1000
    assert len(new_ids - old_ids) == len(old_ids - new_ids) == 47


def test_vigil_style_episode_config_loads():
    episode = EpisodeSpec.from_dict(
        {
            "episode_id": "ep_001",
            "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
            "agent_init": {"position": {"x": 0, "y": 0.9, "z": 0}, "rotation": {"x": 0, "y": 0, "z": 0}, "horizon": 0},
            "task": {"instruction": "Find the mug.", "task_family": "S1_pixel_grounding"},
            "budget": {"max_steps": 5, "max_invalid_actions": 2},
            "success_condition": {"type": "object_state", "target_object_type": "Mug", "field": "visible", "value": True},
            "trace_hints": {"task_family": "S1_pixel_grounding"},
        }
    )
    assert episode.instruction == "Find the mug."
    assert episode.max_steps == 5


def test_duplicate_episode_ids_fail(tmp_path):
    path = tmp_path / "bad_pack.json"
    path.write_text(
        '''
        {
          "episodes": [
            {"episode_id": "dup", "scene_id": "FloorPlan1", "task_family": "S1"},
            {"episode_id": "dup", "scene_id": "FloorPlan1", "task_family": "S1"}
          ]
        }
        ''',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate episode_id"):
        load_pack(path)


def test_vigil_style_episode_preserves_scene_ref():
    episode = EpisodeSpec.from_dict(
        {
            "episode_id": "ep_proc",
            "scene_ref": "procthor10k_train_0001",
            "scene": {"platform": "procthor", "scene_id": "Procedural"},
            "agent_init": {"position": {"x": 0, "y": 0.9, "z": 0}, "rotation": {"x": 0, "y": 0, "z": 0}, "horizon": 0},
            "task": {"instruction": "Find the mug.", "task_family": "S1_pixel_grounding"},
            "budget": {"max_steps": 5},
            "success_condition": {"type": "object_state", "target_object_type": "Mug", "field": "visible", "value": True},
        }
    )
    assert episode.scene_ref == "procthor10k_train_0001"


def test_benchmark_episode_module_is_canonical():
    assert EpisodeSpec is BenchmarkEpisodeSpec


def test_vigil_style_episode_preserves_benchmark_contract_fields():
    episode = EpisodeSpec.from_dict(
        {
            "episode_id": "ep_contract",
            "scene": {"platform": "ithor", "scene_id": "FloorPlan1"},
            "agent_init": {},
            "task": {"instruction": "Open the fridge.", "task_family": "T1_grounded_interaction"},
            "budget": {"max_steps": 6, "max_invalid_actions": 2, "timeout_policy": "fail"},
            "success_condition": {"type": "object_state", "target_object_type": "Fridge", "field": "is_open", "value": True},
            "constraint_spec": {"report_required": False},
            "trace_hints": {"target_object_type": "Fridge"},
            "interactables": [{"object_type": "Fridge"}],
        }
    )

    assert episode.budget["max_steps"] == 6
    assert episode.budget["max_invalid_actions"] == 2
    assert episode.constraint_spec["invalid_action_limit"] == 2
    assert episode.constraint_spec["report_required"] is False
    assert episode.trace_hints["task_family"] == "T1_grounded_interaction"
    assert episode.trace_hints["target_object_type"] == "Fridge"
    assert episode.generation_hints["interactables"] == [{"object_type": "Fridge"}]


def test_load_pack_preserves_release_top_level_metadata(tmp_path):
    episode = {
        "episode_id": "ep_pack",
        "scene_id": "FloorPlan1",
        "task_family": "S1_pixel_grounding",
        "instruction": "Find the fridge.",
        "max_steps": 5,
    }
    pack_path = tmp_path / "pack.json"
    pack_path.write_text(
        json.dumps(
            {
                "version": "2026-05-02",
                "pack_id": "mixed_mainline_manual_first_balanced_1000_v1",
                "platform": "mixed",
                "status": "release",
                "episodes": [episode],
            }
        ),
        encoding="utf-8",
    )

    pack = load_pack(pack_path)

    assert pack.pack_id == "mixed_mainline_manual_first_balanced_1000_v1"
    assert pack.metadata["platform"] == "mixed"
    assert pack.metadata["version"] == "2026-05-02"
