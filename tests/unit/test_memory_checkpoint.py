"""Contract tests for memory-enhanced checkpoints.

Tests that Checkpoint stores memory_entry_ids and that they survive
save/load roundtrips through the store and session manager.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from om_harness.models.session import Checkpoint, Session
from om_harness.models.task import StrategyKind
from om_harness.runtime.bus import EventBus
from om_harness.runtime.session import SessionManager
from om_harness.runtime.store import LocalStore


def _store(tmp_path: Any) -> LocalStore:
    return LocalStore(tmp_path / ".om-harness")


def _session(session_id: str = "sess-1") -> Session:
    return Session(session_id=session_id, repo_root="/repo")


def test_checkpoint_has_memory_entry_ids_field() -> None:
    cp = Checkpoint(
        checkpoint_id="cp-1",
        session_id="sess-1",
    )
    assert cp.memory_entry_ids == []


def test_checkpoint_stores_memory_entry_ids() -> None:
    cp = Checkpoint(
        checkpoint_id="cp-1",
        session_id="sess-1",
        memory_entry_ids=["m1", "m2", "m3"],
    )
    assert cp.memory_entry_ids == ["m1", "m2", "m3"]


def test_checkpoint_memory_entry_ids_roundtrip(tmp_path: Any) -> None:
    store = _store(tmp_path)
    store.save_session(_session())
    cp = Checkpoint(
        checkpoint_id="cp-1",
        session_id="sess-1",
        memory_entry_ids=["m1", "m2"],
        summary="test checkpoint with memory references",
    )
    store.save_checkpoint(cp)
    loaded = store.load_checkpoint("sess-1", "cp-1")
    assert loaded.memory_entry_ids == ["m1", "m2"]


def test_save_checkpoint_accepts_memory_entry_ids(tmp_path: Any) -> None:
    store = _store(tmp_path)
    bus = EventBus()
    manager = SessionManager(store=store, bus=bus)
    session = manager.create(repo_root=Path("/repo"))
    run = manager.start_run(session, goal="g", strategy=StrategyKind.single)
    checkpoint = manager.save_checkpoint(
        session,
        run,
        label="after-run",
        summary="completed with memory",
        memory_entry_ids=["m1", "m2"],
    )
    assert checkpoint.memory_entry_ids == ["m1", "m2"]
    loaded = manager.store.load_checkpoint(session.session_id, checkpoint.checkpoint_id)
    assert loaded.memory_entry_ids == ["m1", "m2"]


def test_checkpoint_without_memory_entry_ids_defaults_empty(tmp_path: Any) -> None:
    store = _store(tmp_path)
    store.save_session(_session())
    cp = Checkpoint(
        checkpoint_id="cp-1",
        session_id="sess-1",
    )
    json_str = cp.model_dump_json()
    loaded = Checkpoint.model_validate_json(json_str)
    assert loaded.memory_entry_ids == []
