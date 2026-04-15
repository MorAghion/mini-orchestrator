"""HTTP-level tests for the project/chat/notes endpoints.

Uses FastAPI's TestClient with the LeadAgent.chat() method mocked so tests
don't invoke the real Claude CLI. Covers project CRUD, launch guards, the
shaping→planning transition marker (BRIEF_READY), note endpoints, and the
chat endpoint's persistence + marker-dispatch behavior.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from backend.agents.lead import ChatReply

# ---------------------------------------------------------------------------
# Shared client fixture — bypasses FastAPI's lifespan and wires the bus by
# hand so we don't take a dependency on `asgi-lifespan` just for tests.
# ---------------------------------------------------------------------------

@pytest.fixture
async def client(isolated_db) -> AsyncIterator[httpx.AsyncClient]:
    from backend.engine.event_bus import EventBus
    from backend.main import app
    app.state.event_bus = EventBus()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# POST /api/projects — creation
# ---------------------------------------------------------------------------

async def test_create_project_defaults_to_shaping(client):
    r = await client.post("/api/projects", json={})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "shaping"
    assert body["project_id"].startswith("proj-")


async def test_create_project_with_idea_still_starts_in_shaping(client):
    # Creation never fires Stage 1 — even if idea provided, must launch explicitly.
    r = await client.post("/api/projects", json={"idea": "Something concrete"})
    assert r.status_code == 201
    pid = r.json()["project_id"]
    # The idea should be persisted though
    detail = (await client.get(f"/api/projects/{pid}")).json()
    assert detail["project"]["idea"] == "Something concrete"
    assert detail["project"]["status"] == "shaping"


async def test_list_projects_returns_created_ones(client):
    r1 = await client.post("/api/projects", json={})
    r2 = await client.post("/api/projects", json={})
    listing = (await client.get("/api/projects")).json()
    ids = {p["id"] for p in listing}
    assert r1.json()["project_id"] in ids
    assert r2.json()["project_id"] in ids


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/launch — guards
# ---------------------------------------------------------------------------

async def test_launch_404_unknown_project(client):
    r = await client.post("/api/projects/proj-nope/launch", json={})
    assert r.status_code == 404


async def test_launch_400_when_no_idea_and_none_stored(client):
    create = await client.post("/api/projects", json={})
    pid = create.json()["project_id"]
    r = await client.post(f"/api/projects/{pid}/launch", json={})
    assert r.status_code == 400


async def test_launch_409_when_not_in_shaping(client, mock_lead_chat):
    # Create shaping, send a chat that triggers BRIEF_READY so the project
    # accepts a launch; then try to launch again — should 409 since status
    # is now planning / later.
    create = await client.post("/api/projects", json={"idea": "dummy brief"})
    pid = create.json()["project_id"]

    # First launch should succeed
    first = await client.post(f"/api/projects/{pid}/launch", json={})
    assert first.status_code == 202

    # Second launch should 409
    second = await client.post(f"/api/projects/{pid}/launch", json={})
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# POST /api/projects/{id}/chat — message flow
# ---------------------------------------------------------------------------

async def test_chat_appends_user_and_lead_messages(client, mock_lead_chat):
    create = await client.post("/api/projects", json={})
    pid = create.json()["project_id"]
    mock_lead_chat["reply"] = ChatReply(display_text="tell me more", cost_usd=0.02)

    r = await client.post(f"/api/projects/{pid}/chat", json={"content": "I want a TODO app"})
    assert r.status_code == 200
    body = r.json()
    assert body["display_text"] == "tell me more"
    assert body["brief_ready"] is False
    assert body["cost_usd"] == 0.02

    # Chat history has both turns
    history = (await client.get(f"/api/projects/{pid}/chat")).json()
    assert [m["role"] for m in history] == ["user", "lead"]
    assert history[0]["content"] == "I want a TODO app"
    assert history[1]["content"] == "tell me more"


async def test_chat_brief_ready_writes_idea_and_bumps_cost(client, mock_lead_chat):
    create = await client.post("/api/projects", json={})
    pid = create.json()["project_id"]
    mock_lead_chat["reply"] = ChatReply(
        display_text="Launching Stage 1 now.",
        brief_ready=True,
        brief_text="A habit tracker for devs. Web app, manual check-off, streaks.",
        cost_usd=0.05,
    )

    r = await client.post(f"/api/projects/{pid}/chat", json={"content": "yes"})
    assert r.status_code == 200
    assert r.json()["brief_ready"] is True

    detail = (await client.get(f"/api/projects/{pid}")).json()
    assert detail["project"]["idea"].startswith("A habit tracker for devs")
    assert detail["project"]["cost_cents"] == 5  # 0.05 * 100


async def test_chat_empty_content_400(client, mock_lead_chat):
    create = await client.post("/api/projects", json={})
    pid = create.json()["project_id"]
    r = await client.post(f"/api/projects/{pid}/chat", json={"content": "   "})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Notes endpoints
# ---------------------------------------------------------------------------

async def test_notes_add_list_drop_roundtrip(client):
    create = await client.post("/api/projects", json={})
    pid = create.json()["project_id"]

    # Initially empty
    assert (await client.get(f"/api/projects/{pid}/notes")).json() == []

    # Add two
    a = (await client.post(f"/api/projects/{pid}/notes", json={"content": "one"})).json()
    await client.post(f"/api/projects/{pid}/notes", json={"content": "two"})
    listing = (await client.get(f"/api/projects/{pid}/notes")).json()
    assert [n["content"] for n in listing] == ["one", "two"]

    # Drop one → only the other remains under pending
    r = await client.delete(f"/api/projects/{pid}/notes/{a['id']}")
    assert r.status_code == 204
    remaining = (await client.get(f"/api/projects/{pid}/notes")).json()
    assert [n["content"] for n in remaining] == ["two"]


async def test_note_chat_marker_writes_to_queue(client, mock_lead_chat):
    create = await client.post("/api/projects", json={"idea": "x"})
    pid = create.json()["project_id"]
    # Launch so the persona becomes narrator
    await client.post(f"/api/projects/{pid}/launch", json={})

    mock_lead_chat["reply"] = ChatReply(
        display_text="Got it.",
        note_queued="don't forget emoji reactions",
        cost_usd=0.01,
    )
    r = await client.post(f"/api/projects/{pid}/chat", json={"content": "oh also…"})
    assert r.status_code == 200

    notes = (await client.get(f"/api/projects/{pid}/notes")).json()
    assert len(notes) == 1
    assert notes[0]["content"] == "don't forget emoji reactions"
