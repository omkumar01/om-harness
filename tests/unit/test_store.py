"""Contract tests for the durable local store (sessions/events/checkpoints)."""

from __future__ import annotations

from typing import Any

import pytest

from om_harness.models.events import Event, EventType
from om_harness.models.session import Checkpoint, Message, MessageRole, Session
from om_harness.models.task import Plan, StrategyKind, Task, TaskResult, TaskStatus
from om_harness.runtime.store import LocalStore, StoreError


@pytest.fixture
def store(tmp_path: Any) -> LocalStore:
    return LocalStore(tmp_path / ".om-harness")


def _session(session_id: str = "sess-1") -> Session:
    return Session(session_id=session_id, repo_root="/repo")


def test_session_roundtrip(store: LocalStore) -> None:
    session = _session()
    session.messages.append(Message(role=MessageRole.user, content="fix the bug"))
    store.save_session(session)
    loaded = store.load_session("sess-1")
    assert loaded == session


def test_load_missing_session_raises(store: LocalStore) -> None:
    with pytest.raises(StoreError, match="not found"):
        store.load_session("nope")


def test_list_sessions_newest_first(store: LocalStore) -> None:
    s1 = _session("sess-1")
    s2 = _session("sess-2")
    store.save_session(s1)
    store.save_session(s2)
    # Touch s1 again so it becomes most recently updated.
    store.save_session(s1)
    sessions = store.list_sessions()
    assert [s.session_id for s in sessions] == ["sess-1", "sess-2"]


def test_latest_session_for_repo(store: LocalStore) -> None:
    assert store.latest_session("/repo") is None
    store.save_session(_session("sess-1"))
    store.save_session(_session("sess-2"))
    assert store.latest_session("/repo").session_id == "sess-2"  # type: ignore[union-attr]


def test_event_log_append_and_read(store: LocalStore) -> None:
    session = _session()
    store.save_session(session)
    events = [
        Event(type=EventType.RUN_STARTED, session_id="sess-1"),
        Event(type=EventType.RUN_COMPLETED, session_id="sess-1", data={"n": 1}),
    ]
    for event in events:
        store.append_event(event)
    assert store.read_events("sess-1") == events


def test_corrupt_session_file_raises_store_error(store: LocalStore) -> None:
    session_dir = store.root / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "broken.json").write_text("{not json")
    with pytest.raises(StoreError, match="corrupt"):
        store.load_session("broken")


def test_interrupted_write_does_not_corrupt(store: LocalStore) -> None:
    """A leftover temp file from a crashed write is ignored on read."""
    store.save_session(_session("sess-1"))
    tmp = store.root / "sessions" / "sess-1.json.tmp"
    tmp.write_text('{"partial": ')
    assert store.load_session("sess-1").session_id == "sess-1"


def test_checkpoint_roundtrip(store: LocalStore) -> None:
    store.save_session(_session())
    cp = Checkpoint(
        checkpoint_id="cp-1",
        session_id="sess-1",
        summary="explored repo",
        plan=Plan(
            goal="g", strategy=StrategyKind.single, tasks=[Task(id="a", title="A", instruction="x")]
        ),
        task_results=[TaskResult(task_id="a", status=TaskStatus.completed, summary="done")],
        completed_task_ids=["a"],
    )
    store.save_checkpoint(cp)
    loaded = store.load_checkpoint("sess-1", "cp-1")
    assert loaded == cp
    assert store.list_checkpoints("sess-1") == [cp]
    assert store.latest_checkpoint("sess-1") == cp


def test_latest_checkpoint_empty(store: LocalStore) -> None:
    store.save_session(_session())
    assert store.latest_checkpoint("sess-1") is None
