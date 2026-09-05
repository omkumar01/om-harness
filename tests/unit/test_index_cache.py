"""Contract tests for the persisted repo-index cache in the user cache dir."""

from __future__ import annotations

import json
from typing import Any

import pytest

from om_harness.context.repo_index import RepoIndex


@pytest.fixture
def repo(tmp_path: Any) -> Any:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    return tmp_path


def test_cache_written_and_reused(repo: Any, tmp_path: Any) -> None:
    cache_dir = tmp_path / "cache"
    index = RepoIndex(repo, cache_dir=cache_dir)

    calls = {"n": 0}

    from om_harness.context import repo_index as ri_module

    real_walk = ri_module.iter_repo_files

    def counting_walk(*args: Any, **kwargs: Any) -> list[Any]:
        calls["n"] += 1
        return real_walk(*args, **kwargs)

    ri_module.iter_repo_files = counting_walk
    try:
        index.build()  # cold: walks + writes cache
        assert calls["n"] == 1
        index2 = RepoIndex(repo, cache_dir=cache_dir)
        index2.build()  # warm: served from cache
        assert calls["n"] == 1
        assert index2.summary() == index.summary()
    finally:
        ri_module.iter_repo_files = real_walk

    cache_file = next((cache_dir / "repo-index").glob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["total_files"] >= 1


def test_expired_cache_rebuilt(repo: Any, tmp_path: Any) -> None:
    cache_dir = tmp_path / "cache"
    RepoIndex(repo, cache_dir=cache_dir).build()
    cache_file = next((cache_dir / "repo-index").glob("*.json"))
    # Simulate age beyond TTL.
    stale = json.loads(cache_file.read_text(encoding="utf-8"))
    stale["built_at"] = "2000-01-01T00:00:00+00:00"
    cache_file.write_text(json.dumps(stale), encoding="utf-8")

    from om_harness.context import repo_index as ri_module

    calls = {"n": 0}
    real_walk = ri_module.iter_repo_files

    def counting_walk(*args: Any, **kwargs: Any) -> list[Any]:
        calls["n"] += 1
        return real_walk(*args, **kwargs)

    ri_module.iter_repo_files = counting_walk
    try:
        index = RepoIndex(repo, cache_dir=cache_dir, cache_ttl_hours=24)
        index.build()
        assert calls["n"] == 1  # cache stale -> walked again
    finally:
        ri_module.iter_repo_files = real_walk


def test_invalidate_removes_cache_file(repo: Any, tmp_path: Any) -> None:
    cache_dir = tmp_path / "cache"
    index = RepoIndex(repo, cache_dir=cache_dir)
    index.build()
    assert list((cache_dir / "repo-index").glob("*.json"))
    index.invalidate()
    assert not list((cache_dir / "repo-index").glob("*.json"))
    # Still functional afterwards (re-walk).
    index.build()
    assert "src/a.py" in index.summary()


def test_no_cache_dir_keeps_previous_behavior(repo: Any) -> None:
    index = RepoIndex(repo)
    index.build()
    index.build()  # in-memory no-op
    assert index.is_built
