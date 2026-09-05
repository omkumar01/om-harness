"""AgentRunner: executes one task with one agent invocation.

Responsibilities: model selection via the router, scoped context assembly,
agent construction, timeout + budget enforcement, usage capture, and event
emission. All failures become failed TaskResults — the runner never raises
except on cancellation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from om_harness.config.loader import BudgetConfig, HarnessConfig
from om_harness.context.assembler import AssembledContext, ContextAssembler
from om_harness.models.events import EventType, make_event
from om_harness.models.task import Task, TaskResult, TaskStatus, TokenUsage
from om_harness.providers.registry import ProviderRegistry
from om_harness.providers.router import ModelRouter
from om_harness.runtime.agent import AgentFactory
from om_harness.runtime.bus import EventBus
from om_harness.tools.registry import GuardedToolExecutor


class RunnerError(Exception):
    pass


def _usage_limits(budget: BudgetConfig) -> Any | None:
    from pydantic_ai.usage import UsageLimits

    if not any(
        (
            budget.max_requests,
            budget.max_input_tokens,
            budget.max_output_tokens,
            budget.max_cost_usd,
        )
    ):
        return None
    return UsageLimits(
        request_limit=budget.max_requests,
        input_tokens_limit=budget.max_input_tokens,
        output_tokens_limit=budget.max_output_tokens,
        cost_limit=(
            __import__("decimal").Decimal(str(budget.max_cost_usd))
            if budget.max_cost_usd is not None
            else None
        ),
    )


class AgentRunner:
    """Runs one Task through one PydanticAI agent invocation."""

    def __init__(
        self,
        *,
        executor: GuardedToolExecutor,
        assembler: ContextAssembler,
        router: ModelRouter,
        provider_registry: ProviderRegistry,
        config: HarnessConfig,
        bus: EventBus | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        model_factory: Callable[[str], Any] | None = None,
    ) -> None:
        self.executor = executor
        self.assembler = assembler
        self.router = router
        self.provider_registry = provider_registry
        self.config = config
        self.bus = bus
        self.session_id = session_id
        self.run_id = run_id
        # Test seam: override model construction (defaults to the registry).
        self.model_factory = model_factory
        self.factory = AgentFactory(executor)

    def _emit(self, event_type: EventType, **data: Any) -> None:
        if self.bus is not None:
            self.bus.publish_sync(
                make_event(
                    event_type,
                    session_id=self.session_id,
                    run_id=self.run_id,
                    **data,
                )
            )

    def _resolve_model(self, task: Task, model_override: str | None) -> tuple[str, Any]:
        model_str = self.router.select(task.task_type, override=model_override)
        factory = self.model_factory or self.provider_registry.make_model
        model = factory(model_str)
        if model is None:
            raise RunnerError(f"provider for {model_str!r} is not available (missing API key?)")
        return model_str, model

    async def run_task(
        self,
        task: Task,
        *,
        prior_results: list[TaskResult] | None = None,
        model_override: str | None = None,
    ) -> TaskResult:
        """Execute one task; never raises except on cancellation."""
        try:
            model_str, model = self._resolve_model(task, model_override)
        except RunnerError as exc:
            return TaskResult(task_id=task.id, status=TaskStatus.failed, errors=[str(exc)])

        assembled: AssembledContext = self.assembler.assemble(
            task.role, task.instruction, prior_results=prior_results
        )
        agent = self.factory.build(
            model=model,
            system_prompt=assembled.system_prompt,
            agent_name=task.role,
        )

        self._emit(
            EventType.AGENT_STARTED,
            task_id=task.id,
            agent=task.role,
            model=model_str,
        )
        self._emit(EventType.MODEL_CALL_STARTED, task_id=task.id, model=model_str)
        started = time.monotonic()

        try:
            async with asyncio.timeout(self.config.agent_timeout_seconds):
                response = await agent.run(
                    assembled.user_prompt, usage_limits=_usage_limits(self.config.budget)
                )
        except TimeoutError:
            elapsed = time.monotonic() - started
            error = f"agent timed out after {elapsed:.1f}s"
            self._emit(EventType.AGENT_FAILED, task_id=task.id, agent=task.role, error=error)
            return TaskResult(task_id=task.id, status=TaskStatus.failed, errors=[error])
        except asyncio.CancelledError:
            self._emit(EventType.AGENT_FAILED, task_id=task.id, agent=task.role, error="cancelled")
            raise
        except Exception as exc:
            self._emit(
                EventType.AGENT_FAILED,
                task_id=task.id,
                agent=task.role,
                error=str(exc),
            )
            return TaskResult(task_id=task.id, status=TaskStatus.failed, errors=[str(exc)])

        usage = response.usage  # RunUsage instance in pydantic-ai 2.x
        cost = float(usage.cost) if usage.cost else None
        token_usage = TokenUsage(
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            requests=usage.requests or 0,
            cost_usd=cost,
        )
        self._emit(
            EventType.MODEL_CALL_COMPLETED,
            task_id=task.id,
            model=model_str,
            input_tokens=token_usage.input_tokens,
            output_tokens=token_usage.output_tokens,
        )
        self._emit(
            EventType.AGENT_COMPLETED,
            task_id=task.id,
            agent=task.role,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        return TaskResult(
            task_id=task.id,
            status=TaskStatus.completed,
            summary=response.output if isinstance(response.output, str) else str(response.output),
            usage=token_usage,
        )
