"""User-level settings persistence: /config set writes to ~/.om-harness.

Values are validated and applied to the live HarnessConfig (mutated in place
so the router/assembler see changes immediately) and merged into
``~/.om-harness/config/config.toml`` for future sessions.
"""

from __future__ import annotations

import json
import tomllib
from typing import Any

from om_harness.config.loader import ApprovalPolicy, ThinkingLevel, Verbosity, parse_timeout
from om_harness.config.paths import user_config_file, user_models_json
from om_harness.models.task import TaskType
from om_harness.providers.registry import ProviderError


class SettingsError(ValueError):
    """Raised for unknown keys or invalid values in /config set."""


def apply_config_update(harness: Any, key: str, value: str) -> str:
    """Apply one ``/config set`` update to the live config and persist it.

    Returns a human-readable confirmation. Raises ``SettingsError`` for
    unknown keys or invalid values (nothing is persisted then).
    """
    config = harness.config
    updates: dict[str, Any]

    if key == "model":
        try:
            harness.provider_registry.resolve_model(value)  # validate early
        except ProviderError as exc:
            raise SettingsError(str(exc)) from exc
        config.routing.default_model = value
        updates = {"routing": {"default_model": value}}
        message = f"default model set to {value}"

    elif key == "approval":
        try:
            policy = ApprovalPolicy(value)
        except ValueError as exc:
            raise SettingsError(
                f"invalid approval policy {value!r}; "
                f"valid: {', '.join(p.value for p in ApprovalPolicy)}"
            ) from exc
        config.approval.policy = policy
        updates = {"approval": {"policy": policy.value}}
        message = f"approval policy set to {policy.value}"

    elif key == "verbosity":
        try:
            verbosity = Verbosity(value)
        except ValueError as exc:
            raise SettingsError(
                f"invalid verbosity {value!r}; valid: {', '.join(v.value for v in Verbosity)}"
            ) from exc
        config.verbosity = verbosity
        updates = {"verbosity": verbosity.value}
        message = f"verbosity set to {verbosity.value}"

    elif key == "thinking":
        try:
            level = ThinkingLevel(value)
        except ValueError as exc:
            raise SettingsError(
                f"invalid thinking level {value!r}; "
                f"valid: {', '.join(lv.value for lv in ThinkingLevel)}"
            ) from exc
        config.thinking = level
        updates = {"thinking": level.value}
        message = f"thinking level set to {level.value}"

    elif key == "max_concurrency":
        parsed = int(value)
        if parsed < 1:
            raise SettingsError("max_concurrency must be >= 1")
        config.max_concurrency = parsed
        updates = {"max_concurrency": parsed}
        message = f"max_concurrency set to {parsed}"

    elif key == "max_requests":
        parsed = int(value)
        if parsed < 1:
            raise SettingsError("max_requests must be >= 1")
        config.budget.max_requests = parsed
        updates = {"budget": {"max_requests": parsed}}
        message = f"budget.max_requests set to {parsed}"

    elif key in ("agent_timeout", "tool_timeout", "tool_max_retries"):
        if key == "tool_max_retries":
            try:
                parsed = int(value)
                if parsed < 0:
                    raise SettingsError("tool_max_retries must be >= 0")
            except ValueError:
                raise SettingsError("tool_max_retries must be an integer >= 0") from None
            config.tool_max_retries = parsed
            updates = {"tool_max_retries": parsed}
            message = f"tool_max_retries set to {parsed}"
        else:
            try:
                seconds = parse_timeout(value)
            except (ValueError, TypeError) as exc:
                raise SettingsError(
                    f"invalid {key} {value!r}; use seconds or 'off' to disable"
                ) from exc
            attr = f"{key}_seconds"
            setattr(config, attr, seconds)
            if key == "tool_timeout":
                # Tools share one live ToolContext; sync it so the change takes
                # effect without rebuilding the registry.
                tool_ctx = getattr(harness, "tool_ctx", None)
                if tool_ctx is not None:
                    tool_ctx.tool_timeout_seconds = seconds
            updates = {attr: "off" if seconds is None else seconds}
            message = (
                f"{key} timeout disabled (no timeout)"
                if seconds is None
                else f"{key} timeout set to {seconds:g}s"
            )

    elif key.startswith("task_model."):
        task_type_raw = key.partition(".")[2]
        try:
            task_type = TaskType(task_type_raw)
        except ValueError:
            valid = ", ".join(t.value for t in TaskType)
            raise SettingsError(f"unknown task type {task_type_raw!r}; valid: {valid}") from None
        try:
            harness.provider_registry.resolve_model(value)
        except ProviderError as exc:
            raise SettingsError(str(exc)) from exc
        config.routing.task_models[task_type] = value
        updates = {"routing": {"task_models": {task_type.value: value}}}
        message = f"task_model.{task_type.value} set to {value}"

    else:
        known = (
            "model, approval, verbosity, max_concurrency, max_requests, "
            "agent_timeout, tool_timeout, tool_max_retries, task_model.<type>"
        )
        raise SettingsError(f"unknown config key {key!r}; configurable: {known}")

    persist_updates(updates)
    return message


def load_user_overrides() -> dict[str, Any]:
    """Raw user-level config table (empty if absent)."""
    path = user_config_file()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f"invalid TOML in {path}: {exc}") from exc


def persist_updates(updates: dict[str, Any]) -> None:
    """Merge updates into the user config.toml (creates it if needed)."""
    current = load_user_overrides()
    merged = _deep_merge(current, updates)
    user_config_file().parent.mkdir(parents=True, exist_ok=True)
    user_config_file().write_text(_dump_toml(merged), encoding="utf-8")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise SettingsError(f"cannot serialize value {value!r} to TOML")


def _dump_toml(table: dict[str, Any], prefix: str = "") -> str:
    """Minimal TOML serializer: scalar keys first, then one nested table per line."""
    lines: list[str] = []
    scalars = {k: v for k, v in table.items() if not isinstance(v, dict)}
    subtables = {k: v for k, v in table.items() if isinstance(v, dict)}
    for key, value in scalars.items():
        lines.append(f"{key} = {_toml_value(value)}")
    for key, value in subtables.items():
        section = f"{prefix}{key}"
        lines.append("")
        lines.append(f"[{section}]")
        lines.append(_dump_toml(value, prefix=f"{section}."))
    return "\n".join(lines).strip() + "\n"


# -- model selector -----------------------------------------------------------


def apply_model(harness: Any, model_str: str) -> str:
    """Select a model from the selector dialog: validate, apply, persist."""
    return apply_config_update(harness, "model", model_str)


def available_model_strings(harness: Any) -> list[tuple[str, str]]:
    """All selectable model strings with a status label, for the selector UI."""
    registry = harness.provider_registry
    options: list[tuple[str, str]] = []
    for info in registry.available_providers():
        label = "available" if info.available else "no API key"
        options.append((info.default_model, f"{info.name} · {label}"))
        if info.strong_model != info.default_model:
            options.append((info.strong_model, f"{info.name} · strong · {label}"))
    for custom in registry.custom_provider_summaries():
        for model in custom["models"]:
            label = "available" if custom["available"] else "unavailable"
            options.append((f"{custom['name']}:{model['id']}", f"{custom['name']} · {label}"))
    return options


# -- provider setup (wizard) --------------------------------------------------


def add_custom_provider(
    *,
    name: str,
    base_url: str,
    api: str = "openai-completions",
    api_key_env: str | None = None,
    api_key: str | None = None,
    allow_local: bool = False,
    models: list[dict[str, Any]] | None = None,
) -> str:
    """Register a custom provider in ~/.om-harness/config/models.json.

    Validates the merged result (URL safety policy, name collisions, api
    kind) and raises ``SettingsError`` without writing anything on invalid
    input. Returns a confirmation message.
    """
    from om_harness.providers.models_json import ModelsJsonConfig, ModelsJsonError

    if not name or not name.replace("-", "").replace("_", "").isalnum():
        raise SettingsError(f"invalid provider name {name!r}: use letters, digits, '-' or '_'")
    model_list = models or [{"id": "default"}]
    doc: dict[str, Any] = {
        "providers": {
            name: {
                "baseUrl": base_url,
                "api": api,
                "allowLocal": allow_local,
                "models": model_list,
            }
        }
    }
    if api_key_env:
        doc["providers"][name]["apiKeyEnv"] = api_key_env
    if api_key:
        doc["providers"][name]["apiKey"] = api_key

    try:
        # Validate the provider standalone first for a focused error message.
        ModelsJsonConfig.model_validate(doc).validate_policy()
    except ModelsJsonError as exc:
        raise SettingsError(str(exc)) from exc

    # Merge into the existing user-level models.json.
    path = user_models_json()
    existing: dict[str, Any] = {"providers": {}}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            existing = {"providers": loaded.get("providers") or {}}
        except (json.JSONDecodeError, OSError) as exc:
            raise SettingsError(f"cannot read {path}: {exc}") from exc
    existing["providers"].update(doc["providers"])
    try:
        ModelsJsonConfig.model_validate(existing).validate_policy()
    except ModelsJsonError as exc:
        raise SettingsError(f"merge failed: {exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    ids = ", ".join(m["id"] for m in model_list)
    return f"provider {name!r} saved to {path} (models: {ids})"
