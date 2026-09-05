"""Coordinator: executes a plan's task graph with bounded concurrency.

Execution model: topological waves. Within a wave, tasks run concurrently
(bounded by a semaphore); results aggregate deterministically in declaration
order. Per-task: timeout, retry with exponential backoff. Tasks whose
dependencies failed (or were skipped) are skipped, never launched.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from om_harness.config.loader import HarnessConfig
from om_harness.models.events import EventType, make_event
from om_harness.models.task import Plan, Task, TaskResult, TaskStatus
from om_harness.runtime.bus import EventBus


class TaskExecutor(Protocol):
    """The runner seam the coordinator depends on (AgentRunner implements it)."""

    async def run_task(
        self,
        task: Task,
        *,
        prior_results: list[TaskResult] | None = None,
        model_override: str | None = None,
    ) -> TaskResult: ...


class Coordinator:
    def __init__(
        self,
        *,
        runner: TaskExecutor,
        config: HarnessConfig,
        bus: EventBus | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self.runner = runner
        self.config = config
        self.bus = bus
        self.session_id = session_id
        self.run_id = run_id
        self.backoff_base_seconds = 0.05

    def _emit(self, event_type: EventType, **data: object) -> None:
        if self.bus is not None:
            self.bus.publish_sync(
                make_event(event_type, session_id=self.session_id, run_id=self.run_id, **data)
            )

    async def execute_plan(
        self,
        plan: Plan,
        *,
        retries: int = 0,
        model_override: str | None = None,
    ) -> list[TaskResult]:
        """Run the whole plan; returns results in deterministic plan order."""
        order = plan.topological_order()
        semaphore = asyncio.Semaphore(self.config.max_concurrency)
        completed: dict[str, TaskResult] = {}
        pending = list(order)

        while pending:
            ready: list[Task] = []
            skippable: list[Task] = []
            for candidate in pending:
                dep_states = [completed[d] for d in candidate.depends_on if d in completed]
                if any(r.status != TaskStatus.completed for r in dep_states):
                    skippable.append(candidate)
                elif all(d in completed for d in candidate.depends_on):
                    ready.append(candidate)
            if not ready and not skippable:  # pragma: no cover - DAG validator prevents
                break

            for task in skippable:
                completed[task.id] = TaskResult(
                    task_id=task.id,
                    status=TaskStatus.skipped,
                    summary="skipped: dependency did not complete",
                )
                self._emit(EventType.TASK_FAILED, task_id=task.id, status="skipped")

            if ready:
                results = await asyncio.gather(
                    *(
                        self._run_with_retry(
                            t,
                            prior_results=self._dep_results(t, completed),
                            retries=retries,
                            model_override=model_override,
                            semaphore=semaphore,
                        )
                        for t in ready
                    )
                )
                for t, result in zip(ready, results, strict=True):
                    completed[t.id] = result

            pending = [t for t in pending if t.id not in completed]

        # Anything left has an unsatisfiable dependency chain.
        for task in pending:
            completed[task.id] = TaskResult(
                task_id=task.id,
                status=TaskStatus.skipped,
                summary="skipped: dependency did not complete",
            )

        return [completed[t.id] for t in order]

    @staticmethod
    def _dep_results(task: Task, completed: dict[str, TaskResult]) -> list[TaskResult] | None:
        if not task.depends_on:
            return None
        return [completed[d] for d in task.depends_on if d in completed]

    async def _run_with_retry(
        self,
        task: Task,
        *,
        prior_results: list[TaskResult] | None,
        retries: int,
        model_override: str | None,
        semaphore: asyncio.Semaphore,
    ) -> TaskResult:
        self._emit(EventType.TASK_STARTED, task_id=task.id, title=task.title)
        last_result: TaskResult | None = None
        for attempt in range(retries + 1):
            if attempt > 0:
                await asyncio.sleep(self.backoff_base_seconds * (2 ** (attempt - 1)))
            async with semaphore:
                try:
                    async with asyncio.timeout(self.config.agent_timeout_seconds):
                        result = await self.runner.run_task(
                            task,
                            prior_results=prior_results,
                            model_override=model_override,
                        )
                except TimeoutError:
                    result = TaskResult(
                        task_id=task.id,
                        status=TaskStatus.failed,
                        errors=[f"task timed out after {self.config.agent_timeout_seconds:.1f}s"],
                    )
                except asyncio.CancelledError:
                    self._emit(EventType.TASK_FAILED, task_id=task.id, error="cancelled")
                    raise
                except Exception as exc:
                    result = TaskResult(
                        task_id=task.id, status=TaskStatus.failed, errors=[str(exc)]
                    )
            last_result = result
            if result.status == TaskStatus.completed:
                break
            self._emit(EventType.TASK_FAILED, task_id=task.id, attempt=attempt, error=result.errors)
        self._emit(
            EventType.TASK_COMPLETED
            if last_result and last_result.status == TaskStatus.completed
            else EventType.TASK_FAILED,
            task_id=task.id,
            status=last_result.status.value if last_result else "unknown",
        )
        assert last_result is not None
        return last_result
