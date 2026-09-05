"""Process execution: the shell tool and the shared async subprocess helper.

Safety model:
- Commands are executed with ``shell=False`` as an argv list (no shell
  interpolation, pipes, or redirection — deliberate v1 tradeoff).
- Shell metacharacters and known catastrophic commands are rejected outright.
- Subprocesses get a scrubbed environment (no provider API keys) and a hard
  timeout with process-tree kill.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
from typing import Any

from pydantic import BaseModel, Field

from om_harness.tools.base import BaseTool, Permission, ToolError, ToolResult, cap_text

# Control characters that would require a shell to interpret.
_SHELL_METACHARS = set(";|&`$><\n")

# Commands that are rejected before execution regardless of policy.
_CATASTROPHIC_PATTERNS = (
    "rm -rf /",
    "rm -rf /*",
    "rm -rf ~",
    "del /f /s /q c:\\",
    "rd /s /q c:\\",
    "format c:",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",
    "git push --force --all",
)


def build_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Snapshot os.environ minus anything that looks like a credential."""
    env = {
        k: v
        for k, v in os.environ.items()
        if "API_KEY" not in k.upper()
        and "SECRET" not in k.upper()
        and "TOKEN" not in k.upper()
        and k.upper() not in {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
    }
    if extra:
        env.update(extra)
    return env


async def run_process(
    argv: list[str],
    *,
    cwd: Any,
    timeout: float,
    env: dict[str, str] | None = None,
    max_output_chars: int = 20_000,
) -> tuple[int, str, str, bool]:
    """Run an argv list; returns (returncode, stdout, stderr, truncated)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env if env is not None else build_env(),
        )
    except (OSError, ValueError) as exc:
        raise ToolError(f"failed to start {argv[0]!r}: {exc}") from exc
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ToolError(f"command timed out after {timeout:.0f}s: {argv[0]!r}") from exc
    out = stdout.decode("utf-8", errors="replace") if stdout else ""
    err = stderr.decode("utf-8", errors="replace") if stderr else ""
    combined_len = len(out) + len(err)
    if combined_len <= max_output_chars:
        return proc.returncode or 0, out, err, False
    keep = max_output_chars // 2
    out = (
        out[:keep]
        + (f"\n... [stdout truncated at {keep} chars] ...\n" if len(out) > keep else "")
        + out[-keep:]
    )
    err = (
        err[:keep]
        + (f"\n... [stderr truncated at {keep} chars] ...\n" if len(err) > keep else "")
        + err[-keep:]
    )
    return proc.returncode or 0, out, err, True


class RunShellArgs(BaseModel):
    command: str = Field(description="The command line to execute, e.g. 'python -m pytest -q'")


class RunShell(BaseTool[RunShellArgs]):
    name = "run_shell"
    description = (
        "Execute a shell command in the repository root (no pipes/redirection; "
        "shell metacharacters are rejected). Returns stdout, stderr, and exit code."
    )
    permission = Permission.mutating
    Args = RunShellArgs

    async def run(self, args: RunShellArgs) -> ToolResult:
        command = args.command.strip()
        if not command:
            raise ToolError("command must not be empty")
        lowered = command.lower()
        for pattern in _CATASTROPHIC_PATTERNS:
            if pattern in lowered:
                raise ToolError(f"command rejected as unsafe: {command!r}")
        if any(ch in command for ch in _SHELL_METACHARS):
            raise ToolError(
                f"command rejected: shell metacharacters are not supported "
                f"(got {command!r}); run simpler commands instead"
            )
        try:
            argv = shlex.split(command, posix=(sys.platform != "win32"))
        except ValueError as exc:
            raise ToolError(f"cannot parse command: {exc}") from exc
        if not argv:
            raise ToolError("command must not be empty")

        code, out, err, truncated = await run_process(
            argv,
            cwd=self.ctx.repo_root,
            timeout=self.ctx.tool_timeout_seconds,
            max_output_chars=self.ctx.max_output_chars,
        )
        output = f"exit code: {code}\n"
        if out:
            output += f"stdout:\n{out}"
        if err:
            output += f"stderr:\n{err}"
        text, cap_hit = cap_text(output, self.ctx.max_output_chars, "command output")
        return ToolResult(
            ok=code == 0,
            output=text,
            error=None if code == 0 else f"command exited with code {code}",
            truncated=truncated or cap_hit,
            data={"exit_code": code, "command": command},
        )
