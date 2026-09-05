"""Contract tests for core Pydantic runtime models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from om_harness.models.events import Event, EventType
from om_harness.models.task import Plan, StrategyKind, Task, TaskResult, TaskStatus, TokenUsage


def test_task_result_roundtrip() -> None:
    result = TaskResult(
        task_id="t1",
        status=TaskStatus.completed,
        summary="Added the function",
        findings=["foo.py already had a helper"],
        files_modified=["src/foo.py"],
        usage=TokenUsage(input_tokens=100, output_tokens=20, requests=1),
        artifacts={"diff": "--- a/foo.py"},
    )
    dumped = result.model_dump_json()
    restored = TaskResult.model_validate_json(dumped)
    assert restored == result


def test_task_result_defaults_are_compact() -> None:
    result = TaskResult(task_id="t2")
    assert result.status == TaskStatus.completed
    assert result.summary == ""
    assert result.findings == []
    assert result.usage.input_tokens == 0


def test_token_usage_add() -> None:
    a = TokenUsage(input_tokens=100, output_tokens=10, requests=1)
    b = TokenUsage(input_tokens=50, output_tokens=5, requests=1, cost_usd=0.5)
    total = a.add(b)
    assert total.input_tokens == 150
    assert total.output_tokens == 15
    assert total.requests == 2
    assert total.cost_usd == 0.5


def test_plan_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError, match="unknown dependency"):
        Plan(
            goal="g",
            strategy=StrategyKind.sequential,
            tasks=[Task(id="a", title="A", instruction="do a", depends_on=["missing"])],
        )


def test_plan_rejects_dependency_cycle() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        Plan(
            goal="g",
            tasks=[
                Task(id="a", title="A", instruction="x", depends_on=["b"]),
                Task(id="b", title="B", instruction="y", depends_on=["a"]),
            ],
        )


def test_plan_valid() -> None:
    plan = Plan(
        goal="g",
        strategy=StrategyKind.parallel,
        tasks=[
            Task(id="a", title="A", instruction="x"),
            Task(id="b", title="B", instruction="y", depends_on=["a"]),
        ],
    )
    assert [t.id for t in plan.topological_order()] == ["a", "b"]


def test_event_has_identity_and_defaults() -> None:
    e1 = Event(type=EventType.RUN_STARTED)
    e2 = Event(type=EventType.RUN_STARTED)
    assert e1.id != e2.id
    assert e1.ts is not None
    assert e1.data == {}


def test_event_roundtrip_preserves_type() -> None:
    event = Event(
        type=EventType.TOOL_CALL_COMPLETED,
        session_id="s1",
        run_id="r1",
        task_id="t1",
        agent="implementer",
        data={"tool": "read_file", "exit_code": 0},
    )
    restored = Event.model_validate_json(event.model_dump_json())
    assert restored == event
    assert restored.type == EventType.TOOL_CALL_COMPLETED


def test_event_type_values_are_namespaced() -> None:
    for et in EventType:
        assert "." in et.value
