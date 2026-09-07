"""Typed event envelope: the single instrumentation spine of the harness.

Every meaningful runtime operation (run lifecycle, agent invocation, model
calls, tool execution, approvals, checkpoints, usage) is published as an
``Event``. UIs, the persistence layer, and tracers all consume the same
stream; events never re-enter model context.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EventType(StrEnum):
    """Namespaced event categories. Values are stable API for UI consumers."""

    # Run lifecycle
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"

    # Planning
    PLAN_CREATED = "plan.created"

    # Task lifecycle
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"

    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    HANDOFF = "agent.handoff"

    # Model/provider calls
    MODEL_CALL_STARTED = "model.call.started"
    MODEL_CALL_COMPLETED = "model.call.completed"
    MODEL_RETRY = "model.retry"

    # Tool execution
    TOOL_CALL_STARTED = "tool.call.started"
    TOOL_CALL_COMPLETED = "tool.call.completed"
    TOOL_CALL_FAILED = "tool.call.failed"
    TOOL_CALL_DENIED = "tool.call.denied"

    # Approvals
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    APPROVAL_DENIED = "approval.denied"

    # State
    SESSION_CREATED = "session.created"
    SESSION_RESUMED = "session.resumed"
    CHECKPOINT_SAVED = "checkpoint.saved"

    # Usage and streaming
    USAGE = "usage.reported"
    MESSAGE_DELTA = "message.delta"

    # Diagnostics
    WARNING = "diag.warning"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Event(BaseModel):
    """One observable runtime occurrence. Small, flat, and JSON-friendly."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    # Monotonic publish order, stamped by the EventBus. Consumers use it as a
    # cursor (bus.since) so draining survives bounded-history eviction.
    seq: int = 0
    type: EventType
    ts: datetime = Field(default_factory=_utcnow)
    session_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    agent: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


def make_event(
    event_type: EventType,
    *,
    session_id: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    agent: str | None = None,
    **data: Any,
) -> Event:
    """Convenience constructor: keyword args become the ``data`` payload."""
    return Event(
        type=event_type,
        session_id=session_id,
        run_id=run_id,
        task_id=task_id,
        agent=agent,
        data=data,
    )
