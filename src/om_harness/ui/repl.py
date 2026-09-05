"""Interactive chat REPL for `om-harness chat`.

Kept deliberately simple: a synchronous prompt loop; each turn reuses the
Harness facade and prints the events the turn produced (verbosity-filtered).
Prompt history and multi-line input come from prompt_toolkit when available.
"""

from __future__ import annotations

import asyncio

from rich.markup import escape

from om_harness.config.loader import Verbosity
from om_harness.harness import Harness
from om_harness.ui.components import DisplayLine, LineLevel, event_to_display
from om_harness.ui.terminal import TerminalRenderer

EXIT_COMMANDS = {"exit", "quit", ":q", "q"}
SLASH_COMMANDS = {"tools", "status", "help"}


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
        self.renderer = renderer or TerminalRenderer()
        self._event_offset = len(harness.bus.history)

    def run_forever(self) -> None:  # pragma: no cover - interactive loop
        self.renderer.repl_prompt(self.session_id)
        while True:
            try:
                text = self._read_input()
            except (EOFError, KeyboardInterrupt):
                self.renderer.info("bye")
                return
            if text.strip().lower() in EXIT_COMMANDS:
                self.renderer.info("bye")
                return
            if not text.strip():
                continue
            if text.strip().lstrip("/").lower() in SLASH_COMMANDS:
                self._slash_command(text.strip().lstrip("/").lower())
                continue
            self.run_turn(text)

    def _read_input(self) -> str:  # pragma: no cover - interactive input
        try:
            from prompt_toolkit import prompt as pt_prompt
            from prompt_toolkit.formatted_text import HTML

            return pt_prompt(HTML("<b>om&gt;</b> "))
        except Exception:
            return input("om> ")

    def _slash_command(self, command: str) -> None:
        if command == "tools":
            for spec in self.harness.registry.specs():
                self.renderer.line(
                    DisplayLine(
                        level=LineLevel.dim,
                        icon="·",
                        text=f"{spec['name']} ({spec['permission']}): {spec['description']}",
                    )
                )
        elif command == "status":
            for key, value in self.harness.status().items():
                self.renderer.console.print(f"[dim]{key}: {value}[/]")
        elif command == "help":
            self.renderer.info("commands: /tools /status /help · exit with 'exit'")

    def run_turn(self, text: str) -> None:
        offset_before = len(self.harness.bus.history)
        try:
            reply = asyncio.run(self.harness.chat_turn(self.session_id, text))
        except Exception as exc:
            self.renderer.error(f"turn failed: {exc}")
            return
        self._print_new_events(offset_before)
        self.renderer.console.print(f"[green]om[/] {escape(reply)}")

    def _print_new_events(self, offset_before: int) -> None:
        for event in self.harness.bus.history[offset_before:]:
            display = event_to_display(event, self.verbosity)
            if display is not None:
                self.renderer.line(display)
        self._event_offset = len(self.harness.bus.history)
