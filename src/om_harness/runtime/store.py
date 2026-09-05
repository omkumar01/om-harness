"""Durable local persistence: JSON sessions, JSONL events, checkpoint files.

Layout under ``<repo>/.om-harness/`` (auto-gitignored by ``om-harness init``)::

    sessions/<session_id>.json
    events/<session_id>.jsonl
    checkpoints/<session_id>/<checkpoint_id>.json

All writes are atomic (temp file + ``os.replace``), so a crash mid-write never
corrupts readable state. This is intentionally simple; the store interface is
the future seam for database-backed persistence.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from om_harness.models.events import Event
from om_harness.models.session import Checkpoint, Session


class StoreError(Exception):
    """Raised for missing, corrupt, or unwritable persistent state."""


def _now_iso() -> str:  # pragma: no cover - reserved for future metadata
    return datetime.now(UTC).isoformat()


def _atomic_write_json(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


class LocalStore:
    """File-backed session/event/checkpoint store rooted at one directory."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._sessions_dir = self.root / "sessions"
        self._events_dir = self.root / "events"
        self._checkpoints_dir = self.root / "checkpoints"

    # -- sessions ------------------------------------------------------------

    def save_session(self, session: Session) -> None:
        session.updated_at = datetime.now(UTC)
        _atomic_write_json(
            self._sessions_dir / f"{session.session_id}.json", session.model_dump_json()
        )

    def load_session(self, session_id: str) -> Session:
        path = self._sessions_dir / f"{session_id}.json"
        if not path.exists():
            raise StoreError(f"session {session_id!r} not found")
        try:
            return Session.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise StoreError(f"corrupt session file {path}: {exc}") from exc

    def list_sessions(self) -> list[Session]:
        """All sessions, most recently updated first."""
        if not self._sessions_dir.exists():
            return []
        sessions: list[Session] = []
        for path in self._sessions_dir.glob("*.json"):
            try:
                sessions.append(Session.model_validate_json(path.read_text(encoding="utf-8")))
            except (ValidationError, OSError):
                continue  # skip corrupt files rather than failing listing
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions

    def latest_session(self, repo_root: str) -> Session | None:
        for session in self.list_sessions():
            if session.repo_root == repo_root:
                return session
        return None

    # -- events --------------------------------------------------------------

    def append_event(self, event: Event) -> None:
        if event.session_id is None:
            raise StoreError("cannot append an event without session_id")
        log = self._events_dir / f"{event.session_id}.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(event.model_dump_json() + "\n")

    def read_events(self, session_id: str) -> list[Event]:
        log = self._events_dir / f"{session_id}.jsonl"
        if not log.exists():
            return []
        events: list[Event] = []
        for line in log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(Event.model_validate_json(line))
            except ValidationError:
                continue  # tolerate a torn final line after a crash
        return events

    # -- checkpoints ---------------------------------------------------------

    def save_checkpoint(self, checkpoint: Checkpoint) -> None:
        directory = self._checkpoints_dir / checkpoint.session_id
        _atomic_write_json(
            directory / f"{checkpoint.checkpoint_id}.json", checkpoint.model_dump_json()
        )

    def load_checkpoint(self, session_id: str, checkpoint_id: str) -> Checkpoint:
        path = self._checkpoints_dir / session_id / f"{checkpoint_id}.json"
        if not path.exists():
            raise StoreError(f"checkpoint {checkpoint_id!r} not found for session {session_id!r}")
        try:
            return Checkpoint.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            raise StoreError(f"corrupt checkpoint file {path}: {exc}") from exc

    def list_checkpoints(self, session_id: str) -> list[Checkpoint]:
        directory = self._checkpoints_dir / session_id
        if not directory.exists():
            return []
        checkpoints: list[Checkpoint] = []
        for path in directory.glob("*.json"):
            try:
                checkpoints.append(Checkpoint.model_validate_json(path.read_text(encoding="utf-8")))
            except (ValidationError, OSError):
                continue
        checkpoints.sort(key=lambda cp: cp.created_at)
        return checkpoints

    def latest_checkpoint(self, session_id: str) -> Checkpoint | None:
        checkpoints = self.list_checkpoints(session_id)
        return checkpoints[-1] if checkpoints else None
