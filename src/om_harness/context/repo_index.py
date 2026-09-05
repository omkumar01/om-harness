"""Repository index: a compact, cached file map used for context scoping.

The index is built once per session and reused. Its summary is a bounded
file listing (paths + sizes, never contents) so every agent call gets the
same cheap spatial map instead of re-exploring the repository.

When a ``cache_dir`` is supplied (the harness passes the user-level cache),
the index also persists across processes:
``<cache_dir>/repo-index/<sha1(repo-path)>.json`` — reused while fresher
than ``cache_ttl_hours``, invalidated explicitly or by TTL expiry.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from om_harness.tools.files import iter_repo_files

CACHE_SUBDIR = "repo-index"


class FileEntry(BaseModel):
    path: str  # repo-relative, posix separators
    size: int


class _CachePayload(BaseModel):
    repo_root: str
    max_files: int
    built_at: str
    total_files: int
    files: list[FileEntry]


def _cache_file(cache_dir: Path, repo_root: Path) -> Path:
    digest = hashlib.sha256(str(repo_root.resolve()).encode("utf-8")).hexdigest()[:16]
    return Path(cache_dir) / CACHE_SUBDIR / f"{digest}.json"


class RepoIndex:
    """Cached, bounded listing of repository files."""

    def __init__(
        self,
        repo_root: Path,
        max_files: int = 500,
        cache_dir: Path | None = None,
        cache_ttl_hours: float = 24.0,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.max_files = max_files
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.cache_ttl_hours = cache_ttl_hours
        self.files: list[FileEntry] = []
        self.total_files: int = 0
        self.built_at: datetime | None = None

    @property
    def is_built(self) -> bool:
        return self.built_at is not None

    @property
    def _cache_file(self) -> Path | None:
        if self.cache_dir is None:
            return None
        return _cache_file(self.cache_dir, self.repo_root)

    def build(self) -> None:
        """Build the index once; reuse memory, then the disk cache."""
        if self.built_at is not None:
            return
        if self._load_disk_cache():
            return
        # Count everything (stat-only walk), but keep details bounded.
        all_paths = iter_repo_files(self.repo_root)
        self.total_files = len(all_paths)
        self.files = [
            FileEntry(path=p.relative_to(self.repo_root).as_posix(), size=p.stat().st_size)
            for p in all_paths[: self.max_files]
        ]
        self.built_at = datetime.now(UTC)
        self._write_disk_cache()

    def _load_disk_cache(self) -> bool:
        path = self._cache_file
        if path is None or not path.is_file():
            return False
        try:
            payload = _CachePayload.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        built_at = datetime.fromisoformat(payload.built_at)
        if datetime.now(UTC) - built_at > timedelta(hours=self.cache_ttl_hours):
            return False
        if payload.max_files != self.max_files:
            return False
        self.files = payload.files
        self.total_files = payload.total_files
        self.built_at = built_at
        return True

    def _write_disk_cache(self) -> None:
        path = self._cache_file
        if path is None or self.built_at is None:
            return
        payload = _CachePayload(
            repo_root=str(self.repo_root),
            max_files=self.max_files,
            built_at=self.built_at.isoformat(),
            total_files=self.total_files,
            files=self.files,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload.model_dump_json(), encoding="utf-8")

    def invalidate(self) -> None:
        """Drop the in-memory index and any persisted cache entry."""
        self.built_at = None
        self.files = []
        self.total_files = 0
        path = self._cache_file
        if path is not None and path.is_file():
            path.unlink()

    def summary(self, max_files: int | None = None) -> str:
        """Compact text form for a system/user prompt, with a tail marker."""
        self.build()
        cap = max_files if max_files is not None else self.max_files
        lines = [f"{entry.path} ({entry.size}B)" for entry in self.files[:cap]]
        if self.total_files > cap:
            lines.append(f"... +{self.total_files - cap} more files (index truncated)")
        header = f"Repository files ({min(self.total_files, cap)} shown, repo root: .):\n"
        return header + "\n".join(lines)
