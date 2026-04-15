"""Event bus pub/sub tests — per-project fan-out, multi-subscriber, clean shutdown."""

from __future__ import annotations

import asyncio

from backend.engine.event_bus import EventBus
from backend.models.events import Event


async def _collect(bus: EventBus, project_id: str, n: int) -> list[Event]:
    """Consume n events from a subscription, with a short timeout."""
    collected: list[Event] = []

    async def consume():
        async for event in bus.subscribe(project_id):
            collected.append(event)
            if len(collected) >= n:
                return

    try:
        await asyncio.wait_for(consume(), timeout=1.0)
    except TimeoutError:
        pass
    return collected


async def test_single_subscriber_receives_events():
    bus = EventBus()
    task = asyncio.create_task(_collect(bus, "p1", 2))
    await asyncio.sleep(0.01)  # let subscribe register
    await bus.publish(Event(type="project:created", project_id="p1", data={"idea": "x"}))
    await bus.publish(Event(type="wave:started", project_id="p1", data={"number": 1}))
    got = await task
    assert [e.type for e in got] == ["project:created", "wave:started"]


async def test_events_are_scoped_per_project():
    bus = EventBus()
    task_a = asyncio.create_task(_collect(bus, "pa", 1))
    task_b = asyncio.create_task(_collect(bus, "pb", 1))
    await asyncio.sleep(0.01)
    await bus.publish(Event(type="task:started", project_id="pa", data={}))
    await bus.publish(Event(type="task:completed", project_id="pb", data={}))

    got_a = await task_a
    got_b = await task_b
    assert [e.type for e in got_a] == ["task:started"]
    assert [e.type for e in got_b] == ["task:completed"]


async def test_multiple_subscribers_all_receive():
    bus = EventBus()
    t1 = asyncio.create_task(_collect(bus, "px", 1))
    t2 = asyncio.create_task(_collect(bus, "px", 1))
    await asyncio.sleep(0.01)
    await bus.publish(Event(type="artifact:created", project_id="px", data={"filename": "PRD.md"}))
    g1 = await t1
    g2 = await t2
    assert len(g1) == 1 and len(g2) == 1
    assert g1[0].type == g2[0].type == "artifact:created"


async def test_close_project_unblocks_subscribers():
    bus = EventBus()
    # Subscribe but never publish — the close_project sentinel should end the iteration.
    done = asyncio.Event()

    async def consume():
        async for _ in bus.subscribe("pc"):
            pass
        done.set()

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await bus.close_project("pc")
    await asyncio.wait_for(done.wait(), timeout=0.5)
    assert done.is_set()
    task.cancel()


async def test_no_subscribers_is_fine():
    # publish() should not raise even if nobody listens.
    bus = EventBus()
    await bus.publish(Event(type="project:created", project_id="p-lonely", data={}))
    # (no subscriber registered; nothing to assert beyond "no exception")


async def test_subscriber_is_cleaned_up_on_exit():
    bus = EventBus()

    async def short_consumer():
        async for _ in bus.subscribe("p-clean"):
            return  # exit after one event

    task = asyncio.create_task(short_consumer())
    await asyncio.sleep(0.01)
    await bus.publish(Event(type="task:started", project_id="p-clean", data={}))
    await task
    # async generators run their `finally` via aclose(), which is scheduled
    # in a later event-loop tick. Give it a moment before asserting.
    for _ in range(5):
        if not bus._subscribers.get("p-clean"):
            break
        await asyncio.sleep(0.005)

    assert bus._subscribers.get("p-clean", set()) == set()
