"""Git tools: safe inspection (read-only) and guarded mutations.

Inspection tools are always read_only; git_commit is mutating because it only
records existing work, while git_restore is destructive because it discards
uncommitted changes.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field, model_validator

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


class GitBranchArgs(BaseModel):
    action: Literal["list", "create", "switch", "delete"] = Field(
        default="list",
        description=(
            "list: show branches; create: make new + switch; switch: checkout; delete: remove"
        ),
    )
    name: str | None = Field(
        default=None, description="Branch name (required for create/switch/delete)"
    )
    all: bool = Field(default=False, description="In list mode: include remote-tracking branches")

    @model_validator(mode="after")
    def _validate_name(self) -> GitBranchArgs:
        if self.action in ("create", "switch", "delete") and not self.name:
            raise ValueError(f"name is required for action={self.action!r}")
        return self


class GitBranch(GitTool[GitBranchArgs]):
    name = "git_branch"
    description = "List, create, switch, or delete git branches."
    permission = Permission.mutating
    Args = GitBranchArgs

    async def run(self, args: GitBranchArgs) -> ToolResult:
        if args.action == "list":
            flags = ["branch", "-vv"]
            if args.all:
                flags.append("-a")
            out = await self._git_text(self.ctx, *flags)
            return ToolResult(output=out.rstrip())
        assert args.name is not None  # guaranteed by model_validator
        if args.action == "create":
            await self._git_text(self.ctx, "switch", "-c", args.name)
            return ToolResult(output=f"Created and switched to branch '{args.name}'.")
        if args.action == "switch":
            await self._git_text(self.ctx, "switch", args.name)
            return ToolResult(output=f"Switched to branch '{args.name}'.")
        # delete
        await self._git_text(self.ctx, "branch", "-d", args.name)
        return ToolResult(output=f"Deleted branch '{args.name}'.")


class GitStashArgs(BaseModel):
    action: Literal["save", "pop", "list", "drop"] = Field(
        default="save",
        description=(
            "save: stash changes; pop: restore latest; list: show stashes; drop: remove latest"
        ),
    )
    message: str | None = Field(default=None, description="Stash message (save only)")
    include_untracked: bool = Field(
        default=False, description="Include untracked files (save only)"
    )


class GitStash(GitTool[GitStashArgs]):
    name = "git_stash"
    description = "Save (stash), restore (pop), list, or drop stashed changes."
    permission = Permission.mutating
    Args = GitStashArgs

    async def run(self, args: GitStashArgs) -> ToolResult:
        if args.action == "save":
            argv = ["stash", "push"]
            if args.include_untracked:
                argv.append("-u")
            if args.message:
                argv += ["-m", args.message]
            out = await self._git_text(self.ctx, *argv)
            return ToolResult(output=out.rstrip() or "Stashed changes.")
        if args.action == "pop":
            out = await self._git_text(self.ctx, "stash", "pop")
            return ToolResult(output=out.rstrip() or "Popped stash.")
        if args.action == "list":
            out = await self._git_text(self.ctx, "stash", "list")
            return ToolResult(output=out.rstrip() or "No stashes.")
        # drop
        await self._git_text(self.ctx, "stash", "drop")
        return ToolResult(output="Dropped latest stash.")


class GitLogGraphArgs(BaseModel):
    max_count: int = Field(
        default=20, ge=1, le=100, description="Maximum number of commits to show"
    )
    all: bool = Field(default=False, description="Show commits across all refs")
    path: str = Field(default="", description="Optional path to limit the graph")


class GitLogGraph(GitTool[GitLogGraphArgs]):
    name = "git_log_graph"
    description = "Show commit history as a visual graph with branch decorations."
    permission = Permission.read_only
    Args = GitLogGraphArgs

    async def run(self, args: GitLogGraphArgs) -> ToolResult:
        argv = ["log", "--graph", "--oneline", "--decorate", f"-n{args.max_count}"]
        if args.all:
            argv.append("--all")
        if args.path:
            argv += ["--", args.path]
        try:
            out = await self._git_text(self.ctx, *argv)
        except ToolError:
            return ToolResult(output="No commits found.")
        if not out.strip():
            return ToolResult(output="No commits found.")
        text, truncated = cap_text(out, self.ctx.max_output_chars, "git log graph")
        return ToolResult(output=text, truncated=truncated)


class GitBlameArgs(BaseModel):
    path: str = Field(description="Repo-relative file path")
    start_line: int | None = Field(default=None, ge=1, description="Starting line number (1-based)")
    end_line: int | None = Field(
        default=None, ge=1, description="Ending line number (1-based, inclusive)"
    )


class GitBlame(GitTool[GitBlameArgs]):
    name = "git_blame"
    description = "Show line-by-line blame attribution for a file (commit, author, date)."
    permission = Permission.read_only
    Args = GitBlameArgs

    async def run(self, args: GitBlameArgs) -> ToolResult:
        # git blame --line-porcelain for machine-parseable output with line ranges
        argv: list[str] = ["blame", "--line-porcelain"]
        if args.start_line is not None and args.end_line is not None:
            argv.append(f"-L{args.start_line},{args.end_line}")
        elif args.start_line is not None:
            argv.append(f"-L{args.start_line},{args.start_line}")
        elif args.end_line is not None:
            argv.append(f"-L1,{args.end_line}")
        argv += ["--", args.path]
        out = await self._git_text(self.ctx, *argv)
        if not out.strip():
            return ToolResult(output=f"No blame data for {args.path}.")
        # Parse porcelain output into structured entries, then format
        entries: list[str] = []
        current_line: str | None = None
        current_commit: str | None = None
        current_author: str | None = None
        current_date: str | None = None
        for line in out.splitlines():
            if not line.startswith("\t"):
                parts = line.rstrip().split()
                if len(parts) >= 4 and not parts[0].startswith("("):
                    # commit hash, source, final line ranges, num_lines
                    current_commit = parts[0]
                elif line.startswith("author "):
                    current_author = line[7:]
                elif line.startswith("author-time "):
                    current_date = line[12:]
            else:
                # This is the source line content (after tab)
                current_line = line[1:]
                if current_commit and current_author and current_date and current_line:
                    entries.append(
                        f"{current_commit[:8]} {current_author} {current_date} | {current_line}"
                    )
                current_line = None
                current_author = None
                current_date = None
        if not entries:
            entries = [f"Could not parse blame output for {args.path}"]
        text, truncated = cap_text("\n".join(entries), self.ctx.max_output_chars, "blame output")
        return ToolResult(output=text, truncated=truncated)


class GitRemoteArgs(BaseModel):
    action: Literal["list", "add", "remove", "fetch"] = Field(
        default="list",
        description=(
            "list: show remotes; add: register a new; remove: delete; fetch: fetch from remote"
        ),
    )
    name: str | None = Field(
        default=None, description="Remote name (required for add/remove/fetch)"
    )
    url: str | None = Field(default=None, description="Remote URL (required for add)")

    @model_validator(mode="after")
    def _validate(self) -> GitRemoteArgs:
        if self.action in ("add", "remove", "fetch") and not self.name:
            raise ValueError(f"name is required for action={self.action!r}")
        if self.action == "add" and not self.url:
            raise ValueError("url is required for action='add'")
        return self


class GitRemote(GitTool[GitRemoteArgs]):
    name = "git_remote"
    description = "List, add, remove, or fetch from git remotes."
    permission = Permission.mutating
    Args = GitRemoteArgs

    async def run(self, args: GitRemoteArgs) -> ToolResult:
        if args.action == "list":
            out = await self._git_text(self.ctx, "remote", "-v")
            return ToolResult(output=out.rstrip() or "No remotes configured.")
        assert args.name is not None  # guaranteed by model_validator
        if args.action == "add":
            assert args.url is not None
            await self._git_text(self.ctx, "remote", "add", args.name, args.url)
            return ToolResult(output=f"Added remote '{args.name}' -> {args.url}.")
        if args.action == "remove":
            await self._git_text(self.ctx, "remote", "remove", args.name)
            return ToolResult(output=f"Removed remote '{args.name}'.")
        # fetch
        argv: list[str] = ["fetch"]
        if args.name:
            argv.append(args.name)
        out = await self._git_text(self.ctx, *argv)
        return ToolResult(output=out.rstrip() or f"Fetched from {args.name or 'all remotes'}.")
