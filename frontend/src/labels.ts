/* User-facing labels for roles, statuses, and project phases.
 * Keeping them in one module so we only re-word things once.
 */

export const ROLE_TITLE: Record<string, string> = {
  prd: "Product Requirements",
  architect: "System Architecture",
  backend_doc: "Backend Design",
  frontend_doc: "Frontend Design",
  security_doc: "Security Design",
  devops_doc: "DevOps & Environments",
  ui_design_doc: "UI Design System",
  screens_doc: "Screen Inventory",
  reviewer: "Consistency Review",
};

export const ROLE_BADGE: Record<string, string> = {
  prd: "PRD",
  architect: "ARCH",
  backend_doc: "BE",
  frontend_doc: "FE",
  security_doc: "SEC",
  devops_doc: "OPS",
  ui_design_doc: "UI",
  screens_doc: "SCR",
  reviewer: "REV",
};

export const ROLE_FILENAME: Record<string, string> = {
  prd: "PRD.md",
  architect: "ARCHITECTURE.md",
  backend_doc: "BACKEND.md",
  frontend_doc: "FRONTEND.md",
  security_doc: "SECURITY.md",
  devops_doc: "ENV.md",
  ui_design_doc: "UI_DESIGN_SYSTEM.md",
  screens_doc: "SCREENS.md",
};

/** Friendly labels for backend project statuses. */
export const PROJECT_STATUS_LABEL: Record<string, string> = {
  created: "Created",
  planning: "Planning the work",
  stage1_running: "Generating documents",
  stage1_review: "Reviewing for consistency",
  stage1_done: "Documents complete",
  failed: "Failed",
};

/** Friendly labels for task/wave statuses. */
export const TASK_STATUS_LABEL: Record<string, string> = {
  pending: "waiting",
  running: "running",
  done: "done",
  error: "error",
  blocked: "blocked",
  flagged: "flagged",
};

/** Top-level phase names for the UI — plain English, no "Stage 1". */
export const PHASE_LABEL: Record<string, string> = {
  documents: "Documents generation",
  execution: "Code execution", // for later Stage 2
};

/** Human-readable description of a project's current phase. */
export function phaseLabelFor(status: string): string {
  // All stage1_* statuses live under the "Documents generation" phase.
  if (status === "created" || status === "planning") return "Planning";
  if (status.startsWith("stage1")) return PHASE_LABEL.documents;
  if (status === "failed") return "Failed";
  return status;
}
