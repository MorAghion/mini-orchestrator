"""REST endpoints for projects.

POST /api/projects                create a new project in `shaping` status
                                  (no Stage 1 yet — user chats with Lead first)
POST /api/projects/{id}/launch    transition shaping → planning + kick off Stage 1
GET  /api/projects                list recent projects
GET  /api/projects/{id}           project details + waves + tasks
GET  /api/projects/{id}/review    review report
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.config import DB_PATH
from backend.engine.artifact_store import project_dir
from backend.engine.wave_engine import run_revision, run_stage1
from backend.models.project import AgentRole, ProjectStatus

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Create / launch
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    # Optional at creation time — shaping phase fills this via chat. If a user
    # already has a brief, they can pass it straight in and skip to launch.
    idea: str | None = None


class CreateProjectResponse(BaseModel):
    project_id: str
    status: str


@router.post("", response_model=CreateProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(body: CreateProjectRequest) -> CreateProjectResponse:
    """Create a fresh project in `shaping` status. Does NOT fire Stage 1.

    The client then chats with the Lead via POST /api/projects/{id}/chat.
    When the user is ready, POST /api/projects/{id}/launch transitions the
    project to `planning` and kicks off Stage 1 in the background.
    """
    project_id = f"proj-{uuid.uuid4().hex[:12]}"
    output_dir = f"backend/output/{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO projects (id, idea, status, output_dir, cost_cents, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 0, ?, ?)",
            (
                project_id,
                (body.idea or "").strip(),
                ProjectStatus.SHAPING.value,
                output_dir,
                now,
                now,
            ),
        )
        await db.commit()
    return CreateProjectResponse(project_id=project_id, status=ProjectStatus.SHAPING.value)


class LaunchRequest(BaseModel):
    # If the shaper chat produced a brief, the client passes it here when
    # launching. If omitted, we use whatever is already in projects.idea
    # (set either at creation time or via an earlier launch that failed).
    idea: str | None = None


@router.post("/{project_id}/launch", status_code=status.HTTP_202_ACCEPTED)
async def launch_project(
    project_id: str, body: LaunchRequest, request: Request
) -> dict[str, str]:
    """Transition shaping → planning and kick off Stage 1 in the background."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT status, idea FROM projects WHERE id = ?", (project_id,)
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="project not found")
    current_status, current_idea = row[0], row[1]
    if current_status != ProjectStatus.SHAPING.value:
        raise HTTPException(
            status_code=409,
            detail=f"project is in '{current_status}', can only launch from 'shaping'",
        )

    idea = (body.idea or current_idea or "").strip()
    if not idea:
        raise HTTPException(
            status_code=400,
            detail="no idea text to launch with — send one in the body or set it via chat first",
        )

    # Persist the final idea + bump status so the engine picks up from here.
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET idea = ?, status = ?, updated_at = ? WHERE id = ?",
            (
                idea,
                ProjectStatus.PLANNING.value,
                datetime.utcnow().isoformat(),
                project_id,
            ),
        )
        await db.commit()

    bus = request.app.state.event_bus
    # Fire and forget — run_stage1 emits events to the bus as it progresses.
    asyncio.create_task(run_stage1(idea, bus=bus, existing_project_id=project_id))
    return {"project_id": project_id, "status": ProjectStatus.PLANNING.value}


# ---------------------------------------------------------------------------
# Revise — user-requested re-run after Stage 1 done
# ---------------------------------------------------------------------------

# When the user doesn't explicitly tell us which docs to revise, default to
# the user-facing surface area — anything that touches features, UI, or
# behavior. Backend / DevOps stay put unless the user names them.
_DEFAULT_REVISION_ROLES: list[AgentRole] = [
    AgentRole.PRD,
    AgentRole.ARCHITECT,
    AgentRole.BACKEND_DOC,
    AgentRole.FRONTEND_DOC,
    AgentRole.SECURITY_DOC,
    AgentRole.UI_DESIGN_DOC,
    AgentRole.SCREENS_DOC,
]


class ReviseRequest(BaseModel):
    instruction: str
    affected_roles: list[str] | None = None  # role.value strings


@router.post("/{project_id}/revise", status_code=status.HTTP_202_ACCEPTED)
async def revise_project(
    project_id: str, body: ReviseRequest, request: Request
) -> dict[str, Any]:
    """Trigger a targeted re-run of selected doc agents + Reviewer.

    Only valid when the project is in `stage1_done`. Validates the role list,
    schedules `run_revision()` as a background task, and returns immediately.
    Progress is observable via the SSE event stream + chat (Lead won't talk
    here; the engine emits wave/task/artifact events same as Stage 1).
    """
    instruction = body.instruction.strip()
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction cannot be empty")

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT status FROM projects WHERE id = ?", (project_id,))
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="project not found")
    project_status = row[0]
    if project_status != ProjectStatus.STAGE1_DONE.value:
        raise HTTPException(
            status_code=409,
            detail=f"project is in '{project_status}' — revisions are only accepted in 'stage1_done'",
        )

    # Validate the requested roles, fall back to the safe default.
    if body.affected_roles is None:
        roles = _DEFAULT_REVISION_ROLES
    else:
        roles = []
        for raw in body.affected_roles:
            try:
                role = AgentRole(raw)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from e
            if role in (AgentRole.LEAD, AgentRole.REVIEWER):
                raise HTTPException(
                    status_code=400,
                    detail=f"cannot revise {role.value} — it doesn't produce a doc artifact",
                )
            roles.append(role)
        if not roles:
            raise HTTPException(status_code=400, detail="affected_roles cannot be empty")

    bus = request.app.state.event_bus
    asyncio.create_task(run_revision(project_id, instruction, roles, bus=bus))
    return {
        "project_id": project_id,
        "status": project_status,
        "affected_roles": [r.value for r in roles],
    }


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@router.get("")
async def list_projects() -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, idea, status, cost_cents, created_at, updated_at FROM projects "
            "ORDER BY created_at DESC LIMIT 50"
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "idea": r[1],
            "status": r[2],
            "cost_cents": r[3],
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, idea, status, output_dir, cost_cents, created_at, updated_at "
            "FROM projects WHERE id = ?",
            (project_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="project not found")
        project = {
            "id": row[0],
            "idea": row[1],
            "status": row[2],
            "output_dir": row[3],
            "cost_cents": row[4],
            "created_at": row[5],
            "updated_at": row[6],
        }

        cur = await db.execute(
            "SELECT id, number, roles, status, is_rework, is_revision, "
            "instruction, started_at, completed_at "
            "FROM waves WHERE project_id = ? ORDER BY number",
            (project_id,),
        )
        waves = [
            {
                "id": w[0],
                "number": w[1],
                "roles": json.loads(w[2]),
                "status": w[3],
                "is_rework": bool(w[4]),
                "is_revision": bool(w[5]),
                "instruction": w[6],
                "started_at": w[7],
                "completed_at": w[8],
            }
            for w in await cur.fetchall()
        ]

        cur = await db.execute(
            "SELECT id, wave_id, role, status, artifact_id, error, started_at, completed_at "
            "FROM doc_tasks WHERE project_id = ? ORDER BY started_at",
            (project_id,),
        )
        tasks = [
            {
                "id": t[0],
                "wave_id": t[1],
                "role": t[2],
                "status": t[3],
                "artifact_id": t[4],
                "error": t[5],
                "started_at": t[6],
                "completed_at": t[7],
            }
            for t in await cur.fetchall()
        ]

    return {"project": project, "waves": waves, "tasks": tasks}


@router.get("/{project_id}/review")
async def get_review(project_id: str) -> dict[str, Any]:
    path = os.path.join(project_dir(project_id), "review_report.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="review report not available yet")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
