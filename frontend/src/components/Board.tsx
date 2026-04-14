import { ProjectDetail, DocTask, Wave } from "../api/client";

interface Props {
  detail: ProjectDetail;
  onTaskClick: (task: DocTask) => void;
}

export function Board({ detail, onTaskClick }: Props) {
  const { project, waves, tasks } = detail;
  const tasksByWave = groupBy(tasks, (t) => t.wave_id);

  return (
    <div className="board">
      <div className="board-header">
        <div>
          <h2>{truncate(project.idea, 80)}</h2>
          <div className="meta">
            {project.id} · status:&nbsp;
            <strong style={{ color: "var(--gold-active)" }}>
              {project.status}
            </strong>
          </div>
        </div>
        <div className="meta">
          {waves.length} waves · {tasks.length} tasks
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
  return (
    <div className={`wave ${wave.status}`}>
      <div className="wave-header">
        <span className="number">Wave {wave.number}</span>
        <span style={{ color: "var(--text-muted)", fontSize: 11 }}>
          {wave.roles.join(" · ")}
        </span>
        <span className={`status ${wave.status}`}>{wave.status}</span>
      </div>
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
      <div className="role-badge">{labelForRole(task.role)}</div>
      <p className="title">{titleForRole(task.role)}</p>
      <div className="meta">
        {task.status}
        {task.error && <> · {truncate(task.error, 60)}</>}
      </div>
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

function labelForRole(role: string): string {
  const abbrev: Record<string, string> = {
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
  return abbrev[role] ?? role.toUpperCase();
}

function titleForRole(role: string): string {
  const titles: Record<string, string> = {
    prd: "Product Requirements",
    architect: "System Architecture",
    backend_doc: "Backend Design",
    frontend_doc: "Frontend Design",
    security_doc: "Security Design",
    devops_doc: "DevOps / Environments",
    ui_design_doc: "UI Design System",
    screens_doc: "Screen Inventory",
    reviewer: "Consistency Review",
  };
  return titles[role] ?? role;
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}
