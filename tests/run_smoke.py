"""End-to-end smoke test for the orchestrator.

Runs the full Stage 1 pipeline against a short project idea and writes the
artifacts under `tests/smoke_runs/<project_id>/`. No assertions — this is a
diagnostic runner meant to be inspected by hand. Use it to verify that a
change to the orchestrator hasn't broken the end-to-end flow.

Usage:
    python -m tests.run_smoke                    # default idea
    python -m tests.run_smoke "your idea here"
"""

from __future__ import annotations

import asyncio
import os
import sys

# Point OUTPUT_DIR at tests/smoke_runs BEFORE importing backend.* so config picks it up.
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_SMOKE_DIR = os.path.join(_TESTS_DIR, "smoke_runs")
os.makedirs(_SMOKE_DIR, exist_ok=True)
os.environ["OUTPUT_DIR"] = _SMOKE_DIR

from backend.database import init_db  # noqa: E402  (after env var set)
from backend.engine.wave_engine import run_stage1  # noqa: E402

DEFAULT_IDEA = "A simple todo app with user auth, tags, and due dates"


async def main() -> int:
    idea = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IDEA
    await init_db()
    result = await run_stage1(idea)
    print(f"\n[smoke] idea:       {idea!r}")
    print(f"[smoke] project id: {result.project.id}")
    print(f"[smoke] output:     {_SMOKE_DIR}/{result.project.id}/docs")
    print(f"[smoke] verdict:    {result.report.overall_verdict}")
    print(f"[smoke] issues:     {len(result.report.issues)}")
    if result.reworked_roles:
        print(f"[smoke] reworked:   {[r.value for r in result.reworked_roles]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
