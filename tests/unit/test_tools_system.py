"""Contract tests for shell/git/test-runner tools and the repo-info tool."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import pytest

from om_harness.tools.base import Permission, ToolContext, ToolError
from om_harness.tools.envinfo import RepoInfo
from om_harness.tools.git import (
    GitAdd,
    GitBlame,
    GitBranch,
    GitCommit,
    GitDiff,
    GitLog,
    GitLogGraph,
    GitRemote,
    GitRestore,
    GitStash,
    GitStatus,
)
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
    result = await RunShell(ctx).run(
        RunShell.Args(command=f"{sys.executable} -c \"print('hello-from-om')\"")
    )
    assert result.ok
    assert "hello-from-om" in result.output
    assert RunShell.permission == Permission.mutating


async def test_run_shell_event_data_carries_output_preview(ctx: ToolContext) -> None:
    """The completion event carries a trimmed output copy for the UI."""
    command = f"{sys.executable} -c \"print('line-one')\""
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    assert result.data["command"] == command
    assert result.data["exit_code"] == 0
    assert "line-one" in result.data["output"]
    assert result.data["output_lines"] == 1


async def test_run_shell_event_output_is_tail_capped(ctx: ToolContext) -> None:
    from om_harness.tools.shell import _EVENT_OUTPUT_CHARS

    command = "python -c \"print('x' * 20000)\""
    result = await RunShell(ctx).run(RunShell.Args(command=command))
    event_output = result.data["output"]
    assert len(event_output) <= _EVENT_OUTPUT_CHARS + 1  # + leading ellipsis
    assert event_output.startswith("…") or len(result.output) <= _EVENT_OUTPUT_CHARS


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


# -- git branch ---------------------------------------------------------------


async def test_git_branch_list(ctx: ToolContext) -> None:
    result = await GitBranch(ctx).run(GitBranch.Args(action="list"))
    assert result.ok
    assert GitBranch.permission == Permission.mutating
    # The current branch is marked with an asterisk
    assert "*" in result.output


async def test_git_branch_create_and_switch(ctx: ToolContext) -> None:
    create = await GitBranch(ctx).run(GitBranch.Args(action="create", name="feature-x"))
    assert create.ok
    assert "feature-x" in create.output
    switch = await GitBranch(ctx).run(GitBranch.Args(action="switch", name="feature-x"))
    assert switch.ok
    branches = await GitBranch(ctx).run(GitBranch.Args(action="list"))
    assert "feature-x" in branches.output


async def test_git_branch_delete(ctx: ToolContext) -> None:
    # Create a branch, switch back, then delete it
    await GitBranch(ctx).run(GitBranch.Args(action="create", name="temp-branch"))
    # Switch back to the default branch to allow deletion (can't delete checked-out branch)
    _git(ctx.repo_root, "switch", "master")
    result = await GitBranch(ctx).run(GitBranch.Args(action="delete", name="temp-branch"))
    assert result.ok
    assert "temp-branch" in result.output


async def test_git_branch_requires_name() -> None:
    with pytest.raises(ValueError, match="name is required"):
        GitBranch.Args(action="create")
    with pytest.raises(ValueError, match="name is required"):
        GitBranch.Args(action="switch")
    with pytest.raises(ValueError, match="name is required"):
        GitBranch.Args(action="delete")


# -- git stash ----------------------------------------------------------------


async def test_git_stash_save_list_pop(ctx: ToolContext) -> None:
    # Modify a tracked file to create uncommitted changes
    (ctx.repo_root / "a.py").write_text("print('modified')\n")
    save = await GitStash(ctx).run(GitStash.Args(action="save", message="wip"))
    assert save.ok
    lst = await GitStash(ctx).run(GitStash.Args(action="list"))
    assert lst.ok
    assert "wip" in lst.output or "stash@{0}" in lst.output
    pop = await GitStash(ctx).run(GitStash.Args(action="pop"))
    assert pop.ok


async def test_git_stash_permissions() -> None:
    assert GitStash.permission == Permission.mutating


# -- git log graph ------------------------------------------------------------


async def test_git_log_graph(ctx: ToolContext) -> None:
    # Add a second commit for a more interesting graph
    (ctx.repo_root / "b.py").write_text("y = 2\n")
    _git(ctx.repo_root, "add", ".")
    _git(ctx.repo_root, "commit", "-q", "-m", "second commit")
    result = await GitLogGraph(ctx).run(GitLogGraph.Args(max_count=5))
    assert result.ok
    assert GitLogGraph.permission == Permission.read_only
    assert "initial" in result.output or "second" in result.output


async def test_git_log_graph_all(ctx: ToolContext) -> None:
    # Create a second branch with its own commit, then switch back to show both in graph
    _git(ctx.repo_root, "branch", "dev")
    _git(ctx.repo_root, "switch", "dev")
    (ctx.repo_root / "dev.txt").write_text("dev work\n")
    _git(ctx.repo_root, "add", ".")
    _git(ctx.repo_root, "commit", "-q", "-m", "dev commit")
    _git(ctx.repo_root, "switch", "master")
    result = await GitLogGraph(ctx).run(GitLogGraph.Args(max_count=10, all=True))
    assert result.ok
    assert "dev" in result.output


async def test_git_log_graph_empty(tmp_path: Any) -> None:
    # Fresh repo with no commits → git log fails gracefully
    empty_repo = tmp_path / "empty-repo"
    empty_repo.mkdir()
    _git(empty_repo, "init", "-q")
    _git(empty_repo, "config", "user.email", "test@example.com")
    _git(empty_repo, "config", "user.name", "Test")
    ctx_empty = ToolContext(repo_root=empty_repo)
    result = await GitLogGraph(ctx_empty).run(GitLogGraph.Args(max_count=5))
    assert result.ok
    assert "No commits" in result.output


# -- git blame ----------------------------------------------------------------


async def test_git_blame(ctx: ToolContext) -> None:
    result = await GitBlame(ctx).run(GitBlame.Args(path="a.py"))
    assert result.ok
    assert GitBlame.permission == Permission.read_only
    # Should contain a commit hash and the file content
    assert "print" in result.output


async def test_git_blame_with_range(ctx: ToolContext) -> None:
    result = await GitBlame(ctx).run(GitBlame.Args(path="a.py", start_line=1, end_line=1))
    assert result.ok


async def test_git_blame_nonexistent_file(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="failed"):
        await GitBlame(ctx).run(GitBlame.Args(path="nonexistent.py"))


# -- git remote ---------------------------------------------------------------


async def test_git_remote_list_empty(ctx: ToolContext) -> None:
    result = await GitRemote(ctx).run(GitRemote.Args(action="list"))
    assert result.ok
    assert GitRemote.permission == Permission.mutating
    assert "No remotes" in result.output


async def test_git_remote_add_and_list(ctx: ToolContext) -> None:
    add = await GitRemote(ctx).run(
        GitRemote.Args(action="add", name="origin", url="https://github.com/user/repo.git")
    )
    assert add.ok
    lst = await GitRemote(ctx).run(GitRemote.Args(action="list"))
    assert lst.ok
    assert "origin" in lst.output
    assert "https://github.com/user/repo.git" in lst.output


async def test_git_remote_remove(ctx: ToolContext) -> None:
    await GitRemote(ctx).run(
        GitRemote.Args(action="add", name="origin", url="https://github.com/user/repo.git")
    )
    result = await GitRemote(ctx).run(GitRemote.Args(action="remove", name="origin"))
    assert result.ok
    lst = await GitRemote(ctx).run(GitRemote.Args(action="list"))
    assert "No remotes" in lst.output


async def test_git_remote_requires_name_and_url() -> None:
    with pytest.raises(ValueError, match="name is required"):
        GitRemote.Args(action="add")
    with pytest.raises(ValueError, match="url is required"):
        GitRemote.Args(action="add", name="origin")
    with pytest.raises(ValueError, match="name is required"):
        GitRemote.Args(action="remove")
