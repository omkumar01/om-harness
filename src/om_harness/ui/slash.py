"""Slash-command registry and typing hints for the interactive shell.

Shared by the REPL (dispatch + status-bar hints) and the prompt_toolkit
completer (autocomplete with descriptions). Everything here is UI logic
only — commands delegate to the Harness or user_settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from prompt_toolkit.completion import Completer, Completion

from om_harness.config.loader import ThinkingLevel, Verbosity


@dataclass(frozen=True)
class SlashCommand:
    name: str
    description: str
    args_hint: str = ""  # e.g. "<provider:model>"


COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("model", "Pick or set the active model", "[provider:model]"),
    SlashCommand("thinking", "Show or set the thinking level", "[off|low|medium|high]"),
    SlashCommand("mode", "Cycle approval mode (ask / auto / deny)"),
    SlashCommand("config", "Show or change configuration", "[set <key> <value>]"),
    SlashCommand("providers", "List providers and availability"),
    SlashCommand("tools", "List available tools and permissions"),
    SlashCommand("status", "Session, checkpoint, and provider status"),
    SlashCommand("sessions", "List recent sessions"),
    SlashCommand("checkpoint", "Save a checkpoint now", "[label]"),
    SlashCommand("setup", "Interactive setup wizard (providers, model, modes)"),
    SlashCommand("verbose", "Cycle verbosity (compact / verbose / debug)"),
    SlashCommand("help", "Show commands and keybindings"),
    SlashCommand("exit", "Leave the session"),
)


def find_command(name: str) -> SlashCommand | None:
    lowered = name.lower().lstrip("/")
    return next((c for c in COMMANDS if c.name == lowered), None)


def cycle(values: tuple[str, ...], current: str) -> str:
    """Next value in a cycle (wraps around)."""
    try:
        return values[(values.index(current) + 1) % len(values)]
    except ValueError:
        return values[0]


def cycle_approval(current: str) -> str:
    return cycle(("ask", "auto", "deny"), current)


def cycle_thinking(current: str) -> str:
    return cycle(
        (ThinkingLevel.off, ThinkingLevel.low, ThinkingLevel.medium, ThinkingLevel.high), current
    )


def cycle_verbosity(current: str) -> str:
    return cycle((Verbosity.compact, Verbosity.verbose, Verbosity.debug), current)


MODE_GLYPHS: dict[str, str] = {
    "ask": "⏵ ask",
    "auto": "⏵⏵ auto",
    "deny": "⛔ deny",
    "allowlist": "⏵ list",
}

THINKING_GLYPHS: dict[str, str] = {
    "off": "◌ thinking",
    "low": "◐ thinking:low",
    "medium": "◑ thinking:med",
    "high": "● thinking:high",
}


def mode_glyph(policy: str) -> str:
    return MODE_GLYPHS.get(policy, policy)


def thinking_glyph(level: str) -> str:
    return THINKING_GLYPHS.get(level, f"◌ {level}")


def args_hint_for(text: str, model_names: list[str]) -> str | None:
    """Inline hint for the slash command currently being typed, if any."""
    if not text.startswith("/"):
        return None
    parts = text[1:].split(maxsplit=1)
    if not parts:
        return None
    command = find_command(parts[0])
    if command is None:
        return None
    base = f"/{command.name} {command.args_hint}".strip()
    if command.name == "model" and model_names:
        sample = ", ".join(model_names[:2])
        return f"{base}  e.g. {sample} · Tab to complete"
    if command.name == "config":
        return (
            base + "  keys: model, thinking, approval, verbosity, max_concurrency, "
            "max_requests, task_model.<type>"
        )
    if command.name == "thinking":
        return base + "  · Tab to complete"
    return base


class SlashCompleter(Completer):
    """Autocomplete slash commands and their arguments with descriptions."""

    def __init__(self, repl: Any) -> None:
        self.repl = repl

    def get_completions(self, document: Any, complete_event: Any) -> Any:
        text = document.text_before_cursor
        if not text.startswith("/") or "  " in text:
            return
        parts = text[1:].split(" ")
        head = parts[0]

        if len(parts) == 1 and not text.endswith(" "):
            # Completing the command name itself.
            for entry in COMMANDS:
                if entry.name.startswith(head.lower()):
                    meta = entry.description
                    if entry.args_hint:
                        meta += f" · {entry.args_hint}"
                    yield Completion(
                        entry.name,
                        start_position=-len(head),
                        display=f"/{entry.name}",
                        display_meta=meta,
                    )
            return

        command = find_command(head)
        if command is None:
            return
        arg_prefix = parts[1] if len(parts) > 1 else ""
        if command.name == "config" and arg_prefix == "set":
            # /config set <key>: the completable token comes after "set".
            arg_prefix = parts[2] if len(parts) > 2 else ""
        if len(parts) < 2 and not text.endswith(" "):
            return

        candidates: list[tuple[str, str]] = []
        if command.name == "model":
            candidates = [(name, label) for name, label in self._model_options()]
        elif command.name == "thinking":
            candidates = [(lv.value, lv.value) for lv in ThinkingLevel]
        elif command.name == "config":
            candidates = [
                ("model", "default model"),
                ("thinking", "off|low|medium|high"),
                ("approval", "ask|auto|allowlist|deny"),
                ("verbosity", "compact|verbose|debug"),
                ("max_concurrency", "parallel agent tasks"),
                ("max_requests", "per-run request budget"),
                ("task_model.explore", "route explore tasks"),
                ("task_model.implement", "route implement tasks"),
                ("task_model.review", "route review tasks"),
            ]
        else:
            return

        for value, meta in candidates:
            if value.startswith(arg_prefix.lower()) or arg_prefix == "":
                yield Completion(
                    value,
                    start_position=-len(arg_prefix),
                    display=value,
                    display_meta=meta,
                )

    def _model_options(self) -> list[tuple[str, str]]:
        try:
            from om_harness.config.user_settings import available_model_strings

            return available_model_strings(self.repl.harness)
        except Exception:
            return []
