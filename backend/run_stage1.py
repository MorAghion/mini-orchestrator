"""Stage 1 CLI runner.

Usage:
    python -m backend.run_stage1 "Todo app with auth"
    python -m backend.run_stage1 --idea-file path/to/idea.txt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from backend.config import DATA_DIR, OUTPUT_DIR
from backend.database import init_db
from backend.engine.artifact_store import docs_dir
from backend.engine.wave_engine import run_stage1


def _parse_args() -> str:
    parser = argparse.ArgumentParser(description="Run Stage 1 doc generation.")
    parser.add_argument("idea", nargs="?", help="Project idea, as a string.")
    parser.add_argument("--idea-file", help="Path to a file containing the project idea.")
    args = parser.parse_args()
    if args.idea_file:
        with open(args.idea_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    if args.idea:
        return args.idea
    parser.error("Provide an idea as an argument or use --idea-file.")


async def main() -> int:
    idea = _parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await init_db()

    print(f"[stage1] idea: {idea!r}")
    result = await run_stage1(idea)

    print(f"\n[stage1] project id: {result.project.id}")
    print(f"[stage1] docs at:    {docs_dir(result.project.id)}")
    print(f"[stage1] verdict:    {result.report.overall_verdict}")
    print(f"[stage1] issues:     {len(result.report.issues)}")
    if result.reworked_roles:
        print(f"[stage1] reworked:   {[r.value for r in result.reworked_roles]}")
    for role, content in result.artifacts.items():
        print(f"  - {role.value}: {len(content)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
