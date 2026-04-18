# Mini Orchestrator — Product Requirements Document

**Version**: 1.0  
**Status**: Stage 1 shipped · Stage 2 planned  
**Last updated**: 2026-04-16

---

## 1. Purpose

Mini Orchestrator takes a project idea and produces engineering design docs through a conversational AI pipeline, then (Stage 2) implements the product using TDD coding agents.

**Primary user**: solo developer or small team who wants to go from idea → reviewed design docs → working code without writing prompts from scratch.

**Key constraint**: runs entirely on the user's Claude Max subscription — no Anthropic API key, no extra billing.

---

## 2. User Journey

```
1. User opens the app, creates a new project
2. Chats with the Lead agent to shape the project brief
3. Lead proposes a brief → user approves → "Launch Stage 1" button appears
4. User launches → 8 specialist agents generate design docs in waves
5. Reviewer checks docs for consistency → rework cycle if needed
6. User reads docs, requests targeted revisions via chat
7. [Stage 2] Bridge synthesizes docs into agent configs
8. [Stage 2] Coding agents implement the product using TDD, sprint by sprint
9. User resolves human-action gates (approvals, external setup, design decisions)
10. Lead merges branches; master → main at sprint boundary with user approval
```

---

## 3. Features

### 3.1 Project Management

| ID | Feature | Status |
|----|---------|--------|
| PM-1 | Create a project (returns project ID, status = `shaping`) | Built |
| PM-2 | List recent projects (last 50, sorted by creation date) | Built |
| PM-3 | Load project detail: waves, tasks, events, cost | Built |
| PM-4 | Cost tracking: accumulate `cost_cents` from every CLI agent call | Built |
| PM-5 | Project status lifecycle: `shaping → planning → stage1_running → stage1_review → stage1_done → failed` | Built |

### 3.2 Shaping Phase (Lead Chat)

The user converses with the Lead agent to refine the idea before any docs are generated.

| ID | Feature | Status |
|----|---------|--------|
| SH-1 | Lead responds in **Shaper** persona: asks clarifying questions, proposes a brief | Built |
| SH-2 | When brief is ready, Lead emits `BRIEF_READY` marker → idea saved to project | Built |
| SH-3 | "Launch Stage 1" button appears once a brief exists | Built |
| SH-4 | Chat history persisted in SQLite (`lead_messages` table) | Built |
| SH-5 | Launching transitions project to `planning` and fires Stage 1 in background | Built |

### 3.3 Stage 1 — Doc Generation

Eight specialist agents generate engineering documents in dependency order.

| ID | Feature | Status |
|----|---------|--------|
| S1-1 | Lead plans waves using a structured tool call (`WavePlan`) | Built |
| S1-2 | Waves execute sequentially; agents within a wave run in parallel | Built |
| S1-3 | Concurrency cap: `MAX_CONCURRENT_AGENTS` (default 3, env-configurable) | Built |
| S1-4 | Eight doc agent roles: PRD, Architect, Backend, Frontend, Security, DevOps, UI Design, Screens | Built |
| S1-5 | Artifact visibility: each agent receives prior artifacts based on dependency rules (e.g. Backend sees PRD + Architecture) | Built |
| S1-6 | Artifacts saved to disk as markdown (`<output_dir>/<project_id>/<role>.md`) | Built |
| S1-7 | Artifact metadata indexed in SQLite (`artifacts` table) | Built |
| S1-8 | All agent calls strip `ANTHROPIC_API_KEY` from env — forces Max subscription path | Built |

**Artifact dependency order**:
```
PRD → Architect → Backend, Frontend (parallel)
                           ↓
                 Security (sees PRD + Arch + Backend)
                 DevOps   (sees PRD + Arch)
                 UI Design (sees PRD + Arch + Frontend)
                           ↓
                 Screens  (sees PRD + Frontend + UI Design)
```

### 3.4 Generated Document Quality

Each doc agent produces a document with a **Shared Patterns** section covering reusable abstractions within its domain. This is explicit output — not implied.

| Doc | Shared Patterns section covers |
|-----|-------------------------------|
| **BACKEND.md** | Base classes, shared middleware, common error shapes, event bus conventions, shared models/DTOs reused across endpoints |
| **FRONTEND.md** | Shared behavioral components (edit mode, modal system, drag handles), shared hooks, optimistic update patterns, layout wrappers |
| **ARCHITECTURE.md** | Cross-service data flow, auth flow, system boundaries — no code-level patterns |

Both Backend and Frontend agent prompts must explicitly request this section. See `backend/agents/prompts/stage1.py`.

### 3.6 Reviewer + Rework Cycle

| ID | Feature | Status |
|----|---------|--------|
| RV-1 | Reviewer agent reads all 8 artifacts, outputs `ReviewReport` (verdict + issues) | Built |
| RV-2 | `ReviewReport` persisted to disk (`review_report.json`) and indexed in SQLite (`review_issues`) | Built |
| RV-3 | If verdict = `needs_rework`: create rework wave, re-run flagged roles with reviewer feedback | Built |
| RV-4 | Max 1 rework cycle — second reviewer pass always terminates (no infinite loops) | Built |
| RV-5 | Project transitions: `stage1_running → stage1_review → stage1_done` (or `failed`) | Built |
| RV-6 | Visual "Reviewer running" row in board during `stage1_review` status | Built |

### 3.7 Lead Narration During Stage 1

While Stage 1 runs, the Lead stays in the chat panel and reports progress.

| ID | Feature | Status |
|----|---------|--------|
| NA-1 | Lead switches to **Narrator** persona when project enters `planning` / `stage1_running` | Built |
| NA-2 | Narrator reports wave progress, completed agents, next steps | Built |
| NA-3 | User can drop notes during narration (captured via `NOTE_QUEUED` marker) | Built |
| NA-4 | Queued notes stored in `notes_queue` table; absorbed into Reviewer's feedback | Built |
| NA-5 | PendingNotes panel shows queued chips; user can drop a note from the queue | Built |

### 3.8 User-Requested Revisions (Post Stage 1)

After all docs are done, the user can ask the Lead to revise specific documents.

| ID | Feature | Status |
|----|---------|--------|
| RR-1 | Lead switches to **Refiner** persona when project = `stage1_done` | Built |
| RR-2 | Refiner emits `REVISION_REQUEST` marker → surfaces as Apply CTA in chat | Built |
| RR-3 | User clicks Apply → `POST /api/projects/{id}/revise` with instruction + optional role list | Built |
| RR-4 | `/revise` transitions project to `stage1_running` synchronously before spawning background task (prevents concurrent revisions) | Built |
| RR-5 | `run_revision()` restores `stage1_done` in `finally` — guaranteed even on error | Built |
| RR-6 | Apply CTA cleared from chat when status transitions to `stage1_running` | Built |
| RR-7 | Default revision scope: PRD, Architect, Backend, Frontend, Security, UI Design, Screens (user can narrow via `affected_roles`) | Built |
| RR-8 | Revision wave stored with `is_revision = true` and `instruction` text | Built |
| RR-9 | User can dismiss revision suggestion (Skip button) | Built |

### 3.9 Artifact Versioning

Currently each revision overwrites the previous artifact file on disk. The `artifacts` table tracks a `version` counter but only the latest file is available.

| ID | Feature | Status |
|----|---------|--------|
| AV-1 | Artifacts saved with versioned filenames: `PRD_v1.md`, `PRD_v2.md`, etc. | Planned |
| AV-2 | ArtifactViewer shows version picker when `version > 1` | Planned |
| AV-3 | Diff view between any two versions of the same role | Planned |

### 3.10 Real-Time Event Stream

| ID | Feature | Status |
|----|---------|--------|
| ES-1 | SSE endpoint per project: `GET /api/projects/{id}/events` | Built |
| ES-2 | Events emitted for: `project:*`, `wave:*`, `task:*`, `artifact:*`, `review:*` | Built |
| ES-3 | Events persisted to `project_events` table for replay after reconnect | Built |
| ES-4 | Frontend merges historical events (from API) + live SSE events, deduplicates by timestamp+type | Built |
| ES-5 | Frontend auto-reconnects SSE on disconnect | Built |

### 3.11 Frontend: Board

| ID | Feature | Status |
|----|---------|--------|
| BRD-1 | Wave cards expand/collapse; running/error waves default expanded | Built |
| BRD-2 | Task cards show role badge, status chip, error text | Built |
| BRD-3 | Click task card → ArtifactViewer modal (markdown rendered) | Built |
| BRD-4 | Rework waves labeled "Rework wave" with ↻ badge | Built |
| BRD-5 | Revision waves labeled "User revision wave" with ✎ badge + instruction text | Built |
| BRD-6 | Multiple revision waves grouped under collapsible "User revisions (N)" divider | Built |
| BRD-7 | ShapingBoard shown while project is in `shaping` status | Built |
| BRD-8 | Reviewer running row shown while project is in `stage1_review` | Built |

### 3.12 Frontend: Chat Panel

| ID | Feature | Status |
|----|---------|--------|
| CH-1 | Message history with role-differentiated bubbles (user / assistant) | Built |
| CH-2 | Composer with send-on-enter | Built |
| CH-3 | Phase label above chat ("Shaping the brief", "Stage 1 running", etc.) | Built |
| CH-4 | "Launch Stage 1" button below chat when brief is ready and project is shaping | Built |
| CH-5 | Revision suggestion CTA: Apply button (sends instruction) + Skip button (dismisses) | Built |
| CH-6 | Sending indicator during agent reply | Built |
| CH-7 | Markdown rendering in chat bubbles | Built |

### 3.13 Frontend: Timeline

| ID | Feature | Status |
|----|---------|--------|
| TL-1 | Vertical timeline of all project events | Built |
| TL-2 | Review report expandable inline (issues + verdict) | Built |
| TL-3 | Connected/disconnected SSE indicator | Built |
| TL-4 | Timeline hidden during shaping phase | Built |

### 3.14 Frontend: General

| ID | Feature | Status |
|----|---------|--------|
| GEN-1 | Dark / light mode toggle (persisted via localStorage) | Built |
| GEN-2 | Project list: pick existing or create new | Built |
| GEN-3 | Cost indicator in header: "0 paid · ~$X.XX API equiv" | Built |
| GEN-4 | Stage tabs: Documents (active) / Code (disabled until Stage 2) | Built |
| GEN-5 | Back button → project list | Built |

---

## 4. Stage 2 — Planned (Not Built)

### 4.1 Bridge: Config Generator

Synthesizes Stage 1 artifacts into agent configuration for the output project.

| ID | Feature |
|----|---------|
| BR-1 | Config Generator agent reads all 8 docs, produces `CLAUDE.md` for the output project |
| BR-2 | Generates `.claude/settings.json` with permissions + auto-approve rules |
| BR-3 | Generates per-role instruction files (`backend-agent.md`, `frontend-agent.md`, etc.) |
| BR-4 | Creates `master` branch off `main` in the output repo |
| BR-5 | Determines `MAX_CONCURRENT_AGENTS` for Stage 2 based on project scope (estimated task count from PRD) and user's declared subscription tier (`max` / `api`); emits value into `.claude/settings.json` |

### 4.2 Task Planning

| ID | Feature |
|----|---------|
| TP-1 | Lead breaks PRD into tasks (dependency DAG) via structured tool call |
| TP-2 | Tasks stored as JSON on disk (`tasks/sprint-N/task-NNN.json`) and indexed in SQLite |
| TP-3 | Task fields: id, title, description, design, acceptance_criteria, notes, status, assignee, branch, depends_on |
| TP-4 | Sequential task IDs (task-001, task-002); Lead is sole creator |
| TP-5 | "Ready-front" readiness check: tasks whose dependencies are all `done` become runnable |

### 4.3 TDD Execution Loop

| ID | Feature |
|----|---------|
| TDD-1 | Test Agent writes tests first (acceptance criteria → test file), commits to agent branch |
| TDD-2 | Code Agent implements against test file, commits to agent branch |
| TDD-3 | Tests run automatically; green = merge to master; red = iterate |
| TDD-4 | Max retries per task; failure triggers handoff to Lead |
| TDD-5 | Lead merges feature branch → `master` when tests green |
| TDD-6 | Lead merges `master` → `main` at sprint boundary (requires user approval) |

### 4.4 Handoff System

| ID | Feature |
|----|---------|
| HO-1 | Agent creates `handoff-NNN.json` when blocked (bug, scope change, missing info) |
| HO-2 | Lead reads handoff, creates new task or routes to human review |
| HO-3 | Handoff stored in `tasks/unassigned/` |

### 4.5 Crash Recovery

| ID | Feature |
|----|---------|
| CR-1 | Agents write heartbeat timestamp to task JSON every 30s |
| CR-2 | Engine detects stale agents (>120s) and respawns |
| CR-3 | New instance reads `notes.next` from task JSON to resume |
| CR-4 | Backend crash recovery: rebuild SQLite from disk JSON, resume wave engine |

### 4.6 Human Action Cards

| ID | Feature |
|----|---------|
| HA-1 | Three types: approval gate, external setup, design decision |
| HA-2 | Board: human cards are draggable (Blocked → Done to resolve) |
| HA-3 | Dependent tasks blocked until human card resolved |
| HA-4 | Expanded card: description, options to choose (design decisions), context |

---

## 5. Non-Goals

- Multi-user / team support (single-user tool)
- Cloud hosting or SaaS deployment
- Support for models other than Claude (all agents use Claude CLI)
- Automated testing of AI-generated doc quality (reviewer is AI; human is final judge)
- Rollback of generated code (user owns the output repo and git history)

---

## 6. Constraints

- All agent work shells out to `claude -p` CLI — requires Claude Code CLI installed and logged in with Max plan
- No Anthropic API key needed (and explicitly stripped from env to prevent accidental use)
- SQLite only — no external databases
- Stage 1 agents disabled for tools (`--tools ""`); Stage 2 coding agents will use full toolset

---

## 7. Agent Roles Reference

| Role | Document | Sees |
|------|----------|------|
| PRD | PRD.md | nothing (seed) |
| Architect | ARCHITECTURE.md | PRD |
| Backend | BACKEND.md | PRD, Architecture |
| Frontend | FRONTEND.md | PRD, Architecture |
| Security | SECURITY.md | PRD, Architecture, Backend |
| DevOps | DEVOPS.md | PRD, Architecture |
| UI Design | UI_DESIGN_SYSTEM.md | PRD, Architecture, Frontend |
| Screens | SCREENS.md | PRD, Frontend, UI Design |
| Reviewer | review_report.json | All 8 docs |
| Lead | — | All docs + chat history |

---

## 8. Project Statuses

| Status | Meaning |
|--------|---------|
| `shaping` | Chat-only; no Stage 1 yet |
| `planning` | Launch triggered; Lead planning waves |
| `stage1_running` | Waves executing (also set during revision) |
| `stage1_review` | Reviewer agent running |
| `stage1_done` | All docs complete and reviewed |
| `failed` | Unrecoverable error during Stage 1 |
