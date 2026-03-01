"""Tests for the in-process pub/sub MessageBus."""

import asyncio

from megobari.api.pubsub import MessageBus, MessageEvent


def _make_event(id: int = 1, content: str = "hello") -> MessageEvent:
    return MessageEvent(
        id=id,
        session_name="default",
        role="user",
        content=content,
        created_at="2026-02-28T12:00:00",
    )


def test_subscribe_returns_queue():
    bus = MessageBus()
    q = bus.subscribe()
    assert isinstance(q, asyncio.Queue)
    assert q.maxsize == 256


def test_subscribe_adds_to_subscribers():
    bus = MessageBus()
    q = bus.subscribe()
    assert q in bus._subscribers


async def test_publish_sends_to_all_subscribers():
    bus = MessageBus()
    q1 = bus.subscribe()
    q2 = bus.subscribe()

    event = _make_event()
    bus.publish(event)

    assert not q1.empty()
    assert not q2.empty()
    assert (await q1.get()) is event
    assert (await q2.get()) is event


async def test_publish_no_subscribers():
    """Publishing with no subscribers should not raise."""
    bus = MessageBus()
    bus.publish(_make_event())  # no error


async def test_unsubscribe_stops_receiving():
    bus = MessageBus()
    q = bus.subscribe()
    bus.unsubscribe(q)

    bus.publish(_make_event())

    assert q.empty()
    assert q not in bus._subscribers


def test_unsubscribe_nonexistent_is_noop():
    """Unsubscribing a queue that was never subscribed should not raise."""
    bus = MessageBus()
    q: asyncio.Queue = asyncio.Queue()
    bus.unsubscribe(q)  # no error


async def test_publish_drops_full_queue():
    bus = MessageBus()
    q = bus.subscribe()

    # Fill the queue to capacity (maxsize=256)
    for i in range(256):
        bus.publish(_make_event(id=i))

    assert q.full()
    assert q in bus._subscribers

    # Next publish should drop the full queue
    bus.publish(_make_event(id=999))

    assert q not in bus._subscribers


async def test_publish_drops_only_full_queues():
    bus = MessageBus()
    q_fast = bus.subscribe()
    q_slow = bus.subscribe()

    # Fill only q_slow
    for i in range(256):
        q_slow.put_nowait(_make_event(id=i))
    # Drain q_fast so it stays not-full
    while not q_fast.empty():
        q_fast.get_nowait()

    assert q_slow.full()
    assert not q_fast.full()

    bus.publish(_make_event(id=1000))

    # q_slow dropped, q_fast still subscribed
    assert q_slow not in bus._subscribers
    assert q_fast in bus._subscribers
    # q_fast received the latest event
    got = await q_fast.get()
    assert got.id == 1000


async def test_multiple_publishes():
    bus = MessageBus()
    q = bus.subscribe()

    bus.publish(_make_event(id=1, content="first"))
    bus.publish(_make_event(id=2, content="second"))
    bus.publish(_make_event(id=3, content="third"))

    assert q.qsize() == 3
    assert (await q.get()).content == "first"
    assert (await q.get()).content == "second"
    assert (await q.get()).content == "third"
