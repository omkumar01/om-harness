"""End-to-end test: om-harness against a real local OpenAI-compatible
gateway (in-process FastAPI server) registered via ``models.json``.

This exercises the full HTTP path — OpenAI client → local endpoint →
PydanticAI → TaskResult — with no external service and no credentials.
The local endpoint requires the ``allowLocal`` opt-in, exactly as a real
LM Studio setup would.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any

import pytest
import uvicorn

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from om_harness.harness import Harness  # noqa: E402
from om_harness.models.task import TaskStatus  # noqa: E402

MODEL_ID = "test-local-model"


def _gateway_app() -> FastAPI:
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def chat_completions(payload: dict[str, Any]) -> JSONResponse:
        return JSONResponse(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": payload.get("model", MODEL_ID),
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "gateway says: 2 + 2 = 4",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 8,
                    "total_tokens": 18,
                },
            }
        )

    return app


@pytest.fixture
def gateway_url() -> Any:
    """Start the OpenAI-compatible gateway on an ephemeral localhost port."""
    server = uvicorn.Server(
        uvicorn.Config(_gateway_app(), host="127.0.0.1", port=0, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "gateway did not start"
    host, port = server.servers[0].sockets[0].getsockname()[:2]
    yield f"http://{host}:{port}/v1"
    server.should_exit = True
    thread.join(timeout=5)


def test_run_against_local_gateway_via_models_json(tmp_path: Any, gateway_url: Any) -> None:
    import subprocess

    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "models.json").write_text(
        json.dumps(
            {
                "providers": {
                    "test-gateway": {
                        "baseUrl": gateway_url,
                        "api": "openai-completions",
                        "allowLocal": True,
                        "models": [{"id": MODEL_ID, "contextWindow": 8192}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    harness = Harness(repo_root=tmp_path, env={}, approval_policy="auto")
    assert harness.provider_registry.is_available("test-gateway")
    override = f"test-gateway:{MODEL_ID}"
    from om_harness.models.task import TaskType

    assert harness.router.select(TaskType.implement, override=override) == override

    outcome = asyncio.run(harness.run("what is 2 + 2?", model_override=override))

    assert outcome.status == "completed"
    assert outcome.results[0].status == TaskStatus.completed
    assert "2 + 2 = 4" in outcome.results[0].summary
    # Usage arrived from the gateway's usage block.
    assert outcome.usage.input_tokens >= 10
