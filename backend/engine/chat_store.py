"""Persistence for the Lead chat and the user's pending-notes queue.

Pattern is consistent with artifact_store: SQLite holds all fields (these
are small, so the DB is the source of truth). No disk mirror — chat history
is structured data, not artifact content.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import aiosqlite

from backend.config import DB_PATH
from backend.models.project import ChatMessage, ChatRole, Note, NoteStatus


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

async def append_message(
    project_id: str, role: ChatRole, content: str
) -> ChatMessage:
    """Insert a chat message and return it with its assigned id."""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO lead_messages (project_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?)",
            (project_id, role.value, content, now),
        )
        await db.commit()
        msg_id = cur.lastrowid
    return ChatMessage(
        id=msg_id,
        project_id=project_id,
        role=role,
        content=content,
        created_at=datetime.fromisoformat(now),
    )


async def load_messages(project_id: str) -> list[ChatMessage]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, role, content, created_at FROM lead_messages "
            "WHERE project_id = ? ORDER BY id",
            (project_id,),
        )
        rows = await cur.fetchall()
    return [
        ChatMessage(
            id=r[0],
            project_id=project_id,
            role=ChatRole(r[1]),
            content=r[2],
            created_at=datetime.fromisoformat(r[3]),
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Notes queue
# ---------------------------------------------------------------------------

def _new_note_id() -> str:
    return f"note-{uuid.uuid4().hex[:12]}"


async def add_note(
    project_id: str,
    content: str,
    source_msg_id: Optional[int] = None,
) -> Note:
    note_id = _new_note_id()
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO notes_queue (id, project_id, content, source_msg_id, status, created_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (note_id, project_id, content, source_msg_id, now),
        )
        await db.commit()
    return Note(
        id=note_id,
        project_id=project_id,
        content=content,
        source_msg_id=source_msg_id,
        status=NoteStatus.PENDING,
        created_at=datetime.fromisoformat(now),
    )


async def list_notes(
    project_id: str,
    status: Optional[NoteStatus] = NoteStatus.PENDING,
) -> list[Note]:
    """List notes for a project; defaults to pending only."""
    if status is None:
        sql = (
            "SELECT id, content, source_msg_id, status, absorbed_at, created_at "
            "FROM notes_queue WHERE project_id = ? ORDER BY created_at"
        )
        params: tuple = (project_id,)
    else:
        sql = (
            "SELECT id, content, source_msg_id, status, absorbed_at, created_at "
            "FROM notes_queue WHERE project_id = ? AND status = ? ORDER BY created_at"
        )
        params = (project_id, status.value)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
    return [
        Note(
            id=r[0],
            project_id=project_id,
            content=r[1],
            source_msg_id=r[2],
            status=NoteStatus(r[3]),
            absorbed_at=datetime.fromisoformat(r[4]) if r[4] else None,
            created_at=datetime.fromisoformat(r[5]),
        )
        for r in rows
    ]


async def drop_note(project_id: str, note_id: str) -> bool:
    """Mark a note as dropped (user clicked X). Idempotent — returns True if it changed."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "UPDATE notes_queue SET status = 'dropped' "
            "WHERE id = ? AND project_id = ? AND status = 'pending'",
            (note_id, project_id),
        )
        await db.commit()
        return cur.rowcount > 0


async def absorb_pending_notes(project_id: str) -> list[Note]:
    """Mark all pending notes as absorbed and return the absorbed set.

    Called by the Reviewer (or rework flow) so the notes fold into the
    feedback the next worker agent sees. Returns them in insertion order.
    """
    pending = await list_notes(project_id, NoteStatus.PENDING)
    if not pending:
        return []
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE notes_queue SET status = 'absorbed', absorbed_at = ? "
            "WHERE project_id = ? AND status = 'pending'",
            (now, project_id),
        )
        await db.commit()
    return pending
