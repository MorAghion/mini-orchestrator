"""SSE event payloads. Used for live frontend updates (wired up in a later phase)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "project:created",
    "project:planned",
    "wave:started",
    "wave:completed",
    "task:started",
    "task:completed",
    "task:error",
    "task:retrying",
    "task:flagged",
    "artifact:created",
    "artifact:updated",
    "review:approved",
    "review:needs_rework",
    "project:completed",
    "project:needs_review",
    "project:failed",
]


class Event(BaseModel):
    type: EventType
    project_id: str
    data: dict[str, Any] = {}
    timestamp: datetime = Field(default_factory=datetime.utcnow)
