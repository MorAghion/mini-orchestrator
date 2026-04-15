"""Artifact retrieval endpoints.

GET /api/projects/{id}/artifacts              list artifacts (metadata only)
GET /api/projects/{id}/artifacts/{filename}   fetch one artifact's content
"""

from __future__ import annotations

import os
from typing import Any

import aiosqlite
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.config import DB_PATH
from backend.engine.artifact_store import read_artifact


router = APIRouter(prefix="/api/projects/{project_id}/artifacts", tags=["artifacts"])


@router.get("")
async def list_artifacts(project_id: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, role, filename, version, created_at FROM artifacts "
            "WHERE project_id = ? ORDER BY role",
            (project_id,),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "role": r[1],
            "filename": r[2],
            "version": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


@router.get("/{filename}", response_class=PlainTextResponse)
async def get_artifact(project_id: str, filename: str) -> str:
    # Basic path safety — filename is a basename only, no traversal.
    safe = os.path.basename(filename)
    if safe != filename or not safe.endswith(".md"):
        raise HTTPException(status_code=400, detail="invalid filename")
    content = await read_artifact(project_id, safe)
    if content is None:
        raise HTTPException(status_code=404, detail="artifact not found")
    return content
