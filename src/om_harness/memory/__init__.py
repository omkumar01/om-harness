"""Project-level memory: persists facts across sessions within a repository.

Public API:
    MemoryEntry — a single knowledge item
    MemoryQuery — search parameters
    MemorySummary — compacted summary of multiple entries
    MemoryStore — file-backed JSONL persistence
    MemoryIndex — in-memory inverted keyword index
    ContextCompressor — mechanical fact extraction and context compression
"""

from __future__ import annotations

from om_harness.memory.compressor import ContextCompressor
from om_harness.memory.index import MemoryIndex
from om_harness.memory.models import MemoryEntry, MemoryQuery, MemorySummary
from om_harness.memory.store import MemoryError, MemoryStore

__all__ = [
    "ContextCompressor",
    "MemoryEntry",
    "MemoryError",
    "MemoryIndex",
    "MemoryQuery",
    "MemoryStore",
    "MemorySummary",
]
