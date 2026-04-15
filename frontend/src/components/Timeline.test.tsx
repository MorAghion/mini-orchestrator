import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewReport } from "../api/client";
import { OrchestratorEvent } from "../hooks/useEventStream";
import { Timeline, buildTimeline } from "./Timeline";

// Mock the api so the Timeline doesn't try a real fetch on mount.
vi.mock("../api/client", () => ({
  api: { getReview: vi.fn() },
}));

import { api } from "../api/client";
const mockedGetReview = api.getReview as unknown as ReturnType<typeof vi.fn>;


function ev(type: string, ts: string, data: Record<string, unknown> = {}): OrchestratorEvent {
  return { type, project_id: "p1", data, timestamp: ts };
}

describe("buildTimeline (pure)", () => {
  it("returns empty for no events", () => {
    expect(buildTimeline([], null)).toEqual([]);
  });

  it("converts each known event type into a labeled entry", () => {
    const events: OrchestratorEvent[] = [
      ev("project:created", "2026-01-01T10:00:00", { idea: "build a TODO app" }),
      ev("project:planned", "2026-01-01T10:01:00", { waves: [["prd"], ["architect"]] }),
      ev("wave:started", "2026-01-01T10:02:00", { number: 1, roles: ["prd"] }),
      ev("task:completed", "2026-01-01T10:03:00", { role: "prd" }),
      ev("review:approved", "2026-01-01T10:04:00", { issue_count: 0, summary: "ok" }),
      ev("project:completed", "2026-01-01T10:05:00", { total_artifacts: 8 }),
    ];
    const out = buildTimeline(events, null);

    // All 6 events become entries (we don't drop any of these).
    expect(out).toHaveLength(6);

    const texts = out.map((e) => e.primary).join(" | ");
    expect(texts).toContain("Project created");
    expect(texts).toContain("planned 2 waves");
    expect(texts).toContain("Wave 1 started");
    expect(texts).toContain("Product Requirements done");
    expect(texts).toContain("Reviewer agent: approved");
    expect(texts).toContain("Stage 1 complete");
  });

  it("orders entries newest-first", () => {
    const events: OrchestratorEvent[] = [
      ev("project:created", "2026-01-01T10:00:00"),
      ev("project:planned", "2026-01-01T10:01:00", { waves: [] }),
      ev("project:completed", "2026-01-01T10:02:00", { total_artifacts: 0 }),
    ];
    const out = buildTimeline(events, null);
    // First entry is the newest (project:completed at 10:02)
    expect(out[0].primary).toContain("Stage 1 complete");
    expect(out[2].primary).toContain("Project created");
  });

  it("silences task:started and wave:completed (too noisy)", () => {
    const events: OrchestratorEvent[] = [
      ev("task:started", "2026-01-01T10:00:00", { role: "prd" }),
      ev("wave:completed", "2026-01-01T10:01:00", { wave_id: "w1" }),
    ];
    expect(buildTimeline(events, null)).toEqual([]);
  });

  it("labels rework + revision waves with their distinct icons", () => {
    const events: OrchestratorEvent[] = [
      ev("wave:started", "2026-01-01T10:00:00", {
        number: 6, roles: ["prd"], rework: true,
      }),
      ev("wave:started", "2026-01-01T10:01:00", {
        number: 7, roles: ["prd", "frontend_doc"], revision: true,
      }),
    ];
    const out = buildTimeline(events, null);
    // Ordering: revision (newer) first
    expect(out[0].icon).toBe("✎");
    expect(out[0].primary).toContain("Revision wave");
    expect(out[0].category).toBe("revision");
    expect(out[1].icon).toBe("↻");
    expect(out[1].primary).toContain("Rework wave");
    expect(out[1].category).toBe("rework");
  });

  it("attaches review report detail only to the latest review entry", () => {
    const events: OrchestratorEvent[] = [
      ev("review:approved", "2026-01-01T10:00:00", { issue_count: 0 }),
      ev("review:needs_rework", "2026-01-01T10:05:00", { issue_count: 3 }),
    ];
    const report: ReviewReport = {
      overall_verdict: "needs_rework",
      summary: "found things",
      issues: [
        {
          severity: "high", category: "x",
          affected_artifacts: ["BACKEND.md"],
          description: "d", suggested_fix: "f",
        },
      ],
    };
    const out = buildTimeline(events, report);
    // Newest first → out[0] is the needs_rework one (gets the detail)
    expect(out[0].primary).toContain("needs rework");
    expect(out[0].detail).toBeTruthy();
    // The earlier approved one has no detail (no historical reports retained)
    expect(out[1].primary).toContain("approved");
    expect(out[1].detail).toBeUndefined();
  });

  it("formats task error entries with the error excerpt", () => {
    const events: OrchestratorEvent[] = [
      ev("task:error", "2026-01-01T10:00:00", {
        role: "frontend_doc",
        error: "claude exited 1: timeout",
      }),
    ];
    const out = buildTimeline(events, null);
    expect(out[0].category).toBe("error");
    expect(out[0].icon).toBe("⚠");
    expect(out[0].primary).toContain("Frontend Design errored");
    expect(out[0].primary).toContain("timeout");
  });
});


describe("<Timeline />", () => {
  beforeEach(() => {
    mockedGetReview.mockReset();
    mockedGetReview.mockResolvedValue(null);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders empty state when no events", () => {
    render(
      <Timeline
        projectId="p1"
        events={[]}
        connected={true}
        reviewTick={0}
      />,
    );
    expect(screen.getByText(/Nothing yet/)).toBeInTheDocument();
  });

  it("renders timestamps and icons for each entry", () => {
    const events: OrchestratorEvent[] = [
      ev("project:created", "2026-01-01T14:30:00"),
    ];
    render(
      <Timeline
        projectId="p1"
        events={events}
        connected={true}
        reviewTick={0}
      />,
    );
    expect(screen.getByText("🚀")).toBeInTheDocument();
    expect(screen.getByText("Project created")).toBeInTheDocument();
    // Time formatted as HH:MM (locale-dependent but deterministic in CI)
    expect(screen.getByText(/14:30|2:30/)).toBeInTheDocument();
  });

  it("review entry expands on click to reveal issue list", async () => {
    mockedGetReview.mockResolvedValueOnce({
      overall_verdict: "needs_rework",
      summary: "missing things",
      issues: [
        {
          severity: "high", category: "user_note_missing",
          affected_artifacts: ["PRD.md"],
          description: "dark mode not in PRD",
          suggested_fix: "add a section",
        },
      ],
    } as ReviewReport);

    const events: OrchestratorEvent[] = [
      ev("review:needs_rework", "2026-01-01T10:00:00", { issue_count: 1, summary: "x" }),
    ];

    render(
      <Timeline
        projectId="p1"
        events={events}
        connected={false}
        reviewTick={1}
      />,
    );

    // Wait for the async useEffect getReview to resolve (next tick)
    await new Promise((r) => setTimeout(r, 0));

    // Click the review row
    fireEvent.click(screen.getByRole("button", { name: /Reviewer agent/i }));
    expect(screen.getByText(/dark mode not in PRD/)).toBeInTheDocument();
    expect(screen.getByText(/add a section/)).toBeInTheDocument();
  });

  it("non-review entries have no chevron + are not clickable to expand", () => {
    const events: OrchestratorEvent[] = [
      ev("task:completed", "2026-01-01T10:00:00", { role: "prd" }),
    ];
    render(
      <Timeline projectId="p1" events={events} connected={true} reviewTick={0} />,
    );
    const row = screen.getByRole("button", { name: /Product Requirements done/i });
    expect(row).toBeDisabled();
  });
});
