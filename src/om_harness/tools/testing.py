"""Test-runner detection and execution."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from om_harness.tools.base import BaseTool, Permission, ToolError, ToolResult, cap_text
from om_harness.tools.shell import build_env, run_process


def detect_test_runner(repo_root: Path) -> tuple[str, list[str]] | None:
    """Detect the most likely test command for a repo (runner, argv-tail)."""
    has_pytest_cfg = (repo_root / "pyproject.toml").exists() or (repo_root / "pytest.ini").exists()
    has_python_tests = any(repo_root.glob("test_*.py")) or any(
        (repo_root / "tests").glob("test_*.py")
    )
    if has_pytest_cfg or has_python_tests:
        return "pytest", [sys.executable, "-m", "pytest", "-q"]
    if (repo_root / "package.json").exists():
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if npm:
            return "npm", [npm, "test", "--silent"]
    return None


class RunTestsArgs(BaseModel):
    extra_args: list[str] = Field(default_factory=list, description="Extra CLI args for the runner")


class RunTests(BaseTool[RunTestsArgs]):
    name = "run_tests"
    description = "Detect and run the repository's test suite (pytest or npm test)."
    permission = Permission.mutating
    Args = RunTestsArgs

    async def run(self, args: RunTestsArgs) -> ToolResult:
        detected = detect_test_runner(self.ctx.repo_root)
        if detected is None:
            raise ToolError(
                "no test runner detected (looked for pytest config/tests, package.json)"
            )
        name, argv = detected
        argv = argv + list(args.extra_args)
        code, out, err, truncated = await run_process(
            argv,
            cwd=self.ctx.repo_root,
            timeout=self.ctx.tool_timeout_seconds,
            max_output_chars=self.ctx.max_output_chars,
            env=build_env(),
        )
        output = out
        if err and name == "pytest":
            output += err  # pytest writes the summary to stdout; keep stderr for context
        text, cap_hit = cap_text(output, self.ctx.max_output_chars, "test output")
        return ToolResult(
            ok=code == 0,
            output=text,
            error=None if code == 0 else f"tests failed with exit code {code}",
            truncated=truncated or cap_hit,
            data={"runner": name, "exit_code": code},
        )
