"""Contract tests for user-level storage (~/.om-harness) and paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from om_harness.config.paths import (
    ensure_user_dirs,
    user_cache_dir,
    user_config_dir,
    user_config_file,
    user_home,
    user_models_json,
    user_plugins_dir,
    user_skills_dir,
)


@pytest.fixture
def home(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("OM_HARNESS_HOME", str(tmp_path / "om-home"))
    return tmp_path / "om-home"


def test_user_home_honors_env_override(home: Any) -> None:
    assert user_home() == home


def test_user_home_defaults_to_dot_om_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OM_HARNESS_HOME", raising=False)
    assert user_home().name == ".om-harness"


def test_layout_paths(home: Any) -> None:
    assert user_config_dir() == home / "config"
    assert user_models_json() == home / "config" / "models.json"
    assert user_config_file() == home / "config" / "config.toml"
    assert user_cache_dir() == home / "cache"


def test_ensure_user_dirs_creates_layout_and_detects_first_run(home: Any) -> None:
    assert ensure_user_dirs() is True  # first run
    assert user_config_dir().is_dir()
    assert user_cache_dir().is_dir()
    assert ensure_user_dirs() is False  # second run: not first anymore


def test_user_skills_dir_defaults_to_dot_agents_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OM_HARNESS_SKILLS_DIR", raising=False)
    assert user_skills_dir() == Path.home() / ".agents" / "skills"


def test_user_skills_dir_honors_env_override(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OM_HARNESS_SKILLS_DIR", str(tmp_path / "skills"))
    assert user_skills_dir() == tmp_path / "skills"


def test_user_plugins_dir_defaults_under_om_harness_home(
    home: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OM_HARNESS_PLUGINS_DIR", raising=False)
    assert user_plugins_dir() == home / "plugins"


def test_user_plugins_dir_honors_env_override(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OM_HARNESS_PLUGINS_DIR", str(tmp_path / "plugins"))
    assert user_plugins_dir() == tmp_path / "plugins"
