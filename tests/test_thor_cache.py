from __future__ import annotations

from pathlib import Path

from vigil.envs.thor import _link_ai2thor_release_cache


def test_link_ai2thor_release_cache(monkeypatch, tmp_path):
    source = tmp_path / "release-cache"
    release_dir = source / "thor-CloudRendering-test"
    release_dir.mkdir(parents=True)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("VIGIL_THOR_RELEASES_DIR", str(source))

    _link_ai2thor_release_cache()

    linked = home / ".ai2thor" / "releases" / release_dir.name
    assert linked.is_symlink()
    assert linked.resolve() == release_dir


def test_link_ai2thor_release_cache_uses_job_base(monkeypatch, tmp_path):
    source = tmp_path / "release-cache"
    release_dir = source / "thor-CloudRendering-test"
    release_dir.mkdir(parents=True)
    job_base = tmp_path / "ai2thor-job"
    monkeypatch.setenv("VIGIL_THOR_RELEASES_DIR", str(source))
    monkeypatch.setenv("VIGIL_AI2THOR_BASE", str(job_base))

    _link_ai2thor_release_cache()

    linked = job_base / "releases" / release_dir.name
    assert linked.is_symlink()
    assert linked.resolve() == release_dir
