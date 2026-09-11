"""Auto-detecting code formatters and linters.

Both tools follow the same auto-detection pattern as ``run_tests``: scan the
repo for evidence of a toolchain (config files + available executables) and
pick the best available runner. This keeps the agent workflow simple — no need
to know whether a repo uses ``ruff``, ``black``, or ``prettier``; the tool
detects and runs it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from om_harness.tools.base import BaseTool, Permission, ToolError, ToolResult, cap_text
from om_harness.tools.shell import _EVENT_OUTPUT_CHARS, build_env, run_process


def _has_config(repo_root: Path, names: list[str]) -> bool:
    """True if any of the given config file names exist in repo_root."""
    return any((repo_root / name).exists() for name in names)


def detect_formatter(repo_root: Path) -> tuple[str, list[str]] | None:
    """Detect the most appropriate formatter for the repo."""
    # Python
    if _has_config(repo_root, ["pyproject.toml", "setup.cfg", "ruff.toml"]) and shutil.which(
        "ruff"
    ):
        return "ruff", [sys.executable, "-m", "ruff", "format"]
    if _has_config(repo_root, ["pyproject.toml", "setup.cfg"]) and shutil.which("black"):
        return "black", [sys.executable, "-m", "black"]
    if shutil.which("isort"):
        return "isort", [sys.executable, "-m", "isort"]
    # JS/TS
    if (repo_root / "package.json").exists() and shutil.which("npx"):
        return "prettier", ["npx", "--no-install", "prettier", "--write"]
    # Go
    if _has_config(repo_root, ["go.mod"]) and shutil.which("gofmt"):
        return "gofmt", ["gofmt", "-w"]
    # Rust
    if _has_config(repo_root, ["Cargo.toml"]) and shutil.which("rustfmt"):
        return "rustfmt", ["rustfmt"]
    return None


def detect_linter(repo_root: Path) -> tuple[str, list[str]] | None:
    """Detect the most appropriate linter for the repo."""
    # Python
    if _has_config(repo_root, ["pyproject.toml", "ruff.toml"]) and shutil.which("ruff"):
        return "ruff", [sys.executable, "-m", "ruff", "check"]
    if shutil.which("flake8"):
        return "flake8", [sys.executable, "-m", "flake8"]
    if shutil.which("mypy") and _has_config(repo_root, ["pyproject.toml", "setup.py"]):
        return "mypy", [sys.executable, "-m", "mypy"]
    # JS/TS
    if (repo_root / "package.json").exists() and shutil.which("npx"):
        return "eslint", ["npx", "--no-install", "eslint"]
    # Go
    if _has_config(repo_root, ["go.mod"]) and shutil.which("golangci-lint"):
        return "golangci-lint", ["golangci-lint", "run"]
    return None


class FormatCodeArgs(BaseModel):
    extra_args: list[str] = Field(
        default_factory=list, description="Extra CLI args for the formatter"
    )
    target: str = Field(
        default="", description="Optional file or directory to format (defaults to repo root)"
    )


class FormatCode(BaseTool[FormatCodeArgs]):
    name = "format_code"
    description = (
        "Auto-detect and run the repository's formatter (ruff, black, prettier, gofmt, rustfmt)."
    )
    permission = Permission.mutating
    Args = FormatCodeArgs

    async def run(self, args: FormatCodeArgs) -> ToolResult:
        detected = detect_formatter(self.ctx.repo_root)
        if detected is None:
            raise ToolError(
                "no formatter detected (looked for ruff/black/isort/prettier/gofmt/rustfmt)"
            )
        name, argv = detected
        if args.target:
            argv.append(args.target)
        argv.extend(args.extra_args)
        code, out, err, truncated = await run_process(
            argv,
            cwd=self.ctx.repo_root,
            timeout=self.ctx.tool_timeout_seconds,
            max_output_chars=self.ctx.max_output_chars,
            env=build_env(),
        )
        output = out
        if err:
            output += "\nstderr:\n" + err
        text, cap_hit = cap_text(output, self.ctx.max_output_chars, "formatter output")
        event_output = text[-_EVENT_OUTPUT_CHARS:]
        if len(text) > _EVENT_OUTPUT_CHARS:
            event_output = "…" + event_output
        return ToolResult(
            ok=code == 0,
            output=text,
            error=None if code == 0 else f"formatter exited with code {code}",
            truncated=truncated or cap_hit,
            data={
                "formatter": name,
                "exit_code": code,
                "command": " ".join(argv),
                "output": event_output,
            },
        )


class LintCodeArgs(BaseModel):
    extra_args: list[str] = Field(default_factory=list, description="Extra CLI args for the linter")
    fix: bool = Field(default=False, description="Attempt to auto-fix issues (may modify files)")
    target: str = Field(
        default="", description="Optional file or directory to lint (defaults to repo root)"
    )


class LintCode(BaseTool[LintCodeArgs]):
    name = "lint_code"
    description = (
        "Auto-detect and run the repository's linter (ruff, flake8, mypy, eslint, golangci-lint)."
    )
    permission = Permission.mutating
    Args = LintCodeArgs

    async def run(self, args: LintCodeArgs) -> ToolResult:
        detected = detect_linter(self.ctx.repo_root)
        if detected is None:
            raise ToolError("no linter detected (looked for ruff/flake8/mypy/eslint/golangci-lint)")
        name, argv = detected
        if args.fix:
            argv.append("--fix")
        if args.target:
            argv.append(args.target)
        argv.extend(args.extra_args)
        code, out, err, truncated = await run_process(
            argv,
            cwd=self.ctx.repo_root,
            timeout=self.ctx.tool_timeout_seconds,
            max_output_chars=self.ctx.max_output_chars,
            env=build_env(),
        )
        output = out
        if err and name != "ruff":
            output += "\nstderr:\n" + err
        text, cap_hit = cap_text(output, self.ctx.max_output_chars, "linter output")
        event_output = text[-_EVENT_OUTPUT_CHARS:]
        if len(text) > _EVENT_OUTPUT_CHARS:
            event_output = "…" + event_output
        return ToolResult(
            ok=code == 0,
            output=text,
            error=None if code == 0 else f"linter exited with code {code}",
            truncated=truncated or cap_hit,
            data={
                "linter": name,
                "exit_code": code,
                "command": " ".join(argv),
                "output": event_output,
            },
        )
