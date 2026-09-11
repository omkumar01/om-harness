"""Contract tests for file tools: list/read/write/edit/search + path safety."""

from __future__ import annotations

from typing import Any

import pytest

from om_harness.tools.base import Permission, ToolContext, ToolError
from om_harness.tools.files import (
    CountLines,
    EditFile,
    FindFiles,
    ListFiles,
    ReadFile,
    SearchFiles,
    WriteFile,
)


@pytest.fixture
def ctx(tmp_path: Any) -> ToolContext:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (tmp_path / "README.md").write_text("# sample\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    return ToolContext(repo_root=tmp_path)


async def test_list_files_skips_git_and_hidden_runtime_dirs(ctx: ToolContext) -> None:
    result = await ListFiles(ctx).run(ListFiles.Args())
    assert result.ok
    assert "src/main.py" in result.output
    assert "README.md" in result.output
    assert ".git" not in result.output


async def test_list_files_respects_max_entries(tmp_path: Any) -> None:
    for i in range(10):
        (tmp_path / f"f{i}.txt").write_text("x")
    ctx = ToolContext(repo_root=tmp_path, max_output_chars=20_000)
    result = await ListFiles(ctx).run(ListFiles.Args(max_entries=3))
    assert result.truncated
    assert result.output.count(".txt") == 3


async def test_read_file(ctx: ToolContext) -> None:
    result = await ReadFile(ctx).run(ReadFile.Args(path="src/main.py"))
    assert result.ok
    assert "def main():" in result.output


async def test_read_file_truncates_long_files(tmp_path: Any) -> None:
    (tmp_path / "big.txt").write_text("x" * 5000)
    ctx = ToolContext(repo_root=tmp_path, max_file_read_chars=100)
    result = await ReadFile(ctx).run(ReadFile.Args(path="big.txt"))
    assert result.truncated
    assert len(result.output) <= ctx.max_file_read_chars + 60  # cap + truncation notice


async def test_read_file_rejects_traversal(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="outside the repository"):
        await ReadFile(ctx).run(ReadFile.Args(path="../secrets.txt"))


async def test_read_file_rejects_absolute_escape(tmp_path: Any) -> None:
    ctx = ToolContext(repo_root=tmp_path)
    with pytest.raises(ToolError, match="outside the repository"):
        await ReadFile(ctx).run(ReadFile.Args(path=str(tmp_path.parent / "elsewhere.txt")))


async def test_write_file_creates_parents(ctx: ToolContext) -> None:
    result = await WriteFile(ctx).run(WriteFile.Args(path="pkg/new/mod.py", content="x = 1\n"))
    assert result.ok
    assert (ctx.repo_root / "pkg" / "new" / "mod.py").read_text() == "x = 1\n"
    assert WriteFile.permission == Permission.mutating


async def test_edit_file_replaces_once(ctx: ToolContext) -> None:
    result = await EditFile(ctx).run(
        EditFile.Args(path="src/main.py", old_string="print('hello')", new_string="print('bye')")
    )
    assert result.ok
    assert "print('bye')" in (ctx.repo_root / "src" / "main.py").read_text()


async def test_edit_file_errors_when_not_found(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="not found"):
        await EditFile(ctx).run(
            EditFile.Args(path="src/main.py", old_string="absent", new_string="x")
        )


async def test_edit_file_errors_on_ambiguous_match(ctx: ToolContext) -> None:
    (ctx.repo_root / "dup.txt").write_text("same same\n")
    with pytest.raises(ToolError, match="2 occurrences"):
        await EditFile(ctx).run(EditFile.Args(path="dup.txt", old_string="same", new_string="x"))


async def test_edit_file_replace_all(ctx: ToolContext) -> None:
    (ctx.repo_root / "dup.txt").write_text("same same\n")
    result = await EditFile(ctx).run(
        EditFile.Args(path="dup.txt", old_string="same", new_string="x", replace_all=True)
    )
    assert result.ok
    assert (ctx.repo_root / "dup.txt").read_text() == "x x\n"


async def test_search_files_regex(ctx: ToolContext) -> None:
    result = await SearchFiles(ctx).run(SearchFiles.Args(pattern=r"def \w+"))
    assert result.ok
    assert "src/main.py" in result.output
    assert "def main" in result.output


async def test_search_files_no_match(ctx: ToolContext) -> None:
    result = await SearchFiles(ctx).run(SearchFiles.Args(pattern="zzz-not-there"))
    assert result.ok
    assert "no matches" in result.output.lower()


# -- find_files ----------------------------------------------------------------


async def test_find_files_by_extension(ctx: ToolContext) -> None:
    result = await FindFiles(ctx).run(FindFiles.Args(pattern="*.py"))
    assert result.ok
    assert "src/main.py" in result.output
    assert "README.md" not in result.output
    assert FindFiles.permission == Permission.read_only


async def test_find_files_no_match(ctx: ToolContext) -> None:
    result = await FindFiles(ctx).run(FindFiles.Args(pattern="*.rs"))
    assert result.ok
    assert "No files" in result.output


async def test_find_files_max_results(ctx: ToolContext) -> None:
    for i in range(10):
        (ctx.repo_root / f"file_{i}.txt").write_text("x")
    result = await FindFiles(ctx).run(FindFiles.Args(pattern="*.txt", max_results=3))
    assert result.ok
    assert result.data["count"] == 3


async def test_find_files_subdirectory(tmp_path: Any) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x")
    (tmp_path / "src" / "b.py").write_text("x")
    (tmp_path / "other.py").write_text("x")
    ctx = ToolContext(repo_root=tmp_path)
    result = await FindFiles(ctx).run(FindFiles.Args(pattern="*.py", subdirectory="src"))
    assert result.ok
    assert "src/a.py" in result.output
    assert "src/b.py" in result.output
    assert "other.py" not in result.output


# -- count_lines ---------------------------------------------------------------


async def test_count_lines_single_file(ctx: ToolContext) -> None:
    result = await CountLines(ctx).run(CountLines.Args(path="src/main.py"))
    assert result.ok
    assert CountLines.permission == Permission.read_only
    assert result.data["total_lines"] == 2  # "def main():" + "    print('hello')"
    assert result.data["file_count"] == 1


async def test_count_lines_directory(ctx: ToolContext) -> None:
    result = await CountLines(ctx).run(CountLines.Args(path="src"))
    assert result.ok
    assert result.data["file_count"] == 1
    assert result.data["total_lines"] == 2


async def test_count_lines_with_extensions(tmp_path: Any) -> None:
    (tmp_path / "a.py").write_text("line1\nline2\nline3\n")
    (tmp_path / "b.txt").write_text("line1\nline2\n")
    ctx = ToolContext(repo_root=tmp_path)
    result = await CountLines(ctx).run(CountLines.Args(path=".", extensions=[".py"]))
    assert result.ok
    assert result.data["file_count"] == 1
    assert result.data["total_lines"] == 3


async def test_count_lines_nonexistent(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="does not exist"):
        await CountLines(ctx).run(CountLines.Args(path="nonexistent.txt"))
