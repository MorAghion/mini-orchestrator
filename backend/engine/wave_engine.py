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
from backend.engine.artifact_store import load_artifacts, save_artifact, save_review_report
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


async def _record_wave(project_id: str, number: int, roles: list[AgentRole]) -> str:
    wave_id = f"wave-{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO waves (id, project_id, number, roles, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                wave_id,
                project_id,
                number,
                json.dumps([r.value for r in roles]),
                WaveStatus.RUNNING.value,
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


async def run_stage1(idea: str, bus: EventBus | None = None) -> Stage1Result:
    """End-to-end Stage 1 pipeline: plan → run waves → review → (optional rework)."""
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

        reviewer = ReviewerAgent()
        report = await reviewer.review(idea, artifacts)
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

            rework_wave_id = await _record_wave(
                project.id, len(plan.waves) + 1, list(affected_by_role.keys())
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
