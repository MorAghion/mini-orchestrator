import { useEffect, useState } from "react";
import { api, DocTask } from "../api/client";

interface Props {
  projectId: string;
  task: DocTask;
  onClose: () => void;
}

const FILENAMES: Record<string, string> = {
  prd: "PRD.md",
  architect: "ARCHITECTURE.md",
  backend_doc: "BACKEND.md",
  frontend_doc: "FRONTEND.md",
  security_doc: "SECURITY.md",
  devops_doc: "ENV.md",
  ui_design_doc: "UI_DESIGN_SYSTEM.md",
  screens_doc: "SCREENS.md",
};

export function ArtifactViewer({ projectId, task, onClose }: Props) {
  const filename = FILENAMES[task.role];
  const [content, setContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!filename || task.status !== "done") return;
    api
      .getArtifactContent(projectId, filename)
      .then((c) => setContent(c))
      .catch((e) => setError(String(e)));
  }, [projectId, filename, task.status]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>
            {filename ?? task.role} · <span style={{ color: "var(--text-muted)", fontSize: 12 }}>{task.status}</span>
          </h3>
          <button className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="modal-body">
          {task.status !== "done" && (
            <div style={{ color: "var(--text-muted)" }}>
              Artifact not available — task is {task.status}.
              {task.error && <pre style={{ marginTop: 12 }}>{task.error}</pre>}
            </div>
          )}
          {task.status === "done" && !content && !error && (
            <div style={{ color: "var(--text-muted)" }}>Loading…</div>
          )}
          {error && (
            <div style={{ color: "var(--security)" }}>Error: {error}</div>
          )}
          {content && <div className="markdown">{content}</div>}
        </div>
      </div>
    </div>
  );
}
