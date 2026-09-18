"""Integration tests for ContextAssembler + memory system.

Tests that:
- Memory facts are injected into the assembled context when an index is provided
- Facts are retrieved using the instruction as query
- Backward compatibility is preserved when no index is given
- Enhanced compression triggers when max_context_tokens is exceeded
- Fact extraction during compression stores facts before summarizing
"""

from __future__ import annotations

from typing import Any

from om_harness.config.loader import HarnessConfig
from om_harness.context.assembler import ContextAssembler
from om_harness.context.repo_index import RepoIndex
from om_harness.memory.index import MemoryIndex
from om_harness.memory.models import MemoryEntry
from om_harness.memory.store import MemoryStore
from om_harness.models.session import Message, MessageRole


def _make_index(tmp_path: Any, entries: list[MemoryEntry] | None = None) -> MemoryIndex:
    store = MemoryStore(tmp_path / "memory")
    idx = MemoryIndex(store)
    if entries:
        for e in entries:
            idx.add(e)
    return idx


def _assembler(
    tmp_path: Any,
    memory_index: MemoryIndex | None = None,
    config: HarnessConfig | None = None,
) -> ContextAssembler:
    (tmp_path / "main.py").write_text("print('hi')\n")
    return ContextAssembler(
        config=config or HarnessConfig(),
        repo_index=RepoIndex(tmp_path),
        memory_index=memory_index,
    )


# -- memory injection ----------------------------------------------------------


def test_assemble_includes_memory_facts_when_index_provided(tmp_path: Any) -> None:
    idx = _make_index(
        tmp_path,
        [
            MemoryEntry(content="database config is postgres://localhost/db", tags=["config"]),
            MemoryEntry(content="parser bug at src/parser.py:42 causes crash", tags=["bug"]),
        ],
    )
    assembler = _assembler(tmp_path, memory_index=idx)
    assembled = assembler.assemble(
        role="implementer",
        instruction="fix the parser bug in the database module",
    )
    assert "Prior project knowledge" in assembled.user_prompt
    assert "database" in assembled.user_prompt.lower()
    assert "parser" in assembled.user_prompt.lower()


def test_assemble_memory_facts_relevant_to_instruction(tmp_path: Any) -> None:
    """Only facts relevant to the instruction should be included."""
    idx = _make_index(
        tmp_path,
        [
            MemoryEntry(content="database URL is postgres://localhost", tags=["config"]),
            MemoryEntry(content="how to season pasta correctly", tags=["recipe"]),
        ],
    )
    assembler = _assembler(tmp_path, memory_index=idx)
    assembled = assembler.assemble(
        role="implementer",
        instruction="the database connection is failing",
    )
    assert "database" in assembled.user_prompt.lower()
    assert "season pasta" not in assembled.user_prompt.lower()


def test_assemble_without_memory_index_omits_memory_section(tmp_path: Any) -> None:
    """Backward compatibility: no memory_index means no memory section."""
    assembler = _assembler(tmp_path, memory_index=None)
    assembled = assembler.assemble(
        role="chat",
        instruction="hello there",
    )
    assert "Prior project knowledge" not in assembled.user_prompt


def test_assemble_records_memory_tokens_in_ledger(tmp_path: Any) -> None:
    idx = _make_index(
        tmp_path,
        [
            MemoryEntry(content="the database config uses postgres", tags=["config"]),
        ],
    )
    assembler = _assembler(tmp_path, memory_index=idx)
    assembled = assembler.assemble(
        role="implementer",
        instruction="database setup",
    )
    assert "memory" in assembled.report.items


# -- compression on threshold --------------------------------------------------


def test_compression_triggers_when_max_context_tokens_exceeded(tmp_path: Any) -> None:
    """When context exceeds max_context_tokens, history is compressed."""
    config = HarnessConfig(context={"max_context_tokens": 50, "max_history_messages": 10})
    idx = _make_index(tmp_path)
    assembler = _assembler(tmp_path, memory_index=idx, config=config)

    # Create history long enough to exceed the 50-token threshold
    history = []
    for i in range(20):
        history.append(Message(role=MessageRole.user, content=f"old message {i} " + "pad " * 100))
        history.append(Message(role=MessageRole.assistant, content=f"reply {i} " + "pad " * 100))

    assembled = assembler.assemble(role="chat", instruction="continue", history=history)
    # The history should be compressed (not 20 messages)
    assert len(assembled.history) <= 10


def test_compression_extracts_facts_to_memory(tmp_path: Any) -> None:
    """When compression runs, it should extract facts to the memory store."""
    config = HarnessConfig(context={"max_context_tokens": 50, "max_history_messages": 10})
    idx = _make_index(tmp_path)
    assembler = _assembler(tmp_path, memory_index=idx, config=config)

    history = [
        Message(role=MessageRole.user, content="The bug is in src/parser.py line 42"),
        Message(role=MessageRole.assistant, content="I decided to add a null check."),
    ] * 10  # Repeat to exceed threshold

    assembler.assemble(role="chat", instruction="continue", history=history)
    # Facts should have been extracted and stored
    assert idx.store.count() > 0


def test_no_compression_when_threshold_not_set(tmp_path: Any) -> None:
    """When max_context_tokens is None, use original summarize_history."""
    config = HarnessConfig(context={"max_context_tokens": None, "max_history_messages": 6})
    idx = _make_index(tmp_path)
    assembler = _assembler(tmp_path, memory_index=idx, config=config)

    history = []
    for i in range(20):
        history.append(Message(role=MessageRole.user, content=f"msg {i} " + "x" * 200))

    assembled = assembler.assemble(role="chat", instruction="next", history=history)
    rendered = assembled.render_history()
    # Original summarize_history is used: first 120 chars of recent user messages
    assert len(rendered) <= 6


# -- memory disabled -----------------------------------------------------------


def test_assemble_with_memory_disabled_in_config(tmp_path: Any) -> None:
    """When memory.enabled is False, no memory facts are injected."""
    config = HarnessConfig(memory={"enabled": False})
    idx = _make_index(
        tmp_path,
        [
            MemoryEntry(content="database config", tags=["config"]),
        ],
    )
    assembler = _assembler(tmp_path, memory_index=idx, config=config)
    assembled = assembler.assemble(
        role="implementer",
        instruction="database setup",
    )
    assert "Prior project knowledge" not in assembled.user_prompt
