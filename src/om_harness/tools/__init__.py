"""Repository tool system: files, shell, git, tests, and the guarded executor."""

from om_harness.tools.approval import ApprovalDecision, ApprovalEngine
from om_harness.tools.base import BaseTool, Permission, ToolContext, ToolError, ToolResult
from om_harness.tools.envinfo import RepoInfo
from om_harness.tools.files import (
    CountLines,
    EditFile,
    FindFiles,
    ListFiles,
    ReadFile,
    SearchFiles,
    WriteFile,
)
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
    GitShow,
    GitStash,
    GitStatus,
)
from om_harness.tools.quality import FormatCode, LintCode
from om_harness.tools.registry import GuardedToolExecutor, ToolRegistry
from om_harness.tools.shell import RunShell
from om_harness.tools.testing import RunTests
from om_harness.tools.web import FetchUrl


def build_default_registry(ctx: ToolContext) -> ToolRegistry:
    """The standard coding-agent toolset, all sharing one ToolContext."""
    registry = ToolRegistry()
    for tool_cls in (
        ListFiles,
        ReadFile,
        SearchFiles,
        WriteFile,
        EditFile,
        FindFiles,
        CountLines,
        RunShell,
        GitStatus,
        GitDiff,
        GitLog,
        GitLogGraph,
        GitShow,
        GitBlame,
        GitBranch,
        GitStash,
        GitRemote,
        GitAdd,
        GitCommit,
        GitRestore,
        RunTests,
        FormatCode,
        LintCode,
        FetchUrl,
        RepoInfo,
    ):
        registry.register(tool_cls(ctx))
    return registry


__all__ = [
    "ApprovalDecision",
    "ApprovalEngine",
    "BaseTool",
    "CountLines",
    "EditFile",
    "FetchUrl",
    "FindFiles",
    "FormatCode",
    "GitAdd",
    "GitBlame",
    "GitBranch",
    "GitCommit",
    "GitDiff",
    "GitLog",
    "GitLogGraph",
    "GitRemote",
    "GitRestore",
    "GitShow",
    "GitStash",
    "GitStatus",
    "GuardedToolExecutor",
    "LintCode",
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
