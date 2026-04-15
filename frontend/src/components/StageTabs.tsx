/* Top-of-board tabs separating the orchestrator's two stages.
 * Documents = Stage 1 (PRD + engineering docs). Currently the only active stage.
 * Code      = Stage 2 (coding agents + sprints). Disabled until Phase 5 lands.
 */

export type Stage = "documents" | "code";

interface Props {
  current: Stage;
  onChange: (s: Stage) => void;
}

export function StageTabs({ current, onChange }: Props) {
  return (
    <div className="stage-tabs" role="tablist">
      <button
        role="tab"
        aria-selected={current === "documents"}
        className={`stage-tab ${current === "documents" ? "active" : ""}`}
        onClick={() => onChange("documents")}
      >
        <span className="stage-tab-label">Documents</span>
        <span className="stage-tab-sub">Idea → 8 design docs</span>
      </button>
      <button
        role="tab"
        aria-selected={current === "code"}
        className="stage-tab disabled"
        disabled
        title="Available once Stage 2 ships"
      >
        <span className="stage-tab-label">Code</span>
        <span className="stage-tab-sub">Docs → working product · coming soon</span>
      </button>
    </div>
  );
}
