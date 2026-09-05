"""Repository index: a compact, cached file map used for context scoping.

The index is built once per session and reused. Its summary is a bounded
file listing (paths + sizes, never contents) so every agent call gets the
same cheap spatial map instead of re-exploring the repository.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from om_harness.tools.files import iter_repo_files


class FileEntry(BaseModel):
    path: str  # repo-relative, posix separators
    size: int


class RepoIndex:
    """Cached, bounded listing of repository files."""

    def __init__(self, repo_root: Path, max_files: int = 500) -> None:
        self.repo_root = Path(repo_root)
        self.max_files = max_files
        self.files: list[FileEntry] = []
        self.total_files: int = 0
        self.built_at: datetime | None = None

    @property
    def is_built(self) -> bool:
        return self.built_at is not None

    def build(self) -> None:
        """Walk the repo once; no-op while the cache is valid."""
        if self.built_at is not None:
            return
        # Count everything (stat-only walk), but keep details bounded.
        all_paths = iter_repo_files(self.repo_root)
        self.total_files = len(all_paths)
        self.files = [
            FileEntry(path=p.relative_to(self.repo_root).as_posix(), size=p.stat().st_size)
            for p in all_paths[: self.max_files]
        ]
        self.built_at = datetime.now(UTC)

    def invalidate(self) -> None:
        self.built_at = None
        self.files = []
        self.total_files = 0

    def summary(self, max_files: int | None = None) -> str:
        """Compact text form for a system/user prompt, with a tail marker."""
        self.build()
        cap = max_files if max_files is not None else self.max_files
        lines = [f"{entry.path} ({entry.size}B)" for entry in self.files[:cap]]
        if self.total_files > cap:
            lines.append(f"... +{self.total_files - cap} more files (index truncated)")
        header = f"Repository files ({min(self.total_files, cap)} shown, repo root: .):\n"
        return header + "\n".join(lines)
