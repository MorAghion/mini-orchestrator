/* Thin typed wrapper around the backend REST endpoints.
 * Calls are same-origin via the Vite dev proxy (/api -> http://localhost:8000).
 */

export interface OrchestratorEvent {
  type: string;
  project_id: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export type ProjectStatus =
  | "shaping"
  | "planning"
  | "stage1_running"
  | "stage1_review"
  | "stage1_done"
  | "failed";

export interface ProjectSummary {
  id: string;
  idea: string;
  status: ProjectStatus;
  cost_cents: number;
  created_at: string;
  updated_at: string;
}

export interface Wave {
  id: string;
  number: number;
  roles: string[];
  status: "pending" | "running" | "done" | "failed";
  is_rework: boolean;
  is_revision: boolean;
  instruction: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface DocTask {
  id: string;
  wave_id: string;
  role: string;
  status: "pending" | "running" | "done" | "error" | "blocked" | "flagged";
  artifact_id: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface ProjectDetail {
  project: ProjectSummary & { output_dir: string };
  waves: Wave[];
  tasks: DocTask[];
  /** Full event history loaded from DB — used to populate the Timeline on
   * initial load so history survives page refreshes. Live SSE events are
   * merged on top of this in App.tsx. */
  events: OrchestratorEvent[];
}

export interface ArtifactMeta {
  id: string;
  role: string;
  filename: string;
  version: number;
  created_at: string;
}

export interface ReviewIssue {
  severity: "low" | "medium" | "high";
  category: string;
  affected_artifacts: string[];
  description: string;
  suggested_fix: string;
}

export interface ReviewReport {
  overall_verdict: "approved" | "needs_rework";
  summary: string;
  issues: ReviewIssue[];
}

export interface ChatMessage {
  id: number;
  role: "user" | "lead";
  content: string;
  created_at: string;
}

export interface ChatReply {
  user_message_id: number;
  lead_message_id: number;
  display_text: string;
  brief_ready: boolean;
  note_queued: string | null;
  revision_request: string | null;
  cost_usd: number;
}

export interface Note {
  id: string;
  content: string;
  source_msg_id: number | null;
  status: "pending" | "absorbed" | "dropped";
  created_at: string;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function getText(path: string): Promise<string> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.text();
}

async function post<T, B>(path: string, body: B): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function del(path: string): Promise<void> {
  const res = await fetch(path, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`DELETE ${path} → ${res.status}`);
  }
}

export const api = {
  // Projects
  listProjects: () => get<ProjectSummary[]>("/api/projects"),
  getProject: (id: string) => get<ProjectDetail>(`/api/projects/${id}`),
  createProject: (idea?: string) =>
    post<{ project_id: string; status: ProjectStatus }, { idea?: string }>(
      "/api/projects",
      idea ? { idea } : {},
    ),
  launchProject: (id: string, idea?: string) =>
    post<{ project_id: string; status: string }, { idea?: string }>(
      `/api/projects/${id}/launch`,
      idea ? { idea } : {},
    ),
  reviseProject: (
    id: string,
    instruction: string,
    affectedRoles?: string[],
  ) =>
    post<
      { project_id: string; status: string; affected_roles: string[] },
      { instruction: string; affected_roles?: string[] }
    >(`/api/projects/${id}/revise`, {
      instruction,
      ...(affectedRoles ? { affected_roles: affectedRoles } : {}),
    }),

  // Artifacts
  getArtifacts: (id: string) =>
    get<ArtifactMeta[]>(`/api/projects/${id}/artifacts`),
  getArtifactContent: (id: string, filename: string) =>
    getText(`/api/projects/${id}/artifacts/${filename}`),
  getReview: (id: string) => get<ReviewReport>(`/api/projects/${id}/review`),

  // Chat
  getChatHistory: (id: string) =>
    get<ChatMessage[]>(`/api/projects/${id}/chat`),
  sendChat: (id: string, content: string) =>
    post<ChatReply, { content: string }>(`/api/projects/${id}/chat`, {
      content,
    }),

  // Notes queue
  getNotes: (id: string) => get<Note[]>(`/api/projects/${id}/notes`),
  addNote: (id: string, content: string) =>
    post<Note, { content: string }>(`/api/projects/${id}/notes`, { content }),
  deleteNote: (projectId: string, noteId: string) =>
    del(`/api/projects/${projectId}/notes/${noteId}`),
};
