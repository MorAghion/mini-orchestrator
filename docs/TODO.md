# Mini Orchestrator — Roadmap

Living TODO. `[x]` = done and merged to `master` (or later). `[ ]` = pending.
This file is the quick-reference snapshot across phases. The deep
architectural details live in [plan.md](plan.md).

**Last updated:** 2026-04-15
**Current phase:** 4.1 — Conversational Lead + right-panel redesign

---

## Phase 1 — Project setup + core scaffolding  ✅

- [x] GitHub repo (`MorAghion/mini-orchestrator`) + three-tier branch model (`feature/* → master → main`)
- [x] Project structure (`backend/`, `frontend/`, `docs/`, `tests/`)
- [x] `.gitignore`, `.env.example`, `CLAUDE.md`
- [x] Python deps, FastAPI skeleton, SQLite init
- [x] Initial commit pushed (`6271ab2`)

## Phase 2 — Stage 1 doc generation pipeline  ✅

- [x] Pydantic domain models (Project, Wave, DocTask, Artifact, ReviewReport)
- [x] SQLite schema + forward-only migrations
- [x] `BaseAgent` — async Claude Code CLI loop (subprocess + JSON envelope + `--json-schema`)
- [x] System prompts for all 10 roles (Lead, 8 doc agents, Reviewer)
- [x] `LeadAgent.plan_stage1()` — forced tool call emits `WavePlan`
- [x] `DocWorkerAgent` — one class, configured per role
- [x] `ReviewerAgent` — structured output via `--json-schema`
- [x] Wave engine: sequential waves + `asyncio.gather` within + `Semaphore(MAX_CONCURRENT_AGENTS)`
- [x] One rework cycle after review, flagged roles only
- [x] Artifact store (disk = source of truth, SQLite = metadata index)
- [x] CLI runner: `python -m backend.run_stage1 "idea"`
- [x] Full end-to-end run verified against a real idea

## Phase 3 — REST API + SSE  ✅

- [x] In-memory `EventBus` (asyncio pub/sub, per-project fan-out)
- [x] Wave engine emits events at every transition (project/wave/task/artifact/review)
- [x] `POST /api/projects` — kicks off Stage 1 in the background
- [x] `GET /api/projects` — list recent runs
- [x] `GET /api/projects/{id}` — project + waves + tasks
- [x] `GET /api/projects/{id}/review` — review report JSON
- [x] `GET /api/projects/{id}/artifacts` — metadata list
- [x] `GET /api/projects/{id}/artifacts/{filename}` — markdown body from disk
- [x] `GET /api/projects/{id}/events` — SSE live stream
- [x] `main → 103d43d` promoted (milestone 1)

## Phase 4 — React frontend  ✅ (initial) + 🟡 (UX polish branch)

### 4.0 Scaffold and initial UI  ✅ (merged)
- [x] Vite + React + TypeScript scaffold
- [x] Typed API client + `useEventStream` + `useProject` hooks
- [x] `ProjectForm` (single textarea — placeholder shape)
- [x] `Board` — waves + cards with role-colored left border
- [x] `ActivityPanel` — one-way SSE feed
- [x] `ReviewPanel` — verdict + issue list
- [x] `ArtifactViewer` — modal with markdown (initially as preformatted text)
- [x] Vite dev proxy `/api/* → :8000`

### 4.1 Conversational Lead + right-panel redesign  🟡 in progress

**Backend (4.1a):**
- [x] New project status `shaping` (draft exists before Stage 1 launches)
- [x] `lead_messages` table (persistent chat per project)
- [x] `notes_queue` table (user-dropped notes awaiting absorption into review)
- [x] `LeadAgent.chat()` with three personas:
    - [x] Shaper — asks clarifying questions pre-run, maintains draft brief
    - [x] Narrator — reports progress during run, queues user notes
    - [x] Refiner — accepts revision requests post-run, triggers targeted rework
- [x] `POST /api/projects/{id}/chat` — non-streaming for now (returns JSON once Lead finishes); streaming deferred
- [x] `POST /api/projects/{id}/launch` — transition `shaping → planning`
- [x] `POST /api/projects/{id}/notes` + `DELETE /.../notes/{note_id}` + `GET /.../notes`
- [x] Accumulate `total_cost_usd` from CLI envelope into `projects.cost_cents`

**Frontend (4.1b):**
- [x] Home screen: "+ Start new project" creates a shaping project and jumps into chat
- [x] `Chat` component — message list + composer + animated typing indicator + markdown rendering for Lead bubbles
- [x] `PendingNotes` strip — chips with click-to-drop, hidden when empty
- [x] Right panel re-layout: Chat (top) · PendingNotes · Review · Activity (collapsed)
- [x] "Launch Stage 1 →" CTA surfaces above the composer when the Lead has set the brief
- [x] Cost indicator in header ("$0.09 equiv · free under Max")

**Post-run + polish (4.1c):**
- [ ] Revision requests trigger a targeted rework wave (distinct label from reviewer-rework)
- [ ] Mobile-responsive layout for chat-first home screen

### 4.2 Cleanup + promote  ✅ (partial — commits on `feature/frontend-ux`)
- [x] Light theme fix (matches `docs/design/board_split.html` exactly)
- [x] Plain-English labels throughout (`Stage 1 → "Documents generation"`)
- [x] Card status chips + collapsible completed waves + clickable full-row + ESC-closes-modal
- [x] Rework wave labeled (`is_rework` column + migration + UI badge)
- [x] Markdown rendering via `react-markdown` + `remark-gfm`
- [x] Stage tabs at top of board (`Documents` active, `Code` disabled)
- [x] Side-panel backgrounds match sprint-row cream
- [x] Artifact cleanup — disk = source of truth, drop `artifacts.content` column
- [x] Pre-commit hook + CLAUDE.md project contract
- [ ] Merge `feature/frontend-ux` → `master`
- [ ] Promote `master` → `main` once Phase 4.1 stabilizes (milestone 2)

## Phase 5 — Bridge + Stage 2 foundation

- [ ] Config Generator agent (generates `CLAUDE.md` + `.claude/settings.json` + per-role agent instructions for **generated** projects)
- [ ] Stage 2 data model:
    - [ ] `stage2_tasks` SQLite table (metadata index only)
    - [ ] `task_deps` SQLite table (dependency graph)
    - [ ] `handoffs` SQLite table (metadata index only)
    - [ ] Disk layout: `tasks/sprint-N/task-NNN.json` + `tasks/unassigned/handoff-NNN.json`
- [ ] PRD → task DAG breakdown (Lead's new tool: reads PRD, emits sprint plan)
- [ ] Sequential task ID generator (`task-001`, `task-002` — Lead is sole creator)
- [ ] CLI manager: spawn/manage long-running Claude Code CLI sessions as coding agents
- [ ] Branch-per-agent git workflow (worktrees or branch switching)
- [ ] Heartbeat + crash-recovery plumbing (read `notes.next` to resume)

## Phase 6 — Stage 2 TDD execution

- [ ] Test Agent — writes tests first from acceptance criteria
- [ ] Code Agent — implements against tests via Claude Code CLI
- [ ] Test verification loop (green = done, red = retry, persistent red = handoff)
- [ ] Handoff system (agent creates handoff → Lead reassigns)
- [ ] Branch merging policy (Lead: feature → master on green; master → main at sprint boundary)
- [ ] Human action cards (drag-and-drop to resolve)
- [ ] Mid-run chat interjection (skip task, change approach, reassign)
- [ ] Stage 2 board view (hybrid kanban: sprint rows + Running/Blocked/Done columns inside active sprint)

## Phase 7 — Polish + ship

- [ ] README with architecture diagram, screenshots, demo GIF
- [ ] Error handling hardening (CLI retry, context budget, graceful degradation)
- [ ] **Humanize the Lead's chat voice** — currently reads too robotic
      (bullet-heavy replies, overly structured clarifying questions,
      "proposed brief" formal headers). Rewrite the three chat prompts
      (shaper/narrator/refiner) to feel like a thinking partner:
      looser prose, variable reply length, sparing use of bullets,
      warmer tone. Consider also whether the shaper's opener should be
      an open question instead of a two-question interview.
- [ ] Demo recording
- [ ] Blog post (ai-from-scratch chapter 19)
- [ ] GitHub polish (description, topics, social preview image)

---

## Cross-cutting / whenever

- [ ] Terminal chat wrapper (`python -m backend.chat <project-id>`) — same DB, power-user surface
- [ ] API-key-only fallback path (for users without a Claude subscription; pay-as-you-go)
- [x] **Testing infrastructure** — pytest/pytest-asyncio/httpx backend, vitest/RTL/jsdom frontend, ruff + py_compile in pre-commit, GitHub Actions CI (backend + frontend + precommit hygiene). 47 tests passing.
- [ ] Wave engine coverage — currently only exercised end-to-end via smoke runner. Mock `DocWorkerAgent` / `ReviewerAgent`, assert rework-role routing, parallel/sequential wave execution, semaphore gating.
- [ ] Replace `datetime.utcnow()` everywhere with `datetime.now(UTC)` (deprecation warnings suppressed in pytest config until then).
- [ ] Structured logging + event-trace observability
- [ ] Auto-approve rules in `.claude/settings.local.json` for safe read-only commands

---

## How to use this file

- Check a box (`- [ ]` → `- [x]`) the moment a task lands on `master`.
- New ideas: append under the right phase. If it's a big one, bump it to its own subsection.
- Commit TODO changes together with the code they reference, so the diff tells the story.


---

## Open question that pops - DO NOT DELETE:
1. can we add a feature that takes under consideration the user's subscription + project scope in order to determine the max number of agents working simultanuesly? this action could take place in the "bridge" part

2. which of the docs generated is responsible of the user's app-level architecture. for example, if the user has several screens in which they have an "edit mode" - the app can have 1 single edit mode component used by every screen. Where do we define these kinds of structures?