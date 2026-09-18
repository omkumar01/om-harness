"""Contract tests for the memory index (inverted keyword index, relevance scoring)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from om_harness.memory.index import MemoryIndex
from om_harness.memory.models import MemoryEntry, MemoryQuery
from om_harness.memory.store import MemoryStore


def _entry(content: str, tags: list[str] | None = None, **kw: Any) -> MemoryEntry:
    return MemoryEntry(content=content, tags=tags or [], **kw)


@pytest.fixture
def idx(tmp_path: Any) -> MemoryIndex:
    store = MemoryStore(tmp_path / "memory")
    return MemoryIndex(store)


# -- build ----------------------------------------------------------------------


def test_build_from_empty_store(idx: MemoryIndex) -> None:
    idx.build()
    assert idx.total_entries == 0


def test_build_indexes_entries(idx: MemoryIndex, tmp_path: Any) -> None:
    idx.store.store(_entry("the database config is in config.yml"))
    idx.store.store(_entry("parser.py line 42 has a division by zero bug"))
    idx.build()
    assert idx.total_entries == 2


# -- basic retrieval ------------------------------------------------------------


def test_retrieve_matches_by_keyword(idx: MemoryIndex) -> None:
    idx.add(_entry("database connection uses postgres://localhost"))
    idx.add(_entry("frontend button color is blue"))
    results = idx.retrieve(MemoryQuery(query="database"))
    assert len(results) == 1
    assert "database" in results[0].content.lower()


def test_retrieve_no_match_returns_empty(idx: MemoryIndex) -> None:
    idx.add(_entry("uses postgres database"))
    results = idx.retrieve(MemoryQuery(query="quantum physics"))
    assert results == []


def test_retrieve_multiple_terms_matches_any(idx: MemoryIndex) -> None:
    """Query with multiple terms matches entries containing any term."""
    idx.add(_entry("database config is in config.yml"))
    idx.add(_entry("parser.py has a crash bug"))
    results = idx.retrieve(MemoryQuery(query="database parser"))
    assert len(results) == 2


def test_retrieve_respects_limit(idx: MemoryIndex) -> None:
    for i in range(5):
        idx.add(_entry(f"fact number {i} about database"))
    results = idx.retrieve(MemoryQuery(query="database", limit=3))
    assert len(results) == 3


# -- filtering ------------------------------------------------------------------


def test_retrieve_filters_by_tags(idx: MemoryIndex) -> None:
    idx.add(_entry("db url is localhost", tags=["config"]))
    idx.add(_entry("parser crashes on null", tags=["bug"]))
    idx.add(_entry("db pool size is 10", tags=["config", "performance"]))
    results = idx.retrieve(MemoryQuery(query="db", tags=["config"]))
    assert len(results) == 2
    for r in results:
        assert "config" in r.tags


def test_retrieve_filters_by_multiple_tags(idx: MemoryIndex) -> None:
    idx.add(_entry("db url", tags=["config"]))
    idx.add(_entry("db pool", tags=["config", "performance"]))
    results = idx.retrieve(MemoryQuery(query="db", tags=["config", "performance"]))
    assert len(results) == 1
    assert "performance" in results[0].tags


def test_retrieve_filters_by_min_confidence(idx: MemoryIndex) -> None:
    idx.add(_entry("high confidence fact", confidence=0.9))
    idx.add(_entry("low confidence fact", confidence=0.3))
    results = idx.retrieve(MemoryQuery(query="fact", min_confidence=0.5))
    assert len(results) == 1
    assert results[0].confidence == 0.9


# -- scoring --------------------------------------------------------------------


def test_relevance_scores_by_match_count(idx: MemoryIndex) -> None:
    """Entry matching more query terms scores higher."""
    idx.add(_entry("database postgresql connection"))
    idx.add(_entry("database"))
    results = idx.retrieve(MemoryQuery(query="database postgresql"))
    assert len(results) == 2
    # The entry with both terms should rank higher
    assert "postgresql" in results[0].content


def test_recency_boosts_score(idx: MemoryIndex) -> None:
    """Newer entries score higher than older ones, all else equal."""
    old = datetime.now(UTC) - timedelta(days=30)
    new = datetime.now(UTC)
    idx.add(_entry("database config", created_at=old))
    idx.add(_entry("database pool", created_at=new))
    results = idx.retrieve(MemoryQuery(query="database"))
    # The newer entry should be ranked first (same match count, recency boost)
    assert results[0].content == "database pool"


def test_access_count_boosts_score(idx: MemoryIndex) -> None:
    """Frequently accessed entries score higher."""
    base = datetime.now(UTC)
    e1 = _entry("database config", created_at=base)
    e2 = _entry("database pool", created_at=base)
    idx.add(e1)
    idx.add(e2)
    # Simulate prior access of e1
    idx._entries[e1.entry_id].access_count = 10
    idx._entries[e1.entry_id].last_accessed = datetime.now(UTC)
    results = idx.retrieve(MemoryQuery(query="database"))
    # e1 should rank higher due to access boost
    matched_ids = [r.entry_id for r in results]
    assert matched_ids.index(e1.entry_id) < matched_ids.index(e2.entry_id)


def test_confidence_weights_score(idx: MemoryIndex) -> None:
    """Low-confidence entries are deprioritized."""
    idx.add(_entry("database config", confidence=1.0))
    idx.add(_entry("database pool", confidence=0.1))
    results = idx.retrieve(MemoryQuery(query="database"))
    assert results[0].confidence == 1.0


# -- mutation -------------------------------------------------------------------


def test_add_persists_and_updates_index(idx: MemoryIndex, tmp_path: Any) -> None:
    idx.add(_entry("first database fact"))
    assert idx.total_entries == 1
    # Verify persisted to store on disk
    store2 = MemoryStore(tmp_path / "memory")
    assert len(store2.load_all()) == 1
    idx.add(_entry("second database fact"))
    assert idx.total_entries == 2
    results = idx.retrieve(MemoryQuery(query="database"))
    assert len(results) == 2


def test_retrieval_bumps_access_count(idx: MemoryIndex) -> None:
    entry = _entry("database config")
    idx.add(entry)
    assert entry.access_count == 0
    idx.retrieve(MemoryQuery(query="database"))
    assert entry.access_count == 1
    idx.retrieve(MemoryQuery(query="database"))
    assert entry.access_count == 2


def test_persist_flushes_index_to_store(idx: MemoryIndex, tmp_path: Any) -> None:
    idx.add(_entry("database fact one"))
    idx.add(_entry("database fact two"))
    idx.persist()
    store2 = MemoryStore(tmp_path / "memory")
    loaded = store2.load_all()
    assert len(loaded) == 2


# -- edge cases -----------------------------------------------------------------


def test_retrieve_on_empty_index(idx: MemoryIndex) -> None:
    results = idx.retrieve(MemoryQuery(query="anything"))
    assert results == []


def test_retrieve_case_insensitive(idx: MemoryIndex) -> None:
    idx.add(_entry("Database Configuration is in config.yml"))
    results = idx.retrieve(MemoryQuery(query="database"))
    assert len(results) == 1


def test_build_rebuilds_from_store_after_external_modification(idx: MemoryIndex) -> None:
    idx.store.store(_entry("external fact"))
    idx.build()
    assert idx.total_entries == 1
    assert any("external fact" in e.content for e in idx.retrieve(MemoryQuery(query="fact")))
