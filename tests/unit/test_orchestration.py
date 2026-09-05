"""Contract tests for orchestration: planner, coordinator, strategies.

Deterministic async tests prove:
- parallel plans are NOT serialized (tasks overlap in time),
- fan-in aggregation is deterministic (declaration order, not completion order),
- dependent tasks run only after their dependencies complete,
- failed dependencies cause skips rather than pointless launches,
- coordinator enforces timeouts, retries with backoff, and cancellation.
"""

from __future__ import annotations

import asyncio

from om_harness.config.loader import HarnessConfig
from om_harness.models.events import EventType
from om_harness.models.task import (
    Plan,
    StrategyKind,
    Task,
    TaskResult,
    TaskStatus,
    TaskType,
)
from om_harness.orchestration.coordinator import Coordinator
from om_harness.orchestration.planner import Planner
from om_harness.runtime.bus import EventBus


class FakeRunner:
    """Scriptable stand-in for AgentRunner recording concurrency behavior."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.events: list[str] = []  # "start:<id>" / "end:<id>"
        self.scripts: dict[str, object] = {}
        self.fail_ids: set[str] = set()
        self.fail_times: dict[str, int] = {}

    async def run_task(
        self,
        task: Task,
        *,
        prior_results: list[TaskResult] | None = None,
        model_override: str | None = None,
    ) -> TaskResult:
        self.calls.append(task.id)
        self.events.append(f"start:{task.id}")
        script = self.scripts.get(task.id)
        try:
            if script is not None:
                await script
            if task.id in self.fail_ids:
                remaining = self.fail_times.get(task.id, 1)
                self.fail_times[task.id] = remaining - 1
                if remaining > 0:
                    return TaskResult(
                        task_id=task.id,
                        status=TaskStatus.failed,
                        summary="boom",
                        errors=["boom"],
                    )
            self.events.append(f"end:{task.id}")
            return TaskResult(task_id=task.id, summary=f"done {task.id}")
        except asyncio.CancelledError:
            self.events.append(f"cancel:{task.id}")
            raise


def _coordinator(runner: FakeRunner, max_concurrency: int = 4) -> Coordinator:
    config = HarnessConfig(max_concurrency=max_concurrency)
    return Coordinator(runner=runner, config=config, bus=EventBus())


# -- planner -------------------------------------------------------------------


def test_planner_defaults_to_single_task_plan() -> None:
    plan = Planner(HarnessConfig()).build_plan("fix the bug")
    assert plan.strategy == StrategyKind.single
    assert len(plan.tasks) == 1


def test_planner_builds_reviewer_plan_with_dependency() -> None:
    plan = Planner(HarnessConfig()).build_plan("add feature and review it", strategy="reviewer")
    assert plan.strategy == StrategyKind.reviewer
    impl, review = plan.tasks
    assert review.depends_on == [impl.id]
    assert review.task_type == TaskType.review


def test_planner_respects_explicit_tasks() -> None:
    tasks = [
        Task(id="a", title="A", instruction="do a", task_type=TaskType.explore),
        Task(id="b", title="B", instruction="do b", task_type=TaskType.implement),
    ]
    plan = Planner(HarnessConfig()).build_plan("two things", tasks=tasks)
    assert [t.id for t in plan.tasks] == ["a", "b"]


def test_planner_sequential_keyword_detection() -> None:
    plan = Planner(HarnessConfig()).build_plan("explore the repo then implement the fix")
    assert plan.strategy == StrategyKind.sequential


# -- coordinator ---------------------------------------------------------------


async def test_sequential_plan_runs_in_dependency_order() -> None:
    runner = FakeRunner()
    coordinator = _coordinator(runner)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.sequential,
        tasks=[
            Task(id="a", title="A", instruction="a"),
            Task(id="b", title="B", instruction="b", depends_on=["a"]),
        ],
    )
    results = await coordinator.execute_plan(plan)
    assert runner.calls == ["a", "b"]
    assert [r.task_id for r in results] == ["a", "b"]
    assert all(r.status == TaskStatus.completed for r in results)


async def test_parallel_plan_overlaps_execution() -> None:
    """Task 'a' waits for task 'b' to have started before finishing.

    If the coordinator serialized independent tasks, this would deadlock and
    the test would time out — proving parallel fan-out really happens.
    """
    runner = FakeRunner()
    gate_b_started = asyncio.Event()

    async def script_a() -> None:
        await asyncio.wait_for(gate_b_started.wait(), timeout=2.0)

    async def script_b() -> None:
        gate_b_started.set()
        await asyncio.sleep(0.01)

    runner.scripts["a"] = script_a()
    runner.scripts["b"] = script_b()

    coordinator = _coordinator(runner)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.parallel,
        tasks=[
            Task(id="a", title="A", instruction="a"),
            Task(id="b", title="B", instruction="b"),
        ],
    )
    results = await coordinator.execute_plan(plan)
    assert len(results) == 2
    # Deterministic aggregation: declaration order, not completion order.
    assert [r.task_id for r in results] == ["a", "b"]


async def test_parallel_wave_starts_before_first_finishes() -> None:
    runner = FakeRunner()

    async def script_slow() -> None:
        await asyncio.sleep(0.05)

    runner.scripts["slow"] = script_slow()
    coordinator = _coordinator(runner)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.parallel,
        tasks=[
            Task(id="slow", title="S", instruction="s"),
            Task(id="fast", title="F", instruction="f"),
        ],
    )
    await coordinator.execute_plan(plan)
    # slow started before fast ended → overlapped, not serialized
    assert runner.events.index("start:slow") < runner.events.index("end:fast")


async def test_failed_dependency_causes_skip() -> None:
    runner = FakeRunner()
    runner.fail_ids.add("a")
    coordinator = _coordinator(runner)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.sequential,
        tasks=[
            Task(id="a", title="A", instruction="a"),
            Task(id="b", title="B", instruction="b", depends_on=["a"]),
            Task(id="c", title="C", instruction="c", depends_on=["b"]),
        ],
    )
    results = await coordinator.execute_plan(plan)
    by_id = {r.task_id: r for r in results}
    assert by_id["a"].status == TaskStatus.failed
    assert by_id["b"].status == TaskStatus.skipped
    assert by_id["c"].status == TaskStatus.skipped
    assert runner.calls == ["a"]  # b and c never launched


async def test_retry_with_backoff_recovers_transient_failure() -> None:
    runner = FakeRunner()
    runner.fail_ids.add("flaky")
    runner.fail_times["flaky"] = 1  # fails once, then succeeds
    coordinator = _coordinator(runner)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.single,
        tasks=[Task(id="flaky", title="F", instruction="f")],
    )
    results = await coordinator.execute_plan(plan, retries=1)
    assert results[0].status == TaskStatus.completed
    assert runner.calls.count("flaky") == 2


async def test_retry_exhaustion_reports_failure() -> None:
    runner = FakeRunner()
    runner.fail_ids.add("broken")
    runner.fail_times["broken"] = 99
    coordinator = _coordinator(runner)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.single,
        tasks=[Task(id="broken", title="B", instruction="b")],
    )
    results = await coordinator.execute_plan(plan, retries=2)
    assert results[0].status == TaskStatus.failed
    assert runner.calls.count("broken") == 3  # initial + 2 retries


async def test_coordinator_respects_max_concurrency() -> None:
    FakeRunner()
    active = 0
    peak = 0

    class Tracked(FakeRunner):
        async def run_task(self, task, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                return await super().run_task(task, **kwargs)
            finally:
                active -= 1

    tracked = Tracked()

    async def script() -> None:
        await asyncio.sleep(0.02)

    tracked.scripts = {f"t{i}": script() for i in range(6)}
    coordinator = _coordinator(tracked, max_concurrency=2)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.parallel,
        tasks=[Task(id=f"t{i}", title=f"T{i}", instruction="x") for i in range(6)],
    )
    await coordinator.execute_plan(plan)
    assert peak <= 2


async def test_coordinator_emits_task_events() -> None:
    runner = FakeRunner()
    bus = EventBus()
    coordinator = Coordinator(runner=runner, config=HarnessConfig(), bus=bus)
    plan = Plan(
        goal="g",
        strategy=StrategyKind.single,
        tasks=[Task(id="t1", title="T", instruction="x")],
    )
    await coordinator.execute_plan(plan)
    types = [e.type for e in bus.history]
    assert EventType.TASK_STARTED in types
    assert EventType.TASK_COMPLETED in types


async def test_coordinator_timeout_cancels_hanging_task() -> None:
    runner = FakeRunner()

    async def hang() -> None:
        await asyncio.sleep(30)

    runner.scripts["hang"] = hang()
    config = HarnessConfig(agent_timeout_seconds=0.1)
    coordinator = Coordinator(runner=runner, config=config, bus=EventBus())
    plan = Plan(
        goal="g",
        strategy=StrategyKind.single,
        tasks=[Task(id="hang", title="H", instruction="x")],
    )
    results = await coordinator.execute_plan(plan)
    assert results[0].status == TaskStatus.failed
    assert "timed out" in results[0].errors[0]
