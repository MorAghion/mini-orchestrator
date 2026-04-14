"""Configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "3"))
AGENT_MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-6")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(BASE_DIR, "tasks")
DATA_DIR = os.path.join(BASE_DIR, "data")
# Runtime output for real orchestrator runs. Override via OUTPUT_DIR env var
# (e.g. tests/smoke_runs for end-to-end tests of the orchestrator itself).
OUTPUT_DIR = os.getenv("OUTPUT_DIR") or os.path.join(BASE_DIR, "backend", "output")
DB_PATH = os.path.join(DATA_DIR, "orchestrator.db")
