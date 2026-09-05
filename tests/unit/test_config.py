"""Contract tests for configuration loading and secret redaction."""

from __future__ import annotations

import os
from typing import Any

import pytest

from om_harness.config.loader import ConfigError, HarnessConfig, load_config
from om_harness.config.secrets import SecretRedactor


def test_defaults() -> None:
    config = HarnessConfig()
    assert config.routing.default_model.startswith(("openai:", "anthropic:", "google-gla:"))
    assert config.approval.policy == "ask"
    assert config.max_concurrency >= 1
    assert config.verbosity == "compact"


def test_load_from_om_harness_toml(tmp_path: Any) -> None:
    (tmp_path / "om-harness.toml").write_text(
        """
[routing]
default_model = "anthropic:claude-sonnet-4-5"
[routing.task_models]
explore = "openai:gpt-4o-mini"

[approval]
policy = "allowlist"
allowlist = ["write_file", "run_tests"]
"""
    )
    config = load_config(tmp_path)
    assert config.routing.default_model == "anthropic:claude-sonnet-4-5"
    assert config.routing.task_models["explore"] == "openai:gpt-4o-mini"
    assert config.approval.policy == "allowlist"
    assert "write_file" in config.approval.allowlist


def test_load_from_pyproject_tool_table(tmp_path: Any) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.om-harness]
max_concurrency = 8
"""
    )
    config = load_config(tmp_path)
    assert config.max_concurrency == 8


def test_env_overrides_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "om-harness.toml").write_text('[routing]\ndefault_model = "openai:gpt-4o"\n')
    monkeypatch.setenv("OM_HARNESS_DEFAULT_MODEL", "google-gla:gemini-2.0-flash")
    monkeypatch.setenv("OM_HARNESS_MAX_CONCURRENCY", "2")
    monkeypatch.setenv("OM_HARNESS_APPROVAL_POLICY", "auto")
    config = load_config(tmp_path)
    assert config.routing.default_model == "google-gla:gemini-2.0-flash"
    assert config.max_concurrency == 2
    assert config.approval.policy == "auto"


def test_invalid_policy_raises(tmp_path: Any) -> None:
    (tmp_path / "om-harness.toml").write_text('[approval]\npolicy = "yolo"\n')
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_explicit_config_path(tmp_path: Any) -> None:
    custom = tmp_path / "custom.toml"
    custom.write_text("[routing]\ndefault_model = 'openai:gpt-4.1'\n")
    config = load_config(tmp_path, config_path=custom)
    assert config.routing.default_model == "openai:gpt-4.1"


def test_missing_repo_root_is_fine(tmp_path: Any) -> None:
    config = load_config(tmp_path)
    # The isolated test home pre-seeds a mock default for offline runs;
    # everything else must match the built-in defaults.
    assert config.max_concurrency == HarnessConfig().max_concurrency
    assert config.approval == HarnessConfig().approval
    assert config.budget == HarnessConfig().budget


def test_redactor_replaces_secret_values() -> None:
    redactor = SecretRedactor(["super-secret-value"])
    text = "config uses super-secret-value inside"
    assert "super-secret-value" not in redactor.redact_text(text)
    assert "REDACTED" in redactor.redact_text(text)


def test_redactor_redacts_by_key_name() -> None:
    redactor = SecretRedactor([])
    data = {"api_key": "whatever", "nested": {"token": "abc", "name": "ok"}}
    out = redactor.redact_value(data)
    assert out["api_key"] == "***REDACTED***"
    assert out["nested"]["token"] == "***REDACTED***"
    assert out["nested"]["name"] == "ok"


def test_redactor_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret")
    redactor = SecretRedactor.from_env(os.environ)
    assert "sk-openai-secret" not in redactor.redact_text("key is sk-openai-secret")
