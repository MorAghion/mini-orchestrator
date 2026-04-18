# Mini Orchestrator — Backend

**Version**: 1.0  
**Last updated**: 2026-04-16

---

## 1. API Surface

All routes are prefixed with `/api`.

### Projects

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/projects` | Create project (status = `shaping`) | — |
| `GET` | `/api/projects` | List 50 most recent projects | — |
| `GET` | `/api/projects/{id}` | Project detail: project + waves + tasks + events | — |
| `POST` | `/api/projects/{id}/launch` | Transition `shaping → planning`, kick off Stage 1 | — |
| `POST` | `/api/projects/{id}/revise` | Re-run selected doc agents + Reviewer | — |
| `GET` | `/api/projects/{id}/review` | Fetch latest `review_report.json` | — |

### Artifacts

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/projects/{id}/artifacts` | List artifact metadata |
| `GET` | `/api/projects/{id}/artifacts/{filename}` | Fetch artifact content (plaintext) |

### Chat + Notes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/projects/{id}/chat` | Full message history |
| `POST` | `/api/projects/{id}/chat` | Send user message; returns Lead reply |
| `GET` | `/api/projects/{id}/notes` | List pending notes |
| `POST` | `/api/projects/{id}/notes` | Manually add note |
| `DELETE` | `/api/projects/{id}/notes/{note_id}` | Drop a pending note |

### Events

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/projects/{id}/events` | SSE stream (live events) |

### Health

| Method | Path |
|--------|------|
| `GET` | `/api/health` |

---

## 2. Data Model (SQLite)

```sql
projects        id, idea, status, output_dir, cost_cents, created_at, updated_at
waves           id, project_id, number, roles (JSON), status,
                is_rework, is_revision, instruction, started_at, completed_at
doc_tasks       id, project_id, wave_id, role, status,
                artifact_id, error, started_at, completed_at
artifacts       id, project_id, role, filename, version, created_at
review_issues   id, project_id, severity, category, affected_artifacts (JSON),
                description, suggested_fix, created_at
project_events  id, project_id, type, data (JSON), timestamp
lead_messages   id, project_id, role (user|lead), content, created_at
notes_queue     id, project_id, content, source_msg_id, status
                (pending|absorbed|dropped), absorbed_at, created_at
```

Disk artifacts: `<OUTPUT_DIR>/<project_id>/<ROLE>.md` and `review_report.json`.

---

## 3. Business Logic Modules

### Wave Engine (`engine/wave_engine.py`)

Runs two entry points:

**`run_stage1(idea, bus, existing_project_id)`**
1. Lead plans waves (structured tool call → `WavePlan`)
2. Waves execute sequentially; agents within a wave run concurrently via `asyncio.gather` + `asyncio.Semaphore(MAX_CONCURRENT_AGENTS)`
3. Each agent failure marks the wave `failed` and aborts Stage 1
4. After all waves: absorb pending notes → Reviewer runs → save `review_report.json`
5. If `needs_rework`: create rework wave with reviewer feedback injected per role
6. Transitions: `planning → stage1_running → stage1_review → stage1_done` (or `failed`)

**`run_revision(project_id, instruction, affected_roles, bus)`**
- Re-runs `affected_roles` with `instruction` as rework feedback
- Re-runs Reviewer over updated artifact set
- Always restores `stage1_done` in `finally` (success or error)
- The `/revise` endpoint transitions status to `stage1_running` synchronously before spawning this task (concurrent revision guard)

### Chat Store (`engine/chat_store.py`)
- `append_message`: writes to `lead_messages`
- `load_messages`: returns full history ordered by `created_at`
- `add_note`, `drop_note`, `list_notes`: manage `notes_queue`
- `absorb_pending_notes`: marks pending notes `absorbed`, returns them for Reviewer consumption

### Artifact Store (`engine/artifact_store.py`)
- `save_artifact`: writes markdown to disk, upserts `artifacts` row (increments version on re-run)
- `read_artifact`: reads file from disk by filename
- `load_artifacts`: reads all current artifacts for a project (latest version of each role)
- `save_review_report`: writes `review_report.json` to disk + upserts `review_issues` rows
- `project_dir(project_id)`: returns the project's output directory path

### Event Bus (`engine/event_bus.py`)
- In-memory asyncio pub/sub: one `asyncio.Queue` per project subscriber
- `publish(event)`: fans out to all subscribers + persists to `project_events`
- `subscribe(project_id)`: async generator; used by SSE route
- `close_project(project_id)`: sends sentinel to unblock all subscribers

---

## 4. Agent Execution

All agents share `BaseAgent` (`agents/base.py`):

```python
# Core call pattern
cmd = ["claude", "-p", user_message,
       "--system-prompt", system_prompt,
       "--model", AGENT_MODEL,
       "--tools", "",        # disabled — text/JSON output only
       "--output-format", "json",
       "--no-session-persistence"]

# Structured output adds:
cmd += ["--json-schema", json.dumps(schema)]
```

`ANTHROPIC_API_KEY` is removed from the subprocess environment before every call.

**Lead Agent** (`agents/lead.py`):
- `plan_stage1(idea)` → `WavePlan` (structured output)
- `chat(history, user_message, persona)` → `ChatReply` (parses markers from text output)
  - Markers: `BRIEF: ... BRIEF_READY`, `NOTE_QUEUED: <text>`, `REVISION_REQUEST: <instruction>`
  - Three system prompts, selected by persona: `shaper`, `narrator`, `refiner`

**Doc Worker Agent** (`agents/worker.py`):
- One instance per role; `produce_doc(idea, prior_artifacts, rework_feedback)` → markdown string
- Builds user message from idea + relevant prior artifacts (per `CONTEXT_DEPS`) + optional rework feedback

**Reviewer Agent** (`agents/reviewer.py`):
- `review(idea, artifacts, user_notes)` → `ReviewReport` (structured output)
- Receives all 8 artifacts; checks cross-document consistency + user note incorporation

---

## 5. Shared Patterns

### Base Classes
- `BaseAgent`: all agents inherit from this; provides `complete()`, `complete_with_usage()`, `structured()`, `tool_call()`
- `CLIError`: raised on non-zero exit or error envelope from the CLI

### Common Response Shapes
- All list endpoints return plain dicts (no Pydantic wrappers on responses)
- Chat endpoint returns `ChatResponse` Pydantic model with explicit boolean/nullable fields
- Error format: FastAPI default `{"detail": "..."}` with appropriate HTTP status

### Event Types (`models/events.py`)
```
project:created   project:planned   project:completed   project:failed
wave:started      wave:completed
task:started      task:completed    task:error
artifact:created
review:approved   review:needs_rework
```

### Cost Accumulation
- Every `complete_with_usage` call returns `(text, cost_usd)`
- Chat route: `_add_cost_cents(project_id, cost_usd)` after each Lead call
- Wave engine: cost accumulation for doc agents is a planned improvement (currently only chat tracks cost)

---

## 6. Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_CONCURRENT_AGENTS` | `3` | Semaphore cap for parallel agents within a wave |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Model passed to `--model` flag |
| `OUTPUT_DIR` | `backend/output` | Root for artifact files |
| `DB_PATH` | `data/orchestrator.db` | SQLite file location |
| `BACKEND_PORT` | `8000` | Uvicorn port |

---

## 7. Error Handling

| Scenario | Behavior |
|----------|----------|
| Agent CLI exits non-zero | `CLIError` raised; task marked `error`; wave marked `failed`; Stage 1 aborts |
| Wave has any agent failure | Project transitions to `failed`; remaining waves skip |
| `/revise` on non-`stage1_done` | `409 Conflict` |
| `/launch` on non-`shaping` | `409 Conflict` |
| Revision background task fails | `finally` always restores `stage1_done` |
| Artifact file missing | `404` from `/artifacts/{filename}` |
| Path traversal attempt | `400` — `os.path.basename` check enforced in artifact route |
