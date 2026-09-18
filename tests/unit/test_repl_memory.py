"""Tests for the /memory slash command in the REPL."""

from __future__ import annotations

import subprocess
from typing import Any

from om_harness.config.loader import Verbosity
from om_harness.harness import Harness
from om_harness.memory.models import MemoryEntry
from om_harness.ui.repl import ChatRepl
from om_harness.ui.slash import find_command


def _repo(tmp_path: Any) -> Any:
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "x.py").write_text("x = 1\n")
    return tmp_path


def _repl(tmp_path: Any, capsys: Any) -> tuple[Harness, ChatRepl]:
    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id, verbosity=Verbosity.verbose)
    return harness, repl


def _add_facts(harness: Harness, *contents: tuple[str, list[str]]) -> None:
    """Helper: add facts to the harness memory index."""
    for content, tags in contents:
        harness.memory_index.add(MemoryEntry(content=content, tags=tags or []))


# -- command discovery ----------------------------------------------------------


def test_memory_is_a_registered_slash_command() -> None:
    cmd = find_command("memory")
    assert cmd is not None
    assert cmd.name == "memory"
    assert "memory" in cmd.description.lower()


# -- /memory list ---------------------------------------------------------------


def test_memory_list_shows_stored_facts(tmp_path: Any, capsys: Any) -> None:
    harness, repl = _repl(tmp_path, capsys)
    _add_facts(harness, ("database config uses postgres", ["config"]))
    _add_facts(harness, ("parser bug at src/parser.py", ["bug"]))
    assert repl._slash_command("/memory list")
    out = capsys.readouterr().out
    assert "database config" in out
    assert "parser bug" in out
    assert "config" in out
    assert "bug" in out


def test_memory_list_empty_when_no_facts(tmp_path: Any, capsys: Any) -> None:
    _harness, repl = _repl(tmp_path, capsys)
    assert repl._slash_command("/memory list")
    out = capsys.readouterr().out
    assert "no" in out.lower() or "empty" in out.lower()


def test_memory_list_filtered_by_tag(tmp_path: Any, capsys: Any) -> None:
    harness, repl = _repl(tmp_path, capsys)
    _add_facts(harness, ("database config", ["config"]))
    _add_facts(harness, ("parser bug", ["bug"]))
    assert repl._slash_command("/memory list config")
    out = capsys.readouterr().out
    assert "database config" in out
    assert "parser bug" not in out


# -- /memory recall -------------------------------------------------------------


def test_memory_recall_search(tmp_path: Any, capsys: Any) -> None:
    harness, repl = _repl(tmp_path, capsys)
    _add_facts(harness, ("database URL is postgres://localhost", ["config"]))
    _add_facts(harness, ("how to make coffee", []))
    assert repl._slash_command("/memory recall database")
    out = capsys.readouterr().out
    assert "database" in out.lower()
    assert "coffee" not in out.lower()


def test_memory_recall_empty_query_shows_help(tmp_path: Any, capsys: Any) -> None:
    _harness, repl = _repl(tmp_path, capsys)
    assert repl._slash_command("/memory recall")
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "query" in out.lower() or "search" in out.lower()


# -- /memory clear --------------------------------------------------------------|


def test_memory_clear_removes_all_facts(tmp_path: Any, capsys: Any) -> None:
    harness, repl = _repl(tmp_path, capsys)
    _add_facts(harness, ("a fact", ["x"]))
    _add_facts(harness, ("another fact", ["y"]))
    assert repl._slash_command("/memory clear")
    # Memory should be empty after clear
    assert harness.memory_store.count() == 0


def test_memory_clear_when_empty(tmp_path: Any, capsys: Any) -> None:
    _harness, repl = _repl(tmp_path, capsys)
    assert repl._slash_command("/memory clear")
    out = capsys.readouterr().out
    assert "no" in out.lower() or "empty" in out.lower()


# -- /memory with no subcommand -------------------------------------------------


def test_memory_command_shows_help(tmp_path: Any, capsys: Any) -> None:
    _harness, repl = _repl(tmp_path, capsys)
    assert repl._slash_command("/memory")
    out = capsys.readouterr().out
    assert "list" in out.lower() or "recall" in out.lower() or "clear" in out.lower()
