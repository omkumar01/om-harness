"""Planner: the smallest component that decides how work gets structured.

Deliberately heuristic in v1: prefer a single agent; split only when the goal
or the user clearly calls for it. The plan graph (not cleverness) is what the
coordinator executes, so plans remain inspectable and testable.
"""

from __future__ import annotations

import re

from om_harness.config.loader import HarnessConfig
from om_harness.models.task import Plan, StrategyKind, Task, TaskType

SEQUENTIAL_HINTS = re.compile(r"\bthen\b|\bafter that\b|\bafterwards\b|\bnext,?\b", re.IGNORECASE)
REVIEW_HINTS = re.compile(r"\breview\b|\bcheck my (work|changes|patch)\b", re.IGNORECASE)
EXPLORE_HINTS = re.compile(
    r"\b(where|how does|what does|find|explain|understand|explore|investigate)\b",
    re.IGNORECASE,
)


class Planner:
    def __init__(self, config: HarnessConfig) -> None:
        self.config = config

    def decide(
        self,
        goal: str,
        strategy_override: str | None = None,
        explicit_tasks: list[Task] | None = None,
    ) -> StrategyKind:
        if strategy_override:
            return StrategyKind(strategy_override)
        if explicit_tasks is not None and len(explicit_tasks) > 1:
            # Multiple user-declared tasks with dependencies => sequential;
            # without dependencies => parallel.
            has_deps = any(t.depends_on for t in explicit_tasks)
            return StrategyKind.sequential if has_deps else StrategyKind.parallel
        if REVIEW_HINTS.search(goal):
            return StrategyKind.reviewer
        if SEQUENTIAL_HINTS.search(goal):
            return StrategyKind.sequential
        return StrategyKind.single

    def build_plan(
        self,
        goal: str,
        strategy: str | None = None,
        tasks: list[Task] | None = None,
    ) -> Plan:
        chosen = self.decide(goal, strategy_override=strategy, explicit_tasks=tasks)

        if tasks is not None:
            return Plan(goal=goal, strategy=chosen, tasks=tasks, rationale="user-declared tasks")

        if chosen == StrategyKind.single:
            task_type = TaskType.explore if EXPLORE_HINTS.search(goal) else TaskType.implement
            return Plan(
                goal=goal,
                strategy=chosen,
                tasks=[Task(id="main", title="Main task", instruction=goal, task_type=task_type)],
                rationale="single agent is the simplest strategy that can complete this",
            )

        if chosen == StrategyKind.sequential:
            return Plan(
                goal=goal,
                strategy=chosen,
                tasks=[
                    Task(
                        id="explore-1",
                        title="Explore",
                        instruction=f"Investigate the repository to prepare for: {goal}",
                        task_type=TaskType.explore,
                        role="explorer",
                    ),
                    Task(
                        id="implement-1",
                        title="Implement",
                        instruction=goal,
                        task_type=TaskType.implement,
                        depends_on=["explore-1"],
                    ),
                ],
                rationale="explore first, then implement, reusing a structured result",
            )

        if chosen == StrategyKind.reviewer:
            return Plan(
                goal=goal,
                strategy=chosen,
                tasks=[
                    Task(id="implement-1", title="Implement", instruction=goal),
                    Task(
                        id="review-1",
                        title="Review changes",
                        instruction=(
                            f"Review the changes made for this goal: {goal}. "
                            "Check correctness, edge cases, and tests."
                        ),
                        task_type=TaskType.review,
                        role="reviewer",
                        depends_on=["implement-1"],
                    ),
                ],
                rationale="implement, then an independent review pass",
            )

        # parallel without declared tasks degrades to sequential shape
        return self.build_plan(goal, strategy="sequential")
