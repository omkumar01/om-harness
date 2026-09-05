"""Filesystem tools: list, read, search, write, and edit repository files."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from om_harness.tools.base import (
    BaseTool,
    Permission,
    ToolError,
    ToolResult,
    cap_text,
    resolve_in_repo,
)

# Directories never walked by list/search (runtime, VCS, dependency caches).
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".om-harness",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".idea",
    ".vscode",
}

SKIP_SUFFIXES = {".pyc", ".pyo", ".so", ".dll", ".exe", ".lock", ".png", ".jpg", ".gif", ".zip"}
MAX_SEARCHABLE_FILE_BYTES = 1_000_000


def iter_repo_files(repo_root: Path, limit: int | None = None) -> list[Path]:
    """Deterministic, bounded walk of the repo skipping junk directories."""
    files: list[Path] = []
    stack = [repo_root]
    while stack and (limit is None or len(files) < limit):
        current = stack.pop()
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        dirs: list[Path] = []
        for entry in entries:
            if entry.is_dir():
                if entry.name not in SKIP_DIRS and not entry.is_symlink():
                    dirs.append(entry)
                continue
            if entry.suffix.lower() in SKIP_SUFFIXES:
                continue
            files.append(entry)
            if limit is not None and len(files) >= limit:
                break
        stack.extend(reversed(dirs))  # keep lexicographic depth-first order
    return files


class ListFilesArgs(BaseModel):
    subdirectory: str = Field(default="", description="Optional subdirectory to list from")
    max_entries: int = Field(default=500, ge=1, le=5000)


class ListFiles(BaseTool[ListFilesArgs]):
    name = "list_files"
    description = "List files in the repository (relative paths)."
    permission = Permission.read_only
    Args = ListFilesArgs

    async def run(self, args: ListFilesArgs) -> ToolResult:
        base = (
            resolve_in_repo(self.ctx, args.subdirectory)
            if args.subdirectory
            else self.ctx.repo_root
        )
        if not base.exists():
            raise ToolError(f"subdirectory {args.subdirectory!r} does not exist")
        files = iter_repo_files(base, limit=args.max_entries + 1)
        rel_base = base.relative_to(self.ctx.repo_root) if base != self.ctx.repo_root else Path("")
        lines = [str(rel_base / f.relative_to(base)).replace("\\", "/") for f in files]
        truncated = len(lines) > args.max_entries
        output = "\n".join(lines[: args.max_entries])
        text, cap_hit = cap_text(output, self.ctx.max_output_chars, "file list")
        return ToolResult(
            output=text,
            truncated=truncated or cap_hit,
            data={"count": len(lines[: args.max_entries])},
        )


class ReadFileArgs(BaseModel):
    path: str = Field(description="Repo-relative file path")
    start_line: int = Field(default=1, ge=1, description="1-based line to start from")
    max_lines: int = Field(default=400, ge=1, le=5000)


class ReadFile(BaseTool[ReadFileArgs]):
    name = "read_file"
    description = "Read a text file from the repository (truncated to the context cap)."
    permission = Permission.read_only
    Args = ReadFileArgs

    async def run(self, args: ReadFileArgs) -> ToolResult:
        path = resolve_in_repo(self.ctx, args.path)
        if not path.is_file():
            raise ToolError(f"file {args.path!r} does not exist")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ToolError(f"cannot read {args.path!r}: {exc}") from exc
        lines = text.splitlines()
        selected = lines[args.start_line - 1 : args.start_line - 1 + args.max_lines]
        header = "" if args.start_line == 1 else f"[starting at line {args.start_line}]\n"
        body, truncated = cap_text(
            header + "\n".join(selected), self.ctx.max_file_read_chars, args.path
        )
        return ToolResult(output=body, truncated=truncated)


class SearchFilesArgs(BaseModel):
    pattern: str = Field(description="Regular expression to search for")
    subdirectory: str = Field(default="")
    max_results: int = Field(default=50, ge=1, le=500)


class SearchFiles(BaseTool[SearchFilesArgs]):
    name = "search_files"
    description = "Search file contents with a regular expression; returns file:line matches."
    permission = Permission.read_only
    Args = SearchFilesArgs

    async def run(self, args: SearchFilesArgs) -> ToolResult:
        try:
            regex = re.compile(args.pattern)
        except re.error as exc:
            raise ToolError(f"invalid regex: {exc}") from exc
        base = (
            resolve_in_repo(self.ctx, args.subdirectory)
            if args.subdirectory
            else self.ctx.repo_root
        )
        matches: list[str] = []
        for path in iter_repo_files(base):
            if len(matches) >= args.max_results:
                break
            if path.stat().st_size > MAX_SEARCHABLE_FILE_BYTES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = path.relative_to(self.ctx.repo_root).as_posix()
            for lineno, line in enumerate(text.splitlines(), start=1):
                if regex.search(line):
                    matches.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                    if len(matches) >= args.max_results:
                        break
        if not matches:
            return ToolResult(output="No matches found.")
        return ToolResult(output="\n".join(matches), data={"count": len(matches)})


class WriteFileArgs(BaseModel):
    path: str = Field(description="Repo-relative file path")
    content: str = Field(description="Full file content to write")


class WriteFile(BaseTool[WriteFileArgs]):
    name = "write_file"
    description = "Create or overwrite a file with the given content (parents are created)."
    permission = Permission.mutating
    Args = WriteFileArgs

    async def run(self, args: WriteFileArgs) -> ToolResult:
        path = resolve_in_repo(self.ctx, args.path)
        if path.is_dir():
            raise ToolError(f"{args.path!r} is a directory")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args.content, encoding="utf-8")
        return ToolResult(
            output=f"Wrote {len(args.content)} characters to {args.path}",
            data={"path": args.path},
        )


class EditFileArgs(BaseModel):
    path: str = Field(description="Repo-relative file path")
    old_string: str = Field(description="Exact text to replace")
    new_string: str = Field(description="Replacement text")
    replace_all: bool = Field(default=False, description="Replace every occurrence")


class EditFile(BaseTool[EditFileArgs]):
    name = "edit_file"
    description = "Replace an exact substring in a file (like a minimal search/replace patch)."
    permission = Permission.mutating
    Args = EditFileArgs

    async def run(self, args: EditFileArgs) -> ToolResult:
        path = resolve_in_repo(self.ctx, args.path)
        if not path.is_file():
            raise ToolError(f"file {args.path!r} does not exist")
        text = path.read_text(encoding="utf-8", errors="replace")
        count = text.count(args.old_string)
        if count == 0:
            raise ToolError(f"old_string not found in {args.path!r}")
        if count > 1 and not args.replace_all:
            raise ToolError(
                f"old_string matches {count} occurrences in {args.path!r}; "
                "provide more context or set replace_all=true"
            )
        if args.replace_all:
            updated = text.replace(args.old_string, args.new_string)
            replaced = count
        else:
            updated = text.replace(args.old_string, args.new_string, 1)
            replaced = 1
        path.write_text(updated, encoding="utf-8")
        return ToolResult(
            output=f"Edited {args.path} ({replaced} replacement(s))",
            data={"path": args.path},
        )
