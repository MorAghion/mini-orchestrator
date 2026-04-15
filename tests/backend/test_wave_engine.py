"""Wave engine — unit tests for the deterministic plumbing.

Mocks the agent classes (LeadAgent, DocWorkerAgent, ReviewerAgent) so we
exercise the orchestration logic — wave recording, feedback assembly,
notes absorption, rework/revision routing — without spawning any real
`claude` CLI subprocess.
"""

from __future__ import annotations

import json
from typing import Any

import aiosqlite
import pytest

from backend.engine.chat_store import add_note, list_notes
from backend.models.project import (
    AgentRole,
    NoteStatus,
    ReviewIssue,
    ReviewReport,
    WavePlan,
)

# ---------------------------------------------------------------------------
# Helpers — patch the agent classes so the engine never hits a real CLI
# ---------------------------------------------------------------------------

def _patch_agents(
    monkeypatch,
    *,
    plan: WavePlan,
    review_report: ReviewReport,
    worker_capture: dict[str, list[dict[str, Any]]],
):
    """Install monkeypatches that replace LeadAgent.plan_stage1, the
    DocWorkerAgent.produce_doc body, and ReviewerAgent.review with stubs.

    `worker_capture` is a dict with two keys we'll populate as the engine
    runs: 'doc_calls' (every produce_doc invocation), 'review_calls' (every
    Reviewer.review invocation).
    """
    worker_capture.setdefault("doc_calls", [])
    worker_capture.setdefault("review_calls", [])

    async def fake_plan_stage1(self, idea):
        return plan

    async def fake_produce_doc(self, idea, prior_artifacts, rework_feedback=None):
        worker_capture["doc_calls"].append(
            {
                "role": self.agent_role,
                "rework_feedback": rework_feedback,
            }
        )
        # Return a deterministic stub so save_artifact sees content.
        return f"# {self.filename}\n\nstub for role={self.agent_role.value}"

    async def fake_review(self, idea, artifacts, user_notes=None):
        worker_capture["review_calls"].append(
            {
                "user_notes": list(user_notes) if user_notes else [],
                "artifact_roles": sorted(r.value for r in artifacts),
            }
        )
        return review_report

    monkeypatch.setattr(
        "backend.agents.lead.LeadAgent.plan_stage1", fake_plan_stage1
    )
    monkeypatch.setattr(
        "backend.agents.worker.DocWorkerAgent.produce_doc", fake_produce_doc
    )
    monkeypatch.setattr(
        "backend.agents.reviewer.ReviewerAgent.review", fake_review
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

# Override the repo-wide `no_real_engine_calls` autouse fixture from
# conftest.py. That one noops out run_stage1 / run_revision so route tests
# can't accidentally fire the real engine. Here we DO want the real engine
# (with mocked agent classes) — providing a same-named fixture at this
# narrower scope shadows the conftest one.
@pytest.fixture(autouse=True)
def no_real_engine_calls():
    yield


async def test_run_stage1_absorbs_pending_notes_into_reviewer(
    isolated_db, monkeypatch
):
    from backend.engine.wave_engine import run_stage1

    # Pre-create a project + seed notes against it. run_stage1 takes
    # an existing_project_id, so we set the project up first.
    project_id = "proj-test-notes"
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO projects (id, idea, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, 'shaping', 'out/x', '2026-01-01', '2026-01-01')",
            (project_id, "an idea"),
        )
        await db.commit()
    await add_note(project_id, "remember dark mode")
    await add_note(project_id, "support keyboard shortcuts")

    capture: dict = {}
    plan = WavePlan(waves=[[AgentRole.PRD]])
    report = ReviewReport(overall_verdict="approved", summary="ok", issues=[])
    _patch_agents(monkeypatch, plan=plan, review_report=report, worker_capture=capture)

    await run_stage1("an idea", existing_project_id=project_id)

    # Reviewer was called exactly once and received both notes
    assert len(capture["review_calls"]) == 1
    received = capture["review_calls"][0]["user_notes"]
    assert [n.content for n in received] == [
        "remember dark mode",
        "support keyboard shortcuts",
    ]

    # The notes_queue rows are now marked absorbed (no longer pending)
    pending = await list_notes(project_id, NoteStatus.PENDING)
    assert pending == []
    absorbed = await list_notes(project_id, NoteStatus.ABSORBED)
    assert {n.content for n in absorbed} == {
        "remember dark mode",
        "support keyboard shortcuts",
    }


async def test_run_stage1_rework_feedback_includes_user_notes(
    isolated_db, monkeypatch
):
    from backend.engine.wave_engine import run_stage1

    project_id = "proj-test-rework-notes"
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO projects (id, idea, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, 'shaping', 'out/x', '2026-01-01', '2026-01-01')",
            (project_id, "an idea"),
        )
        await db.commit()
    await add_note(project_id, "must support emoji reactions")

    capture: dict = {}
    plan = WavePlan(waves=[[AgentRole.PRD]])
    # Reviewer flags PRD — triggers rework. Worker for PRD should see both
    # the issue and the absorbed note in its rework_feedback.
    report = ReviewReport(
        overall_verdict="needs_rework",
        summary="missing things",
        issues=[
            ReviewIssue(
                severity="high",
                category="user_note_missing",
                affected_artifacts=["PRD.md"],
                description="emoji reactions not in PRD",
                suggested_fix="add a section",
            )
        ],
    )
    _patch_agents(monkeypatch, plan=plan, review_report=report, worker_capture=capture)

    await run_stage1("an idea", existing_project_id=project_id)

    # Two doc_calls total: the initial PRD wave + the rework PRD wave.
    # The rework call carries non-None rework_feedback containing both
    # the reviewer issue text and the user note text.
    rework_calls = [c for c in capture["doc_calls"] if c["rework_feedback"]]
    assert len(rework_calls) == 1
    feedback = rework_calls[0]["rework_feedback"]
    assert "emoji reactions not in PRD" in feedback        # reviewer issue
    assert "must support emoji reactions" in feedback      # user note verbatim


async def test_run_revision_includes_pending_notes_in_feedback(
    isolated_db, monkeypatch
):
    from backend.engine.wave_engine import run_revision

    project_id = "proj-test-revision-notes"
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO projects (id, idea, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, 'stage1_done', 'out/x', '2026-01-01', '2026-01-01')",
            (project_id, "an idea"),
        )
        # Need an existing artifact row so load_artifacts returns something.
        await db.execute(
            "INSERT INTO artifacts (id, project_id, role, filename, version, created_at) "
            "VALUES (?, ?, 'prd', 'PRD.md', 1, '2026-01-01')",
            ("art-1", project_id),
        )
        await db.commit()

    # Seed two notes that should get folded in
    await add_note(project_id, "left-over note 1")
    await add_note(project_id, "left-over note 2")

    capture: dict = {}
    report = ReviewReport(overall_verdict="approved", summary="ok", issues=[])
    # No plan needed since run_revision doesn't call the Lead, only worker + reviewer
    _patch_agents(
        monkeypatch,
        plan=WavePlan(waves=[]),
        review_report=report,
        worker_capture=capture,
    )

    await run_revision(
        project_id,
        instruction="add dark mode default",
        affected_roles=[AgentRole.PRD],
    )

    # The PRD worker's rework_feedback contains the user instruction
    # AND both leftover notes.
    assert len(capture["doc_calls"]) == 1
    feedback = capture["doc_calls"][0]["rework_feedback"]
    assert "add dark mode default" in feedback
    assert "left-over note 1" in feedback
    assert "left-over note 2" in feedback

    # And the notes are now absorbed.
    assert await list_notes(project_id, NoteStatus.PENDING) == []


async def test_run_stage1_with_no_notes_passes_empty_list_to_reviewer(
    isolated_db, monkeypatch
):
    """Sanity: no notes queued → reviewer called with empty list, not crash."""
    from backend.engine.wave_engine import run_stage1

    project_id = "proj-test-no-notes"
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO projects (id, idea, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, 'shaping', 'out/x', '2026-01-01', '2026-01-01')",
            (project_id, "an idea"),
        )
        await db.commit()

    capture: dict = {}
    plan = WavePlan(waves=[[AgentRole.PRD]])
    report = ReviewReport(overall_verdict="approved", summary="ok", issues=[])
    _patch_agents(monkeypatch, plan=plan, review_report=report, worker_capture=capture)

    await run_stage1("an idea", existing_project_id=project_id)

    assert capture["review_calls"][0]["user_notes"] == []


async def test_run_stage1_records_rework_wave_with_is_rework_flag(
    isolated_db, monkeypatch
):
    """End-to-end check that needs_rework verdict produces a rework wave row."""
    from backend.engine.wave_engine import run_stage1

    project_id = "proj-test-rework-wave"
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO projects (id, idea, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, 'shaping', 'out/x', '2026-01-01', '2026-01-01')",
            (project_id, "an idea"),
        )
        await db.commit()

    capture: dict = {}
    plan = WavePlan(waves=[[AgentRole.PRD]])
    report = ReviewReport(
        overall_verdict="needs_rework",
        summary="x",
        issues=[
            ReviewIssue(
                severity="high",
                category="x",
                affected_artifacts=["PRD.md"],
                description="d",
                suggested_fix="f",
            )
        ],
    )
    _patch_agents(monkeypatch, plan=plan, review_report=report, worker_capture=capture)

    await run_stage1("an idea", existing_project_id=project_id)

    async with aiosqlite.connect(isolated_db) as db:
        cur = await db.execute(
            "SELECT number, is_rework, is_revision, roles FROM waves "
            "WHERE project_id = ? ORDER BY number",
            (project_id,),
        )
        rows = await cur.fetchall()

    assert len(rows) == 2
    initial, rework = rows
    assert initial[1] == 0 and initial[2] == 0  # not rework, not revision
    assert rework[1] == 1 and rework[2] == 0    # rework, not revision
    assert json.loads(rework[3]) == ["prd"]      # only PRD was reworked


async def test_run_revision_records_revision_wave_with_is_revision_flag(
    isolated_db, monkeypatch
):
    from backend.engine.wave_engine import run_revision

    project_id = "proj-test-revision-wave"
    async with aiosqlite.connect(isolated_db) as db:
        await db.execute(
            "INSERT INTO projects (id, idea, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, 'stage1_done', 'out/x', '2026-01-01', '2026-01-01')",
            (project_id, "an idea"),
        )
        await db.execute(
            "INSERT INTO artifacts (id, project_id, role, filename, version, created_at) "
            "VALUES (?, ?, 'prd', 'PRD.md', 1, '2026-01-01')",
            ("art-1", project_id),
        )
        await db.commit()

    capture: dict = {}
    _patch_agents(
        monkeypatch,
        plan=WavePlan(waves=[]),
        review_report=ReviewReport(overall_verdict="approved", summary="ok", issues=[]),
        worker_capture=capture,
    )

    await run_revision(project_id, "add dark mode", [AgentRole.PRD])

    async with aiosqlite.connect(isolated_db) as db:
        cur = await db.execute(
            "SELECT is_rework, is_revision FROM waves WHERE project_id = ?",
            (project_id,),
        )
        rows = await cur.fetchall()

    assert rows == [(0, 1)]
