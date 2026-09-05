"""Contract tests for the provider layer: registry, availability, routing,
and the mock model path (real pydantic_ai, no network).

Provider keys in these tests are obviously-fake placeholder strings; no test
ever contacts a real API (that lives in tests/integration, gated on env).
"""

from __future__ import annotations

import pytest
from pydantic_ai import Agent

from om_harness.config.loader import RoutingConfig
from om_harness.models.task import TaskType
from om_harness.providers.mock import make_scripted_model
from om_harness.providers.registry import ProviderRegistry
from om_harness.providers.router import ModelRouter

FAKE_OPENAI_KEY = "test-fake-openai-key"
FAKE_ANTHROPIC_KEY = "test-fake-anthropic-key"


# -- registry -----------------------------------------------------------------


def test_registry_availability_follows_env_keys() -> None:
    registry = ProviderRegistry(env={"OPENAI_API_KEY": FAKE_OPENAI_KEY})
    assert registry.is_available("openai")
    assert not registry.is_available("anthropic")
    assert registry.is_available("mock")  # mock always available


def test_registry_lists_known_providers() -> None:
    registry = ProviderRegistry(env={})
    infos = registry.available_providers()
    names = {info.name for info in infos}
    assert {"openai", "anthropic", "google", "mock"} <= names


def test_registry_rejects_unknown_prefix() -> None:
    registry = ProviderRegistry(env={})
    with pytest.raises(Exception, match="unknown provider"):
        registry.resolve_model("mystery:model-x")


def test_registry_parses_model_strings() -> None:
    registry = ProviderRegistry(env={})
    spec = registry.resolve_model("openai:gpt-4o-mini")
    assert spec.provider == "openai"
    assert spec.model_name == "gpt-4o-mini"


def test_registry_creates_mock_model() -> None:
    registry = ProviderRegistry(env={})
    model = registry.make_model("mock:test")
    assert model is not None


def test_registry_returns_none_for_unavailable_provider() -> None:
    registry = ProviderRegistry(env={})
    assert registry.make_model("anthropic:claude-sonnet-4-5") is None


def test_registry_creates_real_model_without_network() -> None:
    """Constructing model objects must not require network access."""
    registry = ProviderRegistry(env={"OPENAI_API_KEY": FAKE_OPENAI_KEY})
    model = registry.make_model("openai:gpt-4o-mini")
    assert model is not None


# -- router -------------------------------------------------------------------


def _router(config: RoutingConfig | None = None, env: dict[str, str] | None = None) -> ModelRouter:
    return ModelRouter(config or RoutingConfig(), ProviderRegistry(env or {}))


def test_explicit_override_wins() -> None:
    router = _router(env={"OPENAI_API_KEY": FAKE_OPENAI_KEY})
    assert router.select(TaskType.explore, override="openai:gpt-4o") == "openai:gpt-4o"


def test_configured_task_model_used_for_that_type_only() -> None:
    config = RoutingConfig(default_model="openai:gpt-4o")
    router = ModelRouter(config, ProviderRegistry(env={"OPENAI_API_KEY": FAKE_OPENAI_KEY}))
    assert router.select(TaskType.explore, override="openai:gpt-4o-mini") == "openai:gpt-4o-mini"
    assert router.select(TaskType.implement) == "openai:gpt-4o"  # default honored


def test_selected_default_model_wins_over_auto_route() -> None:
    """The regression: /model selections must reach the runner even when
    auto_route is enabled (it is on by default)."""
    config = RoutingConfig(default_model="openai:gpt-4o")
    router = ModelRouter(config, ProviderRegistry(env={"OPENAI_API_KEY": FAKE_OPENAI_KEY}))
    for task_type in TaskType:
        assert router.select(task_type) == "openai:gpt-4o"


def test_selected_custom_provider_model_wins() -> None:
    """A models.json provider selected as default must be used directly."""
    from om_harness.providers.models_json import ModelsJsonConfig

    custom = ModelsJsonConfig.model_validate(
        {
            "providers": {
                "lm-studio": {
                    "baseUrl": "http://127.0.0.1:8080/v1",
                    "api": "openai-completions",
                    "allowLocal": True,
                    "models": [{"id": "ornith-1.0-9b"}],
                }
            }
        }
    )
    config = RoutingConfig(default_model="lm-studio:ornith-1.0-9b")
    router = ModelRouter(config, ProviderRegistry(env={}, custom=custom))
    for task_type in TaskType:
        assert router.select(task_type) == "lm-studio:ornith-1.0-9b"


def test_unavailable_default_falls_back_to_auto_route() -> None:
    """Default whose provider has no key still falls back automatically."""
    config = RoutingConfig(default_model="openai:gpt-4o")
    router = ModelRouter(config, ProviderRegistry(env={"ANTHROPIC_API_KEY": FAKE_ANTHROPIC_KEY}))
    model = router.select(TaskType.implement)
    assert model.startswith("anthropic:")


def test_auto_route_prefers_available_providers() -> None:
    router = _router(env={"ANTHROPIC_API_KEY": FAKE_ANTHROPIC_KEY})
    model = router.select(TaskType.implement)
    assert model.startswith("anthropic:")


def test_router_falls_back_to_default_when_no_keys() -> None:
    router = _router()
    assert router.select(TaskType.general) == "mock:echo"


def test_fallback_chain_appends_configured_fallbacks() -> None:
    config = RoutingConfig(
        default_model="openai:gpt-4o-mini", fallbacks=["anthropic:claude-sonnet-4-5"]
    )
    router = ModelRouter(config, ProviderRegistry(env={}))
    assert router.fallback_chain("openai:gpt-4o-mini") == [
        "openai:gpt-4o-mini",
        "anthropic:claude-sonnet-4-5",
    ]


# -- mock model (real pydantic_ai agent, no network) ---------------------------


async def test_scripted_mock_model_drives_an_agent() -> None:
    from pydantic_ai.messages import ModelResponse, TextPart

    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        return ModelResponse(parts=[TextPart(content="mock says: 2 + 2 = 4")])

    model = make_scripted_model(respond)
    agent = Agent(model)
    result = await agent.run("what is 2 + 2?")
    assert result.output == "mock says: 2 + 2 = 4"


async def test_mock_model_receives_message_history() -> None:
    from pydantic_ai.messages import ModelResponse, TextPart

    seen: list[int] = []

    async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
        seen.append(len(messages))
        return ModelResponse(parts=[TextPart(content="ok")])

    model = make_scripted_model(respond)
    agent = Agent(model)
    first = await agent.run("one")
    await agent.run("two", message_history=first.all_messages())
    assert seen == [1, 3]  # second call sees prior turn
