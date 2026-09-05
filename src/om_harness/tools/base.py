"""Tool system foundation: permissions, context, results, and the base class.

Every tool is a small class with:
- a stable ``name`` and one-line ``description`` (shown to the model),
- a ``permission`` level driving the approval policy,
- a Pydantic ``Args`` model that doubles as the JSON schema and validates input,
- an async ``run`` that returns a structured :class:`ToolResult`.

Tools never publish events and never talk to providers; the guarded executor
in ``tools.registry`` wraps them with approval gating and event emission.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, Field

ArgsT = TypeVar("ArgsT", bound=BaseModel)


class Permission(StrEnum):
    read_only = "read_only"
    mutating = "mutating"
    destructive = "destructive"


class ToolError(Exception):
    """Raised by tools for expected failures (bad input, timeout, ...)."""


class ToolResult(BaseModel):
    """Structured tool outcome returned to the model and the event log."""

    ok: bool = True
    output: str = ""
    error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    truncated: bool = False

    @classmethod
    def fail(cls, error: str) -> ToolResult:
        return cls(ok=False, error=error)


class ToolContext(BaseModel):
    """Shared execution context handed to every tool instance."""

    repo_root: Path
    tool_timeout_seconds: float = 60.0
    max_output_chars: int = 20_000
    max_file_read_chars: int = 40_000
    # Environment snapshot for subprocesses. Provider API keys are stripped
    # before this is populated; tools must never see credentials.
    env: dict[str, str] = Field(default_factory=dict)


def resolve_in_repo(ctx: ToolContext, path_str: str) -> Path:
    """Resolve ``path_str`` strictly inside the repository root."""
    if not path_str or not path_str.strip():
        raise ToolError("path must not be empty")
    candidate = Path(path_str)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (ctx.repo_root / candidate).resolve()
    root = ctx.repo_root.resolve()
    if not resolved.is_relative_to(root):
        raise ToolError(f"path {path_str!r} resolves outside the repository")
    return resolved


def cap_text(text: str, limit: int, label: str) -> tuple[str, bool]:
    """Truncate text to ``limit`` chars, appending a notice when cut."""
    if len(text) <= limit:
        return text, False
    notice = f"\n... [{label} truncated at {limit} characters]"
    return text[:limit] + notice, True


class BaseTool(Generic[ArgsT]):
    """Base class for all tools.

    Subclasses declare a module-level ``Args`` pydantic model, alias it as
    ``Args`` (kept for introspection and tests), subclass
    ``BaseTool[TheirArgs]``, and implement ``run``.
    """

    name: ClassVar[str]
    description: ClassVar[str]
    permission: ClassVar[Permission]
    Args: ClassVar[type[BaseModel]]

    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx

    @property
    def args_model(self) -> type[BaseModel]:
        return self.Args

    async def run(self, args: ArgsT) -> ToolResult:  # pragma: no cover - interface
        raise NotImplementedError

    def spec_parameters(self) -> dict[str, Any]:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        schema.pop("description", None)
        for prop in schema.get("properties", {}).values():
            prop.pop("title", None)
        return schema
