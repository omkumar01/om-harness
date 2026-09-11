"""Harness configuration: TOML files + environment variables, validated.

Precedence: defaults < ~/.om-harness/config/config.toml < repo-level file
(om-harness.toml or pyproject.toml [tool.om-harness]) < OM_HARNESS_* env
vars. Secrets are never read from config files — API keys come from the
environment only (see ``config.secrets``).
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from om_harness.config.paths import user_config_file
from om_harness.models.task import TaskType

CONFIG_FILENAME = "om-harness.toml"
PYPROJECT_FILENAME = "pyproject.toml"
PYPROJECT_TABLE = "om-harness"

ENV_PREFIX = "OM_HARNESS_"

_TIMEOUT_OFF_WORDS = {"off", "none", "disabled"}


def parse_timeout(value: Any) -> float | None:
    """Parse a timeout setting: seconds, or ``off``/``0`` to disable (None).

    Raises ``ValueError`` for non-numeric or negative values.
    """
    if isinstance(value, str) and value.strip().lower() in _TIMEOUT_OFF_WORDS:
        return None
    seconds = float(value)
    if seconds < 0:
        raise ValueError(f"timeout must be >= 0, got {seconds}")
    return None if seconds == 0 else seconds


class ConfigError(Exception):
    """Raised when configuration is malformed or semantically invalid."""


class Verbosity(StrEnum):
    compact = "compact"  # status lines + final summary only
    verbose = "verbose"  # add tool calls, agent handoffs, usage
    debug = "debug"  # full traces, payloads, raw events


class ApprovalPolicy(StrEnum):
    auto = "auto"  # approve mutating tools, still gate destructive ones
    ask = "ask"  # prompt the user for mutating + destructive tools
    allowlist = "allowlist"  # approve only tools explicitly listed
    deny = "deny"  # deny every mutating/destructive tool


class ThinkingLevel(StrEnum):
    """Model reasoning effort; mapped per provider by the runner.

    off    — no thinking settings sent
    low    — smallest thinking budget
    medium — provider default budget
    high   — largest budget (reasoning-heavy work)
    """

    off = "off"
    low = "low"
    medium = "medium"
    high = "high"


class ApprovalConfig(BaseModel):
    policy: ApprovalPolicy = ApprovalPolicy.ask
    allowlist: set[str] = Field(default_factory=set)


class BudgetConfig(BaseModel):
    """Optional per-run ceilings; ``None`` means unlimited for that axis."""

    max_requests: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_cost_usd: float | None = None


class RoutingConfig(BaseModel):
    """Task-type -> model routing with explicit user overrides."""

    default_model: str = "openai:gpt-4o-mini"
    task_models: dict[TaskType, str] = Field(default_factory=dict)
    fallbacks: list[str] = Field(default_factory=list)
    auto_route: bool = True  # honor task_models when no explicit override given


class ContextConfig(BaseModel):
    """Context-minimization knobs (see context.assembler)."""

    max_history_messages: int = 40  # hard cap on raw history sent to a model
    summarize_after: int = 24  # summarize history beyond this many messages
    max_repo_index_files: int = 500  # files in the index snippet sent for scoping
    index_cache_ttl_hours: float = 24.0  # persisted repo-index freshness window
    max_file_read_chars: int = 40_000  # per-read cap before truncation


class SkillsConfig(BaseModel):
    """Skill/plugin discovery knobs (see skills and plugins packages)."""

    enabled: bool = True
    extra_dirs: list[str] = Field(default_factory=list)  # additional skill dirs


class HarnessConfig(BaseModel):
    version: int = 1
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    max_concurrency: int = 4
    agent_timeout_seconds: float | None = 600.0
    tool_timeout_seconds: float | None = 60.0
    tool_max_retries: int | None = 3
    verbosity: Verbosity = Verbosity.compact
    thinking: ThinkingLevel = ThinkingLevel.off

    @field_validator("max_concurrency")
    @classmethod
    def _positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_concurrency must be >= 1")
        return value

    @field_validator("agent_timeout_seconds", "tool_timeout_seconds", mode="before")
    @classmethod
    def _timeout_or_off(cls, value: Any) -> float | None:
        return parse_timeout(value)


def _read_table(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` into ``base`` (override wins)."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _config_table(repo_root: Path, config_path: Path | None) -> dict[str, Any]:
    """Effective config table: user-level file merged under repo-level file.

    Precedence: defaults < ~/.om-harness/config/config.toml < repo file.
    An explicit ``config_path`` skips discovery entirely (tests, tooling).
    """
    if config_path is not None:
        return _read_table(config_path)
    user_table = _read_table(user_config_file())
    repo_file = repo_root / CONFIG_FILENAME
    repo_table: dict[str, Any] = {}
    if repo_file.exists():
        repo_table = _read_table(repo_file)
    else:
        pyproject = repo_root / PYPROJECT_FILENAME
        if pyproject.exists():
            repo_table = _read_table(pyproject).get("tool", {}).get(PYPROJECT_TABLE, {})
    return _deep_merge(user_table, repo_table)


def _apply_env(config: HarnessConfig, env: Mapping[str, str]) -> HarnessConfig:
    routing_updates: dict[str, Any] = {}
    updates: dict[str, Any] = {}

    model = env.get(f"{ENV_PREFIX}DEFAULT_MODEL")
    if model:
        routing_updates["default_model"] = model
    task_models_env = env.get(f"{ENV_PREFIX}TASK_MODELS")
    if task_models_env:
        parsed: dict[str, str] = {}
        for pair in task_models_env.split(","):
            task_type, _, model_str = pair.partition("=")
            if not model_str:
                raise ConfigError(
                    f"OM_HARNESS_TASK_MODELS entries must be task_type=model, got {pair!r}"
                )
            parsed[task_type.strip()] = model_str.strip()
        routing_updates["task_models"] = parsed
    if routing_updates:
        # model_validate (not model_copy) so string enum values/keys coerce.
        data = config.routing.model_dump()
        data.update(routing_updates)
        updates["routing"] = RoutingConfig.model_validate(data)

    policy = env.get(f"{ENV_PREFIX}APPROVAL_POLICY")
    if policy:
        updates["approval"] = ApprovalConfig.model_validate(
            {**config.approval.model_dump(), "policy": policy}
        )

    simple = {
        "MAX_CONCURRENCY": ("max_concurrency", int),
        "AGENT_TIMEOUT_SECONDS": ("agent_timeout_seconds", parse_timeout),
        "TOOL_TIMEOUT_SECONDS": ("tool_timeout_seconds", parse_timeout),
        "VERBOSITY": ("verbosity", Verbosity),
        "MAX_REQUESTS": None,
    }
    for env_name, spec in simple.items():
        raw = env.get(f"{ENV_PREFIX}{env_name}")
        if not raw:
            continue
        if spec is None:  # budget axis
            updates["budget"] = config.budget.model_copy(update={"max_requests": int(raw)})
        else:
            attr, caster = spec
            try:
                updates[attr] = caster(raw)
            except (ValueError, TypeError) as exc:
                raise ConfigError(f"invalid {ENV_PREFIX}{env_name}={raw!r}") from exc

    if not updates:
        return config
    return config.model_copy(update=updates)


def load_config(
    repo_root: Path,
    env: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> HarnessConfig:
    """Load, validate, and merge harness configuration.

    Raises ``ConfigError`` for malformed files or unknown enum values so
    misconfiguration fails loudly at startup, not mid-run.

    Precedence: defaults < ~/.om-harness/config/config.toml < repo-level
    file < OM_HARNESS_* environment variables.
    """
    env = env if env is not None else os.environ
    table = _config_table(repo_root, config_path)
    try:
        config = HarnessConfig.model_validate(table)
    except Exception as exc:
        raise ConfigError(str(exc)) from exc
    return _apply_env(config, env)
