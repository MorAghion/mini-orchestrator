"""Shared test fixtures for backend tests.

Key fixture: `isolated_db` gives each test its own SQLite file under tmp_path
and monkeypatches `DB_PATH` across every module that imports it directly.
Use `pytest -v` to see each test exercise a fresh DB.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import pytest

# Every module that imports `DB_PATH` as a top-level name from backend.config.
# Grep confirms this list — keep it in sync if new modules start using the DB.
_DB_PATH_USERS = [
    "backend.config",
    "backend.database",
    "backend.engine.chat_store",
    "backend.engine.artifact_store",
    "backend.engine.wave_engine",
    "backend.routes.projects",
    "backend.routes.chat",
    "backend.routes.artifacts",
]


@pytest.fixture
async def isolated_db(tmp_path, monkeypatch) -> AsyncIterator[str]:
    """Each test gets a fresh DB file + schema, isolated from other tests."""
    test_db = str(tmp_path / "test.db")
    for mod_name in _DB_PATH_USERS:
        monkeypatch.setattr(f"{mod_name}.DB_PATH", test_db, raising=False)

    # Also redirect OUTPUT_DIR so artifact_store writes go to tmp_path
    out_dir = str(tmp_path / "output")
    monkeypatch.setattr("backend.config.OUTPUT_DIR", out_dir, raising=False)
    monkeypatch.setattr("backend.engine.artifact_store.OUTPUT_DIR", out_dir, raising=False)

    from backend.database import init_db
    await init_db()
    yield test_db


@pytest.fixture(autouse=True)
def no_real_engine_calls(monkeypatch):
    """Safety: never spawn the real wave engine functions in tests.

    Route tests call POST /api/projects/{id}/launch and /revise which
    schedule background tasks. Without this fixture those would shell out
    to the live Claude CLI. We replace each with a recording no-op so
    tests can both stay safe and assert the engine was invoked correctly.
    """
    calls: dict[str, list[tuple]] = {"run_stage1": [], "run_revision": []}

    async def _noop_stage1(*args, **kwargs):
        calls["run_stage1"].append((args, kwargs))
        return None

    async def _noop_revision(*args, **kwargs):
        calls["run_revision"].append((args, kwargs))
        return None

    # Patch the function definitions AND the names re-exported into routes.
    monkeypatch.setattr("backend.engine.wave_engine.run_stage1", _noop_stage1, raising=False)
    monkeypatch.setattr("backend.routes.projects.run_stage1", _noop_stage1, raising=False)
    monkeypatch.setattr("backend.engine.wave_engine.run_revision", _noop_revision, raising=False)
    monkeypatch.setattr("backend.routes.projects.run_revision", _noop_revision, raising=False)
    return calls


@pytest.fixture
def mock_lead_chat(monkeypatch) -> Iterator[dict]:
    """Monkeypatch LeadAgent.chat() so tests don't hit the live Claude CLI.

    Usage:
        async def test_xxx(mock_lead_chat, isolated_db, ...):
            mock_lead_chat["reply"] = ChatReply(display_text="hi", cost_usd=0.01)
            # ...post to /chat → the mock is returned
    """
    from backend.agents.lead import ChatReply

    state: dict = {"reply": ChatReply(display_text="(mock)", cost_usd=0.0), "calls": []}

    async def _fake_chat(self, history, user_message, persona):
        state["calls"].append(
            {"history_len": len(history), "user_message": user_message, "persona": persona}
        )
        return state["reply"]

    monkeypatch.setattr("backend.agents.lead.LeadAgent.chat", _fake_chat)
    yield state
