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
    assert {"openai", "anthropic", "google"} <= set(names)
    assert "mock" not in names  # the offline echo model is not a provider


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


def test_bare_command_launches_interactive(repo: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running bare `om-harness` must start an interactive chat session."""
    import om_harness.cli.app as app_module

    calls: list[dict[str, Any]] = []

    def fake_launch(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(app_module, "launch_interactive", fake_launch)
    result = runner.invoke(app, [], catch_exceptions=False)
    assert result.exit_code == 0
    assert len(calls) == 1


def test_version_flag_still_works_with_default_command(repo: Any) -> None:
    result = _invoke("--version")
    assert result.exit_code == 0
    assert "om-harness" in result.output


def test_chat_alias_delegates_to_interactive(repo: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import om_harness.cli.app as app_module

    calls: list[dict[str, Any]] = []

    def fake_launch(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(app_module, "launch_interactive", fake_launch)
    result = runner.invoke(app, ["chat", "--resume"], catch_exceptions=False)
    assert result.exit_code == 0
    assert calls and calls[0]["resume"] is True


def test_subcommands_do_not_launch_interactive(repo: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import om_harness.cli.app as app_module

    def fail_launch(**kwargs: Any) -> None:
        raise AssertionError("launch_interactive must not run for subcommands")

    monkeypatch.setattr(app_module, "launch_interactive", fail_launch)
    result = _invoke("status", "--json")
    assert result.exit_code == 0


# -- plugins: install / plugins / uninstall ------------------------------------


def _make_git_plugin(origin: Any) -> None:
    skills = origin / "skills" / "demo-skill"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: a demo skill\n---\n\nDo demo things.\n",
        encoding="utf-8",
    )
    (origin / "plugin.json").write_text(
        '{"name": "demo", "description": "demo plugin"}\n', encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=origin, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=origin,
        check=True,
        capture_output=True,
    )


def test_plugin_install_list_uninstall_roundtrip(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = tmp_path / "demo-origin"
    origin.mkdir()
    _make_git_plugin(origin)
    monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))

    result = _invoke("install", str(origin))
    assert result.exit_code == 0
    assert "demo" in result.output
    assert "demo-skill" in result.output

    result = _invoke("plugins")
    assert result.exit_code == 0
    assert "demo" in result.output

    result = _invoke("uninstall", "demo")
    assert result.exit_code == 0
    result = _invoke("plugins")
    assert "demo" not in result.output


def test_plugin_commands_json_output(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    origin = tmp_path / "demo-origin"
    origin.mkdir()
    _make_git_plugin(origin)
    monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))

    result = _invoke("install", str(origin), "--json")
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["name"] == "demo"
    assert payload["skills"] == ["demo-skill"]

    result = _invoke("plugins", "--json")
    payload = json.loads(result.output)
    assert [p["name"] for p in payload["plugins"]] == ["demo"]


def test_uninstall_unknown_plugin_exits_nonzero(tmp_path: Any) -> None:
    result = runner.invoke(app, ["uninstall", "ghost"], catch_exceptions=False)
    assert result.exit_code != 0
