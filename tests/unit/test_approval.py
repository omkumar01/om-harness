"""Contract tests for the approval engine and guarded tool executor.

Key safety property proven here: a mutating/destructive tool is never executed
unless the configured approval policy allows it.
"""

from __future__ import annotations

from typing import Any

import pytest

from om_harness.config.loader import ApprovalConfig, ApprovalPolicy
from om_harness.models.events import EventType
from om_harness.runtime.bus import EventBus
from om_harness.tools.approval import ApprovalDecision, ApprovalEngine
from om_harness.tools.base import Permission, ToolContext
from om_harness.tools.files import WriteFile
from om_harness.tools.registry import GuardedToolExecutor, ToolRegistry


@pytest.fixture
def ctx(tmp_path: Any) -> ToolContext:
    return ToolContext(repo_root=tmp_path)


def _engine(
    policy: ApprovalPolicy,
    *,
    interactive: bool = False,
    confirmer=None,
    allowlist: set[str] | None = None,
) -> ApprovalEngine:
    return ApprovalEngine(
        ApprovalConfig(policy=policy, allowlist=allowlist or set()),
        interactive=interactive,
        confirmer=confirmer,
    )


def test_read_only_always_approved(ctx: ToolContext) -> None:
    engine = _engine(ApprovalPolicy.deny)
    assert engine.evaluate("read_file", Permission.read_only) == ApprovalDecision.approved


def test_deny_policy_blocks_everything_else() -> None:
    engine = _engine(ApprovalPolicy.deny)
    assert engine.evaluate("write_file", Permission.mutating) == ApprovalDecision.denied
    assert engine.evaluate("git_restore", Permission.destructive) == ApprovalDecision.denied


def test_auto_policy_approves_mutating_but_gates_destructive() -> None:
    engine = _engine(ApprovalPolicy.auto)
    assert engine.evaluate("write_file", Permission.mutating) == ApprovalDecision.approved
    assert engine.evaluate("git_restore", Permission.destructive) == ApprovalDecision.needs_approval


def test_ask_policy_gates_both() -> None:
    engine = _engine(ApprovalPolicy.ask)
    assert engine.evaluate("write_file", Permission.mutating) == ApprovalDecision.needs_approval
    assert engine.evaluate("git_restore", Permission.destructive) == ApprovalDecision.needs_approval


def test_allowlist_policy() -> None:
    engine = _engine(ApprovalPolicy.allowlist, allowlist={"write_file"})
    assert engine.evaluate("write_file", Permission.mutating) == ApprovalDecision.approved
    assert engine.evaluate("run_shell", Permission.mutating) == ApprovalDecision.needs_approval


async def test_non_interactive_ask_denies() -> None:
    engine = _engine(ApprovalPolicy.ask, interactive=False)
    assert await engine.request("write_file", Permission.mutating) is False


async def test_interactive_ask_uses_confirmer() -> None:
    async def yes(name: str, reason: str) -> bool:
        return True

    async def no(name: str, reason: str) -> bool:
        return False

    assert await _engine(ApprovalPolicy.ask, interactive=True, confirmer=yes).request(
        "write_file", Permission.mutating
    )
    assert not await _engine(ApprovalPolicy.ask, interactive=True, confirmer=no).request(
        "write_file", Permission.mutating
    )


async def test_non_interactive_destructive_auto_denies() -> None:
    engine = _engine(ApprovalPolicy.auto, interactive=False)
    assert await engine.request("git_restore", Permission.destructive) is False


# -- guarded executor ---------------------------------------------------------


def _executor(tmp_path: Any, engine: ApprovalEngine) -> GuardedToolExecutor:
    registry = ToolRegistry()
    registry.register(WriteFile(ToolContext(repo_root=tmp_path)))
    return GuardedToolExecutor(registry=registry, approval=engine, bus=EventBus())


async def test_executor_runs_approved_tool(tmp_path: Any) -> None:
    executor = _executor(tmp_path, _engine(ApprovalPolicy.auto))
    result = await executor.execute("write_file", {"path": "x.txt", "content": "hi"})
    assert result.ok
    assert (tmp_path / "x.txt").read_text() == "hi"


async def test_executor_blocks_denied_tool_without_side_effects(tmp_path: Any) -> None:
    executor = _executor(tmp_path, _engine(ApprovalPolicy.deny))
    result = await executor.execute("write_file", {"path": "x.txt", "content": "hi"})
    assert not result.ok
    assert "denied" in (result.error or "").lower()
    assert not (tmp_path / "x.txt").exists()


async def test_executor_emits_event_trail(tmp_path: Any) -> None:
    bus = EventBus()
    registry = ToolRegistry()
    registry.register(WriteFile(ToolContext(repo_root=tmp_path)))
    executor = GuardedToolExecutor(
        registry=registry, approval=_engine(ApprovalPolicy.auto), bus=bus
    )
    await executor.execute("write_file", {"path": "x.txt", "content": "hi"})
    types = [e.type for e in bus.history]
    # auto policy approves mutating tools silently; no approval event is emitted.
    assert types == [EventType.TOOL_CALL_STARTED, EventType.TOOL_CALL_COMPLETED]


async def test_executor_emits_denial_event(tmp_path: Any) -> None:
    bus = EventBus()
    registry = ToolRegistry()
    registry.register(WriteFile(ToolContext(repo_root=tmp_path)))
    executor = GuardedToolExecutor(
        registry=registry, approval=_engine(ApprovalPolicy.deny), bus=bus
    )
    await executor.execute("write_file", {"path": "x.txt", "content": "hi"})
    types = [e.type for e in bus.history]
    assert EventType.TOOL_CALL_DENIED in types


async def test_executor_rejects_unknown_tool(tmp_path: Any) -> None:
    executor = _executor(tmp_path, _engine(ApprovalPolicy.auto))
    result = await executor.execute("does_not_exist", {})
    assert not result.ok
    assert "unknown tool" in (result.error or "").lower()


async def test_executor_validates_arguments(tmp_path: Any) -> None:
    executor = _executor(tmp_path, _engine(ApprovalPolicy.auto))
    result = await executor.execute("write_file", {"path": "x.txt"})  # missing content
    assert not result.ok
    assert "validation" in (result.error or "").lower()


async def test_executor_reports_tool_errors(tmp_path: Any) -> None:
    executor = _executor(tmp_path, _engine(ApprovalPolicy.auto))
    result = await executor.execute("write_file", {"path": "../escape.txt", "content": "x"})
    assert not result.ok
    assert "outside" in (result.error or "")
