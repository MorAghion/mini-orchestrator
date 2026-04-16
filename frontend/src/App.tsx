import { useEffect, useMemo, useState } from "react";
import { api, DocTask, OrchestratorEvent, ProjectStatus, ProjectSummary } from "./api/client";
import { ArtifactViewer } from "./components/ArtifactViewer";
import { Board } from "./components/Board";
import { Chat } from "./components/Chat";
import { PendingNotes } from "./components/PendingNotes";
import { Stage, StageTabs } from "./components/StageTabs";
import { Timeline } from "./components/Timeline";
import { useChat } from "./hooks/useChat";
import { useEventStream } from "./hooks/useEventStream";
import { useNotes } from "./hooks/useNotes";
import { useProject } from "./hooks/useProject";
import { useTheme } from "./hooks/useTheme";
import { PROJECT_STATUS_LABEL, phaseLabelFor } from "./labels";

export function App() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [listKey, setListKey] = useState(0);
  const [openTask, setOpenTask] = useState<DocTask | null>(null);
  const [stage, setStage] = useState<Stage>("documents");
  const [launching, setLaunching] = useState(false);
  const [pendingRevision, setPendingRevision] = useState<string | null>(null);
  const [applyingRevision, setApplyingRevision] = useState(false);

  const { events, connected } = useEventStream(projectId);
  const { data, refetch } = useProject(projectId, events.length);
  const { messages, sending, send, refresh: refreshChat } = useChat(projectId);
  const { notes, drop: dropNote, refresh: refreshNotes } = useNotes(
    projectId,
    events.length,
  );

  const status: ProjectStatus = data?.project.status ?? "shaping";

  // Merge DB-loaded event history with live SSE events. History gives us
  // events from before this browser session; sseEvents adds events that
  // fired after we connected. Deduplicate by timestamp+type in case the
  // SSE connection was established just as history was loaded.
  const allEvents = useMemo(() => {
    const seen = new Set<string>();
    const merged: OrchestratorEvent[] = [
      ...(data?.events ?? []),
      ...events,
    ];
    return merged.filter((e) => {
      const key = `${e.timestamp}|${e.type}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [data?.events, events]);

  // When the Lead emits BRIEF_READY the idea gets saved; the next refetch
  // will reflect that. Trigger one now so the UI updates immediately.
  const handleSend = async (content: string) => {
    const reply = await send(content);
    if (reply?.brief_ready || reply?.note_queued) {
      await refetch();
      await refreshNotes();
    }
    // Surface the revision suggestion (Lead's REVISION_REQUEST marker).
    // Newest one wins; user can dismiss with Skip if not interested.
    if (reply?.revision_request) {
      setPendingRevision(reply.revision_request);
    }
  };

  const handleLaunch = async () => {
    if (!projectId) return;
    setLaunching(true);
    try {
      await api.launchProject(projectId);
      await refetch();
      await refreshChat();
    } finally {
      setLaunching(false);
    }
  };

  const handleApplyRevision = async (instruction: string) => {
    if (!projectId) return;
    setApplyingRevision(true);
    try {
      await api.reviseProject(projectId, instruction);
      setPendingRevision(null);
      // /revise schedules a background task; SSE events stream wave/task
      // updates and useProject refreshes via events.length tick.
      await refetch();
    } finally {
      setApplyingRevision(false);
    }
  };

  if (!projectId) {
    return (
      <div className="app">
        <Header />
        <ProjectList key={listKey} onPick={setProjectId} onCreate={setProjectId} />
      </div>
    );
  }

  const readyToLaunch =
    status === "shaping" && (data?.project.idea ?? "").trim().length > 0;

  return (
    <div className="app">
      <Header
        right={
          <>
            <CostIndicator cents={data?.project.cost_cents ?? 0} />
            <button
              className="btn"
              onClick={() => {
                setProjectId(null);
                setOpenTask(null);
                setListKey((k) => k + 1);
              }}
            >
              ← Back
            </button>
          </>
        }
      />
      <div className="app-main">
        <div className="main-column">
          <StageTabs current={stage} onChange={setStage} />
          {data ? (
            status === "shaping" ? (
              <ShapingBoard idea={data.project.idea} />
            ) : (
              <Board detail={data} onTaskClick={setOpenTask} />
            )
          ) : (
            <div className="board">
              <div style={{ color: "var(--text-muted)", padding: 16 }}>
                Loading project…
              </div>
            </div>
          )}
        </div>
        <div className="side-panel">
          <Chat
            status={status}
            messages={messages}
            sending={sending}
            onSend={handleSend}
            phaseLabel={phaseLabelFor(status)}
            readyToLaunch={readyToLaunch}
            onLaunch={handleLaunch}
            launching={launching}
            pendingRevision={pendingRevision}
            onApplyRevision={handleApplyRevision}
            onDismissRevision={() => setPendingRevision(null)}
            applyingRevision={applyingRevision}
          />
          <PendingNotes notes={notes} onDrop={dropNote} />
          {status !== "shaping" && (
            <Timeline
              projectId={projectId}
              events={allEvents}
              connected={connected}
              reviewTick={allEvents.length}
              status={status}
            />
          )}
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

/** Placeholder board shown while the project is still in shaping phase. */
function ShapingBoard({ idea }: { idea: string }) {
  return (
    <div className="board">
      <div className="board-header">
        <div>
          <div className="phase-label">Shaping the brief</div>
          <h2>
            {idea
              ? idea.length > 80
                ? idea.slice(0, 79) + "…"
                : idea
              : "No brief yet — chat with the Lead on the right"}
          </h2>
          <div className="meta" style={{ marginTop: 6 }}>
            Once the Lead proposes a brief you approve, you'll get a "Launch
            Stage 1" button below the chat. Stage 1 then runs 8 specialist
            agents and produces design docs.
          </div>
        </div>
      </div>
      {idea && (
        <div
          style={{
            background: "var(--bg-sprint-row)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: 14,
            marginTop: 10,
          }}
        >
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: 0.5,
              textTransform: "uppercase",
              color: "var(--gold-active)",
              marginBottom: 6,
            }}
          >
            Proposed brief
          </div>
          <div style={{ fontSize: 13, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
            {idea}
          </div>
        </div>
      )}
    </div>
  );
}

function CostIndicator({ cents }: { cents: number }) {
  const dollars = (cents / 100).toFixed(2);
  return (
    <div
      className="cost-indicator"
      title={
        `You paid: $0 (Claude Max is a flat subscription). ` +
        `This project would cost ~$${dollars} if billed via the Anthropic API instead. ` +
        `We show the API-equivalent so you can gauge how much quota the run burned.`
      }
    >
      <span className="cost-you-pay">$0</span>
      <span className="cost-caption">
        paid · <span className="cost-equiv">~${dollars} API equiv</span>
      </span>
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
  onCreate,
}: {
  onPick: (id: string) => void;
  onCreate: (id: string) => void;
}) {
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.listProjects().then(setProjects);
  }, []);

  const handleNew = async () => {
    setCreating(true);
    try {
      const { project_id } = await api.createProject();
      onCreate(project_id);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="form-panel">
      <h2>Projects</h2>
      <p>
        Start a new project by chatting with the Lead, or pick up an existing
        run.
      </p>
      <div className="actions" style={{ justifyContent: "flex-start", margin: "4px 0 18px" }}>
        <button className="btn btn-primary" onClick={handleNew} disabled={creating}>
          {creating ? "Creating…" : "+ Start new project"}
        </button>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {projects === null && (
          <div style={{ color: "var(--text-muted)" }}>Loading…</div>
        )}
        {projects?.length === 0 && (
          <div style={{ color: "var(--text-muted)" }}>
            No projects yet. Click <strong>Start new project</strong> above.
          </div>
        )}
        {projects?.map((p) => {
          const title = p.idea?.trim() || "(untitled — brief not yet set)";
          return (
            <button
              key={p.id}
              className="btn"
              onClick={() => onPick(p.id)}
              style={{ textAlign: "left" }}
            >
              <div style={{ fontSize: 13, fontWeight: 500 }}>
                {title.length > 90 ? title.slice(0, 89) + "…" : title}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                {phaseLabelFor(p.status)} ·{" "}
                {PROJECT_STATUS_LABEL[p.status] ?? p.status} ·{" "}
                <span
                  title={`You paid $0 under Max. Equivalent API cost: ~$${(p.cost_cents / 100).toFixed(2)}`}
                >
                  $0 paid
                </span>{" "}
                · {new Date(p.updated_at).toLocaleString()}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
