"""Contract tests for the session manager (lifecycle, messages, checkpoints)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from om_harness.models.events import EventType
from om_harness.models.task import RunStatus, StrategyKind
from om_harness.runtime.bus import EventBus
from om_harness.runtime.session import SessionManager
from om_harness.runtime.store import LocalStore


def _manager(tmp_path: Any) -> tuple[SessionManager, EventBus]:
    bus = EventBus()
    store = LocalStore(tmp_path / ".om-harness")
    return SessionManager(store=store, bus=bus), bus


def test_create_session_publishes_and_persists(tmp_path: Any) -> None:
    manager, bus = _manager(tmp_path)
    session = manager.create(repo_root="/repo")
    assert session.repo_root == "/repo"
    assert bus.history[-1].type == EventType.SESSION_CREATED
    # Reload from disk through a fresh manager to prove durability.
    store = LocalStore(tmp_path / ".om-harness")
    manager2 = SessionManager(store=store, bus=EventBus())
    assert manager2.load(session.session_id).session_id == session.session_id


def test_add_message_updates_and_persists(tmp_path: Any) -> None:
    manager, _ = _manager(tmp_path)
    session = manager.create(repo_root=Path("/repo"))
    manager.add_message(session, role="user", content="hello")
    manager.add_message(session, role="assistant", content="hi", agent="planner")
    assert session.messages[0].role == "user"
    assert session.messages[1].agent == "planner"
    reloaded = manager.store.load_session(session.session_id)
    assert len(reloaded.messages) == 2


def test_run_lifecycle(tmp_path: Any) -> None:
    manager, bus = _manager(tmp_path)
    session = manager.create(repo_root=Path("/repo"))
    run = manager.start_run(session, goal="add feature", strategy=StrategyKind.sequential)
    assert run.status == RunStatus.running
    types = [e.type for e in bus.history]
    assert EventType.RUN_STARTED in types

    manager.finish_run(session, run, status=RunStatus.completed, error=None)
    assert run.status == RunStatus.completed
    assert run.ended_at is not None
    reloaded = manager.store.load_session(session.session_id)
    assert reloaded.runs[-1].status == RunStatus.completed


def test_save_checkpoint_emits_event_and_persists(tmp_path: Any) -> None:
    manager, bus = _manager(tmp_path)
    session = manager.create(repo_root=Path("/repo"))
    run = manager.start_run(session, goal="g", strategy=StrategyKind.single)
    checkpoint = manager.save_checkpoint(
        session,
        run,
        label="after-explore",
        summary="indexed repo",
        completed_task_ids=["t1"],
    )
    assert checkpoint.session_id == session.session_id
    assert EventType.CHECKPOINT_SAVED in [e.type for e in bus.history]
    assert manager.store.latest_checkpoint(session.session_id) == checkpoint


def test_list_and_latest_sessions(tmp_path: Any) -> None:
    manager, _ = _manager(tmp_path)
    assert manager.latest(repo_root=Path("/repo")) is None
    s1 = manager.create(repo_root=Path("/repo"))
    s2 = manager.create(repo_root=Path("/repo"))
    latest = manager.latest(repo_root=Path("/repo"))
    assert latest.session_id in {s1.session_id, s2.session_id}  # type: ignore[union-attr]
