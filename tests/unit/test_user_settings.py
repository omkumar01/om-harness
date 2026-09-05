"""Contract tests for live config updates persisted to ~/.om-harness."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from om_harness.config.loader import load_config
from om_harness.config.user_settings import SettingsError, apply_config_update
from om_harness.harness import Harness


@pytest.fixture
def harness(tmp_path: Any, home: Any) -> Any:
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    return Harness(repo_root=tmp_path, env={})


def test_set_model_updates_live_config_and_persists(harness: Any, home: Any) -> None:
    message = apply_config_update(harness, "model", "openai:gpt-4o")
    assert "gpt-4o" in message
    assert harness.config.routing.default_model == "openai:gpt-4o"
    # Router sees the change immediately (same routing object).
    assert harness.router.config.default_model == "openai:gpt-4o"
    # Persisted to the user config file and readable by a fresh load.
    reloaded = load_config(harness.repo_root, env={})
    assert reloaded.routing.default_model == "openai:gpt-4o"


def test_set_approval_policy(harness: Any) -> None:
    apply_config_update(harness, "approval", "auto")
    assert harness.config.approval.policy == "auto"


def test_set_verbosity(harness: Any) -> None:
    apply_config_update(harness, "verbosity", "verbose")
    assert harness.config.verbosity == "verbose"


def test_set_max_concurrency_and_requests(harness: Any) -> None:
    apply_config_update(harness, "max_concurrency", "3")
    apply_config_update(harness, "max_requests", "25")
    assert harness.config.max_concurrency == 3
    assert harness.config.budget.max_requests == 25


def test_set_task_model(harness: Any) -> None:
    apply_config_update(harness, "task_model.explore", "openai:gpt-4o-mini")
    from om_harness.models.task import TaskType

    assert harness.config.routing.task_models[TaskType.explore] == "openai:gpt-4o-mini"


def test_invalid_model_value_persists_nothing(harness: Any, home: Any) -> None:
    with pytest.raises(SettingsError):
        apply_config_update(harness, "model", "bogus:model-x")
    reloaded = load_config(harness.repo_root, env={})
    assert reloaded.routing.default_model != "bogus:model-x"


def test_invalid_key_rejected(harness: Any) -> None:
    with pytest.raises(SettingsError, match="unknown config key"):
        apply_config_update(harness, "temperature", "0.7")


def test_invalid_enum_value_rejected(harness: Any) -> None:
    with pytest.raises(SettingsError):
        apply_config_update(harness, "approval", "yolo")


def test_persisted_updates_merge_not_replace(harness: Any) -> None:
    apply_config_update(harness, "model", "openai:gpt-4o")
    apply_config_update(harness, "verbosity", "debug")
    reloaded = load_config(harness.repo_root, env={})
    assert reloaded.routing.default_model == "openai:gpt-4o"
    assert reloaded.verbosity == "debug"
