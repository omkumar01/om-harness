"""End-to-end tests: complete coding-agent flows in a real temp git repo,
driven by scripted offline models (FunctionModel) — no network, no keys.

Flow proven here: init session -> plan -> inspect repo via tools -> edit code
-> run tests -> report -> persist state -> resume later.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import FunctionModel

from om_harness.harness import Harness
from om_harness.models.task import TaskStatus


@pytest.fixture
def repo(tmp_path: Any) -> Any:
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    )
    return tmp_path


def scripted_coder(final_answer: str) -> Any:
    """Model that: reads calc.py, edits the bug, runs tests, then answers."""

    def make() -> FunctionModel:
        async def respond(messages: list[ModelMessage], agent_info: Any) -> ModelResponse:
            saw_tool_results = sum(
                1
                for m in messages
                for part in getattr(m, "parts", [])
                if getattr(part, "part_kind", "") == "tool-return"
            )
            if saw_tool_results == 0:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="read_file", args={"path": "calc.py"}, tool_call_id="c1"
                        )
                    ]
                )
            if saw_tool_results == 1:
                return ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="edit_file",
                            args={
                                "path": "calc.py",
                                "old_string": "return a - b",
                                "new_string": "return a + b",
                            },
                            tool_call_id="c2",
                        )
                    ]
                )
            if saw_tool_results == 2:
                return ModelResponse(
                    parts=[ToolCallPart(tool_name="run_tests", args={}, tool_call_id="c3")]
                )
            return ModelResponse(parts=[TextPart(content=final_answer)])

        return FunctionModel(respond)

    return make


def test_complete_coding_flow_with_mocked_model(repo: Any) -> None:
    # auto: mutating tools (edit/run_tests) run without prompting, destructive still gated.
    harness = Harness(repo_root=repo, env={}, approval_policy="auto")
    # Inject the scripted model in place of the mock echo model.
    harness.runner.model_factory = lambda _model_str: scripted_coder(
        "Fixed add() to use + and tests pass."
    )()

    import asyncio

    result = asyncio.run(harness.run("fix the sign bug in calc.py so the test passes"))

    assert result.status == "completed"
    assert result.results[0].status == TaskStatus.completed
    assert "tests pass" in result.results[0].summary
    # The code was actually changed
    assert "return a + b" in (repo / "calc.py").read_text()
    # Tool events were recorded in the durable event log
    events = harness.store.read_events(result.session_id)
    tools_used = {e.data.get("tool") for e in events if e.type.value == "tool.call.started"}
    assert {"read_file", "edit_file", "run_tests"} <= tools_used
    # Checkpoint persisted with the plan and task results
    checkpoint = harness.store.latest_checkpoint(result.session_id)
    assert checkpoint is not None
    assert checkpoint.task_results[0].status == TaskStatus.completed
    # Usage accounting captured model requests
    assert result.usage.requests >= 1


def test_resume_after_interrupted_session(repo: Any) -> None:
    harness = Harness(repo_root=repo, env={}, approval_policy="auto")
    harness.runner.model_factory = lambda _s: scripted_coder("done")()

    import asyncio

    first = asyncio.run(harness.run("fix calc.py"))
    assert first.status == "completed"

    # A fresh Harness instance (simulating a new process) resumes the session.
    harness2 = Harness(repo_root=repo, env={})
    harness2.runner.model_factory = lambda _s: scripted_coder("done")()
    second = asyncio.run(harness2.run("polish calc.py", resume=True, session_id=first.session_id))
    assert second.session_id == first.session_id
    session = harness2.store.load_session(second.session_id)
    assert len(session.runs) == 2


def test_state_dir_is_gitignored(repo: Any) -> None:
    Harness.init_repo(repo)
    proc = subprocess.run(
        ["git", "check-ignore", ".om-harness"],
        cwd=repo,
        capture_output=True,
        text=True,
        shell=False,
    )
    assert proc.returncode == 0, ".om-harness/ should be gitignored"


def test_parallel_plan_fans_out_and_aggregates(repo: Any) -> None:
    """Two independent read-only questions answered concurrently."""
    from om_harness.models.task import Task, TaskType

    (repo / "a.txt").write_text("alpha content\n")
    (repo / "b.txt").write_text("beta content\n")

    def make_model() -> FunctionModel:
        async def respond(messages: list[ModelMessage], agent_info: Any) -> ModelResponse:
            from pydantic_ai.messages import UserPromptPart

            user_text = " ".join(
                str(part.content)
                for m in messages
                for part in getattr(m, "parts", [])
                if isinstance(part, UserPromptPart)
            )
            if "alpha" in user_text:
                answer = "a.txt contains alpha"
            elif "beta" in user_text:
                answer = "b.txt contains beta"
            else:
                answer = f"prompt was: {user_text[:200]}"
            return ModelResponse(parts=[TextPart(content=answer)])

        return FunctionModel(respond)

    harness = Harness(repo_root=repo, env={})
    harness.runner.model_factory = lambda _s: make_model()

    tasks = [
        Task(
            id="q-a",
            title="A",
            instruction="summarize alpha",
            task_type=TaskType.explore,
            role="explorer",
        ),
        Task(
            id="q-b",
            title="B",
            instruction="summarize beta",
            task_type=TaskType.explore,
            role="explorer",
        ),
    ]
    import asyncio

    result = asyncio.run(harness.run("two summaries", tasks=tasks))
    by_id = {r.task_id: r for r in result.results}
    assert by_id["q-a"].status == TaskStatus.completed
    assert by_id["q-b"].status == TaskStatus.completed
    assert "alpha" in by_id["q-a"].summary
    assert "beta" in by_id["q-b"].summary
