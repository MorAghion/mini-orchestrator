import { useEffect, useState } from "react";
import { api, DocTask } from "./api/client";
import { ActivityPanel } from "./components/ActivityPanel";
import { ArtifactViewer } from "./components/ArtifactViewer";
import { Board } from "./components/Board";
import { ProjectForm } from "./components/ProjectForm";
import { ReviewPanel } from "./components/ReviewPanel";
import { Stage, StageTabs } from "./components/StageTabs";
import { useEventStream } from "./hooks/useEventStream";
import { useProject } from "./hooks/useProject";
import { useTheme } from "./hooks/useTheme";
import { PROJECT_STATUS_LABEL, phaseLabelFor } from "./labels";

/** Single-page app: project selector / creator, then board view with live SSE. */
export function App() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [openTask, setOpenTask] = useState<DocTask | null>(null);
  const [stage, setStage] = useState<Stage>("documents");

  const { events, connected } = useEventStream(projectId);
  // Re-fetch project detail whenever a relevant event arrives
  const { data, refetch } = useProject(projectId, events.length);

  useEffect(() => {
    // Nothing selected on load — user goes through ProjectForm or picks existing
  }, []);

  if (!projectId) {
    return (
      <div className="app">
        <Header />
        <ProjectList onPick={setProjectId} onNew={() => setProjectId("__new")} />
      </div>
    );
  }

  if (projectId === "__new") {
    return (
      <div className="app">
        <Header />
        <ProjectForm onCreated={(id) => setProjectId(id)} />
      </div>
    );
  }

  return (
    <div className="app">
      <Header
        right={
          <button
            className="btn"
            onClick={() => {
              setProjectId(null);
              setOpenTask(null);
            }}
          >
            ← Back to projects
          </button>
        }
      />
      <div className="app-main">
        <div className="main-column">
          <StageTabs current={stage} onChange={setStage} />
          {data ? (
            <Board detail={data} onTaskClick={setOpenTask} />
          ) : (
            <div className="board">
              <div style={{ color: "var(--text-muted)", padding: 16 }}>
                Loading project…
              </div>
            </div>
          )}
        </div>
        <div className="side-panel">
          <ActivityPanel events={events} connected={connected} />
          <ReviewPanel projectId={projectId} tick={events.length} />
        </div>
      </div>

      {openTask && (
        <ArtifactViewer
          projectId={projectId}
          task={openTask}
          onClose={() => {
            setOpenTask(null);
            refetch();
          }}
        />
      )}
    </div>
  );
}

function Header({ right }: { right?: React.ReactNode }) {
  const { theme, toggle } = useTheme();
  return (
    <div className="app-header">
      <div>
        <h1>Mini Orchestrator</h1>
        <div className="subtitle">Turn an idea into engineering design docs</div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        {right}
        <button
          className="theme-toggle"
          onClick={toggle}
          aria-label={`switch to ${theme === "dark" ? "light" : "dark"} theme`}
          title={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
        >
          {theme === "dark" ? "☾" : "☀"}
        </button>
      </div>
    </div>
  );
}

function ProjectList({
  onPick,
  onNew,
}: {
  onPick: (id: string) => void;
  onNew: () => void;
}) {
  const [projects, setProjects] = useState<
    { id: string; idea: string; status: string; updated_at: string }[] | null
  >(null);

  useEffect(() => {
    api.listProjects().then(setProjects);
  }, []);

  return (
    <div className="form-panel">
      <h2>Projects</h2>
      <p>Pick an existing run or start a new one.</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {projects === null && (
          <div style={{ color: "var(--text-muted)" }}>Loading…</div>
        )}
        {projects?.length === 0 && (
          <div style={{ color: "var(--text-muted)" }}>No projects yet.</div>
        )}
        {projects?.map((p) => (
          <button
            key={p.id}
            className="btn"
            onClick={() => onPick(p.id)}
            style={{ textAlign: "left" }}
          >
            <div style={{ fontSize: 13, fontWeight: 500 }}>
              {p.idea.length > 90 ? p.idea.slice(0, 89) + "…" : p.idea}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
              {phaseLabelFor(p.status)} ·{" "}
              {PROJECT_STATUS_LABEL[p.status] ?? p.status} ·{" "}
              {new Date(p.updated_at).toLocaleString()}
            </div>
          </button>
        ))}
      </div>
      <div className="actions">
        <button className="btn btn-primary" onClick={onNew}>
          + New project
        </button>
      </div>
    </div>
  );
}
