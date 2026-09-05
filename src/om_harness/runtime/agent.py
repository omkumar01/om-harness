"""AgentFactory: turns harness specs into PydanticAI Agent instances.

The bridge between the om-harness tool registry and PydanticAI is a small,
isolated function: each registry tool becomes a typed single-argument async
function whose schema PydanticAI derives, with execution routed through the
GuardedToolExecutor (approval gating + event trail). This is the only module
that touches PydanticAI's function-schema internals.
"""

from __future__ import annotations

from typing import Any

from pydantic.json_schema import GenerateJsonSchema
from pydantic_ai import Agent

# PydanticAI's function-schema builder is technically private API; it is
# pinned behind this single factory so upgrades only touch this file.
from pydantic_ai import _function_schema as _pa_function_schema
from pydantic_ai.messages import (
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)
from pydantic_ai.tools import Tool

from om_harness.models.events import EventType, make_event
from om_harness.runtime.bus import EventBus
from om_harness.tools.base import BaseTool
from om_harness.tools.registry import GuardedToolExecutor


def make_stream_handler(
    bus: EventBus | None,
    *,
    session_id: str | None,
    run_id: str | None,
    task_id: str,
    agent: str,
) -> Any:
    """Event-stream handler: PydanticAI stream events -> MESSAGE_DELTA events.

    Both text and thinking deltas flow through one handler (verified against
    pydantic-ai 2.40: PartStartEvent/PartDeltaEvent wrap TextPart and
    ThinkingPart / their deltas).
    """

    async def handler(ctx: Any, events: Any) -> None:
        if bus is None:
            return
        async for event in events:
            if not isinstance(event, (PartStartEvent, PartDeltaEvent)):
                continue
            kind: str | None = None
            delta: str | None = None
            if isinstance(event, PartStartEvent):
                if isinstance(event.part, ThinkingPart):
                    kind, delta = "thinking", event.part.content
                elif isinstance(event.part, TextPart):
                    kind, delta = "text", event.part.content
            elif isinstance(event, PartDeltaEvent):
                if isinstance(event.delta, ThinkingPartDelta):
                    kind, delta = "thinking", event.delta.content_delta
                elif isinstance(event.delta, TextPartDelta):
                    kind, delta = "text", event.delta.content_delta
            if kind and delta:
                bus.publish_sync(
                    make_event(
                        EventType.MESSAGE_DELTA,
                        session_id=session_id,
                        run_id=run_id,
                        task_id=task_id,
                        agent=agent,
                        kind=kind,
                        delta=delta,
                    )
                )

    return handler


def extract_thinking(all_messages: list[Any]) -> str:
    """Concatenated thinking content from a completed run's messages."""
    parts: list[str] = []
    for message in all_messages:
        for part in getattr(message, "parts", []):
            if isinstance(part, ThinkingPart) and part.content:
                parts.append(part.content)
    return "\n".join(parts)


def supports_streaming(model: Any) -> bool:
    """Whether the model can serve streamed requests.

    Real providers always can; a non-streaming ``FunctionModel`` cannot, and
    attaching an event handler to it would fail the whole request.
    """
    stream_function = getattr(model, "stream_function", None)
    return not (stream_function is None and type(model).__name__ == "FunctionModel")


class AgentFactory:
    def __init__(self, executor: GuardedToolExecutor) -> None:
        self.executor = executor
        self.registry = executor.registry

    @property
    def bus(self) -> EventBus | None:
        return self.executor.bus

    def build(
        self,
        *,
        model: Any,
        system_prompt: str,
        agent_name: str,
        tool_names: list[str] | None = None,
        retries: int = 1,
    ) -> Agent:
        names = tool_names if tool_names is not None else self.registry.names()
        tools = [self._bridge_tool(self.registry.get(name), agent_name) for name in names]
        return Agent(
            model,
            tools=tools,
            system_prompt=system_prompt,
            name=f"om-harness:{agent_name}",
            retries=retries,
        )

    def _bridge_tool(self, tool: BaseTool, agent_name: str) -> Tool:
        """Wrap a registry tool as a PydanticAI tool via the guarded executor."""
        args_model = tool.args_model
        executor = self.executor

        async def _invoke(args: Any) -> str:
            result = await executor.execute(tool.name, args.model_dump(), agent=agent_name)
            if result.ok:
                return result.output
            return f"TOOL_ERROR: {result.error}"

        _invoke.__name__ = tool.name
        _invoke.__qualname__ = tool.name
        _invoke.__doc__ = tool.description
        # Annotate explicitly (rather than in the signature) so the runtime
        # sees the concrete Args model of this specific tool.
        _invoke.__annotations__ = {"args": args_model, "return": str}

        function_schema = _pa_function_schema.function_schema(
            _invoke, GenerateJsonSchema, tool_name=tool.name
        )
        return Tool(_invoke, function_schema=function_schema)
