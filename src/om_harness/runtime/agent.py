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
from pydantic_ai.tools import Tool

from om_harness.tools.base import BaseTool
from om_harness.tools.registry import GuardedToolExecutor


class AgentFactory:
    def __init__(self, executor: GuardedToolExecutor) -> None:
        self.executor = executor
        self.registry = executor.registry

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
