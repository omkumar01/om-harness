"""Contract tests for the agent runtime runner (PydanticAI bridge, events,
timeouts, budget wiring) — all offline via FunctionModel mocks."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ThinkingPart
from pydantic_ai.models.function import FunctionModel

from om_harness.config.loader import HarnessConfig
from om_harness.context.assembler import ContextAssembler
from om_harness.models.events import EventType
from om_harness.models.task import Task, TaskStatus, TaskType
from om_harness.providers.registry import ProviderRegistry
from om_harness.providers.router import ModelRouter
from om_harness.runtime.bus import EventBus
from om_harness.runtime.runner import AgentRunner
from om_harness.tools.approval import ApprovalEngine
from om_harness.tools.base import ToolContext
from om_harness.tools.files import ReadFile
from om_harness.tools.registry import GuardedToolExecutor, ToolRegistry


@pytest.fixture
def tmp_repo(tmp_path: Any) -> Any:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text("value = 1\n")
    return tmp_path


def _runner(tmp_repo: Any, model: FunctionModel, bus: EventBus) -> AgentRunner:
    config = HarnessConfig()
    registry = ToolRegistry()
    tool_ctx = ToolContext(repo_root=tmp_repo)
    registry.register(ReadFile(tool_ctx))
    executor = GuardedToolExecutor(
        registry=registry,
        approval=ApprovalEngine(config.approval, interactive=False),
        bus=bus,
    )
    return AgentRunner(
        executor=executor,
        assembler=ContextAssembler(config),
        router=ModelRouter(config.routing, ProviderRegistry(env={})),
        provider_registry=ProviderRegistry(env={}),
        config=config,
        bus=bus,
        session_id="sess-test",
        run_id="run-test",
        model_factory=lambda _model_str: model,
    )


async def test_run_task_returns_task_result_with_summary(tmp_repo: Any) -> None:
    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        return ModelResponse(parts=[TextPart(content="I read the file; value is 1")])

    bus = EventBus()
    runner = _runner(tmp_repo, FunctionModel(respond), bus)
    task = Task(id="t1", title="read", instruction="read src/mod.py", task_type=TaskType.explore)
    result = await runner.run_task(task)
    assert result.status == TaskStatus.completed
    assert "value is 1" in result.summary
    assert result.task_id == "t1"


async def test_run_task_emits_expected_event_trail(tmp_repo: Any) -> None:
    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        return ModelResponse(parts=[TextPart(content="done")])

    bus = EventBus()
    runner = _runner(tmp_repo, FunctionModel(respond), bus)
    task = Task(id="t1", title="x", instruction="do x")
    await runner.run_task(task)
    types = [e.type for e in bus.history]
    assert types == [
        EventType.AGENT_STARTED,
        EventType.MODEL_CALL_STARTED,
        EventType.MODEL_CALL_COMPLETED,
        EventType.AGENT_COMPLETED,
    ]


async def test_run_task_tool_bridge_executes_registry_tools(tmp_repo: Any) -> None:
    """The model's tool call must flow through the guarded executor."""

    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        saw_tool_result = any(
            getattr(part, "part_kind", "") == "tool-return"
            for m in messages
            for part in getattr(m, "parts", [])
        )
        if not saw_tool_result:
            from pydantic_ai.messages import ToolCallPart

            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="read_file",
                        args={"path": "src/mod.py"},
                        tool_call_id="c1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="read complete")])

    bus = EventBus()
    runner = _runner(tmp_repo, FunctionModel(respond), bus)
    task = Task(id="t1", title="x", instruction="read the file")
    result = await runner.run_task(task)
    assert result.status == TaskStatus.completed
    # The tool call went through the guarded executor and emitted tool events.
    types = [e.type for e in bus.history]
    assert EventType.TOOL_CALL_STARTED in types
    assert EventType.TOOL_CALL_COMPLETED in types


async def test_run_task_denied_tool_surfaces_error_to_model(tmp_repo: Any) -> None:
    from pydantic_ai.messages import ToolCallPart

    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        saw_tool_result = any(
            getattr(part, "part_kind", "") == "tool-return"
            for m in messages
            for part in getattr(m, "parts", [])
        )
        if not saw_tool_result:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="write_file",
                        args={"path": "x.txt", "content": "hi"},
                        tool_call_id="c1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="gave up")])

    bus = EventBus()
    config = HarnessConfig(approval={"policy": "deny"})  # type: ignore[dict-item]
    registry = ToolRegistry()
    from om_harness.tools.files import WriteFile

    registry.register(WriteFile(ToolContext(repo_root=tmp_repo)))
    executor = GuardedToolExecutor(
        registry=registry, approval=ApprovalEngine(config.approval), bus=bus
    )
    runner = AgentRunner(
        executor=executor,
        assembler=ContextAssembler(config),
        router=ModelRouter(config.routing, ProviderRegistry(env={})),
        provider_registry=ProviderRegistry(env={}),
        config=config,
        bus=bus,
        model_factory=lambda _s: FunctionModel(respond),
    )
    result = await runner.run_task(Task(id="t1", title="x", instruction="read"))
    # The agent still completes, but sees the denial error text.
    assert result.status == TaskStatus.completed
    assert EventType.TOOL_CALL_DENIED in [e.type for e in bus.history]


async def test_run_task_timeout_marks_failed(tmp_repo: Any) -> None:
    async def slow_respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        await asyncio.sleep(5)
        return ModelResponse(parts=[TextPart(content="late")])

    bus = EventBus()
    config = HarnessConfig(agent_timeout_seconds=0.1)
    registry = ToolRegistry()
    registry.register(ReadFile(ToolContext(repo_root=tmp_repo)))
    runner = AgentRunner(
        executor=GuardedToolExecutor(registry=registry, approval=ApprovalEngine(config.approval)),
        assembler=ContextAssembler(config),
        router=ModelRouter(config.routing, ProviderRegistry(env={})),
        provider_registry=ProviderRegistry(env={}),
        config=config,
        bus=bus,
        model_factory=lambda _s: FunctionModel(slow_respond),
    )
    result = await runner.run_task(Task(id="t1", title="x", instruction="go"))
    assert result.status == TaskStatus.failed
    assert "timed out" in (result.errors[0] if result.errors else "")


def test_budget_maps_config_to_usage_limits(tmp_repo: Any) -> None:
    from om_harness.runtime.runner import _usage_limits

    config = HarnessConfig(
        budget={"max_input_tokens": 100, "max_output_tokens": 50, "max_requests": 3}  # type: ignore[dict-item]
    )
    limits = _usage_limits(config.budget)
    assert limits.input_tokens_limit == 100
    assert limits.output_tokens_limit == 50
    assert limits.request_limit == 3


async def test_streaming_deltas_published_as_events(tmp_repo: Any) -> None:
    """A streaming model produces MESSAGE_DELTA events with kind text/thinking."""
    from pydantic_ai.models.function import DeltaThinkingPart

    async def stream_fn(messages, agent_info):  # type: ignore[no-untyped-def]
        yield {0: DeltaThinkingPart(content="let me think")}
        yield "the answer is 4"

    bus = EventBus()
    runner = _runner(tmp_repo, FunctionModel(stream_function=stream_fn), bus)
    task = Task(id="t1", title="x", instruction="compute 2+2")
    result = await runner.run_task(task)
    assert result.status == TaskStatus.completed
    deltas = [e for e in bus.history if e.type == EventType.MESSAGE_DELTA]
    kinds = [d.data["kind"] for d in deltas]
    assert "thinking" in kinds
    assert "text" in kinds
    text = "".join(d.data["delta"] for d in deltas if d.data["kind"] == "text")
    assert "the answer is 4" in text


async def test_thinking_extracted_from_non_streaming_result(tmp_repo: Any) -> None:
    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        return ModelResponse(
            parts=[ThinkingPart(content="pondering"), TextPart(content="answer 4")]
        )

    bus = EventBus()
    runner = _runner(tmp_repo, FunctionModel(respond), bus)
    result = await runner.run_task(Task(id="t1", title="x", instruction="q"))
    assert result.status == TaskStatus.completed
    completed = [e for e in bus.history if e.type == EventType.AGENT_COMPLETED]
    assert "pondering" in completed[-1].data["thinking"]


def test_unset_budget_yields_unlimited_limits() -> None:
    """PydanticAI's UsageLimits defaults request_limit to 50 when left
    implicit; an unset budget must explicitly mean unlimited."""
    from om_harness.runtime.runner import _usage_limits

    limits = _usage_limits(HarnessConfig().budget)
    assert limits.request_limit is None
    assert limits.input_tokens_limit is None
    assert limits.output_tokens_limit is None
    assert limits.cost_limit is None
