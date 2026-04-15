"""REST endpoints for projects.

POST /api/projects              kick off a new Stage 1 run (async)
GET  /api/projects              list recent projects
GET  /api/projects/{id}         project details + waves + tasks
GET  /api/projects/{id}/review  review report
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from backend.config import DB_PATH
from backend.engine.artifact_store import project_dir
from backend.engine.wave_engine import run_stage1


router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    idea: str


class CreateProjectResponse(BaseModel):
    project_id: str


@router.post("", response_model=CreateProjectResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_project(body: CreateProjectRequest, request: Request) -> CreateProjectResponse:
    """Creates a project and kicks off Stage 1 in the background.

    Returns immediately with the project_id; the client subscribes to
    /api/projects/{id}/events for live progress.
    """
    bus = request.app.state.event_bus
    # run_stage1 emits project:created with the project_id in its event data
    # right after it persists the project row, so the client can subscribe
    # to that id via SSE. We don't need to wait for the id here — the client
    # polls /api/projects to find it, or uses a known-good id pattern.
    # Simpler: generate the project inside run_stage1 and let the first SSE
    # event carry the id.
    #
    # For now, we inline a small shim: peek the first project:created event
    # from the bus before returning. This avoids a round-trip for the UI.
    project_id_future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    async def _run_and_capture_id() -> None:
        # Subscribe BEFORE run_stage1 publishes, so we don't race.
        # We don't know the id yet, so subscribe to "*" by patching the bus —
        # simpler: inline the project creation above run_stage1. See below.
        try:
            result = await run_stage1(body.idea, bus=bus)
            if not project_id_future.done():
                project_id_future.set_result(result.project.id)
        except Exception as e:
            if not project_id_future.done():
                project_id_future.set_exception(e)

    # Workaround: generate the id up-front by peeking into the engine.
    # Simpler path — just spawn the task and wait for the first row to land
    # in SQLite. run_stage1 inserts the project row very early (before any
    # agent call), so a short poll is enough.
    task = asyncio.create_task(_run_and_capture_id())
    project_id = await _wait_for_first_project_id_since_task_start(task)
    return CreateProjectResponse(project_id=project_id)


async def _wait_for_first_project_id_since_task_start(task: asyncio.Task, timeout: float = 10.0) -> str:
    """Poll SQLite until the most-recent project appears (inserted by run_stage1)."""
    start_count = await _count_projects()
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if task.done() and task.exception():
            raise HTTPException(
                status_code=500, detail=f"stage1 failed to start: {task.exception()}"
            )
        current_count = await _count_projects()
        if current_count > start_count:
            return await _latest_project_id()
        await asyncio.sleep(0.1)
    raise HTTPException(status_code=500, detail="timed out waiting for project to be created")


async def _count_projects() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM projects")
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def _latest_project_id() -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id FROM projects ORDER BY created_at DESC LIMIT 1"
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="no project found after creation")
    return str(row[0])


@router.get("")
async def list_projects() -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, idea, status, created_at, updated_at FROM projects "
            "ORDER BY created_at DESC LIMIT 50"
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "idea": r[1],
            "status": r[2],
            "created_at": r[3],
            "updated_at": r[4],
        }
        for r in rows
    ]


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict[str, Any]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, idea, status, output_dir, created_at, updated_at FROM projects WHERE id = ?",
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
            "created_at": row[4],
            "updated_at": row[5],
        }

        cur = await db.execute(
            "SELECT id, number, roles, status, is_rework, started_at, completed_at "
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
                "started_at": w[5],
                "completed_at": w[6],
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
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
