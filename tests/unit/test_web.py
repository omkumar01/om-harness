"""Web reference client API tests (FastAPI TestClient, no network)."""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from om_harness.ui.web.server import create_app  # noqa: E402


@pytest.fixture
def repo(tmp_path: Any) -> Any:
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, capture_output=True, shell=False
    )
    (tmp_path / "hello.py").write_text("print('hello')\n")
    return tmp_path


@pytest.fixture
def client(repo: Any) -> Any:
    return TestClient(create_app(repo))


def test_index_serves_html(client: Any) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "om-harness" in res.text
    assert "<form" in res.text


def test_status_and_sessions(client: Any) -> None:
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/sessions").status_code == 200


def test_chat_roundtrip_uses_mock_provider(client: Any) -> None:
    res = client.post("/api/chat", json={"message": "what is in this repo?"})
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"]
    assert data["reply"]
    assert isinstance(data["events"], list)


def test_chat_continues_same_session(client: Any) -> None:
    first = client.post("/api/chat", json={"message": "one"}).json()
    second = client.post(
        "/api/chat", json={"message": "two", "session_id": first["session_id"]}
    ).json()
    assert second["session_id"] == first["session_id"]


def test_recent_events_endpoint(client: Any) -> None:
    created = client.post("/api/session").json()
    session_id = created["session_id"]
    client.post("/api/chat", json={"message": "hi", "session_id": session_id})
    res = client.get(f"/api/events/{session_id}/recent")
    assert res.status_code == 200
    types = [e["type"] for e in res.json()]
    assert "run.completed" in types
    assert all(isinstance(t, str) for t in types)
    # ensure it is valid JSON array with event payloads
    assert json.dumps(res.json()) is not None


def test_recent_events_unknown_session_404(client: Any) -> None:
    res = client.get("/api/events/nope/recent")
    assert res.status_code == 404
