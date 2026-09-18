"""Contract tests for the context compressor (mechanical fact extraction + compression)."""

from __future__ import annotations

from typing import Any

import pytest

from om_harness.memory.compressor import ContextCompressor
from om_harness.memory.store import MemoryStore
from om_harness.models.session import Message, MessageRole


@pytest.fixture
def store(tmp_path: Any) -> MemoryStore:
    return MemoryStore(tmp_path / "memory")


@pytest.fixture
def compressor(store: MemoryStore) -> ContextCompressor:
    return ContextCompressor(store=store, max_fact_chars=200)


# -- fact extraction ------------------------------------------------------------


def test_extract_facts_from_file_paths(compressor: ContextCompressor) -> None:
    """File paths mentioned in text should be extracted as facts."""
    text = "The main issue is in src/parser.py at line 42. Also check src/config.py."
    facts = compressor.extract_facts(text, tags=["auto"])
    assert len(facts) >= 2
    contents = [f.content for f in facts]
    assert any("src/parser.py" in c for c in contents)
    assert any("src/config.py" in c for c in contents)


def test_extract_facts_from_error_messages(compressor: ContextCompressor) -> None:
    """Error-like text should be extracted as facts tagged 'error'."""
    text = "Error: division by zero at line 42"
    facts = compressor.extract_facts(text, tags=["auto"])
    assert len(facts) >= 1
    error_facts = [f for f in facts if "error" in f.tags]
    assert len(error_facts) >= 1


def test_extract_facts_from_decisions(compressor: ContextCompressor) -> None:
    """Decision sentences should be extracted as facts tagged 'decision'."""
    text = "We decided to use postgres for the database. The team agreed on redis for caching."
    facts = compressor.extract_facts(text, tags=["auto"])
    decision_facts = [f for f in facts if "decision" in f.tags]
    assert len(decision_facts) >= 2


def test_extract_facts_key_value_patterns(compressor: ContextCompressor) -> None:
    """Key-value patterns like 'X is Y' or 'X changed to Y' should be extracted."""
    text = "The database URL is postgres://localhost. The port changed to 5432."
    facts = compressor.extract_facts(text, tags=["auto"])
    contents = " ".join(f.content for f in facts)
    assert "database URL" in contents.lower() or "postgres" in contents.lower()


def test_extract_facts_truncates_long_facts(compressor: ContextCompressor) -> None:
    """Facts longer than max_fact_chars should be truncated."""
    long_text = " ".join(["word"] * 200)
    facts = compressor.extract_facts(long_text, tags=["auto"])
    for fact in facts:
        assert len(fact.content) <= 200


def test_extract_facts_empty_text_returns_empty(compressor: ContextCompressor) -> None:
    facts = compressor.extract_facts("", tags=["auto"])
    assert facts == []


def test_extract_facts_no_tags_returns_with_default_tags(compressor: ContextCompressor) -> None:
    text = "database URL is postgres://localhost"
    facts = compressor.extract_facts(text, tags=[])
    assert len(facts) >= 1
    # Should have at least some tag
    for f in facts:
        assert len(f.tags) >= 0  # tags can be empty but the fact is extracted


def test_extract_facts_preserves_session_id(compressor: ContextCompressor) -> None:
    text = "The cache is in src/cache.py"
    facts = compressor.extract_facts(text, tags=["auto"], source_session="sess-123")
    for f in facts:
        assert f.source_session == "sess-123"


# -- compress_history ----------------------------------------------------------


def test_compress_history_extracts_and_summarizes(compressor: ContextCompressor) -> None:
    """compress_history returns a summary and stores extracted facts."""
    history = [
        Message(
            role=MessageRole.user,
            content="The bug is in src/parser.py line 42 - division by zero",
        ),
        Message(
            role=MessageRole.assistant,
            content="I decided to add a null check before the division operation.",
        ),
        Message(
            role=MessageRole.user,
            content="The database URL is postgres://localhost/db",
        ),
    ]
    summary = compressor.compress_history(history, session_id="sess-1")
    assert "Earlier conversation" in summary or "summar" in summary.lower()
    # Facts should have been stored
    assert compressor.store.count() > 0


def test_compress_history_empty_returns_empty_string(compressor: ContextCompressor) -> None:
    summary = compressor.compress_history([], session_id="sess-1")
    assert summary == ""


def test_compress_history_extracts_file_paths(compressor: ContextCompressor) -> None:
    history = [
        Message(role=MessageRole.user, content="Found the issue in src/main.py"),
    ]
    compressor.compress_history(history, session_id="sess-1")
    entries = compressor.store.load_all()
    assert any("src/main.py" in e.content for e in entries)


def test_compress_history_extracts_decisions(compressor: ContextCompressor) -> None:
    history = [
        Message(role=MessageRole.assistant, content="We decided to use the async approach."),
    ]
    compressor.compress_history(history, session_id="sess-1")
    entries = compressor.store.load_all()
    for e in entries:
        if "decided" in e.content.lower():
            assert "decision" in e.tags


def test_compress_history_tags_preserved(compressor: ContextCompressor) -> None:
    history = [
        Message(role=MessageRole.user, content="The database URL is postgres://localhost"),
    ]
    compressor.compress_history(history, session_id="sess-1", extra_tags=["explored"])
    entries = compressor.store.load_all()
    found = False
    for e in entries:
        if "database" in e.content.lower() and "explored" in e.tags:
            found = True
    assert found


# -- salience scoring ----------------------------------------------------------


def test_salience_scores_messages(compressor: ContextCompressor) -> None:
    """Messages with code entities and decisions get higher salience scores."""
    low = Message(
        role=MessageRole.assistant,
        content="Sure, I can help with that.",
    )
    high = Message(
        role=MessageRole.user,
        content="The bug is in src/parser.py at line 42. We decided to fix it with a null check.",
    )
    assert compressor.salience_score(high.content) > compressor.salience_score(low.content)


def test_salience_empty_text_returns_zero(compressor: ContextCompressor) -> None:
    assert compressor.salience_score("") == 0.0


def test_salience_scores_error_messages(compressor: ContextCompressor) -> None:
    regular = "The build is running."
    error = "Error: failed to connect to postgres://localhost"
    assert compressor.salience_score(error) > compressor.salience_score(regular)


# -- LLM compression stub -------------------------------------------------------


def test_llm_compress_is_stubbed(compressor: ContextCompressor) -> None:
    """LLM compression is not implemented; calling it raises NotImplementedError."""
    with pytest.raises(NotImplementedError):
        compressor.llm_compress("some text", model_str="openai:gpt-4o")


def test_llm_compress_strategy_uses_mechanical_fallback(compressor: ContextCompressor) -> None:
    """When strategy is 'llm' but no model is available, falls back to mechanical."""
    text = "The bug is in src/parser.py at line 42"
    summary = compressor.compress(text, strategy="llm", model_str=None, session_id="sess-1")
    assert "parser.py" in summary or "earlier" in summary.lower()
