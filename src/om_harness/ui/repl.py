"""Interactive chat REPL for `om-harness` (and the `chat` alias).

Codex/Claude-style session: live event streaming (tool calls, commands,
model thinking), per-turn activity summaries, cumulative token totals, and
full configuration management through slash commands. Turn logic reuses the
Harness facade exclusively — no runtime logic lives here.
"""

from __future__ import annotations

import asyncio

from rich.markup import escape

from om_harness.config.loader import Verbosity
from om_harness.config.user_settings import SettingsError, apply_config_update
from om_harness.harness import Harness
from om_harness.models.events import Event, EventType
from om_harness.models.task import TokenUsage
from om_harness.ui.components import DisplayLine, LineLevel, event_to_display, turn_activity
from om_harness.ui.terminal import TerminalRenderer

EXIT_COMMANDS = {"exit", "quit", ":q", "q"}
PUMP_INTERVAL_SECONDS = 0.05


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

    # -- main loop -----------------------------------------------------------

    def run_forever(self) -> None:  # pragma: no cover - interactive loop
        self.renderer.repl_prompt(self.session_id)
        while True:
            try:
                text = self._read_input()
            except (EOFError, KeyboardInterrupt):
                self.renderer.info("bye")
                return
            if not text.strip():
                continue
            if text.startswith("/") and self._slash_command(text.strip()):
                continue
            if text.strip().lower() in EXIT_COMMANDS:
                self.renderer.info("bye")
                return
            self.run_turn(text)

    def _read_input(self) -> str:  # pragma: no cover - interactive input
        footer = ""
        if self.total_usage.requests:
            footer = f" [{self.total_usage.input_tokens} in / {self.total_usage.output_tokens} out]"
        prompt = f"om{footer}> "
        try:
            from prompt_toolkit import prompt as pt_prompt
            from prompt_toolkit.formatted_text import HTML

            return pt_prompt(HTML(f"<b>{escape(prompt)}</b>"))
        except Exception:
            return input(prompt)

    # -- turns ---------------------------------------------------------------

    def run_turn(self, text: str) -> None:
        """One user turn: live-render events while the agent works."""
        offset = len(self.harness.bus.history)
        rendered: set[str] = set()

        async def _turn() -> str:
            pump = asyncio.create_task(self._pump(offset_holder, rendered))
            try:
                return await self.harness.chat_turn(self.session_id, text)
            finally:
                pump.cancel()

        offset_holder = [offset]
        try:
            reply = asyncio.run(_turn())
        except Exception as exc:
            self.renderer.error(f"turn failed: {exc}")
            return
        # Render anything the pump missed before it was cancelled.
        for event in self.harness.bus.history[offset_holder[0] :]:
            if event.id not in rendered:
                rendered.add(event.id)
                self._render_event(event)
        self.renderer.console.print(f"[green]om[/] {escape(reply)}")

        segment = self.harness.bus.history[offset:]
        activity = turn_activity(segment)
        self.total_usage = self.total_usage.add(
            TokenUsage(input_tokens=activity.input_tokens, output_tokens=activity.output_tokens)
        )
        line = activity.summary_line()
        if line != "no tool activity":
            self.renderer.line(DisplayLine(level=LineLevel.dim, icon="◇", text=line))

    async def _pump(self, offset_holder: list[int], rendered: set[str]) -> None:
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
                            self._render_event(event)
                await asyncio.sleep(PUMP_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            raise

    def _render_event(self, event: Event) -> None:
        if event.type == EventType.MESSAGE_DELTA:
            kind = event.data.get("kind")
            delta = event.data.get("delta") or ""
            if self.show_thinking and kind == "thinking" and delta:
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
            self._cmd_model(args[0] if args else None)
        elif command == "config":
            self._cmd_config(args)
        elif command == "providers":
            self._cmd_providers()
        elif command == "checkpoint":
            self._cmd_checkpoint(args[0] if args else "")
        elif command == "sessions":
            self._cmd_sessions()
        elif command == "verbose":
            self._toggle_verbosity()
        elif command == "thinking":
            self.show_thinking = not self.show_thinking
            state = "on — model thinking will stream live" if self.show_thinking else "off"
            self.renderer.info(f"thinking display {state}")
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
            "commands: /help /model [name] /config [set <key> <value>] /providers "
            "/tools /status /sessions /checkpoint [label] /verbose /thinking /exit"
        )
        self.renderer.line(
            DisplayLine(
                level=LineLevel.dim,
                icon="·",
                text="config keys: model, approval, verbosity, max_concurrency, "
                "max_requests, task_model.<type>",
            )
        )

    def _cmd_model(self, name: str | None) -> None:
        if name is None:
            self.renderer.info(f"default model: {self.harness.config.routing.default_model}")
            for task_type, model in self.harness.config.routing.task_models.items():
                self.renderer.line(
                    DisplayLine(level=LineLevel.dim, icon="·", text=f"{task_type.value}: {model}")
                )
            return
        try:
            message = apply_config_update(self.harness, "model", name)
        except SettingsError as exc:
            self.renderer.error(str(exc))
            return
        self.renderer.info(message)

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

    def _toggle_verbosity(self) -> None:
        self.verbosity = (
            Verbosity.compact if self.verbosity != Verbosity.compact else Verbosity.verbose
        )
        state = "verbose" if self.verbosity == Verbosity.verbose else "compact"
        self.renderer.info(f"verbosity: {state}")
