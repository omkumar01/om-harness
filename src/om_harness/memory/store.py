"""File-backed memory persistence: JSONL with atomic writes.

Follows the same durability model as ``runtime.store.LocalStore``:
- JSONL format (one ``MemoryEntry`` per line)
- Atomic writes (temp file + ``os.replace``) so crashes never corrupt reads
- Torn final lines are tolerated on read (skip + continue)
- Directory is created on demand

Layout under ``<repo>/.om-harness/memory/``::

    memory.jsonl   # one MemoryEntry per line (append/rewrite model)
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path

from om_harness.memory.models import MemoryEntry


class MemoryError(Exception):
    """Raised for unwritable or unreadable memory state."""


def _atomic_write(path: Path, payload: str) -> None:
    """Write ``payload`` to ``path`` atomically (temp file + rename)."""
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


class MemoryStore:
    """Durable, file-backed store for memory entries.

    Entries are persisted as JSONL. Each ``store`` / ``store_batch`` call
    rewrites the entire file atomically so that an entry's ``entry_id`` acts
    as a stable primary key (last-write wins on duplicate ID).
    """

    def __init__(self, memory_dir: Path) -> None:
        self.memory_dir = Path(memory_dir)
        self._jsonl_path = self.memory_dir / "memory.jsonl"

    # -- persistence -----------------------------------------------------------

    def store(self, entry: MemoryEntry) -> None:
        """Store or replace a single entry (idempotent by entry_id)."""
        entries = {e.entry_id: e for e in self.load_all()}
        entries[entry.entry_id] = entry
        self._rewrite(list(entries.values()))

    def store_batch(self, entries: list[MemoryEntry]) -> None:
        """Store or replace multiple entries (idempotent by entry_id)."""
        merged: dict[str, MemoryEntry] = {e.entry_id: e for e in self.load_all()}
        for entry in entries:
            merged[entry.entry_id] = entry
        self._rewrite(list(merged.values()))

    def _rewrite(self, entries: list[MemoryEntry]) -> None:
        lines = [e.model_dump_json() for e in entries]
        _atomic_write(self._jsonl_path, "\n".join(lines) + ("\n" if lines else ""))

    def load_all(self) -> list[MemoryEntry]:
        """Read all entries, tolerating corrupt lines."""
        if not self._jsonl_path.is_file():
            return []
        entries: list[MemoryEntry] = []
        for line in self._jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entries.append(MemoryEntry.model_validate_json(line))
            except Exception:
                continue  # skip corrupt lines (torn writes, schema drift)
        return entries

    def count(self) -> int:
        """Number of stored entries (0 if file does not exist)."""
        return len(self.load_all())

    def delete(self, entry_id: str) -> bool:
        """Remove an entry by ID. Returns True if found and removed."""
        entries = [e for e in self.load_all() if e.entry_id != entry_id]
        if len(entries) == self.count():
            return False
        self._rewrite(entries)
        return True

    def clear(self) -> None:
        """Remove all entries."""
        self._rewrite([])

    def compact(self, remove_ids: set[str]) -> None:
        """Remove entries whose IDs are in ``remove_ids``."""
        entries = [e for e in self.load_all() if e.entry_id not in remove_ids]
        self._rewrite(entries)
