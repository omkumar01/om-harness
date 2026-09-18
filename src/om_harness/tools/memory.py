"""Memory tools: store and recall project-level facts.

These tools give agents the ability to remember information between sessions
within a repository. ``remember`` is a mutating tool (requires approval under
non-``auto`` policies); ``recall`` is read-only.

Both follow the existing ``BaseTool`` pattern: a stable ``name``, a
``Permission`` level, a Pydantic ``Args`` model that doubles as the JSON
schema, and an async ``run`` returning a structured ``ToolResult``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from om_harness.memory.index import MemoryIndex
from om_harness.memory.models import MemoryEntry, MemoryQuery
from om_harness.memory.store import MemoryStore
from om_harness.tools.base import BaseTool, Permission, ToolResult


class MemoryRememberTool(BaseTool["MemoryRememberTool.Args"]):
    """Store a fact in the project memory."""

    name = "remember"
    description = (
        "Store a fact, insight, or piece of knowledge in the project's "
        "persistent memory so it can be recalled in future sessions. "
        "Use this for important discoveries: file locations, bugs found, "
        "decisions made, configuration details, or patterns learned."
    )
    permission = Permission.mutating

    class Args(BaseModel):
        fact: str = Field(description="The fact or knowledge to store")
        tags: list[str] = Field(
            default_factory=list,
            description="Tags to categorize this fact (e.g. 'bug', 'config', 'decision')",
        )
        confidence: float = Field(default=1.0, description="Confidence level from 0.0 to 1.0")
        source_task: str | None = Field(
            default=None, description="Optional task ID this fact originated from"
        )
        entry_id: str | None = Field(
            default=None, description="Optional entry ID to update an existing fact"
        )

    def __init__(
        self,
        ctx: Any,
        *,
        store: MemoryStore,
        source_session: str = "",
        index: MemoryIndex | None = None,
    ) -> None:
        super().__init__(ctx)
        self.store = store
        self.source_session = source_session
        self.index = index

    async def run(self, args: MemoryRememberTool.Args) -> ToolResult:
        entry = MemoryEntry(
            content=args.fact,
            tags=args.tags,
            source_session=self.source_session,
            source_task=args.source_task,
            confidence=args.confidence,
        )
        if args.entry_id:
            entry.entry_id = args.entry_id
        self.store.store(entry)
        if self.index is not None:
            self.index.add(entry)
        return ToolResult(
            ok=True,
            output=f"Stored in memory (id: {entry.entry_id}): {entry.content[:200]}",
            data={"entry_id": entry.entry_id, "tags": entry.tags},
        )


class MemoryRecallTool(BaseTool["MemoryRecallTool.Args"]):
    """Recall facts from the project memory."""

    name = "recall"
    description = (
        "Search the project's persistent memory for previously stored facts, "
        "insights, or knowledge. Use this to rediscover information from past "
        "sessions instead of re-deriving it. Returns matching facts ranked by "
        "relevance."
    )
    permission = Permission.read_only

    class Args(BaseModel):
        query: str = Field(description="Search terms to find in memory")
        tags: list[str] = Field(
            default_factory=list,
            description="Optionally filter by tags (entry must have ALL listed tags)",
        )
        limit: int = Field(default=10, description="Maximum number of results to return")
        min_confidence: float = Field(
            default=0.0, description="Minimum confidence level (0.0 to 1.0)"
        )

    def __init__(self, ctx: Any, *, index: MemoryIndex) -> None:
        super().__init__(ctx)
        self.index = index

    async def run(self, args: MemoryRecallTool.Args) -> ToolResult:
        query = MemoryQuery(
            query=args.query,
            tags=args.tags if args.tags else None,
            limit=args.limit,
            min_confidence=args.min_confidence,
        )
        results = self.index.retrieve(query)
        if not results:
            return ToolResult(
                ok=True,
                output=f"No memory entries found matching {args.query!r}.",
                data={"count": 0},
            )
        lines = [f"Found {len(results)} memory entries:"]
        for entry in results:
            tag_str = f" (tags: {entry.tags})" if entry.tags else ""
            conf_str = f" (confidence: {entry.confidence})" if entry.confidence < 1.0 else ""
            lines.append(f"- {entry.content}{tag_str}{conf_str}")
        return ToolResult(
            ok=True,
            output="\n".join(lines),
            data={
                "count": len(results),
                "tags": [t for e in results for t in e.tags],
                "entry_ids": [e.entry_id for e in results],
            },
        )


__all__ = [
    "MemoryRecallTool",
    "MemoryRememberTool",
]
