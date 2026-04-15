"""Wave engine — executes the Lead's Stage 1 plan.

Waves run sequentially. Within each wave, doc agents run concurrently bounded by
a semaphore (MAX_CONCURRENT_AGENTS). After all waves, the Reviewer runs over the
full artifact set; if it requests rework, a single rework cycle re-runs the
flagged roles with the reviewer's feedback, then accepts whatever comes back.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

import aiosqlite

from backend.agents.lead import LeadAgent
from backend.agents.reviewer import ReviewerAgent
from backend.agents.worker import DocWorkerAgent
from backend.config import DB_PATH, MAX_CONCURRENT_AGENTS
from backend.engine.artifact_store import (
    load_artifacts,
    save_artifact,
    save_review_report,
)
from backend.engine.chat_store import absorb_pending_notes
from backend.engine.event_bus import EventBus
from backend.models.events import Event, EventType
from backend.models.project import (
    AgentRole,
    Project,
    ProjectStatus,
    ReviewReport,
    TaskStatus,
    WavePlan,
    WaveStatus,
)


async def _emit(
    bus: EventBus | None, project_id: str, event_type: EventType, **data
) -> None:
    if bus is None:
        return
    await bus.publish(Event(type=event_type, project_id=project_id, data=data))


@dataclass
class Stage1Result:
    project: Project
    wave_plan: WavePlan
    artifacts: dict[AgentRole, str]
    report: ReviewReport
    reworked_roles: list[AgentRole]


async def _upsert_project(project: Project) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO projects (id, idea, status, output_dir, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                project.id,
                project.idea,
                project.status.value,
                project.output_dir,
                project.created_at.isoformat(),
                project.updated_at.isoformat(),
            ),
        )
        await db.commit()


async def _record_wave(
    project_id: str,
    number: int,
    roles: list[AgentRole],
    is_rework: bool = False,
    is_revision: bool = False,
) -> str:
    wave_id = f"wave-{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO waves (id, project_id, number, roles, status, "
            "is_rework, is_revision, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                wave_id,
                project_id,
                number,
                json.dumps([r.value for r in roles]),
                WaveStatus.RUNNING.value,
                1 if is_rework else 0,
                1 if is_revision else 0,
                now,
            ),
        )
        await db.commit()
    return wave_id


async def _complete_wave(wave_id: str, status: WaveStatus) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE waves SET status = ?, completed_at = ? WHERE id = ?",
            (status.value, datetime.utcnow().isoformat(), wave_id),
        )
        await db.commit()


async def _record_task(project_id: str, wave_id: str, role: AgentRole) -> str:
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO doc_tasks (id, project_id, wave_id, role, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                task_id,
                project_id,
                wave_id,
                role.value,
                TaskStatus.RUNNING.value,
                datetime.utcnow().isoformat(),
            ),
        )
        await db.commit()
    return task_id


async def _complete_task(task_id: str, status: TaskStatus, artifact_id: str | None = None, error: str | None = None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE doc_tasks SET status = ?, completed_at = ?, artifact_id = ?, error = ? WHERE id = ?",
            (
                status.value,
                datetime.utcnow().isoformat(),
                artifact_id,
                error,
                task_id,
            ),
        )
        await db.commit()


async def _run_worker(
    project_id: str,
    wave_id: str,
    role: AgentRole,
    idea: str,
    prior_artifacts: dict[AgentRole, str],
    rework_feedback: str | None,
    semaphore: asyncio.Semaphore,
    bus: EventBus | None,
) -> tuple[AgentRole, str | None, str | None]:
    """Run one doc agent; returns (role, content_or_None, error_or_None)."""
    task_id = await _record_task(project_id, wave_id, role)
    await _emit(bus, project_id, "task:started", task_id=task_id, role=role.value, wave_id=wave_id)
    async with semaphore:
        try:
            agent = DocWorkerAgent(role)
            content = await agent.produce_doc(idea, prior_artifacts, rework_feedback)
        except Exception as e:  # agent may fail; surface error
            await _complete_task(task_id, TaskStatus.ERROR, error=str(e))
            await _emit(bus, project_id, "task:error", task_id=task_id, role=role.value, error=str(e))
            return role, None, str(e)
    artifact = await save_artifact(project_id, role, content)
    await _complete_task(task_id, TaskStatus.DONE, artifact_id=artifact.id)
    await _emit(
        bus, project_id, "task:completed",
        task_id=task_id, role=role.value, artifact_id=artifact.id,
    )
    await _emit(
        bus, project_id, "artifact:created",
        artifact_id=artifact.id, role=role.value, filename=artifact.filename, version=artifact.version,
    )
    return role, content, None


async def run_stage1(
    idea: str,
    bus: EventBus | None = None,
    existing_project_id: str | None = None,
) -> Stage1Result:
    """End-to-end Stage 1 pipeline: plan → run waves → review → (optional rework).

    If `existing_project_id` is given, the row already exists in `projects`
    (created during the shaping phase). We update it in place and skip the
    project:created emit (subscribers of that id are already connected).
    If None, a fresh project row is created and emitted — used by the CLI
    runner and the old "create + launch" path.
    """
    if existing_project_id:
        project = Project(
            id=existing_project_id,
            idea=idea,
            status=ProjectStatus.PLANNING,
            output_dir=f"backend/output/{existing_project_id}",
        )
        await _upsert_project(project)
    else:
        project = Project(
            id=f"proj-{uuid.uuid4().hex[:12]}",
            idea=idea,
            status=ProjectStatus.PLANNING,
            output_dir=f"backend/output/{uuid.uuid4().hex[:12]}",
        )
        await _upsert_project(project)
        await _emit(bus, project.id, "project:created", idea=idea, project_id=project.id)

    try:
        lead = LeadAgent()
        plan = await lead.plan_stage1(idea)
        await _emit(
            bus, project.id, "project:planned",
            waves=[[r.value for r in wave] for wave in plan.waves],
        )

        project.status = ProjectStatus.STAGE1_RUNNING
        project.updated_at = datetime.utcnow()
        await _upsert_project(project)

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)
        artifacts: dict[AgentRole, str] = {}

        for wave_number, roles in enumerate(plan.waves, start=1):
            wave_id = await _record_wave(project.id, wave_number, roles)
            await _emit(
                bus, project.id, "wave:started",
                wave_id=wave_id, number=wave_number, roles=[r.value for r in roles],
            )
            results = await asyncio.gather(
                *[
                    _run_worker(project.id, wave_id, role, idea, dict(artifacts), None, semaphore, bus)
                    for role in roles
                ]
            )
            wave_failed = False
            for role, content, err in results:
                if err or content is None:
                    wave_failed = True
                    continue
                artifacts[role] = content
            status = WaveStatus.FAILED if wave_failed else WaveStatus.DONE
            await _complete_wave(wave_id, status)
            await _emit(bus, project.id, "wave:completed", wave_id=wave_id, status=status.value)
            if wave_failed:
                project.status = ProjectStatus.FAILED
                project.updated_at = datetime.utcnow()
                await _upsert_project(project)
                await _emit(bus, project.id, "project:failed", reason=f"wave {wave_number} had agent failures")
                raise RuntimeError(f"Wave {wave_number} had agent failures; aborting Stage 1")

        project.status = ProjectStatus.STAGE1_REVIEW
        project.updated_at = datetime.utcnow()
        await _upsert_project(project)

        # Absorb pending notes BEFORE the Reviewer runs so the Reviewer can
        # treat them as additional acceptance criteria. After this call,
        # the notes_queue marks them absorbed and the UI's PendingNotes
        # strip clears.
        absorbed_notes = await absorb_pending_notes(project.id)

        reviewer = ReviewerAgent()
        report = await reviewer.review(idea, artifacts, user_notes=absorbed_notes)
        await save_review_report(project.id, report)
        await _emit(
            bus, project.id,
            "review:approved" if report.overall_verdict == "approved" else "review:needs_rework",
            issue_count=len(report.issues),
            summary=report.summary,
        )

        reworked: list[AgentRole] = []
        if report.overall_verdict == "needs_rework":
            affected_by_role: dict[AgentRole, list[str]] = {}
            from backend.agents.prompts.stage1 import FILENAMES
            filename_to_role = {fname: role for role, fname in FILENAMES.items()}

            for issue in report.issues:
                for fname in issue.affected_artifacts:
                    role = filename_to_role.get(fname)
                    if role is None:
                        continue
                    affected_by_role.setdefault(role, []).append(
                        f"- [{issue.severity}] {issue.description}\n  Fix: {issue.suggested_fix}"
                    )

            # Append the absorbed notes verbatim to every affected role's
            # feedback so the rework agents see the user's words too — not
            # just the Reviewer's interpretation of them.
            if absorbed_notes:
                notes_block = (
                    "\nUser notes from chat (additional acceptance criteria):\n"
                    + "\n".join(f"- {n.content}" for n in absorbed_notes)
                )
                for feedback_lines in affected_by_role.values():
                    feedback_lines.append(notes_block)

            rework_wave_id = await _record_wave(
                project.id,
                len(plan.waves) + 1,
                list(affected_by_role.keys()),
                is_rework=True,
            )
            await _emit(
                bus, project.id, "wave:started",
                wave_id=rework_wave_id,
                number=len(plan.waves) + 1,
                roles=[r.value for r in affected_by_role.keys()],
                rework=True,
            )
            rework_results = await asyncio.gather(
                *[
                    _run_worker(
                        project.id,
                        rework_wave_id,
                        role,
                        idea,
                        dict(artifacts),
                        "\n".join(feedback),
                        semaphore,
                        bus,
                    )
                    for role, feedback in affected_by_role.items()
                ]
            )
            for role, content, err in rework_results:
                if err or content is None:
                    continue
                artifacts[role] = content
                reworked.append(role)
            await _complete_wave(rework_wave_id, WaveStatus.DONE)
            await _emit(bus, project.id, "wave:completed", wave_id=rework_wave_id, status=WaveStatus.DONE.value)

        project.status = ProjectStatus.STAGE1_DONE
        project.updated_at = datetime.utcnow()
        await _upsert_project(project)
        await _emit(
            bus, project.id, "project:completed",
            reworked_roles=[r.value for r in reworked],
            total_artifacts=len(artifacts),
        )

        return Stage1Result(
            project=project,
            wave_plan=plan,
            artifacts=artifacts,
            report=report,
            reworked_roles=reworked,
        )
    finally:
        # Ensure SSE subscribers unblock even on unhandled exceptions
        if bus is not None:
            await bus.close_project(project.id)


# ---------------------------------------------------------------------------
# Revision: user-requested re-run of a subset of doc agents after Stage 1 done
# ---------------------------------------------------------------------------

async def run_revision(
    project_id: str,
    instruction: str,
    affected_roles: list[AgentRole],
    bus: EventBus | None = None,
) -> dict[AgentRole, str]:
    """Re-run `affected_roles` with the user's revision instruction injected
    as feedback, then re-run the Reviewer over the updated artifact set.

    Mechanically very close to the auto-rework cycle in `run_stage1`, but:
    - triggered by user via /revise (not Reviewer's needs_rework verdict)
    - the wave is recorded with `is_revision=True` (not is_rework)
    - the project must already be in `stage1_done`; status doesn't change

    Returns the updated artifacts for the affected roles. The Reviewer's
    new verdict can be fetched via the existing review endpoint.
    """
    if not affected_roles:
        raise ValueError("affected_roles cannot be empty")

    # Pull the existing idea + load all current artifacts as prior context.
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT idea FROM projects WHERE id = ?", (project_id,))
        row = await cur.fetchone()
    if not row:
        raise ValueError(f"project {project_id} not found")
    idea = row[0]

    artifacts = await load_artifacts(project_id)

    # Pick up any leftover pending notes too — fold them into the feedback
    # so a revision doesn't accidentally drop them.
    leftover_notes = await absorb_pending_notes(project_id)

    # Compute the next wave number so the new wave sorts after existing ones.
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COALESCE(MAX(number), 0) FROM waves WHERE project_id = ?",
            (project_id,),
        )
        row = await cur.fetchone()
    next_number = (row[0] if row else 0) + 1

    wave_id = await _record_wave(
        project_id, next_number, affected_roles, is_revision=True
    )
    await _emit(
        bus, project_id, "wave:started",
        wave_id=wave_id,
        number=next_number,
        roles=[r.value for r in affected_roles],
        revision=True,
    )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_AGENTS)
    feedback = f"User-requested revision:\n\n{instruction.strip()}"
    if leftover_notes:
        feedback += "\n\nAlso incorporate these pending user notes:\n" + "\n".join(
            f"- {n.content}" for n in leftover_notes
        )

    results = await asyncio.gather(
        *[
            _run_worker(
                project_id,
                wave_id,
                role,
                idea,
                dict(artifacts),
                feedback,
                semaphore,
                bus,
            )
            for role in affected_roles
        ]
    )

    updated: dict[AgentRole, str] = {}
    wave_failed = False
    for role, content, err in results:
        if err or content is None:
            wave_failed = True
            continue
        artifacts[role] = content
        updated[role] = content

    await _complete_wave(
        wave_id, WaveStatus.FAILED if wave_failed else WaveStatus.DONE
    )
    await _emit(
        bus, project_id, "wave:completed",
        wave_id=wave_id,
        status=(WaveStatus.FAILED if wave_failed else WaveStatus.DONE).value,
    )

    if not wave_failed:
        # Re-run the Reviewer over the new artifact set and persist its verdict.
        reviewer = ReviewerAgent()
        report = await reviewer.review(idea, artifacts)
        await save_review_report(project_id, report)
        await _emit(
            bus, project_id,
            "review:approved" if report.overall_verdict == "approved" else "review:needs_rework",
            issue_count=len(report.issues),
            summary=report.summary,
        )

    return updated
