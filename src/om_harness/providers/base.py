"""Provider abstraction built on PydanticAI's already-unified model interface.

om-harness adds: availability detection (env keys), model-string registry,
task-type routing, fallback chains, and a mock model for tests/demos.
Provider-agnostic code depends only on ``ProviderRegistry``/``ModelRouter``.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


class ProviderInfo(BaseModel):
    """Runtime view of a provider: availability and its known models."""

    name: str
    prefix: str
    available: bool
    default_model: str
    strong_model: str


@dataclass(frozen=True)
class ModelSpec:
    """A parsed ``provider:model`` string."""

    provider: str
    model_name: str

    @property
    def full(self) -> str:
        return f"{self.provider}:{self.model_name}"


@dataclass(frozen=True)
class ProviderSpec:
    """Static description of a supported provider."""

    name: str
    prefix: str  # model-string prefix, e.g. "openai:"
    env_keys: tuple[str, ...]  # any of these makes the provider available
    default_model: str
    # Stronger default used for implement/review tasks when available.
    strong_model: str


PROVIDERS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        name="openai",
        prefix="openai:",
        env_keys=("OPENAI_API_KEY",),
        default_model="openai:gpt-4o-mini",
        strong_model="openai:gpt-4o",
    ),
    ProviderSpec(
        name="anthropic",
        prefix="anthropic:",
        env_keys=("ANTHROPIC_API_KEY",),
        default_model="anthropic:claude-3-5-haiku-latest",
        strong_model="anthropic:claude-sonnet-4-5",
    ),
    ProviderSpec(
        name="google",
        prefix="google-gla:",
        env_keys=("GOOGLE_API_KEY", "GEMINI_API_KEY"),
        default_model="google-gla:gemini-2.0-flash",
        strong_model="google-gla:gemini-2.0-flash",
    ),
)

# The offline echo model is NOT a provider: it is never listed, never
# auto-routed, and never selected automatically. It only answers when a
# user explicitly configures ``mock:<name>`` as their model (offline demos,
# tests). See registry.make_model.
MOCK_PREFIX = "mock:"

BY_NAME = {spec.name: spec for spec in PROVIDERS}
