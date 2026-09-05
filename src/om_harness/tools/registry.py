"""Tool registry and the guarded executor (approval gate + event trail)."""

from __future__ import annotations

from pydantic import ValidationError

from om_harness.models.events import EventType, make_event
from om_harness.runtime.bus import EventBus
from om_harness.tools.approval import ApprovalDecision, ApprovalEngine
from om_harness.tools.base import BaseTool, ToolError, ToolResult


class ToolRegistry:
    """Name-keyed catalog of available tools with schema introspection."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool {tool.name!r} already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolError(f"unknown tool {name!r}") from None

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, object]]:
        """JSON-friendly tool descriptions (for UIs and model schemas)."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "permission": tool.permission.value,
                "parameters": tool.spec_parameters(),
            }
            for tool in sorted(self._tools.values(), key=lambda t: t.name)
        ]


class GuardedToolExecutor:
    """The only path the agent runtime uses to execute tools.

    Sequence per call: validate arguments -> emit TOOL_CALL_STARTED ->
    approval verdict -> run (or deny) -> emit completion/denial/failure event.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        approval: ApprovalEngine,
        bus: EventBus | None = None,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self.registry = registry
        self.approval = approval
        self.bus = bus
        self.session_id = session_id
        self.run_id = run_id

    async def execute(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        task_id: str | None = None,
        agent: str | None = None,
    ) -> ToolResult:
        def emit(event_type: EventType, **data: object) -> None:
            if self.bus is not None:
                self.bus.publish_sync(
                    make_event(
                        event_type,
                        session_id=self.session_id,
                        run_id=self.run_id,
                        task_id=task_id,
                        agent=agent,
                        tool=name,
                        **data,
                    )
                )

        try:
            tool = self.registry.get(name)
        except ToolError:
            emit(EventType.TOOL_CALL_FAILED, error=f"unknown tool {name!r}")
            return ToolResult.fail(f"unknown tool {name!r}")

        try:
            args = tool.args_model.model_validate(arguments)
        except ValidationError as exc:
            emit(
                EventType.TOOL_CALL_FAILED,
                error=f"argument validation failed: {exc.error_count()} error(s)",
            )
            return ToolResult.fail(
                f"argument validation failed: {exc.errors(include_url=False)[0]['msg']}"
            )

        emit(EventType.TOOL_CALL_STARTED, arguments=self._safe_args(arguments))
        decision = self.approval.evaluate(name, tool.permission)
        if decision == ApprovalDecision.denied:
            emit(EventType.APPROVAL_DENIED, permission=tool.permission.value)
            emit(EventType.TOOL_CALL_DENIED, reason="denied by approval policy")
            return ToolResult.fail(f"tool {name!r} denied by approval policy")
        if decision == ApprovalDecision.needs_approval:
            granted = await self.approval.request(name, tool.permission)
            emit(
                EventType.APPROVAL_GRANTED if granted else EventType.APPROVAL_DENIED,
                permission=tool.permission.value,
            )
            if not granted:
                emit(EventType.TOOL_CALL_DENIED, reason="user declined approval")
                return ToolResult.fail(f"tool {name!r} not approved by user")

        try:
            result = await tool.run(args)
        except ToolError as exc:
            emit(EventType.TOOL_CALL_FAILED, error=str(exc))
            return ToolResult.fail(str(exc))
        except Exception as exc:
            emit(EventType.TOOL_CALL_FAILED, error=f"unexpected tool error: {exc}")
            return ToolResult.fail(f"unexpected tool error: {exc}")

        event_type = EventType.TOOL_CALL_COMPLETED if result.ok else EventType.TOOL_CALL_FAILED
        emit(event_type, ok=result.ok, truncated=result.truncated)
        return result

    @staticmethod
    def _safe_args(arguments: dict[str, object]) -> dict[str, object]:
        """Trim large argument payloads before they hit the event log."""
        safe: dict[str, object] = {}
        for key, value in arguments.items():
            if isinstance(value, str) and len(value) > 500:
                safe[key] = value[:500] + f"... [{len(value)} chars total]"
            else:
                safe[key] = value
        return safe
