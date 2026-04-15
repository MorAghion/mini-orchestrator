"""Server-Sent Events endpoint — live progress stream per project.

GET /api/projects/{id}/events

Uses sse-starlette to wire the in-memory EventBus fan-out to HTTP SSE.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from backend.engine.event_bus import EventBus

router = APIRouter(prefix="/api/projects/{project_id}/events", tags=["events"])


@router.get("")
async def stream_events(project_id: str, request: Request) -> EventSourceResponse:
    bus: EventBus = request.app.state.event_bus

    async def generate():
        async for event in bus.subscribe(project_id):
            # Abort if the client has disconnected
            if await request.is_disconnected():
                break
            yield {
                "event": event.type,
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(generate())
