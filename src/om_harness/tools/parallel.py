"""DispatchParallelTool: enables agents to fan-out independent sub-tasks."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel, Field

from om_harness.models.task import Plan, StrategyKind, Task, TaskResult, TaskType
from om_harness.orchestration.coordinator import TaskExecutor
from om_harness.tools.base import BaseTool, Permission, ToolContext, ToolResult


class SubTaskSpec(BaseModel):
    """Specification for a single sub-task to dispatch."""

    id: str = Field(description="Unique identifier for this sub-task")
    title: str = Field(description="Human-readable title")
    instruction: str = Field(description="Detailed instruction for the sub-task")
    task_type: TaskType = Field(
        default=TaskType.general, description="Task flavor for model routing"
    )
    role: str = Field(
        default="implementer", description="Agent role (implementer, explorer, reviewer)"
    )
    depends_on: list[str] = Field(
        default_factory=list, description="IDs of tasks this depends on (for sequential)"
    )


class MapSpec(BaseModel):
    """Generate tasks by mapping a template over a list of items."""

    template: SubTaskSpec = Field(description="Task template with {item_var} placeholders")
    items: list[Any] = Field(min_length=1, description="Items to iterate over")
    item_var: str = Field(default="item", description="Variable name used in template placeholders")


class DispatchParallelArgs(BaseModel):
    """Arguments for dispatching parallel sub-tasks."""

    goal: str = Field(description="Overall goal these sub-tasks contribute to")
    tasks: list[SubTaskSpec] | None = Field(
        default=None, description="Explicit list of sub-tasks (alternative to map)"
    )
    map: MapSpec | None = Field(
        default=None, description="Dynamic task generation: map template over items"
    )
    strategy: str = Field(
        default="parallel",
        description="Execution strategy: 'parallel' for fan-out, 'sequential' for pipeline",
    )
    retries: int = Field(
        default=0, ge=0, le=3, description="Number of retries per sub-task on failure"
    )
    model_override: str | None = Field(
        default=None, description="Optional model override (e.g., 'anthropic:claude-3-5-sonnet')"
    )
    max_concurrency: int | None = Field(
        default=None, ge=1, le=20, description="Override max concurrency for this dispatch"
    )

    def get_tasks(self) -> list[SubTaskSpec]:
        """Resolve tasks from either explicit list or map."""
        if self.tasks is not None and self.map is not None:
            raise ValueError("Cannot specify both 'tasks' and 'map'")
        if self.tasks is not None:
            return self.tasks
        if self.map is not None:
            expanded = []
            for idx, item in enumerate(self.map.items):
                template = self.map.template
                # Replace placeholders in instruction and title
                item_var = self.map.item_var
                placeholder = f"{{{item_var}}}"
                instruction = template.instruction.replace(placeholder, str(item))
                title = template.title.replace(placeholder, str(item))
                task_id = template.id.replace(placeholder, str(item))
                # Ensure unique ID
                if len(self.map.items) > 1:
                    task_id = f"{task_id}-{idx}"
                expanded.append(
                    SubTaskSpec(
                        id=task_id,
                        title=title,
                        instruction=instruction,
                        task_type=template.task_type,
                        role=template.role,
                        depends_on=template.depends_on,
                    )
                )
            return expanded
        raise ValueError("Must specify either 'tasks' or 'map'")


class DispatchParallelTool(BaseTool[DispatchParallelArgs]):
    """Tool for dispatching multiple independent sub-tasks in parallel.

    Use when you have multiple pieces of work that can be done independently
    and concurrently. Each sub-task runs in its own agent invocation with
    isolated context. Results are aggregated and returned together.

    Sub-agents have access to ALL registered tools (files, shell, git, web, etc.).

    Example - Explicit tasks:
        goal = "Refactor the authentication module"
        tasks = [
            SubTaskSpec(id="extract-interface", title="Extract Auth Interface",
                        instruction="Create an interface for the auth module..."),
            SubTaskSpec(id="update-tests", title="Update Tests",
                        instruction="Update tests to use the new interface..."),
            SubTaskSpec(id="update-docs", title="Update Documentation",
                        instruction="Update README with new auth patterns..."),
        ]

    Example - Dynamic map-reduce:
        goal = "Add tests for all utility modules"
        map = MapSpec(
            template=SubTaskSpec(
                id="test-{item}", title="Test {item}",
                instruction="Write comprehensive tests for {item} module"
            ),
            items=["auth", "cache", "config", "logging"]
        )
    """

    name = "dispatch_parallel"
    description = (
        "Dispatch multiple independent sub-tasks to run in parallel (or sequentially). "
        "Each sub-task runs in its own agent with isolated context and FULL TOOL ACCESS. "
        "Supports explicit task lists or dynamic map-reduce (template + items). "
        "Returns aggregated results with per-task summaries, findings, and token usage."
    )
    permission = Permission.mutating
    Args = DispatchParallelArgs

    def __init__(self, ctx: ToolContext, executor: TaskExecutor) -> None:
        super().__init__(ctx)
        self._executor = executor

    async def run(self, args: DispatchParallelArgs) -> ToolResult:
        # Resolve tasks
        try:
            subtask_specs = args.get_tasks()
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        if not subtask_specs:
            return ToolResult.fail("No tasks to dispatch")

        # Build tasks
        tasks = [
            Task(
                id=t.id,
                title=t.title,
                instruction=t.instruction,
                task_type=t.task_type,
                role=t.role,
                depends_on=t.depends_on,
            )
            for t in subtask_specs
        ]

        # Determine strategy
        try:
            strategy = StrategyKind(args.strategy)
        except ValueError:
            return ToolResult.fail(
                f"invalid strategy '{args.strategy}'. Valid: {[s.value for s in StrategyKind]}"
            )

        # Validate dependencies for parallel strategy
        if strategy == StrategyKind.parallel:
            for t in tasks:
                if t.depends_on:
                    return ToolResult.fail(
                        f"task {t.id} has depends_on but strategy is parallel. "
                        "Use sequential strategy or remove dependencies."
                    )

        plan = Plan(
            goal=args.goal,
            strategy=strategy,
            tasks=tasks,
            rationale=f"User-dispatched {strategy.value} sub-tasks ({len(tasks)} tasks)",
        )

        # Execute the plan
        try:
            from om_harness.config.loader import HarnessConfig
            from om_harness.orchestration.coordinator import Coordinator

            # Use the same config but potentially override max_concurrency
            config = HarnessConfig()
            if args.max_concurrency is not None:
                config = config.model_copy(update={"max_concurrency": args.max_concurrency})

            coordinator = Coordinator(
                runner=self._executor,
                config=config,
                bus=None,  # No event bus for sub-dispatch
            )

            results = await coordinator.execute_plan(
                plan, retries=args.retries, model_override=args.model_override
            )

            # Aggregate results
            return self._aggregate_results(plan, results)

        except asyncio.CancelledError:
            return ToolResult.fail("dispatch cancelled")
        except Exception as exc:
            return ToolResult.fail(f"dispatch failed: {exc}")

    def _aggregate_results(self, plan: Plan, results: list[TaskResult]) -> ToolResult:
        """Aggregate sub-task results with compression for large outputs."""
        completed = [r for r in results if r.status.value == "completed"]
        failed = [r for r in results if r.status.value == "failed"]
        skipped = [r for r in results if r.status.value == "skipped"]

        # Build summary lines
        summary_lines = [
            f"Dispatched {len(plan.tasks)} sub-tasks ({plan.strategy.value})",
            f"Completed: {len(completed)}, Failed: {len(failed)}, Skipped: {len(skipped)}",
            "",
        ]

        # Compression threshold
        MAX_OUTPUT_CHARS = 10000
        SUMMARY_TRUNCATE = 500

        total_chars = 0
        for result in results:
            status_icon = "✓" if result.status.value == "completed" else "✗"
            line = f"  {status_icon} {result.task_id}: {result.summary[:SUMMARY_TRUNCATE]}"
            summary_lines.append(line)
            total_chars += len(line)

        # Combine all findings, files, errors
        all_findings = []
        all_files_modified = []
        all_errors = []
        total_usage = None

        for result in results:
            all_findings.extend(result.findings)
            all_files_modified.extend(result.files_modified)
            all_errors.extend(result.errors)
            if total_usage is None:
                total_usage = result.usage
            else:
                total_usage = total_usage.add(result.usage)

        output = "\n".join(summary_lines)

        # Compress if too large
        truncated = False
        if len(output) > MAX_OUTPUT_CHARS:
            # Keep first and last few lines, compress middle
            lines = output.split("\n")
            header = lines[:3]
            task_lines = lines[3:]
            if len(task_lines) > 10:
                compressed = (
                    header
                    + task_lines[:5]
                    + [f"  ... ({len(task_lines) - 10} tasks omitted) ..."]
                    + task_lines[-5:]
                )
                output = "\n".join(compressed)
                truncated = True

        return ToolResult(
            ok=len(failed) == 0,
            output=output,
            truncated=truncated,
            data={
                "results": [
                    {
                        "task_id": r.task_id,
                        "status": r.status.value,
                        "summary": r.summary,
                        "findings": r.findings,
                        "files_modified": r.files_modified,
                        "errors": r.errors,
                        "usage": r.usage.model_dump() if r.usage else None,
                    }
                    for r in results
                ],
                "aggregated": {
                    "total_tasks": len(plan.tasks),
                    "completed": len(completed),
                    "failed": len(failed),
                    "skipped": len(skipped),
                    "findings": list(dict.fromkeys(all_findings)),  # dedupe
                    "files_modified": list(set(all_files_modified)),
                    "errors": all_errors,
                    "total_usage": total_usage.model_dump() if total_usage else None,
                },
            },
        )
