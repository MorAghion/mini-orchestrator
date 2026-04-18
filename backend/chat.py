"""Terminal chat wrapper for the Lead agent.

Usage:
    python -m backend.chat <project-id>
    python -m backend.chat            # lists recent projects, then prompts

The web dashboard (uvicorn + React) can be open simultaneously — both surfaces
read/write the same SQLite DB.  Agent progress appears in the browser via SSE;
this terminal handles the Lead conversation.

Commands (prefix with /):
    /status   — show current project status + brief
    /notes    — list pending notes
    /launch   — transition shaping → planning and start Stage 1 in background
    /apply    — apply the most recent revision suggestion from the Lead
    /quit     — exit (Ctrl+C also works)

Note: /launch and /apply start background asyncio tasks.  Keep this terminal
open while they run — closing it kills the event loop and aborts in-flight agents.
The browser dashboard shows progress via SSE as normal.
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime

try:
    import readline  # noqa: F401  enables arrow keys + history on POSIX
except ImportError:
    pass

import aiosqlite

from backend.config import DB_PATH
from backend.database import init_db
from backend.engine.chat_store import add_note, append_message, list_notes, load_messages
from backend.models.project import ChatRole, NoteStatus, ProjectStatus

# ── ANSI helpers ──────────────────────────────────────────────────────────────

def _b(t: str) -> str:   return f"\033[1m{t}\033[0m"
def _dim(t: str) -> str: return f"\033[2m{t}\033[0m"
def _grn(t: str) -> str: return f"\033[32m{t}\033[0m"
def _yel(t: str) -> str: return f"\033[33m{t}\033[0m"
def _cyn(t: str) -> str: return f"\033[36m{t}\033[0m"


# ── Markdown → plain text ─────────────────────────────────────────────────────

def _strip_md(text: str) -> str:
    """Minimal markdown → plain text for terminal display."""
    text = re.sub(r"```[\w]*\n(.*?)```", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    return text.strip()


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _load_project(project_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, idea, status FROM projects WHERE id = ?", (project_id,)
        )
        row = await cur.fetchone()
    if not row:
        return None
    return {"id": row[0], "idea": row[1], "status": row[2]}


async def _list_projects() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, idea, status, updated_at "
            "FROM projects ORDER BY created_at DESC LIMIT 20"
        )
        rows = await cur.fetchall()
    return [
        {"id": r[0], "idea": r[1], "status": r[2], "updated_at": r[3]}
        for r in rows
    ]


async def _add_cost(project_id: str, cost_usd: float) -> None:
    cents = int(round(cost_usd * 100))
    if cents <= 0:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET cost_cents = cost_cents + ?, updated_at = ? WHERE id = ?",
            (cents, datetime.utcnow().isoformat(), project_id),
        )
        await db.commit()


async def _set_idea(project_id: str, idea: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET idea = ?, updated_at = ? WHERE id = ?",
            (idea.strip(), datetime.utcnow().isoformat(), project_id),
        )
        await db.commit()


def _persona_for(status: str) -> str:
    if status == ProjectStatus.SHAPING.value:
        return "shaper"
    if status in (ProjectStatus.STAGE1_DONE.value, ProjectStatus.FAILED.value):
        return "refiner"
    return "narrator"


# ── One chat turn ─────────────────────────────────────────────────────────────

async def _turn(project_id: str, user_text: str) -> str | None:
    """Run one Lead chat turn.  Returns a revision_request string if the Lead
    suggested one, otherwise None."""
    # Import here to avoid slow startup when just listing projects.
    from backend.agents.lead import LeadAgent

    project = await _load_project(project_id)
    if not project:
        print(_yel("  [project not found]"))
        return None

    persona = _persona_for(project["status"])
    history = await load_messages(project_id)
    user_msg = await append_message(project_id, ChatRole.USER, user_text)

    print(_dim("  Lead is thinking…"))
    lead = LeadAgent()
    reply = await lead.chat(history=history, user_message=user_text, persona=persona)

    await append_message(project_id, ChatRole.LEAD, reply.display_text)

    if reply.cost_usd:
        await _add_cost(project_id, reply.cost_usd)

    print()
    print(_b("Lead:"))
    print(_strip_md(reply.display_text))
    print()

    if reply.brief_ready and reply.brief_text:
        await _set_idea(project_id, reply.brief_text)
        print(_grn("  [Brief saved — type /launch when ready to start Stage 1]"))

    if reply.note_queued:
        await add_note(project_id, reply.note_queued, source_msg_id=user_msg.id)
        print(_yel(f"  [Note queued: {reply.note_queued[:80]}]"))

    if reply.revision_request:
        print(_cyn(f"  [Revision suggested: {reply.revision_request[:100]}]"))
        print(_cyn("  Type /apply to apply it, or continue chatting to ignore."))

    return reply.revision_request


# ── Special commands ──────────────────────────────────────────────────────────

async def _cmd_status(project_id: str) -> None:
    p = await _load_project(project_id)
    if not p:
        print(_yel("  [not found]"))
        return
    print(_b(f"  Status: {p['status']}"))
    idea = (p["idea"] or "").strip()
    if idea:
        print(f"  Brief:  {idea[:100]}{'…' if len(idea) > 100 else ''}")
    persona = _persona_for(p["status"])
    print(_dim(f"  Persona: {persona}"))


async def _cmd_notes(project_id: str) -> None:
    notes = await list_notes(project_id, NoteStatus.PENDING)
    if not notes:
        print(_dim("  No pending notes."))
    else:
        for n in notes:
            print(f"  [{n.id}] {n.content[:80]}")


async def _cmd_launch(project_id: str) -> None:
    """Transition shaping → planning and start Stage 1 as a background task."""
    from backend.engine.wave_engine import run_stage1

    p = await _load_project(project_id)
    if not p:
        print(_yel("  [project not found]"))
        return
    if p["status"] != ProjectStatus.SHAPING.value:
        print(_yel(f"  [can only launch from shaping — current: {p['status']}]"))
        return
    idea = (p["idea"] or "").strip()
    if not idea:
        print(_yel("  [no brief yet — chat with the Lead first to set it]"))
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            (ProjectStatus.PLANNING.value, datetime.utcnow().isoformat(), project_id),
        )
        await db.commit()

    print(_grn("  [Stage 1 starting — watch the browser dashboard for progress]"))
    print(_dim("  Keep this terminal open while agents run."))
    asyncio.create_task(run_stage1(idea, bus=None, existing_project_id=project_id))


async def _cmd_apply(project_id: str, pending: list[str]) -> None:
    """Apply the most recent pending revision suggestion."""
    from backend.engine.wave_engine import run_revision
    from backend.models.project import AgentRole

    if not pending:
        print(_yel("  [no pending revision — ask the Lead for a suggestion first]"))
        return

    instruction = pending.pop()
    p = await _load_project(project_id)
    if not p or p["status"] != ProjectStatus.STAGE1_DONE.value:
        status = p["status"] if p else "unknown"
        print(_yel(f"  [revisions only work in stage1_done — current: {status}]"))
        return

    default_roles = [
        AgentRole.PRD, AgentRole.ARCHITECT, AgentRole.BACKEND_DOC,
        AgentRole.FRONTEND_DOC, AgentRole.SECURITY_DOC,
        AgentRole.UI_DESIGN_DOC, AgentRole.SCREENS_DOC,
    ]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
            (ProjectStatus.STAGE1_RUNNING.value, datetime.utcnow().isoformat(), project_id),
        )
        await db.commit()

    print(_grn("  [Revision started — watch the browser dashboard for progress]"))
    print(_dim("  Keep this terminal open while agents run."))
    asyncio.create_task(run_revision(project_id, instruction, default_roles, bus=None))


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main() -> int:
    await init_db()

    # ── Pick a project ────────────────────────────────────────────────────────
    if len(sys.argv) >= 2:
        project_id = sys.argv[1]
        project = await _load_project(project_id)
        if not project:
            print(f"Project '{project_id}' not found in {DB_PATH}.")
            return 1
    else:
        projects = await _list_projects()
        if not projects:
            print("No projects found. Create one via the web UI first.")
            return 1
        print(_b("Recent projects:"))
        for i, p in enumerate(projects):
            title = (p["idea"] or "(no brief yet)")[:60]
            print(f"  {i + 1}. [{p['status']}] {title}  {_dim(p['id'])}")
        print()
        try:
            choice = input("Pick a number (or paste a project ID): ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            return 0
        if choice.lower() in ("q", "quit", "exit", "/quit", "/exit"):
            return 0
        elif choice.isdigit() and 1 <= int(choice) <= len(projects):
            project_id = projects[int(choice) - 1]["id"]
        else:
            project_id = choice
        project = await _load_project(project_id)
        if not project:
            print(f"Project '{project_id}' not found.")
            return 1

    # ── Greeting ──────────────────────────────────────────────────────────────
    print()
    print(_b("Mini Orchestrator — terminal chat"))
    print(_dim(f"Project: {project_id}"))
    await _cmd_status(project_id)
    print()
    print(_dim("Commands: /status  /notes  /launch  /apply  /quit"))
    print(_dim("Ctrl+C to exit.  Browser dashboard works in parallel."))
    print()

    pending_revision: list[str] = []  # stack — newest first

    # ── REPL ──────────────────────────────────────────────────────────────────
    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not user_input:
            continue

        lc = user_input.lower()
        if lc in ("/quit", "/exit", "quit", "exit"):
            break
        elif lc == "/status":
            await _cmd_status(project_id)
        elif lc == "/notes":
            await _cmd_notes(project_id)
        elif lc == "/launch":
            await _cmd_launch(project_id)
        elif lc == "/apply":
            await _cmd_apply(project_id, pending_revision)
        else:
            revision = await _turn(project_id, user_input)
            if revision:
                pending_revision.append(revision)

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
