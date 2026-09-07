"""Process execution: the shell tool and the shared async subprocess helper.

Safety model:
- Commands are executed with ``shell=False`` as argv lists (no shell
  interpolation, no ``/bin/sh`` — deliberate injection resistance).
- Simple pipelines (``a | b | c``), ``2>&1`` merging, and ``>`` / ``>>``
  file redirection are supported natively by parsing the command here and
  chaining processes — pipes never involve a shell.
- Shell metacharacters that still require a shell (``;``, ``&``, ``<``,
  ``$``, backticks, parentheses) are rejected outright, as are known
  catastrophic commands.
- Subprocesses get a scrubbed environment (no provider API keys) and a hard
  timeout with process kill.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import sys
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from om_harness.tools.base import BaseTool, Permission, ToolError, ToolResult, cap_text

# Control characters / constructs that require a real shell.
_SHELL_METACHARS_REJECTED = set(";&`$<(){}")

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

# Intermediate pipeline stages pass at most this many bytes downstream.
_INTERMEDIATE_CAP_BYTES = 1_000_000

# Output copied into the completion event (UI preview); tail-biased because
# errors surface at the end of command output.
_EVENT_OUTPUT_CHARS = 4_000


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
    timeout: float | None,
    env: dict[str, str] | None = None,
    max_output_chars: int = 20_000,
    input_bytes: bytes | None = None,
    merge_stderr: bool = False,
) -> tuple[int, str, str, bool]:
    """Run an argv list; returns (returncode, stdout, stderr, truncated).

    ``input_bytes`` is fed to stdin (used to chain pipeline stages);
    ``merge_stderr`` sends stderr into stdout (``2>&1``).
    """
    stdin = asyncio.subprocess.PIPE if input_bytes is not None else None
    stderr = asyncio.subprocess.STDOUT if merge_stderr else asyncio.subprocess.PIPE
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=stderr,
            env=env if env is not None else build_env(),
        )
    except (OSError, ValueError) as exc:
        raise ToolError(f"failed to start {argv[0]!r}: {exc}") from exc
    try:
        if input_bytes is not None:
            out_bytes, err_bytes = await asyncio.wait_for(
                proc.communicate(input=input_bytes), timeout=timeout
            )
        else:
            out_bytes, err_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ToolError(f"command timed out after {timeout:.0f}s: {argv[0]!r}") from exc
    out = out_bytes.decode("utf-8", errors="replace") if out_bytes else ""
    err = err_bytes.decode("utf-8", errors="replace") if err_bytes else ""
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


def _split_pipeline(command: str) -> list[str]:
    """Split on ``|`` outside of quotes."""
    stages: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for ch in command:
        if quote:
            current.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            current.append(ch)
        elif ch == "|":
            stages.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    stages.append("".join(current).strip())
    return stages


@dataclass
class _Stage:
    argv: list[str] = field(default_factory=list)
    merge_stderr: bool = False
    redirect_path: str | None = None  # ``>`` / ``>>`` target
    redirect_append: bool = False


def _find_unquoted_metachar(text: str) -> str | None:
    """First shell-control character outside of quotes, if any.

    Metacharacters inside quoted arguments (e.g. ``python -c "a; b"``) are
    literal data and perfectly safe — we never run a shell, so only
    *unquoted* control characters are ambiguous.
    """
    quote: str | None = None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch in _SHELL_METACHARS_REJECTED:
            return ch
    return None


def _parse_stage(text: str) -> _Stage:
    """Parse one pipeline stage: argv plus optional 2>&1 and > / >> redirect."""
    stage = _Stage()
    if "2>&1" in text:
        stage.merge_stderr = True
        text = text.replace("2>&1", " ")
    redirect = re.search(r"(>>?)\s*(\S+)\s*$", text)
    if redirect:
        stage.redirect_path = redirect.group(2).strip("'\"")
        stage.redirect_append = redirect.group(1) == ">>"
        text = text[: redirect.start()]
    metachar = _find_unquoted_metachar(text)
    if metachar:
        raise ToolError(
            f"command rejected: shell metacharacter {metachar!r} requires a shell; "
            "run simpler commands instead"
        )
    posix = sys.platform != "win32"
    try:
        tokens = shlex.split(text, posix=posix)
    except ValueError as exc:
        raise ToolError(f"cannot parse command stage {text!r}: {exc}") from exc
    if not tokens:
        raise ToolError("empty command stage in pipeline")
    # With posix=False (Windows), shlex keeps surrounding quotes in tokens;
    # strip one level so quoted executables and arguments work as expected.
    stage.argv = [
        t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"') else t for t in tokens
    ]
    return stage


class RunShellArgs(BaseModel):
    command: str = Field(
        description=(
            "The command line to execute. Simple pipes (a | b), 2>&1 and "
            "> / >> file redirection are supported; ; & < $ ` () are not."
        )
    )


class RunShell(BaseTool[RunShellArgs]):
    name = "run_shell"
    description = (
        "Execute a command in the repository root. Simple pipes (cmd1 | cmd2), "
        "2>&1, and > / >> file redirection are supported natively; other shell "
        "metacharacters are rejected. Returns stdout, stderr, and exit code."
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

        stages = [_parse_stage(text) for text in _split_pipeline(command)]
        for index, stage in enumerate(stages):
            if stage.redirect_path and index != len(stages) - 1:
                raise ToolError("redirection is only supported on the final pipeline stage")

        code = 0
        output = ""
        err_acc: list[str] = []
        truncated = False
        input_bytes: bytes | None = None
        total_stages = len(stages)

        for index, stage in enumerate(stages):
            is_last = index == total_stages - 1
            code, out, err, stage_trunc = await run_process(
                stage.argv,
                cwd=self.ctx.repo_root,
                timeout=self.ctx.tool_timeout_seconds,
                max_output_chars=self.ctx.max_output_chars,
                input_bytes=input_bytes,
                merge_stderr=stage.merge_stderr,
            )
            if err and not stage.merge_stderr:
                err_acc.append(err)
            if is_last and stage.redirect_path:
                from om_harness.tools.base import resolve_in_repo

                target = resolve_in_repo(self.ctx, stage.redirect_path)
                mode = "ab" if stage.redirect_append else "wb"
                with target.open(mode) as fh:
                    fh.write(out.encode("utf-8"))
                verb = "appended" if stage.redirect_append else "wrote"
                output = f"{verb} {len(out)} bytes to {stage.redirect_path}"
                out = ""
            elif not is_last:
                # Feed the next stage; keep only the tail if huge.
                input_bytes = out.encode("utf-8")[-_INTERMEDIATE_CAP_BYTES:]
                out = ""
            if out:
                output += out
            truncated = truncated or stage_trunc

        if err_acc:
            output += "\nstderr:\n" + "\n".join(err_acc)
        text, cap_hit = cap_text(output, self.ctx.max_output_chars, "command output")
        # The event-bus copy is a tail preview (errors live at the end); the
        # model still receives the full `output` via the tool result.
        event_output = text[-_EVENT_OUTPUT_CHARS:]
        if len(text) > _EVENT_OUTPUT_CHARS:
            event_output = "…" + event_output
        return ToolResult(
            ok=code == 0,
            output=text,
            error=None if code == 0 else f"command exited with code {code}",
            truncated=truncated or cap_hit,
            data={
                "exit_code": code,
                "command": command,
                "stages": total_stages,
                "output": event_output,
                "output_lines": len(output.splitlines()),
            },
        )
