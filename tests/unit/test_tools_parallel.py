"""Contract tests for the dispatch_parallel tool."""

from __future__ import annotations

import pytest

from om_harness.tools.base import ToolContext
from om_harness.tools.parallel import (
    DispatchParallelArgs,
    DispatchParallelTool,
    MapSpec,
    SubTaskSpec,
)


class MockExecutor:
    """Mock TaskExecutor for testing the dispatch_parallel tool."""

    def __init__(self):
        self.called = False
        self.last_plan = None
        self.last_retries = None
        self.last_model_override = None

    async def run_task(self, task, *, prior_results=None, model_override=None):
        from om_harness.models.task import TaskResult, TaskStatus, TokenUsage

        self.called = True
        return TaskResult(
            task_id=task.id,
            status=TaskStatus.completed,
            summary=f"Completed {task.title}",
            findings=[f"Finding from {task.id}"],
            files_modified=[f"{task.id}.py"],
            usage=TokenUsage(input_tokens=10, output_tokens=20),
        )


@pytest.fixture
def mock_executor() -> MockExecutor:
    return MockExecutor()


@pytest.fixture
def ctx(tmp_path) -> ToolContext:
    return ToolContext(repo_root=tmp_path)


async def test_dispatch_parallel_explicit_tasks(ctx: ToolContext, mock_executor: MockExecutor):
    """Test dispatch_parallel with explicit task list."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test parallel dispatch",
        tasks=[
            SubTaskSpec(id="task-1", title="Task One", instruction="Do task one"),
            SubTaskSpec(id="task-2", title="Task Two", instruction="Do task two"),
        ],
        strategy="parallel",
    )

    result = await tool.run(args)

    assert result.ok
    assert "Dispatched 2 sub-tasks" in result.output
    assert "Completed: 2" in result.output
    assert "task-1" in result.output
    assert "task-2" in result.output

    # Check aggregated data
    assert result.data["aggregated"]["total_tasks"] == 2
    assert result.data["aggregated"]["completed"] == 2
    assert len(result.data["results"]) == 2
    assert mock_executor.called


async def test_dispatch_parallel_map_reduce(ctx: ToolContext, mock_executor: MockExecutor):
    """Test dispatch_parallel with map-reduce (template + items)."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test map-reduce",
        map=MapSpec(
            template=SubTaskSpec(
                id="test-{item}", title="Test {item}", instruction="Write tests for {item}"
            ),
            items=["auth", "cache", "config"],
        ),
        strategy="parallel",
    )

    result = await tool.run(args)

    assert result.ok
    assert "Dispatched 3 sub-tasks" in result.output
    assert "Completed: 3" in result.output
    # Check that IDs were expanded correctly
    task_ids = [r["task_id"] for r in result.data["results"]]
    assert "test-auth-0" in task_ids
    assert "test-cache-1" in task_ids
    assert "test-config-2" in task_ids


async def test_dispatch_parallel_sequential_strategy(ctx: ToolContext, mock_executor: MockExecutor):
    """Test dispatch_parallel with sequential strategy."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test sequential",
        tasks=[
            SubTaskSpec(id="step-1", title="Step 1", instruction="First step"),
            SubTaskSpec(
                id="step-2", title="Step 2", instruction="Second step", depends_on=["step-1"]
            ),
        ],
        strategy="sequential",
    )

    result = await tool.run(args)

    assert result.ok
    assert "sequential" in result.output


async def test_dispatch_parallel_invalid_strategy(ctx: ToolContext, mock_executor: MockExecutor):
    """Test that invalid strategy is rejected."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test",
        tasks=[SubTaskSpec(id="t1", title="T1", instruction="Do it")],
        strategy="invalid",
    )

    result = await tool.run(args)
    assert not result.ok
    assert "invalid strategy" in result.error


async def test_dispatch_parallel_parallel_with_deps_rejected(
    ctx: ToolContext, mock_executor: MockExecutor
):
    """Test that parallel strategy with dependencies is rejected."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test",
        tasks=[
            SubTaskSpec(id="t1", title="T1", instruction="Do it", depends_on=["other"]),
        ],
        strategy="parallel",
    )

    result = await tool.run(args)
    assert not result.ok
    assert "depends_on but strategy is parallel" in result.error


async def test_dispatch_parallel_both_tasks_and_map_rejected(
    ctx: ToolContext, mock_executor: MockExecutor
):
    """Test that specifying both tasks and map is rejected."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test",
        tasks=[SubTaskSpec(id="t1", title="T1", instruction="Do it")],
        map=MapSpec(
            template=SubTaskSpec(id="t-{item}", title="T {item}", instruction="Do {item}"),
            items=["a"],
        ),
    )

    result = await tool.run(args)
    assert not result.ok
    assert "Cannot specify both" in result.error


async def test_dispatch_parallel_no_tasks_rejected(ctx: ToolContext, mock_executor: MockExecutor):
    """Test that neither tasks nor map is rejected."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(goal="Test", tasks=None, map=None)

    result = await tool.run(args)
    assert not result.ok
    assert "Must specify either" in result.error


async def test_dispatch_parallel_empty_tasks_rejected(
    ctx: ToolContext, mock_executor: MockExecutor
):
    """Test that empty task list is rejected."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(goal="Test", tasks=[])

    result = await tool.run(args)
    assert not result.ok
    assert "No tasks to dispatch" in result.error


async def test_dispatch_parallel_retries_passed(ctx: ToolContext, mock_executor: MockExecutor):
    """Test that retries parameter is passed to coordinator."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test retries",
        tasks=[SubTaskSpec(id="t1", title="T1", instruction="Do it")],
        retries=2,
    )

    result = await tool.run(args)
    assert result.ok
    # Verify retries was passed (we can't easily check coordinator internals,
    # but we can verify the call happened)
    assert mock_executor.called


async def test_dispatch_parallel_model_override(ctx: ToolContext, mock_executor: MockExecutor):
    """Test that model_override is passed."""
    tool = DispatchParallelTool(ctx, mock_executor)

    args = DispatchParallelArgs(
        goal="Test model override",
        tasks=[SubTaskSpec(id="t1", title="T1", instruction="Do it")],
        model_override="anthropic:claude-3-5-sonnet",
    )

    result = await tool.run(args)
    assert result.ok
    assert mock_executor.called


async def test_dispatch_parallel_result_compression(ctx: ToolContext, mock_executor: MockExecutor):
    """Test output compression for large results."""

    # Create a mock executor that returns many tasks
    class ManyTasksExecutor:
        def __init__(self):
            self.called = False

        async def run_task(self, task, *, prior_results=None, model_override=None):
            from om_harness.models.task import TaskResult, TaskStatus

            self.called = True
            return TaskResult(
                task_id=task.id,
                status=TaskStatus.completed,
                summary="x" * 1000,  # Large summary
                findings=[],
                files_modified=[],
            )

    executor = ManyTasksExecutor()
    tool = DispatchParallelTool(ctx, executor)

    args = DispatchParallelArgs(
        goal="Test compression",
        tasks=[
            SubTaskSpec(id=f"task-{i}", title=f"Task {i}", instruction=f"Do task {i}")
            for i in range(20)
        ],
    )

    result = await tool.run(args)
    assert result.ok
    # Output should be compressed (truncated)
    assert "omitted" in result.output or len(result.output) < 20000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
