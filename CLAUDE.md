# Mini Orchestrator

## What is this?

A mini AI orchestration system that takes a project idea and builds the entire product through two stages:
1. **Stage 1 (Planning)**: Generates engineering docs (PRD, Architecture, Backend, Frontend, Security, etc.) via specialized AI agents, reviews for consistency
2. **Bridge**: Synthesizes docs into CLAUDE.md and agent config files
3. **Stage 2 (Execution)**: Breaks PRD into sprint tasks, coding agents build the product via Claude Code CLI with TDD

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite, Anthropic Claude API
- **Frontend**: React (Vite), CSS with metallic color palette
- **Agent execution**: Claude Code CLI (Stage 2 coding agents)
- **Persistence**: JSON files (source of truth) + SQLite (UI queries)

## Project Structure

```
backend/          Python FastAPI backend
  agents/         Agent classes + system prompts
  engine/         Wave engine, artifact store, CLI manager
  models/         Pydantic models
  routes/         API endpoints + SSE
frontend/         React board UI
  src/components/ Board, TaskCard, LeadChat, etc.
tasks/            JSON task files (runtime, gitignored)
data/             SQLite DB (runtime, gitignored)
docs/design/      HTML UI mockups (design reference)
```

## Key Architecture Decisions

- **Blackboard pattern**: Agents never communicate directly. All state flows through JSON files + SQLite.
- **Lead agent**: Claude API only (never codes). Coordinates, plans sprints, manages handoffs, merges branches.
- **Coding agents**: Claude Code CLI sessions, one branch per agent.
- **TDD**: Test agent writes tests first, code agent implements, tests must pass.
- **Task IDs**: Sequential (task-001, task-002). Lead is sole creator.
- **Crash recovery**: State lives in files, not memory. Process monitoring + heartbeat for agent health.

## Conventions

- Agent system prompts live in `backend/agents/prompts/` as Python files
- BaseAgent in `backend/agents/base.py` — all agents use this async Claude API loop
- SSE events use `event_type:data` format (e.g., `task:completed`)
- Task JSON follows the 5-field payload: title, description, design, acceptance_criteria, notes
- Color palette: metallic (gold, rose gold, teal, purple, sky blue)

## Git Workflow (strict)

Three-tier branching — **the same rule applies to this repo and to every project the orchestrator generates**:

```
feature/<task>  →  master (integration)  →  main (stable, public)
```

- **Never commit directly to `main`.** `main` is the public-facing branch and only receives merges from `master` after integration is verified.
- Every piece of work starts on a feature branch cut from `master` (e.g. `feature/stage1-pipeline`, `fix/wave-engine-race`).
- Merge feature → `master` when the work is complete and (for Stage 2) tests pass.
- Merge `master` → `main` only at a clean checkpoint (sprint boundary, milestone) and only with explicit user approval.
- The Lead agent is the sole merger for generated projects. Coding agents never merge.

The Config Generator (Bridge step) must propagate this rule into every generated project's `CLAUDE.md` **and** into each per-role agent instruction file, so coding agents see it in their immediate context and don't accidentally branch off or merge into `main`.
