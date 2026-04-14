# Mini Orchestrator — Complete System Plan

## Context

A mini AI orchestration system that takes a project idea and **builds the entire product** through two stages: generating engineering docs, then coding it sprint-by-sprint with specialized AI agents. Inspired by Gastown (75k lines Go) but dramatically simpler. Presented as a portfolio piece on GitHub, LinkedIn, and the tech blog (chapter 19).

---

## System Overview

```
User inputs project idea
        │
   STAGE 1: PLANNING
        │  Lead → doc agents → Reviewer → rework (max 1 cycle)
        │  Output: PRD, ARCHITECTURE, BACKEND, FRONTEND, SECURITY,
        │          ENV, UI_DESIGN_SYSTEM, SCREENS
        │
   BRIDGE: CONFIG GENERATION
        │  Synthesize docs → CLAUDE.md + .claude/settings.json
        │  + per-role agent instruction files
        │
   STAGE 2: EXECUTION
        │  Lead breaks PRD into tasks (dependency DAG)
        │  Per sprint:
        │    Test Agent writes tests (TDD)
        │    Code Agents implement (Claude Code CLI, branch per agent)
        │    Tests verify → pass = done, fail = iterate
        │    Agents can create handoffs → Lead reassigns
        │    Human actions: drag-and-drop on board
        │
   COMPLETE when all PRD tasks done + tests passing
```

**Stack**: Python (FastAPI) + Claude API orchestrator, Claude Code CLI for coding agents, React (Vite) frontend, SQLite + JSON files for persistence

---

## Agent System

### Agent Types (not singletons — Lead spawns N instances)

| Agent | Stage 1 | Stage 2 | Tool | Notes |
|-------|---------|---------|------|-------|
| **Lead** | Plans doc waves | Breaks PRD into tasks, assigns sprints, manages handoffs, merges branches | Claude API | Coordinator only, never codes |
| **Architect** | ARCHITECTURE.md | Structural refactors | Claude Code CLI | |
| **PRD Writer** | PRD.md | — | Claude API | Stage 1 only |
| **Backend Dev** | BACKEND.md | APIs, DB, logic | Claude Code CLI | |
| **Frontend Dev** | FRONTEND.md + styling | Components, pages | Claude Code CLI | Also handles CSS/design tokens |
| **Security Analyst** | SECURITY.md | Auth, RLS, rate limiting | Claude Code CLI | |
| **DevOps** | ENV.md | Docker, CI/CD, env | Claude Code CLI | |
| **UI Designer** | UI_DESIGN_SYSTEM.md | — | Claude API | Stage 1 only |
| **Screen Designer** | SCREENS.md | — | Claude API | Stage 1 only |
| **Reviewer** | Cross-doc review | — | Claude API | Stage 1 only |
| **QA/Test Agent** | — | Writes tests (TDD), E2E | Claude Code CLI | |
| **Config Generator** | — | CLAUDE.md + settings | Claude API | Bridge step |

`MAX_CONCURRENT_AGENTS` configurable (default: 3). Wave engine uses semaphore.

---

## Task Types

### Stage 1 (Docs)
`prd` · `architecture` · `backend_doc` · `frontend_doc` · `security_doc` · `devops_doc` · `ui_design_doc` · `screens_doc` · `review`

### Stage 2 (Code)
`backend` · `frontend` · `architecture` · `security` · `devops` · `test` · `qa` · `human_action`

### Color Assignment (metallic palette)

| Type | Color | Hex |
|------|-------|-----|
| Backend | Metallic Teal | `#5AADA0` |
| Frontend | Rose Gold | `#C4907A` |
| Architecture | Metallic Purple | `#8A80B8` |
| Security | Deep Rose | `#B87A8A` |
| DevOps | Lavender Purple | `#9B8EC4` |
| QA/Test | Sky Blue | `#68A8D4` |
| Human Action | Amber Gold | `#E8C87A` |
| PRD | Warm Silver | `#A0988A` |
| Review | Light Purple | `#A898C4` |

**Left border = task type** (constant), **card visual state = status** (changes).

---

## Agent Communication: Blackboard Pattern

Agents never talk directly. All communication through JSON files + SQLite.

### Context Flow
```
Lead plans → tasks created (JSON + DB)
Wave engine dispatches → agent reads task JSON + prior artifacts
Agent works → updates task JSON notes field
Agent completes → artifact saved, task status updated
SSE event → frontend updates
```

### Which Agents See Which Artifacts (Stage 1)

| Agent | Sees |
|-------|------|
| PRD Writer | (none) |
| Architect | prd |
| Backend Dev | prd, architecture |
| Frontend Dev | prd, architecture |
| Security | prd, architecture, backend |
| DevOps | prd, architecture |
| UI Designer | prd, architecture, frontend |
| Screen Designer | prd, frontend, ui_design |
| Reviewer | ALL |

### Review + Rework (Stage 1)

Reviewer checks: API consistency, data model consistency, PRD coverage, security cross-check, naming consistency.

Output: JSON ReviewReport with `overall_verdict: "approved" | "needs_rework"`.

**Max 1 rework cycle.** If issues persist → `needs_human_review`, proceed anyway.

---

## Task JSON Structure

File: `/tasks/sprint-{N}/task-{NNN}.json`

IDs are **sequential** (task-001, task-002). Lead is sole creator, no collision risk.

```json
{
  "id": "task-003",
  "title": "Implement Auth API (JWT + OAuth)",
  "description": "Build auth endpoints: signup, login, token refresh, Google OAuth.",
  "design": "FastAPI + python-jose for JWT. OAuth via authlib. Httponly cookies.",
  "acceptance_criteria": [
    "POST /api/auth/signup creates user and returns JWT",
    "POST /api/auth/login validates credentials",
    "POST /api/auth/refresh rotates refresh token",
    "GET /api/auth/google initiates OAuth flow"
  ],
  "notes": {
    "completed": "DB schema for users table",
    "in_progress": "JWT token generation",
    "next": "OAuth callback, rate limiting",
    "blockers": "Supabase credentials (task-005)",
    "key_decisions": "Chose httponly cookies over localStorage"
  },

  "task_type": "backend",
  "status": "in_progress",
  "priority": 1,
  "sprint": 2,

  "assignee": "BE-1",
  "branch": "sprint2/backend-auth-api",
  "prd_ref": "US-003",

  "depends_on": ["task-001", "task-005"],
  "blocks": ["task-008"],
  "parent": "epic-auth",

  "artifacts": {
    "docs_context": ["PRD.md", "BACKEND.md", "SECURITY.md"],
    "files_changed": ["src/api/auth.py", "src/middleware/jwt.py"],
    "test_file": "tests/test_auth.py"
  },

  "created_at": "2026-04-14T10:00:00Z",
  "updated_at": "2026-04-14T10:45:00Z",
  "started_at": "2026-04-14T10:05:00Z",
  "completed_at": null,

  "history": [
    { "timestamp": "2026-04-14T10:05:00Z", "event": "status_changed", "from": "pending", "to": "in_progress", "actor": "Lead" }
  ]
}
```

### Handoff JSON

File: `/tasks/unassigned/handoff-{NNN}.json`

Created by agents mid-task, picked up by Lead who converts to a task.

```json
{
  "id": "handoff-001",
  "type": "bug",
  "title": "Login returns 500 on empty email",
  "description": "POST /api/auth/login crashes instead of returning 422.",
  "from_agent": "BE-1",
  "from_task": "task-003",
  "suggested_type": "qa",
  "severity": "medium",
  "context": {
    "file": "src/api/auth.py",
    "line": 47,
    "reproduction": "curl -X POST /api/auth/login -d '{\"email\": \"\"}'"
  },
  "status": "pending",
  "resolved_by_task": null,
  "created_at": "2026-04-14T10:30:00Z"
}
```

---

## Task Lifecycle

```
pending → running → done
                  → error (retry up to max, then stays error)
                  → blocked (agent discovers dependency)
blocked → pending (blocker resolved / human acts)
done    → flagged (reviewer finds issues)
flagged → running (rework)
```

Valid transitions enforced in code. Only the Lead changes statuses (except human_action cards).

---

## Human Actions

Three types: **approval gates**, **external setup**, **design decisions**.

Task field: `task_type: "human_action"`, `human_action_type: "approval" | "external_setup" | "decision"`.

**Board behavior**: Only tasks depending on the human action are blocked. Everything else continues.

**UI interaction**: Human cards are **drag-and-drop only**. Drag from Blocked → Done to resolve. Agent cards are read-only (move automatically via SSE).

For decision cards: click to open expanded view, choose option, then drag to Done.

---

## PRD Breakdown (How Lead Plans Sprints)

Lead reads PRD and produces a **dependency DAG**:

```
Infrastructure tasks (no deps) → Sprint 1
Core backend (depends on infra) → Sprint 2
Frontend (depends on backend APIs) → Sprint 3
Integration (depends on BE + FE) → Sprint 4
Polish (depends on integration) → Sprint 5
```

**"Ready front" model** (from beads): instead of manually assigning every task to a sprint, the engine asks "which tasks have all dependencies met?" Those are ready to run. As tasks complete, new ones become ready.

Lead can re-plan: move tasks between sprints, split large tasks, reassign after failures.

---

## TDD Flow (Stage 2)

Each sprint:
1. Lead creates test task (from PRD acceptance criteria)
2. Test Agent writes tests (Claude Code CLI, own branch off `master`)
3. Lead creates code task (depends on test task)
4. Code Agent implements (Claude Code CLI, own branch off `master`)
5. Tests run automatically → green = done, red = iterate
6. Lead merges agent branch → `master` when green
7. If agent can't fix → handoff → Lead reassigns
8. At sprint end (all sprint tasks green + cross-task checks pass) → Lead merges `master` → `main`

`main` always represents a verified end-of-sprint state. Agent work never touches `main` directly.

---

## Bridge: Claude Code Config Generation

After Stage 1 docs are approved, before Stage 2:

- **CLAUDE.md** — synthesized from all docs: project overview, tech stack, conventions, architecture rules, **git branch policy** (feature → master → main)
- **.claude/settings.json** — permissions, allowed tools, auto-approve patterns
- **Per-role instruction files** — `backend-agent.md`, `frontend-agent.md`, etc. with role-specific context
- **Branch scaffolding** — Config Generator creates the `master` branch off `main` and makes it the default working branch for Stage 2

Generated by Config Generator agent (or Lead).

---

## Persistence: JSON Files + SQLite

**JSON files** (agents read/write directly):
```
tasks/
  sprint-1/
    task-001.json
    task-002.json
  sprint-2/
    task-003.json
  unassigned/
    handoff-001.json
```

**SQLite** (mirrors JSON for UI queries):
- projects, waves, tasks, artifacts, review_issues tables
- Synced: JSON is source of truth, SQLite mirrors for fast queries/board UI

---

## Crash Recovery

**Principle**: State lives in files, not memory. Any component can restart and recover.

### Agent crash (CLI session dies)
- **Detection**: Process monitoring (instant) + heartbeat timeout (catches hangs, >120s stale)
- **Recovery**: Engine reads task JSON `notes` field → spawns new agent instance → resumes from `in_progress` / `next` fields. Branch has partial commits — new agent picks up from there.
- Agents write heartbeat timestamp to task JSON every 30s.

### Lead crash (API call fails)
- Lead is stateless between calls. Reads current state from JSON + SQLite each time.
- Failed planning call → retry. Wave plan only saved after successful completion.
- Mid-sprint crash → on restart, reads all task statuses and resumes.

### Backend crash (FastAPI dies)
- JSON files on disk are source of truth — nothing lost.
- On restart: scan `/tasks/` directory, rebuild SQLite state, resume wave engine.
- SSE connections drop → frontend auto-reconnects.

### Frontend crash (browser refresh)
- All state in backend. Frontend reconnects SSE, fetches state via `GET /api/projects/{id}`, board rebuilds.

---

## GitHub Repo Setup

### Branch model (both paths)

Three-tier workflow keeps AI-generated code out of `main` until integration is verified:

```
feature branches (one per agent/task)
        ↓ merged by Lead when tests green
master (integration — all sprint work lands here)
        ↓ merged by Lead at sprint boundaries, after cross-task checks pass
main (stable, public — only verified end-of-sprint states)
```

`main` is what a visitor to the repo sees. `master` is where integration happens. Agent branches are short-lived (one per task).

### Two paths:

**Path A: New project from scratch**
```
User submits idea + GitHub token
  → Create local git repo in output/{project}/
  → Create GitHub repo under user's account (gh CLI)
  → Initial commit on main: project idea + metadata
  → Create master branch off main (integration branch)
  → Stage 1: each doc committed to master as generated
  → Stage 2: agents branch off master, Lead merges to master on green, merges master→main at sprint boundaries
```

**Path B: Existing repo**
```
User submits idea + repo URL + GitHub token
  → Clone the repo
  → Create master branch off main (if not present)
  → Stage 1: docs committed to master (or /docs branch off master)
  → Stage 2: agents branch off master, same merge flow as Path A
```

ProjectForm UI: toggle "Start from scratch" vs "Add to existing repo" + URL field.

Config requires: `GITHUB_TOKEN` in `.env`.

---

## Lead Communication: Chat Panel + Activity Feed

Board has a **chat panel** (right side) where the Lead communicates:

- **Proactive updates**: "Sprint 2 started with 3 tasks", "Review found 2 issues", "BE-1 crashed, respawning"
- **User can type messages**: "Skip the OAuth task", "Change auth to sessions instead of JWT", "Why is Sprint 2 slow?"
- **Lead responds with context**: it has access to all task states, artifacts, history

The Lead is still a Claude API agent (not CLI) — the chat is a persistent conversation stored in SQLite. Activity feed events are interspersed with chat messages.

```
Board (left)              Lead Chat (right)
┌──────────────────┐     ┌──────────────────────┐
│ Sprint rows +    │     │ Lead: Sprint 2 started│
│ kanban...        │     │ with 3 tasks. BE-1    │
│                  │     │ and QA-1 running.     │
│                  │     │                      │
│                  │     │ Lead: ⚠ Need Supabase│
│                  │     │ creds. Created human  │
│                  │     │ action card.          │
│                  │     │                      │
│                  │     │ You: skip OAuth task  │
│                  │     │                      │
│                  │     │ Lead: Moving task-007 │
│                  │     │ to deferred.          │
│                  │     │                      │
│                  │     │ [Type a message...]   │
└──────────────────┘     └──────────────────────┘
```

---

## Board UI

### Layout: Hybrid (sprint rows + kanban inside active sprint)

- Completed sprints: collapsed row
- Active sprint: expanded into kanban columns (Running, Blocked, Done)
- Future sprints: collapsed with task names listed
- Stage 1 docs: collapsed row at top

### Color Palette: Metallic

- **Gold** (`#D4AF37`) — running state glow, progress bar
- **Rose Gold** (`#C4907A`) — frontend tasks
- **Metallic Teal** (`#5AADA0`) — backend tasks
- **Metallic Purple** (`#9B8EC4`) — devops
- **Sky Blue** (`#68A8D4`) — test/QA
- **Silver** (`#A0988A`) — neutral/muted

Light mode: warm cream (`#F5F2EB`), dark mode: lifted charcoal (`#1E1C22`).

### Card Interaction

- **Agent cards**: auto-move via SSE events. Read-only, click to view details.
- **Human cards**: drag-and-drop. Drag Blocked → Done to resolve.
- **Expanded card view**: shows full 5-field payload (title, description, design, acceptance criteria, handoff notes), dependencies, files changed, history.

### SSE Events

`project:created` · `project:planned` · `wave:started` · `wave:completed` · `task:started` · `task:completed` · `task:error` · `task:retrying` · `task:flagged` · `artifact:created` · `artifact:updated` · `review:approved` · `review:needs_rework` · `project:completed` · `project:needs_review` · `project:failed`

---

## Project Structure

```
mini-orchestrator/
├── README.md
├── CLAUDE.md                    # manually written for orchestrator dev
├── .env.example
├── .gitignore
│
├── backend/
│   ├── main.py                  # FastAPI app
│   ├── config.py                # settings, API keys, MAX_CONCURRENT_AGENTS
│   ├── database.py              # SQLite schema + sync from JSON
│   ├── requirements.txt
│   ├── models/
│   │   ├── project.py           # Pydantic models
│   │   └── events.py            # SSE event types
│   ├── agents/
│   │   ├── base.py              # BaseAgent (async Claude API loop)
│   │   ├── lead.py              # Lead agent (plans, assigns, merges)
│   │   ├── reviewer.py          # Reviewer agent
│   │   ├── config_generator.py  # Bridge: generates CLAUDE.md etc.
│   │   ├── registry.py          # Agent types → config
│   │   └── prompts/             # System prompts per agent type
│   ├── engine/
│   │   ├── wave_engine.py       # Wave execution, dispatch, ready-front
│   │   ├── artifact_store.py    # Read/write artifacts
│   │   └── cli_manager.py      # Spawn/manage Claude Code CLI sessions
│   ├── routes/
│   │   ├── projects.py          # REST endpoints
│   │   ├── artifacts.py         # Artifact endpoints
│   │   ├── tasks.py             # Task status updates (drag-and-drop)
│   │   ├── chat.py              # Lead chat (POST messages, GET history)
│   │   └── events.py            # SSE streaming
│   └── output/                  # Generated project output
│
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── api/client.js
│       ├── hooks/
│       │   ├── useProject.js
│       │   └── useEventStream.js
│       ├── components/
│       │   ├── ProjectForm.jsx      # new/existing repo toggle
│       │   ├── Board.jsx
│       │   ├── WaveColumn.jsx
│       │   ├── TaskCard.jsx       # drag-and-drop for human cards
│       │   ├── AgentBadge.jsx
│       │   ├── ArtifactViewer.jsx
│       │   ├── TaskDetail.jsx     # expanded card view
│       │   ├── ProgressBar.jsx
│       │   ├── ReviewPanel.jsx
│       │   └── LeadChat.jsx        # chat panel + activity feed
│       └── styles/index.css       # metallic palette, dark/light mode
│
├── tasks/                         # JSON task files (source of truth)
│   └── .gitkeep
│
├── data/                          # SQLite DB
│   └── .gitkeep
│
└── docs/
    └── design/                    # HTML mockups we created
        ├── board_split.html
        └── board_metallic.html
```

---

## Implementation Phases

### Phase 1: Project Setup + Core
- Create GitHub repo
- Project structure, .gitignore, .env.example, CLAUDE.md
- SQLite schema (`database.py`)
- BaseAgent class (async, from research-agent pattern)
- Config with .env support
- **Commit**: "Initial project structure"

### Phase 2: Stage 1 — Doc Generation
- Lead agent + wave plan tool
- Worker agents: PRD, Architect, Backend, Frontend, Security, DevOps, UI Designer, Screen Designer
- Wave engine (sequential waves, parallel tasks within)
- Artifact store (JSON + SQLite + disk)
- Reviewer + rework cycle
- **Commit**: "Stage 1: doc generation pipeline"

### Phase 3: API + SSE
- FastAPI routes (projects, artifacts, tasks)
- SSE streaming
- Wire engine → events
- **Commit**: "REST API + SSE events"

### Phase 4: React Frontend
- Vite + React setup
- Hybrid board (sprint rows + kanban)
- Lead chat panel (right side) + activity feed
- Metallic palette, dark/light mode
- SSE hook for live updates
- Expanded card view (5-field payload)
- Drag-and-drop for human cards
- ProjectForm: new project / existing repo toggle
- **Commit**: "React board UI"

### Phase 5: Bridge + Stage 2 Foundation
- Config Generator (CLAUDE.md, settings.json, agent files)
- PRD → task DAG breakdown (Lead)
- Task JSON file management
- CLI manager (spawn Claude Code sessions)
- Branch-per-agent git workflow
- **Commit**: "Bridge + Stage 2 task management"

### Phase 6: Stage 2 — TDD Execution
- Test Agent (writes tests from acceptance criteria)
- Code agents via Claude Code CLI
- Handoff system (agent creates handoff → Lead assigns)
- Test verification loop
- Branch merging
- **Commit**: "Stage 2: TDD coding pipeline"

### Phase 7: Polish
- README with architecture diagram + screenshots
- Error handling (retries, context budget)
- Demo recording
- **Commit**: "Portfolio-ready"

---

## Verification

1. **Stage 1**: Submit "Todo app with auth" → 8 docs generated → reviewer approves or triggers 1 rework → docs consistent
2. **Bridge**: CLAUDE.md generated from docs, contains project-specific rules
3. **Stage 2**: Lead creates sprint tasks → test agent writes tests → code agent implements → tests pass → branch merged
4. **Board**: Cards animate in real-time, human cards draggable, expanded view shows full task detail
5. **End-to-end**: Project idea → docs → code → working product
