"""Environment/repository inspection (read-only)."""

from __future__ import annotations

import platform
import sys

from pydantic import BaseModel

from om_harness.tools.base import Permission, ToolResult
from om_harness.tools.files import iter_repo_files
from om_harness.tools.git import GitTool


class RepoInfoArgs(BaseModel):
    pass


class RepoInfo(GitTool[RepoInfoArgs]):
    name = "repo_info"
    description = "Summarize the repository: branch, HEAD, languages, and file counts."
    permission = Permission.read_only
    Args = RepoInfoArgs

    async def run(self, args: RepoInfoArgs) -> ToolResult:
        lines = [f"python: {sys.version.split()[0]} ({platform.system().lower()})"]
        branch, head = "unknown", "unknown"
        try:
            branch = (await self._git_text(self.ctx, "rev-parse", "--abbrev-ref", "HEAD")).strip()
            head = (await self._git_text(self.ctx, "rev-parse", "--short", "HEAD")).strip()
            lines.append(f"git: branch {branch} @ {head}")
        except Exception:
            lines.append("git: not a git repository")
        files = iter_repo_files(self.ctx.repo_root, limit=5000)
        by_ext: dict[str, int] = {}
        for path in files:
            ext = path.suffix.lower() or "(none)"
            by_ext[ext] = by_ext.get(ext, 0) + 1
        top = sorted(by_ext.items(), key=lambda kv: kv[1], reverse=True)[:8]
        summary = ", ".join(f"{ext}={count}" for ext, count in top)
        lines.append(f"files: {len(files)} found ({summary})")
        return ToolResult(output="\n".join(lines), data={"branch": branch, "head": head})
