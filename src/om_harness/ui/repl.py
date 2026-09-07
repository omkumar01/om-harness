"""Interactive shell for `om-harness` — Claude-Code-style, uniquely om.

One input box, always-on status line (model · thinking · mode · context
gauge), keybindings for everything, slash commands with autocomplete hints,
a model selector, and a guided /setup wizard. Turn logic reuses the Harness
facade exclusively — no runtime logic lives here.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass, field
from typing import Any

from rich.markup import escape
from rich.panel import Panel

from om_harness import __version__
from om_harness.config.loader import Verbosity
from om_harness.config.user_settings import SettingsError, apply_config_update
from om_harness.harness import Harness
from om_harness.models.events import Event, EventType
from om_harness.models.task import TokenUsage
from om_harness.ui.components import (
    DisplayLine,
    LineLevel,
    event_to_display,
    header_line,
    status_bar,
    turn_activity,
    welcome_panel,
)
from om_harness.ui.slash import (
    SlashCompleter,
    args_hint_for,
    cycle_approval,
    cycle_thinking,
    cycle_verbosity,
    mode_glyph,
    thinking_glyph,
)
from om_harness.ui.terminal import TerminalRenderer

EXIT_COMMANDS = {"exit", "quit", ":q", "q"}
PUMP_INTERVAL_SECONDS = 0.05
CONTEXT_BUDGET_TOKENS = 200_000  # gauge ceiling when no budget is configured

# Tools whose completions trigger a real-time file-change display.
_CHANGE_TOOLS = {"write_file", "edit_file"}

# Tools that execute commands; completions always render a command block with
# a collapsed output preview, regardless of verbosity (like file changes).
_COMMAND_TOOLS = {"run_shell", "run_tests"}
_COMMAND_HISTORY_MAX = 20  # commands kept for Alt+O / /output recall
_COMMAND_PREVIEW_LINES = 3  # tail lines shown in the collapsed block
_COMMAND_EXPAND_LINES = 300  # inline cap when Alt+O expands an output
_OUTPUT_PAGE_LINES = 50  # /output pages instead of printing above this

# Keybinding table: action -> candidate key groups. The first group whose
# key names are all valid for this platform wins. Note: Ctrl+M is physically
# the same key as Enter, so the model selector must never bind to it.
KEYBINDINGS: dict[str, tuple[tuple[str, ...], ...]] = {
    "submit": (("enter",),),
    "newline": (("escape", "enter"), ("c-j",)),
    "mode": (("s-tab",), ("backtab",)),
    "thinking": (("c-t",),),
    "verbosity": (("c-o",),),
    "model_selector": (("escape", "m"), ("f4",)),
    "command_output": (("escape", "o"), ("c-y",)),
    "help": (("c-g",),),
    "clear": (("c-l",),),
}


@dataclass
class _TurnStream:
    """Inline-stream state for one turn.

    Tracks both text (for reply de-duplication) and whether a partial line is
    currently open on the terminal — thinking deltas print with ``end=""`` and
    must be closed before any block output or the next prompt overdraws them.
    """

    text: list[str] = field(default_factory=list)
    line_open: bool = False
    delta_count: int = 0

    def joined(self) -> str:
        return "".join(self.text)


@dataclass
class CommandRun:
    """One executed command, kept so its output can be re-opened later."""

    command: str
    output: str
    exit_code: int | None = None
    failed: bool = False


class ChatRepl:
    def __init__(
        self,
        harness: Harness,
        *,
        session_id: str,
        verbosity: Verbosity = Verbosity.compact,
        renderer: TerminalRenderer | None = None,
    ) -> None:
        self.harness = harness
        self.session_id = session_id
        self.verbosity = verbosity
        self.show_thinking = True
        self.renderer = renderer or TerminalRenderer()
        self.total_usage = TokenUsage()
        self._last_ctrl_c = 0.0
        self._pending_paths: dict[str, str] = {}
        self._pending_commands: dict[str, str] = {}
        self._command_outputs: list[CommandRun] = []
        self._output_cursor = 0  # Alt+O cycles backwards through commands

    # -- state ----------------------------------------------------------------

    @property
    def model(self) -> str:
        return self.harness.config.routing.default_model

    @property
    def thinking(self) -> str:
        return self.harness.config.thinking.value

    @property
    def mode(self) -> str:
        return self.harness.config.approval.policy.value

    def _active(self) -> tuple[str, str]:
        """(provider, model) that the NEXT turn will actually use.

        Goes through the router, so it reflects /model selections, per-task
        routing, and any fallback when the configured model is unavailable.
        """
        from om_harness.models.task import TaskType

        try:
            model = self.harness.router.select(TaskType.general)
            provider = self.harness.provider_registry.resolve_model(model).provider
        except Exception:
            model = self.harness.config.routing.default_model
            provider = "—"
        return provider, model

    def _context_used(self) -> int:
        return self.total_usage.input_tokens

    def _context_max(self) -> int:
        configured = self.harness.config.budget.max_input_tokens
        return configured if configured else CONTEXT_BUDGET_TOKENS

    # -- main loop ------------------------------------------------------------

    def run_forever(self) -> None:  # pragma: no cover - interactive loop
        self._show_welcome()
        session = self._make_prompt_session()
        while True:
            try:
                text = session.prompt(
                    message=self._prompt_message(), bottom_toolbar=self._status_bar
                )
                self.renderer.console.print("╰" + "─" * 6 + "╯")
            except EOFError:
                self.renderer.info("bye")
                return
            except _ModelSelectorRequested:
                self._cmd_model_selector()
                continue
            except KeyboardInterrupt:
                now = time.monotonic()
                if now - self._last_ctrl_c < 2.0:
                    self.renderer.info("bye")
                    return
                self._last_ctrl_c = now
                self.renderer.line(
                    DisplayLine(level=LineLevel.dim, icon="·", text="press Ctrl+C again to quit")
                )
                continue
            if not text.strip():
                continue
            if text.strip().lower() in EXIT_COMMANDS:
                self.renderer.info("bye")
                return
            if text.startswith("/") and self._slash_command(text.strip()):
                continue
            self.run_turn(text)

    def _show_welcome(self) -> None:  # pragma: no cover - interactive
        registry = self.harness.provider_registry
        providers = [p.name for p in registry.available_providers() if p.available]
        providers += [n for n in registry.custom_provider_names if registry.is_available(n)]
        body = welcome_panel(__version__, self.model, providers, first_run=False)
        self.renderer.console.print(
            Panel(body, border_style="cyan", padding=(0, 2), title="✦", title_align="left")
        )

    def _make_prompt_session(self) -> Any:  # pragma: no cover - TTY wiring
        """PromptSession with keybindings, completer, and live status bar.

        If prompt_toolkit cannot attach to this terminal, the reason is
        reported once and we fall back to a plain prompt that still shows
        the boxed header and status line before every input. On Windows a
        stray ``TERM`` environment variable (inherited from Git Bash, often
        set by shell prompts) breaks console detection, so construction is
        retried once with it cleared.
        """
        import os

        try:
            return self._build_prompt_session()
        except Exception as first_error:
            reason = str(first_error) or type(first_error).__name__
            saved_term = os.environ.get("TERM")
            if saved_term:
                os.environ.pop("TERM")
                try:
                    return self._build_prompt_session()
                except Exception as second_error:
                    reason = str(second_error) or type(second_error).__name__
                finally:
                    os.environ["TERM"] = saved_term
            self.renderer.line(
                DisplayLine(
                    level=LineLevel.warn,
                    icon="⚠",
                    text=f"rich terminal unavailable ({reason}) — falling back to "
                    "basic input; keybindings and the pinned footer are disabled",
                )
            )
            return _PlainSession(self)

    def _build_prompt_session(self) -> Any:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
        from prompt_toolkit.key_binding import KeyBindings

        kb = KeyBindings()
        repl = self

        def bind(groups: Any, func: Any) -> None:
            """Register a binding under the first valid key name.

            Key names differ across prompt_toolkit versions and platforms
            (e.g. Shift+Tab is 's-tab' here but 'backtab' elsewhere); one
            invalid key must never abort building the whole session.
            """
            if isinstance(groups, str):
                groups = (groups,)
            for group in groups:
                keys = tuple(group) if isinstance(group, (tuple, list)) else (group,)
                try:
                    kb.add(*keys)(func)
                    return
                except (KeyError, ValueError):
                    continue  # invalid key name on this platform: try next alias

        def _submit(event: Any) -> None:
            buffer = event.current_buffer
            if buffer.text.endswith("\\"):
                buffer.delete_before_cursor(1)
                buffer.insert_text("\n")
            else:
                buffer.validate_and_handle()

        def _newline(event: Any) -> None:
            event.current_buffer.insert_text("\n")

        def _mode(event: Any) -> None:
            from om_harness.config.loader import ApprovalPolicy

            repl.harness.config.approval.policy = ApprovalPolicy(cycle_approval(repl.mode))
            event.app.invalidate()

        def _thinking(event: Any) -> None:
            with contextlib.suppress(SettingsError):
                apply_config_update(repl.harness, "thinking", cycle_thinking(repl.thinking))
            event.app.invalidate()

        def _verbosity(event: Any) -> None:
            repl.verbosity = Verbosity(cycle_verbosity(repl.verbosity.value))
            event.app.invalidate()

        def _selector(event: Any) -> None:
            event.app.exit(exception=_ModelSelectorRequested(), style="class:aborting")

        def _help(event: Any) -> None:
            repl._cmd_help()
            event.app.invalidate()

        def _clear(event: Any) -> None:
            event.app.renderer.clear()

        def _command_output(event: Any) -> None:
            repl._cmd_output([])
            event.app.invalidate()

        handlers: dict[str, Any] = {
            "submit": _submit,
            "newline": _newline,
            "mode": _mode,
            "thinking": _thinking,
            "verbosity": _verbosity,
            "model_selector": _selector,
            "command_output": _command_output,
            "help": _help,
            "clear": _clear,
        }
        for action, groups in KEYBINDINGS.items():
            bind(groups, handlers[action])

        return PromptSession(
            completer=SlashCompleter(self),
            complete_while_typing=True,
            auto_suggest=AutoSuggestFromHistory(),
            key_bindings=kb,
        )

    # The prompt message and status bar are rebuilt on every iteration so the
    # boxed header always shows the live provider / model / mode / thinking.

    def _prompt_message(self) -> str:
        provider, model = self._active()
        header = header_line(provider, model, mode_glyph(self.mode), thinking_glyph(self.thinking))
        return header + "\n│ ❯ "

    def _status_bar(self) -> str:
        try:
            hint = self._typing_hint()
            provider, model = self._active()
            return status_bar(
                provider,
                model,
                self.thinking,
                mode_glyph(self.mode),
                self._context_used(),
                self._context_max(),
                hint=hint,
            )
        except Exception:
            return "om-harness"

    def _typing_hint(self) -> str | None:
        # Live buffer text (so slash hints appear while typing). Outside the
        # prompt_toolkit app (tests, piped input) there is no buffer.
        try:
            from prompt_toolkit.application import get_app_or_none

            app = get_app_or_none()
            text = app.current_buffer.text if app is not None else ""
        except Exception:
            text = ""
        if not text.startswith("/"):
            return None
        model_names = [name for name, _label in self._model_names()]
        return args_hint_for(text, model_names)

    def _model_names(self) -> list[tuple[str, str]]:
        try:
            from om_harness.config.user_settings import available_model_strings

            return available_model_strings(self.harness)
        except Exception:
            return []

    # -- turns ---------------------------------------------------------------

    def run_turn(self, text: str) -> None:
        """One user turn: live-render events and stream the reply."""
        # Seq cursor into the bus (not a positional offset): history is a
        # bounded deque, so positional slicing goes dead once it evicts.
        cursor = self.harness.bus.cursor
        rendered: set[str] = set()
        stream = _TurnStream()
        self._output_cursor = len(self._command_outputs)

        async def _turn() -> str:
            pump = asyncio.create_task(self._pump(cursor_holder, rendered, stream))
            try:
                return await self.harness.chat_turn(self.session_id, text)
            finally:
                # Cancel, then let the pump finish its in-flight pass so
                # deltas emitted in the final tick render in-stream instead
                # of bursting after the turn.
                pump.cancel()
                try:
                    await pump
                except asyncio.CancelledError:
                    task = asyncio.current_task()
                    if task is not None and task.cancelling():
                        raise  # the turn itself was cancelled, not just the pump
                except Exception as exc:
                    self._stream_warning(exc)

        cursor_holder = [cursor]
        error: Exception | None = None
        interrupted = False
        reply: str | None = None
        try:
            reply = asyncio.run(_turn())
        except (KeyboardInterrupt, asyncio.CancelledError):
            interrupted = True
        except Exception as exc:
            error = exc
        finally:
            # Render anything the pump missed, on EVERY exit path — the error
            # and interrupt paths must not swallow late deltas or diffs.
            for event in self.harness.bus.since(cursor_holder[0]):
                if event.id not in rendered:
                    rendered.add(event.id)
                    try:
                        self._render_event(event, stream)
                    except Exception as exc:
                        self._stream_warning(exc)
            self._close_stream_line(stream)

        if interrupted:
            self.renderer.line(DisplayLine(level=LineLevel.warn, icon="⏹", text="turn interrupted"))
            return
        if error is not None:
            self.renderer.error(f"turn failed: {error}")
            return

        streamed_text = stream.joined()
        if not streamed_text or streamed_text != (reply or ""):
            self.renderer.console.print(f"[green]om[/] {escape(reply or '')}")
        if stream.delta_count == 0:
            self.renderer.line(
                DisplayLine(
                    level=LineLevel.dim,
                    icon="·",
                    text="no live stream this turn — model streaming unavailable or thinking off",
                )
            )

        segment = self.harness.bus.since(cursor)
        activity = turn_activity(segment)
        self.total_usage = self.total_usage.add(
            TokenUsage(input_tokens=activity.input_tokens, output_tokens=activity.output_tokens)
        )
        line = activity.summary_line()
        if line != "no tool activity":
            self.renderer.line(DisplayLine(level=LineLevel.dim, icon="◇", text=line))
        # Always-on status in the text flow (visible even without a toolbar).
        provider, model = self._active()
        self.renderer.line(
            DisplayLine(
                level=LineLevel.dim,
                icon="▁",
                text=status_bar(
                    provider,
                    model,
                    self.thinking,
                    mode_glyph(self.mode),
                    self._context_used(),
                    self._context_max(),
                ),
            )
        )

    def _stream_warning(self, exc: Exception) -> None:
        """Report a live-stream failure without ending the turn."""
        with contextlib.suppress(Exception):
            self.renderer.line(
                DisplayLine(
                    level=LineLevel.warn,
                    icon="⚠",
                    text=f"live stream interrupted: {exc}",
                )
            )

    def _close_stream_line(self, stream: _TurnStream | None) -> None:
        """Terminate an open partial line (text/thinking printed with end="")."""
        if stream is not None and stream.line_open:
            self.renderer.console.print()
            stream.line_open = False

    def _flush_console(self) -> None:
        """Flush partial (end="") writes to the terminal.

        Rich only auto-flushes on newline; without this, deltas can sit in
        the buffer and the stream appears to stall. Rich 15 dropped
        ``Console.flush()``, so flush the underlying file.
        """
        with contextlib.suppress(Exception):
            self.renderer.console.file.flush()

    async def _pump(
        self, cursor_holder: list[int], rendered: set[str], stream: _TurnStream
    ) -> None:
        """Live-render new events while the turn runs (polling drain)."""
        while True:
            new = self.harness.bus.since(cursor_holder[0])
            if new:
                cursor_holder[0] = new[-1].seq
                for event in new:
                    if event.id in rendered:
                        continue
                    rendered.add(event.id)
                    try:
                        self._render_event(event, stream)
                    except Exception as exc:
                        # One bad event must never kill the live stream.
                        self._stream_warning(exc)
            await asyncio.sleep(PUMP_INTERVAL_SECONDS)

    def _render_event(self, event: Event, stream: _TurnStream | None = None) -> None:
        # File changes and executed commands are always shown in real time,
        # regardless of verbosity.
        if event.type == EventType.TOOL_CALL_STARTED:
            tool = event.data.get("tool")
            arguments = event.data.get("arguments") or {}
            if tool in _CHANGE_TOOLS and isinstance(arguments.get("path"), str):
                self._pending_paths[tool] = arguments["path"]
            if tool in _COMMAND_TOOLS and isinstance(arguments.get("command"), str):
                self._pending_commands[tool] = arguments["command"]
        elif event.type in (EventType.TOOL_CALL_COMPLETED, EventType.TOOL_CALL_FAILED):
            tool = event.data.get("tool") or ""
            if (
                event.type == EventType.TOOL_CALL_COMPLETED
                and tool in _CHANGE_TOOLS
                and event.data.get("ok", True)
            ):
                path = event.data.get("path") or self._pending_paths.pop(tool, None)
                self._close_stream_line(stream)
                self._show_file_change(path)
                return
            self._pending_paths.pop(tool, None)
            if tool in _COMMAND_TOOLS:
                self._close_stream_line(stream)
                if self._show_command(event):
                    return
        if event.type == EventType.MESSAGE_DELTA:
            kind = event.data.get("kind")
            delta = event.data.get("delta") or ""
            if kind == "text" and delta:
                self.renderer.console.print(f"[green]{escape(delta)}[/]", end="")
                self._flush_console()
                if stream is not None:
                    stream.text.append(delta)
                    stream.line_open = True
                    stream.delta_count += 1
            elif self.show_thinking and kind == "thinking" and delta:
                self.renderer.console.print(f"[dim italic]{escape(delta)}[/]", end="")
                self._flush_console()
                if stream is not None:
                    stream.line_open = True
                    stream.delta_count += 1
            return
        display = event_to_display(event, self.verbosity)
        if display is not None:
            self._close_stream_line(stream)
            self.renderer.line(display)

    # -- real-time file-change rendering --------------------------------------

    def _show_file_change(self, path: str | None) -> None:
        """Render a live diff/status for a file the agent just changed."""
        if not path:
            return
        self.renderer.console.print(f"[yellow]✎[/] [bold]{escape(path)}[/]")
        diff = self._diff_preview(path)
        if diff:
            for line in diff.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    self.renderer.console.print(f"[green]{escape(line)}[/]")
                elif line.startswith("-") and not line.startswith("---"):
                    self.renderer.console.print(f"[red]{escape(line)}[/]")
                elif line.startswith("@@"):
                    self.renderer.console.print(f"[dim]{escape(line)}[/]")
                else:
                    self.renderer.console.print(f"[dim]{escape(line)}[/]")

    def _diff_preview(self, path: str, max_lines: int = 16) -> str | None:
        """Short git diff for a changed file; falls back to new-file marker."""
        import subprocess

        try:
            proc = subprocess.run(
                ["git", "diff", "--unified=0", "--", path],
                cwd=str(self.harness.repo_root),
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            if proc.returncode != 0:
                return None
            if proc.stdout.strip():
                lines = [
                    line
                    for line in proc.stdout.splitlines()
                    if not line.startswith(("diff ", "index ", "--- ", "+++ "))
                ]
                preview = lines[:max_lines]
                if len(lines) > max_lines:
                    preview.append(f"... +{len(lines) - max_lines} more diff lines")
                return "\n".join(preview)
            status = subprocess.run(
                ["git", "status", "--porcelain", "--", path],
                cwd=str(self.harness.repo_root),
                capture_output=True,
                text=True,
                timeout=5,
                shell=False,
            )
            if status.stdout.strip().startswith("??"):
                return "(new file — not yet tracked)"
        except Exception:
            return None
        return None

    # -- real-time command rendering ------------------------------------------

    def _show_command(self, event: Event) -> bool:
        """Render an executed command with a collapsed output preview.

        Returns True if a command block was rendered. Commands are shown in
        every verbosity mode, like file changes.
        """
        data = event.data
        tool = data.get("tool") or ""
        failed = event.type == EventType.TOOL_CALL_FAILED
        command = data.get("command")
        if not isinstance(command, str) or not command:
            command = self._pending_commands.pop(tool, None)
            if not command:
                return False
        else:
            self._pending_commands.pop(tool, None)
        output = data.get("output")
        output = output if isinstance(output, str) else ""
        exit_code = data.get("exit_code")
        exit_code = exit_code if isinstance(exit_code, int) else None

        self._command_outputs.append(
            CommandRun(command=command, output=output, exit_code=exit_code, failed=failed)
        )
        if len(self._command_outputs) > _COMMAND_HISTORY_MAX:
            del self._command_outputs[:-_COMMAND_HISTORY_MAX]

        console = self.renderer.console
        if failed:
            status = "[red]failed[/]"
        elif exit_code is None:
            status = ""
        else:
            status = f"[dim]exit {exit_code}[/]" if exit_code == 0 else f"[red]exit {exit_code}[/]"
        head = f"[bold]⚙ ${escape(command)}[/]"
        if status:
            head += f"  {status}"
        console.print(head)

        if failed and data.get("error"):
            console.print(f"[red]{escape(str(data['error']))}[/]")
        lines = output.splitlines() if output else []
        if lines:
            for line in lines[-_COMMAND_PREVIEW_LINES:]:
                console.print(f"[dim]│ {escape(line)}[/]")
        else:
            console.print("[dim]│ (no output)[/]")
        hidden = max(0, len(lines) - _COMMAND_PREVIEW_LINES)
        if hidden:
            console.print(f"[dim]╵ ⋯ +{hidden} earlier lines — Alt+O output · /output to page[/]")
        else:
            console.print("[dim]╵ Alt+O output · /output to page[/]")
        return True

    def _print_command_output(self, run: CommandRun) -> None:
        """Re-print a recorded command's output inline, capped."""
        console = self.renderer.console
        console.print(f"[bold]⚙ ${escape(run.command)}[/]")
        lines = run.output.splitlines() if run.output else ["(no output)"]
        for line in lines[:_COMMAND_EXPAND_LINES]:
            console.print(f"[dim]│ {escape(line)}[/]")
        if len(lines) > _COMMAND_EXPAND_LINES:
            console.print(
                f"[dim]╵ … +{len(lines) - _COMMAND_EXPAND_LINES} more lines — /output to page[/]"
            )

    def _cmd_output(self, args: list[str]) -> None:
        """Alt+O handler and /output command: re-open executed command output.

        With no args, expand the most recent command (repeated presses cycle
        backwards); ``/output <n>`` shows that command, paging if long.
        """
        runs = self._command_outputs
        if not runs:
            self.renderer.info("no commands executed yet this session")
            return
        if not args:
            if self._output_cursor <= 0:
                self._output_cursor = len(runs)
            run = runs[self._output_cursor - 1]
            self._output_cursor -= 1
            self._print_command_output(run)
            return
        try:
            index = int(args[0])
        except ValueError:
            self.renderer.error("usage: /output [n]")
            return
        if not 1 <= index <= len(runs):
            self.renderer.error(f"no command {index} — /output lists 1..{len(runs)}")
            return
        run = runs[index - 1]
        lines = run.output.splitlines() if run.output else ["(no output)"]
        if len(lines) > _OUTPUT_PAGE_LINES:
            import pydoc

            self.renderer.console.print(f"[bold]⚙ ${escape(run.command)}[/]")
            pydoc.pager("\n".join(lines))
        else:
            self._print_command_output(run)

    # -- slash commands ------------------------------------------------------

    def _slash_command(self, text: str) -> bool:
        """Handle a /command; returns False if it should go to the agent."""
        parts = text[1:].split()
        command, args = parts[0].lower(), parts[1:]

        if command in EXIT_COMMANDS:
            raise EOFError
        if command == "help":
            self._cmd_help()
        elif command == "model":
            if args:
                self._cmd_model(args[0])
            else:
                self._cmd_model_selector()
        elif command == "thinking":
            if args:
                self._set_thinking(args[0])
            else:
                self.show_thinking = not self.show_thinking
                state = "on — reasoning streams live" if self.show_thinking else "off"
                self.renderer.info(
                    f"thinking display {state} (model level: {self.thinking}; "
                    "/thinking <level> or Ctrl+T changes it)"
                )
        elif command == "mode":
            from om_harness.config.loader import ApprovalPolicy

            self.harness.config.approval.policy = ApprovalPolicy(cycle_approval(self.mode))
            self.renderer.info(f"approval mode: {mode_glyph(self.mode)}")
        elif command == "config":
            self._cmd_config(args)
        elif command == "timeout":
            self._cmd_timeout(args)
        elif command == "providers":
            self._cmd_providers()
        elif command == "checkpoint":
            self._cmd_checkpoint(args[0] if args else "")
        elif command == "sessions":
            self._cmd_sessions()
        elif command == "setup":
            self._cmd_setup()
        elif command == "verbose":
            self.verbosity = Verbosity(cycle_verbosity(self.verbosity.value))
            self.renderer.info(f"verbosity: {self.verbosity.value}")
        elif command == "tools":
            self._cmd_tools()
        elif command == "skills":
            self._cmd_skills()
        elif command == "skill":
            self._cmd_skill(args)
        elif command == "plugins":
            self._cmd_plugins()
        elif command == "status":
            self._cmd_status()
        elif command == "output":
            self._cmd_output(args)
        else:
            self.renderer.error(f"unknown command /{command} — try /help (or send it as a message)")
            return False
        return True

    def _cmd_help(self) -> None:
        self.renderer.info(
            "commands: "
            + "  ".join(
                f"/{c}"
                for c in (
                    "model",
                    "thinking",
                    "mode",
                    "config",
                    "timeout",
                    "providers",
                    "tools",
                    "skills",
                    "skill",
                    "plugins",
                    "status",
                    "sessions",
                    "checkpoint",
                    "setup",
                    "verbose",
                    "output",
                    "help",
                    "exit",
                )
            )
        )
        self.renderer.line(
            DisplayLine(
                level=LineLevel.dim,
                icon="·",
                text="keys: ⇧Tab mode · alt+M model · ^T thinking · ^O verbose"
                " · ⌥O output · ^G help",
            )
        )
        self.renderer.line(
            DisplayLine(
                level=LineLevel.dim,
                icon="·",
                text="/config set keys: model, thinking, approval, verbosity, "
                "max_concurrency, max_requests, agent_timeout, tool_timeout, "
                "task_model.<type>",
            )
        )

    def _cmd_model(self, name: str) -> None:
        try:
            message = apply_config_update(self.harness, "model", name)
        except SettingsError as exc:
            self.renderer.error(str(exc))
            return
        self.renderer.info(message)

    def _set_thinking(self, level: str) -> None:
        try:
            message = apply_config_update(self.harness, "thinking", level)
        except SettingsError as exc:
            self.renderer.error(str(exc))
            return
        self.renderer.info(message)

    def _cmd_model_selector(self) -> None:  # pragma: no cover - TTY dialog
        """Arrow-key model picker; falls back gracefully without a TTY."""
        from om_harness.config.user_settings import apply_model, available_model_strings

        options = available_model_strings(self.harness)
        if not options:
            self.renderer.error("no models available — run /setup")
            return
        values = [(name, f"{name}  ({label})") for name, label in options]
        try:
            from prompt_toolkit.shortcuts import radiolist_dialog

            chosen = radiolist_dialog(
                title="✦ select model",
                text="Arrow keys to move, Enter to select, Esc to cancel.",
                values=values,
                default=self.model if self.model in dict(values) else values[0][0],
            ).run()
        except Exception:
            chosen = None
        if not chosen:
            self.renderer.line(DisplayLine(level=LineLevel.dim, icon="·", text="model unchanged"))
            return
        try:
            self.renderer.info(apply_model(self.harness, chosen))
        except SettingsError as exc:
            self.renderer.error(str(exc))

    def _cmd_config(self, args: list[str]) -> None:
        if not args:
            for key, value in self.harness.config.model_dump(mode="json").items():
                self.renderer.console.print(f"[bold]{key}:[/] {value}")
            return
        if args[0] == "set" and len(args) >= 3:
            key, value = args[1], args[2]
            try:
                message = apply_config_update(self.harness, key, value)
            except SettingsError as exc:
                self.renderer.error(str(exc))
                return
            self.renderer.info(f"{message} · saved to ~/.om-harness/config/config.toml")
            return
        self.renderer.error("usage: /config  or  /config set <key> <value>")

    def _cmd_timeout(self, args: list[str]) -> None:
        def _fmt(seconds: float | None) -> str:
            return "off" if seconds is None else f"{seconds:g}s"

        if not args:
            config = self.harness.config
            self.renderer.info(
                f"agent timeout: {_fmt(config.agent_timeout_seconds)} · "
                f"tool timeout: {_fmt(config.tool_timeout_seconds)} "
                "(/timeout agent|tool <seconds|off>, or /timeout off to disable both)"
            )
            return
        if args[0].lower() == "off" and len(args) == 1:
            keys = ("agent_timeout", "tool_timeout")
        elif args[0].lower() in ("agent", "tool") and len(args) == 2:
            keys = (f"{args[0].lower()}_timeout",)
        else:
            self.renderer.error("usage: /timeout  |  /timeout off  |  /timeout agent|tool <seconds|off>")
            return
        for key in keys:
            try:
                self.renderer.info(apply_config_update(self.harness, key, args[-1]))
            except SettingsError as exc:
                self.renderer.error(str(exc))
                return

    def _cmd_providers(self) -> None:
        for info in self.harness.provider_registry.available_providers():
            state = "available" if info.available else "no API key"
            self.renderer.console.print(f"{info.name:12} {state}  default: {info.default_model}")
        for custom in self.harness.provider_registry.custom_provider_summaries():
            state = "available" if custom["available"] else "unavailable"
            self.renderer.console.print(f"{custom['name']:12} {state}  ({custom['api']})")
            for model in custom["models"]:
                self.renderer.console.print(f"  {custom['name']}:{model['id']}")

    def _cmd_tools(self) -> None:
        for spec in self.harness.registry.specs():
            self.renderer.line(
                DisplayLine(
                    level=LineLevel.dim,
                    icon="·",
                    text=f"{spec['name']} ({spec['permission']}): {spec['description']}",
                )
            )

    def _cmd_skills(self) -> None:
        if not self.harness.skills:
            self.renderer.info("no skills installed (~/.agents/skills or repo .agents/skills)")
            return
        for skill in self.harness.skills.values():
            hint = f" [args: {skill.argument_hint}]" if skill.argument_hint else ""
            self.renderer.line(
                DisplayLine(
                    level=LineLevel.info,
                    icon="·",
                    text=f"{skill.name} [{skill.source}]{hint}: {skill.description}",
                )
            )

    def _cmd_plugins(self) -> None:
        from om_harness.plugins import load_plugins

        installed = load_plugins()
        if not installed:
            self.renderer.info(
                "no plugins installed — try: om-harness install git:github.com/<owner>/<repo>"
            )
            return
        for plugin in installed:
            self.renderer.line(
                DisplayLine(
                    level=LineLevel.info,
                    icon="·",
                    text=f"{plugin.name} ({len(plugin.skills)} skills): {plugin.description}",
                )
            )
            for skill in plugin.skills:
                self.renderer.line(
                    DisplayLine(
                        level=LineLevel.dim, icon="·", text=f"{skill.name}: {skill.description}"
                    )
                )

    def _cmd_skill(self, args: list[str]) -> None:
        if not args:
            self.renderer.error("usage: /skill <name> [args] — see /skills")
            return
        name = args[0]
        if name not in self.harness.skills:
            available = ", ".join(sorted(self.harness.skills)) or "(none)"
            self.renderer.error(f"unknown skill {name!r} — available: {available}")
            return
        extra = " ".join(args[1:])
        prompt = (
            f"Load the skill {name!r} with the skill tool and follow its "
            "instructions to handle this request."
        )
        if extra:
            prompt += f" Arguments/context: {extra}"
        self.run_turn(prompt)

    def _cmd_status(self) -> None:
        for key, value in self.harness.status().items():
            self.renderer.console.print(f"[dim]{key}: {value}[/]")

    def _cmd_sessions(self) -> None:
        for session in self.harness.sessions.list_sessions()[:10]:
            self.renderer.console.print(
                f"{session.session_id}  {session.status.value}  "
                f"{len(session.messages)} msgs, {len(session.runs)} runs  "
                f"repo: {session.repo_root}"
            )

    def _cmd_checkpoint(self, label: str) -> None:
        session = self.harness.sessions.load(self.session_id)
        if not session.runs:
            self.renderer.error("nothing to checkpoint yet")
            return
        run = session.runs[-1]
        checkpoint = self.harness.sessions.save_checkpoint(
            session,
            run,
            label=label or f"manual-{len(session.runs)}",
            summary=f"manual checkpoint after {len(session.messages)} messages",
        )
        self.renderer.info(f"checkpoint saved: {checkpoint.checkpoint_id}")

    # -- /setup wizard -------------------------------------------------------

    def _cmd_setup(self) -> None:  # pragma: no cover - TTY wizard
        """Guided configuration: provider → model → mode → verbosity → thinking."""
        if not self._setup_provider():
            return
        self._cmd_model_selector()
        self._setup_choice(
            "approval mode",
            ("ask", "auto", "deny"),
            self.mode,
            lambda v: apply_config_update(self.harness, "approval", v),
        )
        self._setup_choice(
            "verbosity",
            ("compact", "verbose", "debug"),
            self.verbosity.value,
            lambda v: apply_config_update(self.harness, "verbosity", v),
        )
        self._setup_choice(
            "thinking level",
            tuple(level.value for level in self._thinking_levels()),
            self.thinking,
            lambda v: apply_config_update(self.harness, "thinking", v),
        )
        self.renderer.info("setup complete — settings persisted to ~/.om-harness/")

    @staticmethod
    def _thinking_levels() -> list[Any]:
        from om_harness.config.loader import ThinkingLevel

        return list(ThinkingLevel)

    def _setup_choice(
        self, title: str, options: tuple[str, ...], current: str, apply: Any
    ) -> None:  # pragma: no cover - TTY dialog
        try:
            from prompt_toolkit.shortcuts import radiolist_dialog

            chosen = radiolist_dialog(
                title=f"✦ {title}",
                values=[(o, o) for o in options],
                default=current if current in options else options[0],
            ).run()
        except Exception:
            chosen = None
        if not chosen:
            return
        try:
            self.renderer.info(apply(chosen))
        except SettingsError as exc:
            self.renderer.error(str(exc))

    def _setup_provider(self) -> bool:  # pragma: no cover - TTY wizard
        """Optionally add a custom OpenAI-compatible provider. True to continue."""
        self.renderer.line(
            DisplayLine(
                level=LineLevel.dim,
                icon="·",
                text="providers with env keys are detected automatically; "
                "add a custom endpoint (LM Studio, NVIDIA, …) if you like",
            )
        )
        try:
            from prompt_toolkit.shortcuts import confirm, input_dialog

            if not confirm(message="Add an OpenAI-compatible endpoint?"):
                return True
            name = input_dialog(title="provider name", text="e.g. lm-studio").run()
            if not name:
                return True
            base_url = input_dialog(title="base URL", text="e.g. http://127.0.0.1:8080/v1").run()
            if not base_url:
                return True
            api_key_env = input_dialog(
                title="API key env var", text="env var name (empty for local gateways)"
            ).run()
            allow = confirm(message="Is this a local/private endpoint (127.0.0.1, 192.168.x…)?")
            from om_harness.config.user_settings import add_custom_provider

            self.renderer.info(
                add_custom_provider(
                    name=name.strip(),
                    base_url=base_url.strip(),
                    api="openai-completions",
                    api_key_env=(api_key_env or "").strip() or None,
                    allow_local=bool(allow),
                )
            )
            return True
        except Exception as exc:
            self.renderer.error(f"setup provider step skipped: {exc}")
            return True


class _ModelSelectorRequested(Exception):
    """Internal signal: Ctrl+M pressed inside the prompt."""


class _PlainSession:
    """Fallback prompt for terminals where prompt_toolkit cannot attach.

    Still prints the boxed header and the full status line before every
    input, so the provider/model/mode/thinking footer stays visible even
    without a rich terminal.
    """

    def __init__(self, repl: ChatRepl | None = None) -> None:
        self.repl = repl

    def prompt(self, **kwargs: Any) -> str:
        if self.repl is not None:
            try:
                self.repl.renderer.console.print(self.repl._prompt_message())
                bar = self.repl._status_bar()
                self.repl.renderer.console.print(f"[dim]{escape(bar)}[/]")
            except Exception:
                pass
        return input("om> ")
