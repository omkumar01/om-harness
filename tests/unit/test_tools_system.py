"""Contract tests for shell/git/test-runner tools and the repo-info tool."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from om_harness.tools.base import Permission, ToolContext, ToolError
from om_harness.tools.envinfo import RepoInfo
from om_harness.tools.git import GitAdd, GitCommit, GitDiff, GitLog, GitRestore, GitStatus
from om_harness.tools.shell import RunShell
from om_harness.tools.testing import RunTests


def _git(repo: Any, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, shell=False)


@pytest.fixture
def repo(tmp_path: Any) -> Any:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.py").write_text("print('hi')\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


@pytest.fixture
def ctx(repo: Any) -> ToolContext:
    return ToolContext(repo_root=repo)


# -- shell --------------------------------------------------------------------


async def test_run_shell_captures_output(ctx: ToolContext) -> None:
    result = await RunShell(ctx).run(RunShell.Args(command="echo hello-from-om"))
    assert result.ok
    assert "hello-from-om" in result.output
    assert RunShell.permission == Permission.mutating


async def test_run_shell_reports_nonzero_exit(ctx: ToolContext) -> None:
    import sys

    command = "false" if sys.platform != "win32" else "cmd /c exit 1"
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    assert not result.ok
    assert result.error is not None


async def test_run_shell_timeout(tmp_path: Any) -> None:
    import sys

    ctx = ToolContext(repo_root=tmp_path, tool_timeout_seconds=1.0)
    blocker = "sleep 5" if sys.platform != "win32" else "ping -n 6 127.0.0.1"
    with pytest.raises(ToolError, match="timed out"):
        await RunShell(ctx).run(RunShell.Args(command=blocker))


async def test_run_shell_rejects_empty_command(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="empty"):
        await RunShell(ctx).run(RunShell.Args(command="   "))


async def test_run_shell_rejects_catastrophic_commands(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="rejected"):
        await RunShell(ctx).run(RunShell.Args(command="rm -rf /"))


async def test_run_shell_rejects_argument_injection_artifacts(ctx: ToolContext) -> None:
    # Shell control characters are rejected: commands run without a shell.
    with pytest.raises(ToolError, match="rejected"):
        await RunShell(ctx).run(RunShell.Args(command="echo a; echo b"))


# -- git ----------------------------------------------------------------------


async def test_git_status_clean(ctx: ToolContext) -> None:
    result = await GitStatus(ctx).run(GitStatus.Args())
    assert result.ok
    assert "clean" in result.output.lower()
    assert GitStatus.permission == Permission.read_only


async def test_git_status_shows_dirty(ctx: ToolContext) -> None:
    (ctx.repo_root / "a.py").write_text("changed\n")
    result = await GitStatus(ctx).run(GitStatus.Args())
    assert "a.py" in result.output


async def test_git_diff_and_log(ctx: ToolContext) -> None:
    (ctx.repo_root / "a.py").write_text("print('changed')\n")
    diff = await GitDiff(ctx).run(GitDiff.Args())
    assert diff.ok and "changed" in diff.output
    log = await GitLog(ctx).run(GitLog.Args(max_count=5))
    assert log.ok and "initial" in log.output


async def test_git_add_and_commit(ctx: ToolContext) -> None:
    (ctx.repo_root / "new.txt").write_text("data\n")
    add = await GitAdd(ctx).run(GitAdd.Args(paths=["new.txt"]))
    assert add.ok
    commit = await GitCommit(ctx).run(GitCommit.Args(message="add file"))
    assert commit.ok
    log = await GitLog(ctx).run(GitLog.Args(max_count=1))
    assert "add file" in log.output
    assert GitCommit.permission == Permission.mutating


async def test_git_restore_is_destructive(ctx: ToolContext) -> None:
    (ctx.repo_root / "a.py").write_text("throwaway\n")
    result = await GitRestore(ctx).run(GitRestore.Args(path="a.py"))
    assert result.ok
    assert (ctx.repo_root / "a.py").read_text() == "print('hi')\n"
    assert GitRestore.permission == Permission.destructive


# -- tests & repo info --------------------------------------------------------


async def test_run_tests_with_pytest(tmp_path: Any) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (tmp_path / "test_x.py").write_text("def test_ok():\n    assert True\n")
    ctx = ToolContext(repo_root=tmp_path, tool_timeout_seconds=120.0)
    result = await RunTests(ctx).run(RunTests.Args())
    assert result.ok, result.error
    assert "passed" in result.output
    assert result.error is None


async def test_run_tests_no_runner_detected(tmp_path: Any) -> None:
    ctx = ToolContext(repo_root=tmp_path)
    with pytest.raises(ToolError, match="no test runner detected"):
        await RunTests(ctx).run(RunTests.Args())


async def test_repo_info(ctx: ToolContext) -> None:
    result = await RepoInfo(ctx).run(RepoInfo.Args())
    assert result.ok
    assert "python" in result.output.lower()
