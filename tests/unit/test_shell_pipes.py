"""Contract tests for native pipeline support in the run_shell tool.

Pipes run as chained argv processes (no shell), so injection-prone
metacharacters (; & < $ ` ()) stay rejected while simple `|`, `2>&1`,
and `>` / `>>` redirection work cross-platform (python-based stages).
"""

from __future__ import annotations

import sys
from typing import Any

import pytest

from om_harness.tools.base import ToolContext, ToolError
from om_harness.tools.shell import RunShell

PY = sys.executable.replace("\\", "/")


@pytest.fixture
def ctx(tmp_path: Any) -> ToolContext:
    return ToolContext(repo_root=tmp_path, tool_timeout_seconds=30)


def py(code: str) -> str:
    """A quoted `python -c ...` fragment that parses cross-platform."""
    escaped = code.replace('"', '\\"')
    return '"' + PY + '" -c "' + escaped + '"'


def pipe(*stages: str) -> str:
    return " | ".join(stages)


async def test_simple_pipe_chains_two_stages(ctx: ToolContext) -> None:
    command = pipe(
        py("print('hello world')"),
        py("import sys; print(sys.stdin.read().upper())"),
    )
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    assert result.ok
    assert "HELLO WORLD" in result.output


async def test_pipe_feeds_stdout_to_next_stage(ctx: ToolContext) -> None:
    command = pipe(
        py("print('one')"),
        py("import sys; print(sys.stdin.read().strip() + '-two')"),
    )
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    assert result.ok
    assert "one-two" in result.output


async def test_stderr_merge_with_2_redirect_1(ctx: ToolContext) -> None:
    command = py("import sys; sys.stderr.write('to-stderr')") + " 2>&1"
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    assert result.ok
    assert "to-stderr" in result.output


async def test_redirect_write_and_append(ctx: ToolContext) -> None:
    shell = RunShell(ctx)
    result = await shell.run(RunShell.Args(command=py("print('data')") + " > out.txt"))
    assert result.ok
    assert (ctx.repo_root / "out.txt").read_text().strip() == "data"
    result = await shell.run(RunShell.Args(command=py("print('more')") + " >> out.txt"))
    assert result.ok
    content = (ctx.repo_root / "out.txt").read_text()
    assert "data" in content and "more" in content


async def test_redirect_target_confined_to_repo(ctx: ToolContext) -> None:
    command = py("print('x')") + " > ../escape.txt"
    with pytest.raises(ToolError, match="outside the repository"):
        await RunShell(ctx).run(RunShell.Args(command=command))


async def test_metacharacters_still_rejected(ctx: ToolContext) -> None:
    for command in ("echo a; echo b", "echo a & echo b", "echo `id`", "echo $(id)"):
        with pytest.raises(ToolError, match="rejected"):
            await RunShell(ctx).run(RunShell.Args(command=command))


async def test_quoted_metachars_are_literal_data(ctx: ToolContext) -> None:
    """Metacharacters inside quoted arguments are data, not shell syntax."""
    command = py("print('a;b&c')")
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    assert result.ok
    assert "a;b&c" in result.output


async def test_catastrophic_pipe_rejected(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="unsafe"):
        await RunShell(ctx).run(RunShell.Args(command="rm -rf / | tail -5"))


async def test_empty_stage_rejected(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="empty command stage"):
        await RunShell(ctx).run(RunShell.Args(command="echo | | wc"))


async def test_intermediate_redirect_rejected(ctx: ToolContext) -> None:
    command = pipe(py("print('x')") + " > mid.txt", py("print('y')"))
    with pytest.raises(ToolError, match="final pipeline stage"):
        await RunShell(ctx).run(RunShell.Args(command=command))


async def test_nonzero_last_stage_reports_error(ctx: ToolContext) -> None:
    command = py("import sys; sys.exit(3)")
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    assert not result.ok
    assert result.data["exit_code"] == 3
