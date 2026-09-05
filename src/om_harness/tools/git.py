"""Git tools: safe inspection (read-only) and guarded mutations.

Inspection tools are always read_only; git_commit is mutating because it only
records existing work, while git_restore is destructive because it discards
uncommitted changes.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from om_harness.tools.base import BaseTool, Permission, ToolContext, ToolError, ToolResult, cap_text
from om_harness.tools.shell import build_env, run_process

ArgsT = TypeVar("ArgsT", bound=BaseModel)


class GitTool(BaseTool[ArgsT], Generic[ArgsT]):
    """Shared git subprocess plumbing for all git tools."""

    async def _git(self, ctx: ToolContext, *args: str) -> tuple[int, str, str, bool]:
        return await run_process(
            ["git", *args],
            cwd=ctx.repo_root,
            timeout=ctx.tool_timeout_seconds,
            max_output_chars=ctx.max_output_chars,
            env=build_env(),
        )

    async def _git_text(self, ctx: ToolContext, *args: str) -> str:
        code, out, err, _ = await self._git(ctx, *args)
        if code != 0:
            raise ToolError(f"git {args[0]} failed: {err.strip() or 'unknown error'}")
        return out


class GitStatusArgs(BaseModel):
    pass


class GitStatus(GitTool[GitStatusArgs]):
    name = "git_status"
    description = "Show the current branch and modified/staged files."
    permission = Permission.read_only
    Args = GitStatusArgs

    async def run(self, args: GitStatusArgs) -> ToolResult:
        out = await self._git_text(self.ctx, "status", "--porcelain=v1", "-b")
        branch_lines = [ln for ln in out.splitlines() if ln.startswith("##")]
        file_lines = [ln for ln in out.splitlines() if ln and not ln.startswith("##")]
        if not file_lines:
            branch = branch_lines[0][2:].strip() if branch_lines else "unknown"
            return ToolResult(output=f"On branch {branch}\nWorking tree clean.")
        return ToolResult(output=out.rstrip())


class GitDiffArgs(BaseModel):
    staged: bool = Field(default=False, description="Show staged (cached) diff instead")
    path: str = Field(default="", description="Optional path to limit the diff")


class GitDiff(GitTool[GitDiffArgs]):
    name = "git_diff"
    description = "Show the unified diff of uncommitted changes (optionally staged only)."
    permission = Permission.read_only
    Args = GitDiffArgs

    async def run(self, args: GitDiffArgs) -> ToolResult:
        argv = ["diff", "--cached"] if args.staged else ["diff"]
        if args.path:
            argv += ["--", args.path]
        out = await self._git_text(self.ctx, *argv)
        if not out.strip():
            return ToolResult(output="No differences.")
        text, truncated = cap_text(out, self.ctx.max_output_chars, "diff")
        return ToolResult(output=text, truncated=truncated)


class GitLogArgs(BaseModel):
    max_count: int = Field(default=10, ge=1, le=100)


class GitLog(GitTool[GitLogArgs]):
    name = "git_log"
    description = "Show recent commit history (oneline, newest first)."
    permission = Permission.read_only
    Args = GitLogArgs

    async def run(self, args: GitLogArgs) -> ToolResult:
        out = await self._git_text(self.ctx, "log", "--oneline", f"-n{args.max_count}")
        return ToolResult(output=out.strip())


class GitShowArgs(BaseModel):
    path: str = Field(description="Repo-relative path")


class GitShow(GitTool[GitShowArgs]):
    name = "git_show"
    description = "Show a file's content at HEAD (last committed version)."
    permission = Permission.read_only
    Args = GitShowArgs

    async def run(self, args: GitShowArgs) -> ToolResult:
        out = await self._git_text(self.ctx, "show", f"HEAD:{args.path}")
        text, truncated = cap_text(out, self.ctx.max_output_chars, "git show")
        return ToolResult(output=text, truncated=truncated)


class GitAddArgs(BaseModel):
    paths: list[str] = Field(min_length=1, description="Repo-relative paths to stage")


class GitAdd(GitTool[GitAddArgs]):
    name = "git_add"
    description = "Stage files for commit."
    permission = Permission.mutating
    Args = GitAddArgs

    async def run(self, args: GitAddArgs) -> ToolResult:
        await self._git_text(self.ctx, "add", "--", *args.paths)
        return ToolResult(output=f"Staged: {', '.join(args.paths)}")


class GitCommitArgs(BaseModel):
    message: str = Field(min_length=1, description="Commit message")


class GitCommit(GitTool[GitCommitArgs]):
    name = "git_commit"
    description = "Commit staged changes with a message."
    permission = Permission.mutating
    Args = GitCommitArgs

    async def run(self, args: GitCommitArgs) -> ToolResult:
        out = await self._git_text(self.ctx, "commit", "-m", args.message)
        return ToolResult(output=out.strip() or "Committed.")


class GitRestoreArgs(BaseModel):
    path: str = Field(description="Repo-relative path to restore")


class GitRestore(GitTool[GitRestoreArgs]):
    name = "git_restore"
    description = "DISCARD uncommitted changes to a file (destructive; cannot be undone)."
    permission = Permission.destructive
    Args = GitRestoreArgs

    async def run(self, args: GitRestoreArgs) -> ToolResult:
        await self._git_text(self.ctx, "restore", "--", args.path)
        return ToolResult(output=f"Restored {args.path} to last committed version.")
