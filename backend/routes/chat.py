"""Lead-chat and pending-notes-queue endpoints.

GET  /api/projects/{id}/chat         load full message history
POST /api/projects/{id}/chat         send a user message; returns Lead's reply

GET    /api/projects/{id}/notes      list pending notes
POST   /api/projects/{id}/notes      manually add a note (bypasses chat)
DELETE /api/projects/{id}/notes/{note_id}  drop a pending note

The chat persona is chosen based on project status:
- `shaping`                  → shaper
- `planning` / `stage1_*`    → narrator (during run) / refiner (after done)
- `failed`                   → refiner (so the user can retry / revise)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel

from backend.agents.lead import ChatPersona, LeadAgent
from backend.config import DB_PATH
from backend.engine.chat_store import (
    add_note,
    append_message,
    drop_note,
    list_notes,
    load_messages,
)
from backend.models.project import (
    ChatRole,
    NoteStatus,
    ProjectStatus,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["chat"])


def _persona_for(project_status: str) -> ChatPersona:
    """Pick which Lead persona to activate based on project phase."""
    if project_status == ProjectStatus.SHAPING.value:
        return "shaper"
    if project_status == ProjectStatus.STAGE1_DONE.value:
        return "refiner"
    if project_status == ProjectStatus.FAILED.value:
        return "refiner"
    # planning / stage1_running / stage1_review
    return "narrator"


async def _load_project_status(project_id: str) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT status FROM projects WHERE id = ?", (project_id,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="project not found")
    return row[0]


async def _add_cost_cents(project_id: str, cost_usd: float) -> None:
    """Add the CLI-reported cost (float USD) to projects.cost_cents."""
    cents = int(round(cost_usd * 100))
    if cents <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET cost_cents = cost_cents + ?, updated_at = ? WHERE id = ?",
            (cents, datetime.utcnow().isoformat(), project_id),
        )
        await db.commit()


async def _set_idea(project_id: str, idea: str) -> None:
    """Write the project idea (called when shaper emits BRIEF_READY)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET idea = ?, updated_at = ? WHERE id = ?",
            (idea.strip(), datetime.utcnow().isoformat(), project_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    content: str


class ChatResponse(BaseModel):
    user_message_id: int
    lead_message_id: int
    display_text: str
    brief_ready: bool = False
    note_queued: str | None = None
    revision_request: str | None = None
    cost_usd: float = 0.0


@router.get("/chat")
async def get_chat_history(project_id: str) -> list[dict[str, Any]]:
    await _load_project_status(project_id)  # 404 if missing
    msgs = await load_messages(project_id)
    return [
        {
            "id": m.id,
            "role": m.role.value,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]


@router.post("/chat", response_model=ChatResponse)
async def post_chat(project_id: str, body: ChatRequest) -> ChatResponse:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="empty message")

    project_status = await _load_project_status(project_id)
    persona: ChatPersona = _persona_for(project_status)

    # Append the user message first so history fed into the Lead includes it
    # implicitly via load_messages on the next turn. Here we render history
    # excluding the just-saved user msg because we pass it as the "new" one.
    history = await load_messages(project_id)
    user_msg = await append_message(project_id, ChatRole.USER, content)

    lead = LeadAgent()
    reply = await lead.chat(history=history, user_message=content, persona=persona)

    # Persist the Lead's reply (display_text — markers already stripped).
    lead_msg = await append_message(project_id, ChatRole.LEAD, reply.display_text)

    # Accumulate cost.
    if reply.cost_usd:
        await _add_cost_cents(project_id, reply.cost_usd)

    # Act on orchestrator markers.
    if reply.brief_ready and persona == "shaper" and reply.brief_text:
        await _set_idea(project_id, reply.brief_text)

    if reply.note_queued and persona == "narrator":
        await add_note(project_id, reply.note_queued, source_msg_id=user_msg.id)

    # revision_request handling is Phase 4.1c — parked for now; we just surface
    # it in the response so the frontend can show a "Lead wants to schedule a
    # revision: [Apply]" button.

    return ChatResponse(
        user_message_id=user_msg.id or 0,
        lead_message_id=lead_msg.id or 0,
        display_text=reply.display_text,
        brief_ready=reply.brief_ready,
        note_queued=reply.note_queued,
        revision_request=reply.revision_request,
        cost_usd=reply.cost_usd,
    )


# ---------------------------------------------------------------------------
# Notes queue
# ---------------------------------------------------------------------------

class AddNoteRequest(BaseModel):
    content: str


@router.get("/notes")
async def get_notes(project_id: str) -> list[dict[str, Any]]:
    await _load_project_status(project_id)
    notes = await list_notes(project_id, NoteStatus.PENDING)
    return [
        {
            "id": n.id,
            "content": n.content,
            "source_msg_id": n.source_msg_id,
            "status": n.status.value,
            "created_at": n.created_at.isoformat(),
        }
        for n in notes
    ]


@router.post("/notes", status_code=status.HTTP_201_CREATED)
async def post_note(project_id: str, body: AddNoteRequest) -> dict[str, Any]:
    await _load_project_status(project_id)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="empty note")
    note = await add_note(project_id, content)
    return {
        "id": note.id,
        "content": note.content,
        "status": note.status.value,
        "created_at": note.created_at.isoformat(),
    }


@router.delete("/notes/{note_id}")
async def delete_note(project_id: str, note_id: str) -> Response:
    await _load_project_status(project_id)
    changed = await drop_note(project_id, note_id)
    if not changed:
        raise HTTPException(status_code=404, detail="note not found or already resolved")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
