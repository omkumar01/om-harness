"""Contract tests for the CLI: commands, exit codes, and --json output.

Uses Typer's CliRunner so everything is exercised in-process; runs are
offline (mock provider).
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest
from typer.testing import CliRunner

from om_harness.cli.app import app

runner = CliRunner()


@pytest.fixture
def repo(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "app.py").write_text("print('hi')\n")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _invoke(*args: str) -> Any:
    return runner.invoke(app, list(args), catch_exceptions=False)


def test_version_flag() -> None:
    result = _invoke("--version")
    assert result.exit_code == 0
    assert "om-harness" in result.output


def test_init_creates_state(repo: Any) -> None:
    result = _invoke("init")
    assert result.exit_code == 0
    assert (repo / ".om-harness").is_dir()
    assert ".om-harness/" in (repo / ".gitignore").read_text()


def test_providers_json_lists_providers(repo: Any) -> None:
    result = _invoke("providers", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    names = [p["name"] for p in data["providers"]]
    assert {"openai", "anthropic", "google", "mock"} <= set(names)
    mock = next(p for p in data["providers"] if p["name"] == "mock")
    assert mock["available"] is True


def test_doctor_json(repo: Any) -> None:
    _invoke("init")
    result = _invoke("doctor", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    names = {item["name"] for item in data["items"]}
    assert "git_repository" in names
    assert "providers" in names


def test_status_json_before_and_after_run(repo: Any) -> None:
    _invoke("init")
    result = _invoke("status", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["sessions"] == 0


def test_run_json_completes_offline(repo: Any) -> None:
    _invoke("init")
    result = _invoke("run", "inspect the repository layout", "--json")
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["status"] == "completed"
    assert data["session_id"]
    assert data["results"][0]["status"] == "completed"
    assert data["plan"]["strategy"] in {"single", "sequential"}


def test_run_default_output_is_compact(repo: Any) -> None:
    _invoke("init")
    result = _invoke("run", "what does app.py do")
    assert result.exit_code == 0, result.output
    # Compact UX: a summary appears; no raw tool payloads flooding stdout.
    assert "completed" in result.output.lower()


def test_resume_json_uses_existing_session(repo: Any) -> None:
    _invoke("init")
    first = json.loads(_invoke("run", "first goal", "--json").output)
    second = json.loads(
        _invoke("run", "second goal", "--json", "--session", first["session_id"]).output
    )
    assert second["session_id"] == first["session_id"]


def test_status_after_run_shows_session(repo: Any) -> None:
    _invoke("init")
    _invoke("run", "a goal", "--json")
    data = json.loads(_invoke("status", "--json").output)
    assert data["sessions"] == 1
    assert data["checkpoints"] >= 1


def test_agent_command_lists_tools(repo: Any) -> None:
    result = _invoke("agent", "--list-tools", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    tool_names = [t["name"] for t in data["tools"]]
    assert "read_file" in tool_names
    assert "write_file" in tool_names
    permissions = {t["name"]: t["permission"] for t in data["tools"]}
    assert permissions["read_file"] == "read_only"
    assert permissions["git_restore"] == "destructive"


def test_config_show_json(repo: Any) -> None:
    result = _invoke("config", "show", "--json")
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "routing" in data
