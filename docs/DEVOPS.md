# Mini Orchestrator — DevOps

**Version**: 1.0  
**Last updated**: 2026-04-16

---

## 1. Environments

Single environment: **local developer machine**. No staging, no cloud. This is a personal tool; it runs on your laptop.

| Thing | Dev |
|-------|-----|
| Backend | `uvicorn backend.main:app --port 8000 --reload` |
| Frontend | `cd frontend && npm run dev` (Vite, port 5173) |
| DB | `data/orchestrator.db` (SQLite, auto-created) |
| Artifacts | `backend/output/<project_id>/` (gitignored) |

---

## 2. Configuration

All config is loaded from `.env` via `python-dotenv` in `backend/config.py`.

| Variable | Default | Notes |
|----------|---------|-------|
| `MAX_CONCURRENT_AGENTS` | `3` | Semaphore cap for parallel Stage 1 agents |
| `AGENT_MODEL` | `claude-sonnet-4-6` | Passed to `--model` on every CLI call |
| `OUTPUT_DIR` | `backend/output` | Root for generated artifacts; override for tests |
| `DB_PATH` | `data/orchestrator.db` | SQLite location |
| `BACKEND_PORT` | `8000` | Uvicorn port |
| `GITHUB_TOKEN` | *(empty)* | Reserved for Stage 2 repo operations |

`.env.example` documents all variables. `.env` is gitignored.

**Critical**: `ANTHROPIC_API_KEY` must NOT be set (or is stripped at runtime). The app uses Claude Max subscription via `claude` CLI — an API key would cause auth failures.

---

## 3. Dependencies

### Backend
Managed via `pyproject.toml` / `requirements.txt`. Core deps:
- `fastapi`, `uvicorn[standard]`
- `aiosqlite`
- `sse-starlette`
- `pydantic`
- `python-dotenv`

Install: `python -m venv venv && ./venv/bin/pip install -r requirements.txt`

### Frontend
Managed via `package.json`. Core deps:
- `react`, `react-dom`
- `react-markdown`
- `vite`, `@vitejs/plugin-react`
- `typescript`

Dev deps: `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `jsdom`

Install: `cd frontend && npm install`

### External Requirement
`claude` CLI must be installed and logged in with a Max plan account.
Check: `claude --version && claude -p "ping" --output-format json`

---

## 4. Build

### Frontend production build
```bash
cd frontend && npm run build
# outputs to frontend/dist/
```

### Backend — no build step
Python runs directly from source. The Vite `dist/` output would be served by a static file server or mounted in FastAPI for production, but currently the dev server handles this.

---

## 5. CI (`github/workflows/ci.yml`)

Three jobs on push/PR to `main` or `master`:

| Job | Steps |
|-----|-------|
| `backend` | `ruff check` + `pytest tests/backend` with coverage |
| `frontend` | `tsc --noEmit` + `vitest run` + `npm run build` |
| `precommit` | Runs `scripts/precommit.sh` against the commit diff |

---

## 6. Pre-commit Hook (`scripts/precommit.sh`)

Wired via `.git/hooks/pre-commit`. **Blocks** on:
- Junk files (`.DS_Store`, `*.pyc`, `*.log`, `.env` variants)
- Likely secrets (`sk-ant-*`, `ghp_*`, AWS keys, PEM keys)
- `.gitignore`-listed files staged with force-add
- Staged `.py` files that fail `python -m py_compile`
- Staged `.ts`/`.tsx` if `tsc --noEmit` fails

**Warns** (non-blocking) on:
- Unknown top-level entries (update `ALLOWED_TOP` in the script)
- `backend/` changes without touching `CLAUDE.md` or `docs/`

Bypass: `git commit --no-verify` (document the reason in the commit message).

---

## 7. Observability

**Backend logs**: uvicorn stdout. `--log-level warning` reduces noise during normal runs. Stage 1 errors surface via `task:error` SSE events.

**Frontend**: browser console. SSE connection status shown in Timeline component.

**Smoke runner**: `./venv/bin/python -m tests.run_smoke` — spins a full Stage 1 run, writes all output to `tests/smoke_runs/<project-id>/`. Diagnostic only, no assertions.

No metrics, no traces, no external logging infrastructure — out of scope for a local-only tool.

---

## 8. Dev Workflow

```bash
# 1. Start backend (always use --reload)
OUTPUT_DIR=tests/smoke_runs ./venv/bin/uvicorn backend.main:app \
  --port 8000 --reload --log-level warning

# 2. Start frontend
cd frontend && npm run dev

# 3. Run backend tests
./venv/bin/pytest tests/backend -v

# 4. Run frontend tests
cd frontend && npm test

# 5. Smoke run (full Stage 1, uses subscription quota)
./venv/bin/python -m tests.run_smoke "your idea here"
```

---

## 9. Data Management

- `data/orchestrator.db` — delete to reset all project metadata
- `backend/output/` — delete to remove all generated artifacts
- Both are gitignored; there is no migration rollback

Schema is forward-only: `init_db()` runs `CREATE TABLE IF NOT EXISTS` + `_ensure_column` / `_drop_column_if_exists` on startup. Safe to run repeatedly on an existing DB.
