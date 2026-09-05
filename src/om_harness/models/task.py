"""Task and plan contracts, including the structured agent-to-agent result.

Agents never exchange raw conversation histories: they return ``TaskResult``
objects — a compact summary, key findings, touched files, errors, and optional
artifacts. This is the primary lever for keeping multi-agent context small.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TaskType(StrEnum):
    """Task flavor, used for provider routing and prompt scoping."""

    general = "general"
    explore = "explore"
    implement = "implement"
    review = "review"
    test = "test"


class StrategyKind(StrEnum):
    """Execution strategies supported by the orchestration layer."""

    single = "single"  # one agent, one task
    sequential = "sequential"  # ordered pipeline of tasks
    parallel = "parallel"  # fan-out/fan-in of independent tasks
    reviewer = "reviewer"  # implement, then review, then fix


class TaskStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    skipped = "skipped"


class TokenUsage(BaseModel):
    """Accumulated token/request/cost accounting."""

    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    cost_usd: float | None = None

    def add(self, other: TokenUsage) -> TokenUsage:
        cost = None
        if self.cost_usd is not None or other.cost_usd is not None:
            cost = (self.cost_usd or 0.0) + (other.cost_usd or 0.0)
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            requests=self.requests + other.requests,
            cost_usd=cost,
        )


class Task(BaseModel):
    """A unit of work assigned to one agent invocation."""

    id: str
    title: str
    instruction: str
    task_type: TaskType = TaskType.general
    role: str = "implementer"
    depends_on: list[str] = Field(default_factory=list)


class TaskResult(BaseModel):
    """Structured hand-off between agents (or agent -> coordinator).

    Deliberately compact: a resumed or coordinating agent receives this, not
    the sub-agent's message history.
    """

    task_id: str
    status: TaskStatus = TaskStatus.completed
    summary: str = ""
    findings: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    artifacts: dict[str, str] = Field(default_factory=dict)


class Plan(BaseModel):
    """An execution plan produced by the planner or the model itself."""

    goal: str
    strategy: StrategyKind = StrategyKind.single
    rationale: str = ""
    tasks: list[Task] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> Plan:
        ids = {t.id for t in self.tasks}
        for task in self.tasks:
            for dep in task.depends_on:
                if dep not in ids:
                    raise ValueError(f"unknown dependency {dep!r} for task {task.id!r}")
        # Cycle detection via Kahn's algorithm.
        indegree = {t.id: 0 for t in self.tasks}
        dependents: dict[str, list[str]] = {t.id: [] for t in self.tasks}
        for task in self.tasks:
            for dep in task.depends_on:
                indegree[task.id] += 1
                dependents[dep].append(task.id)
        queue = [tid for tid, deg in indegree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop()
            visited += 1
            for nxt in dependents[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if visited != len(self.tasks):
            raise ValueError("dependency cycle in plan")
        return self

    def topological_order(self) -> list[Task]:
        """Deterministic topological order (declaration order breaks ties)."""
        remaining = {t.id: set(t.depends_on) for t in self.tasks}
        by_id = {t.id: t for t in self.tasks}
        order: list[Task] = []
        while remaining:
            ready = [tid for tid, deps in remaining.items() if not deps]
            if not ready:  # pragma: no cover - validator rejects cycles
                raise ValueError("dependency cycle in plan")
            for tid in ready:  # declaration order preserved via dict iteration
                order.append(by_id[tid])
                del remaining[tid]
            for deps in remaining.values():
                deps.difference_update(t.id for t in order)
        return order


class RunStatus(StrEnum):
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


OutcomeStatus = Literal["completed", "failed", "cancelled"]
