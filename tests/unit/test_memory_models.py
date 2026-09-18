"""Contract tests for memory models: MemoryEntry, MemoryQuery, MemorySummary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from om_harness.memory.models import MemoryEntry, MemoryQuery, MemorySummary


def test_memory_entry_has_defaults() -> None:
    entry = MemoryEntry(content="the build script lives in Makefile")
    assert entry.confidence == 1.0
    assert entry.access_count == 0
    assert entry.tags == []
    assert entry.source_session is not None
    assert entry.created_at is not None


def test_memory_entry_stores_all_fields() -> None:
    session_id = "sess-abc123"
    entry = MemoryEntry(
        content="Fixed bug in parser.py at line 42",
        tags=["bug", "fix"],
        source_session=session_id,
        source_task="impl-1",
        confidence=0.9,
    )
    assert entry.content == "Fixed bug in parser.py at line 42"
    assert entry.tags == ["bug", "fix"]
    assert entry.source_session == session_id
    assert entry.source_task == "impl-1"
    assert entry.confidence == 0.9
    assert entry.access_count == 0
    assert entry.last_accessed is None


def test_memory_entry_roundtrips_via_json() -> None:
    entry = MemoryEntry(
        content="database URL is postgres://localhost/db",
        tags=["config", "db"],
        source_session="sess-1",
        confidence=0.8,
    )
    json_str = entry.model_dump_json()
    loaded = MemoryEntry.model_validate_json(json_str)
    assert loaded == entry


def test_memory_entry_confidence_is_clamped() -> None:
    entry = MemoryEntry(content="test", confidence=1.5)
    assert entry.confidence == 1.0

    entry2 = MemoryEntry(content="test", confidence=-0.5)
    assert entry2.confidence == 0.0


def test_memory_entry_is_expired_when_past_ttl() -> None:
    past = datetime.now(UTC) - timedelta(days=10)
    entry = MemoryEntry(
        content="temporary fact",
        expires_at=past,
    )
    assert entry.is_expired() is True


def test_memory_entry_is_not_expired_when_no_ttl() -> None:
    entry = MemoryEntry(content="permanent fact", expires_at=None)
    assert entry.is_expired() is False


def test_memory_entry_is_not_expired_when_within_ttl() -> None:
    future = datetime.now(UTC) + timedelta(days=1)
    entry = MemoryEntry(content="recent fact", expires_at=future)
    assert entry.is_expired() is False


def test_memory_entry_bumps_access_on_recall() -> None:
    entry = MemoryEntry(content="test")
    assert entry.access_count == 0
    entry.bump_access()
    assert entry.access_count == 1
    assert entry.last_accessed is not None
    entry.bump_access()
    assert entry.access_count == 2


def test_memory_query_defaults() -> None:
    q = MemoryQuery(query="database config")
    assert q.tags is None
    assert q.limit == 10
    assert q.min_confidence == 0.0


def test_memory_query_with_filters() -> None:
    q = MemoryQuery(query="error", tags=["bug", "fix"], limit=5, min_confidence=0.5)
    assert q.query == "error"
    assert q.tags == ["bug", "fix"]
    assert q.limit == 5
    assert q.min_confidence == 0.5


def test_memory_query_roundtrips() -> None:
    q = MemoryQuery(query="parser", tags=["bug"], limit=3, min_confidence=0.7)
    loaded = MemoryQuery.model_validate_json(q.model_dump_json())
    assert loaded == q


def test_memory_summary_stores_ids() -> None:
    s = MemorySummary(summary="compacted 5 entries", entry_ids=["m1", "m2", "m3"])
    assert s.summary == "compacted 5 entries"
    assert s.entry_ids == ["m1", "m2", "m3"]


def test_memory_summary_roundtrips() -> None:
    s = MemorySummary(summary="old facts compacted", entry_ids=["a", "b"])
    loaded = MemorySummary.model_validate_json(s.model_dump_json())
    assert loaded == s
