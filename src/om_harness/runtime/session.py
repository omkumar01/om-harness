"""Session lifecycle: creation, messages, runs, and checkpointing.

The manager mediates between the pure models and the durable store, and
publishes lifecycle events so UIs and tracers stay informed without any
runtime component knowing about presentation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from om_harness.models.events import EventType, make_event
from om_harness.models.session import (
    Checkpoint,
    Message,
    MessageRole,
    RunRecord,
    Session,
)
from om_harness.models.task import Plan, RunStatus, StrategyKind, TaskResult, TokenUsage
from om_harness.runtime.bus import EventBus
from om_harness.runtime.store import LocalStore

RoleLiteral = Literal["user", "assistant", "system"]


class SessionManager:
    def __init__(self, store: LocalStore, bus: EventBus) -> None:
        self.store = store
        self.bus = bus

    # -- lifecycle -----------------------------------------------------------

    def create(self, repo_root: str | Path) -> Session:
        session = Session(
            session_id=uuid.uuid4().hex[:12],
            repo_root=str(repo_root),
        )
        self.store.save_session(session)
        self.bus.publish_sync(
            make_event(
                EventType.SESSION_CREATED,
                session_id=session.session_id,
                repo_root=session.repo_root,
            )
        )
        return session

    def load(self, session_id: str) -> Session:
        return self.store.load_session(session_id)

    def latest(self, repo_root: str | Path) -> Session | None:
        return self.store.latest_session(str(repo_root))

    def list_sessions(self) -> list[Session]:
        return self.store.list_sessions()

    # -- conversation --------------------------------------------------------

    def add_message(
        self,
        session: Session,
        role: RoleLiteral,
        content: str,
        agent: str | None = None,
    ) -> Message:
        message = Message(role=MessageRole(role), content=content, agent=agent)
        session.messages.append(message)
        session.updated_at = datetime.now(UTC)
        self.store.save_session(session)
        return message

    # -- runs ----------------------------------------------------------------

    def start_run(self, session: Session, goal: str, strategy: StrategyKind) -> RunRecord:
        run = RunRecord(run_id=uuid.uuid4().hex[:12], goal=goal, strategy=strategy.value)
        session.runs.append(run)
        session.updated_at = datetime.now(UTC)
        self.store.save_session(session)
        self.bus.publish_sync(
            make_event(
                EventType.RUN_STARTED,
                session_id=session.session_id,
                run_id=run.run_id,
                goal=goal,
                strategy=strategy.value,
            )
        )
        return run

    def finish_run(
        self,
        session: Session,
        run: RunRecord,
        status: RunStatus,
        error: str | None = None,
        usage: TokenUsage | None = None,
        task_results: list[TaskResult] | None = None,
    ) -> RunRecord:
        run.status = status
        run.ended_at = datetime.now(UTC)
        run.error = error
        if usage is not None:
            run.usage = usage
        if task_results is not None:
            run.task_results = task_results
        session.updated_at = datetime.now(UTC)
        self.store.save_session(session)
        event_type = {
            RunStatus.completed: EventType.RUN_COMPLETED,
            RunStatus.failed: EventType.RUN_FAILED,
            RunStatus.cancelled: EventType.RUN_CANCELLED,
            RunStatus.running: EventType.RUN_STARTED,  # not used in practice
        }[status]
        self.bus.publish_sync(
            make_event(
                event_type,
                session_id=session.session_id,
                run_id=run.run_id,
                error=error,
            )
        )
        return run

    # -- checkpoints ---------------------------------------------------------

    def save_checkpoint(
        self,
        session: Session,
        run: RunRecord,
        *,
        label: str = "",
        summary: str = "",
        working_notes: str = "",
        next_hint: str | None = None,
        plan: Plan | None = None,
        task_results: list[TaskResult] | None = None,
        completed_task_ids: list[str] | None = None,
    ) -> Checkpoint:
        checkpoint = Checkpoint(
            checkpoint_id=f"cp-{uuid.uuid4().hex[:8]}",
            session_id=session.session_id,
            label=label,
            summary=summary,
            working_notes=working_notes,
            next_hint=next_hint,
            plan=plan,
            task_results=task_results or [],
            completed_task_ids=completed_task_ids or [],
        )
        self.store.save_checkpoint(checkpoint)
        self.bus.publish_sync(
            make_event(
                EventType.CHECKPOINT_SAVED,
                session_id=session.session_id,
                run_id=run.run_id,
                checkpoint_id=checkpoint.checkpoint_id,
                label=label,
                summary=summary,
            )
        )
        return checkpoint

    def load_checkpoint(self, session_id: str, checkpoint_id: str) -> Checkpoint:
        return self.store.load_checkpoint(session_id, checkpoint_id)
