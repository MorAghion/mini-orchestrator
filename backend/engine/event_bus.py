"""In-memory pub/sub event bus for SSE streaming.

Shape: a single EventBus instance is held on `app.state.event_bus`. Publishers
(wave engine) call `publish(project_id, event)`. Subscribers (SSE endpoints)
call `subscribe(project_id)` and iterate the async generator.

Each subscriber gets its own asyncio.Queue so slow consumers don't block the
publisher. Events are fanned out per project_id.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator

from backend.models.events import Event


class EventBus:
    def __init__(self) -> None:
        # project_id -> set of subscriber queues
        self._subscribers: dict[str, set[asyncio.Queue[Event | None]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(event.project_id, ()))
        for q in queues:
            # put_nowait — events are small, queues unbounded
            q.put_nowait(event)

    async def subscribe(self, project_id: str) -> AsyncIterator[Event]:
        """Yields events for a given project until the caller stops iterating."""
        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        async with self._lock:
            self._subscribers[project_id].add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    return
                yield event
        finally:
            async with self._lock:
                self._subscribers[project_id].discard(queue)

    async def close_project(self, project_id: str) -> None:
        """Send a sentinel to all subscribers of a project so they unblock cleanly."""
        async with self._lock:
            queues = list(self._subscribers.get(project_id, ()))
        for q in queues:
            q.put_nowait(None)
