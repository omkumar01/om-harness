"""Regression test: selecting a custom models.json model in the interactive
shell must be honored by the runner — the mock provider must never answer
for a model the user explicitly selected."""

from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from om_harness.config.user_settings import apply_config_update
from om_harness.harness import Harness
from om_harness.models.task import TaskType

SELECTED = "lm-studio:ornith-1.0-9b"


@pytest.fixture
def repo_with_custom_provider(tmp_path: Any) -> Any:
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "lm-studio": {
                        "baseUrl": "http://127.0.0.1:8080/v1",
                        "api": "openai-completions",
                        "allowLocal": True,
                        "models": [{"id": "ornith-1.0-9b", "contextWindow": 256000}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "app.py").write_text("x = 1\n")
    return tmp_path


def test_selected_model_reaches_the_runner(repo_with_custom_provider: Any) -> None:
    harness = Harness(repo_root=repo_with_custom_provider, env={})

    # User picks the custom model from the selector (same path as /model, ^M).
    apply_config_update(harness, "model", SELECTED)
    assert harness.router.select(TaskType.general) == SELECTED

    # Spy on which model string the runner asks the factory for.
    requested: list[str] = []

    def spy_factory(model_str: str) -> Any:
        requested.append(model_str)

        # Whatever is requested, answer with a distinguishable marker.
        async def respond(messages, agent_info) -> ModelResponse:  # type: ignore[no-untyped-def]
            return ModelResponse(parts=[TextPart(content=f"answered by {model_str}")])

        return FunctionModel(respond)

    harness.runner.model_factory = spy_factory
    outcome = asyncio.run(harness.run("say which model you are"))

    assert outcome.status == "completed"
    assert requested and requested[0] == SELECTED, (
        f"runner asked for {requested}, expected {SELECTED}"
    )
    assert f"answered by {SELECTED}" in outcome.results[0].summary
    assert "mock" not in requested
