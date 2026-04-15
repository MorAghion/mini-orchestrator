"""Chat store round-trip tests.

Exercises lead_messages + notes_queue persistence against a fresh DB via
the isolated_db fixture. No CLI calls, no FastAPI — pure DB.
"""

from __future__ import annotations

from backend.engine.chat_store import (
    absorb_pending_notes,
    add_note,
    append_message,
    drop_note,
    list_notes,
    load_messages,
)
from backend.models.project import ChatRole, NoteStatus

PROJECT = "proj-test"


async def test_append_and_load_messages(isolated_db):
    msg1 = await append_message(PROJECT, ChatRole.USER, "hello")
    msg2 = await append_message(PROJECT, ChatRole.LEAD, "hi back")
    assert msg1.id is not None and msg2.id is not None
    assert msg2.id > msg1.id  # monotonic

    loaded = await load_messages(PROJECT)
    assert [m.content for m in loaded] == ["hello", "hi back"]
    assert [m.role for m in loaded] == [ChatRole.USER, ChatRole.LEAD]


async def test_load_messages_scoped_per_project(isolated_db):
    await append_message("proj-a", ChatRole.USER, "from A")
    await append_message("proj-b", ChatRole.USER, "from B")
    assert len(await load_messages("proj-a")) == 1
    assert len(await load_messages("proj-b")) == 1
    assert len(await load_messages("proj-none")) == 0


async def test_add_and_list_notes_defaults_to_pending(isolated_db):
    await add_note(PROJECT, "remember tags")
    await add_note(PROJECT, "also dark mode")
    notes = await list_notes(PROJECT)  # default: pending
    assert len(notes) == 2
    assert all(n.status == NoteStatus.PENDING for n in notes)
    assert [n.content for n in notes] == ["remember tags", "also dark mode"]


async def test_drop_note_marks_as_dropped_and_excludes_from_pending(isolated_db):
    n = await add_note(PROJECT, "skip this one")
    changed = await drop_note(PROJECT, n.id)
    assert changed is True
    # No longer returned under pending
    pending = await list_notes(PROJECT, NoteStatus.PENDING)
    assert pending == []
    # But still present under the full list
    all_notes = await list_notes(PROJECT, status=None)
    assert len(all_notes) == 1
    assert all_notes[0].status == NoteStatus.DROPPED


async def test_drop_note_idempotent(isolated_db):
    n = await add_note(PROJECT, "x")
    first = await drop_note(PROJECT, n.id)
    second = await drop_note(PROJECT, n.id)
    assert first is True
    assert second is False  # already dropped, nothing changed


async def test_drop_note_unknown_id_returns_false(isolated_db):
    changed = await drop_note(PROJECT, "note-doesnotexist")
    assert changed is False


async def test_absorb_pending_notes_returns_and_marks_all(isolated_db):
    await add_note(PROJECT, "n1")
    await add_note(PROJECT, "n2")
    await add_note(PROJECT, "n3")
    # Drop one — it shouldn't be absorbed, it was already resolved.
    dropped = (await list_notes(PROJECT))[1]
    await drop_note(PROJECT, dropped.id)

    absorbed = await absorb_pending_notes(PROJECT)
    assert [n.content for n in absorbed] == ["n1", "n3"]

    # All pending are now absorbed
    assert await list_notes(PROJECT, NoteStatus.PENDING) == []
    all_notes = await list_notes(PROJECT, status=None)
    statuses = {n.content: n.status for n in all_notes}
    assert statuses["n1"] == NoteStatus.ABSORBED
    assert statuses["n2"] == NoteStatus.DROPPED
    assert statuses["n3"] == NoteStatus.ABSORBED


async def test_absorb_pending_notes_empty_noop(isolated_db):
    absorbed = await absorb_pending_notes(PROJECT)
    assert absorbed == []


async def test_note_source_msg_id_roundtrip(isolated_db):
    msg = await append_message(PROJECT, ChatRole.USER, "queue X")
    note = await add_note(PROJECT, "X", source_msg_id=msg.id)
    assert note.source_msg_id == msg.id

    loaded = await list_notes(PROJECT)
    assert loaded[0].source_msg_id == msg.id
