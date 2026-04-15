# Mini Orchestrator

## What is this?

A mini AI orchestration system that takes a project idea and builds the entire product through two stages:
1. **Stage 1 (Planning)**: Generates engineering docs (PRD, Architecture, Backend, Frontend, Security, etc.) via specialized AI agents, reviews for consistency
2. **Bridge**: Synthesizes docs into CLAUDE.md and agent config files
3. **Stage 2 (Execution)**: Breaks PRD into sprint tasks, coding agents build the product via Claude Code CLI with TDD

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLite
- **Frontend**: React (Vite), CSS with metallic color palette
- **Agent execution**: Claude Code CLI for **all** agents — Lead, Stage 1 doc agents, and Stage 2 coding agents alike. Every call shells out to `claude -p ...` and consumes the user's Claude subscription (Max plan). No Anthropic API key is required.
- **Persistence**: JSON files (source of truth) + SQLite (UI queries)

## Project Structure

```
backend/              Python/FastAPI orchestrator
  agents/
    base.py           shared Claude-CLI subprocess loop
    lead.py           Lead: plans waves (tool call)
    worker.py         DocWorkerAgent: one per doc role
    reviewer.py       cross-doc consistency check (structured output)
    prompts/stage1.py system prompts for all 10 roles
  engine/
    wave_engine.py    sequential waves + parallel within + rework cycle
    event_bus.py      in-memory asyncio pub/sub for SSE
    artifact_store.py disk writer + SQLite index
  models/
    project.py        Pydantic: Project, Wave, DocTask, Artifact, ReviewReport
    events.py         SSE event type strings + Event wrapper
  routes/
    projects.py       POST/GET project + review
    artifacts.py      list metadata + read content from disk
    events.py         SSE stream per project
  main.py             FastAPI app + lifespan hook (init_db, bus)
  config.py           env-loaded settings
  database.py         SQLite schema + forward-only migrations
  run_stage1.py       CLI entry point
  output/             real-run artifacts (gitignored)

frontend/             React + TypeScript + Vite
  src/
    api/client.ts     typed REST wrapper
    components/       Board, ProjectForm, ActivityPanel, ReviewPanel,
                      ArtifactViewer, StageTabs
    hooks/            useTheme, useProject, useEventStream
    labels.ts         user-facing strings (roles, statuses, phases)
    App.tsx, main.tsx, styles.css
  index.html, package.json, tsconfig.json, vite.config.ts

docs/
  plan.md             full system plan — source of truth for architecture
  design/             HTML mockups (metallic palette reference)

tests/
  run_smoke.py        end-to-end smoke runner
  smoke_runs/         per-run outputs (contents gitignored)

scripts/
  precommit.sh        pre-commit hygiene check (wired via .git/hooks/pre-commit)

data/                 SQLite DB (gitignored, created at runtime)
```

Anything new at the top level requires updating `ALLOWED_TOP` in `scripts/precommit.sh` — the hook warns on unknown entries.

## Key Architecture Decisions

- **Blackboard pattern**: Agents never communicate directly. All state flows through JSON files + SQLite.
- **Disk is the source of truth, SQLite is an index.** Generated artifacts (markdown docs, review reports, Stage 2 task/handoff JSONs) live on disk under `<output_dir>/<project_id>/`. SQLite (`data/orchestrator.db`) holds metadata-only rows so the UI can cheaply list + filter. **Never store content bodies in SQLite** — only ids, foreign keys, filenames, status flags, timestamps. Chat/notes are the one exception: they're small structured data, so `lead_messages` and `notes_queue` hold everything in SQLite with no disk mirror.
- **Conversational Lead spans the project lifecycle.** A project starts in `shaping` status (no Stage 1 yet) while the user and Lead converse to produce a brief. The same chat continues into `planning`/`stage1_*` where the Lead narrates progress and accepts notes, and into `stage1_done` where the Lead accepts revision requests. Persona switches via system prompt (`shaper` / `narrator` / `refiner`) — same agent, same chat history. The Lead emits structured markers (`BRIEF:…BRIEF_READY`, `NOTE_QUEUED:`, `REVISION_REQUEST:`) that the orchestrator parses to drive project state transitions.
- **Claude CLI for every agent**: Every Lead/doc/reviewer/coder call shells out to `claude -p` with `--system-prompt`, `--model`, `--tools ""` (disabled), and `--output-format json`. Structured outputs use `--json-schema`. This lets the orchestrator run entirely on the user's Max subscription.
- **Lead agent**: never codes. Coordinates, plans sprints, manages handoffs, merges branches. Still a dedicated role — just executed via the CLI like everyone else.
- **Coding agents**: Claude Code CLI sessions, one branch per agent.
- **TDD**: Test agent writes tests first, code agent implements, tests must pass.
- **Task IDs**: Sequential (task-001, task-002). Lead is sole creator.
- **Crash recovery**: State lives in files, not memory. Process monitoring + heartbeat for agent health.

## Conventions

- Agent system prompts live in `backend/agents/prompts/` as Python files
- BaseAgent in `backend/agents/base.py` — all agents spawn the `claude` CLI via `asyncio.create_subprocess_exec`. It exposes `complete()` (text) and `structured()` (JSON-schema validated)
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

## Pre-commit hygiene

Every commit runs `scripts/precommit.sh` via `.git/hooks/pre-commit`. The hook **blocks** commits that include:

- Junk files (`.DS_Store`, `*.pyc`, `__pycache__/`, `*.log`, `*.tmp`, `*.swp`, `*.bak`, `~`-suffixed backups, `.env` and its variants except `.env.example`)
- Likely secrets (`sk-ant-*`, `ghp_*`, `gho_*`, `github_pat_*`, AWS access keys, `aws_secret_access_key` lines, PEM private keys)
- Files that match `.gitignore` but were force-added
- Staged `.py` files that fail `python -m py_compile`
- Staged `.ts`/`.tsx` under `frontend/src/` if `tsc --noEmit` fails

And **warns** (non-blocking) on:

- Unknown top-level entries (update `ALLOWED_TOP` in the script if intentional)
- `backend/` changes without a touch to `CLAUDE.md` or `docs/plan.md` — soft nudge to keep docs fresh

The hook is a 3-line shim at `.git/hooks/pre-commit` that delegates to `scripts/precommit.sh` — the script is the source of truth, edit it there. Bypass once with `git commit --no-verify` only when there's a real reason, and explain the reason in the commit message.

## Testing

- **End-to-end smoke**: `./venv/bin/python -m tests.run_smoke [optional idea]` — spins Stage 1 against a short project idea and writes to `tests/smoke_runs/<project-id>/`. Diagnostic, no assertions; inspect the output by hand.
- **No unit tests yet.** Stage 1 output is non-deterministic (live CLI calls), so assertions on content are brittle. Phase 5 will add unit tests for the deterministic pieces (DAG planner, dependency-cycle detection, artifact store round-trips, event-bus fan-out).

## Skills

Available Claude Code skills to use when appropriate:

- **`claude-api`** — when building code that calls the Anthropic SDK directly. (We used it briefly for Phase 2 before pivoting to the CLI; rarely needed now.)
- **`simplify`** — invoke after any non-trivial code change to review for reuse, quality, efficiency. Default on for multi-file PRs.
- **`update-config`** — for changes to `.claude/settings.json` / `settings.local.json` (hooks, auto-approve permissions, env vars).
- **`loop`** — for polling or recurring tasks during development (e.g., tail a log for errors).
- **`schedule`** — for scheduled remote agents.
- **`keybindings-help`** — for keyboard shortcut customization.

Default to using `simplify` when the current change touches more than one file; skip on pure doc edits.
