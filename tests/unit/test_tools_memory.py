"""Contract tests for memory tools: remember and recall."""

from __future__ import annotations

from typing import Any

import pytest

from om_harness.memory.index import MemoryIndex
from om_harness.memory.models import MemoryEntry
from om_harness.memory.store import MemoryStore
from om_harness.tools.base import Permission, ToolContext
from om_harness.tools.memory import MemoryRecallTool, MemoryRememberTool


@pytest.fixture
def idx_and_store(tmp_path: Any) -> tuple[MemoryIndex, MemoryStore]:
    store = MemoryStore(tmp_path / "memory")
    idx = MemoryIndex(store)
    idx.build()
    return idx, store


@pytest.fixture
def remember_tool(
    tmp_path: Any, idx_and_store: tuple[MemoryIndex, MemoryStore]
) -> MemoryRememberTool:
    idx, store = idx_and_store
    ctx = ToolContext(repo_root=tmp_path)
    return MemoryRememberTool(ctx, store=store, source_session="sess-1", index=idx)


@pytest.fixture
def recall_tool(tmp_path: Any, idx_and_store: tuple[MemoryIndex, MemoryStore]) -> MemoryRecallTool:
    idx, _store = idx_and_store
    ctx = ToolContext(repo_root=tmp_path)
    return MemoryRecallTool(ctx, index=idx)


# -- remember tool --------------------------------------------------------------


def test_remember_permission_is_mutating(remember_tool: MemoryRememberTool) -> None:
    assert remember_tool.permission == Permission.mutating


async def test_remember_stores_fact(remember_tool: MemoryRememberTool) -> None:
    result = await remember_tool.run(
        MemoryRememberTool.Args(
            fact="The database URL is postgres://localhost/db",
            tags=["config", "db"],
        )
    )
    assert result.ok
    entries = remember_tool.store.load_all()
    assert len(entries) == 1
    assert "database URL" in entries[0].content
    assert "config" in entries[0].tags
    assert "db" in entries[0].tags
    assert entries[0].source_session == "sess-1"


async def test_remember_defaults_confidence(remember_tool: MemoryRememberTool) -> None:
    await remember_tool.run(MemoryRememberTool.Args(fact="the build is in Makefile"))
    entry = remember_tool.store.load_all()[0]
    assert entry.confidence == 1.0


async def test_remember_accepts_custom_confidence(remember_tool: MemoryRememberTool) -> None:
    await remember_tool.run(MemoryRememberTool.Args(fact="maybe this is true", confidence=0.3))
    entry = remember_tool.store.load_all()[0]
    assert entry.confidence == 0.3


async def test_remember_includes_source_task(remember_tool: MemoryRememberTool) -> None:
    result = await remember_tool.run(
        MemoryRememberTool.Args(
            fact="found the parser bug",
            source_task="explore-1",
        )
    )
    assert result.ok
    entry = remember_tool.store.load_all()[0]
    assert entry.source_task == "explore-1"


async def test_remember_updates_existing_entry_by_id(remember_tool: MemoryRememberTool) -> None:
    """Storing a fact with a known entry_id updates rather than duplicates."""
    existing = MemoryEntry(entry_id="known-id", content="original fact", source_session="sess-1")
    remember_tool.store.store(existing)
    await remember_tool.run(MemoryRememberTool.Args(fact="updated fact", entry_id="known-id"))
    entries = remember_tool.store.load_all()
    assert len(entries) == 1
    assert entries[0].content == "updated fact"


async def test_remember_returns_entry_id_in_data(remember_tool: MemoryRememberTool) -> None:
    result = await remember_tool.run(MemoryRememberTool.Args(fact="important fact"))
    assert result.ok
    assert "entry_id" in result.data
    assert result.data["entry_id"]


async def test_remember_updates_index(
    remember_tool: MemoryRememberTool, recall_tool: MemoryRecallTool
) -> None:
    """remember should also update the in-memory index for immediate recall."""
    await remember_tool.run(MemoryRememberTool.Args(fact="database config is in config.yml"))
    # The index should now have this entry
    assert remember_tool.index.total_entries == 1
    # And recall should find it
    result = await recall_tool.run(MemoryRecallTool.Args(query="database"))
    assert result.ok
    assert "database" in result.output.lower()


# -- recall tool ----------------------------------------------------------------


def test_recall_permission_is_read_only(recall_tool: MemoryRecallTool) -> None:
    assert recall_tool.permission == Permission.read_only


async def test_recall_finds_matching_entries(recall_tool: MemoryRecallTool) -> None:
    recall_tool.index.add(_entry("database config uses postgres://localhost"))
    result = await recall_tool.run(MemoryRecallTool.Args(query="database"))
    assert result.ok
    assert "database" in result.output.lower()


async def test_recall_returns_empty_when_no_match(recall_tool: MemoryRecallTool) -> None:
    recall_tool.index.add(_entry("database config uses postgres://localhost"))
    result = await recall_tool.run(MemoryRecallTool.Args(query="nonexistent keyword"))
    assert result.ok
    assert "no" in result.output.lower()


async def test_recall_filters_by_tags(recall_tool: MemoryRecallTool) -> None:
    recall_tool.index.add(_entry("db url is localhost", tags=["config"]))
    recall_tool.index.add(_entry("parser crashes here", tags=["bug"]))
    result = await recall_tool.run(MemoryRecallTool.Args(query="localhost", tags=["config"]))
    assert result.ok
    # Only config-tagged entry should be returned
    assert "parser" not in result.output.lower()


async def test_recall_respects_limit(recall_tool: MemoryRecallTool) -> None:
    for i in range(10):
        recall_tool.index.add(_entry(f"database fact number {i}"))
    result = await recall_tool.run(MemoryRecallTool.Args(query="database", limit=3))
    assert result.ok
    assert result.data["count"] == 3


async def test_recall_returns_entry_metadata(recall_tool: MemoryRecallTool) -> None:
    recall_tool.index.add(_entry("database config", tags=["db", "config"]))
    result = await recall_tool.run(MemoryRecallTool.Args(query="database"))
    assert result.ok
    assert "count" in result.data
    assert result.data["count"] == 1


def _entry(content: str, tags: list[str] | None = None, **kw: Any) -> MemoryEntry:
    return MemoryEntry(content=content, tags=tags or [], **kw)
