"""Optional integration tests: real provider round-trips.

These run ONLY when credentials are present, and are deselected by default
(`-m "not integration"` in addopts). Run explicitly with:

    uv run pytest -m integration
"""

from __future__ import annotations

import os

import pytest

from om_harness.providers.registry import ProviderRegistry

pytestmark = pytest.mark.integration

CASES = [
    ("openai", "OPENAI_API_KEY", "openai:gpt-4o-mini"),
    ("anthropic", "ANTHROPIC_API_KEY", "anthropic:claude-3-5-haiku-latest"),
    ("google", "GOOGLE_API_KEY", "google-gla:gemini-2.0-flash"),
]


def _available() -> list[tuple[str, str, str]]:
    registry = ProviderRegistry(env=os.environ)
    return [case for case in CASES if registry.is_available(case[0])]


@pytest.mark.parametrize("provider,env_key,model", CASES, ids=[c[0] for c in CASES])
def test_provider_roundtrip(provider: str, env_key: str, model: str) -> None:
    if (provider, env_key, model) not in _available():
        pytest.skip(f"no {env_key} configured")
    from pydantic_ai import Agent

    from om_harness.providers.registry import ProviderRegistry as R

    registry = R(env=os.environ)
    pydantic_model = registry.make_model(model)
    assert pydantic_model is not None
    agent = Agent(pydantic_model)
    result = agent.run_sync("Reply with exactly: OK")
    assert "OK" in result.output
