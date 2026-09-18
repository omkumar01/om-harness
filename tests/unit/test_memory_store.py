"""Contract tests for the memory store (JSONL persistence, atomic writes)."""

from __future__ import annotations

from typing import Any

import pytest

from om_harness.memory.models import MemoryEntry
from om_harness.memory.store import MemoryStore


@pytest.fixture
def store(tmp_path: Any) -> MemoryStore:
    return MemoryStore(tmp_path / "memory")


def _entry(content: str = "test fact") -> MemoryEntry:
    return MemoryEntry(content=content, tags=["test"])


def test_store_roundtrip(store: MemoryStore) -> None:
    entry = _entry("the cache is at src/cache.py")
    store.store(entry)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].content == "the cache is at src/cache.py"
    assert loaded[0].tags == ["test"]


def test_store_empty_dir_returns_empty(store: MemoryStore) -> None:
    assert store.load_all() == []


def test_store_batch(store: MemoryStore) -> None:
    entries = [_entry(f"fact {i}") for i in range(5)]
    store.store_batch(entries)
    loaded = store.load_all()
    assert len(loaded) == 5
    assert {e.content for e in loaded} == {f"fact {i}" for i in range(5)}


def test_store_creates_directory(store: MemoryStore, tmp_path: Any) -> None:
    assert not (tmp_path / "memory").exists()
    store.store(_entry())
    assert (tmp_path / "memory").is_dir()
    assert (tmp_path / "memory" / "memory.jsonl").exists()


def test_store_delete_by_id(store: MemoryStore) -> None:
    e1 = _entry("first")
    e2 = _entry("second")
    store.store(e1)
    store.store(e2)
    assert store.delete(e1.entry_id) is True
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].content == "second"


def test_store_delete_nonexistent_returns_false(store: MemoryStore) -> None:
    store.store(_entry())
    assert store.delete("nonexistent-id") is False


def test_store_clear_removes_all(store: MemoryStore) -> None:
    store.store(_entry("a"))
    store.store(_entry("b"))
    store.store(_entry("c"))
    store.clear()
    assert store.load_all() == []


def test_store_corrupt_line_is_skipped(store: MemoryStore) -> None:
    """A torn final line after a crash should not prevent loading valid entries."""
    store.store(_entry("good fact"))
    # Append a corrupt line manually (simulating a crash mid-write)
    jsonl = store._jsonl_path
    with jsonl.open("a", encoding="utf-8") as fh:
        fh.write("{not valid json\n")
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].content == "good fact"


def test_store_corrupt_file_raises_on_empty_store(store: MemoryStore) -> None:
    """All lines corrupt — load_all returns empty rather than crashing."""
    jsonl = store._jsonl_path
    jsonl.parent.mkdir(parents=True, exist_ok=True)
    jsonl.write_text("{broken\n", encoding="utf-8")
    assert store.load_all() == []


def test_store_interrupted_write_does_not_corrupt(store: MemoryStore) -> None:
    """An atomic write means a crash leaves a .tmp file, not corrupt data."""
    store.store(_entry("safe fact"))
    # Leftover temp file from a crashed write is ignored
    tmp = store._jsonl_path.parent / "memory.jsonl.tmp"
    tmp.write_text('{"partial": ', encoding="utf-8")
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].content == "safe fact"


def test_store_compact_removes_entries_by_ids(store: MemoryStore) -> None:
    """Compact removes entries whose IDs are in the remove set."""
    e1 = _entry("keep me")
    e2 = _entry("remove me")
    e3 = _entry("also remove")
    store.store(e1)
    store.store(e2)
    store.store(e3)
    store.compact(remove_ids={e2.entry_id, e3.entry_id})
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].content == "keep me"


def test_store_persists_across_store_instances(store: MemoryStore, tmp_path: Any) -> None:
    """A new MemoryStore pointing at the same directory reads prior data."""
    store.store(_entry("persisted fact"))
    store2 = MemoryStore(tmp_path / "memory")
    loaded = store2.load_all()
    assert len(loaded) == 1
    assert loaded[0].content == "persisted fact"


def test_store_store_idempotent_replace(store: MemoryStore) -> None:
    """Storing an entry with an existing ID overwrites the old one (dedup)."""
    entry = MemoryEntry(entry_id="fixed-id", content="original")
    store.store(entry)
    updated = MemoryEntry(entry_id="fixed-id", content="replacement", tags=["updated"])
    store.store(updated)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].content == "replacement"
    assert loaded[0].tags == ["updated"]


def test_store_count(store: MemoryStore) -> None:
    store.store(_entry("a"))
    store.store(_entry("b"))
    assert store.count() == 2
    store.store(_entry("c"))
    assert store.count() == 3
