"""Contract tests for auto-detecting formatters and linters."""

from __future__ import annotations

from typing import Any

import pytest

from om_harness.tools.base import Permission, ToolContext, ToolError
from om_harness.tools.quality import FormatCode, LintCode, detect_formatter, detect_linter


@pytest.fixture
def ctx(tmp_path: Any) -> ToolContext:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    return ToolContext(repo_root=tmp_path)


# -- detection ---------------------------------------------------------------


def test_detect_formatter_none_without_tools(tmp_path: Any) -> None:
    """No formatter detected when executables aren't on PATH."""
    result = detect_formatter(tmp_path)
    assert result is None


def test_detect_formatter_ruff_when_available(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda cmd: "/fake/ruff" if cmd == "ruff" else None)
    result = detect_formatter(ctx.repo_root)
    assert result is not None
    name, argv = result
    assert name == "ruff"
    assert "format" in argv


def test_detect_linter_none_without_tools(tmp_path: Any) -> None:
    result = detect_linter(tmp_path)
    assert result is None


def test_detect_linter_ruff_when_available(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda cmd: "/fake/ruff" if cmd == "ruff" else None)
    result = detect_linter(ctx.repo_root)
    assert result is not None
    name, argv = result
    assert name == "ruff"
    assert "check" in argv


def test_detect_formatter_falls_back_to_black(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\n")
    monkeypatch.setattr("shutil.which", lambda cmd: "/fake/black" if cmd == "black" else None)
    result = detect_formatter(tmp_path)
    assert result is not None
    assert result[0] == "black"


def test_detect_linter_falls_back_to_flake8(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda cmd: "/fake/flake8" if cmd == "flake8" else None)
    result = detect_linter(tmp_path)
    assert result is not None
    assert result[0] == "flake8"


# -- format_code tool --------------------------------------------------------


async def test_format_code_no_formatter_detected(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(ToolError, match="no formatter detected"):
        await FormatCode(ctx).run(FormatCode.Args())


async def test_format_code_with_mocked_ruff(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mock that ruff is available and returns success.
    monkeypatch.setattr(
        "om_harness.tools.quality.shutil.which",
        lambda cmd: "/fake/ruff" if cmd == "ruff" else None,
    )
    monkeypatch.setattr(
        "om_harness.tools.quality.run_process",
        _make_fake_run_process(0, "Would format files.\n", ""),
    )
    result = await FormatCode(ctx).run(FormatCode.Args())
    assert result.ok
    assert result.data["formatter"] == "ruff"
    assert result.data["exit_code"] == 0
    assert FormatCode.permission == Permission.mutating


# -- lint_code tool ----------------------------------------------------------


async def test_lint_code_no_linter_detected(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    with pytest.raises(ToolError, match="no linter detected"):
        await LintCode(ctx).run(LintCode.Args())


async def test_lint_code_with_mocked_flake8(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "om_harness.tools.quality.shutil.which",
        lambda cmd: "/fake/flake8" if cmd == "flake8" else None,
    )
    monkeypatch.setattr(
        "om_harness.tools.quality.run_process",
        _make_fake_run_process(0, "All checks passed.\n", ""),
    )
    result = await LintCode(ctx).run(LintCode.Args())
    assert result.ok
    assert result.data["linter"] == "flake8"
    assert result.data["exit_code"] == 0
    assert LintCode.permission == Permission.mutating


async def test_lint_code_with_issues(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "om_harness.tools.quality.shutil.which",
        lambda cmd: "/fake/ruff" if cmd == "ruff" else None,
    )
    monkeypatch.setattr(
        "om_harness.tools.quality.run_process",
        _make_fake_run_process(1, "", "src/main.py:1:1: E501 line too long"),
    )
    result = await LintCode(ctx).run(LintCode.Args())
    assert not result.ok
    assert result.data["linter"] == "ruff"
    assert result.data["exit_code"] == 1


async def test_format_code_with_target(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "om_harness.tools.quality.shutil.which",
        lambda cmd: "/fake/ruff" if cmd == "ruff" else None,
    )
    monkeypatch.setattr(
        "om_harness.tools.quality.run_process",
        _make_fake_run_process(0, "Formatted.\n", ""),
    )
    result = await FormatCode(ctx).run(FormatCode.Args(target="src/main.py"))
    assert result.ok
    assert "src/main.py" in result.data["command"]


async def test_format_code_with_stderr(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "om_harness.tools.quality.shutil.which",
        lambda cmd: "/fake/ruff" if cmd == "ruff" else None,
    )
    monkeypatch.setattr(
        "om_harness.tools.quality.run_process",
        _make_fake_run_process(0, "Done.\n", "warning: deprecated"),
    )
    result = await FormatCode(ctx).run(FormatCode.Args())
    assert result.ok
    assert "stderr" in result.output


async def test_lint_code_with_fix(ctx: ToolContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "om_harness.tools.quality.shutil.which",
        lambda cmd: "/fake/ruff" if cmd == "ruff" else None,
    )
    monkeypatch.setattr(
        "om_harness.tools.quality.run_process",
        _make_fake_run_process(0, "All good.\n", ""),
    )
    result = await LintCode(ctx).run(LintCode.Args(fix=True))
    assert result.ok
    assert "--fix" in result.data["command"]


async def test_lint_code_with_target_and_stderr(
    ctx: ToolContext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "om_harness.tools.quality.shutil.which",
        lambda cmd: "/fake/flake8" if cmd == "flake8" else None,
    )
    monkeypatch.setattr(
        "om_harness.tools.quality.run_process",
        _make_fake_run_process(1, "", "src/main.py:1:1: F401 unused import"),
    )
    result = await LintCode(ctx).run(LintCode.Args(target="src/main.py"))
    assert not result.ok
    assert "src/main.py" in result.data["command"]
    assert "stderr" in result.output


# -- helpers -----------------------------------------------------------------


def _make_fake_run_process(returncode: int, stdout: str, stderr: str):
    """Return an async function that mimics run_process's return signature."""

    async def _fake(*_args: object, **_kwargs: object) -> tuple[int, str, str, bool]:
        return returncode, stdout, stderr, False

    return _fake
