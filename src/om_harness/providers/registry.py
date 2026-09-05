"""Provider registry: model-string resolution and PydanticAI model factory.

``make_model`` is the only place that imports provider-specific PydanticAI
classes. Construction must never require network access; requests happen
later, inside ``agent.run``. Unavailable providers return ``None`` so callers
can degrade gracefully (e.g. route to the mock provider or report in doctor).

Custom OpenAI-compatible providers from a ``models.json`` file (local
gateways like LM Studio, or remote endpoints) are registered through the
same surface: see ``providers/models_json.py``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from om_harness.providers.base import (
    BY_NAME,
    MOCK_PREFIX,
    PROVIDERS,
    ModelSpec,
    ProviderInfo,
)
from om_harness.providers.mock import make_echo_model
from om_harness.providers.models_json import ModelsJsonConfig, validate_provider_url

# Placeholder key for local gateways that need a non-empty Authorization
# header but no real credential (e.g. LM Studio). Not a secret.
LOCAL_KEY_PLACEHOLDER = "om-harness-local"


class ProviderError(Exception):
    """Raised for unknown providers or malformed model strings."""


def _local_http_client() -> Any:
    """An HTTP client that bypasses system proxies (for local endpoints).

    A configured HTTP(S)_PROXY would otherwise swallow 127.0.0.1 traffic
    and surface as a bogus "Connection error". The openai SDK vendors its
    own httpx (``httpx2``); fall back to plain httpx on older versions.
    """
    try:
        import httpx2 as httpx_mod
    except ImportError:  # pragma: no cover - depends on SDK version
        import httpx as httpx_mod  # type: ignore[no-redef]
    return httpx_mod.AsyncClient(trust_env=False)


class ProviderRegistry:
    def __init__(
        self,
        env: Mapping[str, str] | None = None,
        custom: ModelsJsonConfig | None = None,
    ) -> None:
        self._env: Mapping[str, str] = env if env is not None else os.environ
        self._custom = custom

    # -- availability --------------------------------------------------------

    def is_available(self, provider_name: str) -> bool:
        # The offline echo model is only usable via explicit configuration.
        if provider_name == "mock":
            return True
        if self._custom is not None and provider_name in self._custom.providers:
            return self._custom.providers[provider_name].is_available(dict(self._env))
        spec = BY_NAME.get(provider_name)
        if spec is None:
            return False
        return any(self._env.get(key) for key in spec.env_keys)

    def available_providers(self) -> list[ProviderInfo]:
        return [
            ProviderInfo(
                name=spec.name,
                prefix=spec.prefix,
                available=self.is_available(spec.name),
                default_model=spec.default_model,
                strong_model=spec.strong_model,
            )
            for spec in PROVIDERS
        ]

    def custom_provider_summaries(self) -> list[dict[str, Any]]:
        """JSON-friendly description of configured custom providers."""
        if self._custom is None:
            return []
        summaries: list[dict[str, Any]] = []
        for name, provider in sorted(self._custom.providers.items()):
            summaries.append(
                {
                    "name": name,
                    "prefix": f"{name}:",
                    "base_url": provider.base_url,
                    "api": provider.api,
                    "available": self.is_available(name),
                    "allow_local": provider.allow_local,
                    "key_source": (
                        "inline" if provider.api_key else (provider.api_key_env or "none")
                    ),
                    "models": [
                        {
                            "id": m.id,
                            "reasoning": m.reasoning,
                            "tool_calling": m.tool_calling,
                            "vision": m.vision,
                            "context_window": m.context_window,
                        }
                        for m in provider.models
                    ],
                }
            )
        return summaries

    def first_available(self) -> str | None:
        """First real provider with a key, or None when nothing is configured.

        The offline echo model is deliberately excluded: it is never
        auto-selected.
        """
        for spec in PROVIDERS:
            if self.is_available(spec.name):
                return spec.name
        return None

    @property
    def custom_provider_names(self) -> list[str]:
        """Names of providers registered via models.json (sorted)."""
        return sorted(self._custom.providers) if self._custom is not None else []

    # -- model strings -------------------------------------------------------

    def resolve_model(self, model_str: str) -> ModelSpec:
        # Offline echo model: explicit selection only (never auto-routed).
        if model_str.startswith(MOCK_PREFIX):
            model_name = model_str[len(MOCK_PREFIX) :]
            if not model_name:
                raise ProviderError(f"malformed model string {model_str!r}")
            return ModelSpec(provider="mock", model_name=model_name)

        for spec in PROVIDERS:
            if model_str.startswith(spec.prefix):
                model_name = model_str[len(spec.prefix) :]
                if not model_name:
                    raise ProviderError(f"malformed model string {model_str!r}")
                return ModelSpec(provider=spec.name, model_name=model_name)

        if self._custom is not None:
            provider_name, sep, model_id = model_str.partition(":")
            if sep and provider_name in self._custom.providers:
                try:
                    self._custom.get_model(provider_name, model_id)
                except Exception as exc:
                    raise ProviderError(str(exc)) from exc
                return ModelSpec(provider=provider_name, model_name=model_id)
            if provider_name in self._custom.providers:
                raise ProviderError(f"malformed model string {model_str!r}")

        raise ProviderError(
            f"unknown provider in {model_str!r}; expected one of: "
            + ", ".join(spec.prefix for spec in PROVIDERS)
            + (", or a provider from models.json" if self._custom is not None else "")
        )

    def default_model(self) -> str:
        provider = self.first_available()
        if provider is None:
            raise ProviderError(
                "no provider available — set an API key or add providers to models.json"
            )
        return BY_NAME[provider].default_model

    # -- model factory -------------------------------------------------------

    def endpoint_for(self, model_str: str) -> str | None:
        """The HTTP endpoint a model string would talk to (for diagnostics)."""
        try:
            parsed = self.resolve_model(model_str)
            if self._custom is not None and parsed.provider in self._custom.providers:
                provider = self._custom.providers[parsed.provider]
                model = self._custom.get_model(parsed.provider, parsed.model_name)
                return provider.base_url_for(model)
            if parsed.provider == "openai":
                return "https://api.openai.com/v1"
        except Exception:
            return None
        return None

    def _api_key(self, provider_name: str) -> str | None:
        spec = BY_NAME[provider_name]
        for key in spec.env_keys:
            if self._env.get(key):
                return self._env[key]
        return None

    def _make_custom_model(self, parsed: ModelSpec) -> Any | None:
        """Build the client for a models.json provider, or None if unavailable."""
        if self._custom is None:
            return None
        try:
            provider = self._custom.providers[parsed.provider]
            model = self._custom.get_model(parsed.provider, parsed.model_name)
        except KeyError:
            return None
        if not self.is_available(parsed.provider):
            return None

        # Re-validate the endpoint at request-config time (defense in depth;
        # the same policy already ran when models.json was loaded).
        try:
            base_url = validate_provider_url(
                provider.base_url_for(model), allow_local=provider.allow_local
            )
        except Exception as exc:
            raise ProviderError(str(exc)) from exc

        api_key = provider.resolved_api_key(dict(self._env)) or LOCAL_KEY_PLACEHOLDER
        model_name = parsed.model_name

        if provider.api == "openai-completions":
            from openai import AsyncOpenAI
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            if provider.allow_local:
                # Local endpoints must bypass system proxies: a configured
                # HTTP(S)_PROXY would otherwise swallow 127.0.0.1 traffic
                # and surface as a bogus "Connection error". The openai SDK
                # vendors its own httpx (httpx2); fall back to plain httpx.
                client = AsyncOpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    http_client=_local_http_client(),
                )
                return OpenAIChatModel(model_name, provider=OpenAIProvider(openai_client=client))

            return OpenAIChatModel(
                model_name,
                provider=OpenAIProvider(base_url=base_url, api_key=api_key),
            )
        if provider.api == "openai-responses":
            from pydantic_ai.models.openai import OpenAIResponsesModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIResponsesModel(
                model_name,
                provider=OpenAIProvider(base_url=base_url, api_key=api_key),
            )
        # validate_policy() already rejects unsupported kinds; defensive only.
        raise ProviderError(  # pragma: no cover
            f"unsupported api {provider.api!r} for provider {parsed.provider!r}"
        )

    def make_model(self, model_str: str) -> Any | None:
        """Build a PydanticAI model instance, or None if unavailable.

        Imports are local so the core package works without provider SDK
        extras installed. The API key is passed explicitly from the registry's
        environment mapping, so construction works even before the process
        environment is fully populated and never requires network access.
        """
        parsed = self.resolve_model(model_str)

        if self._custom is not None and parsed.provider in self._custom.providers:
            return self._make_custom_model(parsed)

        if parsed.provider == "mock":  # explicit selection only
            return make_echo_model()

        provider = BY_NAME[parsed.provider]

        if not self.is_available(provider.name):
            return None

        if provider.name == "openai":
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIChatModel(
                parsed.model_name,
                provider=OpenAIProvider(api_key=self._api_key("openai")),
            )

        if provider.name == "anthropic":
            from pydantic_ai.models.anthropic import AnthropicModel
            from pydantic_ai.providers.anthropic import AnthropicProvider

            return AnthropicModel(
                parsed.model_name,
                provider=AnthropicProvider(api_key=self._api_key("anthropic")),
            )

        if provider.name == "google":
            from pydantic_ai.models.google import GoogleModel
            from pydantic_ai.providers.google import GoogleProvider

            return GoogleModel(
                parsed.model_name,
                provider=GoogleProvider(api_key=self._api_key("google")),
            )

        raise ProviderError(f"no factory for provider {provider.name!r}")  # pragma: no cover
