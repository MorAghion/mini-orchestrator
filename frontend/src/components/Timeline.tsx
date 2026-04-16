/* Project timeline — single merged panel that replaces the old separate
 * ActivityPanel (raw SSE events) + ReviewPanel (verdict + issues).
 *
 * Why merged: when the Reviewer flags issues and rework agents fix them,
 * those events belong next to each other so the user can see cause → effect.
 * Splitting them across panels orphaned the "fix" from its "find".
 *
 * Each row is one event with:
 *   • an icon prefix indicating the source (👁 reviewer, 🔧 agent, 🌊 wave, …)
 *   • a timestamp (the user can tell read direction: top = newest)
 *   • a short human line; reviewer entries expand to show issues
 */

import { useEffect, useState } from "react";
import { api, ReviewReport } from "../api/client";
import { OrchestratorEvent } from "../hooks/useEventStream";
import { ROLE_TITLE } from "../labels";

interface Props {
  projectId: string | null;
  events: OrchestratorEvent[];
  connected: boolean;
  /** Bumped by the parent on every event tick; we use it to refetch the
   * review report when a new review event lands. */
  reviewTick: number;
  /** Current project status — used to skip the review fetch when no report
   * exists yet (avoids a spurious 404 during stage1_running / stage1_review).
   * Defaults to "" (unknown) — safe: review will only be fetched once a review
   * SSE event has been seen. */
  status?: string;
}

export function Timeline({ projectId, events, connected, reviewTick, status = "" }: Props) {
  const [report, setReport] = useState<ReviewReport | null>(null);

  // Only fetch the review report when one is known to exist: either the
  // project has finished Stage 1 (review_report.json is on disk), or a
  // review SSE event has arrived in this session (covers mid-run rework cycles).
  // Skipping it during stage1_running / stage1_review avoids a spurious 404.
  const hasSeenReview = events.some((e) => e.type.startsWith("review:"));
  const reviewExists = status === "stage1_done" || hasSeenReview;

  useEffect(() => {
    if (!projectId || !reviewExists) return;
    api
      .getReview(projectId)
      .then(setReport)
      .catch(() => setReport(null));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, reviewTick, reviewExists]);

  const entries = buildTimeline(events, report);

  return (
    <div className="panel timeline-panel">
      <div className="timeline-header">
        <h3>
          Project history{" "}
          <span
            className="timeline-conn"
            style={{ color: connected ? "var(--backend)" : "var(--text-muted)" }}
          >
            ● {connected ? "live" : "offline"}
          </span>
        </h3>
        <span className="timeline-direction">↓ newest</span>
      </div>

      {entries.length === 0 && (
        <div className="timeline-empty">
          Nothing yet. The Lead's first move appears here once Stage 1 launches.
        </div>
      )}

      <div className="timeline-list">
        {entries.map((e) => (
          <TimelineRow key={e.id} entry={e} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One row
// ---------------------------------------------------------------------------

function TimelineRow({ entry }: { entry: TimelineEntry }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = entry.detail !== undefined;

  return (
    <div className={`tl-row tl-${entry.category}`}>
      <button
        className="tl-row-main"
        onClick={() => hasDetail && setExpanded((x) => !x)}
        disabled={!hasDetail}
        aria-expanded={hasDetail ? expanded : undefined}
      >
        <span className="tl-icon" aria-hidden>
          {entry.icon}
        </span>
        <span className="tl-time" title={entry.ts.toLocaleString()}>
          {formatTime(entry.ts)}
        </span>
        <span className="tl-text">{entry.primary}</span>
        {hasDetail && (
          <span className="tl-chev" aria-hidden>
            {expanded ? "▾" : "▸"}
          </span>
        )}
      </button>
      {hasDetail && expanded && <div className="tl-detail">{entry.detail}</div>}
    </div>
  );
}

function formatTime(d: Date): string {
  // HH:MM, 24h. Compact and unambiguous for read direction.
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

// ---------------------------------------------------------------------------
// Build the merged timeline
// ---------------------------------------------------------------------------

type Category =
  | "project"
  | "wave"
  | "task"
  | "review"
  | "revision"
  | "rework"
  | "error";

interface TimelineEntry {
  id: string;
  ts: Date;
  category: Category;
  icon: string;
  primary: string;
  detail?: React.ReactNode;
}

export function buildTimeline(
  events: OrchestratorEvent[],
  report: ReviewReport | null,
): TimelineEntry[] {
  const out: TimelineEntry[] = [];
  let lastReviewIdx: number | null = null;

  events.forEach((e, i) => {
    const ts = new Date(e.timestamp);
    const id = `${e.timestamp}-${i}-${e.type}`;

    switch (e.type) {
      case "project:created": {
        const idea = String((e.data as { idea?: string }).idea ?? "");
        out.push({
          id,
          ts,
          category: "project",
          icon: "🚀",
          primary: idea ? `Project created — "${truncate(idea, 60)}"` : "Project created",
        });
        break;
      }
      case "project:planned": {
        const waves = (e.data as { waves?: string[][] }).waves ?? [];
        out.push({
          id,
          ts,
          category: "project",
          icon: "🧠",
          primary: `Lead planned ${waves.length} wave${waves.length === 1 ? "" : "s"}`,
        });
        break;
      }
      case "project:completed":
        out.push({
          id,
          ts,
          category: "project",
          icon: "✅",
          primary: `Stage 1 complete — ${(e.data as { total_artifacts?: number }).total_artifacts ?? "?"} artifacts`,
        });
        break;
      case "project:failed":
        out.push({
          id,
          ts,
          category: "error",
          icon: "✗",
          primary: `Project failed: ${(e.data as { reason?: string }).reason ?? "unknown"}`,
        });
        break;
      case "wave:started": {
        const data = e.data as {
          number?: number;
          roles?: string[];
          rework?: boolean;
          revision?: boolean;
          instruction?: string;
        };
        const kind = data.revision ? "Revision wave" : data.rework ? "Rework wave" : `Wave ${data.number}`;
        const cat: Category = data.revision ? "revision" : data.rework ? "rework" : "wave";
        const icon = data.revision ? "✎" : data.rework ? "↻" : "🌊";
        // For revision waves, prefer the instruction itself over the role
        // dump — user wants to identify each revision by what they asked for.
        const tail =
          data.revision && data.instruction
            ? `“${truncate(data.instruction, 60)}”`
            : (data.roles ?? []).join(", ");
        out.push({
          id,
          ts,
          category: cat,
          icon,
          primary: `${kind} started — ${tail}`,
        });
        break;
      }
      case "wave:completed":
        // Skip — wave:started + per-task done already tells the story.
        break;
      case "task:started":
        // Skip — too noisy; we only show the completion to keep the list scannable.
        break;
      case "task:completed": {
        const role = String((e.data as { role?: string }).role ?? "");
        out.push({
          id,
          ts,
          category: "task",
          icon: "🔧",
          primary: `${ROLE_TITLE[role] ?? role} done`,
        });
        break;
      }
      case "task:error": {
        const role = String((e.data as { role?: string }).role ?? "");
        const err = String((e.data as { error?: string }).error ?? "");
        out.push({
          id,
          ts,
          category: "error",
          icon: "⚠",
          primary: `${ROLE_TITLE[role] ?? role} errored: ${truncate(err, 60)}`,
        });
        break;
      }
      case "review:approved":
      case "review:needs_rework": {
        const data = e.data as { issue_count?: number; summary?: string };
        const verdict = e.type === "review:approved" ? "approved" : "needs rework";
        out.push({
          id,
          ts,
          category: "review",
          icon: "👁",
          primary: `Reviewer agent: ${verdict} — ${data.issue_count ?? 0} issue${data.issue_count === 1 ? "" : "s"}`,
          // Detail attached below once we know which review entry is the latest.
        });
        lastReviewIdx = out.length - 1;
        break;
      }
      // artifact:created — silenced for the timeline; task:completed already
      // covers it. We can resurface if users want per-artifact granularity.
    }
  });

  // Attach the live ReviewReport detail to the most recent review entry only
  // — older review entries (from a prior review/revision cycle) stay
  // collapsed without expandable detail since we don't keep historical
  // reports on disk yet.
  if (lastReviewIdx !== null && report) {
    out[lastReviewIdx].detail = <ReviewDetail report={report} />;
  }

  // Newest first — sort descending by timestamp. The header reads "↓ newest".
  out.sort((a, b) => b.ts.getTime() - a.ts.getTime());
  return out;
}

function ReviewDetail({ report }: { report: ReviewReport }) {
  if (report.issues.length === 0) {
    return <div className="tl-review-summary">{report.summary}</div>;
  }
  // Sort issues by severity: high first, then medium, then low.
  const order = { high: 0, medium: 1, low: 2 };
  const issues = [...report.issues].sort((a, b) => order[a.severity] - order[b.severity]);
  return (
    <div className="tl-review-detail">
      <div className="tl-review-summary">{report.summary}</div>
      <ul className="tl-issues">
        {issues.map((issue, i) => (
          <li key={i} className={`tl-issue tl-issue-${issue.severity}`}>
            <span className="tl-issue-sev">{issue.severity}</span>
            <span className="tl-issue-cat">{issue.category}</span>
            <div className="tl-issue-body">{issue.description}</div>
            <div className="tl-issue-fix">
              <strong>Fix:</strong> {issue.suggested_fix}
            </div>
            {issue.affected_artifacts.length > 0 && (
              <div className="tl-issue-affected">
                Affects: {issue.affected_artifacts.join(", ")}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}
