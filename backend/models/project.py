"""Domain models for projects, waves, tasks, artifacts, and reviews."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    # Stage 1 doc roles
    PRD = "prd"
    ARCHITECT = "architect"
    BACKEND_DOC = "backend_doc"
    FRONTEND_DOC = "frontend_doc"
    SECURITY_DOC = "security_doc"
    DEVOPS_DOC = "devops_doc"
    UI_DESIGN_DOC = "ui_design_doc"
    SCREENS_DOC = "screens_doc"
    REVIEWER = "reviewer"
    # Coordination
    LEAD = "lead"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    BLOCKED = "blocked"
    FLAGGED = "flagged"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class ProjectStatus(str, Enum):
    SHAPING = "shaping"            # pre-run conversation with Lead; brief is being drafted
    PLANNING = "planning"          # Lead is computing the wave DAG
    STAGE1_RUNNING = "stage1_running"
    STAGE1_REVIEW = "stage1_review"
    STAGE1_DONE = "stage1_done"
    FAILED = "failed"


class WaveStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Project(BaseModel):
    id: str
    idea: str                                   # "" while in shaping
    status: ProjectStatus = ProjectStatus.SHAPING
    output_dir: str
    cost_cents: int = 0                         # accumulated equivalent cost across the run
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatRole(str, Enum):
    USER = "user"
    LEAD = "lead"


class ChatMessage(BaseModel):
    id: Optional[int] = None            # DB autoincrement, absent before insert
    project_id: str
    role: ChatRole
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class NoteStatus(str, Enum):
    PENDING = "pending"
    ABSORBED = "absorbed"
    DROPPED = "dropped"


class Note(BaseModel):
    id: str                             # note-<hex>
    project_id: str
    content: str
    source_msg_id: Optional[int] = None
    status: NoteStatus = NoteStatus.PENDING
    absorbed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WavePlan(BaseModel):
    """Lead's plan for Stage 1 — list of waves, each a list of roles."""
    waves: list[list[AgentRole]]


class Wave(BaseModel):
    id: str
    project_id: str
    number: int
    roles: list[AgentRole]
    status: WaveStatus = WaveStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class DocTask(BaseModel):
    """A Stage 1 doc-generation task."""
    id: str
    project_id: str
    wave_id: str
    role: AgentRole
    status: TaskStatus = TaskStatus.PENDING
    artifact_id: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class Artifact(BaseModel):
    """Metadata for a generated engineering doc.

    The actual markdown content lives on disk (see engine.artifact_store) —
    read it via `read_artifact(project_id, filename)` rather than carrying
    large strings through this model.
    """
    id: str
    project_id: str
    role: AgentRole
    filename: str  # e.g. PRD.md, ARCHITECTURE.md
    version: int = 1  # bumped on rework
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewIssue(BaseModel):
    severity: Literal["low", "medium", "high"]
    category: str  # e.g. "api_consistency", "data_model", "security"
    affected_artifacts: list[str]  # filenames
    description: str
    suggested_fix: str


class ReviewReport(BaseModel):
    overall_verdict: Literal["approved", "needs_rework"]
    summary: str
    issues: list[ReviewIssue] = []
