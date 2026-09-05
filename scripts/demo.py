"""End-to-end demo without API keys: a scripted "coder" model performs a
real coding flow (inspect -> edit -> test) through the public Harness API.

Usage:
    uv run python scripts/demo.py [--repo /path/to/repo]

Without --repo, a disposable sample repository is created in a temp dir.
The scripted model uses PydanticAI's FunctionModel — the same machinery the
test suite uses — so the demo exercises the real agent loop, tool bridge,
approval gate, event stream, and persistence with zero network access.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import tempfile
from pathlib import Path

from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

from om_harness.harness import Harness

SAMPLE_FILES = {
    "calc.py": "def add(a, b):\n    return a - b  # BUG: should be +\n",
    "test_calc.py": ("from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"),
}


def make_sample_repo(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=base, check=True, capture_output=True, shell=False)
    for name, content in SAMPLE_FILES.items():
        (base / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=base, check=True, capture_output=True, shell=False)
    subprocess.run(
        ["git", "-c", "user.email=demo@om", "-c", "user.name=demo", "commit", "-qm", "sample"],
        cwd=base,
        check=True,
        capture_output=True,
        shell=False,
    )
    return base


def scripted_coder_model() -> FunctionModel:
    """A model script: read the file, fix the bug, run tests, then summarize."""

    async def respond(messages: list[ModelMessage], agent_info: object) -> ModelResponse:
        from pydantic_ai.messages import ToolReturnPart

        returns = [
            p for m in messages for p in getattr(m, "parts", []) if isinstance(p, ToolReturnPart)
        ]
        if not returns:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="read_file", args={"path": "calc.py"}, tool_call_id="1")
                ]
            )
        if len(returns) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="edit_file",
                        args={
                            "path": "calc.py",
                            "old_string": "return a - b  # BUG: should be +",
                            "new_string": "return a + b",
                        },
                        tool_call_id="2",
                    )
                ]
            )
        if len(returns) == 2:
            return ModelResponse(
                parts=[ToolCallPart(tool_name="run_tests", args={}, tool_call_id="3")]
            )
        goal = next(
            (
                str(p.content)
                for m in messages
                for p in getattr(m, "parts", [])
                if isinstance(p, UserPromptPart)
            ),
            "",
        )
        summary = (
            f"Fixed add() in calc.py (sign bug), ran the test suite: green. Goal was: {goal[:120]}"
        )
        return ModelResponse(parts=[TextPart(content=summary)])

    return FunctionModel(respond)


async def demo(repo: Path) -> None:
    Harness.init_repo(repo)
    harness = Harness(repo_root=repo, env={}, approval_policy="auto")
    # Demo-only seam: swap the resolved model for the scripted coder.
    harness.runner.model_factory = lambda _model_str: scripted_coder_model()

    offset = len(harness.bus.history)
    outcome = await harness.run("fix the sign bug in calc.py so test_add passes")

    from om_harness.config.loader import Verbosity
    from om_harness.ui.components import event_to_display, outcome_to_summary
    from om_harness.ui.terminal import TerminalRenderer

    renderer = TerminalRenderer()
    for event in harness.bus.history[offset:]:
        display = event_to_display(event, Verbosity.verbose)
        if display is not None:
            renderer.line(display)
    renderer.summary(outcome_to_summary(outcome))

    print(f"\n--- {repo / 'calc.py'} after the run ---")
    print((repo / "calc.py").read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None, help="Existing repository to run in")
    args = parser.parse_args()

    if args.repo:
        repo = args.repo.resolve()
    else:
        repo = make_sample_repo(Path(tempfile.mkdtemp(prefix="om-harness-demo-")) / "demo")
        print(f"Created sample repo: {repo}")

    asyncio.run(demo(repo))


if __name__ == "__main__":
    main()
