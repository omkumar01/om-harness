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
    "help": (("c-g",),),
    "clear": (("c-l",),),
}


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
        self.show_thinking = False
        self.renderer = renderer or TerminalRenderer()
        self.total_usage = TokenUsage()
        self._last_ctrl_c = 0.0

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

        handlers: dict[str, Any] = {
            "submit": _submit,
            "newline": _newline,
            "mode": _mode,
            "thinking": _thinking,
            "verbosity": _verbosity,
            "model_selector": _selector,
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
        offset = len(self.harness.bus.history)
        rendered: set[str] = set()
        streamed: list[str] = []

        async def _turn() -> str:
            pump = asyncio.create_task(self._pump(offset_holder, rendered, streamed))
            try:
                return await self.harness.chat_turn(self.session_id, text)
            finally:
                pump.cancel()

        offset_holder = [offset]
        try:
            reply = asyncio.run(_turn())
        except (KeyboardInterrupt, asyncio.CancelledError):
            for event in self.harness.bus.history[offset_holder[0] :]:
                if event.id not in rendered:
                    rendered.add(event.id)
                    self._render_event(event)
            self.renderer.console.print()
            self.renderer.line(DisplayLine(level=LineLevel.warn, icon="⏹", text="turn interrupted"))
            return
        except Exception as exc:
            self.renderer.error(f"turn failed: {exc}")
            return
        # Render anything the pump missed before it was cancelled.
        for event in self.harness.bus.history[offset_holder[0] :]:
            if event.id not in rendered:
                rendered.add(event.id)
                self._render_event(event, streamed)
        streamed_text = "".join(streamed)
        if streamed_text:
            self.renderer.console.print()  # close the streamed line
            if streamed_text != reply:
                self.renderer.console.print(f"[green]om[/] {escape(reply)}")
        else:
            self.renderer.console.print(f"[green]om[/] {escape(reply)}")

        segment = self.harness.bus.history[offset:]
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

    async def _pump(
        self, offset_holder: list[int], rendered: set[str], streamed: list[str]
    ) -> None:
        """Live-render new events while the turn runs (polling drain)."""
        try:
            while True:
                history = self.harness.bus.history
                new = history[offset_holder[0] :]
                if new:
                    offset_holder[0] += len(new)
                    for event in new:
                        if event.id not in rendered:
                            rendered.add(event.id)
                            self._render_event(event, streamed)
                await asyncio.sleep(PUMP_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise

    def _render_event(self, event: Event, streamed: list[str] | None = None) -> None:
        if event.type == EventType.MESSAGE_DELTA:
            kind = event.data.get("kind")
            delta = event.data.get("delta") or ""
            if kind == "text" and delta:
                self.renderer.console.print(f"[green]{escape(delta)}[/]", end="")
                if streamed is not None:
                    streamed.append(delta)
            elif self.show_thinking and kind == "thinking" and delta:
                self.renderer.console.print(f"[dim italic]{escape(delta)}[/]", end="")
            return
        display = event_to_display(event, self.verbosity)
        if display is not None:
            self.renderer.line(display)

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
                self.renderer.info(f"thinking level: {self.thinking}")
        elif command == "mode":
            from om_harness.config.loader import ApprovalPolicy

            self.harness.config.approval.policy = ApprovalPolicy(cycle_approval(self.mode))
            self.renderer.info(f"approval mode: {mode_glyph(self.mode)}")
        elif command == "config":
            self._cmd_config(args)
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
        elif command == "status":
            self._cmd_status()
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
                    "providers",
                    "tools",
                    "status",
                    "sessions",
                    "checkpoint",
                    "setup",
                    "verbose",
                    "help",
                    "exit",
                )
            )
        )
        self.renderer.line(
            DisplayLine(
                level=LineLevel.dim,
                icon="·",
                text="keys: ⇧Tab mode · alt+M model · ^T thinking · ^O verbose · ^G help",
            )
        )
        self.renderer.line(
            DisplayLine(
                level=LineLevel.dim,
                icon="·",
                text="/config set keys: model, thinking, approval, verbosity, "
                "max_concurrency, max_requests, task_model.<type>",
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
