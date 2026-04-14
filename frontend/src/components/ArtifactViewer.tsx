import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, DocTask } from "../api/client";
import { ROLE_FILENAME, ROLE_TITLE, TASK_STATUS_LABEL } from "../labels";

interface Props {
  projectId: string;
  task: DocTask;
  onClose: () => void;
}

export function ArtifactViewer({ projectId, task, onClose }: Props) {
  const filename = ROLE_FILENAME[task.role];
  const [content, setContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!filename || task.status !== "done") return;
    api
      .getArtifactContent(projectId, filename)
      .then((c) => setContent(c))
      .catch((e) => setError(String(e)));
  }, [projectId, filename, task.status]);

  // ESC closes the modal
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h3>{ROLE_TITLE[task.role] ?? task.role}</h3>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
              {filename} · {TASK_STATUS_LABEL[task.status] ?? task.status}
            </div>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="close">
            ✕
          </button>
        </div>
        <div className="modal-body">
          {task.status !== "done" && (
            <div style={{ color: "var(--text-muted)" }}>
              Artifact not available — task is{" "}
              {TASK_STATUS_LABEL[task.status] ?? task.status}.
              {task.error && <pre style={{ marginTop: 12 }}>{task.error}</pre>}
            </div>
          )}
          {task.status === "done" && !content && !error && (
            <div style={{ color: "var(--text-muted)" }}>Loading…</div>
          )}
          {error && (
            <div style={{ color: "var(--security)" }}>Error: {error}</div>
          )}
          {content && (
            <div className="prose">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
