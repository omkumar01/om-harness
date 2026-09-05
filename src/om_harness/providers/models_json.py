"""Custom model providers from a local ``models.json`` file.

This feature lets users register arbitrary OpenAI-compatible providers
(LM Studio, Ollama-style gateways, NVIDIA NIM, private inference endpoints)
without code changes::

    {
      "providers": {
        "lm-studio": {
          "baseUrl": "http://127.0.0.1:8080/v1",
          "api": "openai-completions",
          "allowLocal": true,
          "models": [{"id": "qwen3-32b", "contextWindow": 256000}]
        }
      }
    }

Model strings take the form ``<provider>:<model-id>`` (e.g.
``lm-studio:qwen3-32b``) and flow through the same registry, router, and CLI
surfaces as the built-in providers.

Security policy:
- URLs must be http/https. Loopback, private, link-local, and reserved
  hosts are rejected **unless** the provider sets ``"allowLocal": true`` —
  an explicit opt-in for local inference servers written by the user who
  also owns the machine. The validation runs again before any client is
  constructed.
- API keys should reference environment variables via ``"apiKeyEnv"``.
  Inline ``"apiKey"`` values are accepted (local gateways often require a
  dummy key) and are automatically registered with the secret redactor so
  they never reach events, logs, or checkpoints.
"""

from __future__ import annotations

import ipaddress
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import AliasChoices, BaseModel, Field, model_validator

from om_harness.config.paths import user_models_json

MODELS_JSON_FILENAME = "models.json"
ENV_MODELS_JSON = "OM_HARNESS_MODELS_JSON"

SUPPORTED_APIS = ("openai-completions", "openai-responses")


class ModelsJsonError(Exception):
    """Raised for malformed, unsafe, or inconsistent models.json content."""


class ModelCost(BaseModel):
    """Relative token costs; informational (all zeros for local servers)."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = Field(default=0.0, validation_alias=AliasChoices("cacheRead", "cache_read"))
    cache_write: float = Field(
        default=0.0, validation_alias=AliasChoices("cacheWrite", "cache_write")
    )


class CustomModelSpec(BaseModel):
    """One model offered by a custom provider."""

    id: str
    name: str | None = None
    url: str | None = None  # per-model base-url override
    reasoning: bool = False
    tool_calling: bool = Field(
        default=False, validation_alias=AliasChoices("toolCalling", "tool_calling")
    )
    vision: bool = False
    input: list[str] = Field(default_factory=lambda: ["text"])
    context_window: int | None = Field(
        default=None, validation_alias=AliasChoices("contextWindow", "context_window")
    )
    max_tokens: int | None = Field(
        default=None, validation_alias=AliasChoices("maxTokens", "max_tokens")
    )
    max_input_tokens: int | None = Field(
        default=None, validation_alias=AliasChoices("maxInputTokens", "max_input_tokens")
    )
    max_output_tokens: int | None = Field(
        default=None, validation_alias=AliasChoices("maxOutputTokens", "max_output_tokens")
    )
    cost: ModelCost = Field(default_factory=ModelCost)


class CustomProviderSpec(BaseModel):
    """One OpenAI-compatible endpoint plus its models."""

    base_url: str = Field(validation_alias=AliasChoices("baseUrl", "base_url"))
    api: str = "openai-completions"
    api_key: str | None = Field(default=None, validation_alias=AliasChoices("apiKey", "api_key"))
    api_key_env: str | None = Field(
        default=None, validation_alias=AliasChoices("apiKeyEnv", "api_key_env")
    )
    allow_local: bool = Field(
        default=False, validation_alias=AliasChoices("allowLocal", "allow_local")
    )
    models: list[CustomModelSpec] = Field(min_length=1)

    def resolved_api_key(self, env: dict[str, str]) -> str | None:
        """Inline key first, then the referenced environment variable."""
        if self.api_key:
            return self.api_key
        if self.api_key_env and env.get(self.api_key_env):
            return env[self.api_key_env]
        return None

    def is_available(self, env: dict[str, str]) -> bool:
        """Local gateways need no key; remote ones need inline or env key."""
        if self.api_key or self.allow_local:
            return True
        return bool(self.api_key_env and env.get(self.api_key_env))

    def base_url_for(self, model: CustomModelSpec) -> str:
        return model.url or self.base_url


class ModelsJsonConfig(BaseModel):
    """Top-level ``models.json`` document."""

    providers: dict[str, CustomProviderSpec]

    @model_validator(mode="after")
    def _validate(self) -> ModelsJsonConfig:
        return self.validate_policy()

    def validate_policy(self) -> ModelsJsonConfig:
        """URL safety, name collisions, API kinds, duplicate model ids."""
        from om_harness.providers.base import PROVIDERS

        builtin_names = {spec.name for spec in PROVIDERS}
        for name, provider in self.providers.items():
            if name in builtin_names:
                raise ModelsJsonError(f"provider name {name!r} is reserved by built-in providers")
            if provider.api not in SUPPORTED_APIS:
                raise ModelsJsonError(
                    f"provider {name!r}: unsupported api {provider.api!r}; "
                    f"supported: {', '.join(SUPPORTED_APIS)}"
                )
            try:
                validate_provider_url(provider.base_url, allow_local=provider.allow_local)
            except ModelsJsonError as exc:
                raise ModelsJsonError(f"provider {name!r}: {exc}") from exc
            seen: set[str] = set()
            for model in provider.models:
                if model.id in seen:
                    raise ModelsJsonError(f"provider {name!r}: duplicate model id {model.id!r}")
                seen.add(model.id)
                if model.url:
                    try:
                        validate_provider_url(model.url, allow_local=provider.allow_local)
                    except ModelsJsonError as exc:
                        raise ModelsJsonError(
                            f"provider {name!r} model {model.id!r}: {exc}"
                        ) from exc
        return self

    def inline_api_keys(self) -> list[str]:
        """Inline keys, for registration with the secret redactor."""
        return [p.api_key for p in self.providers.values() if p.api_key]

    def get_model(self, provider_name: str, model_id: str) -> CustomModelSpec:
        try:
            provider = self.providers[provider_name]
        except KeyError:
            raise ModelsJsonError(
                f"unknown custom provider {provider_name!r}; "
                f"configured: {', '.join(sorted(self.providers)) or 'none'}"
            ) from None
        for model in provider.models:
            if model.id == model_id:
                return model
        raise ModelsJsonError(
            f"unknown model {model_id!r} for provider {provider_name!r}; "
            f"configured: {', '.join(m.id for m in provider.models)}"
        )


def _is_local_or_private_host(host: str) -> bool:
    """True for loopback, private, link-local, reserved, or local-suffix hosts."""
    lowered = host.lower().rstrip(".")
    if lowered in {"localhost", "local", "internal"} or lowered.endswith(
        (".localhost", ".local", ".internal")
    ):
        return True
    try:
        ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_provider_url(url: str, *, allow_local: bool = False) -> str:
    """Enforce the URL safety policy; returns the URL when acceptable.

    - scheme must be http/https,
    - loopback/private/reserved hosts are rejected unless ``allow_local``
      (explicit opt-in for local inference servers).
    """
    if not url or not url.strip():
        raise ModelsJsonError("empty URL")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ModelsJsonError(f"URL scheme must be http or https, got {parsed.scheme!r} in {url!r}")
    host = parsed.hostname
    if not host:
        raise ModelsJsonError(f"URL has no host: {url!r}")
    if allow_local and _is_local_or_private_host(host):
        # Explicitly opted in: accept, but only for genuinely local/private
        # hosts — a public host doesn't need the opt-in.
        return url
    if _is_local_or_private_host(host):
        raise ModelsJsonError(
            f'refusing local or private endpoint {host!r}; set "allowLocal": true '
            "on the provider to explicitly opt in (for local inference servers)"
        )
    return url


def load_models_json(
    repo_root: Path,
    env: Mapping[str, str] | None = None,
    config_path: Path | None = None,
) -> ModelsJsonConfig | None:
    """Discover, parse, merge, and validate models.json; None if absent.

    Sources, merged in order (later sources override same-named providers):
    ``~/.om-harness/config/models.json`` (user-level, the normal home for a
    delivered install), ``<repo>/models.json`` (repo-specific additions), and
    ``OM_HARNESS_MODELS_JSON`` (explicit override). An explicit
    ``config_path`` skips discovery entirely (tests, tooling).
    """
    env_mapping: Mapping[str, str] = env if env is not None else os.environ
    if config_path is not None:
        sources: list[Path] = [config_path]
    else:
        # More specific sources come later and win: user-level defaults,
        # then repo-specific providers, then an explicit env override.
        sources = [user_models_json()]
        sources.append(Path(repo_root) / MODELS_JSON_FILENAME)
        env_path = env_mapping.get(ENV_MODELS_JSON)
        if env_path:
            sources.append(Path(env_path))

    merged_providers: dict[str, Any] = {}
    found_any = False
    for source in sources:
        if not source.is_file():
            continue
        found_any = True
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ModelsJsonError(f"failed to parse {source}: {exc}") from exc
        if not isinstance(data, dict):
            raise ModelsJsonError(f"invalid models.json at {source}: expected an object")
        merged_providers.update(data.get("providers") or {})
    if not found_any:
        return None
    if not merged_providers:
        return None
    try:
        return ModelsJsonConfig.model_validate({"providers": merged_providers})
    except ModelsJsonError:
        raise
    except Exception as exc:
        raise ModelsJsonError(f"invalid models.json content: {exc}") from exc
