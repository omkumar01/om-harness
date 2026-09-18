"""Reusable presentation primitives shared by terminal and web clients.

These components convert the runtime event stream and run outcomes into
small, presentation-neutral views (``DisplayLine``, ``RunSummaryView``).
The terminal renderer maps them to rich markup; the web client maps them to
JSON. Verbosity filtering happens here, once, for every client.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from om_harness.config.loader import Verbosity
from om_harness.harness import RunOutcome
from om_harness.models.events import Event, EventType


class LineLevel(StrEnum):
    info = "info"
    dim = "dim"
    tool = "tool"
    success = "success"
    error = "error"
    warn = "warn"


class DisplayLine(BaseModel):
    level: LineLevel
    icon: str
    text: str


class TaskSummaryView(BaseModel):
    task_id: str
    status: str
    summary: str


class RunSummaryView(BaseModel):
    session_id: str
    run_id: str
    status: str
    strategy: str
    tasks: list[TaskSummaryView] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    elapsed_seconds: float = 0.0
    checkpoint_id: str | None = None
    error: str | None = None


def outcome_to_summary(outcome: RunOutcome) -> RunSummaryView:
    return RunSummaryView(
        session_id=outcome.session_id,
        run_id=outcome.run_id,
        status=outcome.status.value,
        strategy=outcome.plan.strategy.value,
        tasks=[
            TaskSummaryView(task_id=r.task_id, status=r.status.value, summary=r.summary[:400])
            for r in outcome.results
        ],
        input_tokens=outcome.usage.input_tokens,
        output_tokens=outcome.usage.output_tokens,
        requests=outcome.usage.requests,
        elapsed_seconds=outcome.elapsed_seconds,
        checkpoint_id=outcome.checkpoint_id,
        error=outcome.error,
    )


_ICONS = {
    EventType.RUN_STARTED: "\u25b6",
    EventType.RUN_COMPLETED: "\u2714",
    EventType.RUN_FAILED: "\u2716",
    EventType.RUN_CANCELLED: "\u25a0",
    EventType.PLAN_CREATED: "\u2261",
    EventType.AGENT_STARTED: "\u2026",
    EventType.AGENT_COMPLETED: "\u2714",
    EventType.AGENT_FAILED: "\u2716",
    EventType.HANDOFF: "\u21c4",
    EventType.TOOL_CALL_STARTED: "\u2699",
    EventType.TOOL_CALL_COMPLETED: "\u2699",
    EventType.TOOL_CALL_FAILED: "\u2716",
    EventType.TOOL_CALL_DENIED: "\u26d4",
    EventType.APPROVAL_REQUESTED: "?",
    EventType.APPROVAL_GRANTED: "\u2611",
    EventType.APPROVAL_DENIED: "\u2716",
    EventType.CHECKPOINT_SAVED: "\u2318",
    EventType.USAGE: "$",
    EventType.WARNING: "!",
}

# Compact mode shows only these events; verbose adds tool/handoff details;
# debug adds everything (including model call bookkeeping).
# Failures are ALWAYS shown regardless of verbosity — errors must never be
# invisible to the user.
_COMPACT_TYPES = {
    EventType.RUN_STARTED,
    EventType.PLAN_CREATED,
    EventType.RUN_COMPLETED,
    EventType.RUN_FAILED,
    EventType.RUN_CANCELLED,
    EventType.CHECKPOINT_SAVED,
    # failure visibility (never filtered out)
    EventType.AGENT_FAILED,
    EventType.TASK_FAILED,
    EventType.TOOL_CALL_FAILED,
    EventType.TOOL_CALL_DENIED,
}
_VERBOSE_EXTRA = {
    EventType.AGENT_STARTED,
    EventType.AGENT_COMPLETED,
    EventType.AGENT_FAILED,
    EventType.TOOL_CALL_STARTED,
    EventType.TOOL_CALL_COMPLETED,
    EventType.TOOL_CALL_FAILED,
    EventType.TOOL_CALL_DENIED,
    EventType.APPROVAL_REQUESTED,
    EventType.APPROVAL_GRANTED,
    EventType.APPROVAL_DENIED,
}


def _describe(event: Event) -> str:
    data = event.data
    # `agent` and `task_id` may live as top-level event fields or in data.
    agent = event.agent or data.get("agent")
    if event.type == EventType.PLAN_CREATED:
        return (
            f"plan: {data.get('strategy')} with {data.get('task_count')} task(s) "
            f"— {data.get('rationale', '')}"
        )
    if event.type == EventType.AGENT_STARTED:
        return f"agent {agent} starting (model {data.get('model')})"
    if event.type == EventType.AGENT_COMPLETED:
        return f"agent {agent} finished"
    if event.type == EventType.TOOL_CALL_STARTED:
        args = data.get("arguments") or {}
        rendered = ", ".join(f"{k}={v!r}" for k, v in args.items())[:120]
        return f"tool {data.get('tool')}({rendered})"
    if event.type == EventType.TOOL_CALL_COMPLETED:
        return f"tool {data.get('tool')} done"
    if event.type == EventType.TOOL_CALL_FAILED:
        return f"tool {data.get('tool')} failed: {data.get('error')}"
    if event.type == EventType.TOOL_CALL_DENIED:
        return f"tool {data.get('tool')} denied: {data.get('reason')}"
    if event.type == EventType.APPROVAL_REQUESTED:
        return f"approval requested: {data.get('reason')}"
    if event.type == EventType.CHECKPOINT_SAVED:
        return f"checkpoint saved ({data.get('label')})"
    if event.type == EventType.RUN_STARTED:
        return f"goal: {data.get('goal')}"
    if event.type == EventType.RUN_COMPLETED:
        return "run completed"
    if event.type == EventType.RUN_FAILED:
        return f"run failed: {data.get('error')}"
    if event.type == EventType.USAGE:
        tokens = data.get("input_tokens", 0), data.get("output_tokens", 0)
        return f"usage: {tokens[0]} in / {tokens[1]} out tokens"
    parts = [f"{k}={v}" for k, v in data.items()]
    return f"{event.type.value}: {', '.join(parts)[:160]}"


def event_to_display(event: Event, verbosity: Verbosity) -> DisplayLine | None:
    """Map an event to a display line, or None if filtered by verbosity.

    MESSAGE_DELTA events are never rendered here — they stream live via the
    REPL pump (deltas would duplicate the final reply otherwise).
    """
    if event.type == EventType.MESSAGE_DELTA:
        return None
    if verbosity == Verbosity.debug:
        shown = True
    elif verbosity == Verbosity.verbose:
        shown = event.type in _COMPACT_TYPES or event.type in _VERBOSE_EXTRA
    else:
        shown = event.type in _COMPACT_TYPES

    if not shown:
        return None

    level = LineLevel.info
    icon = _ICONS.get(event.type, "·")
    if event.type in {EventType.RUN_FAILED, EventType.AGENT_FAILED, EventType.TOOL_CALL_FAILED}:
        level = LineLevel.error
    elif event.type == EventType.TOOL_CALL_DENIED:
        level = LineLevel.warn
    elif event.type in {EventType.RUN_COMPLETED, EventType.AGENT_COMPLETED}:
        level = LineLevel.success
    elif event.type in {EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_COMPLETED}:
        level = LineLevel.tool
    elif event.type in {EventType.PLAN_CREATED, EventType.CHECKPOINT_SAVED}:
        level = LineLevel.dim
    return DisplayLine(level=level, icon=icon, text=_describe(event))


class TurnActivity(BaseModel):
    """What one chat turn actually did — files, commands, tokens."""

    files_read: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    commands_run: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    def summary_line(self) -> str:
        parts: list[str] = []
        if self.files_read:
            parts.append("read " + ", ".join(dict.fromkeys(self.files_read)))
        if self.files_modified:
            parts.append("wrote " + ", ".join(dict.fromkeys(self.files_modified)))
        if self.commands_run:
            parts.append("ran " + ", ".join(self.commands_run))
        if self.input_tokens or self.output_tokens:
            parts.append(f"{self.input_tokens}+{self.output_tokens} tok")
        return " · ".join(parts) if parts else "no tool activity"


_MUTATING_TOOLS = {"write_file", "edit_file", "format_code", "lint_code"}
_READ_TOOLS = {"read_file"}
_COMMAND_TOOLS = {
    "run_shell",
    "run_tests",
    "git_branch",
    "git_stash",
    "git_remote",
    "format_code",
    "lint_code",
    "fetch_url",
    "fetch_batch_url",
}


def turn_activity(events: list[Event]) -> TurnActivity:
    """Derive the concrete activity of one turn from its event segment."""
    activity = TurnActivity()
    for event in events:
        data = event.data
        tool = data.get("tool")
        if event.type == EventType.TOOL_CALL_STARTED and tool:
            arguments = data.get("arguments") or {}
            path = arguments.get("path") or arguments.get("subdirectory") or ""
            if tool in _READ_TOOLS and path:
                activity.files_read.append(str(path))
            elif tool in _MUTATING_TOOLS and path:
                activity.files_modified.append(str(path))
            elif tool in _COMMAND_TOOLS:
                label = tool
                if tool == "run_shell" and arguments.get("command"):
                    label = f"run_shell({arguments['command'][:60]})"
                activity.commands_run.append(label)
        elif event.type == EventType.MODEL_CALL_COMPLETED:
            activity.input_tokens += int(data.get("input_tokens") or 0)
            activity.output_tokens += int(data.get("output_tokens") or 0)
    return activity


# -- interactive-shell chrome (pure builders, unit-testable) -------------------


def usage_bar(used_tokens: int, max_tokens: int, width: int = 10) -> str:
    """Ten-segment context gauge: \u25ae\u25ae\u25ae\u25af\u25af 3k/20k."""
    if max_tokens <= 0:
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, used_tokens / max_tokens))
    filled = round(ratio * width)
    bar = "\u25ae" * filled + "\u25af" * (width - filled)

    def fmt(n: int, *, precise: bool = False) -> str:
        """Compact token count. ``precise`` (used tokens) keeps one-decimal
        resolution below 100k so 1,500 never rounds up to a bogus '2k'."""
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if precise and 1_000 <= n < 100_000:
            return f"{n / 1000:.1f}k"
        return f"{n / 1000:.0f}k" if n >= 1000 else str(n)

    return f"{bar} {fmt(used_tokens, precise=True)}/{fmt(max_tokens)}"


def header_line(provider: str, model: str, mode: str, thinking: str, width: int = 64) -> str:
    """Top border of the input box with state baked in."""
    state = f"om \u00b7 {provider} \u00b7 {model} \u00b7 {mode} \u00b7 {thinking}"
    if len(state) > width - 4:
        state = state[: width - 7] + "\u2026"
    filler = "─" * max(0, width - len(state) - 4)
    return f"╭─ {state} {filler}╮"


def status_bar(
    provider: str,
    model: str,
    thinking: str,
    mode: str,
    used_tokens: int,
    max_tokens: int,
    hint: str | None = None,
    thinking_active: bool = False,
) -> str:
    """Always-on status line: approval mode, provider, model, thinking,
    context gauge, hints — visible at all times.

    ``thinking_active`` adds a ``\u25d0`` pulse prefix when reasoning is
    currently streaming in minimized display mode.
    """
    thinking_segment = f"\u25d0 {thinking}" if thinking_active else thinking
    parts = [
        mode,
        f"provider {provider}",
        f"model {model}",
        f"thinking {thinking_segment}",
        f"context {usage_bar(used_tokens, max_tokens)}",
    ]
    if hint:
        parts.append(hint)
    else:
        parts.append("alt+M model · ^T thinking · ⇧Tab mode · ^G help")
    return "  \u00b7  ".join(parts)


def resume_hint(session_id: str, checkpoint_id: str | None = None) -> str:
    """One-line resume command for a session (suitable for status/footer).

    Uses the bare shell-resume form: it reopens the interactive shell
    continuing that session, no new goal required.
    """
    base = f"om-harness --resume --session {session_id}"
    if checkpoint_id:
        base += f"  \u00b7  cp: {checkpoint_id}"
    return base


def welcome_panel(version: str, model: str, providers: list[str], first_run: bool) -> str:
    """Plain-text body of the welcome panel (renderer wraps it in a Panel)."""
    provider_text = ", ".join(providers) if providers else "none \u2014 add keys or models.json"
    lines = [
        f"\u2726 om-harness {version}",
        f"model: {model}",
        f"providers: {provider_text}",
        "",
        "type a request, / for commands, /setup for guided configuration",
    ]
    if first_run:
        lines.insert(1, "first run \u2014 config created under ~/.om-harness/")
    return "\n".join(lines)


__all__ = [
    "DisplayLine",
    "LineLevel",
    "RunSummaryView",
    "TaskSummaryView",
    "TurnActivity",
    "event_to_display",
    "header_line",
    "outcome_to_summary",
    "resume_hint",
    "status_bar",
    "turn_activity",
    "usage_bar",
    "welcome_panel",
]
