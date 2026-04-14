"""SQLite schema and init. Mirrors JSON state for UI queries; JSON on disk remains source of truth."""

import aiosqlite

from backend.config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    idea TEXT NOT NULL,
    status TEXT NOT NULL,
    output_dir TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS waves (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    number INTEGER NOT NULL,
    roles TEXT NOT NULL,            -- JSON array
    status TEXT NOT NULL,
    is_rework INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS doc_tasks (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    wave_id TEXT NOT NULL REFERENCES waves(id),
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    artifact_id TEXT,
    error TEXT,
    started_at TEXT,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    role TEXT NOT NULL,
    filename TEXT NOT NULL,
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(id),
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    affected_artifacts TEXT NOT NULL,  -- JSON array
    description TEXT NOT NULL,
    suggested_fix TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_waves_project ON waves(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON doc_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_wave ON doc_tasks(wave_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        # Lightweight forward-only migrations for pre-existing DBs. Each one is
        # idempotent — try the ALTER, swallow "duplicate column" errors.
        await _ensure_column(db, "waves", "is_rework", "INTEGER NOT NULL DEFAULT 0")
        await db.commit()


async def _ensure_column(db: aiosqlite.Connection, table: str, column: str, decl: str) -> None:
    cur = await db.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in await cur.fetchall()}
    if column not in cols:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


async def get_connection() -> aiosqlite.Connection:
    return await aiosqlite.connect(DB_PATH)
