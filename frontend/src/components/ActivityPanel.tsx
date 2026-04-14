import { OrchestratorEvent } from "../hooks/useEventStream";

interface Props {
  events: OrchestratorEvent[];
  connected: boolean;
}

export function ActivityPanel({ events, connected }: Props) {
  return (
    <div className="panel">
      <h3>
        Lead chat · activity feed{" "}
        <span
          style={{
            fontSize: 10,
            color: connected ? "var(--backend)" : "var(--text-muted)",
            marginLeft: 6,
          }}
        >
          ● {connected ? "live" : "offline"}
        </span>
      </h3>

      <div className="activity">
        {events.length === 0 && (
          <div style={{ color: "var(--text-muted)", fontSize: 12 }}>
            No events yet.
          </div>
        )}
        {[...events].reverse().map((e, i) => (
          <div
            key={`${e.timestamp}-${i}`}
            className={`activity-event ${categoryFor(e.type)}`}
          >
            <div className="event-type">{e.type}</div>
            <div className="event-body">{describe(e)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function categoryFor(type: string): string {
  if (type.startsWith("project:")) return "project";
  if (type.startsWith("wave:")) return "wave";
  if (type.startsWith("task:error")) return "error";
  if (type.startsWith("task:")) return "task";
  if (type.startsWith("artifact:")) return "artifact";
  if (type.startsWith("review:")) return "review";
  return "";
}

function describe(e: OrchestratorEvent): string {
  const d = e.data;
  switch (e.type) {
    case "project:created":
      return `Idea: ${String(d.idea).slice(0, 80)}`;
    case "project:planned":
      return `Lead planned ${(d.waves as string[][])?.length ?? 0} waves`;
    case "project:completed":
      return `All done — ${d.total_artifacts ?? "?"} artifacts${
        Array.isArray(d.reworked_roles) && d.reworked_roles.length > 0
          ? `, ${d.reworked_roles.length} reworked`
          : ""
      }`;
    case "project:failed":
      return `Failed: ${d.reason ?? "unknown"}`;
    case "wave:started":
      return `Wave ${d.number}: ${(d.roles as string[])?.join(", ")}${
        d.rework ? " (rework)" : ""
      }`;
    case "wave:completed":
      return `Wave done: ${d.status}`;
    case "task:started":
      return `${d.role} started`;
    case "task:completed":
      return `${d.role} finished`;
    case "task:error":
      return `${d.role} errored: ${String(d.error).slice(0, 80)}`;
    case "artifact:created":
      return `${d.filename} v${d.version}`;
    case "review:approved":
      return `Review: approved — ${d.issue_count} minor issues`;
    case "review:needs_rework":
      return `Review: needs rework — ${d.issue_count} issues`;
    default:
      return JSON.stringify(d).slice(0, 100);
  }
}
