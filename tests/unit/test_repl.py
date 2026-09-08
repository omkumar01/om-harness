"""Tests for the chat REPL logic (input loop mocked, harness is real)."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import pytest

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


# -- live-stream robustness ----------------------------------------------------


def test_pump_survives_render_error(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    """A render exception must not kill the live stream or the turn."""
    import om_harness.ui.repl as repl_mod

    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id, verbosity=Verbosity.verbose)

    original = repl_mod.event_to_display
    calls = {"n": 0}

    def flaky(event: Any, verbosity: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("render boom")
        return original(event, verbosity)

    monkeypatch.setattr(repl_mod, "event_to_display", flaky)
    repl.run_turn("hello")
    out = capsys.readouterr().out
    assert "live stream interrupted" in out
    assert "turn failed" not in out
    assert "[mock" in out  # the turn itself completed


def test_error_path_still_flushes_events(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    """When chat_turn raises, events emitted before the failure are rendered."""
    from om_harness.models.events import EventType, make_event

    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id, verbosity=Verbosity.verbose)

    async def fail_midway(*args: Any, **kwargs: Any) -> str:
        harness.bus.publish_sync(
            make_event(
                EventType.PLAN_CREATED,
                session_id=repl.session_id,
                strategy="single",
                task_count=1,
                rationale="midway",
            )
        )
        raise RuntimeError("model exploded")

    monkeypatch.setattr(harness, "chat_turn", fail_midway)
    repl.run_turn("hello")
    out = capsys.readouterr().out
    assert "turn failed" in out
    assert "plan:" in out  # the event was not swallowed by the error path


def test_thinking_deltas_render_and_close_the_line(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    """Thinking deltas stream inline and the line is closed before the reply."""
    from om_harness.models.events import EventType, make_event

    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    async def stream_then_reply(*args: Any, **kwargs: Any) -> str:
        for chunk in ("think ", "more "):
            harness.bus.publish_sync(
                make_event(
                    EventType.MESSAGE_DELTA,
                    session_id=repl.session_id,
                    kind="thinking",
                    delta=chunk,
                )
            )
        return "the reply"

    monkeypatch.setattr(harness, "chat_turn", stream_then_reply)
    repl.run_turn("hello")
    out = capsys.readouterr().out
    assert "think more" in out
    assert "the reply" in out
    assert "no live stream" not in out  # deltas arrived, no diagnostic needed


# -- command display -----------------------------------------------------------


def _shell_turn_repl(tmp_path: Any, home: Any) -> ChatRepl:
    """A REPL whose scripted model runs one shell command then replies."""
    from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    harness = Harness(repo_root=_repo(tmp_path), env={}, approval_policy="auto")
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    async def respond(messages: Any, agent_info: Any) -> ModelResponse:
        saw = any(
            getattr(p, "part_kind", "") == "tool-return"
            for m in messages
            for p in getattr(m, "parts", [])
        )
        if not saw:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="run_shell",
                        args={"command": "echo om-command-ran"},
                        tool_call_id="c1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="ran it")])

    harness.runner.model_factory = lambda _s: FunctionModel(respond)
    return repl


def test_executed_command_rendered_with_collapsed_output(
    tmp_path: Any, home: Any, capsys: Any
) -> None:
    repl = _shell_turn_repl(tmp_path, home)
    repl.run_turn("run a command")
    out = capsys.readouterr().out
    assert "$" in out and "echo om-command-ran" in out
    assert "om-command-ran" in out  # preview line
    assert "Alt+O" in out  # collapsed-output affordance


def test_output_slash_command_expands_last_output(tmp_path: Any, home: Any, capsys: Any) -> None:
    repl = _shell_turn_repl(tmp_path, home)
    repl.run_turn("run a command")
    capsys.readouterr()
    assert repl._slash_command("/output")
    out = capsys.readouterr().out
    assert "echo om-command-ran" in out
    assert "om-command-ran" in out


def test_output_recording_caps_history(tmp_path: Any, home: Any, capsys: Any) -> None:
    from om_harness.models.events import EventType, make_event
    from om_harness.ui.repl import _COMMAND_HISTORY_MAX

    repl = _shell_turn_repl(tmp_path, home)
    for i in range(_COMMAND_HISTORY_MAX + 5):
        repl._render_event(
            make_event(
                EventType.TOOL_CALL_COMPLETED,
                session_id=repl.session_id,
                tool="run_shell",
                command=f"cmd-{i}",
                output=f"out-{i}",
                exit_code=0,
            )
        )
    assert len(repl._command_outputs) == _COMMAND_HISTORY_MAX
    assert repl._slash_command("/output")
    out = capsys.readouterr().out
    assert "cmd-24" in out  # newest command still listed


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


# -- skills and plugins slash commands -----------------------------------------


def _write_skill_file(skills_dir: Any, name: str, description: str) -> None:
    d = skills_dir / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nDo {name} things.\n",
        encoding="utf-8",
    )


def _skills_repl(tmp_path: Any, home: Any, monkeypatch: Any) -> tuple[ChatRepl, Harness]:
    skills_dir = tmp_path / "agent-skills"
    _write_skill_file(skills_dir, "analyse", "pick a method")
    monkeypatch.setenv("OM_HARNESS_SKILLS_DIR", str(skills_dir))
    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    return ChatRepl(harness, session_id=session.session_id), harness


def test_slash_skills_lists_discovered_skills(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    repl, _ = _skills_repl(tmp_path, home, monkeypatch)
    assert repl._slash_command("/skills")
    out = capsys.readouterr().out
    assert "analyse" in out
    assert "pick a method" in out


def test_slash_plugins_lists_installed_plugins(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    import subprocess

    origin = tmp_path / "demo-origin"
    (origin / "skills" / "demo-skill").mkdir(parents=True)
    (origin / "skills" / "demo-skill" / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: a demo skill\n---\nbody\n", encoding="utf-8"
    )
    (origin / "plugin.json").write_text(
        '{"name": "demo", "description": "demo plugin"}\n', encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=origin, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=origin,
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
    monkeypatch.delenv("OM_HARNESS_SKILLS_DIR", raising=False)

    from om_harness.plugins import install_plugin

    install_plugin(str(origin))

    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    assert repl._slash_command("/plugins")
    out = capsys.readouterr().out
    assert "demo" in out
    assert "demo-skill" in out
    # Plugin skills are active in the harness too.
    assert "demo:demo-skill" in repl.harness.skills


def test_slash_skill_runs_turn_for_known_skill(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    repl, harness = _skills_repl(tmp_path, home, monkeypatch)
    captured: dict[str, str] = {}

    async def fake_chat_turn(session_id: str, text: str, **kwargs: Any) -> str:
        captured["text"] = text
        return "did the thing"

    monkeypatch.setattr(harness, "chat_turn", fake_chat_turn)
    assert repl._slash_command("/skill analyse auth flow")
    assert "analyse" in captured["text"]
    assert "auth flow" in captured["text"]


def test_slash_skill_unknown_skill_is_handled(
    tmp_path: Any, home: Any, capsys: Any, monkeypatch: Any
) -> None:
    repl, _ = _skills_repl(tmp_path, home, monkeypatch)
    assert repl._slash_command("/skill nope")
    out = capsys.readouterr().out
    assert "nope" in out
    assert "analyse" in out  # hints at what is available


# -- pinned status bar during turns ---------------------------------------------

_REGION_SET = "\x1b[1;3r"  # 4-line test terminal: scroll region rows 1..H-1
_REGION_RESET = "\x1b[r"


def _pinned_repl(tmp_path: Any, monkeypatch: Any, *, lines: int = 4) -> ChatRepl:
    """A REPL whose pin path believes it is on a small VT terminal."""
    import om_harness.ui.repl as repl_mod

    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)
    monkeypatch.setattr(repl, "_stdout_is_tty", staticmethod(lambda: True))
    monkeypatch.setattr(repl_mod, "_enable_vt_output", lambda: (True, None))

    class FakeSize:
        def __init__(self, lines: int) -> None:
            self.lines = lines
            self.columns = 80

    monkeypatch.setattr(repl_mod.shutil, "get_terminal_size", lambda: FakeSize(lines))
    return repl


def test_run_turn_completes_with_bar_pinning_disabled(tmp_path: Any, capsys: Any) -> None:
    """Fallback path: no TTY / pinning off behaves exactly as before."""
    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)
    repl._pin_status_bar = False

    repl.run_turn("hello")

    out = capsys.readouterr().out
    assert "[mock" in out
    assert "\x1b" not in out  # no ANSI pin sequences leaked


def test_pinned_bar_reserves_bottom_row_during_turn(
    tmp_path: Any, capsys: Any, monkeypatch: Any
) -> None:
    """With pinning active, the turn runs inside a scroll region and the bar
    is drawn on the reserved bottom row; the turn result still comes back."""
    repl = _pinned_repl(tmp_path, monkeypatch)

    repl.run_turn("hello")

    out = capsys.readouterr().out
    assert "[mock" in out  # the turn itself completed
    assert _REGION_SET in out  # scrolling confined to rows 1..H-1
    assert "\x1b[4;1H" in out  # bar painted on the reserved row 4
    assert "provider" in out  # real status bar content
    assert out.index(_REGION_SET) < out.rindex(_REGION_RESET)  # reset after set
    assert out.count(_REGION_RESET) >= 1  # region released at teardown


def test_pinned_bar_redraws_on_tick(tmp_path: Any, capsys: Any, monkeypatch: Any) -> None:
    """The repaint loop redraws the bar while the turn is running."""
    import om_harness.ui.repl as repl_mod

    monkeypatch.setattr(repl_mod, "BAR_REFRESH_SECONDS", 0.01)
    repl = _pinned_repl(tmp_path, monkeypatch)

    async def scenario() -> None:
        async def slowish() -> str:
            await asyncio.sleep(0.08)
            return "ok"

        await repl._with_pinned_bar(asyncio.create_task(slowish()))

    asyncio.run(scenario())
    out = capsys.readouterr().out
    assert out.count("\x1b[4;1H") >= 2  # initial paint plus at least one tick


def test_pinned_bar_resets_region_on_cancellation(
    tmp_path: Any, capsys: Any, monkeypatch: Any
) -> None:
    """Cancelling the turn (Ctrl+C) still releases the scroll region."""
    repl = _pinned_repl(tmp_path, monkeypatch)

    async def scenario() -> None:
        async def sleepy() -> str:
            await asyncio.sleep(5)
            return "never"

        task = asyncio.create_task(sleepy())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await repl._with_pinned_bar(task)

    asyncio.run(scenario())
    assert repl is not None  # scenario completed without hanging
    out = capsys.readouterr().out
    assert _REGION_SET in out
    assert _REGION_RESET in out  # teardown ran on the cancellation path


def test_pinned_bar_falls_back_without_vt(tmp_path: Any, capsys: Any, monkeypatch: Any) -> None:
    """A terminal that cannot do VT sequences gets the plain await."""
    import om_harness.ui.repl as repl_mod

    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)
    monkeypatch.setattr(repl, "_stdout_is_tty", staticmethod(lambda: True))
    monkeypatch.setattr(repl_mod, "_enable_vt_output", lambda: (False, None))

    repl.run_turn("hello")

    out = capsys.readouterr().out
    assert "[mock" in out  # the turn itself completed
    assert _REGION_SET not in out  # no pin sequences were written


def test_cancelled_chat_turn_reports_interrupted(
    tmp_path: Any, capsys: Any, monkeypatch: Any
) -> None:
    harness = Harness(repo_root=_repo(tmp_path), env={})
    session = harness.sessions.create(repo_root=str(tmp_path))
    repl = ChatRepl(harness, session_id=session.session_id)

    async def cancelled(*args: Any, **kwargs: Any) -> str:
        raise asyncio.CancelledError()

    monkeypatch.setattr(harness, "chat_turn", cancelled)
    repl.run_turn("hello")
    assert "turn interrupted" in capsys.readouterr().out
