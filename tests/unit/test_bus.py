"""Contract tests for the async event bus (fan-out, ordering, redaction)."""

from __future__ import annotations

import asyncio
import os

import pytest

from om_harness.config.secrets import SecretRedactor
from om_harness.models.events import Event, EventType
from om_harness.runtime.bus import EventBus


async def test_publish_fans_out_to_all_subscribers() -> None:
    bus = EventBus()
    reader1 = bus.subscribe()
    reader2 = bus.subscribe()
    await bus.publish(Event(type=EventType.RUN_STARTED))
    got1 = await asyncio.wait_for(reader1.get(), timeout=1.0)
    got2 = await asyncio.wait_for(reader2.get(), timeout=1.0)
    assert got1.type == EventType.RUN_STARTED
    assert got2.type == EventType.RUN_STARTED


async def test_events_are_delivered_in_order_per_subscriber() -> None:
    bus = EventBus()
    reader = bus.subscribe()
    for i in range(10):
        await bus.publish(Event(type=EventType.TASK_STARTED, data={"n": i}))
    received = []
    for _ in range(10):
        received.append(await asyncio.wait_for(reader.get(), timeout=1.0))
    assert [e.data["n"] for e in received] == list(range(10))


async def test_redaction_applied_on_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-live-secret")
    bus = EventBus(redactor=SecretRedactor.from_env(os.environ))
    reader = bus.subscribe()
    await bus.publish(
        Event(type=EventType.TOOL_CALL_COMPLETED, data={"output": "key=sk-ant-live-secret"})
    )
    event = await asyncio.wait_for(reader.get(), timeout=1.0)
    assert "sk-ant-live-secret" not in str(event.data)
    assert "REDACTED" in str(event.data)


def test_history_is_bounded() -> None:
    bus = EventBus(history_size=3)
    for i in range(5):
        bus.publish_sync(Event(type=EventType.TASK_STARTED, data={"n": i}))
    assert [e.data["n"] for e in bus.history] == [2, 3, 4]


def test_events_carry_monotonic_seq() -> None:
    bus = EventBus()
    for _ in range(5):
        bus.publish_sync(Event(type=EventType.USAGE))
    seqs = [e.seq for e in bus.history]
    assert seqs == [1, 2, 3, 4, 5]
    assert bus.cursor == 5


def test_since_returns_events_after_cursor() -> None:
    bus = EventBus()
    for _ in range(3):
        bus.publish_sync(Event(type=EventType.USAGE))
    cursor = bus.cursor
    for _ in range(4):
        bus.publish_sync(Event(type=EventType.MESSAGE_DELTA))
    new = bus.since(cursor)
    assert [e.type for e in new] == [EventType.MESSAGE_DELTA] * 4
    assert all(e.seq > cursor for e in new)
    assert bus.since(bus.cursor) == []


def test_since_survives_history_eviction() -> None:
    """Regression: the live-stream freeze.

    Consumers used positional offsets into the bounded history
    (``history[offset:]``); once ``offset`` reached the deque cap, the slice
    was empty forever and the live view froze mid-turn while the agent kept
    running. Seq cursors must keep draining after eviction.
    """
    bus = EventBus(history_size=10)
    bus.publish_sync(Event(type=EventType.RUN_STARTED))
    cursor = bus.cursor
    # Flood well past the cap: old entries evict, positions shift.
    for i in range(50):
        bus.publish_sync(Event(type=EventType.MESSAGE_DELTA, data={"n": i}))
    assert len(bus.history) == 10  # bounded, evicting
    # The old positional drain would return [] here (offset == 11 > 10).
    assert bus.history[11:] == []
    # The seq cursor still sees every retained event published after it.
    new = bus.since(cursor)
    assert [e.data["n"] for e in new] == list(range(40, 50))
    # A cursor taken mid-flood sees only later events.
    mid = bus.since(bus.cursor)
    assert mid == []


async def test_publish_before_subscribe_does_not_lose_history_semantics() -> None:
    bus = EventBus()
    await bus.publish(Event(type=EventType.RUN_STARTED))
    reader = bus.subscribe()
    # Late subscriber only gets future events, but history is queryable.
    assert bus.history[0].type == EventType.RUN_STARTED
    assert reader.empty()


async def test_collect_helper() -> None:
    bus = EventBus()
    reader = bus.subscribe()
    for _ in range(3):
        await bus.publish(Event(type=EventType.USAGE))
    events = await reader.collect(3, timeout=1.0)
    assert len(events) == 3


async def test_close_unblocks_reader() -> None:
    bus = EventBus()
    reader = bus.subscribe()
    await bus.close()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(reader.get(), timeout=1.0)
