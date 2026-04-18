"""End-to-end smoke runner for the orchestrator.

Exercises the full pipeline with real Claude CLI calls:
  1. Stage 1 — Lead plans waves, doc agents write artifacts, Reviewer checks
  2. Notes — adds a note that gets absorbed into the next revision
  3. Revision — user-requested re-run with a specific instruction
  4. Verified assertions — instruction stored in DB, note absorbed

Artifacts are written under tests/smoke_runs/<project_id>/.

Usage:
    python -m tests.run_smoke                    # default idea
    python -m tests.run_smoke "your idea here"
"""

from __future__ import annotations

import asyncio
import os
import sys

# Point OUTPUT_DIR at tests/smoke_runs BEFORE importing backend.* so config picks it up.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SMOKE_DIR = os.path.join(_TESTS_DIR, "smoke_runs")
os.makedirs(_SMOKE_DIR, exist_ok=True)
os.environ["OUTPUT_DIR"] = _SMOKE_DIR

import aiosqlite  # noqa: E402

from backend.config import DB_PATH  # noqa: E402
from backend.database import init_db  # noqa: E402
from backend.engine.chat_store import add_note, list_notes  # noqa: E402
from backend.engine.wave_engine import run_revision, run_stage1  # noqa: E402
from backend.models.project import AgentRole, NoteStatus  # noqa: E402

DEFAULT_IDEA = "A simple todo app with user auth, tags, and due dates"

_OK = "\033[32m✓\033[0m"
_FAIL = "\033[31m✗\033[0m"
_WARN = "\033[33m⚠\033[0m"


def _check(label: str, ok: bool, detail: str = "") -> None:
    icon = _OK if ok else _FAIL
    suffix = f"  {detail}" if detail else ""
    print(f"  {icon} {label}{suffix}")
    if not ok:
        raise AssertionError(f"FAILED: {label}{suffix}")


async def main() -> int:
    idea = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IDEA
    await init_db()

    # -----------------------------------------------------------------------
    # 1. Stage 1
    # -----------------------------------------------------------------------
    print(f"\n[smoke] Stage 1 — idea: {idea!r}")
    result = await run_stage1(idea)
    project_id = result.project.id

    _check("project created", bool(project_id))
    _check(
        "artifacts produced",
        len(result.artifacts) >= 5,
        f"got {len(result.artifacts)}",
    )
    _check(
        "review verdict present",
        result.report.overall_verdict in ("approved", "needs_rework"),
        result.report.overall_verdict,
    )
    _check(
        "output dir exists",
        os.path.isdir(os.path.join(_SMOKE_DIR, project_id, "docs")),
    )
    _check(
        "review_report.json written",
        os.path.exists(os.path.join(_SMOKE_DIR, project_id, "review_report.json")),
    )

    # Verify waves were recorded in DB
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM waves WHERE project_id = ?", (project_id,)
        )
        wave_count = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM project_events WHERE project_id = ?", (project_id,)
        )
        event_count = (await cur.fetchone())[0]

    _check("waves recorded in DB", wave_count >= 1, f"{wave_count} wave(s)")
    _check(
        "SSE events persisted to DB",
        event_count >= 3,  # at minimum: project:planned, wave:started, review:*
        f"{event_count} event(s)",
    )

    if result.reworked_roles:
        print(
            f"  {_WARN} rework cycle ran for: {[r.value for r in result.reworked_roles]}"
        )

    # -----------------------------------------------------------------------
    # 2. Notes — seed one before the revision
    # -----------------------------------------------------------------------
    print(f"\n[smoke] Notes — project: {project_id}")
    note_text = "must support dark mode toggle"
    await add_note(project_id, note_text)
    pending = await list_notes(project_id, NoteStatus.PENDING)
    _check("note added to pending queue", len(pending) == 1, f"{len(pending)} note(s)")

    # -----------------------------------------------------------------------
    # 3. Revision
    # -----------------------------------------------------------------------
    instruction = "add sort-by-name to all list views"
    affected_roles = [AgentRole.PRD, AgentRole.FRONTEND_DOC, AgentRole.SCREENS_DOC]
    print(f"\n[smoke] Revision — instruction: {instruction!r}")
    await run_revision(project_id, instruction, affected_roles)

    # Verify instruction stored in waves table
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT instruction FROM waves WHERE project_id = ? AND is_revision = 1",
            (project_id,),
        )
        revision_row = await cur.fetchone()
        cur = await db.execute(
            "SELECT COUNT(*) FROM project_events WHERE project_id = ? AND type = 'wave:started'",
            (project_id,),
        )
        wave_started_count = (await cur.fetchone())[0]

    _check(
        "revision wave created",
        revision_row is not None,
    )
    _check(
        "revision instruction stored verbatim",
        revision_row is not None and revision_row[0] == instruction,
        f"stored: {revision_row[0]!r}" if revision_row else "no row",
    )

    # Note should be absorbed during the revision
    still_pending = await list_notes(project_id, NoteStatus.PENDING)
    absorbed = await list_notes(project_id, NoteStatus.ABSORBED)
    _check(
        "note absorbed during revision",
        any(n.content == note_text for n in absorbed),
        f"{len(absorbed)} absorbed, {len(still_pending)} still pending",
    )

    _check(
        "wave:started event persisted for revision wave",
        wave_started_count >= 2,  # initial stage1 wave + at least one revision wave
        f"{wave_started_count} wave:started events",
    )

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print(f"\n[smoke] {_OK} all checks passed")
    print(f"  project id: {project_id}")
    print(f"  output:     {_SMOKE_DIR}/{project_id}/docs")
    print(f"  verdict:    {result.report.overall_verdict}")
    print(f"  artifacts:  {len(result.artifacts)}")
    print(f"  waves:      {wave_count}")
    print(f"  events:     {event_count}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
