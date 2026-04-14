"""Configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "3"))
AGENT_MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-4-20250514")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(BASE_DIR, "tasks")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "backend", "output")
DB_PATH = os.path.join(DATA_DIR, "orchestrator.db")
