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
    EventType.RUN_STARTED: "▶",
    EventType.RUN_COMPLETED: "✔",
    EventType.RUN_FAILED: "✖",
    EventType.RUN_CANCELLED: "■",
    EventType.PLAN_CREATED: "≡",
    EventType.AGENT_STARTED: "…",
    EventType.AGENT_COMPLETED: "✔",
    EventType.AGENT_FAILED: "✖",
    EventType.HANDOFF: "⇄",
    EventType.TOOL_CALL_STARTED: "⚙",
    EventType.TOOL_CALL_COMPLETED: "⚙",
    EventType.TOOL_CALL_FAILED: "✖",
    EventType.TOOL_CALL_DENIED: "⛔",
    EventType.APPROVAL_REQUESTED: "?",
    EventType.APPROVAL_GRANTED: "☑",
    EventType.APPROVAL_DENIED: "✖",
    EventType.CHECKPOINT_SAVED: "⌘",
    EventType.USAGE: "$",
    EventType.WARNING: "!",
}

# Compact mode shows only these events; verbose adds tool/handoff details;
# debug adds everything (including model call bookkeeping).
_COMPACT_TYPES = {
    EventType.RUN_STARTED,
    EventType.PLAN_CREATED,
    EventType.RUN_COMPLETED,
    EventType.RUN_FAILED,
    EventType.RUN_CANCELLED,
    EventType.CHECKPOINT_SAVED,
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
    """Map an event to a display line, or None if filtered by verbosity."""
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


__all__ = [
    "DisplayLine",
    "LineLevel",
    "RunSummaryView",
    "TaskSummaryView",
    "event_to_display",
    "outcome_to_summary",
]
