"""Provider registry: model-string resolution and PydanticAI model factory.

``make_model`` is the only place that imports provider-specific PydanticAI
classes. Construction must never require network access; requests happen
later, inside ``agent.run``. Unavailable providers return ``None`` so callers
can degrade gracefully (e.g. route to the mock provider or report in doctor).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from om_harness.providers.base import BY_NAME, PROVIDERS, ModelSpec, ProviderInfo


class ProviderError(Exception):
    """Raised for unknown providers or malformed model strings."""


class ProviderRegistry:
    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        import os

        self._env: Mapping[str, str] = env if env is not None else os.environ

    # -- availability --------------------------------------------------------

    def is_available(self, provider_name: str) -> bool:
        spec = BY_NAME.get(provider_name)
        if spec is None:
            return False
        if spec.name == "mock":
            return True
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

    def first_available(self) -> str:
        """First real provider with a key, else the mock provider."""
        for spec in PROVIDERS:
            if spec.name != "mock" and self.is_available(spec.name):
                return spec.name
        return "mock"

    # -- model strings -------------------------------------------------------

    def resolve_model(self, model_str: str) -> ModelSpec:
        for spec in PROVIDERS:
            if model_str.startswith(spec.prefix):
                model_name = model_str[len(spec.prefix) :]
                if not model_name:
                    raise ProviderError(f"malformed model string {model_str!r}")
                return ModelSpec(provider=spec.name, model_name=model_name)
        raise ProviderError(
            f"unknown provider in {model_str!r}; expected one of: "
            + ", ".join(spec.prefix for spec in PROVIDERS)
        )

    def default_model(self) -> str:
        spec = BY_NAME[self.first_available()]
        return spec.default_model

    # -- model factory -------------------------------------------------------

    def _api_key(self, provider_name: str) -> str | None:
        spec = BY_NAME[provider_name]
        for key in spec.env_keys:
            if self._env.get(key):
                return self._env[key]
        return None

    def make_model(self, model_str: str) -> Any | None:
        """Build a PydanticAI model instance, or None if unavailable.

        Imports are local so the core package works without provider SDK
        extras installed. The API key is passed explicitly from the registry's
        environment mapping, so construction works even before the process
        environment is fully populated and never requires network access.
        """
        parsed = self.resolve_model(model_str)
        provider = BY_NAME[parsed.provider]

        if provider.name == "mock":
            from om_harness.providers.mock import make_echo_model

            return make_echo_model()

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
