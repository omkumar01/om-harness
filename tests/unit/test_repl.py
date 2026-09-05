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


# -- slash commands -----------------------------------------------------------


def _repl(tmp_path: Any, home: Any) -> tuple[ChatRepl, Harness]:
    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    return ChatRepl(harness, session_id=session.session_id), harness


def test_slash_config_set_updates_and_persists(tmp_path: Any, home: Any, capsys: Any) -> None:
    repl, harness = _repl(tmp_path, home)
    assert repl._slash_command("/config set model openai:gpt-4o")
    assert harness.config.routing.default_model == "openai:gpt-4o"
    from om_harness.config.loader import load_config

    assert load_config(harness.repo_root, env={}).routing.default_model == "openai:gpt-4o"


def test_slash_model_selector_fallback(tmp_path: Any, home: Any, capsys: Any) -> None:
    """/model with no args opens the selector; without a TTY it no-ops safely."""
    repl, harness = _repl(tmp_path, home)
    assert repl._slash_command("/model")
    out = capsys.readouterr().out
    assert "model unchanged" in out  # selector can't open without a TTY
    assert harness.config.routing.default_model  # nothing broken


def test_slash_thinking_toggles_display(tmp_path: Any, home: Any, capsys: Any) -> None:
    repl, _ = _repl(tmp_path, home)
    assert repl.show_thinking is True  # on by default
    assert repl._slash_command("/thinking")
    assert repl.show_thinking is False
    assert "thinking display off" in capsys.readouterr().out


def test_slash_thinking_sets_level(tmp_path: Any, home: Any, capsys: Any) -> None:
    repl, harness = _repl(tmp_path, home)
    assert repl._slash_command("/thinking medium")
    assert harness.config.thinking == "medium"
    # Persisted to user config.
    from om_harness.config.loader import load_config

    assert load_config(harness.repo_root, env={}).thinking == "medium"


def test_slash_verbose_toggles(tmp_path: Any, home: Any) -> None:
    repl, _ = _repl(tmp_path, home)
    assert repl._slash_command("/verbose")
    assert repl.verbosity == Verbosity.verbose


def test_unknown_slash_returns_false(tmp_path: Any, home: Any, capsys: Any) -> None:
    repl, _ = _repl(tmp_path, home)
    assert repl._slash_command("/definitely-not-a-command") is False


def test_slash_checkpoint_saves(tmp_path: Any, home: Any, capsys: Any) -> None:
    repl, harness = _repl(tmp_path, home)
    repl.run_turn("hello")  # creates a run
    assert repl._slash_command("/checkpoint my-label")
    checkpoints = harness.store.list_checkpoints(repl.session_id)
    assert checkpoints


def test_turn_activity_summary_rendered(tmp_path: Any, home: Any, capsys: Any) -> None:
    """A turn whose scripted model edits a file shows the activity line."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    harness = Harness(repo_root=_repo(tmp_path), env={}, approval_policy="auto")
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        saw = any(
            getattr(p, "part_kind", "") == "tool-return"
            for m in messages
            for p in getattr(m, "parts", [])
        )
        if not saw:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="write_file",
                        args={"path": "new.txt", "content": "hi"},
                        tool_call_id="c1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="wrote the file")])

    harness.runner.model_factory = lambda _s: FunctionModel(respond)
    repl.run_turn("write new.txt please")
    out = capsys.readouterr().out
    assert "wrote new.txt" in out


def test_file_change_rendered_in_real_time(tmp_path: Any, home: Any, capsys: Any) -> None:
    """A write_file tool call renders a live change marker for the file."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    harness = Harness(repo_root=_repo(tmp_path), env={}, approval_policy="auto")
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        saw = any(
            getattr(p, "part_kind", "") == "tool-return"
            for m in messages
            for p in getattr(m, "parts", [])
        )
        if not saw:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="write_file",
                        args={"path": "brand-new.txt", "content": "hello"},
                        tool_call_id="c1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    harness.runner.model_factory = lambda _s: FunctionModel(respond)
    repl.run_turn("create brand-new.txt")
    out = capsys.readouterr().out
    assert "✎" in out
    assert "brand-new.txt" in out
    assert "new file" in out  # untracked file marker from git status


def test_diff_preview_shows_changes_for_tracked_file(tmp_path: Any, home: Any, capsys: Any) -> None:
    """A tracked, committed file that the agent edits shows + / - diff lines."""
    import subprocess

    harness = Harness(repo_root=_repo(tmp_path), env={}, approval_policy="auto")
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    # Commit x.py first so it is tracked, then overwrite it.
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True, shell=False)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        shell=False,
    )
    (tmp_path / "x.py").write_text("x = 2\n")

    repl._show_file_change("x.py")
    out = capsys.readouterr().out
    assert "✎" in out
    assert "x = 2" in out
    assert "+" in out
