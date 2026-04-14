/* Thin typed wrapper around the backend REST endpoints.
 * Calls are same-origin via the Vite dev proxy (/api -> http://localhost:8000).
 */

export interface ProjectSummary {
  id: string;
  idea: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface Wave {
  id: string;
  number: number;
  roles: string[];
  status: "pending" | "running" | "done" | "failed";
  is_rework: boolean;
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

export const api = {
  listProjects: () => get<ProjectSummary[]>("/api/projects"),
  getProject: (id: string) => get<ProjectDetail>(`/api/projects/${id}`),
  getArtifacts: (id: string) =>
    get<ArtifactMeta[]>(`/api/projects/${id}/artifacts`),
  getArtifactContent: (id: string, filename: string) =>
    getText(`/api/projects/${id}/artifacts/${filename}`),
  getReview: (id: string) => get<ReviewReport>(`/api/projects/${id}/review`),
  createProject: (idea: string) =>
    post<{ project_id: string }, { idea: string }>("/api/projects", { idea }),
};
