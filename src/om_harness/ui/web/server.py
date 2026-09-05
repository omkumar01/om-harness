"""Web reference client: FastAPI app exposing the same runtime as the CLI.

This module is intentionally small: it proves the runtime/UI separation by
serving chat and event-stream endpoints on top of the Harness facade with no
runtime logic of its own. The one-page HTML client in ``static/`` consumes
it. Requires the ``web`` extra: ``uv sync --extra web``.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from om_harness.config.loader import Verbosity
from om_harness.harness import Harness
from om_harness.ui.components import event_to_display

STATIC_DIR = Path(__file__).parent / "static"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    model: str | None = None


def create_app(repo_root: Path, harness: Harness | None = None) -> FastAPI:
    """Build the web app bound to one repository."""
    harness = harness or Harness(repo_root=repo_root, interactive=True)
    web_app = FastAPI(title="om-harness web", version="0.1.0")

    @web_app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_html = STATIC_DIR / "index.html"
        return HTMLResponse(index_html.read_text(encoding="utf-8"))

    @web_app.get("/api/status")
    async def status() -> dict[str, Any]:
        return harness.status()

    @web_app.get("/api/sessions")
    async def sessions() -> list[dict[str, Any]]:
        return [
            {
                "session_id": s.session_id,
                "status": s.status.value,
                "messages": len(s.messages),
                "runs": len(s.runs),
            }
            for s in harness.sessions.list_sessions()
        ]

    @web_app.post("/api/session")
    async def create_session() -> dict[str, str]:
        session = harness.sessions.create(repo_root=str(harness.repo_root))
        return {"session_id": session.session_id}

    @web_app.post("/api/chat")
    async def chat(request: ChatRequest) -> dict[str, Any]:
        session_id = request.session_id
        if session_id:
            harness.sessions.load(session_id)
        else:
            created = harness.sessions.create(repo_root=str(harness.repo_root))
            session_id = created.session_id
        offset = len(harness.bus.history)
        try:
            reply = await harness.chat_turn(
                session_id, request.message, model_override=request.model
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        events = []
        for e in harness.bus.history[offset:]:
            display = event_to_display(e, Verbosity.verbose)
            if display is not None:
                events.append(display.model_dump(mode="json"))
        return {"session_id": session_id, "reply": reply, "events": events}

    @web_app.get("/api/events/{session_id}")
    async def events(session_id: str) -> StreamingResponse:
        """Server-sent events stream for one session (live UI updates)."""

        async def stream() -> AsyncIterator[str]:
            reader = harness.bus.subscribe()
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(reader.get(), timeout=15.0)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    payload = json.dumps(
                        {
                            "type": event.type.value,
                            "ts": event.ts.isoformat(),
                            "data": event.data,
                        }
                    )
                    yield f"data: {payload}\n\n"
            except asyncio.CancelledError:  # client disconnected
                raise

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @web_app.get("/api/events/{session_id}/recent")
    async def recent_events(session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        try:
            harness.sessions.load(session_id)
        except Exception as exc:  # StoreError -> 404 for unknown sessions
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        history = [e for e in harness.bus.history if e.session_id == session_id]
        return [
            {"type": e.type.value, "ts": e.ts.isoformat(), "data": e.data} for e in history[-limit:]
        ]

    return web_app


def main() -> None:  # pragma: no cover - manual launch helper
    import uvicorn

    uvicorn.run(
        create_app(Path.cwd()),
        host="127.0.0.1",
        port=8710,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
