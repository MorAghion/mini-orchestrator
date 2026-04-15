import { useState } from "react";
import { DocTask, ProjectDetail, Wave } from "../api/client";
import {
  PROJECT_STATUS_LABEL,
  ROLE_BADGE,
  ROLE_TITLE,
  TASK_STATUS_LABEL,
  phaseLabelFor,
} from "../labels";

interface Props {
  detail: ProjectDetail;
  onTaskClick: (task: DocTask) => void;
}

export function Board({ detail, onTaskClick }: Props) {
  const { project, waves, tasks } = detail;
  const tasksByWave = groupBy(tasks, (t) => t.wave_id);
  const doneCount = tasks.filter((t) => t.status === "done").length;

  return (
    <div className="board">
      <div className="board-header">
        <div>
          <div className="phase-label">{phaseLabelFor(project.status)}</div>
          <h2>{truncate(project.idea, 80)}</h2>
          <div className="meta">
            {PROJECT_STATUS_LABEL[project.status] ?? project.status} ·{" "}
            {doneCount}/{tasks.length} agents done
          </div>
        </div>
        <div className="meta">
          {project.id}
        </div>
      </div>

      {waves.length === 0 && (
        <div style={{ padding: 20, color: "var(--text-muted)" }}>
          Waiting for the Lead to plan waves…
        </div>
      )}

      {waves.map((wave) => (
        <WaveRow
          key={wave.id}
          wave={wave}
          tasks={tasksByWave.get(wave.id) ?? []}
          onTaskClick={onTaskClick}
        />
      ))}
    </div>
  );
}

function WaveRow({
  wave,
  tasks,
  onTaskClick,
}: {
  wave: Wave;
  tasks: DocTask[];
  onTaskClick: (t: DocTask) => void;
}) {
  // Collapse done waves by default; active ones stay expanded.
  const isActive = wave.status === "running" || tasks.some((t) => t.status === "running");
  const hasError = tasks.some((t) => t.status === "error");
  const [expanded, setExpanded] = useState(isActive || hasError || wave.status !== "done");
  const doneCount = tasks.filter((t) => t.status === "done").length;

  const kindClass = wave.is_revision
    ? " wave-revision"
    : wave.is_rework
      ? " wave-rework"
      : "";

  return (
    <div
      className={`wave ${wave.status}${expanded ? "" : " collapsed"}${kindClass}`}
    >
      <div
        className="wave-header"
        role="button"
        tabIndex={0}
        onClick={() => setExpanded((x) => !x)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setExpanded((x) => !x);
          }
        }}
        aria-expanded={expanded}
        aria-label={`Wave ${wave.number}, ${expanded ? "collapse" : "expand"}`}
      >
        <span className="toggle-indicator">{expanded ? "▾" : "▸"}</span>
        <div className="wave-title">
          <div className="wave-title-row">
            <span className="number">
              {wave.is_revision
                ? "User revision wave"
                : wave.is_rework
                  ? "Rework wave"
                  : `Wave ${wave.number}`}
            </span>
            {wave.is_revision && (
              <span className="revision-badge">✎ User revision</span>
            )}
            {wave.is_rework && !wave.is_revision && (
              <span className="rework-badge">↻ Fix pass</span>
            )}
            <span className="wave-roles">
              {wave.roles.map((r) => ROLE_BADGE[r] ?? r).join(" · ")}
            </span>
          </div>
          {wave.is_revision ? (
            <div className="wave-subtitle">
              {wave.instruction ? (
                <>
                  <span className="wave-instruction-label">Your request:</span>{" "}
                  <span className="wave-instruction">
                    &ldquo;{wave.instruction}&rdquo;
                  </span>
                </>
              ) : (
                "You requested a change — these agents re-ran with your instruction and the Reviewer agent re-checked."
              )}
            </div>
          ) : wave.is_rework ? (
            <div className="wave-subtitle">
              Reviewer agent marked issues — these agents re-ran to address
              the feedback.
            </div>
          ) : null}
        </div>
        <span className="meta-right">
          {doneCount}/{tasks.length || wave.roles.length}
        </span>
        <span className={`status ${wave.status}`}>{wave.status}</span>
      </div>
      {expanded && (
        <div className="wave-tasks">
          {tasks.length === 0 && (
            <div
              style={{
                color: "var(--text-muted)",
                fontSize: 12,
                padding: "6px 0",
              }}
            >
              Not started
            </div>
          )}
          {tasks.map((t) => (
            <TaskCard key={t.id} task={t} onClick={() => onTaskClick(t)} />
          ))}
        </div>
      )}
    </div>
  );
}

function TaskCard({
  task,
  onClick,
}: {
  task: DocTask;
  onClick: () => void;
}) {
  return (
    <div
      className={`card role-${task.role} status-${task.status}`}
      onClick={onClick}
    >
      <div className="card-top-row">
        <span className="role-badge">{ROLE_BADGE[task.role] ?? task.role}</span>
        <span className={`status-chip ${task.status}`}>
          {TASK_STATUS_LABEL[task.status] ?? task.status}
        </span>
      </div>
      <p className="title">{ROLE_TITLE[task.role] ?? task.role}</p>
      {task.error && (
        <div className="meta">{truncate(task.error, 60)}</div>
      )}
    </div>
  );
}

function groupBy<T, K>(items: T[], key: (t: T) => K): Map<K, T[]> {
  const map = new Map<K, T[]>();
  for (const item of items) {
    const k = key(item);
    const arr = map.get(k);
    if (arr) arr.push(item);
    else map.set(k, [item]);
  }
  return map;
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}
