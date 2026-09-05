"""Terminal renderer: rich console output for the shared UI primitives."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm

from om_harness.ui.components import DisplayLine, LineLevel, RunSummaryView

_STYLES = {
    LineLevel.info: "bold",
    LineLevel.dim: "dim",
    LineLevel.tool: "cyan",
    LineLevel.success: "green",
    LineLevel.error: "red",
    LineLevel.warn: "yellow",
}


class TerminalRenderer:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    def line(self, display: DisplayLine) -> None:
        style = _STYLES[display.level]
        self.console.print(f"[{style}]{escape(display.icon)} {escape(display.text)}[/]")

    def error(self, text: str) -> None:
        self.console.print(f"[red]✖ {escape(text)}[/]")

    def info(self, text: str) -> None:
        self.console.print(f"[bold]{escape(text)}[/]")

    def summary(self, view: RunSummaryView) -> None:
        lines = [
            f"[bold]{escape(t.status)}[/]  {escape(t.task_id)}: {escape(t.summary[:160])}"
            for t in view.tasks
        ]
        body = "\n".join(lines) if lines else "no task results"
        footer = (
            f"{view.requests} request(s), {view.input_tokens} in / {view.output_tokens} out "
            f"tokens, {view.elapsed_seconds:.1f}s"
        )
        if view.checkpoint_id:
            footer += f" · checkpoint {view.checkpoint_id}"
        self.console.print(
            Panel(
                body,
                title=f"run {view.run_id} · {view.status} · {view.strategy}",
                subtitle=footer,
                border_style="green" if view.status == "completed" else "red",
            )
        )

    def confirm(self, tool_name: str, reason: str) -> bool:
        return Confirm.ask(f"[yellow]? {escape(reason)}[/]", default=False)

    def repl_prompt(self, session_id: str) -> None:
        self.console.print(f"[dim]session {session_id} · type your request, 'exit' to quit[/]")
