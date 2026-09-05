"""Asynchronous event bus: one publish point, many subscribers.

Runtime components publish; UIs, the persistence layer, and tracers consume.
Redaction is applied at publish time so every consumer is covered once.
Subscribers are asyncio-queue-backed readers; history is a bounded deque for
late inspection (``bus.history``) — events are never replayed into models.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from typing import Any

from om_harness.config.secrets import SecretRedactor
from om_harness.models.events import Event


class EventReader:
    """Async iterator over events published after subscription."""

    def __init__(self, queue: asyncio.Queue[Event | None]) -> None:
        self._queue = queue

    def empty(self) -> bool:
        return self._queue.empty()

    async def get(self, timeout: float | None = None) -> Event:
        if timeout is None:
            event = await self._queue.get()
        else:
            event = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        if event is None:
            raise asyncio.CancelledError()
        return event

    async def collect(self, count: int, timeout: float = 5.0) -> list[Event]:
        """Collect exactly ``count`` events; raises on timeout."""
        events: list[Event] = []
        for _ in range(count):
            events.append(await self.get(timeout=timeout))
        return events

    def __aiter__(self) -> EventReader:
        return self

    async def __anext__(self) -> Event:
        try:
            return await self.get()
        except asyncio.CancelledError:
            raise StopAsyncIteration from None


class EventBus:
    """Fan-out event hub with bounded history and publish-time redaction."""

    def __init__(
        self,
        redactor: SecretRedactor | None = None,
        history_size: int = 1000,
        max_queue: int = 10_000,
    ) -> None:
        self._redactor = redactor
        self._history: deque[Event] = deque(maxlen=history_size)
        self._max_queue = max_queue
        self._subscribers: list[asyncio.Queue[Event | None]] = []
        self._closed = False

    def subscribe(self) -> EventReader:
        queue: asyncio.Queue[Event | None] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.append(queue)
        return EventReader(queue)

    @property
    def history(self) -> list[Event]:
        return list(self._history)

    async def publish(self, event: Event) -> None:
        if self._closed:
            return
        event = self._redact(event)
        self._history.append(event)
        for queue in list(self._subscribers):
            self._enqueue(queue, event)

    def publish_sync(self, event: Event) -> None:
        """Synchronous path for non-async callers (CLI one-shots, tests)."""
        if self._closed:
            return
        event = self._redact(event)
        self._history.append(event)
        for queue in list(self._subscribers):
            self._enqueue(queue, event)

    async def close(self) -> None:
        self._closed = True
        for queue in self._subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    def _enqueue(self, queue: asyncio.Queue[Event | None], event: Event) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - defensive
            # Drop the oldest event rather than blocking the runtime.
            try:
                queue.get_nowait()
                queue.put_nowait(event)
            except asyncio.QueueEmpty:
                pass

    def _redact(self, event: Event) -> Event:
        if self._redactor is None:
            return event
        return event.model_copy(update={"data": self._redactor.redact_value(event.data)})


class EventCollector:
    """Test/diagnostic helper that records every event passing through."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    def reader_factory(self, bus: EventBus) -> Any:
        reader = bus.subscribe()

        async def _pump() -> None:
            try:
                while True:
                    self.events.append(await reader.get())
            except asyncio.CancelledError:
                return

        return _pump
