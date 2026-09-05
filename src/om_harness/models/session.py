"""Session, message, run, and checkpoint contracts.

Checkpoints store *compact state* (plan, task results, summaries, working
notes) rather than full transcripts, so resuming never re-floods context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from om_harness.models.task import Plan, RunStatus, TaskResult, TokenUsage


class SessionStatus(StrEnum):
    active = "active"
    completed = "completed"
    failed = "failed"


class MessageRole(StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"


class Message(BaseModel):
    """A conversational message belonging to the session (UI-facing)."""

    role: MessageRole
    content: str
    agent: str | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    meta: dict[str, Any] = Field(default_factory=dict)


class RunRecord(BaseModel):
    """One orchestration run over a session (goal in, outcome out)."""

    run_id: str
    goal: str
    strategy: str = "single"
    status: RunStatus = RunStatus.running
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    usage: TokenUsage = Field(default_factory=TokenUsage)
    error: str | None = None
    task_results: list[TaskResult] = Field(default_factory=list)


class Checkpoint(BaseModel):
    """Durable, compact snapshot for resuming interrupted or long work."""

    checkpoint_id: str
    session_id: str
    label: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: str = ""
    working_notes: str = ""
    next_hint: str | None = None
    plan: Plan | None = None
    task_results: list[TaskResult] = Field(default_factory=list)
    completed_task_ids: list[str] = Field(default_factory=list)


class Session(BaseModel):
    """Durable session identity and conversation record."""

    session_id: str
    repo_root: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: SessionStatus = SessionStatus.active
    messages: list[Message] = Field(default_factory=list)
    runs: list[RunRecord] = Field(default_factory=list)
