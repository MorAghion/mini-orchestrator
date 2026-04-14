import { useState } from "react";
import { api } from "../api/client";

interface Props {
  onCreated: (projectId: string) => void;
}

export function ProjectForm({ onCreated }: Props) {
  const [idea, setIdea] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!idea.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const { project_id } = await api.createProject(idea.trim());
      onCreated(project_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <div className="form-panel">
      <h2>New project</h2>
      <p>
        Describe the product you want to build. The orchestrator generates eight
        engineering design docs (PRD, Architecture, Backend, Frontend, Security,
        DevOps, UI system, Screens), runs them through a consistency reviewer,
        and patches any issues in a single rework cycle.
      </p>
      <form onSubmit={handleSubmit}>
        <textarea
          placeholder="e.g. A pomodoro timer web app with user accounts and streak tracking"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          disabled={busy}
        />
        {error && (
          <p style={{ color: "var(--security)", marginTop: 8 }}>{error}</p>
        )}
        <div className="actions">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={busy || !idea.trim()}
          >
            {busy ? "Starting…" : "Run Stage 1"}
          </button>
        </div>
      </form>
    </div>
  );
}
