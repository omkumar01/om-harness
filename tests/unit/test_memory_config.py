"""Contract tests for memory-related configuration."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from om_harness.config.loader import ConfigError, HarnessConfig, load_config


def test_memory_config_defaults() -> None:
    config = HarnessConfig()
    assert config.memory.enabled is True
    assert config.memory.max_entries == 1000
    assert config.memory.max_fact_chars == 500
    assert config.memory.auto_extract is True
    assert config.memory.compression_strategy == "mechanical"
    assert config.memory.retrieval_limit == 10
    assert config.memory.fact_ttl_days == 7


def test_context_config_has_max_context_tokens() -> None:
    config = HarnessConfig()
    assert config.context.max_context_tokens is None


def test_memory_config_from_toml(tmp_path: Any) -> None:
    (tmp_path / "om-harness.toml").write_text(
        """
[memory]
enabled = false
max_entries = 500
compression_strategy = "llm"
retrieval_limit = 5
fact_ttl_days = 0  # 0 means no TTL (facts never expire)

[context]
max_context_tokens = 8000
"""
    )
    config = load_config(tmp_path)
    assert config.memory.enabled is False
    assert config.memory.max_entries == 500
    assert config.memory.compression_strategy == "llm"
    assert config.memory.retrieval_limit == 5
    assert config.memory.fact_ttl_days is None  # 0 → None
    assert config.context.max_context_tokens == 8000


def test_memory_config_from_pyproject_table(tmp_path: Any) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.om-harness.memory]
max_entries = 200
"""
    )
    config = load_config(tmp_path)
    assert config.memory.max_entries == 200


def test_memory_config_invalid_strategy_raises(tmp_path: Any) -> None:
    (tmp_path / "om-harness.toml").write_text('[memory]\ncompression_strategy = "invalid"\n')
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_memory_config_max_entries_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        HarnessConfig(memory={"max_entries": 0})


def test_memory_config_fact_ttl_can_be_disabled() -> None:
    config = HarnessConfig(memory={"fact_ttl_days": None})
    assert config.memory.fact_ttl_days is None
