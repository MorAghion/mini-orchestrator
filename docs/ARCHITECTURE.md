# Mini Orchestrator — Architecture

**Version**: 1.0  
**Last updated**: 2026-04-16

---

## 1. System Overview

```
Browser (React/Vite)
  │
  ├── REST API ──────────────────────────────┐
  └── SSE stream ────────────────────────────┤
                                             │
                                   FastAPI (Python)
                                             │
                          ┌──────────────────┼──────────────────┐
                          │                  │                  │
                      SQLite DB         Disk (JSON/MD)    claude CLI
                    (metadata,          (artifacts,       subprocess
                     events,            review reports,   (per agent
                     chat, notes)       task JSONs)       invocation)
```

Single-process backend. No message broker, no worker pool — agent parallelism is managed via `asyncio.Semaphore`.

---

## 2. Tech Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python 3.11 + FastAPI | Async-native; matches asyncio subprocess model |
| Frontend | React 18 + Vite + TypeScript | Fast dev loop; no heavy framework needed |
| DB | SQLite (aiosqlite) | Single-file, zero-setup, single-user app |
| Agent runtime | `claude` CLI subprocess | Runs on Max subscription; no API key needed |
| SSE | sse-starlette | Thin wrapper; no WebSocket complexity |
| Styling | Vanilla CSS (CSS custom properties) | Full control over metallic palette; no runtime overhead |

---

## 3. Components

### FastAPI App (`backend/main.py`)
- Lifespan hook: initializes SQLite schema (`init_db`) + creates in-memory `EventBus`
- CORS: allows `localhost:5173` (Vite dev server)
- Routers: `projects`, `artifacts`, `events`, `chat`

### Wave Engine (`backend/engine/wave_engine.py`)
- `run_stage1`: orchestrates the full Stage 1 pipeline
- `run_revision`: re-runs a subset of agents on user request
- Manages wave + task lifecycle in SQLite; emits events to bus + persists them

### Lead Agent (`backend/agents/lead.py`)
- Three personas: `shaper` (brief), `narrator` (during Stage 1), `refiner` (post-done)
- Emits markers parsed by the chat route: `BRIEF_READY`, `NOTE_QUEUED`, `REVISION_REQUEST`
- Also performs structured Stage 1 planning via `plan_stage1` (`WavePlan` tool call)

### Doc Worker Agent (`backend/agents/worker.py`)
- One instantiated per role per wave
- Receives prior artifacts as context (per `CONTEXT_DEPS` in `stage1.py`)
- Returns raw markdown; artifact store writes it to disk + indexes in SQLite

### Reviewer Agent (`backend/agents/reviewer.py`)
- Reads all 8 artifacts + user notes
- Returns structured `ReviewReport` (JSON schema validated)
- Triggers rework wave if `overall_verdict == "needs_rework"`

### Artifact Store (`backend/engine/artifact_store.py`)
- Writes markdown to `<OUTPUT_DIR>/<project_id>/<FILENAME>`
- Indexes metadata (id, role, filename, version) in SQLite `artifacts` table
- `load_artifacts`: reads all current files for a project from disk

### Event Bus (`backend/engine/event_bus.py`)
- In-memory asyncio pub/sub, one channel per project
- `publish`: fans out to all SSE subscribers + persists to `project_events`
- `subscribe`: async generator consumed by the SSE route
- `close_project`: unblocks all subscribers when Stage 1 finishes

### SQLite (`backend/database.py`)
- Schema: `projects`, `waves`, `doc_tasks`, `artifacts`, `review_issues`, `project_events`, `lead_messages`, `notes_queue`
- Forward-only migrations via `_ensure_column` / `_drop_column_if_exists`
- Content bodies are never stored in SQLite (exception: `lead_messages` and `notes_queue` are small enough to be stored directly)

---

## 4. Data Flow — Stage 1 Launch

```
POST /api/projects/{id}/launch
  → validates project is in 'shaping'
  → sets status = 'planning', persists idea
  → asyncio.create_task(run_stage1(...))   ← fire-and-forget
  → returns 202 immediately

run_stage1:
  → lead.plan_stage1(idea)               ← claude CLI: structured output (WavePlan)
  → emit project:planned
  → for each wave:
      → _record_wave in SQLite
      → asyncio.gather(*[_run_worker(role) for role in wave], semaphore)
        → each worker: claude CLI subprocess → save_artifact (disk + SQLite) → emit task events
  → status = 'stage1_review'
  → absorb_pending_notes
  → reviewer.review(artifacts, notes)    ← claude CLI: structured output (ReviewReport)
  → save_review_report (disk + SQLite)
  → emit review:approved / review:needs_rework
  → (if needs_rework): run rework wave with feedback injected
  → status = 'stage1_done'
  → emit project:completed
```

---

## 5. Storage Model

**Disk** (source of truth for content):
- `backend/output/<project_id>/<ROLE>.md` — generated design docs
- `backend/output/<project_id>/review_report.json` — reviewer output
- Future: `tasks/sprint-N/task-NNN.json`, `tasks/unassigned/handoff-NNN.json`

**SQLite** (metadata index for UI queries):
- All foreign keys and status flags; no content bodies
- `lead_messages` + `notes_queue`: small structured data, stored directly

**Environment variables** (config):
- `OUTPUT_DIR`, `DB_PATH`, `MAX_CONCURRENT_AGENTS`, `AGENT_MODEL`, `BACKEND_PORT`

---

## 6. Key Architecture Decisions

**Blackboard pattern** — agents never communicate directly. Every artifact is written to disk and read by the next wave via the artifact store. No agent-to-agent calls.

**Disk is source of truth** — SQLite holds metadata only. If the DB is lost, it can be rebuilt by scanning the output directory. This is the crash recovery strategy for Stage 2.

**No API key** — `ANTHROPIC_API_KEY` is stripped from the subprocess environment before every `claude -p` call. All agent work consumes the user's Max subscription.

**Single-process async** — no Celery, no worker processes. `asyncio.gather` + `asyncio.Semaphore` handle Stage 1 parallelism. Keeps the deployment model simple (single `uvicorn` process).

**SSE over WebSocket** — unidirectional server-push is sufficient; simpler than WebSocket. Events are persisted to SQLite so the frontend can replay history on reconnect.

**Concurrency guard on revisions** — `/revise` transitions status to `stage1_running` synchronously before spawning the background task. `run_revision` restores `stage1_done` in `finally`. This prevents concurrent revisions without a distributed lock.
