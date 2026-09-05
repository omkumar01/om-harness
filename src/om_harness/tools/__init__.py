"""Repository tool system: files, shell, git, tests, and the guarded executor."""

from om_harness.tools.approval import ApprovalDecision, ApprovalEngine
from om_harness.tools.base import BaseTool, Permission, ToolContext, ToolError, ToolResult
from om_harness.tools.envinfo import RepoInfo
from om_harness.tools.files import EditFile, ListFiles, ReadFile, SearchFiles, WriteFile
from om_harness.tools.git import GitAdd, GitCommit, GitDiff, GitLog, GitRestore, GitShow, GitStatus
from om_harness.tools.registry import GuardedToolExecutor, ToolRegistry
from om_harness.tools.shell import RunShell
from om_harness.tools.testing import RunTests


def build_default_registry(ctx: ToolContext) -> ToolRegistry:
    """The standard coding-agent toolset, all sharing one ToolContext."""
    registry = ToolRegistry()
    for tool_cls in (
        ListFiles,
        ReadFile,
        SearchFiles,
        WriteFile,
        EditFile,
        RunShell,
        GitStatus,
        GitDiff,
        GitLog,
        GitShow,
        GitAdd,
        GitCommit,
        GitRestore,
        RunTests,
        RepoInfo,
    ):
        registry.register(tool_cls(ctx))
    return registry


__all__ = [
    "ApprovalDecision",
    "ApprovalEngine",
    "BaseTool",
    "EditFile",
    "GitAdd",
    "GitCommit",
    "GitDiff",
    "GitLog",
    "GitRestore",
    "GitShow",
    "GitStatus",
    "GuardedToolExecutor",
    "ListFiles",
    "Permission",
    "ReadFile",
    "RepoInfo",
    "RunShell",
    "RunTests",
    "SearchFiles",
    "ToolContext",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "WriteFile",
    "build_default_registry",
]
