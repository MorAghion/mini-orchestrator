"""Artifact store — writes generated docs to disk, mirrors metadata to SQLite.

**Disk is the source of truth** for artifact content. The SQLite `artifacts`
table is a metadata-only index (role → filename + current version) that lets
the UI list artifacts cheaply. To read content, always open the file on disk.

Disk layout: <OUTPUT_DIR>/<project_id>/docs/<FILENAME.md>
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

import aiosqlite

from backend.agents.prompts.stage1 import FILENAMES
from backend.config import DB_PATH, OUTPUT_DIR
from backend.models.project import AgentRole, Artifact, ReviewReport


def project_dir(project_id: str) -> str:
    return os.path.join(OUTPUT_DIR, project_id)


def docs_dir(project_id: str) -> str:
    return os.path.join(project_dir(project_id), "docs")


def ensure_project_dirs(project_id: str) -> None:
    os.makedirs(docs_dir(project_id), exist_ok=True)


async def save_artifact(
    project_id: str,
    role: AgentRole,
    content: str,
) -> Artifact:
    """Write artifact to disk and upsert into SQLite. Bumps version on rewrite."""
    ensure_project_dirs(project_id)
    filename = FILENAMES[role]
    path = os.path.join(docs_dir(project_id), filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, version FROM artifacts WHERE project_id = ? AND role = ?",
            (project_id, role.value),
        )
        row = await cur.fetchone()
        now = datetime.utcnow().isoformat()
        if row:
            artifact_id, version = row[0], row[1] + 1
            await db.execute(
                "UPDATE artifacts SET version = ?, created_at = ? WHERE id = ?",
                (version, now, artifact_id),
            )
        else:
            artifact_id = f"art-{uuid.uuid4().hex[:12]}"
            version = 1
            await db.execute(
                "INSERT INTO artifacts (id, project_id, role, filename, version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (artifact_id, project_id, role.value, filename, version, now),
            )
        await db.commit()

    return Artifact(
        id=artifact_id,
        project_id=project_id,
        role=role,
        filename=filename,
        version=version,
    )


async def load_artifacts(project_id: str) -> dict[AgentRole, str]:
    """Return all artifacts for a project as a role -> markdown content mapping.

    The DB tells us which roles have artifacts and the current filename; the
    content itself is read from disk (source of truth).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT role, filename FROM artifacts WHERE project_id = ?",
            (project_id,),
        )
        rows = await cur.fetchall()
    out: dict[AgentRole, str] = {}
    for role_value, filename in rows:
        path = os.path.join(docs_dir(project_id), filename)
        if not os.path.exists(path):
            # DB row exists but file is gone — skip. The alternative is to
            # delete the stale row, but we prefer non-destructive reads.
            continue
        with open(path, encoding="utf-8") as f:
            out[AgentRole(role_value)] = f.read()
    return out


async def read_artifact(project_id: str, filename: str) -> str | None:
    """Return the markdown body for an artifact, or None if missing.

    Shared helper so routes/agents agree on the read path.
    """
    path = os.path.join(docs_dir(project_id), filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


async def save_review_report(project_id: str, report: ReviewReport) -> None:
    """Persist issues to SQLite and write the full report as JSON next to the docs."""
    path = os.path.join(project_dir(project_id), "review_report.json")
    ensure_project_dirs(project_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM review_issues WHERE project_id = ?", (project_id,))
        for issue in report.issues:
            await db.execute(
                "INSERT INTO review_issues (project_id, severity, category, "
                "affected_artifacts, description, suggested_fix) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    project_id,
                    issue.severity,
                    issue.category,
                    json.dumps(issue.affected_artifacts),
                    issue.description,
                    issue.suggested_fix,
                ),
            )
        await db.commit()
