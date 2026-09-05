"""Mock provider: scripted models for deterministic tests and offline demos.

Wraps PydanticAI's official ``FunctionModel`` — the same machinery PydanticAI
itself uses for testing — so harness tests exercise the real agent loop,
tool-calling protocol, and message flow without any network access.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

ScriptFn = Callable[[Sequence[ModelMessage], AgentInfo], Awaitable[ModelResponse | str]]


def make_scripted_model(function: ScriptFn, model_name: str = "mock-scripted") -> FunctionModel:
    """A FunctionModel delegating to an async script ``async f(messages, info)``."""
    return FunctionModel(function)


def make_echo_model(model_name: str = "mock-echo") -> FunctionModel:
    """Minimal offline model: echoes the latest user request back."""

    async def respond(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
        last_text = ""
        for message in reversed(messages):
            content = getattr(message, "content", None)
            if isinstance(content, str) and content:
                last_text = content
                break
        return ModelResponse(parts=[TextPart(content=f"[mock:{model_name}] {last_text}")])

    return FunctionModel(respond, model_name=model_name)


def make_tool_call_then_answer(
    tool_name: str,
    tool_args: dict[str, Any],
    final_text: str = "done",
) -> FunctionModel:
    """Scripted model that calls one tool, then produces the final answer.

    The first request returns a tool-call response; every later request
    (which will contain the ToolReturnPart) returns the final text.
    """
    from pydantic_ai.messages import ToolCallPart

    async def respond(messages: list[ModelMessage], agent_info: AgentInfo) -> ModelResponse:
        saw_tool_result = any(
            getattr(part, "part_kind", "") == "tool-return"
            for message in messages
            for part in getattr(message, "parts", [])
        )
        if not saw_tool_result:
            return ModelResponse(
                parts=[ToolCallPart(tool_name=tool_name, args=tool_args, tool_call_id="mock-1")]
            )
        return ModelResponse(parts=[TextPart(content=final_text)])

    return FunctionModel(respond, model_name="mock-toolcall")
