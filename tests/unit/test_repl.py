"""Tests for the chat REPL logic (input loop mocked, harness is real)."""

from __future__ import annotations

import subprocess
from typing import Any

from om_harness.config.loader import Verbosity
from om_harness.harness import Harness
from om_harness.ui.repl import ChatRepl


def _repo(tmp_path: Any) -> Any:
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "x.py").write_text("x = 1\n")
    return tmp_path


def test_run_turn_records_messages_and_replies(tmp_path: Any, capsys: Any) -> None:
    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id, verbosity=Verbosity.verbose)

    repl.run_turn("what is in x.py?")

    out = capsys.readouterr().out
    assert "x = 1" not in out  # compact: mock echo replies with the goal text
    assert "[mock" in out
    loaded = harness.store.load_session(session.session_id)
    roles = [m.role.value for m in loaded.messages]
    assert roles == ["user", "assistant"]


def test_run_turn_survives_errors(tmp_path: Any, capsys: Any, monkeypatch: Any) -> None:
    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    async def boom(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("model exploded")

    monkeypatch.setattr(harness, "chat_turn", boom)
    repl.run_turn("hello")
    out = capsys.readouterr().out
    assert "turn failed" in out
    assert "model exploded" in out
