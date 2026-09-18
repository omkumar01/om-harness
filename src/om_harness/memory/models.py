"""Memory contracts for the project-level knowledge base.

These Pydantic models define the structured facts that persist across sessions
within a single repository. They mirror the style of ``models/session.py``:
compact, versioned, and JSON-serializable.

The memory system is deliberately non-LLM: facts are stored as structured
entries with keyword tags and a confidence score. Retrieval uses a keyword
inverted index (see ``memory.index``), not embeddings — aligning with the
project's design philosophy (design.md Tradeoff 2: "Mechanical minimization is
deterministic, testable, and free").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MemoryEntry(BaseModel):
    """A single fact or knowledge item persisted across sessions."""

    entry_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: str
    tags: list[str] = Field(default_factory=list)
    source_session: str = ""
    source_task: str | None = None
    confidence: float = Field(default=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    access_count: int = 0
    last_accessed: datetime | None = None
    expires_at: datetime | None = None

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float | Any) -> float:
        return max(0.0, min(1.0, float(v)))

    def is_expired(self) -> bool:
        """True if this entry has a TTL and it has elapsed."""
        if self.expires_at is None:
            return False
        return datetime.now(UTC) > self.expires_at

    def bump_access(self) -> None:
        """Record a retrieval: increment counter and update timestamp."""
        self.access_count += 1
        self.last_accessed = datetime.now(UTC)


class MemoryQuery(BaseModel):
    """Parameters for searching the memory store."""

    query: str
    tags: list[str] | None = None
    limit: int = 10
    min_confidence: float = 0.0

    @field_validator("limit")
    @classmethod
    def _positive_limit(cls, v: int | Any) -> int:
        n = int(v)
        if n < 1:
            raise ValueError("limit must be >= 1")
        return n


class MemorySummary(BaseModel):
    """Result of compacting multiple memory entries into a single summary."""

    summary: str
    entry_ids: list[str]


__all__ = [
    "MemoryEntry",
    "MemoryQuery",
    "MemorySummary",
]
